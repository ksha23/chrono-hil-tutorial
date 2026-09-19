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
# DEMOS 1 AND 2 LIVE HERE.
#
#     python demos/driver/tutorial_HIL_driver.py          run it
#     python demos/driver/tutorial_HIL_driver.py --help   the switches, listed
#
# Nothing is passed on the command line. Every switch is a constant in the
# CONFIGURATION block at the bottom of this file, and the two demos are two
# settings of it:
#
#   Demo 1  Does the clock matter     INPUT_SOURCE = "data"
#                                     REALTIME = "none", then "vehicle"
#   Demo 2  A person driving          INPUT_SOURCE = "keyboard"
#                                     KEYBOARD_MODE = "held"
#
# Three more switches are here too. They are not demos and they have no
# numbers; each is named after the constant that turns it on, and the code
# below is marked with the same name so it can be found by searching for it:
#
#   VEHICLE, SHOW_*            which car, and the built-in Irrlicht overlay
#   TRANSMISSION               changing gear, which is not part of ChDriver
#   PLANT                      a gantry crane instead of a car
#
# The vehicle defaults to an HMMWV on flat rigid terrain (same model as
# demo_VEH_HMMWV) but VEHICLE can pick any of a few other Chrono::Vehicle
# models - see build_vehicle(). The vehicle reference frame has Z up, X
# towards the front of the vehicle, and Y pointing to the left.
#
# Three modules next to this one keep this file a readable simulation loop
# rather than a pile of special cases:
#
#   hil_gearbox.py   TRANSMISSION, and the shift keys
#   hil_scene.py     the flat terrain everything drives on
#   hil_plants.py    PLANT, a vehicle or a gantry crane
# =============================================================================

import math
import os
import sys
import time

# --help before anything heavy: this script has no __main__ guard, it runs on
# import, so a check placed further down never gets reached.
if "-h" in sys.argv or "--help" in sys.argv:
    print("usage: python demos/driver/tutorial_HIL_driver.py\n"
          "\n"
          "Configured by editing, not by flags: every switch is in the\n"
          "CONFIGURATION block at the bottom of this file.\n"
          "\n"
          "  Demo 1, does the clock matter\n"
          "      INPUT_SOURCE = \"data\",  REALTIME = \"none\"  then \"vehicle\"\n"
          "      Watch the drift column in the console run away, then not.\n"
          "\n"
          "  Demo 2, a person driving\n"
          "      INPUT_SOURCE = \"keyboard\",  KEYBOARD_MODE = \"held\"\n"
          "      A vehicle: W/A/S/D drive, in the 3D window. The arrow keys\n"
          "      there are the chase camera, not driving controls.\n"
          "      PLANT = \"crane\": no ChVehicle, so a small input window of\n"
          "      our own opens. Keep THAT one focused; arrow keys drive.\n"
          "\n"
          "  Not numbered, and in the same block: VEHICLE, TRANSMISSION,\n"
          "  PLANT (\"crane\") and the SHOW_* overlay switches.")
    raise SystemExit(0)

# The loader-path trap, and its message, live in one place for every demo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
from chronohil.chrono_env import chrono, require_window

import pychrono.irrlicht as irr
# Not optional and not a convenience alias: `veh` is used at module level in the
# CONFIGURATION block at the bottom, so losing this line does not fail at the
# first vehicle call, it fails while the file is still being read.
import pychrono.vehicle as veh

import hil_gearbox
import hil_plants
import hil_scene


# =============================================================================
# Demo 1: REAL-TIME ENFORCEMENT (REALTIME)
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
# THE HUMAN INTERFACE, IN FULL
# =============================================================================
#
# The whole "human interface" to a Chrono vehicle is three numbers per step:
#     steering in [-1, 1], throttle in [0, 1], braking in [0, 1]
# ChDriver is a plain container for those numbers with SetSteering(),
# SetThrottle(), SetBraking().  Anything that can produce three floats can
# drive the vehicle, and the two classes below are what a plant with no
# ChVehicle uses in its place.


