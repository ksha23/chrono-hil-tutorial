# =============================================================================
# PROJECT CHRONO - http://projectchrono.org
#
# Copyright (c) 2026 projectchrono.org
# All rights reserved.
#
# Use of this source code is governed by a BSD-style license that can be found
# in the LICENSE file at the top level of the distribution and at
# http://projectchrono.org/license-chrono.txt.
#
# =============================================================================
# PART 8 support: control something that isn't a car.
#
# Parts 1-7 put a human in the loop around a Chrono::Vehicle.  Nothing about
# the pattern needs a vehicle, though.  The loop is:
#
#     read three numbers from the human  ->  push them into the model
#     step the model  ->  wait for real time  ->  send some numbers back
#
# and "the model" can be anything Chrono can simulate.  This module has two
# other things to steer, both driven by exactly the same three numbers coming
# from exactly the same devices:
#
#   "rover"  a Viper rover on the same terrain.  Steering and drive speed
#            instead of steering and throttle -- six independently driven
#            wheels, a rocker-bogie suspension, and no gearbox anywhere.
#
#   "crane"  a gantry crane with a payload on a cable.  No Chrono::Vehicle at
#            all: four rigid bodies, two motors and a distance constraint.
#            The payload swings, and damping that swing while placing it is a
#            genuinely hard manual task -- which is the point.  This is the
#            one to try if you want to feel why HIL work is done at all.
#
# All three plants expose the same handful of methods, which is what lets the
# simulation loop in tutorial_HIL_driver.py stay one loop:
#
#     apply(inputs)              push steering/throttle/braking into the model
#     synchronize(t, inputs)     the plant's own Synchronize, if it has one
#     advance(step)              step the plant (the system is stepped by the
#                                caller for plants that do not step themselves)
#     speed()                    m/s, for the console line
#     status()                   a short string, or "" for nothing to add
#     attach(vis)                hook the plant up to a visual system
#
# =============================================================================

import math

import pychrono as chrono
import pychrono.vehicle as veh


# =============================================================================
# The Chrono::Vehicle plant (Parts 1-7)
# =============================================================================


class VehiclePlant:
    """A wheeled Chrono::Vehicle: the plant Parts 1-7 use.

    Thin, because the vehicle model already does everything -- this exists so
    the rover and the crane have something to look like.
    """

    needs_vehicle_vis = True   # wants ChWheeledVehicleVisualSystemIrrlicht
    steps_own_system = True    # vehicle_model.Advance() steps the ChSystem

    def __init__(self, vehicle_model, terrain, gearbox=None):
        self.model = vehicle_model
        self.vehicle = vehicle_model.GetVehicle()
        self.system = vehicle_model.GetSystem()
        self.terrain = terrain
        self.gearbox = gearbox

    def apply(self, inputs):
        pass  # the vehicle reads the inputs in Synchronize

    def synchronize(self, t, inputs):
        self.model.Synchronize(t, inputs, self.terrain)

    def advance(self, step):
        self.model.Advance(step)

    def speed(self):
        return self.vehicle.GetSpeed()

    def status(self):
        return f"gear {self.gearbox.describe()}" if self.gearbox else ""

    def attach(self, vis):
        vis.AttachVehicle(self.vehicle)


# =============================================================================
# The rover plant
# =============================================================================


