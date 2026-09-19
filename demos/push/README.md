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
  recovers from 325 N and goes over at 330. The trained locomotion policy
  recovers from 1850 N and goes over at 1900.

## The stance PD numbers need re-measuring

The policy pair above reproduces exactly, today, from the sweep command at the
top of this file: `always recovers at 1850 N (92.50 N.s), always falls at
1900 N (95.00 N.s)`.

The stance PD pair, 325 N and 330 N, does not. Re-run under the same rig with
`chronohil.scenes.GO2_CONTROL = "pd"` and the PD recovers cleanly at 340 N, at
500 N and at 600 N, and first falls at 650 N. Two differences are known and
neither has been isolated as the cause: `scene_go2` raises the solver to 600
iterations only on the policy branch, so the PD runs at 200; and the Go2 now
has collision geometry on every link rather than on the feet and base only.

Nothing here has been changed to match the new reading -- the old pair is left
where it is, in `make_slides.py`'s `N` table, because it is a real measurement
of some configuration and the deck quotes it. It wants a deliberate re-run by
someone who knows which configuration was meant.

There is also no command-line switch for the controller: `GO2_POLICY_CKPT`
only chooses a different checkpoint, and `GO2_CONTROL` is a module global on
`chronohil.scenes`. That is why the PD half of this comparison is harder to
reproduce than the policy half.

Every push appends a row to `push_log.csv` at the repository root
(`--log` moves it). `--trace` writes the recovery trace of the first push.

## The files here

| | |
|---|---|
| `rig.py` | the push, the recovery test, the reset, and the headless sweep. No UI at all. |
| `panel.py` | the pygame configurator window, the in-window input, and the 3D markers |
| `main.py` | argument parsing, the interactive loop, and the headless entry point |