class DriverInputs:
    """The whole ChDriver contract, in Python.

    ChDriver is a container for three numbers and the accessors that read them
    back.  The crane (PLANT) has no ChVehicle to hand it, so it uses this
    stand-in instead, and every line of the simulation loop stays the same.

    Worth being precise about what this is and is not.  It is the ChDriver
    contract, which is a Chrono::VEHICLE contract -- steering, throttle and
    braking are vehicle channels, and ChDriver's own constructor demands a
    ChVehicle&.  Chrono itself requires nothing of a human interface: the
    crane's entire input surface is two SetSetpoint() calls on a
    ChFunctionSetpoint, and it would be happy with one signed axis per motor.

    The three numbers are a convention this tutorial adopts so that one loop
    can drive a car and a crane without changing.  plant.apply() is where they
    are given their meaning, and the crane shows what the convention costs: it
    has to compute throttle - braking to recover the signed axis it wanted in
    the first place.
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


class WindowInputs(DriverInputs):
    """A person driving a plant that has no ChVehicle, from our own window.

    ChInteractiveDriver needs a ChVehicle, so a crane cannot use it, and there
    is nothing else in Chrono to fall back on: no other module has a driver
    abstraction at all. Something has to read the keys, so this is it -- and
    the size of it is the point, because a crane being hand-drivable is the one
    thing the crane is here to show.

    LocalInput is the portable pygame window the manipulation demo already uses.
    It needs no second terminal and no socket, and it hands back exactly the
    three floats the plant protocol wants. Keep ITS window focused, not the 3D
    view: the arrow keys drive, because this is our window, not Chrono's.
    """

    # Seconds of simulated time between repaints of the input window.  Reading
    # the keys is cheap and is done every step, so no input is ever missed;
    # PAINTING is not, and this is the whole reason the two are separated.
    REDRAW_DT = 1.0 / 30.0

    def __init__(self):
        super().__init__()
        from chronohil.input import LocalInput
        self.dev = LocalInput()
        self.next_draw = 0.0

    def Synchronize(self, t):
        steer, thr, brk = self.dev.poll()
        self.dev.take_commands()  # shift keys; a crane has no gearbox to shift
        self.m_steering, self.m_throttle, self.m_braking = steer, thr, brk

        # The window has to be painted or it stays blank, and a blank window is
        # indistinguishable from a hung one.  It doubles as the key legend,
        # which is the part people need in front of them.
        #
        # But paint it ONCE PER STEP and the crane runs at RTF 2.78 -- measured,
        # against 1.00 with this block removed.  A 3 ms step leaves 3 ms for
        # everything, and one pygame.display.flip() costs more than that on its
        # own.  A human interface is a RENDER, at render rates; putting it on
        # the physics clock is the same mistake as rendering every step.
        if t < self.next_draw:
            return
        self.next_draw = t + self.REDRAW_DT
        self.dev.draw([
            "keep THIS window focused",
            "up/down  bridge travel   left/right  trolley",
            "ESC  quit",
            f"t {t:6.2f} s   steer {steer:+.2f}  "
            f"thr {thr:.2f}  brk {brk:.2f}",
        ])


class ScriptedInputs(DriverInputs):
    """ChDataDriver for a plant that has no ChVehicle: interpolate a table by time.

    Same table, same linear interpolation between entries, same hold before the
    first and after the last.  Here so that Demo 1 (which is about real time,
    not about vehicles) works on both plants.
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


# =============================================================================
# VEHICLE: CHOOSE YOUR CAR
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
# through them.
SPAWN_HEIGHT = {"hmmwv": 1.6, "sedan": 0.5, "uazbus": 0.4, "gator": 0.4, "audi": 0.5}


