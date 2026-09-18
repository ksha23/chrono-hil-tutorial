# Archive

Working demos that are not part of the talk. They are kept because they run and
because each answers a question people ask, not because the deck needs them.

| | |
|---|---|
| `hil_place.py` | Top-down scene layout: drag objects, read their x/y/yaw live, press `T` to dump a pasteable `LAYOUT` block. Kinematic, so nothing reacts -- useful, and not human-in-the-loop by this tutorial's definition. |
| `operator_console.py` | The UDP operator console for `INPUT_SOURCE = "udp"`. Run it in a second terminal and it drives the simulation over a socket while telemetry comes back. |

Run them from here; both add the parent directory to the path themselves.
