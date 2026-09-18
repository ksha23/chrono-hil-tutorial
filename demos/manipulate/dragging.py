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
"""The human's grip on the scene: press, pull, let go.

Pulled out of main() because it is the one piece of that loop with a life of
its own. It owns five pieces of state -- whether something is held, what, where
it was grabbed, the surface normal there, and how far the drag plane has been
turned -- and threading those through a 282-line function as locals is how the
loop got that long.

The keyboard path and the mouse path share the same grip, which is why both
live here: pressing Z and clicking are the same act.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from chronohil import (GRAB_REACH, Grabber, chrono, pick_along_ray,
                       pick_near_ray)


class Manipulator:
    """Whatever the person currently has hold of, and how they got it."""

    def __init__(self, system, grabbable, kinematic=False):
        self.system = system
        # A kinematic scene is positioned outright, not pulled on, so the
        # mouse path is simply not offered there.
        self.kinematic = kinematic
        self.grabbable = grabbable
        self.grabber = Grabber(system)
        self.held = False
        self.plane_angle = 0.0
        self.grab_point = None
        self.grab_normal = None

    # -- the keyboard path ---------------------------------------------------
    def toggle(self, body):
        """Z: grab what is selected, or let go of what is held."""
        if self.held:
            self.release()
            return False
        self.grabber.grab(body, body.GetPos())
        self.held = True
        return True

    def release(self):
        if self.held:
            self.grabber.release()
            self.held = False

    # -- passthroughs the loop and the HUD want ------------------------------
    def move(self, dx, dy, dz):
        self.grabber.move(dx, dy, dz)

    def force(self):
        return self.grabber.force() if self.held else 0.0

    def draw_link(self):
        self.grabber.draw_link()

    # -- the mouse path ------------------------------------------------------
    def mouse_update(self, console):
        """One step of press / drag / release, straight on the 3D window."""
        if console is None or not hasattr(console, "ray_through") or self.kinematic:
            return
        down = console.mouse_down()
        at = console.cursor_pixel()
        if down and not console.prev_mouse and at is not None:
            r = console.ray_through(*at)
            if r:
                got = pick_along_ray(self.system, r[0], r[1])
                if got and got[0] not in self.grabbable:
                    # A real ray hit on something that cannot be dragged.
                    # Say so for the arm base: it is the one part of the
                    # robot a user will click and get nothing from, and
                    # silence there reads as "the click was ignored" rather
                    # than "that piece is bolted to the table". Grabbing it
                    # anyway would be worse -- a fixed body has no degrees of
                    # freedom, so the spring would pull on nothing.
                    if got[0].IsFixed() and got[0].GetName().startswith("panda"):
                        print(f"[mouse] {got[0].GetName()} is bolted down")
                    got = None       # hit the floor or something unpickable
                if got is None:
                    d0 = r[1] - r[0]
                    got = pick_near_ray(self.grabbable, r[0], d0 / d0.Length())
                if got:
                    body, point, normal = got
                    # `is` compares Python proxies, and CastToChBody mints a
                    # fresh one per call, so it never matched and this guard
                    # did nothing. SWIG's __eq__ compares the C++ pointer.
                    if self.grabber.handle is None or body != self.grabber.handle:
                        self.grabber.grab(body, point)
                        self.held = True
                        self.plane_angle = 0.0
                        fwd = r[1] - r[0]
                        fwd = fwd / fwd.Length()
                        self.grabber.set_plane(point, normal, fwd, self.plane_angle)
                        self.grab_normal = normal
                        self.grab_point = point
                        print(f"[mouse] grabbed {body.GetName()}")
        elif down and self.held and at is not None:
            spin = console.plane_spin()
            if spin:
                # Past about 70 degrees the plane turns edge-on to the camera
                # and the cursor ray stops meeting it, which reads as the drag
                # dying. Genesis just skips those frames; clamping short of it
                # keeps every rotation usable.
                # NB: this block runs every physics step, not every render
                # frame, so the rate is per STEP. Scaling it by render_every
                # as well made it 10x too fast, and Q/E just slammed into the
                # clamp -- which reads exactly like the key doing nothing.
                self.plane_angle = max(-1.2, min(1.2, self.plane_angle + spin * 1.5 * STEP))
                cf = console.vis.GetActiveCamera()
                cp, ct = cf.getAbsolutePosition(), cf.getTarget()
                fwd = chrono.ChVector3d(ct.X - cp.X, ct.Y - cp.Y, ct.Z - cp.Z)
                fwd = fwd / fwd.Length()
                self.grabber.set_plane(self.grabber.body.GetPos(), self.grab_normal, fwd, self.plane_angle)
            r = console.ray_through(*at)
            if r:
                d = (r[1] - r[0])
                d = d / d.Length()
                target = self.grabber.plane_point(r[0], d)
                if target is not None:
                    # A near-parallel plane puts the intersection a very long
                    # way off; letting the handle jump there stretches the
                    # spring into a launch.
                    here = self.grabber.body.GetPos()
                    off = target - here
                    far = off.Length()
                    if far > GRAB_REACH:
                        target = here + off * (GRAB_REACH / far)
                    self.grabber.handle.SetPos(target)
        elif (not down) and console.prev_mouse and self.held:
            self.grabber.release(); self.held = False
            print("[mouse] released")
        console.prev_mouse = down