def build_vehicle(name, start, transmission="automatic"):
    """Construct and initialize one of a few Chrono::Vehicle models.

    start         where to put it
    transmission  "automatic" or "manual" (TRANSMISSION)

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
        ### TRANSMISSION: the one model here with a manual gearbox to row through ###
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
    """Create the thing being controlled, and the terrain under it (PLANT).

    Returns (plant, chase_distance).  The plant wraps whatever was built behind
    the small interface described at the top of hil_plants.py, which is what
    lets the loop below be one loop no matter what is being driven.

    Note the ordering, which is not free to change: the vehicle owns the
    ChSystem, the terrain has to be added to that system, and the vehicle has
    to be told where to spawn before it is initialized.  Hence plan_scene() up
    front (no system needed) and plan.build() afterwards.
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

    if PLANT == "crane":
        ### PLANT = "crane": no Chrono::Vehicle involved at all ###
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
    # What are we driving (VEHICLE, PLANT), and on what terrain?
    # -----------------------------------------------------------------------
    spawn_height = SPAWN_HEIGHT.get(VEHICLE, 0.5) if PLANT == "vehicle" else 0.5
    plan = hil_scene.plan_scene(spawn_height)

    plant, chase_dist = build_plant(plan)
    system = plant.system
    terrain = getattr(plant, "terrain", None)
    gearbox = getattr(plant, "gearbox", None)

    # The keyboard driver class below needs a ChVehicle. The crane does not
    # have one, so it takes its input from the scripted table (INPUT_SOURCE =
    # "data") - which is the lesson, not a limitation: the three numbers did
    # not have to change to drive a crane.
    vehicle = plant.vehicle if PLANT == "vehicle" else None

    # -----------------------------------------------------------------------
    # Create the driver system - this is where the human plugs in
    # -----------------------------------------------------------------------
    if INPUT_SOURCE == "data":
        ### Demo 1: scripted inputs - no human in the loop ###
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
        ### Demo 2: keyboard through the Irrlicht window ###
        # W/A/S/D drive, 'C' centers steering, 'R' releases the pedals, 'L' locks
        # the current inputs.  The ARROW keys are not driving controls: they belong
        # to the chase camera (zoom and orbit), which is a separate Irrlicht event
        # receiver.  Easy to get wrong, because every other part of this tutorial
        # drives with the arrow keys - but those are OUR pygame console, not Chrono.
        if not vehicle:
            # No ChVehicle, so no ChInteractiveDriver -- none of the setup below
            # exists for this plant.  Our own window instead, which is how
            # anything that is not a vehicle takes human input.  Drive it with
            # the ARROW keys, in ITS window, not in the 3D view.
            driver = WindowInputs()
        else:
            driver = veh.ChInteractiveDriver(vehicle)
            driver.SetGains(4.0, 4.0, 4.0)  # first-order lag from key to applied input

            # KEYBOARD_MODE picks what a keypress MEANS, which is a real design
            # question and not a detail:
            #
            #   "cumulative"  each keypress nudges a target by a fixed delta, and
            #                 the target stays where you left it.  Historical
            #                 Chrono behaviour, and what the deltas below set.
            #   "held"        the input follows the keys currently held down and
            #                 ramps back when you let go, as in a driving game.
            #                 The input is a LEVEL rather than a nudge, and
            #                 SetGains above is the ramp rate.
            #
            # "held" needs the KeyboardMode API (PyChrono build 1187 / Aug 2026
            # and later).  On an older PyChrono, say so and carry on cumulatively
            # rather than dying with an AttributeError.
            if KEYBOARD_MODE == "held":
                if hasattr(veh.ChInteractiveDriver, "KeyboardMode_HELD"):
                    driver.SetKeyboardMode(veh.ChInteractiveDriver.KeyboardMode_HELD)
                else:
                    print('[keyboard] this PyChrono predates KeyboardMode; '
                          'using "cumulative". Update to build 1187 or later '
                          'for "held".')

            steering_time = 1.0  # time to go from 0 to +1 (or from 0 to -1)
            throttle_time = 1.0  # time to go from 0 to +1
            braking_time = 0.3   # time to go from 0 to +1
            driver.SetSteeringDelta(render_step_size / steering_time)
            driver.SetThrottleDelta(render_step_size / throttle_time)
            driver.SetBrakingDelta(render_step_size / braking_time)

    else:
        raise ValueError(f"unknown INPUT_SOURCE {INPUT_SOURCE!r}")

    driver.Initialize()

    # -----------------------------------------------------------------------
    # Create the Irrlicht interface
    #
    # Two flavours: the vehicle one, which adds a chase camera and the driver
    # HUD, and the plain one for the crane. Everything after this point treats
    # them the same, because the pieces the loop uses (Run, BeginScene, Render,
    # EndScene, Synchronize, Advance) are on the base class.
    # -----------------------------------------------------------------------
    title = f"{VEHICLE if PLANT == 'vehicle' else PLANT} on {plan.name} - human in the loop"
    if plant.needs_vehicle_vis:
        vis = veh.ChWheeledVehicleVisualSystemIrrlicht()
        vis.SetWindowTitle(title)
        vis.SetWindowSize(1280, 800)
        vis.SetChaseCamera(chrono.ChVector3d(0.0, 0.0, 1.75), chase_dist, 0.5)
        vis.Initialize()
        # This guard cannot save the vehicle case and is here for the day it
        # can. ChWheeledVehicleVisualSystemIrrlicht::Initialize builds the HUD
        # through the video driver it just failed to make, so on a machine with
        # no display it segfaults INSIDE this call, one frame below Python. The
        # plain visual system further down returns from Initialize and is
        # caught properly. PLANT = "crane" takes that branch.
        require_window(vis, how="the push demo is the one that runs without one")
        vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
        vis.AddLightDirectional()
        vis.AddSkyBox()
        plant.attach(vis)
        if INPUT_SOURCE == "keyboard":
            vis.AttachDriver(driver)  # route Irrlicht key events to the driver

        # SHOW_*: the built-in overlay - nothing here is hand-drawn, every piece
        # is a flag or a method on `vis` itself
        vis.EnableStats(SHOW_VEHICLE_HUD)        # speed/steering/throttle/brake panel
        vis.SetHUDLocation(*HUD_CORNER)          # where that panel sits
        vis.ShowInfoPanel(SHOW_SIM_INFO_PANEL)   # Chrono's own tabbed info panel
                                                 # (bodies, contacts, timers); also
                                                 # toggles live with the 'i' key
        vis.ShowProfiler(SHOW_PROFILER)          # per-module timing bars
    else:
        ### PLANT = "crane": a plain visual system, no vehicle to attach ###
        vis = irr.ChVisualSystemIrrlicht()
        # Chrono's world here is Z-up, but a plain ChVisualSystemIrrlicht
        # defaults to a Y-up camera, which renders the ground as a wall. The
        # vehicle visual system sets this for you; this one does not.
        vis.SetCameraVertical(chrono.CameraVerticalDir_Z)
        vis.SetWindowTitle(title)
        vis.SetWindowSize(1280, 800)
        # Attach after Initialize, so require_window gets a turn: Initialize
        # binds every attached asset, and with no display that binding
        # segfaults before the guard can speak. See demos/manipulate/main.py.
        vis.Initialize()
        require_window(vis, how="the push demo is the one that runs without one")
        vis.AttachSystem(system)
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
    # Real-time setup (Demo 1)
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
    # One loop for both plants and both input sources. Everything that differs
    # between them was decided above and is behind `plant`, `driver` and `vis`;
    # nothing below branches on which part of the tutorial you are on.
    # -----------------------------------------------------------------------
    render_steps = math.ceil(render_step_size / step_size)
    report_steps = math.ceil(1.0 / step_size)  # console report once per sim second

    print(f"\nPLANT={PLANT}  INPUT_SOURCE={INPUT_SOURCE}"
          f"  REALTIME={realtime_mode}  step_size={step_size}")
    if INPUT_SOURCE == "keyboard" and gearbox and gearbox.present:
        ### TRANSMISSION: Chrono already binds these; this file need not ###
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

        # Get driver inputs (three floats) - the shape every plant here is driven through
        driver_inputs = driver.GetInputs()

        # THE BINDING: hand the three numbers to whatever is controlled. For a
        # Chrono::Vehicle this does nothing (the vehicle reads them in
        # Synchronize); for the crane it is where they land.
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
        # A Chrono::Vehicle steps its own ChSystem inside Advance; the crane
        # does not, so the system is stepped here instead. Stepping twice would
        # run the clock at double speed, which is why this is a branch.
        if not plant.steps_own_system:
            system.DoStepDynamics(step_size)
        if plant.needs_vehicle_vis:
            vis.Advance(step_size)

        # Console report: how far is the sim from wall time?
        if step_number % report_steps == 0:
            wall = time.perf_counter() - wall_start
            # A ChVehicle measures its own real-time factor per step. The crane
            # does not, so it is measured here over the reporting interval
            # instead: same quantity, coarser sampling.
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

        step_number += 1

        # Demo 1: spin in place for real time to catch up
        if realtime_mode == "per_step":
            rt_timer.Spin(step_size)
        elif realtime_mode == "cumulative":
            cum_timer.spin(system.GetChTime())