class RoverPlant:
    """A Viper rover driven by the same three numbers as the car.

    The mapping is the interesting part.  A rover has no throttle and no
    gearbox: its six wheels are speed-controlled motors, so "throttle" becomes
    a commanded wheel speed and "braking" commands zero.  Steering is the one
    input that means the same thing on both plants.

    ViperDCMotorControl models the motor rather than imposing the speed
    outright -- it has a stall torque and a no-load speed, so the rover bogs
    down on a slope exactly as the real thing would.
    """

    needs_vehicle_vis = False  # a plain ChVisualSystemIrrlicht is enough
    steps_own_system = False   # the caller steps the ChSystem

    #: rad/s at full throttle. The Viper's own demos use pi, about 0.5 m/s.
    MAX_WHEEL_SPEED = math.pi

    #: Smallest no-load speed ever commanded, rad/s.
    #: ViperDCMotorControl is a DC motor model: its torque falls off linearly
    #: from the stall torque at rest to zero at the no-load speed, which means
    #: the no-load speed is a divisor. Commanding exactly zero -- which closing
    #: the throttle otherwise would -- makes that 0/0 at rest, and the whole
    #: rover goes to NaN on the first step with no error anywhere. Flooring it
    #: costs nothing physically: at 1e-3 rad/s the motor produces no useful
    #: torque above a standstill, which is what a closed throttle should do.
    MIN_NO_LOAD_SPEED = 1e-3

    #: rad at full lock. Viper::m_max_steer_angle is the hard limit; stay under it.
    MAX_STEER_ANGLE = math.pi / 6

    def __init__(self, system, start, wheel_material=None):
        import pychrono.robot as robot

        self.WHEELS = (robot.V_LF, robot.V_RF, robot.V_LB, robot.V_RB)
        self.system = system
        self.driver = robot.ViperDCMotorControl()
        self.rover = robot.Viper(system)
        self.rover.SetDriver(self.driver)
        if wheel_material is not None:
            self.rover.SetWheelContactMaterial(wheel_material)
        self.rover.Initialize(chrono.ChFramed(start.pos, start.rot))
        self._speed_cmd = 0.0

    def apply(self, inputs):
        # The vehicle driver's steering is normalized to [-1, 1]; the rover's is
        # an actual wheel angle in radians, so this is a scale rather than a
        # pass-through. Getting that wrong is silent: the rover just barely turns.
        self.driver.SetSteering(inputs.m_steering * self.MAX_STEER_ANGLE)
        # Throttle sets the speed the motors will pull up to; braking closes
        # them again. Braking wins, so standing on the brake lets the rover roll
        # to a stop whatever the throttle says.
        #
        # Note what "braking" can and cannot mean here: ViperDriver has no brake
        # input, so this releases the drive rather than applying a friction
        # brake. The rover coasts down on rolling resistance instead of stopping
        # dead, which is the honest behaviour for a machine built this way.
        target = inputs.m_throttle * (1.0 - inputs.m_braking)
        self._speed_cmd = max(target * self.MAX_WHEEL_SPEED, self.MIN_NO_LOAD_SPEED)
        # Per wheel, because a rover can be commanded to skid-steer; here all
        # four get the same command and the steering angles do the turning.
        for wheel in self.WHEELS:
            self.driver.SetMotorNoLoadSpeed(self._speed_cmd, wheel)

    def synchronize(self, t, inputs):
        pass  # the rover has no Synchronize; Update() below does the work

    def advance(self, step):
        self.rover.Update()

    def speed(self):
        v = self.rover.GetChassisVel()
        return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)

    def status(self):
        return f"wheel cmd {self._speed_cmd:5.2f} rad/s"

    def attach(self, vis):
        pass  # nothing to attach: the rover's bodies are already in the system

    def chase_target(self):
        return self.rover.GetChassis().GetBody()


# =============================================================================
# The crane plant
# =============================================================================


