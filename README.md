# Chrono support for human-in-the-loop simulation (PyChrono tutorial)

A person's action changes the state of a running simulation, the simulation's
response changes what that person does next, and the cycle closes fast enough
that they can keep reacting. That is what this tutorial means by
human-in-the-loop, and everything here is an instance of it.

## Run the demos

```bash
conda env create -f environment.yml
conda activate chrono-hil
```

On macOS, `unset DYLD_LIBRARY_PATH` first if your shell sets it: it shadows
conda's libChrono and PyChrono fails to import with a missing-symbol error.

| # | demo | command | what you do |
|---|---|---|---|
| 1 | Does the clock matter | `python tutorial_HIL_driver.py` | set `REALTIME = "none"`, watch the drift column run away, then set it back |
| 2 | A person driving | `python tutorial_HIL_driver.py` | `INPUT_SOURCE = "keyboard"`; W/A/S/D drive, arrows are the camera |
| 3 | Reaching in | `python hil_manipulate.py go2` | click and drag a leg; the locomotion policy steps to keep its feet |
| 3b | | `python hil_manipulate.py arm` | drag a Franka link; `arm-limp` for motors off |
| 4 | How hard can you shove it | `python hil_push.py` | click where the push lands, set direction and magnitude, SPACE fires |

Demo 4 without a human, which is how the numbers in the talk were produced:

```bash
python hil_push.py --headless --sweep 1700:1950:50 --dir 1,0,0 --fresh
```

Every script takes `--help`. The switches for demos 1 and 2 live in the
`CONFIGURATION` block at the bottom of `tutorial_HIL_driver.py`.

## What is in here

| path | |
|---|---|
| `tutorial_HIL_driver.py` | demos 1 and 2, and Parts 1 to 8. Imports `hil_scene`, `hil_gearbox`, `hil_plants` |
| `hil_manipulate.py` | demo 3: picking and dragging, the Go2 policy, the Franka |
| `hil_push.py` | demo 4: the push rig and its panel |
| `make_slides.py` | builds the deck; `--pdf` exports it too |
| `experimental/` | the one-line SWIG change that would let PyChrono read its own window |
| `archive/` | earlier demos, not presented: the placement tool and the UDP console |
| `ASSETS.md` | where the vendored robot meshes and the policy came from |

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

**Intel Macs:** `osx-64` PyChrono is frozen at 8.0.0 (2023) and much of the API
used here does not exist in it. Apple Silicon, Linux and Windows all have 10.0.0.

## Demos 1 and 2: the clock, and a person driving

Both are `tutorial_HIL_driver.py`, configured in the `CONFIGURATION` block at
the bottom of the file.

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

## Driving something that is not a vehicle

`ChDriver` and `ChInteractiveDriver` live in Chrono::Vehicle. Nothing else in
Chrono has a driver abstraction, so the question "how do I put a person in the
loop of my crane" has no built-in answer. This is the pattern this repo uses,
and it is three decisions.

**1. Normalise the input.** Pick a small, bounded set of numbers that a device
produces and a plant consumes, and make it device-independent. This tutorial
reuses the vehicle convention -- steering, throttle, braking in [-1,1] and
[0,1] -- so one keyboard, one gamepad and one socket can drive a car, a rover
and a crane without knowing which is on the other end.

**2. Bind those numbers to actuation.** This is the only plant-specific part,
and Chrono gives you four routes:

| the human's number becomes | Chrono | used by |
|---|---|---|
| a driver input | `ChDriver`, `ChInteractiveDriver` | the HMMWV |
| a motor setpoint | `ChLinkMotor*` + `ChFunctionSetpoint` | the crane, the rover |
| a force on a body | `AddAccumulator`, `AccumulateForce` | the push rig |
| a constraint to a handle you move | `ChLinkTSDA` | the mouse drag |
| a pose you set outright | `SetPos`, `SetRot` | placement, and not in the loop |

**3. Send something back.** Speed, a swing angle, a contact count -- whatever
the person needs to decide what to do next. Without it they are driving open
loop, which is not human-in-the-loop.

