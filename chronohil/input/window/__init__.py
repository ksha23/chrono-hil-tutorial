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
    macos    the same surface, reconstructed from Quartz and AppKit because
             the build above is not available. macOS only, and about five
             times the code.
    None     no in-window picking. The demo falls back to its own window and
             keyboard, which works everywhere.

Ordering matters: once the director line is upstream, `native` wins on every
platform and the macOS file stops being reachable. Nothing else has to change.
"""

import platform


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

    if platform.system() == "Darwin":
        try:
            from .macos import MacOSWindowInput
            return MacOSWindowInput(vis, title, content_w, content_h,
                                    edges=edges)
        except Exception as exc:
            if not quiet:
                print(f"[input] macOS window input unavailable ({exc})")

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
    """
    if platform.system() != "Darwin":
        return None
    try:
        from .macos import PanelPointer
        return PanelPointer(title, content_w, content_h)
    except Exception as exc:
        if not quiet:
            print(f"[panel] OS cursor unavailable ({exc}); using pygame events")
        return None