class CranePlant:
    """A gantry crane: bridge, trolley, cable and payload.

    No Chrono::Vehicle, no terrain, no tires -- four bodies, two speed motors
    and one distance constraint.  It is here to show that the human-in-the-loop
    pattern is not a Chrono::Vehicle feature: anything Chrono can simulate can
    have a person in its loop, and the plumbing does not change.

        steering  ->  cross-travel, the trolley along the bridge (Y)
        throttle  ->  long-travel forward, the bridge along its rails (X)
        braking   ->  long-travel reverse

    The payload hangs on a cable of fixed length and is free to swing in both
    directions.  Nothing damps it but the operator, which is what makes this a
    real control task rather than a demo: accelerate hard and the load swings,
    and it stays swinging until someone drives the trolley back under it.

    `status()` reports the swing angle, so the console line shows how badly you
    are doing without having to watch the window.
    """

    needs_vehicle_vis = False
    steps_own_system = False

    SPAN = 12.0          # bridge length, m (cross-travel range is +/- SPAN/2)
    RUN = 30.0           # rail length, m
    HEIGHT = 8.0         # bridge height above the ground, m
    CABLE = 5.0          # cable length, m
    MAX_LONG_SPEED = 2.0   # m/s at full throttle
    MAX_CROSS_SPEED = 1.5  # m/s at full steering

    def __init__(self, system, start):
        self.system = system
        z0 = start.pos.z
        x0 = start.pos.x
        y0 = start.pos.y

        ground = chrono.ChBody()
        ground.SetFixed(True)
        ground.EnableCollision(False)
        ground.SetName("crane ground")
        # The rails, drawn only so there is something to judge motion against.
        for side in (-self.SPAN / 2, self.SPAN / 2):
            rail = chrono.ChVisualShapeBox(self.RUN, 0.3, 0.3)
            rail.SetColor(chrono.ChColor(0.35, 0.35, 0.40))
            ground.AddVisualShape(rail, chrono.ChFramed(
                chrono.ChVector3d(x0, y0 + side, z0 + self.HEIGHT + 0.4)))
        system.AddBody(ground)
        self.ground = ground

        # --- bridge: travels along X on the rails ---------------------------
        bridge = chrono.ChBody()
        bridge.SetMass(2000.0)
        bridge.SetInertiaXX(chrono.ChVector3d(4000, 4000, 4000))
        bridge.SetPos(chrono.ChVector3d(x0, y0, z0 + self.HEIGHT))
        bridge.EnableCollision(False)
        bridge.SetName("bridge")
        girder = chrono.ChVisualShapeBox(0.5, self.SPAN, 0.5)
        girder.SetColor(chrono.ChColor(0.80, 0.55, 0.10))
        bridge.AddVisualShape(girder)
        system.AddBody(bridge)
        self.bridge = bridge

        self.long_motor = chrono.ChLinkMotorLinearSpeed()
        # A linear motor slides along the joint frame's Z, so the frame is
        # rotated to put Z along world X.
        self.long_motor.Initialize(
            bridge, ground,
            chrono.ChFramed(bridge.GetPos(), chrono.QuatFromAngleY(chrono.CH_PI_2)))
        self.long_speed = chrono.ChFunctionSetpoint()
        self.long_motor.SetSpeedFunction(self.long_speed)
        system.AddLink(self.long_motor)

        # --- trolley: travels along Y on the bridge --------------------------
        trolley = chrono.ChBody()
        trolley.SetMass(400.0)
        trolley.SetInertiaXX(chrono.ChVector3d(80, 80, 80))
        trolley.SetPos(chrono.ChVector3d(x0, y0, z0 + self.HEIGHT))
        trolley.EnableCollision(False)
        trolley.SetName("trolley")
        cab = chrono.ChVisualShapeBox(0.9, 0.9, 0.6)
        cab.SetColor(chrono.ChColor(0.15, 0.35, 0.75))
        trolley.AddVisualShape(cab)
        system.AddBody(trolley)
        self.trolley = trolley

        self.cross_motor = chrono.ChLinkMotorLinearSpeed()
        self.cross_motor.Initialize(
            trolley, bridge,
            chrono.ChFramed(trolley.GetPos(), chrono.QuatFromAngleX(-chrono.CH_PI_2)))
        self.cross_speed = chrono.ChFunctionSetpoint()
        self.cross_motor.SetSpeedFunction(self.cross_speed)
        system.AddLink(self.cross_motor)

        # --- payload: hangs from the trolley on a cable ----------------------
        payload = chrono.ChBody()
        payload.SetMass(800.0)
        payload.SetInertiaXX(chrono.ChVector3d(60, 60, 60))
        payload.SetPos(chrono.ChVector3d(x0, y0, z0 + self.HEIGHT - self.CABLE))
        payload.EnableCollision(False)
        payload.SetName("payload")
        crate = chrono.ChVisualShapeBox(1.2, 1.2, 1.2)
        crate.SetColor(chrono.ChColor(0.65, 0.16, 0.16))
        payload.AddVisualShape(crate)
        system.AddBody(payload)
        self.payload = payload

        # A distance constraint IS the cable: it holds the payload at a fixed
        # radius from the trolley and lets it swing freely in both directions,
        # which is exactly a spherical pendulum with a moving pivot.
        self.cable = chrono.ChLinkDistance()
        self.cable.Initialize(trolley, payload, False,
                              trolley.GetPos(), payload.GetPos())
        system.AddLink(self.cable)
        # Drawn so the payload is not floating unexplained.
        self.cable_shape = chrono.ChVisualShapeSegment()
        self.cable.AddVisualShape(self.cable_shape)

        # A mark on the ground to aim the payload at.
        target = chrono.ChBody()
        target.SetFixed(True)
        target.EnableCollision(False)
        target.SetName("target")
        pad = chrono.ChVisualShapeCylinder(1.5, 0.05)
        pad.SetColor(chrono.ChColor(0.20, 0.65, 0.25))
        target.AddVisualShape(pad, chrono.ChFramed(
            chrono.ChVector3d(x0 + 10.0, y0 + 3.0, z0 + 0.03)))
        system.AddBody(target)
        self.target_pos = chrono.ChVector3d(x0 + 10.0, y0 + 3.0, z0)

    def apply(self, inputs):
        t = self.system.GetChTime()
        # Throttle drives forward, braking drives back: two pedals, one axis.
        long_cmd = (inputs.m_throttle - inputs.m_braking) * self.MAX_LONG_SPEED
        self.long_speed.SetSetpoint(long_cmd, t)
        self.cross_speed.SetSetpoint(inputs.m_steering * self.MAX_CROSS_SPEED, t)

    def synchronize(self, t, inputs):
        pass

    def advance(self, step):
        pass  # the motors and the constraint are stepped with the system

    def speed(self):
        v = self.payload.GetPosDt()
        return math.sqrt(v.x * v.x + v.y * v.y)

    def swing_angle(self):
        """Cable angle from vertical, in degrees. Zero is a load hanging still."""
        d = self.payload.GetPos() - self.trolley.GetPos()
        horizontal = math.sqrt(d.x * d.x + d.y * d.y)
        return math.degrees(math.atan2(horizontal, max(1e-6, -d.z)))

    def miss_distance(self):
        """How far the payload is from the target pad, in metres."""
        d = self.payload.GetPos() - self.target_pos
        return math.sqrt(d.x * d.x + d.y * d.y)

    def status(self):
        return f"swing {self.swing_angle():5.1f} deg  miss {self.miss_distance():5.2f} m"

    def attach(self, vis):
        pass

    def chase_target(self):
        return self.payload
