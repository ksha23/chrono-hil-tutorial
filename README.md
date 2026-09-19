# Chrono support for human-in-the-loop simulation (PyChrono tutorial)

A person's action changes the state of a running simulation, the simulation's
response changes what that person does next, and the cycle closes fast enough
that they can keep reacting. That is what this tutorial means by
human-in-the-loop, and everything here is an instance of it.

This is the companion repository for a 30-minute tutorial talk. Four demos,
numbered 1 to 4 here and in the talk, and a small shared library they are
assembled from.

## Start here

```bash
conda env create -f environment.yml
conda activate chrono-hil
python demos/push/main.py --headless --mag 300 --dir 1,0,0
```

That last line needs no window and no human, and it prints a verdict in a few
seconds. If it works, everything else will. On macOS, `unset
DYLD_LIBRARY_PATH` first if your shell sets it: it shadows conda's libChrono
and PyChrono fails to import with a missing-symbol error.

Then open a window:

```bash
python demos/manipulate/main.py go2
```

Drag one of the quadruped's legs with the mouse and watch the locomotion
policy step to keep its feet.

## The four demos

| # | demo | command | what you do |
|---|---|---|---|
| 1 | Does the clock matter | `python demos/driver/tutorial_HIL_driver.py` | set `REALTIME = "none"`, watch the drift column run away, then set it back |
| 2 | A person driving | `python demos/driver/tutorial_HIL_driver.py` | set `INPUT_SOURCE = "keyboard"`; W/A/S/D drive, arrows are the camera |
| 3 | Reaching in | `python demos/manipulate/main.py go2` | drag a leg; the locomotion policy steps to keep its feet |
| 3 | | `python demos/manipulate/main.py arm` | drag a Franka link; `arm-limp` for motors off |
| 4 | How hard can you shove it | `python demos/push/main.py` | click where the push lands, set direction and magnitude, SPACE fires |

Demos 1 and 2 are the same script, configured by editing the `CONFIGURATION`
block at the bottom of `tutorial_HIL_driver.py` rather than by flags. Demos 3
and 4 take arguments; every script takes `--help`.

Each demo folder has a README of its own saying what to press and what to look
for: [demos/driver](demos/driver/README.md),
[demos/manipulate](demos/manipulate/README.md),
[demos/push](demos/push/README.md).

Demo 4 without a human, which is how the numbers in the talk were produced:

```bash
python demos/push/main.py --headless --sweep 1700:1950:50 --dir 1,0,0 --fresh
# RECOVERY THRESHOLD: always recovers at 1850 N (92.50 N.s),
#                     always falls at 1900 N (95.00 N.s)
```

It takes a few minutes. `--fresh` rebuilds the robot for every trial, which is
the only version of that threshold worth quoting to anyone;
`evaluate()` in `demos/push/rig.py` says why.

## What is in here

| path | |
|---|---|
| `demos/driver/` | demos 1 and 2, and the vehicle and crane parts |
| `demos/manipulate/` | demo 3: picking and dragging |
| `demos/push/` | demo 4: the push rig and its panel |
| `chronohil/` | everything demos 3 and 4 are assembled from. Portable. Its `__init__.py` is the map of what each file does |
| `chronohil/input/window/` | reading the 3D window. `native.py` is the portable way and needs one line in Chrono; `macos.py`, `linux.py` and `windows.py` ask the operating system instead, until that lands. The only directory in the project that names an operating system |
| `tests_parts.py`, `tests_drag.py` | the two regressions that keep coming back; see below |
| `make_slides.py` | builds the deck; `--pdf` exports it too, `--check` validates it |
| `experimental/` | the one-line SWIG change, and what it buys |
| `archive/` | earlier demos, not presented |
| `ASSETS.md` | where the vendored robot meshes and the policy came from |

## Checking it works

```bash
python tests_parts.py go2      # 17/17 parts respond to a drag
python tests_parts.py arm      # 10/10
python tests_drag.py arm       # MOVED 0.2430 m after a scripted 25 cm drag
python3 make_slides.py --check # every code quote in the deck still resolves
```

`tests_parts.py` is the regression that has come back in three disguises: a
name whitelist that missed a link, a mass-scaled spring too weak to move a
40 g foot, and a gripper with no controller at all. `tests_drag.py` drives the
demo's real press/drag/release code, which is the path every headless test
otherwise misses.

