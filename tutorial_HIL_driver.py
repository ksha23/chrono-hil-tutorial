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
#   PART 6: Change gear                               (TRANSMISSION, and the
#                                                      keys listed at startup)
#   PART 7: Drive somewhere real                      (SCENE = "mcity")
#   PART 8: Control something that isn't a car        (PLANT = "rover"/"crane")
#
# The vehicle defaults to an HMMWV on flat rigid terrain (same model as
# demo_VEH_HMMWV) but VEHICLE can pick any of a few other Chrono::Vehicle
# models - see build_vehicle() and PART 5 below. The vehicle reference frame
# has Z up, X towards the front of the vehicle, and Y pointing to the left.
#
# Parts 6-8 live in three modules next to this one, so that this file stays a
# readable simulation loop rather than a pile of special cases:
#
#   hil_gearbox.py   PART 6, the transmission
#   hil_scene.py     PART 7, flat terrain or the Mcity digital twin
#   hil_plants.py    PART 8, a vehicle, a rover, or a gantry crane
# =============================================================================

import math
import socket
import time

import pychrono as chrono
import pychrono.vehicle as veh
import pychrono.irrlicht as irr

import hil_gearbox
import hil_plants
import hil_scene


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
# second - no separate probe script needed.
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


class DriverInputs:
    """The whole ChDriver contract, in Python.

    ChDriver is a container for three numbers and the accessors that read them
    back; nothing about it is vehicle-specific except that its constructor asks
    for a ChVehicle.  The rover and the crane (PART 8) have no ChVehicle, so
    they use this instead, and every line of the simulation loop stays the same.

    Worth reading as the answer to "what does Chrono actually require of a
    human interface": this class, and nothing else.
    """

    def __init__(self):
        self.m_steering = 0.0
        self.m_throttle = 0.0
        self.m_braking = 0.0

    def SetSteering(self, v):
        self.m_steering = v

    def SetThrottle(self, v):
        self.m_throttle = v

    def SetBraking(self, v):
        self.m_braking = v

    def GetInputs(self):
        return self

    def Initialize(self):
        pass

    def Synchronize(self, t):
        pass

    def Advance(self, step):
        pass


class ScriptedInputs(DriverInputs):
    """ChDataDriver for a plant that has no ChVehicle: interpolate a table by time.

    Same table, same linear interpolation between entries, same hold before the
    first and after the last.  Here so that PART 1 (which is about real time,
    not about vehicles) works on all three plants.
    """

    def __init__(self, entries):
        super().__init__()
        self.entries = sorted(entries)

    def Synchronize(self, t):
        rows = self.entries
        if t <= rows[0][0]:
            _, self.m_steering, self.m_throttle, self.m_braking = rows[0]
            return
        if t >= rows[-1][0]:
            _, self.m_steering, self.m_throttle, self.m_braking = rows[-1]
            return
        for (t0, s0, h0, b0), (t1, s1, h1, b1) in zip(rows, rows[1:]):
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                self.m_steering = s0 + f * (s1 - s0)
                self.m_throttle = h0 + f * (h1 - h0)
                self.m_braking = b0 + f * (b1 - b0)
                return


class UdpInput:
    """Receive 'steering,throttle,braking[,gear]' text datagrams from an operator.

    Run operator_console.py in another terminal (or on another machine) and
    drive with the arrow keys there.  The socket is non-blocking: the physics
    loop never waits for the operator.  If no packet arrived since the last
    step, the previous target is held (zero-order hold).

    PART 6 added the optional fourth field.  It is a single character naming a
    gear command (see hil_gearbox.Gearbox.COMMANDS) or '-' for "no command this
    packet", and unlike the three numbers it is an EVENT rather than a level:
    the operator presses ']' once and means one upshift, not "keep upshifting".
    take_gear_commands() below is what enforces that, by handing each command
    out exactly once.

    Keeping the field optional is what stops the change from breaking an older
    console: a three-field packet still parses.
    """

    def __init__(self, port=9870):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.setblocking(False)
        self.operator_addr = None
        self.last = (0.0, 0.0, 0.0)
        self.packets = 0
        self.gear_commands = []
        print(f"[udp] listening on port {port} - start operator_console.py")

    def poll(self):
        # Drain everything that is queued and keep only the newest packet.  The
        # gear commands are the exception: they accumulate, because dropping one
        # loses a shift the operator asked for.
        while True:
            try:
                data, addr = self.sock.recvfrom(256)
            except BlockingIOError:
                break
            fields = data.decode().split(",")
            if len(fields) < 3:
                continue
            try:
                s, t, b = (float(x) for x in fields[:3])
            except ValueError:
                continue
            self.last = (s, t, b)
            self.operator_addr = addr
            self.packets += 1
            if len(fields) > 3 and fields[3] and fields[3] != "-":
                self.gear_commands.append(fields[3][0])
        return self.last

    def take_gear_commands(self):
        """Hand back the gear commands received since the last call, and forget them."""
        commands, self.gear_commands = self.gear_commands, []
        return commands

    # PART 4: telemetry back to whoever is sending us inputs
    def send_feedback(self, text):
        if self.operator_addr is not None:
            self.sock.sendto(text.encode(), self.operator_addr)