# =============================================================================
# CONFIGURATION
# =============================================================================

# PLANT: what are we controlling?
#   "vehicle"  a Chrono::Vehicle, which is what Demos 1 and 2 drive
#   "crane"    a gantry crane with a swinging payload, and no Chrono::Vehicle
#              anywhere in it. Watch the load swing as the bridge accelerates;
#              the console prints the swing angle and the miss distance.
# Either PLANT takes either INPUT_SOURCE. The crane has no ChVehicle, so it
# cannot use ChDataDriver or ChInteractiveDriver; it gets the same two inputs
# from ScriptedInputs and WindowInputs instead, and the loop cannot tell.
PLANT = "vehicle"

# VEHICLE: choose your car - "hmmwv" | "sedan" | "uazbus" | "gator" | "audi"
# "audi" is built from JSON rather than from a model wrapper class, which is
# what makes TRANSMISSION = "manual" possible: the wrappers each ship
# one powertrain and none of them ships a manual gearbox.
VEHICLE = "hmmwv"

# TRANSMISSION: which gearbox. "automatic" | "manual".
# Only VEHICLE = "audi" has both; the other models ship an automatic each and
# say so rather than silently ignoring this.
TRANSMISSION = "automatic"

# TRANSMISSION: start an automatic in MANUAL shift mode, so '[' and ']' do something
# immediately. Left in AUTOMATIC, the gearbox overrides your gear on the next
# step, which looks exactly like the shift keys being broken.
START_IN_MANUAL_SHIFT = False

