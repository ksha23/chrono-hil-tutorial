# Experimental: mouse and keyboard in PyChrono, natively

`hil_manipulate.py` reaches the Irrlicht window's mouse through macOS itself --
`NSEvent.mouseLocation`, `CGEventSourceKeyState`, `CGWindowListCopyWindowInfo`.
That works, but it is 135 lines, it is macOS-only, and it is not Chrono. It is a
workaround for PyChrono not exposing the window's input at all.

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

[`native_pick.py`](native_pick.py) is the same capability in **18 lines**,
portable, with no `Quartz`, no `AppKit`, and no window-geometry arithmetic:

```python
class MouseReceiver(irr.IEventReceiver):
    def OnEvent(self, ev):
        if ev.EventType == irr.EET_MOUSE_INPUT_EVENT:
            self.x, self.y = ev.MouseInput.X, ev.MouseInput.Y
            ...
        return False
```

|  | lines | portable |
|---|---|---|
| macOS glue in `hil_manipulate.py` | 135 | no |
| with directors enabled | 18 | yes |

## Running it

```bash
cmake -S <chrono> -B build -G Ninja -DCH_ENABLE_MODULE_IRRLICHT=ON -DCH_ENABLE_MODULE_PYTHON=ON
ninja -C build
PYTHONPATH=build/bin python native_pick.py
```

Nobody needs to do this to follow the tutorial -- `hil_manipulate.py` works on
stock PyChrono. This is here to show what the gap costs and how small the fix is.
