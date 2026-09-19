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
"""Reading the mouse over the 3D window, by whatever means this build allows.

THE DEMOS NEVER IMPORT A BACKEND. They call `open_window_input(...)` and get
one of three answers, in this order:

    native   Irrlicht hands Python the events directly. Portable, short, and
             correct. Needs one line in Chrono's SWIG interface:
                 %feature("director") irr::IEventReceiver;
    an OS    the same surface, reconstructed by asking the operating system
             where the cursor is, whether the button is down, and where our
             window sits, because the build above is not available. One file
             per platform, and about five times the code:
                 macos.py    Quartz and AppKit     (tested)
                 linux.py    X11 through ctypes    (tested, Xorg only)
                 windows.py  Win32 through ctypes  (tested, see its header)
    None     no in-window picking. The demo falls back to its own window and
             keyboard, which works everywhere.

Ordering matters: once the director line is upstream, `native` wins on every
platform and every OS file here stops being reachable. Nothing else changes.

THIS DIRECTORY IS THE ONLY PLACE IN THE PROJECT THAT NAMES AN OPERATING
SYSTEM, and inside it, this file is the only place that asks which one is
running. That is worth keeping: a platform test that leaks into a demo is how
a tutorial ends up with three slightly different demos.
"""

import importlib
import platform

# The whole platform map. A backend is loaded only on the platform it is for,
# so an import error inside one (pyobjc missing, say) cannot affect the others.
_BACKENDS = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}


def _backend():
    """The module for this platform, or None where there is nothing to try."""
    name = _BACKENDS.get(platform.system())
    if name is None:
        return None
    try:
        return importlib.import_module(f".{name}", __package__)
    except Exception:
        return None                  # a backend that will not even import is
                                     # a backend this machine does not have


def open_window_input(vis, title, content_w, content_h, quiet=False,
                      edges=None):
    """Best available in-window input, or None.

    `edges` remaps which key raises which command, so a demo can want
    different keys without subclassing a backend it should not know about.
    """
    from . import native
    if native.available():
        return native.NativeWindowInput(vis, title, content_w, content_h,
                                        edges=edges)

    mod = _backend()
    if mod is not None:
        try:
            # open_input returns None when the platform is there but cannot
            # answer -- a Wayland session, say -- and says why itself, because
            # only it knows. It is not supposed to raise; the guard is for the
            # ways an OS can surprise us, since a demo must never die of this.
            got = mod.open_input(vis, title, content_w, content_h, edges=edges,
                                 quiet=quiet)
            if got is not None:
                return got
        except Exception as exc:
            if not quiet:
                print(f"[input] {mod.WHAT} window input unavailable ({exc})")

    if not quiet:
        print("[input] this PyChrono cannot read its own 3D window, so clicking\n"
              "        on it does nothing. Use the input window instead.\n"
              "        One line in Chrono's SWIG interface fixes this for every\n"
              "        platform: see chronohil/input/window/native.py")
    return None


def open_panel_pointer(title, content_w, content_h, quiet=True):
    """Read the cursor over a pygame window we own, when the platform allows.

    Same story as open_window_input, one layer down. A pygame window created
    after the 3D one does not reliably receive clicks: both want the same event
    queue, and whichever loop runs first can consume a press meant for the
    other. Polling the cursor sidesteps that, and needs the platform. Returns
    None where it cannot, and the panel falls back to pygame's own events.

    Not every backend offers one, and that is a judgement each of them makes
    rather than a gap: see linux.py's PanelPointer for what it is used for
    where pygame's own events DO arrive, and windows.py for why there is none.
    """
    mod = _backend()
    opener = getattr(mod, "open_panel_pointer", None) if mod else None
    if opener is None:
        return None
    try:
        return opener(title, content_w, content_h)
    except Exception as exc:
        if not quiet:
            print(f"[panel] OS cursor unavailable ({exc}); using pygame events")
        return None