# =============================================================================
# PART 5: CHOOSE YOUR CAR
# =============================================================================
#
# Every "full vehicle" model in Chrono::Vehicle (HMMWV_Full, Sedan, UAZBUS,
# Gator, ...) exposes the same handful of setup calls and the same
# GetVehicle() / GetSystem() / Synchronize() / Advance() interface. That means
# the rest of this script (terrain, driver, vis, the simulation loop) does not
# care which one you picked - only build_vehicle() knows the differences
# between an HMMWV and a bus.


class JsonVehicle:
    """Give a JSON-built WheeledVehicle the wrapper interface the loop expects.

    The model classes (HMMWV_Full, Sedan, ...) are wrappers that own a ChVehicle
    and a ChSystem and forward Synchronize/Advance to both. A WheeledVehicle read
    from JSON is the ChVehicle itself, so it has no GetVehicle() and no
    GetSystem(). Six lines here mean build_plant() and the simulation loop do not
    have to know which kind they were handed.
    """

    def __init__(self, vehicle):
        self.vehicle = vehicle

    def GetVehicle(self):
        return self.vehicle

    def GetSystem(self):
        return self.vehicle.GetSystem()

    def Synchronize(self, t, inputs, terrain):
        self.vehicle.Synchronize(t, inputs, terrain)

    def Advance(self, step):
        self.vehicle.Advance(step)


# Ride height at spawn, per model: how far above the ground the vehicle's
# reference frame has to start so that it settles onto its tires rather than
# through them.  PART 7 needs these separately from the pose, because on Mcity
# the ground is not at z = 0.
SPAWN_HEIGHT = {"hmmwv": 1.6, "sedan": 0.5, "uazbus": 0.4, "gator": 0.4, "audi": 0.5}