`make_slides.py` locates every code excerpt in the deck by anchor text rather
than by line number, so editing a demo cannot silently rot a slide. Run
`--check` after touching any file the deck quotes. It needs `python-pptx` and
`Pillow`, which are deliberately NOT in `environment.yml`: building the deck is
not part of running the demos, and nobody cloning this to try them should have
to install a PowerPoint library. `pip install python-pptx Pillow` if you want
it. `--pdf` additionally drives PowerPoint itself, so it is macOS only.

## Setup

`environment.yml` pins the right packages. If you build an environment by hand
instead, there are two ways to end up with a PyChrono that cannot run this,
both of which install without an error:

- **`pip install pychrono`** is an unrelated PyPI package of the same name.
- **conda-forge also publishes `pychrono` 10.0.0**, and it is a different
  package: 4.7 MB against 498 MB, with only `core`, `fea` and `robot`. This
  tutorial needs `pychrono.vehicle` and `pychrono.irrlicht`. Same name, same
  version, no warning. The `projectchrono` channel is what pins the right one.

Check with `python -c "import pychrono.vehicle, pychrono.irrlicht"`.

The build number is pinned too, not just the version: build 1187 is the first
with the `KeyboardMode::HELD` API demo 2 uses, and `pychrono=10.0.0` alone is
happy to hand you a build from five months earlier that does not have it.

**Intel Macs:** `osx-64` PyChrono is frozen at 8.0.0 (2023) and much of the API
used here does not exist in it. Apple Silicon, Linux and Windows all have 10.0.0.

**Windows: run the demos from the desktop, not over ssh.** Every demo here
works on Windows, including the headless ones, but only from a session that has
a real desktop. In a Windows OpenSSH shell you land in session 0, a service
window station, and there `import pychrono` never returns: it hangs inside the
extension modules that link a graphics stack, `vsg3d` first and `fsi` next if
you stub that one out. It is not slow, it is stopped, and PyChrono's own
`try: from . import vsg3d / except: pass` cannot catch a DLL that never
finishes loading. So `--headless` on Windows means "no window is opened", not
"no desktop is needed". If you must drive it remotely, use RDP, or hand the
command to the console session with
`schtasks /create /tn run /tr <your.bat> /sc once /st 00:00 /it /f` and
`schtasks /run /tn run`. The one thing that does work over ssh is
`python demos/driver/tutorial_HIL_driver.py --help`, because that exits before
the import. (Measured on 10.0.26200, `pychrono 10.0.0=py312h418371c_1187`.)

## Demos 1 and 2: the clock, and a person driving

Both are `demos/driver/tutorial_HIL_driver.py`, configured in the
`CONFIGURATION` block at the bottom of the file.

**`REALTIME`** decides whether the process sleeps off the time it did not need:

| | |
|---|---|
| `"none"` | no pacing. Watch the drift column in the console run away. |
| `"per_step"` | `ChRealtimeStepTimer.Spin(step)` once per loop. |
| `"vehicle"` | `vehicle.EnableRealtime(True)`; the same policy, applied inside `Advance()`. |
| `"cumulative"` | paces against total elapsed time, so it can catch up after a slow step. The per-step timers cannot. |

**`KEYBOARD_MODE`** decides what a keypress means, which is a real design
question and not a detail:

| | |
|---|---|
| `"cumulative"` | a press nudges the input and it stays where you left it. Fine for a test script, strange under a hand. |
| `"held"` | the input follows the keys currently down, like a driving game. Needs the `KeyboardMode` API (PyChrono build 1187 and later). |

W/A/S/D drive. The arrow keys are the chase camera, not the car.

Three more switches in the same block are worth knowing and are not demos:
`VEHICLE` and the `SHOW_*` overlay flags, `TRANSMISSION`, and `PLANT`.
[demos/driver/README.md](demos/driver/README.md) has the table.

## Driving something that is not a vehicle

`ChDriver` and `ChInteractiveDriver` live in Chrono::Vehicle. Nothing else in
Chrono has a driver abstraction, so the question "how do I put a person in the
loop of my crane" has no built-in answer. This is the pattern this repo uses,
and it is three decisions.

**1. Normalise the input.** Pick a small, bounded set of numbers that a device
produces and a plant consumes, and make it device-independent. This tutorial
reuses the vehicle convention -- steering, throttle, braking in [-1,1] and
[0,1] -- so one set of three numbers drives a car and a crane without either
end knowing what is on the other. `WindowInputs` in
`demos/driver/tutorial_HIL_driver.py` is the whole producing end: ~20 lines
that open a window, read three floats out of it and expose the same accessors
`ChDriver` does, so a plant that was written against `ChDriver` accepts it
unchanged.

