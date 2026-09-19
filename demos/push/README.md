# Demo 4: how hard can you shove it

A freehand drag cannot answer "how hard can I shove it", because no two drags
are the same: the force depends on how fast your hand moved and how long you
held the button. So the person keeps the parts where judgement helps -- where
on the body, and in which direction -- and the magnitude is scripted:

```
impulse J = F * dt      a constant force, held for a fixed window
```

Both are printed and logged, so "a 1850 N push for 50 ms, 92.50 N.s, on the
base COM, pointing +X" is reproducible by someone else.

```bash
python demos/push/main.py                                     # click, aim, SPACE
python demos/push/main.py --headless --mag 300 --dir 1,0,0    # one scripted push
python demos/push/main.py --headless --sweep 1700:1950:50 --dir 1,0,0 --fresh
python demos/push/main.py --help
```

The sweep is how the numbers in the talk were produced. It takes a few minutes
and ends with the threshold.

## What to press

**Click ON the robot** to set where the push lands. Then **SPACE** fires,
**X** resets to the standing pose, **C** points back at the base COM, and
**T** logs a state line. **Left/right** change azimuth, **up/down** elevation,
**[ ]** magnitude. **A/D** orbit the camera, **W/S** zoom, **R/F** raise and
lower it. There is no quit key here: close a window to stop.

The pygame panel beside the 3D view has the same controls as sliders, plus the
six axis buttons and the last four results. `--no-panel` runs without it, and
is the only way to get a correct `--shot` PNG on every platform.

## What to look for

- **The verdict.** "Recovered" is a sustained condition, not an instant one:
  the base has to be back near its standing height, still upright, and no
  longer moving, and hold all three for 0.40 s. A robot that sails through the
  right height on its way to the floor does not count.
- **The threshold is a band, not a number.** Right at the edge the same push
  from a bit-identical start goes both ways. `--trials` reports a pass rate
  and `--fresh` makes the trials actually independent; `evaluate()` in
  `rig.py` has the measurement that says why `--trials` alone is not enough.
- **The controller is the whole story.** Same rig, same robot: the stance PD
  recovers from 600 N and goes over at 625. The trained locomotion policy
  recovers from 1850 N and goes over at 1900.

## Where the stance PD numbers come from

Both pairs were measured with the same rig, the same 50 ms window, and the same
solver, so the comparison is like for like:

| controller | forward | sideways |
|---|---|---|
| PD holding a stance | 600 N recovers, 625 N does not | 275 N recovers, 300 N does not |
| trained locomotion policy | 1850 N recovers, 1900 N does not | 1100 N recovers, 1200 N does not |

Reproduce the policy half with the sweep at the top of this file. The PD half
needs `chronohil.scenes.GO2_CONTROL = "pd"` set from Python before the scene is
built; there is no command-line switch for it yet.

The forward PD figure used to be 325 N. It changed when collision was enabled on
every Go2 link rather than only the feet and the torso: with every link solid, a
robot tipping forward catches itself on its own thighs. Sideways barely moved,
which fits, because sideways it falls past its legs rather than onto them.

The solver used to be raised to 600 iterations only when the policy was driving,
so the two halves of this comparison ran on different solvers. They no longer
do. Measured either way, iteration count makes no difference to the PD: same
verdicts and same drifts at 200 and at 600.

## The files here

| | |
|---|---|
| `rig.py` | the push, the recovery test, the reset, and the headless sweep. No UI at all. |
| `panel.py` | the pygame configurator window, the in-window input, and the 3D markers |
| `main.py` | argument parsing, the interactive loop, and the headless entry point |
