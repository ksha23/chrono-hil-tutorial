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
"""Pixel to world ray. The one part of reading this window that has no OS in it.

Every backend in this package answers three questions of its operating system
-- where the cursor is, whether the button is down, where our window sits --
and then does the SAME arithmetic on the answer. That arithmetic was copied
into each backend, and copies drift: the macOS and Irrlicht ones had already
grown apart in spelling (componentwise subtraction against ChVector3d
subtraction) while computing the same thing, and adding X11 and Win32 would
have made four and five. A ray that is subtly wrong in one backend is a bug
that only appears on one person's machine, which is the worst kind to chase.

It needs no platform because ICameraSceneNode IS wrapped by SWIG: getFOV() and
getAspectRatio() are readable from Python on every build, which is exactly why
this is the piece that never needed the OS in the first place.
"""

import math

from ...chrono_env import chrono


class CameraRay:
    """ray_through() for any backend that carries .vis, .cw and .ch.

    Mixed in rather than called, so the demos' `hasattr(console, "ray_through")`
    test -- their way of asking "can this console point at the 3D view?" --
    keeps meaning what it meant.
    """

    def ray_through(self, px, py, reach=60.0):
        """(near, far) in world coordinates through window pixel (px, py)."""
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
