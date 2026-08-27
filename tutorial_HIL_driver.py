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
# Tutorial: Chrono support for human-in-the-loop simulation
#
# One script, five parts. Change the switches in the CONFIGURATION section at
# the bottom of the file to move from one part to the next.
#
#   PART 1: Keep the simulation real-time            (INPUT_SOURCE = "data")
#   PART 2: A human on the keyboard                  (INPUT_SOURCE = "keyboard")
#   PART 3: A gamepad or wheel, read natively         (INPUT_SOURCE = "gamepad")
#   PART 4: A device Chrono doesn't know, and         (INPUT_SOURCE = "udp",
#           closing the loop back to it                SEND_FEEDBACK = True)
#   PART 5: Customize the built-in overlay            (SHOW_* switches, VEHICLE)
#
# The vehicle defaults to an HMMWV on flat rigid terrain (same model as
# demo_VEH_HMMWV) but VEHICLE can pick any of a few other Chrono::Vehicle
# models - see build_vehicle() and PART 5 below. The vehicle reference frame
# has Z up, X towards the front of the vehicle, and Y pointing to the left.
# =============================================================================

import math
import socket
import time

import pychrono as chrono
import pychrono.vehicle as veh
import pychrono.irrlicht as irr


# =============================================================================
# PART 1: REAL-TIME ENFORCEMENT
# =============================================================================
#
# Chrono only gives you *soft* real-time: after every step we check how much
# wall-clock time passed and, if the step ran faster than real time, we wait.
# If the step ran SLOWER than real time nothing can be done - the sim falls
# behind (watch the "drift" column in the console).
#
# Three ways to get the same thing:
#   "per_step"   - chrono.ChRealtimeStepTimer().Spin(step)  once per loop
#   "vehicle"    - vehicle.EnableRealtime(True): the vehicle does the above
#                  internally inside vehicle.Advance()
#   "cumulative" - wait until wall time == simulation time (below)
#   "none"       - run as fast as possible (batch mode)


