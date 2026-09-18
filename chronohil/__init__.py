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
"""Shared pieces behind the demos.

Each demo in demos/ is a thin main() over this package. Nothing here is
platform-specific; anything that has to ask the operating system a question
lives under chronohil.input.window and is optional.
"""

from .chrono_env import chrono
from .config import (GRAB_MAX_SPEED, GRAB_OMEGA, GRAB_REACH, GRAB_ZETA,
                     HANDLE_SPEED, RENDER_FPS, STEP, UDP_PORT)
from .controllers import FreeDriveJoint, LimpJoint, StanceHolder
from .picking import Grabber, pick_along_ray, pick_at_crosshair, pick_near_ray
from .policy import Go2Policy, find_go2_policy
from .scenes import ground_plane, scene_arm, scene_go2, scene_place
from .urdf import make_chrono_safe_urdf

__all__ = [
    "chrono", "STEP", "RENDER_FPS", "HANDLE_SPEED", "UDP_PORT",
    "GRAB_OMEGA", "GRAB_ZETA", "GRAB_REACH", "GRAB_MAX_SPEED",
    "pick_along_ray", "pick_near_ray", "pick_at_crosshair", "Grabber",
    "LimpJoint", "FreeDriveJoint", "StanceHolder",
    "Go2Policy", "find_go2_policy",
    "ground_plane", "scene_go2", "scene_arm", "scene_place",
    "make_chrono_safe_urdf",
]
