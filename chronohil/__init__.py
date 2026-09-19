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
"""Shared pieces behind the demos: the map of this package.

Each demo in demos/ is a thin main() over what is here. Nothing in this
package is platform-specific; the one directory that has to ask an operating
system a question is chronohil/input/window, and it is optional.

WHAT IS IN EACH FILE, in the order it is worth reading them:

    chrono_env.py   `import pychrono`, and the two failures everyone hits:
                    a loader path shadowing libChrono, and a 3D window that
                    could not open. Every demo imports chrono from here.
    config.py       every tuned number in one place, each with the measurement
                    that chose it. Start here to understand the grab spring.
    paths.py        where the vendored robots live, resolved once

    scenes.py       the three scenes: a Go2 from URDF, a Franka Panda, and a
                    kinematic placement scene. Each returns the same tuple.
    urdf.py         the two things in a stock robot URDF that segfault
                    Chrono's parser, and what is done about them
    policy.py       the trained Go2 locomotion policy, and the conventions it
                    was trained under, none of which are ours
    controllers.py  the joint-level laws: limp, hand-guided, locked, stance PD

    picking.py      a screen ray to a body (pick_along_ray), and a body to
                    something you can pull (Grabber)
    watchdog.py     notice the simulation going unstable and print the run-up,
                    not just the crater

    input/          ways a person's numbers reach the simulation:
      keys.py         a small pygame window of our own. Portable, always works.
      window/         the 3D window itself, when the build allows it. Read
                      window/__init__.py first: it picks a backend and it is
                      the only file in the project that names an OS.

Demos 3 and 4 are assembled almost entirely from this package. Demos 1 and 2
(demos/driver/) take only chrono_env from it and keep the rest of their parts
in three modules beside the script, so that script can be read top to bottom.
"""

from .chrono_env import chrono, require_window
from .config import (GRAB_MAX_SPEED, GRAB_MIN_MASS, GRAB_OMEGA, GRAB_REACH, GRAB_ZETA,
                     HANDLE_SPEED, RENDER_FPS, STEP)
from .controllers import FreeDriveJoint, LimpJoint, LockedJoint, StanceHolder
from .picking import Grabber, pick_along_ray, pick_at_crosshair, pick_near_ray
from .policy import Go2Policy, find_go2_policy
from .scenes import ground_plane, scene_arm, scene_go2, scene_place
from .urdf import make_chrono_safe_urdf

__all__ = [
    "chrono", "require_window", "STEP", "RENDER_FPS", "HANDLE_SPEED",
    "GRAB_OMEGA", "GRAB_ZETA", "GRAB_REACH", "GRAB_MAX_SPEED", "GRAB_MIN_MASS",
    "pick_along_ray", "pick_near_ray", "pick_at_crosshair", "Grabber",
    "LimpJoint", "FreeDriveJoint", "LockedJoint", "StanceHolder",
    "Go2Policy", "find_go2_policy",
    "ground_plane", "scene_go2", "scene_arm", "scene_place",
    "make_chrono_safe_urdf",
]
