# =============================================================================
# PROJECT CHRONO - http://projectchrono.org
#
# Copyright (c) 2026 projectchrono.org
# All rights reserved.
#
# Use of this source code is governed by a BSD-style license that can be found
# in the LICENSE file at the top level of the distribution and at
# http://projectchrono.org/license-chrono.txt.
# =============================================================================
"""Reading the 3D window by asking macOS. Optional, and the last resort.

NOTHING IN demos/ IMPORTS THIS DIRECTLY. It is selected, if it is selected at
all, by chronohil.input.window, and the demos see the same interface either way.

It exists because PyChrono cannot hand Python the events of its own window: see
chronohil/input/window/native.py for the one-line change that removes the need
for any of this.
"""

import math

from ...chrono_env import chrono

class MacOSWindowInput:
    """Mouse and keyboard read from the OS, so they work ON the 3D window.

    PyChrono cannot read that window itself: SWIG directors are off so
    irr::IEventReceiver cannot be subclassed, and getCursorControl() and
    getSceneCollisionManager() both come back as unwrapped SwigPyObjects.  But
    the window belongs to this process and macOS will tell us about it:

        AppKit.NSEvent.mouseLocation()        where the cursor is, focus or not
        Quartz.CGEventSourceButtonState()     whether the left button is down
        Quartz.CGEventSourceKeyState()        whether a key is down
        Quartz.CGWindowListCopyWindowInfo()   where our window sits on screen

    None of those need accessibility permission.  What Irrlicht will not hand
    over is the ray for a screen pixel, but ICameraSceneNode IS wrapped, so
    getFOV() and getAspectRatio() are enough to build it exactly.
    """

    # macOS virtual key codes
    K = {"left": 123, "right": 124, "down": 125, "up": 126,
         "z": 6, "x": 7, "c": 8, "t": 17, "lbracket": 33, "rbracket": 30,
         # camera, deliberately on keys so the mouse stays free for grabbing
         "a": 0, "d": 2, "w": 13, "s": 1, "r": 15, "f": 3,
         # rotate the drag plane -> this is the depth control
         "q": 12, "e": 14,
         "esc": 53}
    EDGE = {"z": "f", "x": "n", "c": "r", "t": "m", "rbracket": "u", "lbracket": "d",
            "esc": "q"}

    def __init__(self, vis, title, content_w, content_h, edges=None):
        import Quartz, AppKit
        self.Q, self.AK = Quartz, AppKit
        self.vis, self.title = vis, title
        self.cw, self.ch = content_w, content_h
        self.commands = []
        if edges is not None:
            self.EDGE = dict(edges)
        self.prev = {k: False for k in self.EDGE}
        self.prev_mouse = False
        self.addr = ("direct", 0)
        self.last = (0.0, 0.0, 0.0)
        self._rect = None
        self._rect_age = 0
        print("[input] reading mouse and keys from the OS - click straight on the 3D window")

    # -- OS state ------------------------------------------------------------
    def _key(self, name):
        return bool(self.Q.CGEventSourceKeyState(
            self.Q.kCGEventSourceStateHIDSystemState, self.K[name]))

    def mouse_down(self):
        return bool(self.Q.CGEventSourceButtonState(
            self.Q.kCGEventSourceStateHIDSystemState, 0))

    def window_rect(self):
        """Screen rect of our Irrlicht window, refreshed occasionally (it can move)."""
        self._rect_age -= 1
        if self._rect is not None and self._rect_age > 0:
            return self._rect
        wl = self.Q.CGWindowListCopyWindowInfo(
            self.Q.kCGWindowListOptionOnScreenOnly | self.Q.kCGWindowListExcludeDesktopElements,
            self.Q.kCGNullWindowID)
        for w in wl:
            if self.title.lower() in (w.get("kCGWindowName") or "").lower():
                b = w["kCGWindowBounds"]
                self._rect = (b["X"], b["Y"], b["Width"], b["Height"])
                self._rect_age = 60
                return self._rect
        return self._rect

    def cursor_pixel(self):
        """Cursor in window content pixels, or None when it is outside."""
        r = self.window_rect()
        if r is None:
            return None
        wx, wy, ww, wh = r
        loc = self.AK.NSEvent.mouseLocation()
        screen_h = self.AK.NSScreen.screens()[0].frame().size.height
        top_y = screen_h - loc.y                      # Quartz counts down from the top
        chrome = wh - self.ch                          # title bar
        px = loc.x - wx
        py = top_y - wy - chrome
        if 0 <= px < self.cw and 0 <= py < self.ch:
            return px, py
        return None

    # -- the ray Irrlicht would not give us ----------------------------------
    def ray_through(self, px, py, reach=60.0):
        cam = self.vis.GetActiveCamera()
        # vis.GetCameraPosition() reports (0,0,0) for a camera added with
        # AddCamera, so ask the Irrlicht node itself. Chrono passes world
        # coordinates through 1:1 once SetCameraVertical(Z) is set.
        cp, ct = cam.getAbsolutePosition(), cam.getTarget()
        eye = chrono.ChVector3d(cp.X, cp.Y, cp.Z)
        tgt = chrono.ChVector3d(ct.X, ct.Y, ct.Z)
        fwd = tgt - eye
        n = fwd.Length()
        if n < 1e-9:
            return None
        fwd = fwd / n
        world_up = chrono.ChVector3d(0, 0, 1)
        right = fwd.Cross(world_up)
        if right.Length() < 1e-6:
            right = chrono.ChVector3d(1, 0, 0)
        right = right / right.Length()
        up = right.Cross(fwd)
        tan_v = math.tan(cam.getFOV() * 0.5)
        aspect = cam.getAspectRatio()
        ndc_x = (2.0 * px / self.cw) - 1.0
        ndc_y = 1.0 - (2.0 * py / self.ch)
        d = fwd + right * (ndc_x * tan_v * aspect) + up * (ndc_y * tan_v)
        d = d / d.Length()
        return eye, eye + d * reach

    # -- Console-compatible surface -----------------------------------------
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
        """(-1/0/+1) from Q/E: rotate the drag plane about the surface normal."""
        return (-1.0 if self._key("q") else 0.0) + (1.0 if self._key("e") else 0.0)

    def camera_nudge(self):
        """(orbit, zoom, rise) from A/D, W/S, R/F -- held, not edge-triggered."""
        return ((-1.0 if self._key("a") else 0.0) + (1.0 if self._key("d") else 0.0),
                (-1.0 if self._key("w") else 0.0) + (1.0 if self._key("s") else 0.0),
                (-1.0 if self._key("f") else 0.0) + (1.0 if self._key("r") else 0.0))

    def send(self, text):
        pass


