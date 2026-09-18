# Chrono support for human-in-the-loop simulation (PyChrono tutorial)

Run Chrono in real time with a person providing live control input.

The two patterns worth taking away: keeping a simulation real-time (Part 1)
and closing an external device's control loop back to it (Part 4). Both show
up anywhere a person or outside hardware talks to a live simulation. Parts 2
and 3 are two ways to feed a human's input in; Parts 5-8 are bonus material,
not the point.

The slide deck (`tutorial_HIL_driver.pptx`, and the same thing as a PDF) is a
25-slide, 30-minute walkthrough. It opens on the gantry crane of Part 8 -- a
swinging load that only a person can place -- so that the three-float driver
contract arrives as the answer to a question rather than as a definition. The
body is the two patterns that transfer: keeping the simulation real-time
(Part 1) and closing an external device's loop back to it (Part 4), with the
keyboard (Part 2) as the easy case in between. Parts 6-8 are one summary slide
near the end; Parts 3 and 5 are repo-only.

## Setup

```bash
conda create -n chrono_hil -c conda-forge projectchrono::pychrono pygame python=3.13
conda activate chrono_hil
```

Two ways to end up with a PyChrono that cannot run this tutorial, both of which
install without an error message:

- **`pip install pychrono`** installs an unrelated PyPI package of the same name.
- **conda-forge also publishes a `pychrono` 10.0.0**, and it is a different
  package: 4.7 MB against 498 MB, shipping only `core`, `fea` and `robot`. This
  tutorial imports `pychrono.vehicle` and `pychrono.irrlicht`, and neither is in
  it, so it fails on the first import. Same name, same version number, no
  warning. The `projectchrono::` prefix above is what pins the right one --
  without it, listing `-c conda-forge` first is enough to get the wrong one.

Check what you got with `python -c "import pychrono.vehicle, pychrono.irrlicht"`.

`pygame` is only needed for Part 4 (`operator_console.py`); a gamepad or
wheel is read natively by Chrono and needs no extra package.

**Intel Macs:** `osx-64` PyChrono is frozen at 8.0.0 (2023) and much of the API
used here does not exist in it. Apple Silicon (`osx-arm64`), Linux and Windows
all have 10.0.0. Note that Chrono::Sensor is not built for macOS on either
architecture -- it is in the Linux and Windows packages only, and nothing in
this tutorial needs it.

Files:

| file | what it is |
|---|---|
| `tutorial_HIL_driver.py` | the tutorial (HMMWV -- or `VEHICLE` of your choice -- on rigid terrain, Irrlicht window) |
| `operator_console.py` | a pygame window that sends driver inputs over UDP and prints telemetry |
| `hil_gearbox.py` | Part 6: reading and driving a vehicle's transmission |
| `hil_scene.py` | Part 7: flat terrain, or the Mcity digital twin |
| `hil_plants.py` | Part 8: the vehicle, a Viper rover, and a gantry crane |

## Parts

All switches live in the `CONFIGURATION` section at the bottom of
`tutorial_HIL_driver.py`.

| part | `INPUT_SOURCE` | `REALTIME` | `SEND_FEEDBACK` | what you see |
|---|---|---|---|---|
| 1. Keep it real-time | `"data"` | `"none"` -> `"per_step"` / `"vehicle"` / `"cumulative"` | `False` | scripted drive; console shows sim time vs wall time, drift, RTF |
| 2. Human on the keyboard | `"keyboard"` | `"vehicle"` | `False` | `W`/`A`/`S`/`D` in the Irrlicht window drive the HMMWV (see `KEYBOARD_MODE`) |
| 3. A gamepad or wheel | `"gamepad"` | `"vehicle"` | `False` | joystick/wheel drives the HMMWV, read natively -- no pygame |
| 4. A device Chrono doesn't know, and closing the loop | `"udp"` | `"vehicle"` | `True` | `operator_console.py` in a second terminal drives the HMMWV and shows telemetry back |
| 5. Customize the overlay / choose your car | any | any | any | `SHOW_*` switches and `VEHICLE` (see below) |
| 6. Change gear | `keyboard` / `udp` | any | any | `TRANSMISSION`, and the keys printed at startup |
| 7. Drive somewhere real | any | any | any | `SCENE = "mcity"` puts the car in the Mcity digital twin |
| 8. Control something that isn't a car | `udp` / `data` | any | any | `PLANT = "rover"` or `"crane"` |

