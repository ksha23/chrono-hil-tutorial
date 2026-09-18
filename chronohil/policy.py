# =============================================================================
# PROJECT CHRONO - http://projectchrono.org
#
# Copyright (c) 2026 projectchrono.org
# All rights reserved.
#
# Use of this source code is governed by a BSD-style license that can be found
# in the LICENSE file at the top level of the distribution and at
# http://projectchrono.org/license-chrono.txt.
# =============================================================================
"""A trained locomotion policy, driving the joints through a PD actuator."""

import os

from .chrono_env import chrono
from .paths import GO2_POLICY

GO2_POLICY_PATHS = (
    os.environ.get("GO2_POLICY_CKPT", ""),
    GO2_POLICY,
)


def find_go2_policy():
    """The vendored checkpoint, or whatever GO2_POLICY_CKPT names. Nothing else.

    This used to end with a path to a checkpoint on the author's machine. When
    the vendored one could not be found the demo silently ran a FINE-TUNED
    policy instead of the baseline, which stands 20 cm lower and falls over to a
    push the baseline shrugs off. A missing checkpoint must look missing.
    """
    for q in GO2_POLICY_PATHS:
        if q and os.path.exists(q):
            return q
    return None


class Go2Policy:
    """A trained locomotion policy, driving the joints through a PD actuator.

    NONE OF THESE CONVENTIONS ARE OURS and none of them are negotiable: they
    belong to the harness the checkpoint was trained in, and each one silently
    corrupts the observation if it is wrong, which shows up as a robot that
    twitches and falls rather than as an error. They are taken from NeDM's
    imported_policy.py, which derived them against the checkpoint's own config.

        joint order    the policy counts FL, FR, RL, RR; the URDF gives us
                       RR, RL, FR, FL, hence TO_POLICY
        sign           joint angles and targets are NEGATED between the two
        defaults       hips are +/-0.1, not 0, and front and rear thighs differ
        observation    45, not the base config's 48: there is no base linear
                       velocity block, which is exactly why this checkpoint
                       ports to another simulator at all
        rates          the POLICY runs at 50 Hz; the PD underneath it runs every
                       physics step. A PD evaluated only at the policy rate is a
                       different controller and this policy would not survive it.

    Unlike the stance holder, this one can pick a foot up, so a shove it cannot
    simply stiffen against is answered by stepping.
    """

    NAMES = ["RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
             "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
             "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
             "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"]
    TO_POLICY = [9, 10, 11, 6, 7, 8, 3, 4, 5, 0, 1, 2]
    SIGN = -1.0
    # The gains every legged_gym-family Go2 config specifies, and what this
    # checkpoint assumes. Matching them is the point: a policy from that family
    # assumes this actuator, so tuning them to suit a particular checkpoint
    # would defeat the reason for having them.
    KP = float(os.environ.get("GO2_POLICY_KP", "20.0"))
    KD = float(os.environ.get("GO2_POLICY_KD", "0.5"))
    CTRL_DT = 0.02               # 50 Hz policy, decimation 4 over their 200 Hz PD
    ANG_VEL_SCALE = 0.25
    DOF_VEL_SCALE = 0.05
    ACTION_SCALE = 0.25

    def __init__(self, system, parser, ckpt, command=(0.0, 0.0, 0.0)):
        import numpy as np
        import torch
        self.np, self.torch = np, torch
        self.DEFAULTS = np.array([0.1, 0.8, -1.5, -0.1, 0.8, -1.5,
                                  0.1, 1.0, -1.5, -0.1, 1.0, -1.5], dtype=np.float32)
        self.EFFORT = np.array([23.7, 23.7, 45.43] * 4)   # URDF <limit effort>
        self.CMD_SCALE = np.array([2.0, 2.0, 0.25], dtype=np.float32)
        self.model = torch.jit.load(str(ckpt), map_location="cpu")
        self.model.eval()
        self.system = system
        self.motors, self.fns = [], []
        for n in self.NAMES:
            m = chrono.CastToChLinkMotorRotationTorque(parser.GetChMotor(n))
            if m is None:
                raise RuntimeError(f"no torque motor for {n}")
            fn = chrono.ChFunctionConst(0.0)
            m.SetMotorFunction(fn)
            self.motors.append(m)
            self.fns.append(fn)
        self.base = parser.GetChBody("base")
        self.command = np.array(command, dtype=np.float32)
        self.last_actions = np.zeros(12, dtype=np.float32)
        self.target = self.default_targets()
        self.next_ctrl = 0.0
        # SETTLE FIRST, THEN HAND OVER. The URDF spawns every joint at zero,
        # which is nowhere near the pose this policy was ever shown: its
        # observation block is (q - defaults), so at t=0 that is a whole radian
        # of error on eight joints and the network is being asked about a robot
        # it has never seen. Handed the scene in that state it diverges -- feet
        # four metres up, robot inverted. A second of plain PD onto the default
        # pose puts the first real observation inside the distribution.
        # Their handover, not ours: ramp the joints to a stand over RAMP seconds,
        # hold it for SETTLE, and only then let the network drive. Stepping
        # straight to the pose, or handing over from the spawn pose, puts the
        # first observation outside anything the policy was trained on and it
        # diverges -- feet metres in the air within two seconds.
        self.ramp = 0.75
        self.settle = 0.5
        self.q0 = None
        # The scripted stand. Hips at 0, which is NOT the policy's own zero-action
        # pose (+/-0.1); this is the pose their collector ramps to.
        self.stand = self.np.array([0.0, -1.0, 1.5, 0.0, -1.0, 1.5,
                                    0.0, -0.8, 1.5, 0.0, -0.8, 1.5])

    # -- conventions ---------------------------------------------------------
    def default_targets(self):
        """The policy's rest pose, in Chrono joint order and Chrono's sign."""
        out = self.np.zeros(12)
        out[self.TO_POLICY] = self.DEFAULTS
        return self.SIGN * out

    @staticmethod
    def _projected_gravity(q):
        """Gravity in the base frame: what the policy uses instead of a pose."""
        qw, qx, qy, qz = q.e0, q.e1, q.e2, q.e3
        return [-2.0 * (qx * qz - qw * qy),
                -2.0 * (qy * qz + qw * qx),
                -(1.0 - 2.0 * (qx * qx + qy * qy))]

    def _q(self):
        np = self.np
        return (np.array([m.GetMotorAngle() for m in self.motors], dtype=np.float32),
                np.array([m.GetMotorAngleDt() for m in self.motors], dtype=np.float32))

    def observe(self):
        """ang_vel(3) | gravity(3) | command(3) | dof_pos(12) | dof_vel(12) | prev(12)"""
        np = self.np
        w = self.base.GetAngVelLocal()
        ang = np.array([w.x, w.y, w.z], dtype=np.float32) * self.ANG_VEL_SCALE
        grav = np.array(self._projected_gravity(self.base.GetRot()), dtype=np.float32)
        cmd = self.command * self.CMD_SCALE
        qc, qdc = self._q()
        q = self.SIGN * qc[self.TO_POLICY]
        qd = self.SIGN * qdc[self.TO_POLICY]
        return np.concatenate([ang, grav, cmd, q - self.DEFAULTS,
                               qd * self.DOF_VEL_SCALE,
                               self.last_actions]).astype(np.float32)

    # -- the two rates -------------------------------------------------------
    def update(self):
        """Called every physics step: policy at 50 Hz, PD underneath at step rate."""
        t = self.system.GetChTime()
        if self.q0 is None:
            self.q0 = self._q()[0].astype(float)
        if t < self.ramp:
            a = t / self.ramp
            self.target = self.q0 + a * (self.stand - self.q0)
            self.next_ctrl = self.ramp + self.settle
        elif t < self.ramp + self.settle:
            self.target = self.stand
            self.next_ctrl = self.ramp + self.settle
        elif t >= self.next_ctrl:
            self.next_ctrl = t + self.CTRL_DT
            obs = self.torch.from_numpy(self.observe()).unsqueeze(0)
            with self.torch.no_grad():
                action = self.model(obs).squeeze(0).numpy().astype(self.np.float32)
            self.last_actions = action
            targets = action * self.ACTION_SCALE + self.DEFAULTS
            out = self.np.zeros(12)
            out[self.TO_POLICY] = targets
            self.target = self.SIGN * out
        qc, qdc = self._q()
        tau = self.KP * (self.target - qc) - self.KD * qdc
        tau = self.np.clip(tau, -self.EFFORT, self.EFFORT)
        for fn, v in zip(self.fns, tau):
            fn.SetConstant(float(v))