**2. Bind those numbers to actuation.** This is the only plant-specific part,
and Chrono gives you four routes into a model, plus one that is not in the loop
at all:

| the human's number becomes | Chrono | used by |
|---|---|---|
| a driver input | `ChDriver`, `ChInteractiveDriver` | the HMMWV |
| a motor setpoint | `ChLinkMotor*` + `ChFunctionSetpoint` | the crane |
| a force on a body | `AddAccumulator`, `AccumulateForce` | the push rig |
| a constraint to a handle you move | `ChLinkTSDA` | the mouse drag |
| _a pose you set outright_ | `SetPos`, `SetRot` | _placement, and not in the loop_ |

**3. Send something back.** Speed, a swing angle, a contact count -- whatever
the person needs to decide what to do next. Without it they are driving open
loop, which is not human-in-the-loop.

### The protocol

Every plant in `demos/driver/hil_plants.py` implements the same six methods,
and the loop never learns which one it has:

```python
class Plant:
    needs_vehicle_vis = False   # a plain ChVisualSystemIrrlicht will do
    steps_own_system = False    # the caller steps the ChSystem

    def apply(self, inputs):          ...  # THE BINDING. The only plant-specific part.
    def synchronize(self, t, inputs): ...  # modules read each other
    def advance(self, step):          ...  # plant-internal integration, if any
    def speed(self):                  ...  # what goes back to the human
    def status(self):                 ...  # one line of plant-specific telemetry
    def attach(self, vis):            ...  # anything the visualiser must be told
```

The plant with no chase camera of its own adds a seventh, `chase_target()`,
naming the body the camera should follow.

```python
while vis.Run():
    inputs = device.poll()        # never blocking: a late human is not a stalled sim
    plant.apply(inputs)           # <- the binding
    plant.synchronize(t, inputs)
    plant.advance(step)
    if not plant.steps_own_system:
        system.DoStepDynamics(step)   # a ChVehicle steps its own inside Advance
    rt_timer.Spin(step)           # give the wall clock its due
```

### The crane, in full

Four bodies, two linear speed motors and one distance constraint. No vehicle,
no terrain, no tires.

```python
# Construction: a motor, and a setpoint function to steer it with.
self.long_motor = chrono.ChLinkMotorLinearSpeed()
self.long_motor.Initialize(bridge, ground, chrono.ChFramed(
    bridge.GetPos(), chrono.QuatFromAngleY(chrono.CH_PI_2)))
self.long_speed = chrono.ChFunctionSetpoint()
self.long_motor.SetSpeedFunction(self.long_speed)
system.AddLink(self.long_motor)

# The cable IS a distance constraint: a fixed radius from the trolley, free to
# swing in both directions. A spherical pendulum with a moving pivot.
self.cable = chrono.ChLinkDistance()
self.cable.Initialize(trolley, payload, False, trolley.GetPos(), payload.GetPos())
system.AddLink(self.cable)
```

```python
def apply(self, inputs):
    t = self.system.GetChTime()
    # Throttle drives forward, braking drives back: two pedals, one axis.
    long_cmd = (inputs.m_throttle - inputs.m_braking) * self.MAX_LONG_SPEED
    self.long_speed.SetSetpoint(long_cmd, t)
    self.cross_speed.SetSetpoint(inputs.m_steering * self.MAX_CROSS_SPEED, t)
```

`ChFunctionSetpoint` is the piece worth knowing. A Chrono motor is driven by a
`ChFunction` of time, and a human's input is not a function of time anybody can
write down in advance. The setpoint function is the adapter: push a new value
into it each step and the motor reads it as the current value.

The crane is worth building because nothing damps the swing but the operator.
Accelerate hard and the load swings, and it keeps swinging until someone drives
the trolley back under it. `status()` reports the swing angle, so the console
scores you.

### What the numbers MEAN is a decision, and it has a cost

A shared convention buys you one input path for every plant. It charges you
for it at the binding: the crane computes `throttle - braking`, because it has
one travel axis and the convention gave it two pedals. No crane operator would
recognise that.