def build_vehicle(name, start, transmission="automatic"):
    """Construct and initialize one of a few Chrono::Vehicle models.

    start         where to put it (PART 7: flat terrain and Mcity differ)
    transmission  "automatic" or "manual" (PART 6)

    Returns (vehicle_model, chase_distance): vehicle_model is the wrapper
    object (what used to be called `hmmwv`); chase_distance is how far back
    the camera should sit for a vehicle of that size.
    """
    if name == "hmmwv":
        v = veh.HMMWV_Full()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisCollisionType(veh.CollisionType_NONE)
        v.SetChassisFixed(False)
        v.SetInitPosition(start)
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
        v.SetInitPosition(start)
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 6.0

    elif name == "uazbus":
        v = veh.UAZBUS()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisFixed(False)
        v.SetInitPosition(start)
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 6.0

    elif name == "gator":
        v = veh.Gator()
        v.SetContactMethod(chrono.ChContactMethod_SMC)
        v.SetChassisFixed(False)
        v.SetInitPosition(start)
        v.SetTireType(tire_model)
        v.SetTireStepSize(tire_step_size)
        v.Initialize()
        chase_dist = 6.0

    elif name == "audi":
        ### PART 6: the one model here with a manual gearbox to row through ###
        #
        # Built from JSON rather than from a model wrapper class, which is how
        # most real Chrono::Vehicle work is done: the wrappers above hard-code
        # one powertrain each, and none of them ships a manual transmission.
        # WheeledVehicle reads the vehicle from JSON and takes the engine and
        # transmission separately, so "which gearbox" becomes a choice of file.
        v = veh.WheeledVehicle(veh.GetVehicleDataFile("audi/json/audi_Vehicle.json"))
        v.Initialize(start)
        v.SetChassisVisualizationType(chrono.VisualizationType_MESH)
        v.SetSuspensionVisualizationType(chrono.VisualizationType_MESH)
        v.SetSteeringVisualizationType(chrono.VisualizationType_MESH)
        v.SetWheelVisualizationType(chrono.VisualizationType_MESH)

        engine = veh.ReadEngineJSON(veh.GetVehicleDataFile("audi/json/audi_EngineSimpleMap.json"))
        gearbox_json = ("audi/json/audi_ManualTransmissionShafts.json" if transmission == "manual"
                        else "audi/json/audi_AutomaticTransmissionSimpleMap.json")
        gearbox = veh.ReadTransmissionJSON(veh.GetVehicleDataFile(gearbox_json))
        v.InitializePowertrain(veh.ChPowertrainAssembly(engine, gearbox))

        for axle in v.GetAxles():
            for wheel in axle.GetWheels():
                tire = veh.ReadTireJSON(veh.GetVehicleDataFile("audi/json/audi_TMeasyTire.json"))
                tire.SetStepsize(tire_step_size)
                v.InitializeTire(tire, wheel, chrono.VisualizationType_MESH)

        # WheeledVehicle IS the vehicle, not a wrapper around one, so it has no
        # GetVehicle()/GetSystem(). JsonVehicle below gives it the two accessors
        # the rest of this file uses, and nothing else has to know the difference.
        return JsonVehicle(v), 6.0

    else:
        raise ValueError(f"unknown VEHICLE {name!r}")

    if transmission == "manual":
        # Say so rather than leaving the gear readout at "--" with no explanation.
        # The model wrapper classes each hard-code one powertrain, and asking one
        # for a transmission it does not ship leaves it with NO transmission at
        # all -- silently, and the vehicle then will not drive. So this warns and
        # keeps the automatic rather than honouring the request.
        print(f"[gearbox] TRANSMISSION = 'manual', but the {name} model ships only an "
              f"automatic and keeps it.\n"
              f"[gearbox] Use VEHICLE = 'audi' for a manual gearbox.")

    v.SetChassisVisualizationType(chrono.VisualizationType_MESH)
    v.SetSuspensionVisualizationType(chrono.VisualizationType_PRIMITIVES)
    v.SetSteeringVisualizationType(chrono.VisualizationType_PRIMITIVES)
    v.SetWheelVisualizationType(chrono.VisualizationType_MESH)
    v.SetTireVisualizationType(chrono.VisualizationType_MESH)
    return v, chase_dist


# =============================================================================
# MAIN
# =============================================================================


def build_plant(plan):
    """Create the thing being controlled, and the terrain under it (PARTS 7, 8).

    Returns (plant, chase_distance).  The plant wraps whatever was built behind
    the small interface described at the top of hil_plants.py, which is what
    lets the loop below be one loop no matter what is being driven.

    Note the ordering, which is not free to change: the vehicle owns the
    ChSystem, the scene has to be added to that system, and the vehicle has to
    be told where to spawn before it is initialized.  Hence plan_scene() up
    front (files only) and plan.build() afterwards.
    """
    if PLANT == "vehicle":
        vehicle_model, chase_dist = build_vehicle(VEHICLE, plan.start, TRANSMISSION)
        system = vehicle_model.GetSystem()
        system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
        # A road-driving vehicle under-solves with the default solver, which
        # shows up as the suspension juddering for no visible reason. These are
        # the settings Chrono's own road demos use.
        system.SetSolverType(chrono.ChSolver.Type_BARZILAIBORWEIN)
        system.GetSolver().AsIterative().SetMaxIterations(150)
        terrain = plan.build(system)

        gearbox = hil_gearbox.Gearbox(vehicle_model.GetVehicle())
        gearbox.set_manual_shifting(START_IN_MANUAL_SHIFT)
        return hil_plants.VehiclePlant(vehicle_model, terrain, gearbox), chase_dist

    if PLANT == "rover":
        ### PART 8: a Viper rover - same three numbers, a completely different machine ###
        system = chrono.ChSystemNSC()
        system.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
        system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
        plan.build(system)
        wheel_mat = chrono.ChContactMaterialData()
        wheel_mat.mu = 0.4
        return hil_plants.RoverPlant(system, plan.start,
                                     wheel_mat.CreateMaterial(system.GetContactMethod())), 4.0

    if PLANT == "crane":
        ### PART 8: a gantry crane - no Chrono::Vehicle involved at all ###
        # NSC rather than SMC: this model is constraints and motors with no
        # contact anywhere, so there is nothing for a penalty formulation to do.
        system = chrono.ChSystemNSC()
        system.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
        system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
        plan.build(system)
        return hil_plants.CranePlant(system, plan.start), 25.0

    raise ValueError(f"unknown PLANT {PLANT!r}")


