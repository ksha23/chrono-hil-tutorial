# Chrono support for human-in-the-loop simulation (PyChrono tutorial)

Run Chrono in real time with a person providing live control input.

The two patterns worth taking away: keeping a simulation real-time (Part 1)
and closing an external device's control loop back to it (Part 4). Both show
up anywhere a person or outside hardware talks to a live simulation. Parts 2
and 3 are two ways to feed a human's input in; Part 5 (choose your car,
customize the overlay) is a bonus, not the point.

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

Part 3 needs a gamepad or steering wheel. Set `JOYSTICK_CONFIG` to one of the
JSON files that ship with Chrono in `data/vehicle/joystick/` --
`controller_XboxOneForWindows.json`, `controller_LogitechRumblePad2.json`,
`controller_WheelPedalsAndShifters.json`, or `controller_Default.json` -- or
write your own. Set `JOYSTICK_DEBUG = True` and run the tutorial to print
live axis/button numbers for your device, the same job `probe_gamepad.py`
used to do by hand.

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
`"sedan"`, `"uazbus"`, or `"gator"`. `build_vehicle()` is the only place that
knows the differences between them; everything else (terrain, driver, vis,
the simulation loop) uses the same `GetVehicle()` / `GetSystem()` /
`Synchronize()` / `Advance()` interface no matter which one you pick.

```python
VEHICLE = "uazbus"  # try "hmmwv", "sedan", "uazbus", "gator"
```

## Things to try

- `REALTIME = "none"` with `step_size = 5e-4`: RTF goes above 1 and no timer can save you.
- Compare `drift` for `"per_step"` and `"cumulative"` over a few minutes.
- Set `SmoothedInputs(gain=50.0)` in Part 4 and feel what raw inputs do to the suspension.
- Unplug the network mid-run (or stop the operator console): the last input is held.
- `JOYSTICK_DEBUG = True`: move one axis at a time and watch the printed numbers to build your own controller config.
- Set `VEHICLE = "uazbus"` and try to drive the same scripted course as the HMMWV -- same driver, same terrain, very different vehicle.
- `SHOW_SIM_INFO_PANEL = True` and press `i` while the sim is running: same panel, two ways to reach it.
