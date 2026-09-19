# Experimental: mouse and keyboard in PyChrono, natively

Demo 3 reaches the Irrlicht window's mouse through the operating system:
`NSEvent.mouseLocation` and `CGEventSourceKeyState` on macOS, `XQueryPointer`
and `XQueryKeymap` on X11, `GetCursorPos` and `GetAsyncKeyState` on Windows.
That works, and it is 724 lines across four files
(`chronohil/input/window/macos.py`, `linux.py`, `windows.py`, and the
pixel-to-ray arithmetic they share in `camera.py`). None of it is Chrono. It is
a workaround for PyChrono not exposing its own window's input at all.

It does not have to be that way, and the fix is one line.

## The gap

Genesis ships this as a first-class feature. A user writes three lines:

```python
scene.viewer.add_plugin(
    gs.vis.viewer_plugins.MouseInteractionPlugin(use_force=True, use_visual_geom=True)
)
```

and gets grab-and-drag with a choice of spring forces or direct positioning,
raycasting against visual or collision geometry, and a keybinding system --
435 lines of it, maintained in the library.

Chrono has none of it, and PyChrono cannot even be *given* it from Python:
`irr::IEventReceiver` is `%include`d in the SWIG interface but has no
`%feature("director")`, so it wraps as an abstract class with no constructor.
`getCursorControl()` and `getSceneCollisionManager()` both come back as
unwrapped `SwigPyObject`s. There is no way in.

## The change

[`swig-irrlicht-directors.patch`](swig-irrlicht-directors.patch), against
`src/chrono_swig/interface/irrlicht/ChModuleIrrlicht.i`:

```swig
%feature("director") irr::IEventReceiver;
```

The module is already declared `%module(directors="1", threads="1") irrlicht`,
so nothing else has to change -- `IEventReceiver` simply never opted in.

## It works

Built against `projectchrono/chrono` main at `125858e00` with
`CH_ENABLE_MODULE_IRRLICHT=ON` and `CH_ENABLE_MODULE_PYTHON=ON`:

- `irr.IEventReceiver` becomes constructible and subclassable from Python
- `vis.AddUserEventReceiver(python_object)` accepts it
- `ChIrrEventReceiver::OnEvent` gives user receivers the first chance at every
  event, so both keyboard and mouse arrive

Verified by injecting known events and counting them: 10 synthetic key presses
(20 down/up events) and 30 mouse moves arrived as exactly `key=20 mouse=30`,
and a synthetic click arrived with its pixel coordinates.

## What it replaces

[`native_pick.py`](native_pick.py) is the receiver in **18 lines**, portable,
with no `Quartz`, no `AppKit`, no `Xlib`, no `user32` and no window-geometry
arithmetic:

```python
class MouseReceiver(irr.IEventReceiver):
    def OnEvent(self, ev):
        if ev.EventType == irr.EET_MOUSE_INPUT_EVENT:
            self.x, self.y = ev.MouseInput.X, ev.MouseInput.Y
            ...
        return False
```

`chronohil/input/window/native.py` is the production version of the same
thing: the whole surface the three OS backends offer -- keys, edge-triggered
commands, camera nudges, cursor-in-window -- in **81 lines**, on every platform
Irrlicht supports. `open_window_input()` already prefers it and falls back to
the OS files only when `IEventReceiver` cannot be subclassed, so the day the
patch lands upstream nothing in the demos changes.

|  | lines | portable |
|---|---|---|
| the OS path: `macos.py` + `linux.py` + `windows.py` + `camera.py` | 724 | no |
| with directors enabled: `native.py` | 81 | yes |
| the bare receiver: `native_pick.py`'s `MouseReceiver` | 18 | yes |

Every count above is non-blank, non-comment, non-docstring lines, on both
sides. Counting a hand-count of one file against a different rule for the other
is how numbers like these drift apart. `make_slides.py` carries the same two
figures for the deck, in its `N` table.

## Running it

```bash
cmake -S <chrono> -B build -G Ninja -DCH_ENABLE_MODULE_IRRLICHT=ON -DCH_ENABLE_MODULE_PYTHON=ON
ninja -C build
PYTHONPATH=build/bin python experimental/native_pick.py
```

Nobody needs to do this to follow the tutorial -- demo 3 works on stock
PyChrono. This is here to show what the gap costs and how small the fix is.
