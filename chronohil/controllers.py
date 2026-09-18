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
"""Small joint-level controllers: what holds a robot up while you pull on it."""

from .chrono_env import chrono

def joint_readers(motor):
    """(position, velocity) readers for a motor, whichever kind it is.

    A revolute joint answers GetMotorAngle and a prismatic one GetMotorPos, and
    a controller written for one silently does nothing for the other. That is
    not hypothetical: the Panda's two finger joints are PRISMATIC, the damper
    loop only ever cast to a rotation motor, so the fingers got no control at
    all -- and ChLinkMotorLinear does not enforce the URDF's travel limits
    either, so they slid along their own axis under gravity and left the hand
    at 3.96 m/s, 80 cm away inside three seconds. A small piece visibly shooting
    off the arm.
    """
    if hasattr(motor, "GetMotorAngle"):
        return motor.GetMotorAngle, motor.GetMotorAngleDt
    return motor.GetMotorPos, motor.GetMotorPosDt


class LimpJoint:
    """An unactuated joint: no control at all, only bearing friction.

    Zero torque would be more literally "unactuated", but a frictionless 7-link
    chain is a chaotic pendulum that swings forever and never settles. Real
    joints have friction, so a little viscous damping is the honest model and it
    lets the arm collapse and come to rest, which is the thing worth watching.
    """

    KD = 1.2
    TAU_MAX = 40.0

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target
        self.pos, self.vel = joint_readers(motor)

    def update(self):
        tau = -self.KD * self.vel()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))


class FreeDriveJoint:
    """Cobot-style free drive: holds its pose, but yields to a sustained push.

    Pure damping is not enough -- an arm under gravity simply falls over, which
    is what the primitive three-link version did. A plain PD holding a fixed
    target is the opposite problem: it springs back and you cannot pose it.

    So the target LAGS the actual angle. Over a short push the joint feels like a
    stiff spring; hold it somewhere for longer than the lag and that becomes the
    new rest pose. This is how a real collaborative arm behaves in hand-guiding
    mode, and it is what "move the arm by hand" needs.
    """

    KP = 400.0     # N.m per rad -- enough to carry the arm's own weight
    KD = 16.0      # N.m per rad/s
    TAU_MAX = 87.0  # N.m, the Panda's largest joint limit
    FOLLOW = 0.004  # per step, and ONLY while something is being held

    # A rest pose that always creeps toward the actual angle droops: gravity
    # walks the arm down and the target follows it. One that never creeps springs
    # back and cannot be posed. Real hand-guiding resolves this by being a MODE:
    # the arm complies while you have hold of it and locks the instant you let
    # go. The loop sets this while the grabber holds something.
    guiding = False

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target
        self.pos, self.vel = joint_readers(motor)

    def update(self):
        q = self.pos()
        if FreeDriveJoint.guiding:
            self.target += (q - self.target) * self.FOLLOW
        tau = self.KP * (self.target - q) - self.KD * self.vel()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))


class LockedJoint:
    """Holds one joint exactly where it started, and never gives ground.

    FreeDriveJoint deliberately lets its target creep toward the joint's actual
    position while something is being held, which is what makes the arm posable
    by hand. Applied to the gripper that is a bug with a plausible face: every
    drag poses the FINGERS a little too, the creep never reverses, and the
    gripper walks shut. Measured at 16.63 mm after twelve seconds of swinging
    the arm around, and still moving.

    So the fingers get this instead. Same idea, no follow term.
    """

    KP = 2000.0    # N per m -- the fingers are 0.1 kg, so this is stiff
    KD = 20.0      # N per m/s
    F_MAX = 70.0   # N, the Panda gripper's own grasp force

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target
        self.pos, self.vel = joint_readers(motor)

    def update(self):
        f = self.KP * (self.target - self.pos()) - self.KD * self.vel()
        self.fn.SetConstant(max(-self.F_MAX, min(self.F_MAX, f)))


class StanceHolder:
    """One joint's PD law: the stand-in for a locomotion policy.

    A real policy would read the whole robot state and emit twelve torques; this
    reads one joint and emits one. What matters for the demo is identical --
    something is actively holding a pose, so a human pulling on a leg is a
    disturbance it has to reject.
    """

    # These have to actually hold the robot up. At KP 26 it sags, topples and
    # ends up on its back with its legs in the air -- and because the legs then
    # hang unloaded, the per-joint error reads LOW, which is a metric that hides
    # exactly the failure it should catch. Check the base height and uprightness
    # instead: standing is z ~ 0.27 with the body z-axis still pointing up.
    KP = 120.0     # N.m per rad
    KD = 4.0       # N.m per rad/s
    TAU_MAX = 60.0  # N.m

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target

    def update(self):
        err = self.target - self.motor.GetMotorAngle()
        tau = self.KP * err - self.KD * self.motor.GetMotorAngleDt()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))
