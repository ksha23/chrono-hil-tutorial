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
"""Reading the 3D window by asking Win32. Optional, and the last resort.

WHAT WAS TESTED, AND WHAT WAS NOT. This file was written blind, with no Windows
machine to hand, and has since been run on one: Windows 10.0.26200, Python
3.10.8 (MSC v.1933, 64-bit), a 1920x1080 display at 100% scaling. It was
exercised against a real top-level window -- a tkinter one, because the three
questions here are about a WINDOW and any window with a known title answers
them, while PyChrono on Windows is a conda install and a 500 MB download that
would prove nothing further about user32. What that run covered:

    the window found by exact title and by substring, ours preferred over an
    identically titled window in another process; the client rect matching the
    window's real position and client size, across a move, a minimise and a
    restore, and None once the window was gone; the cursor driven to known
    screen points with SetCursorPos and read back as the right client pixel at
    the centre and all four corners, and as None one pixel outside each edge;
    a window half the size of the demo's pixel grid scaling onto it exactly;
    a synthetic button press read by mouse_down(), with the buttons the usual
    way round and with SwapMouseButton on; every key in K driving
    poll(), camera_nudge(), plane_spin() and the EDGE commands, each edge
    firing once and not again while the key stayed down.

STILL UNTESTED, and worth saying plainly:

    An actual Irrlicht window. So: that Chrono's SetWindowTitle reaches the
    Win32 caption FindWindowW matches on, and that Irrlicht's client area is
    the 1280x800 the demo asked for. The second is harmless either way, since
    _Window.pixel() scales whatever the client turns out to be onto the demo's
    grid, and that scaling IS tested.

    A display with DPI scaling. The machine reachable for this runs at 100%,
    where an unaware process and an aware one see the same numbers, so nothing
    below distinguishes them. See _Window.rect() for why the arithmetic should
    survive one anyway, and treat that as reasoning, not as a measurement.

    A physical left-handed mouse. mouse_down()'s swap handling was measured by
    flipping SwapMouseButton and injecting presses, not by plugging in a mouse
    and setting it up in Control Panel.

    demos/push/panel.py. There is no PanelPointer here on purpose, for the
    reasons at the bottom of this note, and whether the pygame panel does keep
    receiving its own clicks alongside an Irrlicht window is a claim about
    pygame and Irrlicht, not about anything in this file.

    GetCursorPos in a session with no input desktop. A Windows OpenSSH shell
    lands in session 0, where GetCursorPos simply fails and every window_rect()
    is None; the tests here had to be run through a scheduled task in the
    console session to mean anything. Nothing in a session like that has a 3D
    window to point at either, so this file does not try to detect it.

That this file is built to fail quietly still matters: open_input() returns
None for anything it does not like, chronohil.input.window falls through to the
portable pygame input window, and the demo keeps working with keyboard
selection. The worst outcome this file is allowed to have is no mouse on the
3D view.

NOTHING IN demos/ IMPORTS THIS DIRECTLY. It is selected, if at all, by
chronohil.input.window, and the demos see the same interface either way. The
same three questions as everywhere else, answered by user32:

    GetCursorPos                    where the cursor is, in screen pixels
    GetAsyncKeyState + SM_SWAPBUTTON   whether the DRAG button is down; the
                                    two are needed together, see mouse_down()
    GetAsyncKeyState(vk)            whether a key is down, focus or not
    FindWindowW / EnumWindows       which HWND is ours, by the title Chrono set
    GetClientRect + ClientToScreen  where its drawable area sits, and how big

Pure ctypes on purpose: user32 is present on every Windows install, so this
adds no dependency, which is the rule for every backend in this package.

WHAT IS NOT HERE: a PanelPointer. The macOS one exists because two windows in
one process fight over the Cocoa event queue and the pygame panel loses its
clicks; Win32 delivers messages per thread and Irrlicht's own PeekMessage loop
dispatches them to SDL's window procedure, so the panel should keep getting
its events the ordinary way. Writing an untested polling path instead would
risk turning a panel that works into a panel with dead sliders, to fix the
much smaller problem that demos/push/main.py cannot tell whether the cursor is
over the panel (so a slider drag on top of the 3D view will also fire a pick).
If someone runs this on Windows and the panel misbehaves, linux.py's
PanelPointer is the pattern to copy.
"""

import ctypes
import os
import time

from .camera import CameraRay

WHAT = "Win32"