class CumulativeRealtimeTimer:
    """Soft real-time that does not accumulate drift.

    ChRealtimeStepTimer measures each step independently: any time lost on a
    slow step (or spent in Python between steps) is never recovered.  This timer
    instead compares the *total* simulated time with the *total* wall time, so a
    slow step is followed by a few fast steps that catch back up.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.t_start = time.perf_counter()

    def spin(self, sim_time):
        while time.perf_counter() - self.t_start < sim_time:
            pass  # spin in place until real time catches up


# =============================================================================
# PART 3: A GAMEPAD OR WHEEL, READ NATIVELY
# =============================================================================
#
# ChInteractiveDriver already knows how to read a joystick - no pygame, no
# custom polling class.  A JSON config file maps device axes/buttons to
# steering/throttle/braking/clutch/shifting; Chrono ships four presets
# (data/vehicle/joystick/controller_*.json) and you can write your own.
# vis.SetJoystickDebug(True) prints live axis and button numbers twice a
# second - the same job probe_gamepad.py used to do, built in.
#
# =============================================================================
# PART 4: BRING A DEVICE CHRONO DOESN'T KNOW ABOUT
# =============================================================================
#
# The whole "human interface" to a Chrono vehicle is three numbers per step:
#     steering in [-1, 1], throttle in [0, 1], braking in [0, 1]
# ChDriver is a plain container for those numbers with SetSteering(),
# SetThrottle(), SetBraking().  Anything that can produce three floats can
# drive the vehicle - a socket, a phone, a ROS node, another machine on the
# network - Chrono just doesn't ship a reader for it the way it does for a
# joystick, so operator_console.py plays that role here.


class SmoothedInputs:
    """First-order lag from a *target* input to the *applied* input.

    Raw device values should not be teleported into the model: a keypress is a
    step function, and a step in steering excites the suspension and tires in a
    way no human arm ever would.  This mirrors the internal dynamics of
    ChInteractiveDriver (see SetGains) so the behavior is the same whether the
    inputs come from the Irrlicht keyboard handler or from our own device.
    """

    def __init__(self, gain=4.0):
        self.gain = gain
        self.steering = 0.0
        self.throttle = 0.0
        self.braking = 0.0
        self.target = (0.0, 0.0, 0.0)

    def set_target(self, steering, throttle, braking):
        self.target = (
            max(-1.0, min(1.0, steering)),
            max(0.0, min(1.0, throttle)),
            max(0.0, min(1.0, braking)),
        )

    def advance(self, step):
        s, t, b = self.target
        self.steering += min(1.0, self.gain * step) * (s - self.steering)
        self.throttle += min(1.0, self.gain * step) * (t - self.throttle)
        self.braking += min(1.0, self.gain * step) * (b - self.braking)

    def apply_to(self, driver):
        driver.SetSteering(self.steering)
        driver.SetThrottle(self.throttle)
        driver.SetBraking(self.braking)


class UdpInput:
    """Receive 'steering,throttle,braking' text datagrams from an operator.

    Run operator_console.py in another terminal (or on another machine) and
    drive with the arrow keys there.  The socket is non-blocking: the physics
    loop never waits for the operator.  If no packet arrived since the last
    step, the previous target is held (zero-order hold).
    """

    def __init__(self, port=9870):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.setblocking(False)
        self.operator_addr = None
        self.last = (0.0, 0.0, 0.0)
        self.packets = 0
        print(f"[udp] listening on port {port} - start operator_console.py")

    def poll(self):
        # Drain everything that is queued and keep only the newest packet
        while True:
            try:
                data, addr = self.sock.recvfrom(256)
            except BlockingIOError:
                break
            try:
                s, t, b = (float(x) for x in data.decode().split(","))
                self.last = (s, t, b)
                self.operator_addr = addr
                self.packets += 1
            except ValueError:
                pass
        return self.last

    # PART 4: telemetry back to whoever is sending us inputs
    def send_feedback(self, text):
        if self.operator_addr is not None:
            self.sock.sendto(text.encode(), self.operator_addr)


# =============================================================================
# PART 5: CHOOSE YOUR CAR
# =============================================================================
#
# Every "full vehicle" model in Chrono::Vehicle (HMMWV_Full, Sedan, CityBus,
# Gator, ...) exposes the same handful of setup calls and the same
# GetVehicle() / GetSystem() / Synchronize() / Advance() interface. That means
# the rest of this script (terrain, driver, vis, the simulation loop) does not
# care which one you picked - only build_vehicle() knows the differences
# between an HMMWV and a bus.


def build_vehicle(name):
    """Construct and initialize one of a few Chrono::Vehicle models.

    Returns (vehicle_model, chase_distance): vehicle_model is the wrapper
    object (what used to be called `hmmwv`); chase_distance is how far back
    the camera should sit for a vehicle of that size.
    """
    if name == "hmmwv":
        v = veh.HMMWV_Full()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisCollisionType(veh.CollisionType_NONE)
        v.SetChassisFixed(False)
        v.SetInitPosition(chrono.ChCoordsysd(chrono.ChVector3d(0, 0, 1.6), chrono.QUNIT))
        v.SetEngineType(veh.EngineModelType_SHAFTS)
        v.SetTransmissionType(veh.TransmissionModelType_AUTOMATIC_SHAFTS)
        v.SetDriveType(veh.DrivelineTypeWV_AWD)
        v.SetSteeringType(veh.SteeringTypeWV_PITMAN_ARM)
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 6.0

    elif name == "sedan":
        v = veh.Sedan()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisFixed(False)
        v.SetInitPosition(chrono.ChCoordsysd(chrono.ChVector3d(0, 0, 0.5), chrono.QUNIT))
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 6.0

    elif name == "citybus":
        v = veh.CityBus()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisFixed(False)
        v.SetInitPosition(chrono.ChCoordsysd(chrono.ChVector3d(0, 0, 0.5), chrono.QUNIT))
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 15.0

    elif name == "gator":
        v = veh.Gator()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisFixed(False)
        v.SetInitPosition(chrono.ChCoordsysd(chrono.ChVector3d(0, 0, 0.4), chrono.QUNIT))
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 6.0

    else:
        raise ValueError(f"unknown VEHICLE {name!r}")

    v.SetChassisVisualizationType(chrono.VisualizationType_MESH)
    v.SetSuspensionVisualizationType(chrono.VisualizationType_PRIMITIVES)
    v.SetSteeringVisualizationType(chrono.VisualizationType_PRIMITIVES)
    v.SetWheelVisualizationType(chrono.VisualizationType_MESH)
    v.SetTireVisualizationType(chrono.VisualizationType_MESH)
    return v, chase_dist


# =============================================================================
# MAIN
# =============================================================================


def main():
    # -----------------------------------------------------------------------
    # Create the vehicle (PART 5) and initialize
    # -----------------------------------------------------------------------
    vehicle_model, chase_dist = build_vehicle(VEHICLE)

    vehicle = vehicle_model.GetVehicle()
    system = vehicle_model.GetSystem()
    system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)

    # -----------------------------------------------------------------------
    # Create the terrain
    # -----------------------------------------------------------------------
    terrain = veh.RigidTerrain(system)
    patch_mat = chrono.ChContactMaterialSMC()
    patch_mat.SetFriction(0.9)
    patch_mat.SetRestitution(0.01)
    patch_mat.SetYoungModulus(2e7)
    patch = terrain.AddPatch(patch_mat, chrono.CSYSNORM, 200.0, 200.0)
    patch.SetTexture(veh.GetVehicleDataFile("terrain/textures/tile4.jpg"), 200, 200)
    patch.SetColor(chrono.ChColor(0.8, 0.8, 0.5))
    terrain.Initialize()

    # -----------------------------------------------------------------------
    # Create the driver system - this is where the human plugs in
    # -----------------------------------------------------------------------
    device = None  # PART 4 input device (UdpInput) - gamepad/wheel needs no device object

    if INPUT_SOURCE == "data":
        ### PART 1: scripted inputs - no human in the loop ###
        # (time, steering, throttle, braking)
        data = veh.vector_Entry([
            veh.DataDriverEntry(0.0, 0.0, 0.0, 0.0),
            veh.DataDriverEntry(0.5, 0.0, 0.8, 0.0),
            veh.DataDriverEntry(4.0, 0.4, 0.8, 0.0),
            veh.DataDriverEntry(8.0, -0.4, 0.8, 0.0),
            veh.DataDriverEntry(12.0, 0.0, 0.0, 0.8),
        ])
        driver = veh.ChDataDriver(vehicle, data)

    elif INPUT_SOURCE == "keyboard":
        ### PART 2: keyboard through the Irrlicht window ###
        # Arrow keys steer/accelerate/brake, 'C' centers steering, 'R' releases
        # the pedals, 'L' locks the current inputs.
        driver = veh.ChInteractiveDriver(vehicle)
        steering_time = 1.0  # time to go from 0 to +1 (or from 0 to -1)
        throttle_time = 1.0  # time to go from 0 to +1
        braking_time = 0.3   # time to go from 0 to +1
        driver.SetSteeringDelta(render_step_size / steering_time)
        driver.SetThrottleDelta(render_step_size / throttle_time)
        driver.SetBrakingDelta(render_step_size / braking_time)
        driver.SetGains(4.0, 4.0, 4.0)  # first-order lag from key target to applied input

    elif INPUT_SOURCE == "gamepad":
        ### PART 3: a gamepad or wheel - same driver class as keyboard ###
        # SetInputMode(JOYSTICK) switches ChInteractiveDriver from reading the
        # Irrlicht window's keyboard to reading the joystick vis configures
        # below.  Smoothing (SetGains) applies the same way either mode.
        driver = veh.ChInteractiveDriver(vehicle)
        driver.SetGains(4.0, 4.0, 4.0)
        driver.SetInputMode(driver.InputMode_JOYSTICK)

    else:
        ### PART 4: a device Chrono doesn't know about writes into a plain ChDriver ###
        driver = veh.ChDriver(vehicle)
        if INPUT_SOURCE == "udp":
            device = UdpInput(port=UDP_PORT)
        else:
            raise ValueError(f"unknown INPUT_SOURCE {INPUT_SOURCE!r}")
        smoother = SmoothedInputs(gain=4.0)

    driver.Initialize()

    # -----------------------------------------------------------------------
    # Create the vehicle Irrlicht interface
    # -----------------------------------------------------------------------
    vis = veh.ChWheeledVehicleVisualSystemIrrlicht()
    vis.SetWindowTitle(f"{VEHICLE} - human in the loop")
    vis.SetWindowSize(1280, 800)
    vis.SetChaseCamera(chrono.ChVector3d(0.0, 0.0, 1.75), chase_dist, 0.5)
    vis.Initialize()
    vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
    vis.AddLightDirectional()
    vis.AddSkyBox()
    vis.AttachVehicle(vehicle)
    if INPUT_SOURCE in ("keyboard", "gamepad"):
        vis.AttachDriver(driver)  # route Irrlicht key/joystick events to the driver
    if INPUT_SOURCE == "gamepad":
        vis.SetJoystickConfigFile(JOYSTICK_CONFIG)
        vis.SetJoystickDebug(JOYSTICK_DEBUG)  # prints live axis/button numbers

    # PART 5: the built-in overlay - nothing here is hand-drawn, every piece
    # is a flag or a method on `vis` itself
    vis.EnableStats(SHOW_VEHICLE_HUD)        # speed/steering/throttle/brake panel
    vis.SetHUDLocation(*HUD_CORNER)          # where that panel sits
    vis.ShowInfoPanel(SHOW_SIM_INFO_PANEL)   # Chrono's own tabbed info panel
                                              # (bodies, contacts, timers); also
                                              # toggles live with the 'i' key
    vis.ShowProfiler(SHOW_PROFILER)          # per-module timing bars

    # -----------------------------------------------------------------------
    # Real-time setup (PART 1)
    # -----------------------------------------------------------------------
    if REALTIME == "vehicle":
        vehicle.EnableRealtime(True)
    rt_timer = chrono.ChRealtimeStepTimer()  # used when REALTIME == "per_step"
    cum_timer = CumulativeRealtimeTimer()    # used when REALTIME == "cumulative"

    # -----------------------------------------------------------------------
    # Simulation loop
    # -----------------------------------------------------------------------
    render_steps = math.ceil(render_step_size / step_size)
    report_steps = math.ceil(1.0 / step_size)  # console report once per sim second

    print(f"\nINPUT_SOURCE={INPUT_SOURCE}  REALTIME={REALTIME}  step_size={step_size}\n")
    print(f"{'sim t':>7} {'wall t':>7} {'drift':>7} {'RTF':>6} {'speed':>7}  {'steer':>6} {'thr':>5} {'brk':>5}")

    step_number = 0
    wall_start = time.perf_counter()

    while vis.Run():
        sim_time = system.GetChTime()

        # Render scene
        if step_number % render_steps == 0:
            vis.BeginScene()
            vis.Render()
            vis.EndScene()

        # PART 4: sample the device ONCE per step and hold it for the step
        if device is not None:
            smoother.set_target(*device.poll())
            smoother.advance(step_size)
            smoother.apply_to(driver)

        # Get driver inputs (three floats) - this is the whole human-in-the-loop contract
        driver_inputs = driver.GetInputs()

        # Update modules (process inputs from other modules)
        driver.Synchronize(sim_time)
        terrain.Synchronize(sim_time)
        vehicle_model.Synchronize(sim_time, driver_inputs, terrain)
        vis.Synchronize(sim_time, driver_inputs)

        # Advance simulation for one timestep for all modules
        driver.Advance(step_size)
        terrain.Advance(step_size)
        vehicle_model.Advance(step_size)  # spins here if REALTIME == "vehicle"
        vis.Advance(step_size)

        # Console report: how far is the sim from wall time?
        if step_number % report_steps == 0:
            wall = time.perf_counter() - wall_start
            print(f"{sim_time:7.2f} {wall:7.2f} {wall - sim_time:+7.3f} {vehicle.GetRTF():6.2f}"
                  f" {vehicle.GetSpeed():7.2f}  {driver_inputs.m_steering:6.2f}"
                  f" {driver_inputs.m_throttle:5.2f} {driver_inputs.m_braking:5.2f}")

        # PART 4: feedback to the operator (speed, RTF, lateral acceleration, applied inputs)
        if SEND_FEEDBACK and device is not None and step_number % render_steps == 0:
            acc = vehicle.GetPointAcceleration(chrono.ChVector3d(0, 0, 0))
            device.send_feedback(f"{sim_time:.3f},{vehicle.GetSpeed():.3f},{vehicle.GetRTF():.3f},{acc.y:.3f},"
                                 f"{driver_inputs.m_steering:.3f},{driver_inputs.m_throttle:.3f},{driver_inputs.m_braking:.3f}")

        step_number += 1

        # PART 1: spin in place for real time to catch up
        if REALTIME == "per_step":
            rt_timer.Spin(step_size)
        elif REALTIME == "cumulative":
            cum_timer.spin(system.GetChTime())


# =============================================================================
# CONFIGURATION
# =============================================================================

# PART 5: choose your car - "hmmwv" | "sedan" | "citybus" | "gator"
VEHICLE = "hmmwv"

# Where do the driver inputs come from?
#   "data"      PART 1 - scripted ChDataDriver, no human
#   "keyboard"  PART 2 - ChInteractiveDriver, arrow keys in the Irrlicht window
#   "gamepad"   PART 3 - a joystick/wheel, read natively (JOYSTICK_CONFIG below)
#   "udp"       PART 4 - operator_console.py sends packets over the network
INPUT_SOURCE = "data"

# How is real time enforced?  "none" | "per_step" | "vehicle" | "cumulative"
REALTIME = "none"

# PART 4: send telemetry back to the operator (udp source only)
SEND_FEEDBACK = False

# Simulation step sizes.  Make step_size smaller (e.g. 5e-4) to see RTF > 1.
step_size = 3e-3
tire_step_size = 1e-3

# Tire model (RIGID, FIALA, TMEASY, PAC89, PAC02)
tire_model = veh.TireModelType_TMEASY

# Time interval between two render frames
render_step_size = 1.0 / 50  # FPS = 50

# PART 3: joystick/wheel config - four presets ship with Chrono, or write your own
#   controller_XboxOneForWindows.json, controller_LogitechRumblePad2.json,
#   controller_WheelPedalsAndShifters.json, controller_Default.json
JOYSTICK_CONFIG = veh.GetVehicleDataFile("joystick/controller_XboxOneForWindows.json")
JOYSTICK_DEBUG = False  # True: print live axis/button numbers to find your device's mapping

# PART 4 device settings
UDP_PORT = 9870

# PART 5: the built-in Irrlicht overlay - add or remove pieces of it here
# instead of writing your own on top of the 3D view
SHOW_VEHICLE_HUD = True         # speed/steering/throttle/brake panel
HUD_CORNER = (10, 10)           # (x, y) pixels from the top-left corner
SHOW_SIM_INFO_PANEL = False     # Chrono's tabbed info panel (bodies/contacts/timers)
SHOW_PROFILER = False           # per-module timing bars

main()
