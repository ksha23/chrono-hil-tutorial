# Chrono support for human-in-the-loop simulation (PyChrono tutorial)

Run Chrono in real time with a person providing live control input.

## Setup

```bash
conda create -n chrono_hil -c projectchrono -c conda-forge pychrono pygame python=3.13
conda activate chrono_hil
```

Do **not** `pip install pychrono` -- the package with that name on PyPI is an
unrelated library. PyChrono comes from the `projectchrono` conda channel.

Files:

| file | what it is |
|---|---|
| `tutorial_HIL_driver.py` | the tutorial (HMMWV on rigid terrain, Irrlicht window) |
| `operator_console.py` | a pygame window that sends driver inputs over UDP and shows telemetry |
| `probe_gamepad.py` | prints which SDL axis/button each control on your gamepad/wheel maps to |

## Parts

All switches live in the `CONFIGURATION` section at the bottom of
`tutorial_HIL_driver.py`.

| part | `INPUT_SOURCE` | `REALTIME` | `SEND_FEEDBACK` | what you see |
|---|---|---|---|---|
| 1. Keep it real-time | `"data"` | `"none"` -> `"per_step"` / `"vehicle"` / `"cumulative"` | `False` | scripted drive; console shows sim time vs wall time, drift, RTF |
| 2. Human on the keyboard | `"keyboard"` | `"vehicle"` | `False` | arrow keys in the Irrlicht window drive the HMMWV |
| 3. Bring your own device | `"udp"` (or `"gamepad"`) | `"vehicle"` | `False` | `operator_console.py` in a second terminal drives the HMMWV |
| 4. Close the loop | `"udp"` | `"vehicle"` | `True` | operator console shows speed, RTF, lateral acceleration |

Part 3 with `"udp"` needs nothing but a second terminal:

```bash
python tutorial_HIL_driver.py          # terminal 1
python operator_console.py             # terminal 2 (or on another machine: python operator_console.py <sim ip>)
```

Part 3 with `"gamepad"` is optional and needs a gamepad or steering wheel. Run
`probe_gamepad.py` to find the axis numbers and edit `GamepadInput.MAPPINGS`.

## Things to try

- `REALTIME = "none"` with `step_size = 5e-4`: RTF goes above 1 and no timer can save you.
- Compare `drift` for `"per_step"` and `"cumulative"` over a few minutes.
- Set `SmoothedInputs(gain=50.0)` in Part 3 and feel what raw inputs do to the suspension.
- Unplug the network mid-run (or stop the operator console): the last input is held.