# Win32 types, spelled in plain ctypes. ctypes.wintypes cannot even be
# IMPORTED off Windows and ctypes.WINFUNCTYPE does not exist there either, so
# both stay inside functions: this module must remain importable on macOS and
# Linux or the package's own smoke tests cannot look at it.
_HWND = ctypes.c_void_p             # a real pointer: c_int would truncate it
_DWORD = ctypes.c_ulong
_LONG = ctypes.c_long

_VK_LBUTTON = 0x01
_VK_RBUTTON = 0x02
_SM_SWAPBUTTON = 23                 # GetSystemMetrics: are the buttons swapped?
_DOWN = 0x8000                      # the high bit of GetAsyncKeyState's SHORT


class _POINT(ctypes.Structure):
    _fields_ = [("x", _LONG), ("y", _LONG)]


class _RECT(ctypes.Structure):
    _fields_ = [("left", _LONG), ("top", _LONG),
                ("right", _LONG), ("bottom", _LONG)]


_USER32 = None
_ENUMPROC = None                    # the EnumWindows callback type, see _user32


def unsupported():
    """Why this cannot work here, or None when it is worth trying."""
    if not hasattr(ctypes, "windll"):
        return "not a Windows build of Python, so there is no user32 to ask"
    return None


def _user32():
    """user32 with its prototypes declared, loaded at most once."""
    global _USER32, _ENUMPROC
    if _USER32 is not None:
        return _USER32
    u = ctypes.windll.user32
    # Declared, not left to ctypes' int default: HWND is 64 bits in a 64-bit
    # process and an undeclared return truncates it to garbage, which fails as
    # "the window is never found" rather than as an error.
    u.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
    u.GetCursorPos.restype = ctypes.c_int
    u.GetAsyncKeyState.argtypes = [ctypes.c_int]
    u.GetAsyncKeyState.restype = ctypes.c_short
    u.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    u.FindWindowW.restype = _HWND
    u.GetWindowTextW.argtypes = [_HWND, ctypes.c_wchar_p, ctypes.c_int]
    u.GetWindowTextW.restype = ctypes.c_int
    u.GetWindowTextLengthW.argtypes = [_HWND]
    u.GetWindowTextLengthW.restype = ctypes.c_int
    u.IsWindowVisible.argtypes = [_HWND]
    u.IsWindowVisible.restype = ctypes.c_int
    u.IsWindow.argtypes = [_HWND]
    u.IsWindow.restype = ctypes.c_int
    u.GetWindowThreadProcessId.argtypes = [_HWND, ctypes.POINTER(_DWORD)]
    u.GetWindowThreadProcessId.restype = _DWORD
    u.GetClientRect.argtypes = [_HWND, ctypes.POINTER(_RECT)]
    u.GetClientRect.restype = ctypes.c_int
    u.ClientToScreen.argtypes = [_HWND, ctypes.POINTER(_POINT)]
    u.ClientToScreen.restype = ctypes.c_int
    u.GetSystemMetrics.argtypes = [ctypes.c_int]
    u.GetSystemMetrics.restype = ctypes.c_int
    # The EnumWindows callback type, built here rather than at import because
    # WINFUNCTYPE is the stdcall factory and CPython only defines it on
    # Windows. _user32() is only ever reached past unsupported()'s guard, so
    # this line runs nowhere else. Declaring it also lets EnumWindows itself be
    # prototyped like every other call above, instead of relying on ctypes'
    # default marshalling for a function pointer and a pointer-sized LPARAM.
    _ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, _HWND, ctypes.c_ssize_t)
    u.EnumWindows.argtypes = [_ENUMPROC, ctypes.c_ssize_t]
    u.EnumWindows.restype = ctypes.c_int
    _USER32 = u
    return u


def _find_window(title):
    """The HWND whose title contains `title`, ours preferred, or None.

    FindWindowW is tried first and wants the title EXACTLY; that is the cheap
    path and it is the one that will normally hit, since the demos hand over
    the very string they passed to vis.SetWindowTitle. EnumWindows covers the
    case where something decorated it, and matches the way the macOS and X11
    backends do: substring, case-insensitive.

    Windows of THIS process win, which is a guarantee neither sibling can
    make: a second copy of the demo, or an editor showing this file with the
    title in its tab, cannot steal the match. Measured: with a second process
    holding a window of the very same title, this still returned ours.

    A window is findable the instant it exists. The macOS sibling is not --
    there a freshly created window is missing from CGWindowListCopyWindowInfo
    until it has been pumped for a few frames, which cost an hour of looking
    for a permissions problem that was not there. On Windows the same probe hit
    on its first try, 0.000 s after tkinter returned the window, because the
    window IS the kernel object EnumWindows walks. Callers still retry, since
    that costs nothing and _Window.id() throttles the misses anyway.
    """
    u = _user32()
    exact = u.FindWindowW(None, title)
    mine = os.getpid()
    if exact:
        pid = _DWORD()
        u.GetWindowThreadProcessId(_HWND(exact), ctypes.byref(pid))
        if pid.value == mine:
            return exact
    want = title.lower()
    found = [None, None]            # [ours, anyone's]

    def visit(hwnd, _lparam):
        if not u.IsWindowVisible(hwnd):
            return 1
        n = u.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return 1
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        if want not in buf.value.lower():
            return 1
        pid = _DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == mine:
            found[0] = hwnd
            return 0                # stop: nothing will beat our own window
        if found[1] is None:
            found[1] = hwnd
        return 1

    cb = _ENUMPROC(visit)           # held in a local until EnumWindows returns
    u.EnumWindows(cb, 0)
    return found[0] or found[1] or (exact if exact else None)


