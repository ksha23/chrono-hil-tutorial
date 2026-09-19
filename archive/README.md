# Archive

Working demos that are not part of the talk. They are kept because they run and
because each answers a question people ask, not because the deck needs them.

| | |
|---|---|
| `hil_place.py` | Top-down scene layout: drag objects, read their x/y/yaw live, press `T` to dump a pasteable `LAYOUT` block. Kinematic, so nothing reacts -- useful, and not human-in-the-loop by this tutorial's definition. |
| `operator_console.py` | The UDP operator console. Run it in a second terminal and it drives the simulation over a socket while telemetry comes back. Still the console every UDP path expects: `INPUT_SOURCE = "udp"` in demo 1/2's script, and `--udp` on demo 3. |

```bash
python archive/hil_place.py
python archive/operator_console.py                # simulation on this machine
python archive/operator_console.py 192.168.1.20   # simulation elsewhere
```

Both run from any working directory: `hil_place.py` puts the repository root on
`sys.path` itself, and `operator_console.py` imports nothing from the
repository at all -- three floats over a socket is the whole interface, which
is the point it exists to make.

**These two files still use the old PART numbering** that the rest of the
repository has dropped in favour of Demo 1 to Demo 4. They were left as they
are rather than edited. The map:

| in these files | elsewhere |
|---|---|
| PART 1 | Demo 1, real-time enforcement |
| PART 2 | Demo 2, the keyboard |
| PART 4 | `INPUT_SOURCE = "udp"` |
| PART 5 | the `SHOW_*` overlay switches |
| PART 6 | `TRANSMISSION` and the shift keys |
| PART 8 | `PLANT = "rover"` / `"crane"` |
| PART 9 | Demo 3, `demos/manipulate/` |
| PART 10 | Demo 4, `demos/push/` |

`hil_place.py` also refers to `hil_manipulate.py`, which was split into
`demos/manipulate/` and `chronohil/`.