def main():
    # -----------------------------------------------------------------------
    # Where are we driving (PART 7), and what are we driving (PARTS 5, 8)?
    # -----------------------------------------------------------------------
    spawn_height = SPAWN_HEIGHT.get(VEHICLE, 0.5) if PLANT == "vehicle" else 0.5
    plan = hil_scene.plan_scene(SCENE, spawn_height,
                                mcity_dir=MCITY_DIR, mcity_detail=MCITY_DETAIL)

    plant, chase_dist = build_plant(plan)
    system = plant.system
    terrain = getattr(plant, "terrain", None)
    gearbox = getattr(plant, "gearbox", None)

    # The driver classes below need a ChVehicle. The rover and the crane do not
    # have one, so they take their input over the network (PART 4) or from the
    # scripted table (PART 1) - which is the lesson, not a limitation: the
    # operator console did not have to change to drive a crane.
    vehicle = plant.vehicle if PLANT == "vehicle" else None
    if PLANT != "vehicle" and INPUT_SOURCE in ("keyboard", "gamepad"):
        raise SystemExit(
            f"\nINPUT_SOURCE = {INPUT_SOURCE!r} needs a ChInteractiveDriver, which needs a\n"
            f"Chrono::Vehicle, and PLANT = {PLANT!r} does not have one.\n"
            f"Use INPUT_SOURCE = 'udp' (operator_console.py drives it just as well) or 'data'.\n")

    # -----------------------------------------------------------------------
    # Create the driver system - this is where the human plugs in
    # -----------------------------------------------------------------------
    device = None  # PART 4 input device (UdpInput) - gamepad/wheel needs no device object

    if INPUT_SOURCE == "data":
        ### PART 1: scripted inputs - no human in the loop ###
        # (time, steering, throttle, braking)
        data_entries = [
            (0.0, 0.0, 0.0, 0.0),
            (0.5, 0.0, 0.8, 0.0),
            (4.0, 0.4, 0.8, 0.0),
            (8.0, -0.4, 0.8, 0.0),
            (12.0, 0.0, 0.0, 0.8),
        ]
        data = veh.vector_Entry([veh.DataDriverEntry(*e) for e in data_entries])
        # ChDataDriver interpolates the table above; for a plant with no
        # ChVehicle we hold the same table ourselves (ScriptedInputs below).
        driver = veh.ChDataDriver(vehicle, data) if vehicle else ScriptedInputs(data_entries)

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
        # A plain ChDriver is a container for three floats. For a plant with no
        # ChVehicle to hand it, DriverInputs below is that same container in
        # twelve lines of Python - which is the clearest statement of how little
        # the "driver" side of this interface actually is.
        driver = veh.ChDriver(vehicle) if vehicle else DriverInputs()
        if INPUT_SOURCE == "udp":
            device = UdpInput(port=UDP_PORT)
        else:
            raise ValueError(f"unknown INPUT_SOURCE {INPUT_SOURCE!r}")
        smoother = SmoothedInputs(gain=4.0)

    driver.Initialize()

    # -----------------------------------------------------------------------
    # Create the Irrlicht interface
    #
    # Two flavours: the vehicle one, which adds a chase camera and the driver
    # HUD, and the plain one for the rover and the crane. Everything after this
    # point treats them the same, because the pieces the loop uses (Run,
    # BeginScene, Render, EndScene, Synchronize, Advance) are on the base class.
    # -----------------------------------------------------------------------
    title = f"{VEHICLE if PLANT == 'vehicle' else PLANT} on {plan.name} - human in the loop"
    if plant.needs_vehicle_vis:
        vis = veh.ChWheeledVehicleVisualSystemIrrlicht()
        vis.SetWindowTitle(title)
        vis.SetWindowSize(1280, 800)
        vis.SetChaseCamera(chrono.ChVector3d(0.0, 0.0, 1.75), chase_dist, 0.5)
        vis.Initialize()
        vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
        vis.AddLightDirectional()
        vis.AddSkyBox()
        plant.attach(vis)
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
    else:
        ### PART 8: a plain visual system, because there is no vehicle to attach ###
        vis = irr.ChVisualSystemIrrlicht()
        vis.AttachSystem(system)
        vis.SetWindowTitle(title)
        vis.SetWindowSize(1280, 800)
        vis.Initialize()
        vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
        vis.AddTypicalLights()
        vis.AddSkyBox()
        # No chase camera on the base class, so the camera is moved by hand once
        # per render frame in the loop below (see follow_camera).
        vis.AddCamera(chrono.ChVector3d(chase_dist, -chase_dist, chase_dist * 0.6),
                      plant.chase_target().GetPos())

    def follow_camera():
        """Keep the plain visual system's camera pointed at a moving plant."""
        if plant.needs_vehicle_vis:
            return  # the vehicle chase camera does this itself
        target = plant.chase_target().GetPos()
        vis.UpdateCamera(chrono.ChVector3d(target.x - chase_dist * 0.8,
                                           target.y - chase_dist,
                                           target.z + chase_dist * 0.6),
                         target)

    # -----------------------------------------------------------------------
    # Real-time setup (PART 1)
    # -----------------------------------------------------------------------
    realtime_mode = REALTIME
    if REALTIME == "vehicle":
        if vehicle:
            vehicle.EnableRealtime(True)
        else:
            # There is no vehicle to do the spinning, so fall back to the timer
            # that does the same thing from outside. Same soft real time, same
            # per-step measurement, no drift recovery either way.
            print('[realtime] REALTIME = "vehicle" needs a Chrono::Vehicle; '
                  'using "per_step", which is the same policy.')
            realtime_mode = "per_step"
    rt_timer = chrono.ChRealtimeStepTimer()  # used when REALTIME == "per_step"
    cum_timer = CumulativeRealtimeTimer()    # used when REALTIME == "cumulative"

    # -----------------------------------------------------------------------
    # Simulation loop
    #
    # One loop for all three plants and all four input sources. Everything that
    # differs between them was decided above and is behind `plant`, `driver` and
    # `vis`; nothing below branches on which part of the tutorial you are on.
    # -----------------------------------------------------------------------
    render_steps = math.ceil(render_step_size / step_size)
    report_steps = math.ceil(1.0 / step_size)  # console report once per sim second

    print(f"\nPLANT={PLANT}  SCENE={plan.name}  INPUT_SOURCE={INPUT_SOURCE}"
          f"  REALTIME={realtime_mode}  step_size={step_size}")
    if plan.note:
        print(f"scenery: {plan.note}")
    if INPUT_SOURCE in ("keyboard", "gamepad") and gearbox and gearbox.present:
        ### PART 6: Chrono already binds these; nothing in this file has to ###
        print("\nkeys handled by Chrono's Irrlicht event receiver:")
        print(hil_gearbox.KEYBOARD_HELP)
    print()
    header = (f"{'sim t':>7} {'wall t':>7} {'drift':>7} {'RTF':>6} {'speed':>7} "
              f" {'steer':>6} {'thr':>5} {'brk':>5}")
    print(header + ("  status" if plant.status() else ""))

    step_number = 0
    wall_start = time.perf_counter()
    last_wall, last_sim = 0.0, 0.0  # previous report, for the measured RTF below

    while vis.Run():
        sim_time = system.GetChTime()

        # Render scene
        if step_number % render_steps == 0:
            follow_camera()
            vis.BeginScene()
            vis.Render()
            vis.EndScene()

        # PART 4: sample the device ONCE per step and hold it for the step
        if device is not None:
            smoother.set_target(*device.poll())
            smoother.advance(step_size)
            smoother.apply_to(driver)
            # PART 6: gear commands are events, not levels, so they are applied
            # once each rather than held like the three numbers above.
            if gearbox is not None:
                for command in device.take_gear_commands():
                    gearbox.command_char(command)

        # Get driver inputs (three floats) - this is the whole human-in-the-loop contract
        driver_inputs = driver.GetInputs()

        # PART 8: hand the three numbers to whatever is being controlled. For a
        # Chrono::Vehicle this does nothing (the vehicle reads them in
        # Synchronize); for the rover and the crane it is where they land.
        plant.apply(driver_inputs)

        # Update modules (process inputs from other modules)
        driver.Synchronize(sim_time)
        if terrain is not None:
            terrain.Synchronize(sim_time)
        plant.synchronize(sim_time, driver_inputs)
        # Synchronize and Advance are on the VEHICLE visual system, not on the
        # base one: they drive the chase camera and the driver HUD, and a plain
        # ChVisualSystemIrrlicht has neither.
        if plant.needs_vehicle_vis:
            vis.Synchronize(sim_time, driver_inputs)

        # Advance simulation for one timestep for all modules
        driver.Advance(step_size)
        if terrain is not None:
            terrain.Advance(step_size)
        plant.advance(step_size)  # spins here if REALTIME == "vehicle"
        # A Chrono::Vehicle steps its own ChSystem inside Advance; the rover and
        # the crane do not, so the system is stepped here instead. Stepping twice
        # would run the clock at double speed, which is why this is a branch.
        if not plant.steps_own_system:
            system.DoStepDynamics(step_size)
        if plant.needs_vehicle_vis:
            vis.Advance(step_size)

        # Console report: how far is the sim from wall time?
        if step_number % report_steps == 0:
            wall = time.perf_counter() - wall_start
            # A ChVehicle measures its own real-time factor per step. The rover
            # and the crane do not, so it is measured here over the reporting
            # interval instead: same quantity, coarser sampling.
            if vehicle:
                rtf = vehicle.GetRTF()
            else:
                d_wall = wall - last_wall
                d_sim = sim_time - last_sim
                rtf = (d_wall / d_sim) if d_sim > 0 else 0.0
                last_wall, last_sim = wall, sim_time
            print(f"{sim_time:7.2f} {wall:7.2f} {wall - sim_time:+7.3f} {rtf:6.2f}"
                  f" {plant.speed():7.2f}  {driver_inputs.m_steering:6.2f}"
                  f" {driver_inputs.m_throttle:5.2f} {driver_inputs.m_braking:5.2f}"
                  f"  {plant.status()}")

        # PART 4: feedback to the operator (speed, RTF, lateral acceleration, applied
        # inputs, and since PART 6 the gear)
        if SEND_FEEDBACK and device is not None and step_number % render_steps == 0:
            acc = (vehicle.GetPointAcceleration(chrono.ChVector3d(0, 0, 0)).y
                   if vehicle else 0.0)
            rtf = vehicle.GetRTF() if vehicle else 0.0
            gear = gearbox.describe() if gearbox else plant.status() or "--"
            device.send_feedback(
                f"{sim_time:.3f},{plant.speed():.3f},{rtf:.3f},{acc:.3f},"
                f"{driver_inputs.m_steering:.3f},{driver_inputs.m_throttle:.3f},"
                f"{driver_inputs.m_braking:.3f},{gear}")

        step_number += 1

        # PART 1: spin in place for real time to catch up
        if realtime_mode == "per_step":
            rt_timer.Spin(step_size)
        elif realtime_mode == "cumulative":
            cum_timer.spin(system.GetChTime())


