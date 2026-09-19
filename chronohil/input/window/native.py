"""Reading the 3D window the way Chrono intends, once PyChrono lets you.

THIS IS THE VERSION THAT NEEDS NO OPERATING SYSTEM AT ALL. Irrlicht already
delivers mouse and key events in window coordinates; the only reason Python
cannot receive them is that SWIG emits irr::IEventReceiver as an abstract class
with no constructor, so it can be named and not implemented:

    >>> irr.IEventReceiver()
    AttributeError: No constructor defined - class is abstract

One line in the interface file fixes it, and the module is already generated
with directors enabled:

    %feature("director") irr::IEventReceiver;

With that in, this file works on every platform Irrlicht supports and the
macOS sibling next door becomes dead weight. Without it, `available()` returns
False and nothing here is used.
"""

import math

from ...chrono_env import chrono


def available():
    """True when this PyChrono can SUBCLASS IEventReceiver.

    Instantiating the base is the wrong test and gave the wrong answer on both
    builds. Without the director it raises AttributeError, because SWIG emitted
    an abstract class with no constructor. WITH the director it still raises,
    now RuntimeError, because OnEvent is pure virtual and directors are honest
    about that. The question is whether a subclass can be made, so ask that.
    """
    try:
        import pychrono.irrlicht as irr

        class _Probe(irr.IEventReceiver):
            def OnEvent(self, ev):
                return False

        _Probe()
    except Exception:
        return False
    return True


if available():                      # pragma: no cover - depends on the build
    import pychrono.irrlicht as irr

    class _Receiver(irr.IEventReceiver):
        """Everything the demos need, straight from Irrlicht."""

        def __init__(self):
            super().__init__()
            self.x = self.y = 0
            self.down = False
            self.pressed = False
            self.keys = set()

        def OnEvent(self, ev):
            if ev.EventType == irr.EET_MOUSE_INPUT_EVENT:
                self.x, self.y = ev.MouseInput.X, ev.MouseInput.Y
                if ev.MouseInput.Event == irr.EMIE_LMOUSE_PRESSED_DOWN:
                    self.down = self.pressed = True
                elif ev.MouseInput.Event == irr.EMIE_LMOUSE_LEFT_UP:
                    self.down = False
            elif ev.EventType == irr.EET_KEY_INPUT_EVENT:
                k = int(ev.KeyInput.Key)
                self.keys.add(k) if ev.KeyInput.PressedDown else self.keys.discard(k)
            return False             # let Chrono's own GUI see it too
else:
    _Receiver = None


class NativeWindowInput:
    """The same surface the macOS backend offers, with none of the OS calls."""

    # Irrlicht key codes, so no platform table is needed
    K = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
         "a": 0x41, "c": 0x43, "d": 0x44, "e": 0x45, "f": 0x46, "q": 0x51,
         "r": 0x52, "s": 0x53, "t": 0x54, "w": 0x57, "x": 0x58, "z": 0x5A,
         "lbracket": 0xDB, "rbracket": 0xDD, "esc": 0x1B, "space": 0x20}
    EDGE = {"z": "f", "x": "n", "c": "r", "t": "m",
            "rbracket": "u", "lbracket": "d", "esc": "q"}

    def __init__(self, vis, title, content_w, content_h, edges=None):
        if _Receiver is None:
            raise RuntimeError("this PyChrono cannot subclass IEventReceiver")
        self.vis, self.cw, self.ch = vis, content_w, content_h
        self.rx = _Receiver()
        vis.AddUserEventReceiver(self.rx)
        self.commands = []
        if edges is not None:
            self.EDGE = dict(edges)
        self.prev = {k: False for k in self.EDGE}
        self.prev_mouse = False
        self.last = (0.0, 0.0, 0.0)
        self._rendered = False
        print("[input] reading the 3D window through Irrlicht (no OS calls)")

    # -- the same methods the macOS backend exposes --------------------------
    def _key(self, name):
        return self.K[name] in self.rx.keys

    def frame_rendered(self):
        """The loop calls this after its first BeginScene/Render/EndScene."""
        self._rendered = True

    def mouse_down(self):
        return self.rx.down

    def cursor_pixel(self):
        """Already window-relative, which is the whole point."""
        if 0 <= self.rx.x < self.cw and 0 <= self.rx.y < self.ch:
            return self.rx.x, self.rx.y
        return None

    def ray_through(self, px, py, reach=60.0):
        """The ray Irrlicht already knows how to build.

        On stock PyChrono this is twenty lines of arithmetic: take the camera's
        position and target, build a basis, apply the FOV and aspect ratio, turn
        the pixel into normalised device coordinates. All of it is a
        reimplementation of something Irrlicht does internally, and all of it is
        a chance to get a sign or an aspect ratio subtly wrong.

        With ISceneCollisionManager exposed it is one call. The manager is the
        scene's own, so it uses the same projection the scene was rendered with
        by construction, which is the part hand-rolled maths cannot promise.
        """
        # The camera's view matrix is not set up until the scene has been
        # rendered once, and before that the manager returns a ray built from a
        # stale transform: same answer wherever the camera is. The demo loop
        # renders before anything can be clicked, but a caller that asks earlier
        # deserves an answer rather than a wrong one.
        if not self._rendered:
            return None
        cm = self.vis.GetDevice().getSceneManager().getSceneCollisionManager()
        line = cm.getRayFromScreenCoordinates(irr.vector2di(int(px), int(py)),
                                              self.vis.GetActiveCamera())
        a, b = line.start, line.end
        eye = chrono.ChVector3d(a.X, a.Y, a.Z)
        far = chrono.ChVector3d(b.X, b.Y, b.Z)
        # Irrlicht ends the ray at the camera's far plane, which is thousands of
        # metres away. Shorten it: a ray that long picks up scenery behind the
        # thing being aimed at.
        d = far - eye
        n = d.Length()
        if n < 1e-9:
            return None
        return eye, eye + d * (reach / n)

    def poll(self):
        for name, cmd in self.EDGE.items():
            now = self._key(name)
            if now and not self.prev[name]:
                self.commands.append(cmd)
            self.prev[name] = now
        steer = (-1.0 if self._key("left") else 0.0) + (1.0 if self._key("right") else 0.0)
        self.last = (steer, 1.0 if self._key("up") else 0.0,
                     1.0 if self._key("down") else 0.0)
        return self.last

    def take_commands(self):
        c, self.commands = self.commands, []
        return c

    def plane_spin(self):
        return (-1.0 if self._key("q") else 0.0) + (1.0 if self._key("e") else 0.0)

    def camera_nudge(self):
        return ((-1.0 if self._key("a") else 0.0) + (1.0 if self._key("d") else 0.0),
                (-1.0 if self._key("w") else 0.0) + (1.0 if self._key("s") else 0.0),
                (-1.0 if self._key("f") else 0.0) + (1.0 if self._key("r") else 0.0))