Set `PLANT = "crane"` in `tutorial_HIL_driver.py` to drive it by hand. It has
no `ChVehicle`, so `ChInteractiveDriver` is not available to it -- a small
input window of our own opens instead, and the arrow keys there drive the
bridge and the trolley. Keep THAT window focused, not the 3D view.

One measured detail, because it is the real-time lesson in miniature: that
window is repainted 30 times a second, not once per step. Painting it every
step drops the crane to RTF 2.78 on this machine, against 1.00 with the
repaint throttled. Reading the keys stays on the physics clock, so no keypress
is missed -- it is drawing that cannot afford to be there.

## The Go2's locomotion policy

The quadruped is driven by a trained locomotion policy, not by a PD holding a
pose. That is the difference between a robot that stiffens against a shove and
one that picks a foot up and steps into it, and the push rig reports it as a
number: the stance PD recovers from 600 N and goes over at 625, the policy
recovers from 1850 N and goes over at 1900.

The checkpoint is vendored: `go2_assets/go2_policy.pt`, committed so the demos
run straight after a clone. See [ASSETS.md](ASSETS.md) for where it came from.
`GO2_POLICY_CKPT` points the loader at a different one.

It needs `torch`. Without torch the scene falls back to the stance PD and says
so at startup; with the checkpoint missing, nothing is printed and the startup
hint changes instead.

From `wty-yy/go2_rl_gym` (MIT). A legged_gym-family actor: 45 observations in,
12 joint targets out, run at 50 Hz over a PD at the physics rate.

## Demo 3: reaching into the scene

`demos/manipulate/main.py`. Click a body in the 3D window and pull on it while
its controller keeps working. The pick is `ChCollisionSystem::RayHit`, which is
already in PyChrono; the pull is a stiff critically-damped `ChLinkTSDA` between
the body and an invisible handle that follows the cursor.

Two things that are easy to get wrong:

- **A ray sees COLLISION geometry, never visual geometry.** A link you can see
  but whose collision is off is invisible to every click. That accounted for
  every "it will not pick" bug here.
- **The spring's gains must scale with the mass being pulled.** A stiffness that
  feels right on a 134 kg ball is a catapult on a 0.154 kg shin. The gains are
  built from the body's own mass, as `k = m*w^2` and `c = 2*m*w`, with a floor
  on the mass so that a 40 g foot on a driven leg still moves.
  `chronohil/config.py` carries the measurement behind every number in that
  sentence.

`go2` drags a quadruped held up by a trained locomotion policy, `arm` a Franka
whose motors hold position, `arm-limp` the same arm with the motors off, and
`place` a kinematic scene with no dynamics at all.

## Demo 4: the push rig

`demos/push/main.py`. A freehand drag cannot answer "how hard can I shove it",
because no two drags are the same: the force depends on how fast your hand
moved and how long you held the button. So the person keeps the parts where
judgement helps -- where on the body, and in which direction -- and the
magnitude is scripted:

```
impulse J = F * dt      a constant force, held for a fixed window
```

Both are printed and logged, so "a 1850 N push for 50 ms, 92.50 N.s, on the
base COM, pointing +X" is reproducible by someone else. Sweeping the magnitude
finds the threshold where recovery stops, which is the number a robustness test
exists to produce -- and that threshold is a band, not a number, which
`evaluate()` in `demos/push/rig.py` measures and explains.

## The mouse layer is not Chrono

The grab-and-drag in demo 3 reaches the Irrlicht window through the operating
system: Quartz and AppKit on macOS, Xlib on X11, user32 on Windows. That is 724
statements across four files -- one per platform, plus the pixel-to-ray
arithmetic all three share -- and no two of the platform files can be tested on
the same machine. It is a workaround rather than a capability: PyChrono exposes
`irr::IEventReceiver` but without SWIG directors, so it is abstract with no
constructor and cannot be implemented from Python.

Under Wayland it cannot be written at all. No Wayland client may ask where the
cursor is while it is over someone else's surface, so `linux.py` says so and
returns None, and the demo opens its own input window instead.

Adding one line to Chrono's SWIG interface fixes it, and the same capability
then takes 81 statements in one portable file, `chronohil/input/window/native.py`
-- or 18 for a bare receiver that only reports clicks. Built, tested and
written up in [`experimental/`](experimental/README.md), along with what
Genesis gives its users for comparison. Nothing there is needed to follow this
tutorial.

(Both counts are non-blank, non-comment, non-docstring lines. Counting a
hand-count of one file against a different rule for the other is how these
numbers drift apart.)
