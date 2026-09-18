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

    def update(self):
        tau = -self.KD * self.motor.GetMotorAngleDt()
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

    def update(self):
        q = self.motor.GetMotorAngle()
        if FreeDriveJoint.guiding:
            self.target += (q - self.target) * self.FOLLOW
        tau = self.KP * (self.target - q) - self.KD * self.motor.GetMotorAngleDt()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))


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
