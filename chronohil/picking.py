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
"""Turning a screen ray into a body, and a body into something you can pull."""

from .chrono_env import chrono
from .config import GRAB_MAX_SPEED, GRAB_OMEGA, GRAB_REACH, GRAB_ZETA

def pick_along_ray(system, start, end):
    """The primitive a mouse click would use. Returns (body, world_point) or None."""
    res = chrono.ChRayhitResult()
    system.GetCollisionSystem().RayHit(start, end, res)
    if not res.hit:
        return None
    body = chrono.CastToChBody(res.hitModel.GetContactable())
    if body is None:
        return None
    p, nrm = res.abs_hitPoint, res.abs_hitNormal
    return (body, chrono.ChVector3d(p.x, p.y, p.z),
            chrono.ChVector3d(nrm.x, nrm.y, nrm.z))


def pick_near_ray(bodies, origin, direction, tol=0.06):
    """Pick the body whose centre lies closest along a ray, within `tol` metres.

    Picking by collision raycast ties what you can CLICK to what has contact
    geometry, and those are different questions. The Go2's thighs and calves
    deliberately have no collision -- their URDF cylinders run the full length of
    the limb and make the robot stand on its shins -- but they are exactly the
    parts a user wants to grab. Masking them out of contacts does not help either:
    a body with an empty collision mask is not raycast-hittable at all (measured).

    So: geometry-free picking. It is also more forgiving, which matters when the
    target is a 4 cm calf seen from three metres away.
    """
    best = None
    for b in bodies:
        c = b.GetPos()
        w = chrono.ChVector3d(c.x - origin.x, c.y - origin.y, c.z - origin.z)
        along = w.x * direction.x + w.y * direction.y + w.z * direction.z
        if along <= 0:
            continue                      # behind the camera
        perp = (w - direction * along).Length()
        if perp <= tol and (best is None or along < best[0]):
            best = (along, b, chrono.ChVector3d(c.x, c.y, c.z))
    if best is None:
        return None
    return best[1], best[2], chrono.ChVector3d(0, 0, 1)


def pick_at_crosshair(system, vis, reach=50.0):
    """Ray from the camera through the centre of the view. With a wrapped mouse
    this would be getRayFromScreenCoordinates(cursor) instead; the rest is the same."""
    cam = vis.GetActiveCamera()
    cp, ct = cam.getAbsolutePosition(), cam.getTarget()
    eye = chrono.ChVector3d(cp.X, cp.Y, cp.Z)
    tgt = chrono.ChVector3d(ct.X, ct.Y, ct.Z)
    d = tgt - eye
    n = d.Length()
    if n < 1e-9:
        return None
    d = d / n
    return pick_along_ray(system, eye, eye + d * reach)