# Where do the driver inputs come from?
#   "data"      Demo 1 - a scripted table, no human
#   "keyboard"  Demo 2 - a person at the keys
# Which class provides it depends on PLANT, and that is the point of Demo 2:
#   vehicle  ChDataDriver / ChInteractiveDriver, W/A/S/D in the Irrlicht window
#   crane    ScriptedInputs / WindowInputs, arrow keys in our own small window
INPUT_SOURCE = "data"

# Demo 2: what a keypress means.  "cumulative" | "held"
#   "cumulative"  a keypress nudges the input by a delta and it stays there
#   "held"        the input follows the keys held down, as in a driving game
# See the KEYBOARD_MODE comment in main() for why the difference matters.
KEYBOARD_MODE = "cumulative"

# How is real time enforced?  "none" | "per_step" | "vehicle" | "cumulative"
REALTIME = "none"

# Simulation step sizes.  Make step_size smaller (e.g. 5e-4) to see RTF > 1.
step_size = 3e-3
tire_step_size = 1e-3

# Tire model (RIGID, FIALA, TMEASY, PAC89, PAC02)
tire_model = veh.TireModelType_TMEASY

# Time interval between two render frames
render_step_size = 1.0 / 50  # FPS = 50

# The built-in Irrlicht overlay - add or remove pieces of it here
# instead of writing your own on top of the 3D view
SHOW_VEHICLE_HUD = True         # speed/steering/throttle/brake panel
HUD_CORNER = (10, 10)           # (x, y) pixels from the top-left corner
SHOW_SIM_INFO_PANEL = False     # Chrono's tabbed info panel (bodies/contacts/timers)
SHOW_PROFILER = False           # per-module timing bars

main()