## Part 2: what a keypress means

Driving is `W`/`A`/`S`/`D`, plus `C` to center the steering, `R` to release the
pedals and `L` to lock the current inputs. The **arrow keys are not driving
controls** -- they zoom and orbit the chase camera, which is a separate Irrlicht
event receiver. (Part 4's `operator_console.py` *does* drive with the arrow keys,
but that is our own pygame window, not Chrono's.)

`KEYBOARD_MODE` picks what holding a key actually means, and the two answers are
worth comparing because Part 4 has to answer the same question for its own device:

| `KEYBOARD_MODE` | what a key does | configured by |
|---|---|---|
| `"cumulative"` | each keypress nudges a target by a fixed delta, and the target stays where you left it | `SetThrottleDelta`, `SetSteeringDelta`, `SetBrakingDelta` |
| `"held"` | the input follows the keys currently held down and ramps back when you let go, as in a driving game | `SetGains` |

`"cumulative"` is the historical Chrono::Vehicle behaviour and is still the
default. `"held"` is the interesting one here, because it is the *same model the
UDP console already uses*: `operator_console.py` re-sends absolute steering,
throttle and braking every frame, and `SmoothedInputs` ramps toward them. So
`"held"` is Chrono doing for its own keyboard exactly what Part 4 does by hand
for a device Chrono has never heard of -- with `SetGains` as the shared ramp rate.

```python
KEYBOARD_MODE = "held"
INPUT_SOURCE = "keyboard"
```

`"held"` needs the `KeyboardMode` API, which landed in PyChrono build `1187`
(August 2026). On an older build the tutorial prints a note and stays cumulative
rather than failing.

Part 3 needs a gamepad or steering wheel. Set `JOYSTICK_CONFIG` to one of the
JSON files that ship with Chrono in `data/vehicle/joystick/` --
`controller_XboxOneForWindows.json`, `controller_LogitechRumblePad2.json`,
`controller_WheelPedalsAndShifters.json`, or `controller_Default.json` -- or
write your own. Set `JOYSTICK_DEBUG = True` and run the tutorial to print
live axis/button numbers for your device -- no separate probe script needed.

Part 4 needs nothing but a second terminal:

Terminal 1, with `INPUT_SOURCE = "udp"`:

```bash
python tutorial_HIL_driver.py
```

Terminal 2 (add the simulation's IP instead to drive it from another machine):

```bash
python operator_console.py
```

Do not paste those with a trailing `# comment`: zsh only treats `#` as a comment
when `INTERACTIVE_COMMENTS` is set, and otherwise hands it to the script as the
simulation's hostname.

## Part 5: customize the built-in overlay

The Irrlicht window already ships with an on-screen HUD (the speed/steering/
throttle/brake panel you've been watching in every part) plus Chrono's own
tabbed info panel (bodies, contacts, timers) and a profiler. None of it is
hand-drawn -- it's all flags and method calls on the `vis` object, so there is
no need to build a custom overlay to add or remove pieces of it:

| switch | method | what it does |
|---|---|---|
| `SHOW_VEHICLE_HUD` | `vis.EnableStats(bool)` | the speed/steering/throttle/brake panel |
| `HUD_CORNER` | `vis.SetHUDLocation(x, y)` | where that panel sits on screen |
| `SHOW_SIM_INFO_PANEL` | `vis.ShowInfoPanel(bool)` | Chrono's tabbed panel (bodies/contacts/timers) -- also toggles live with the `i` key while the sim is running |
| `SHOW_PROFILER` | `vis.ShowProfiler(bool)` | per-module timing bars |

Set `SHOW_VEHICLE_HUD = False` to remove the default panel entirely, or turn
on `SHOW_SIM_INFO_PANEL` / `SHOW_PROFILER` to add Chrono's other built-in
panels -- no new drawing code required either way.

## Choose your car

`VEHICLE` picks which Chrono::Vehicle model gets built -- `"hmmwv"` (default),
`"sedan"`, `"uazbus"`, `"gator"`, or `"audi"`. `build_vehicle()` is the only
place that knows the differences between them; everything else (terrain,
driver, vis, the simulation loop) uses the same `GetVehicle()` /
`GetSystem()` / `Synchronize()` / `Advance()` interface no matter which one
you pick.

```python
VEHICLE = "uazbus"  # try "hmmwv", "sedan", "uazbus", "gator", "audi"
```

`"audi"` is the odd one out: it is assembled from JSON files rather than from a
model wrapper class, which is how most real Chrono::Vehicle work is done and
which is what makes Part 6's manual gearbox possible. `JsonVehicle` in the
tutorial is the six-line adapter that lets the rest of the file treat it like
the others.

## Part 6: change gear

The three numbers a `ChDriver` carries -- steering, throttle, braking -- are
the whole human interface, and a gear is not one of them. It belongs to the
vehicle, so it is reached through the vehicle:

```python
transmission = vehicle.GetTransmission()
transmission.ShiftUp()                                  # or ShiftDown, SetGear
transmission.asAutomatic().SetDriveMode(...)            # D / N / R
transmission.asAutomatic().SetShiftMode(...)            # let it shift, or row it
```

On the keyboard you do not have to write any of that. Chrono's own Irrlicht
event receiver already binds it, and `vis.AttachDriver(driver)` is what wires
it up; the tutorial prints the mapping at startup:

| key | automatic | manual |
|---|---|---|
| `Z` | toggle drive mode D / R | -- |
| `X` | neutral | -- |
| `T` | toggle AUTO / MANUAL shifting | -- |
| `[` `]` | shift down / up | shift down / up |
| `Q` `E` | -- | clutch out / in |

For a device Chrono has never heard of (Part 4) nothing is wired up for you,
which is the point of Part 4. `hil_gearbox.Gearbox` is the small adapter, and
`operator_console.py` sends the commands over the socket it already uses,
in an optional fourth field. Note what that field is not: the three numbers
are *levels*, re-sent every frame, and a lost packet costs nothing. A gear
command is an *event*, and a lost one is a shift that never happened -- so it
is sent once, on the key-down edge, and applied exactly once.

```python
VEHICLE = "audi"          # the only model here with a manual gearbox
TRANSMISSION = "manual"   # "automatic" | "manual"
START_IN_MANUAL_SHIFT = True   # or '[' and ']' look broken: an automatic left
                               # in AUTOMATic mode overrides your gear next step
```

## Part 7: drive somewhere real

`SCENE = "mcity"` swaps the 200 x 200 m patch for the Mcity digital twin: a
real 32-acre test facility, its road surface driven as a collision mesh and
its buildings, poles, signal heads and barriers drawn from a placement
manifest.

The scene is a third-party dataset of a few hundred megabytes and is *not*
shipped here. It is generated once, by the converter in the Chrono tree:

```bash
cd <chrono>/src/demos/vehicle/terrain/mcity
python3 -m pip install usd-core
./setup_mcity.sh --repo /path/to/mcity-digital-twin
```

Set `MCITY_DIR` if you built it somewhere other than `<chrono data>/mcity`. If
it is not there, the tutorial says so and falls back to flat terrain rather
than failing.

`MCITY_DETAIL` is the knob for a weaker machine:

| level | what is drawn | notes |
|---|---|---|
| `"ground"` | the road surface only | full elevation and full geometry to drive on, nothing else drawn. Start here on a laptop. |
| `"light"` | plus poles, signal heads, street lights | ~430 placements, ~240k triangles |
| `"full"` | everything in the manifest | ~860 placements |

Two details worth knowing, both of which cost time to rediscover:

- The car drives on the *drawn* geometry. Mcity also publishes an OpenDRIVE
  network, and its elevation profile differs from the artist's road mesh by
  -0.24 to +0.29 m at the 5th and 95th percentiles -- enough to watch a car
  float and sink. Using the mesh for both makes them the same surface.
- The spawn height is read from the ground mesh, not from `terrain.GetHeight()`.
  `RigidTerrain` answers height queries by raycasting the collision system, and
  that system does not exist until the first `DoStepDynamics`; asking during
  setup returns zero, which on a site whose datum is 274 m drops the car out of
  the world.

`hil_scene.load_scenery()` is worth a read for one trick: a `ChVisualShape` is
added to a body *with a frame*, and the same shape object can be added again at
another frame. 860 placements therefore cost 230 meshes, not 860 copies.

## Part 8: control something that isn't a car

Two things about the plain visual system are worth knowing before you run the
rover or the crane, because both were invisible while Part 8 was only ever
checked headlessly:

- A plain `ChVisualSystemIrrlicht` defaults to a **Y-up camera** while this
  world is Z-up, so without `SetCameraVertical(CameraVerticalDir_Z)` the ground
  renders as a wall. `ChWheeledVehicleVisualSystemIrrlicht` sets this for you;
  the plain one does not.
- The Irrlicht backend does not draw `ChVisualShapeSegment` at all -- it handles
  boxes, spheres, cylinders, capsules, cones, barrels, ellipsoids, surfaces and
  meshes, and silently ignores anything else. VSG does draw segments. The crane's
  cable is therefore a thin cylinder, re-aimed once per step, or the payload
  appears to float unattached.

Nothing about the pattern needs a vehicle. `PLANT` picks what the same three
numbers, arriving from the same devices, are wired into:

| `PLANT` | what it is | how the inputs map |
|---|---|---|
| `"vehicle"` | a Chrono::Vehicle (Parts 1-7) | as usual |
| `"rover"` | a Viper rover | steering -> wheel angle, throttle -> commanded wheel speed |
| `"crane"` | a gantry crane with a payload on a cable | steering -> cross-travel, throttle/braking -> forward/reverse travel |

The crane is the interesting one. There is no Chrono::Vehicle in it at all --
four rigid bodies, two speed motors and a distance constraint -- and the
payload swings freely, with nothing to damp it but you. The console prints the
swing angle and how far the load is from the green pad, so try to set it down
without letting it swing. It is a genuinely hard manual task, which is the
clearest answer to why anyone puts a human in a simulation loop at all.

Neither the rover nor the crane has a `ChVehicle`, so `ChInteractiveDriver`
cannot read the keyboard for them; use `INPUT_SOURCE = "udp"` and drive them
from `operator_console.py`, which needs no changes at all to do it. That is the
lesson rather than the limitation: `DriverInputs` in the tutorial is the entire
`ChDriver` contract rewritten in twelve lines of Python.

```python
PLANT = "crane"
INPUT_SOURCE = "udp"
REALTIME = "vehicle"      # falls back to "per_step" when there is no vehicle
```

## Part 9: reach into the scene (hil_manipulate.py)

Parts 1-8 put a person in the *control* loop. This is the other thing people
want a human for, and it is not the same: pushing a robot to see whether its
controller recovers, dragging an object somewhere and recording where you put
it, moving a limp arm by hand.

Chrono ships **no click-and-drag manipulator**. The mouse in both the Irrlicht
and VSG backends is wired to the camera, and the one Irrlicht picking call in
the tree is a commented-out line in `ChIrrCamera.cpp`. But the primitives are
all there, and `hil_manipulate.py` is the twenty lines that assemble them:

| piece | what it does |
|---|---|
| `ChCollisionSystem::RayHit()` | pick a body along a ray, the way a click would |
| `ChRayhitResult.hitModel` | `-> GetContactable() -> CastToChBody()` |
| `ChLinkTSDA` | a stiff, damped rubber band from a handle body to the pick point |

Dragging with a spring instead of teleporting is the point: the body still
collides, still carries momentum, and a controller holding it still fights back.

One command, one process, two windows -- the 3D view and a small input panel:

```bash
python hil_manipulate.py go2
python hil_manipulate.py arm
python hil_manipulate.py place
```

**Click straight on the 3D window.** Press the left button on a body to pick it,
drag to pull it, release to let go. Arrow keys and `Z`/`X`/`C`/`T` work there too,
whichever window has focus.

The mouse does nothing but manipulate. `AddCamera` builds an `RTSCamera`, which
normally takes the mouse for orbit/pan/zoom, so a drag moved the body *and* swung
the view. Its input receiver is switched off, and the camera is on keys instead:

| keys | |
|---|---|
| mouse drag | grab and pull a body |
| arrows, `[` `]` | move the grab handle (X/Y, then Z) |
| `Z` `X` `C` `T` | grab/release, cycle selection, reset, log pose |
| `Q` `E` *while dragging* | rotate the drag plane -- the depth control |
| `A` `D` / `W` `S` / `R` `F` | camera orbit / zoom / height |

The Go2's joints are **torque**-actuated with a PD stance controller
(`StanceHolder`), not position-actuated. That distinction is the demo: a
position-actuated joint is a *constraint*, so the solver holds its angle exactly
and pulling a leg does nothing at all -- a soft grab cannot move it and a stiff
one only destabilises the solver until the robot is flung across the scene.
Torque actuation is compliant, so the leg gives when pulled and the controller
pulls back when released.

What you should see: grabbing a calf and dragging takes that leg's worst joint
from about 3 degrees of error to 14, and releasing recovers it to about 11. It
does not go all the way back, because the foot is planted and friction holds it
there -- which is what a real quadruped does too. Lift the leg clear of the
ground before releasing and the recovery is obvious.

Dragging at a fixed distance from the camera confines the handle to a sphere, so
a leg can be swung across the view but never pulled toward or away from it --
which is why only some parts of a robot feel reachable. The cursor ray is instead
intersected with a **drag plane** through the grab point, one that contains the
surface normal and faces the camera as squarely as it can. `Q`/`E` rotate that
plane about the surface normal, which is what turns sideways mouse motion into
depth. Genesis puts the same rotation on the scroll wheel.

PyChrono genuinely cannot read that window: SWIG directors are off so
`irr::IEventReceiver` cannot be subclassed, and `getCursorControl()` and
`getSceneCollisionManager()` both come back as unwrapped `SwigPyObject`s. But the
window belongs to this process and macOS will describe it -- `NSEvent.mouseLocation()`,
`CGEventSourceButtonState`, `CGEventSourceKeyState` and `CGWindowListCopyWindowInfo`,
none of which need accessibility permission. The one thing Irrlicht will not hand
over is the ray for a screen pixel, and `ICameraSceneNode` *is* wrapped, so
`getFOV()` and `getAspectRatio()` are enough to build it exactly.

That needs `pip install pyobjc-framework-Quartz`. Without it the script falls back
to a small pygame input panel (keep *that* focused instead).

To drive it from `operator_console.py` in a second terminal instead, or from
another machine, add `--udp`:

```bash
python hil_manipulate.py go2 --udp
```

| mode | what it shows |
|---|---|
| `go2` | a real Unitree Go2 from URDF, joint motors holding a stance while you haul a leg out of it |
| `arm` | a Franka Emika Panda in hand-guiding mode: it holds its pose, and complies while you hold a link |
| `arm-limp` | the same arm with nothing holding it up, so it collapses under gravity and stays down |
| `place` | kinematic placement: the pose is *set*, not pushed, and `T` logs it to `placement_place.log` |

Input comes from `operator_console.py` over UDP, unchanged -- arrows move the
handle, `[` and `]` raise and lower it, `Z` grabs, `X` cycles the selection, `T`
logs a pose. That is not a design flourish: **PyChrono cannot read the Irrlicht
window at all.** `irr::IEventReceiver` is exposed but abstract with no
constructor (SWIG directors are off), and `device.getCursorControl()` returns an
unwrapped `SwigPyObject`. No keyboard, no mouse. Part 4's socket was already the
answer.

The Go2 comes from [wty-yy/go2_rl_gym](https://github.com/wty-yy/go2_rl_gym)
and is not shipped here (`go2_assets/` is gitignored):

```bash
git clone https://github.com/wty-yy/go2_rl_gym
export GO2_URDF=go2_rl_gym/resources/robots/go2/urdf/go2.urdf
```

Three things about that URDF cost real time, and the script handles all of them:

- **Eight links have no `<inertial>`** (collision-only cylinders on the calves).
  Chrono's parser *segfaults* on them rather than complaining. They are stripped.
- **The visual meshes are Collada.** Chrono reads every mesh with `tiny_obj`, so
  a `.dae` reaches a Wavefront parser and segfaults. Convert them once and the
  script picks the `.obj` up automatically:

  ```bash
  pip install trimesh pycollada
  python - <<'PY'
  import trimesh, glob, os
  os.makedirs("go2_assets/obj", exist_ok=True)
  for d in glob.glob("go2_assets/dae/*.dae"):
      trimesh.load(d, force="mesh").export(
          "go2_assets/obj/" + os.path.splitext(os.path.basename(d))[0] + ".obj")
  PY
  ```

  With no `obj/` beside the `dae/`, the visuals are dropped and the collision
  primitives are drawn instead -- 5 boxes, 17 cylinders, 5 spheres. Correct
  physics, blocky picture.
- **The default NSC solver cannot hold it still.** PSOR at 50 iterations cannot
  resolve eighteen motor constraints and four foot contacts in one step, and
  friction is what loses: the robot creeps across the floor as though it were on
  ice. Barzilai-Borwein at 200 iterations takes the residual drift from 13 mm/s
  to 0.3 mm/s. These are the same settings `tutorial_HIL_driver.py` already uses
  on vehicles, for the same reason.
- **`ChParserURDF` leaves collision *disabled*** on every body it creates, so
  the robot drops silently through the floor. It is enabled on the feet only;
  enabling it everywhere makes adjacent links fight and the robot tears itself
  apart.

The stance is held by position motors rather than a learned policy. Swapping in
the repo's pretrained `.pt` would need torch plus that policy's exact
observation layout; the demo is about the perturbation, not the controller.

## The mouse layer is not Chrono

The grab-and-drag in `hil_manipulate.py` reaches the Irrlicht window through
macOS itself. That is 135 lines, macOS-only, and a workaround rather than a
capability: PyChrono exposes `irr::IEventReceiver` but without SWIG directors,
so it is abstract with no constructor and cannot be implemented from Python.

Adding one line to Chrono's SWIG interface fixes it, and the same feature then
takes 18 portable lines. Built, tested and written up in
[`experimental/`](experimental/README.md) -- along with what Genesis gives its
users for comparison. Nothing there is needed to follow this tutorial.

## Things to try

- `REALTIME = "none"` with `step_size = 5e-4`: RTF goes above 1 and no timer can save you.
- Compare `drift` for `"per_step"` and `"cumulative"` over a few minutes.
- Set `SmoothedInputs(gain=50.0)` in Part 4 and feel what raw inputs do to the suspension.
- Unplug the network mid-run (or stop the operator console): the last input is held.
- `JOYSTICK_DEBUG = True`: move one axis at a time and watch the printed numbers to build your own controller config.
- Set `VEHICLE = "uazbus"` and try to drive the same scripted course as the HMMWV -- same driver, same terrain, very different vehicle.
- `KEYBOARD_MODE = "held"` vs `"cumulative"` with the same `SetGains`: the second one ratchets, the first one drives.
- `SHOW_SIM_INFO_PANEL = True` and press `i` while the sim is running: same panel, two ways to reach it.
- `VEHICLE = "audi"`, `TRANSMISSION = "manual"`, `START_IN_MANUAL_SHIFT = True`: pull away in third and feel the engine bog down.
- `T` then `[` in the Irrlicht window: take an automatic out of auto and hold a gear through a corner.
- `SCENE = "mcity"` with `MCITY_DETAIL = "ground"` first, then `"light"`: watch the frame rate, and note that the driving does not change.
- `PLANT = "crane"` with `INPUT_SOURCE = "udp"`: put the load on the pad with the swing under 2 degrees. Harder than it looks.
- `PLANT = "rover"` and hold the brake: it coasts rather than stopping, because `ViperDriver` has no brake input. Real limits show up like this.