### The protocol

Every plant in `hil_plants.py` implements the same six methods, and the loop
never learns which one it has:

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

```python
while vis.Run():
    inputs = device.poll()        # never blocking: a late human is not a stalled sim
    plant.apply(inputs)           # <- the binding
    plant.synchronize(t, inputs)
    plant.advance(step)
    system.DoStepDynamics(step)
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

A shared convention buys you one console and one input path for every plant. It
charges you for it at the binding:

- The crane computes `throttle - braking`, because it has one travel axis and
  the convention gave it two pedals. No crane operator would recognise that.
- The rover's "braking" releases the drive rather than applying a brake, because
  `ViperDriver` has no brake input. It coasts down on rolling resistance instead
  of stopping dead, which is the honest behaviour for a machine built that way.
- The rover's steering is an angle in radians, not a normalised [-1,1], so the
  binding scales it. Getting that wrong is silent: the rover just barely turns.

Set `PLANT = "crane"` or `"rover"` in `tutorial_HIL_driver.py` to drive either.

## The Go2's locomotion policy

The quadruped is driven by a trained locomotion policy, not by a PD holding a
pose. That is the difference between a robot that stiffens against a shove and
one that picks a foot up and steps into it, and the push rig reports it as a
number: the stance PD tips at 325 N, the policy at 1850 N.

The checkpoint is third-party and not vendored here:

```
curl -sSL -o go2_assets/go2_policy.pt \
  https://raw.githubusercontent.com/wty-yy/go2_rl_gym/HEAD/deploy/pre_train/go2/go2_cts_150k.pt
```

It needs `torch`; without either the checkpoint or torch the scene falls back to
the stance PD and says so at startup. `GO2_POLICY_CKPT` overrides the path.

From `wty-yy/go2_rl_gym` (MIT). A legged_gym-family actor: 45 observations in,
12 joint targets out, run at 50 Hz over a PD at the physics rate.

## Demo 3: reaching into the scene (`hil_manipulate.py`)

Click a body in the 3D window and pull on it while its controller keeps working.
The pick is `ChCollisionSystem::RayHit`, which is already in PyChrono; the pull
is a stiff critically-damped `ChLinkTSDA` between the body and an invisible
handle that follows the cursor.

Two things that are easy to get wrong:

- **A ray sees COLLISION geometry, never visual geometry.** A link you can see
  but whose collision is off is invisible to every click. That accounted for
  every "it will not pick" bug here.
- **The spring's gains must scale with the mass being pulled.** A stiffness that
  feels right on a 134 kg ball is a catapult on a 0.154 kg shin. The gains are
  built from the body's own mass, as `k = m*w^2` and `c = 2*m*w`.

`go2` drags a quadruped held up by a trained locomotion policy, `arm` a Franka
whose motors hold position, `arm-limp` the same arm with the motors off.

## Demo 4: the push rig (`hil_push.py`)

A freehand drag cannot answer "how hard can I shove it", because no two drags
are the same: the force depends on how fast your hand moved and how long you
held the button. So the person keeps the parts where judgement helps -- where on
the body, and in which direction -- and the magnitude is scripted:

```
impulse J = F * dt      a constant force, held for a fixed window
```

Both are printed and logged, so "a 1850 N push for 50 ms, 92.5 N.s, on the base
COM, pointing +X" is reproducible by someone else. Sweeping the magnitude finds
the threshold where recovery stops, which is the number a robustness test exists
to produce.

## The mouse layer is not Chrono

The grab-and-drag in `hil_manipulate.py` reaches the Irrlicht window through
macOS itself. That is 135 lines, macOS-only, and a workaround rather than a
capability: PyChrono exposes `irr::IEventReceiver` but without SWIG directors,
so it is abstract with no constructor and cannot be implemented from Python.

Adding one line to Chrono's SWIG interface fixes it, and the same feature then
takes 18 portable lines. Built, tested and written up in
[`experimental/`](experimental/README.md) -- along with what Genesis gives its
users for comparison. Nothing there is needed to follow this tutorial.