class PanelPointer:
    """Where the cursor is inside the panel window, and whether the button is down.

    The panel could not be clicked, and the reason is not pygame's fault.  Two
    windows in this process want the same Cocoa event queue: Irrlicht's device
    calls nextEventMatchingMask itself every frame, and a press aimed at the
    pygame window gets dequeued there and dropped, so the panel never becomes
    the key window and never sees a MOUSEBUTTONDOWN.  Measured on this machine,
    two identical runs of the same probe delivered 184 mouse events and then 0 --
    decided entirely by which window happened to hold focus at the time.

    The cursor and the button are global state though, and macOS will say where
    the panel sits, so the panel can poll for its mouse exactly the way
    DirectInput already does for the 3D view.  Focus stops mattering.

    Non-macOS keeps the pygame path, where none of this applies.
    """

    def __init__(self, title, cw, ch):
        import Quartz, AppKit                      # pyobjc, same as DirectInput
        self.Q, self.AK = Quartz, AppKit
        self.title, self.cw, self.ch = title.lower(), cw, ch
        self._rect = None
        self._age = 0

    def rect(self):
        """Screen rect of the panel window.  Cached; it can be dragged around."""
        self._age -= 1
        if self._rect is not None and self._age > 0:
            return self._rect
        wl = self.Q.CGWindowListCopyWindowInfo(
            self.Q.kCGWindowListOptionOnScreenOnly
            | self.Q.kCGWindowListExcludeDesktopElements,
            self.Q.kCGNullWindowID)
        for w in wl:
            if self.title in (w.get("kCGWindowName") or "").lower():
                b = w["kCGWindowBounds"]
                self._rect = (b["X"], b["Y"], b["Width"], b["Height"])
                self._age = 240          # this runs per physics step, not per frame
                return self._rect
        return self._rect

    def pos(self, inside_only=True):
        """Cursor in panel content pixels.

        inside_only=False is for a drag already in progress: a slider you keep
        pulling past the edge of the window should peg at its end, not freeze,
        which is what every real slider does.
        """
        r = self.rect()
        if r is None:
            return None
        wx, wy, ww, wh = r
        loc = self.AK.NSEvent.mouseLocation()
        screen_h = self.AK.NSScreen.screens()[0].frame().size.height
        px = loc.x - wx
        py = (screen_h - loc.y) - wy - (wh - self.ch)   # wh - ch is the title bar
        if inside_only and not (0 <= px < self.cw and 0 <= py < self.ch):
            return None
        return int(px), int(py)

    def down(self):
        return bool(self.Q.CGEventSourceButtonState(
            self.Q.kCGEventSourceStateHIDSystemState, 0))


# -----------------------------------------------------------------------------
# The panel: pygame, because the Irrlicht window cannot be read
# -----------------------------------------------------------------------------
