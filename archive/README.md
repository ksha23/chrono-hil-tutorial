# Archive

A working demo that is not part of the talk. It is kept because it runs and
because it answers a question people ask, not because the deck needs it.

| | |
|---|---|
| `hil_place.py` | Top-down scene layout: drag objects, read their x/y/yaw live, press `T` to dump a pasteable `LAYOUT` block. Kinematic, so nothing reacts -- useful, and not human-in-the-loop by this tutorial's definition. |

```bash
python archive/hil_place.py
```

It runs from any working directory: `hil_place.py` puts the repository root on
`sys.path` itself.

**This file still uses the old PART numbering** that the rest of the
repository has dropped in favour of Demo 1 to Demo 4. It was left as it is
rather than edited. The map:

| in this file | elsewhere |
|---|---|
| PART 1 | Demo 1, real-time enforcement |
| PART 2 | Demo 2, the keyboard |
| PART 5 | the `SHOW_*` overlay switches |
| PART 6 | `TRANSMISSION` and the shift keys |
| PART 8 | `PLANT = "crane"` |
| PART 9 | Demo 3, `demos/manipulate/` |
| PART 10 | Demo 4, `demos/push/` |

`hil_place.py` also refers to `hil_manipulate.py`, which was split into
`demos/manipulate/` and `chronohil/`.