# =============================================================================
# CONFIGURATION
# =============================================================================

# PART 8: what are we controlling?
#   "vehicle"  a Chrono::Vehicle (PARTS 1-7)
#   "rover"    a Viper rover: same three numbers, six wheels, no gearbox
#   "crane"    a gantry crane with a swinging payload, and no Chrono::Vehicle
#              anywhere in it. Try to put the load on the green pad without
#              letting it swing; the console prints the swing angle.
# The rover and the crane have no ChVehicle, so they take INPUT_SOURCE "udp"
# (operator_console.py drives them unchanged) or "data".
PLANT = "vehicle"

# PART 5: choose your car - "hmmwv" | "sedan" | "uazbus" | "gator" | "audi"
# "audi" is built from JSON rather than from a model wrapper class, which is
# what makes TRANSMISSION = "manual" (PART 6) possible: the wrappers each ship
# one powertrain and none of them ships a manual gearbox.
VEHICLE = "hmmwv"

# PART 6: which gearbox. "automatic" | "manual".
# Only VEHICLE = "audi" has both; the other models ship an automatic each and
# say so rather than silently ignoring this.
TRANSMISSION = "automatic"

# PART 6: start an automatic in MANUAL shift mode, so '[' and ']' do something
# immediately. Left in AUTOMATIC, the gearbox overrides your gear on the next
# step, which looks exactly like the shift keys being broken.
START_IN_MANUAL_SHIFT = False

# PART 7: where to drive. "flat" | "mcity"
#   "flat"   200 x 200 m patch, no download, runs on anything
#   "mcity"  the Mcity digital twin, generated by the converter in the Chrono
#            tree (see hil_scene.py). Falls back to "flat" if it is not built.
SCENE = "flat"

# PART 7: how much of Mcity to draw. "ground" | "light" | "full"
#   "ground"  the road surface only. The one to use on a laptop: full elevation
#             and full geometry to drive on, nothing else drawn.
#   "light"   plus poles, signal heads and street lights
#   "full"    everything in the manifest
MCITY_DETAIL = "light"

# PART 7: where the converted Mcity scene lives. None = <chrono data>/mcity
MCITY_DIR = None

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
