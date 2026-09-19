# Demos 1 and 2: the clock, and a person driving

Both demos are this one script. Nothing is passed on the command line: every
switch is a constant in the `CONFIGURATION` block at the bottom of
`tutorial_HIL_driver.py`.

```bash
python demos/driver/tutorial_HIL_driver.py          # run whatever is configured
python demos/driver/tutorial_HIL_driver.py --help   # the switches, listed
```

## Demo 1: does the clock matter

```python
INPUT_SOURCE = "data"      # a scripted drive, no human
REALTIME     = "none"      # then rerun with "vehicle"
```

No window interaction needed. Watch the `drift` column in the console: with
`"none"` it runs away, because the simulation is going as fast as the machine
allows. Set `REALTIME = "vehicle"` and it stays near zero. That is the whole
precondition for a human in the loop, and it is one line.

`REALTIME` has four settings, and the fourth is the one worth knowing:

| | |
|---|---|
| `"none"` | no pacing at all |
| `"per_step"` | `ChRealtimeStepTimer.Spin(step)` once per loop |
| `"vehicle"` | `vehicle.EnableRealtime(True)`, the same policy inside `Advance()` |
| `"cumulative"` | paces against total elapsed time, so it can catch up after a slow step. The per-step timers cannot. |

## Demo 2: a person driving

```python
INPUT_SOURCE  = "keyboard"
KEYBOARD_MODE = "held"     # needs PyChrono build 1187 or later
```

Click the 3D window so it has focus, then:

- **W/A/S/D** drive. **C** centres steering, **R** releases the pedals, **L**
  locks the current inputs.
- **The arrow keys are the chase camera**, not the car. This catches everyone,
  because demo 3's input window drives with the arrows.
- The gear keys are printed at startup, from `hil_gearbox.KEYBOARD_HELP`.

`KEYBOARD_MODE` is the point of the demo as much as the driving is. With
`"cumulative"` a press nudges the input and it stays where you left it; with
`"held"` the input follows the keys currently down, like a driving game. Same
keyboard, same vehicle, and they feel nothing alike.

## The three switches that are not demos

They live in the same `CONFIGURATION` block and are named after the constant
that turns each one on.

| set this | and you get |
|---|---|
| `VEHICLE`, `SHOW_*` | `"hmmwv"`, `"sedan"`, `"uazbus"`, `"gator"` or `"audi"`, and the built-in Irrlicht overlay |
| `TRANSMISSION = "manual"` | a gearbox to row through. Only `VEHICLE = "audi"` has one; the others say so rather than silently ignoring it. |
| `PLANT = "crane"` | a gantry crane, driven by the same three numbers. It has no `ChVehicle`, so `ChDataDriver` and `ChInteractiveDriver` are both out; `ScriptedInputs` and `WindowInputs` stand in, and the loop cannot tell. |

The crane is the one to try, on `INPUT_SOURCE = "keyboard"`. Nothing damps the
payload's swing except you: a small input window of our own opens, the arrow
keys there drive the bridge and the trolley, and the console scores you with
the swing angle and the miss distance. Keep THAT window focused, not the 3D
view.

## The files here

| | |
|---|---|
| `tutorial_HIL_driver.py` | the simulation loop and the `CONFIGURATION` block. One loop for both plants and both input sources. |
| `hil_plants.py` | `PLANT`: the vehicle and the crane, behind one six-method interface |
| `hil_scene.py` | the flat terrain both plants sit on |
| `hil_gearbox.py` | `TRANSMISSION`: the gearbox, and the keys that shift it |
