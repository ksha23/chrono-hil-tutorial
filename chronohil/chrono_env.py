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
"""`import pychrono`, and the two failures everyone hits, explained.

A loader path pointing at an older libChrono wins over the packaged one, and
PyChrono then fails with a missing symbol rather than anything that names the
cause. The variable differs by platform; the mistake does not.

The second one is require_window() below: a 3D window that could not open.
"""

import os
import sys

_LOADER_VARS = ("DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH", "PATH")

try:
    import pychrono as chrono
except ImportError as exc:
    if "symbol not found" in str(exc) or "undefined symbol" in str(exc):
        set_vars = [v for v in _LOADER_VARS[:2] if os.environ.get(v)]
        if set_vars:
            v = set_vars[0]
            sys.exit(
                f"PyChrono failed to load because {v} points somewhere with an\n"
                "older libChrono, so its symbols win over the packaged ones:\n"
                f"  {v}={os.environ[v]}\n\n"
                f"  unset {v} && python " + " ".join(sys.argv) + "\n\n"
                f"(original error: {exc})")
    raise


def require_window(vis, how="this demo"):
    """Stop with a message when the 3D window did not open, instead of crashing.

    ChVisualSystemIrrlicht.Initialize() does not raise when it cannot make a
    video driver. It prints "Failed to create the video driver - giving up",
    returns normally, and leaves GetDevice() null -- and the NEXT call into the
    driver dereferences that null. Measured on a headless Linux box: the
    manipulate demo died at exit 139 inside vis.AddLogo(), one line after
    Initialize, with no Python traceback and nothing naming a display.

    IsInitialized() is the question worth asking, and it is about the window,
    not about the operating system: False here on a machine with no desktop
    session, True on a Mac and True on the same Linux box with DISPLAY set.

    WHY os._exit AND NOT sys.exit. A visual system holding a null device also
    segfaults in its own destructor, which runs during interpreter shutdown --
    so plain sys.exit() raised the right message and then lost it, because the
    crash came before Python flushed stderr. Every run of the manipulate demo
    on the headless box printed only Chrono's own line and died at 139. Writing
    the message first, then leaving without finalizing, is what gets it read.
    """
    if vis.IsInitialized():
        return vis
    sys.stdout.flush()
    sys.stderr.write(
        "\nThe 3D window could not be opened, so there is nothing to drive.\n"
        "Chrono reported 'Failed to create the video driver' just above.\n\n"
        "  This needs a desktop session. Over ssh, either forward one or point\n"
        "  the process at a display that exists.\n"
        f"  For numbers without a window, {how}.\n")
    sys.stderr.flush()
    os._exit(1)


__all__ = ["chrono", "require_window"]
