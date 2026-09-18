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
"""`import pychrono` with the failure everyone hits explained.

A loader path pointing at an older libChrono wins over the packaged one, and
PyChrono then fails with a missing symbol rather than anything that names the
cause. The variable differs by platform; the mistake does not.
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

__all__ = ["chrono"]
