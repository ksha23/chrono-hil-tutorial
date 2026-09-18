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
"""Numbers shared across the demos, each with the measurement behind it."""

STEP = 2e-3               # s, the physics step every demo uses
RENDER_FPS = 50           # the eye does not need the step rate
HANDLE_SPEED = 1.2        # m/s at full stick, for key-driven dragging
UDP_PORT = 9870

# The grab spring. Gains are built from the mass being pulled, so one setting
# works on a 0.15 kg shin and a 2.7 kg arm link.
GRAB_OMEGA = 90.0         # rad/s. Has to beat a stance controller or a held
                          # leg will not budge.
GRAB_ZETA = 1.0           # critically damped
GRAB_REACH = 0.45         # m: furthest the handle may sit from the held point.
                          # This bounds the force, since F = k*x. At 3 m a
                          # 2.7 kg link saw 24,300 m/s^2, which is 48 m/s in one
                          # 2 ms step: straight through the floor.
GRAB_MAX_SPEED = 2.5      # m/s: a held body cannot outrun contact detection