class _Window:
    """Our window, and where the cursor is inside its client area."""

    # The client rect only changes when someone drags an edge, and both calls
    # that produce it are kernel transitions; the cursor and the keys are not
    # cached at all because GetCursorPos and GetAsyncKeyState are cheap local
    # reads with no round trip to anything. (linux.py caches those two because
    # there each of them is a request and a reply over a socket.)
    RECT_S = 0.5
    FIND_S = 1.0

    def __init__(self, title, content_w, content_h):
        self.title = title
        self.cw, self.ch = content_w, content_h
        self.hwnd = None
        self._found_at = -1e9
        self._rect = None
        self._rect_at = -1e9

    def id(self):
        if self.hwnd is not None:
            if _user32().IsWindow(_HWND(self.hwnd)):
                return self.hwnd
            self.hwnd = None        # closed and, maybe, reopened
        now = time.monotonic()
        if now - self._found_at < self.FIND_S:
            return None
        self._found_at = now
        self.hwnd = _find_window(self.title)
        return self.hwnd

    def rect(self):
        """(x, y, w, h) of the CLIENT area on screen, or None.

        The client area, not the window: GetWindowRect would include the title
        bar and the borders, and then every cursor position would be off by
        the height of the title bar. The macOS backend has to subtract that
        chrome by hand because CGWindowBounds is the whole window; here Win32
        draws the distinction for us.

        DPI, and this is reasoning rather than a measurement: the test machine
        runs at 100%, where a scaled and an unscaled reading are the same
        number. All three calls this class makes -- GetCursorPos, ClientToScreen
        and GetClientRect -- answer in the DPI space of the CALLING PROCESS, and
        there is only one process here, so a display Windows scales moves all
        three together and their differences survive. (The probe reported this
        python.exe as PROCESS_DPI_UNAWARE, so on a 150% display Windows would
        virtualise every one of those three by the same 1.5.) What is left for
        pixel() is that the client may not be content_w by content_h, which is
        why it scales rather than subtracts; that part IS measured, on a window
        deliberately made half the size of the demo's grid.
        """
        now = time.monotonic()
        if self._rect is not None and now - self._rect_at < self.RECT_S:
            return self._rect
        hwnd = self.id()
        if hwnd is None:
            return None
        u = _user32()
        box, org = _RECT(), _POINT(0, 0)
        if not u.GetClientRect(_HWND(hwnd), ctypes.byref(box)):
            self.hwnd = None
            return None
        if not u.ClientToScreen(_HWND(hwnd), ctypes.byref(org)):
            self.hwnd = None
            return None
        w, h = box.right - box.left, box.bottom - box.top
        if w <= 0 or h <= 0:        # minimised: nothing to point at
            return None
        self._rect = (org.x, org.y, w, h)
        self._rect_at = now
        return self._rect

    def pixel(self, inside_only=True):
        """Cursor in content pixels, or None."""
        r = self.rect()
        if r is None:
            return None
        u = _user32()
        at = _POINT()
        if not u.GetCursorPos(ctypes.byref(at)):
            return None             # a locked workstation answers this way
        x, y, w, h = r
        px = (at.x - x) * self.cw / w
        py = (at.y - y) * self.ch / h
        if inside_only and not (0 <= px < self.cw and 0 <= py < self.ch):
            return None
        return px, py


