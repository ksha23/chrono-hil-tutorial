# Chrono support for human-in-the-loop simulation (PyChrono tutorial)

Run Chrono in real time with a person providing live control input.

The two patterns worth taking away: keeping a simulation real-time (Part 1)
and closing an external device's control loop back to it (Part 4). Both show
up anywhere a person or outside hardware talks to a live simulation. Parts 2
and 3 are two ways to feed a human's input in; Parts 5-8 are bonus material,
not the point.

The slide deck (`tutorial_HIL_driver.pptx`, and the same thing as a PDF) is a
30-minute walkthrough: Parts 1, 2 and 4 in full, then Parts 6-8 -- changing
gear, driving somewhere real, and steering something that is not a car -- more
briefly at the end. Parts 3 and 5 are repo-only; there is no time for them in
the talk.

## Setup

```bash
conda create -n chrono_hil -c projectchrono -c conda-forge pychrono pygame python=3.13
conda activate chrono_hil
```

Do **not** `pip install pychrono` -- the package with that name on PyPI is an
unrelated library. PyChrono comes from the `projectchrono` conda channel.
`pygame` is only needed for Part 4 (`operator_console.py`); a gamepad or
wheel is read natively by Chrono and needs no extra package.

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
| 2. Human on the keyboard | `"keyboard"` | `"vehicle"` | `False` | arrow keys in the Irrlicht window drive the HMMWV |
| 3. A gamepad or wheel | `"gamepad"` | `"vehicle"` | `False` | joystick/wheel drives the HMMWV, read natively -- no pygame |
| 4. A device Chrono doesn't know, and closing the loop | `"udp"` | `"vehicle"` | `True` | `operator_console.py` in a second terminal drives the HMMWV and shows telemetry back |
| 5. Customize the overlay / choose your car | any | any | any | `SHOW_*` switches and `VEHICLE` (see below) |
| 6. Change gear | `keyboard` / `udp` | any | any | `TRANSMISSION`, and the keys printed at startup |
| 7. Drive somewhere real | any | any | any | `SCENE = "mcity"` puts the car in the Mcity digital twin |
| 8. Control something that isn't a car | `udp` / `data` | any | any | `PLANT = "rover"` or `"crane"` |

Part 3 needs a gamepad or steering wheel. Set `JOYSTICK_CONFIG` to one of the
JSON files that ship with Chrono in `data/vehicle/joystick/` --
`controller_XboxOneForWindows.json`, `controller_LogitechRumblePad2.json`,
`controller_WheelPedalsAndShifters.json`, or `controller_Default.json` -- or
write your own. Set `JOYSTICK_DEBUG = True` and run the tutorial to print
live axis/button numbers for your device -- no separate probe script needed.

Part 4 needs nothing but a second terminal:

```bash
python tutorial_HIL_driver.py          # terminal 1 (INPUT_SOURCE = "udp")
python operator_console.py             # terminal 2 (or on another machine: python operator_console.py <sim ip>)
```

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

## Things to try

- `REALTIME = "none"` with `step_size = 5e-4`: RTF goes above 1 and no timer can save you.
- Compare `drift` for `"per_step"` and `"cumulative"` over a few minutes.
- Set `SmoothedInputs(gain=50.0)` in Part 4 and feel what raw inputs do to the suspension.
- Unplug the network mid-run (or stop the operator console): the last input is held.
- `JOYSTICK_DEBUG = True`: move one axis at a time and watch the printed numbers to build your own controller config.
- Set `VEHICLE = "uazbus"` and try to drive the same scripted course as the HMMWV -- same driver, same terrain, very different vehicle.
- `SHOW_SIM_INFO_PANEL = True` and press `i` while the sim is running: same panel, two ways to reach it.
- `VEHICLE = "audi"`, `TRANSMISSION = "manual"`, `START_IN_MANUAL_SHIFT = True`: pull away in third and feel the engine bog down.
- `T` then `[` in the Irrlicht window: take an automatic out of auto and hold a gear through a corner.
- `SCENE = "mcity"` with `MCITY_DETAIL = "ground"` first, then `"light"`: watch the frame rate, and note that the driving does not change.
- `PLANT = "crane"` with `INPUT_SOURCE = "udp"`: put the load on the pad with the swing under 2 degrees. Harder than it looks.
- `PLANT = "rover"` and hold the brake: it coasts rather than stopping, because `ViperDriver` has no brake input. Real limits show up like this.