class Grabber:
    """A handle body and a stiff spring to whatever is being held."""

    def __init__(self, system):
        self.system = system
        self.handle = chrono.ChBody()
        self.handle.SetFixed(True)
        self.handle.EnableCollision(False)
        self.handle.SetName("grab handle")
        marker = chrono.ChVisualShapeSphere(0.04)
        marker.SetColor(chrono.ChColor(1.0, 0.25, 0.1))
        self.handle.AddVisualShape(marker)
        system.AddBody(self.handle)
        self.spring = None
        self.body = None
        self.plane_n = None
        self.plane_d = 0.0
        # Genesis draws the held point, the line to the cursor and the drag plane.
        # Without them you are steering something invisible, which is most of why
        # this felt uncontrollable. The line is the one that matters.
        self.link_shape = chrono.ChVisualShapeCylinder(0.006, 1.0)
        self.link_shape.SetColor(chrono.ChColor(1.0, 0.55, 0.1))
        self.link_body = chrono.ChBody()
        self.link_body.SetFixed(True)
        self.link_body.EnableCollision(False)
        self.link_body.SetName("grab line")
        self.link_body.AddVisualShape(self.link_shape)
        system.AddBody(self.link_body)

    def set_plane(self, point, surf_n, cam_fwd, angle):
        """A plane through the grab point that the cursor ray is intersected with.

        Dragging at a fixed distance from the camera confines the handle to a
        sphere, so a leg can be swung across the view but never pulled toward or
        away from it -- which is why only some parts of a robot feel reachable.
        Genesis solves it by dragging in a PLANE and letting the scroll wheel
        rotate that plane about the surface normal; rotating it is what converts
        sideways mouse motion into depth. Same idea here, on two keys.

        The plane contains the surface normal and faces the camera as squarely as
        it can, which is the orientation that makes the first drag feel natural.
        """
        # Start SCREEN-PARALLEL: plane normal = view direction. That is the best
        # conditioned plane there is (the cursor ray meets it head on) and it does
        # the obvious thing -- the body tracks the cursor across the view.
        #
        # Genesis orients its plane off the surface normal instead. That is lovely
        # for sliding along a face, but it degenerates when the surface you picked
        # happens to face the camera: the plane then contains the view direction,
        # a pixel of mouse movement slides the intersection metres along the view
        # axis, and the held body rockets at the viewer. Which is what the orange
        # handle "growing" was.
        f = cam_fwd
        lf = f.Length()
        f = f / lf if lf > 1e-9 else chrono.ChVector3d(0, 1, 0)
        # tilt axis: horizontal on screen, so left/right drags become depth
        axis = f.Cross(chrono.ChVector3d(0, 0, 1))
        if axis.Length() < 1e-6:
            axis = f.Cross(chrono.ChVector3d(1, 0, 0))
        axis = axis / axis.Length()
        pn = f * math.cos(angle) + axis * math.sin(angle)
        pn = pn / pn.Length()
        self.plane_n = pn
        self.plane_d = -(pn.x * point.x + pn.y * point.y + pn.z * point.z)

    def plane_point(self, origin, direction):
        """Where a cursor ray meets the drag plane, or None if it is parallel."""
        if self.plane_n is None:
            return None
        denom = (self.plane_n.x * direction.x + self.plane_n.y * direction.y
                 + self.plane_n.z * direction.z)
        if abs(denom) < 1e-6:
            return None
        t = -((self.plane_n.x * origin.x + self.plane_n.y * origin.y
               + self.plane_n.z * origin.z) + self.plane_d) / denom
        if t <= 0:
            return None
        return origin + direction * t

    def grab(self, body, point):
        self.release()
        self.body = body
        self.handle.SetPos(point)
        # Gains have to scale with what is being pulled. A fixed stiffness that
        # feels right on a 134 kg ball is a catapult on a 0.154 kg Go2 calf:
        # sqrt(4000/0.154) is 161 rad/s, which a 2 ms step cannot integrate, and
        # the robot leaves the scene. Genesis sidesteps this by building its
        # impulse from the link's own mass and inertia; the same idea here, as a
        # critically damped spring with a fixed time constant.
        # Stiffness is per scene, not global. The Go2 needs a hard pull to beat a
        # stance controller holding a 0.154 kg calf; a 2.7 kg arm link on a
        # 7-link chain needs a tenth of that, or yanking one link whips the whole
        # arm at tens of m/s and drives it through the floor.
        omega = getattr(self.system, "grab_omega", GRAB_OMEGA)
        m = max(body.GetMass(), 1e-3)
        k = m * omega * omega
        c = 2.0 * m * omega * GRAB_ZETA
        # Belt and braces against tunnelling: a grabbed body may not move faster
        # than contact detection can keep up with at this step size.
        self._had_limit = body.GetLimitSpeed() if hasattr(body, "GetLimitSpeed") else False
        body.SetLimitSpeed(True)
        body.SetMaxLinVel(GRAB_MAX_SPEED)
        self.spring = chrono.ChLinkTSDA()
        self.spring.Initialize(self.handle, body, False, point, point)
        self.spring.SetRestLength(0.0)
        self.spring.SetSpringCoefficient(k)
        self.spring.SetDampingCoefficient(c)
        self.system.AddLink(self.spring)

    def release(self):
        if self.spring is not None:
            self.system.RemoveLink(self.spring)
            self.spring = None
        if self.body is not None:
            self.body.SetLimitSpeed(False)
        self.body = None

    def held(self):
        return self.spring is not None

    def move(self, dx, dy, dz):
        p = self.handle.GetPos()
        self.handle.SetPos(chrono.ChVector3d(p.x + dx, p.y + dy, p.z + dz))

    def force(self):
        return abs(self.spring.GetForce()) if self.spring else 0.0

    def draw_link(self):
        """Stretch the marker line between the held body and the handle."""
        if self.body is None:
            self.link_body.SetPos(chrono.ChVector3d(0, 0, -1000))   # parked offscreen
            return
        a = self.body.GetPos()
        b = self.handle.GetPos()
        d = b - a
        length = d.Length()
        if length < 1e-4:
            return
        ez = d / length
        ref = chrono.ChVector3d(0, 0, 1)
        if abs(ez.z) > 0.99:
            ref = chrono.ChVector3d(1, 0, 0)
        ex = ref.Cross(ez); ex = ex / ex.Length()
        ey = ez.Cross(ex)
        rot = chrono.ChMatrix33d()
        rot.SetFromDirectionAxes(ex, ey, ez)
        self.link_shape.GetGeometry().h = length   # ChCylinder's height is mutable
        self.link_body.SetPos((a + b) * 0.5)
        self.link_body.SetRot(rot.GetQuaternion())