def _pressed(vk):
    """Is this virtual key down NOW?

    Bit 15, not bit 0: bit 0 says "was pressed since the last call", which two
    callers in the same frame would steal from each other. GetAsyncKeyState
    reads the physical keyboard and does not care which window has focus,
    which is the property this whole package is built on.

    The restype is a SIGNED short, so a held key comes back as -32768 or
    -32767, never as 0x8000. The mask still works: Python's & is defined on
    two's complement of unbounded width, so -32768 & 0x8000 is 32768. Spelled
    out because the alternative reading -- that the sign makes this always
    false -- is the obvious one, and it is wrong.
    """
    return bool(_user32().GetAsyncKeyState(vk) & _DOWN)


class Win32WindowInput(CameraRay):
    """Mouse and keyboard read from Win32, so they work ON the 3D window.

    The surface is the macOS backend's, method for method, because the demos
    are written against one console interface and must not be able to tell
    which backend answered. Every method below was run against a real window;
    what that run could not reach is listed in the module docstring.
    """

    # Windows virtual key codes. Irrlicht's own KEY_KEY_A / KEY_LEFT constants
    # are these same numbers -- Irrlicht took its key enum from Win32 -- so
    # this table and native.py's are the same table. Every entry was pressed
    # with keybd_event on the test machine and came back through _key().
    K = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
         "space": 0x20, "esc": 0x1B,
         "lbracket": 0xDB, "rbracket": 0xDD,        # VK_OEM_4 / VK_OEM_6
         # camera, deliberately on keys so the mouse stays free for grabbing
         "a": 0x41, "d": 0x44, "w": 0x57, "s": 0x53, "r": 0x52, "f": 0x46,
         # rotate the drag plane -> this is the depth control
         "q": 0x51, "e": 0x45,
         "z": 0x5A, "x": 0x58, "c": 0x43, "t": 0x54}
    EDGE = {"z": "f", "x": "n", "c": "r", "t": "m", "rbracket": "u",
            "lbracket": "d", "esc": "q"}

    def __init__(self, vis, title, content_w, content_h, edges=None):
        _user32()                   # fail here, not on the first frame
        self.vis, self.title = vis, title
        self.cw, self.ch = content_w, content_h
        self.w = _Window(title, content_w, content_h)
        self.commands = []
        if edges is not None:
            self.EDGE = dict(edges)
        self.prev = {k: False for k in self.EDGE}
        self.prev_mouse = False
        self.addr = ("direct", 0)
        self.last = (0.0, 0.0, 0.0)
        print("[input] reading mouse and keys from Win32 - "
              "click straight on the 3D window")

    # -- OS state ------------------------------------------------------------
    def _key(self, name):
        # .get, never [name]: an `edges` naming a key this table does not have
        # would otherwise raise KeyError out of poll() and kill the demo on its
        # first frame, which is exactly how the macOS backend once broke.
        vk = self.K.get(name)
        return False if vk is None else _pressed(vk)

    def mouse_down(self):
        """Is the button a person DRAGS with down?

        Not simply VK_LBUTTON, and this was the one real bug the first run on
        Windows turned up. GetAsyncKeyState reports the PHYSICAL buttons and
        ignores the left-handed swap; the message layer and GetKeyState do
        follow it. Measured on 10.0.26200 with SwapMouseButton(TRUE) set, one
        MOUSEEVENTF_LEFTDOWN injected, then both states read:

            GetAsyncKeyState:  LBUTTON True   RBUTTON False
            GetKeyState:       LBUTTON False  RBUTTON True

        So on a swapped machine VK_LBUTTON is the button that opens context
        menus and the one being dragged with is VK_RBUTTON. Reading VK_LBUTTON
        unconditionally, as this file did when it was written blind, gives a
        left-handed user a demo whose drag fires off their menu button.

        SM_SWAPBUTTON is re-read every call rather than cached at startup: it
        is a read of a value win32k keeps in shared memory, no dearer than the
        key state beside it, and it means someone who changes the setting while
        the demo is running is not left without a mouse until they restart.
        """
        swapped = _user32().GetSystemMetrics(_SM_SWAPBUTTON)
        return _pressed(_VK_RBUTTON if swapped else _VK_LBUTTON)

    def window_rect(self):
        return self.w.rect()

    def cursor_pixel(self):
        """Cursor in window content pixels, or None when it is outside."""
        return self.w.pixel()

    # -- the ray Irrlicht would not give us ----------------------------------
    # ray_through() comes from CameraRay, shared with every other backend.

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


def open_input(vis, title, content_w, content_h, edges=None, quiet=False):
    """A Win32 backend, or None when it cannot be had. Never raises."""
    why = unsupported()
    if why is None:
        try:
            return Win32WindowInput(vis, title, content_w, content_h, edges=edges)
        except Exception as exc:
            why = f"user32 said no ({exc})"
    if not quiet:
        print(f"[input] {why}")
    return None
