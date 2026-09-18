# =============================================================================
# PROJECT CHRONO - http://projectchrono.org
#
# Copyright (c) 2026 projectchrono.org
# All rights reserved.
#
# Use of this source code is governed by a BSD-style license that can be found
# in the LICENSE file at the top level of the distribution and at
# http://projectchrono.org/license-chrono.txt.
#
# =============================================================================
# PART 9: the other kind of human-in-the-loop -- reaching into the scene.
#
# Parts 1-8 put a person in the control loop of a plant: three numbers in,
# state out.  This is the other thing people want a human for, and it is not
# the same thing:
#
#     "push the robot and see whether the controller recovers"
#     "drag this object over there and tell me where you put it"
#     "grab that link and move the arm by hand"
#
# Here the human perturbs the WORLD rather than driving the plant.  Chrono has
# no built-in click-and-drag manipulator -- the mouse in both the Irrlicht and
# VSG backends is wired to the camera, and the one Irrlicht picking call in the
# tree is a commented-out line in ChIrrCamera.cpp.  But every primitive is
# there, and this file is the twenty lines that put them together:
#
#     ChCollisionSystem::RayHit()   pick a body along a ray
#     ChRayhitResult.hitModel       -> GetContactable() -> CastToChBody()
#     ChLinkTSDA                    a rubber band from a handle to the body
#
# Dragging with a spring rather than teleporting is the whole point: the body
# still collides, still has momentum, and a controller holding it still fights
# back.  That is what makes it a robustness test rather than a cheat.
#
# WHY THERE IS NO KEYBOARD HERE.  PyChrono cannot read the Irrlicht window's
# keyboard: irr::IEventReceiver is exposed but abstract with no constructor
# (SWIG directors are off), and device.getCursorControl() hands back an
# unwrapped SwigPyObject.  So there is no mouse and no keys from Python.  That
# turns out not to matter, because PART 4 already solved it: operator_console.py
# sends input over UDP and needs no changes at all to drive this.
#
#     python hil_manipulate.py go2      # and operator_console.py in terminal 2
#     python hil_manipulate.py arm
#     python hil_manipulate.py place
#
# CONTROLS (all from operator_console.py, unchanged)
#     arrow keys   move the grab handle: up/down = X, left/right = Y
#     ] and [      move it up and down in Z
#     Z            grab / release the selected body
#     X            cycle which body is selected
#     C            reset the scene
#     T            log the selected body's pose (the placement workflow)
# =============================================================================

import math
import socket
import time

import os
import sys

try:
    import pychrono as chrono
except ImportError as exc:
    if "symbol not found" in str(exc) and os.environ.get("DYLD_LIBRARY_PATH"):
        sys.exit(
            "PyChrono failed to load because DYLD_LIBRARY_PATH points somewhere\n"
            "with an older libChrono, so its symbols win over the conda ones:\n"
            f"  DYLD_LIBRARY_PATH={os.environ['DYLD_LIBRARY_PATH']}\n\n"
            "  unset DYLD_LIBRARY_PATH && python " + " ".join(sys.argv) + "\n\n"
            f"(original error: {exc})")
    raise
import pychrono.irrlicht as irr

UDP_PORT = 9870
STEP = 2e-3
RENDER_FPS = 50
HANDLE_SPEED = 1.2        # m/s at full stick
GRAB_OMEGA = 90.0      # rad/s: how hard the cursor pulls. Has to beat the
                       # stance controller or a held leg will not budge.
GRAB_ZETA = 1.0        # critically damped
GRAB_REACH = 0.45      # m: furthest the handle may sit from the held point.
                       # This bounds the spring force. At the old 3 m a 2.7 kg
                       # Panda link saw 24,300 m/s^2 -- 48 m/s in one 2 ms step,
                       # which tunnels through the floor and fights contact into
                       # a jitter. Force is k*x, so clamping x is the cheap fix.
GRAB_MAX_SPEED = 2.5   # m/s: a held body cannot outrun contact detection


# -----------------------------------------------------------------------------
# The PART 4 input path, unchanged in spirit: levels are held, commands are drained
# -----------------------------------------------------------------------------
class Console:
    def __init__(self, port=UDP_PORT):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.sock.setblocking(False)
        self.last = (0.0, 0.0, 0.0)
        self.commands = []
        self.addr = None
        print(f"[udp] listening on {port} - now run:  python operator_console.py")

    def poll(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(256)
            except BlockingIOError:
                break
            f = data.decode().split(",")
            if len(f) < 3:
                continue
            try:
                self.last = tuple(float(x) for x in f[:3])
            except ValueError:
                continue
            self.addr = addr
            if len(f) > 3 and f[3] and f[3] != "-":
                self.commands.append(f[3][0])
        return self.last

    def take_commands(self):
        c, self.commands = self.commands, []
        return c

    def send(self, text):
        if self.addr:
            self.sock.sendto(text.encode(), self.addr)


class LocalInput:
    """A small pygame window in this same process, so one command is enough.

    PyChrono still cannot read the Irrlicht window (SWIG directors are off, and
    getCursorControl() returns an unwrapped object), so the keys have to be read
    by something else -- but that something does not have to be another process.
    pygame and Irrlicht coexist happily here; only the socket was ever needed.

    Same interface as Console, so the loop cannot tell them apart.
    """

    KEYS = None          # filled in on first use, so pygame is imported lazily

    def __init__(self):
        import pygame
        self.pg = pygame
        pygame.init()
        self.screen = pygame.display.set_mode((460, 190))
        pygame.display.set_caption("hil_manipulate - input (keep this window focused)")
        self.font = pygame.font.SysFont("menlo,dejavusansmono,monospace", 15)
        LocalInput.KEYS = {
            pygame.K_RIGHTBRACKET: "u", pygame.K_LEFTBRACKET: "d",
            pygame.K_z: "f", pygame.K_x: "n", pygame.K_c: "r", pygame.K_t: "m",
        }
        self.commands = []
        self.last = (0.0, 0.0, 0.0)
        self.addr = ("local", 0)
        self.status = ""
        print("[input] local window open - keep IT focused, not the 3D view")

    def poll(self):
        pg = self.pg
        for ev in pg.event.get():
            if ev.type == pg.QUIT:
                raise SystemExit
            if ev.type == pg.KEYDOWN:
                if ev.key == pg.K_ESCAPE:
                    raise SystemExit
                if ev.key in LocalInput.KEYS:
                    self.commands.append(LocalInput.KEYS[ev.key])
        k = pg.key.get_pressed()
        steer = (-1.0 if k[pg.K_LEFT] else 0.0) + (1.0 if k[pg.K_RIGHT] else 0.0)
        thr = 1.0 if k[pg.K_UP] else 0.0
        brk = 1.0 if k[pg.K_DOWN] else 0.0
        self.last = (steer, thr, brk)
        return self.last

    def take_commands(self):
        c, self.commands = self.commands, []
        return c

    def send(self, text):
        self.status = text

    def draw(self, lines):
        pg = self.pg
        self.screen.fill((18, 18, 22))
        for i, line in enumerate(lines):
            self.screen.blit(self.font.render(line, True, (220, 220, 200)), (12, 10 + i * 22))
        pg.display.flip()


class DirectInput:
    """Mouse and keyboard read from the OS, so they work ON the 3D window.

    PyChrono cannot read that window itself: SWIG directors are off so
    irr::IEventReceiver cannot be subclassed, and getCursorControl() and
    getSceneCollisionManager() both come back as unwrapped SwigPyObjects.  But
    the window belongs to this process and macOS will tell us about it:

        AppKit.NSEvent.mouseLocation()        where the cursor is, focus or not
        Quartz.CGEventSourceButtonState()     whether the left button is down
        Quartz.CGEventSourceKeyState()        whether a key is down
        Quartz.CGWindowListCopyWindowInfo()   where our window sits on screen

    None of those need accessibility permission.  What Irrlicht will not hand
    over is the ray for a screen pixel, but ICameraSceneNode IS wrapped, so
    getFOV() and getAspectRatio() are enough to build it exactly.
    """

    # macOS virtual key codes
    K = {"left": 123, "right": 124, "down": 125, "up": 126,
         "z": 6, "x": 7, "c": 8, "t": 17, "lbracket": 33, "rbracket": 30,
         # camera, deliberately on keys so the mouse stays free for grabbing
         "a": 0, "d": 2, "w": 13, "s": 1, "r": 15, "f": 3,
         # rotate the drag plane -> this is the depth control
         "q": 12, "e": 14,
         "esc": 53}
    EDGE = {"z": "f", "x": "n", "c": "r", "t": "m", "rbracket": "u", "lbracket": "d",
            "esc": "q"}

    def __init__(self, vis, title, content_w, content_h):
        import Quartz, AppKit
        self.Q, self.AK = Quartz, AppKit
        self.vis, self.title = vis, title
        self.cw, self.ch = content_w, content_h
        self.commands = []
        self.prev = {k: False for k in self.EDGE}
        self.prev_mouse = False
        self.addr = ("direct", 0)
        self.last = (0.0, 0.0, 0.0)
        self._rect = None
        self._rect_age = 0
        print("[input] reading mouse and keys from the OS - click straight on the 3D window")

    # -- OS state ------------------------------------------------------------
    def _key(self, name):
        return bool(self.Q.CGEventSourceKeyState(
            self.Q.kCGEventSourceStateHIDSystemState, self.K[name]))

    def mouse_down(self):
        return bool(self.Q.CGEventSourceButtonState(
            self.Q.kCGEventSourceStateHIDSystemState, 0))

    def window_rect(self):
        """Screen rect of our Irrlicht window, refreshed occasionally (it can move)."""
        self._rect_age -= 1
        if self._rect is not None and self._rect_age > 0:
            return self._rect
        wl = self.Q.CGWindowListCopyWindowInfo(
            self.Q.kCGWindowListOptionOnScreenOnly | self.Q.kCGWindowListExcludeDesktopElements,
            self.Q.kCGNullWindowID)
        for w in wl:
            if self.title.lower() in (w.get("kCGWindowName") or "").lower():
                b = w["kCGWindowBounds"]
                self._rect = (b["X"], b["Y"], b["Width"], b["Height"])
                self._rect_age = 60
                return self._rect
        return self._rect

    def cursor_pixel(self):
        """Cursor in window content pixels, or None when it is outside."""
        r = self.window_rect()
        if r is None:
            return None
        wx, wy, ww, wh = r
        loc = self.AK.NSEvent.mouseLocation()
        screen_h = self.AK.NSScreen.screens()[0].frame().size.height
        top_y = screen_h - loc.y                      # Quartz counts down from the top
        chrome = wh - self.ch                          # title bar
        px = loc.x - wx
        py = top_y - wy - chrome
        if 0 <= px < self.cw and 0 <= py < self.ch:
            return px, py
        return None

    # -- the ray Irrlicht would not give us ----------------------------------
    def ray_through(self, px, py, reach=60.0):
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

    # -- Console-compatible surface -----------------------------------------
    def poll(self):
        for name, cmd in self.EDGE.items():
            now = self._key(name)
            if now and not self.prev[name]:
                self.commands.append(cmd)
            self.prev[name] = now
        steer = (-1.0 if self._key("left") else 0.0) + (1.0 if self._key("right") else 0.0)
        self.last = (steer, 1.0 if self._key("up") else 0.0,
                     1.0 if self._key("down") else 0.0)
        return self.last

    def take_commands(self):
        c, self.commands = self.commands, []
        return c

    def plane_spin(self):
        """(-1/0/+1) from Q/E: rotate the drag plane about the surface normal."""
        return (-1.0 if self._key("q") else 0.0) + (1.0 if self._key("e") else 0.0)

    def camera_nudge(self):
        """(orbit, zoom, rise) from A/D, W/S, R/F -- held, not edge-triggered."""
        return ((-1.0 if self._key("a") else 0.0) + (1.0 if self._key("d") else 0.0),
                (-1.0 if self._key("w") else 0.0) + (1.0 if self._key("s") else 0.0),
                (-1.0 if self._key("f") else 0.0) + (1.0 if self._key("r") else 0.0))

    def send(self, text):
        pass


# -----------------------------------------------------------------------------
# Picking and grabbing
# -----------------------------------------------------------------------------
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


# -----------------------------------------------------------------------------
# Scenes
# -----------------------------------------------------------------------------
def ground_plane(system, size=20.0):
    """The floor, with whichever contact material this system can actually use.

    An NSC material in an SMC system is not an error and not a warning: bodies
    simply fall through it. The Go2 scene runs SMC because that is what its
    policy was trained against, so this has to follow the system rather than
    assume.
    """
    if system.GetContactMethod() == chrono.ChContactMethod_SMC:
        # The values the policy was trained against, from NeDM's rigid ground.
        mat = chrono.ChContactMaterialSMC()
        mat.SetFriction(0.9)
        mat.SetRestitution(0.01)
        mat.SetGn(60.0)
        mat.SetKn(2e5)
    else:
        mat = chrono.ChContactMaterialNSC()
        mat.SetFriction(0.8)
    g = chrono.ChBodyEasyBox(size, size, 1.0, 1000, True, True, mat)
    g.SetPos(chrono.ChVector3d(0, 0, -0.5))
    g.SetFixed(True)
    g.GetVisualShape(0).SetTexture(chrono.GetChronoDataFile("textures/concrete.jpg"), 8, 8)
    system.AddBody(g)
    return g


class LimpJoint:
    """An unactuated joint: no control at all, only bearing friction.

    Zero torque would be more literally "unactuated", but a frictionless 7-link
    chain is a chaotic pendulum that swings forever and never settles. Real
    joints have friction, so a little viscous damping is the honest model and it
    lets the arm collapse and come to rest, which is the thing worth watching.
    """

    KD = 1.2
    TAU_MAX = 40.0

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target

    def update(self):
        tau = -self.KD * self.motor.GetMotorAngleDt()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))


class FreeDriveJoint:
    """Cobot-style free drive: holds its pose, but yields to a sustained push.

    Pure damping is not enough -- an arm under gravity simply falls over, which
    is what the primitive three-link version did. A plain PD holding a fixed
    target is the opposite problem: it springs back and you cannot pose it.

    So the target LAGS the actual angle. Over a short push the joint feels like a
    stiff spring; hold it somewhere for longer than the lag and that becomes the
    new rest pose. This is how a real collaborative arm behaves in hand-guiding
    mode, and it is what "move the arm by hand" needs.
    """

    KP = 400.0     # N.m per rad -- enough to carry the arm's own weight
    KD = 16.0      # N.m per rad/s
    TAU_MAX = 87.0  # N.m, the Panda's largest joint limit
    FOLLOW = 0.004  # per step, and ONLY while something is being held

    # A rest pose that always creeps toward the actual angle droops: gravity
    # walks the arm down and the target follows it. One that never creeps springs
    # back and cannot be posed. Real hand-guiding resolves this by being a MODE:
    # the arm complies while you have hold of it and locks the instant you let
    # go. The loop sets this while the grabber holds something.
    guiding = False

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target

    def update(self):
        q = self.motor.GetMotorAngle()
        if FreeDriveJoint.guiding:
            self.target += (q - self.target) * self.FOLLOW
        tau = self.KP * (self.target - q) - self.KD * self.motor.GetMotorAngleDt()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))


class StanceHolder:
    """One joint's PD law: the stand-in for a locomotion policy.

    A real policy would read the whole robot state and emit twelve torques; this
    reads one joint and emits one. What matters for the demo is identical --
    something is actively holding a pose, so a human pulling on a leg is a
    disturbance it has to reject.
    """

    # These have to actually hold the robot up. At KP 26 it sags, topples and
    # ends up on its back with its legs in the air -- and because the legs then
    # hang unloaded, the per-joint error reads LOW, which is a metric that hides
    # exactly the failure it should catch. Check the base height and uprightness
    # instead: standing is z ~ 0.27 with the body z-axis still pointing up.
    KP = 120.0     # N.m per rad
    KD = 4.0       # N.m per rad/s
    TAU_MAX = 60.0  # N.m

    def __init__(self, motor, fn, target):
        self.motor, self.fn, self.target = motor, fn, target

    def update(self):
        err = self.target - self.motor.GetMotorAngle()
        tau = self.KP * err - self.KD * self.motor.GetMotorAngleDt()
        self.fn.SetConstant(max(-self.TAU_MAX, min(self.TAU_MAX, tau)))


# -----------------------------------------------------------------------------
# The real thing: a trained locomotion policy driving the twelve joints
# -----------------------------------------------------------------------------
# WHERE THE CHECKPOINT COMES FROM. A legged_gym-family Go2 actor, TorchScript,
# 45 observations in and 12 actions out. Set GO2_POLICY_CKPT, or drop one at
# go2_assets/go2_policy.pt. Without one the scene falls back to the PD stance
# holder below, which holds a pose but cannot step.
GO2_POLICY_PATHS = (
    os.environ.get("GO2_POLICY_CKPT", ""),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "go2_assets/go2_policy.pt"),
    os.path.expanduser("~/sync/sbel/go2_finetuned_v4.pt"),
)


def find_go2_policy():
    for q in GO2_POLICY_PATHS:
        if q and os.path.exists(q):
            return q
    return None


class Go2Policy:
    """A trained locomotion policy, driving the joints through a PD actuator.

    NONE OF THESE CONVENTIONS ARE OURS and none of them are negotiable: they
    belong to the harness the checkpoint was trained in, and each one silently
    corrupts the observation if it is wrong, which shows up as a robot that
    twitches and falls rather than as an error. They are taken from NeDM's
    imported_policy.py, which derived them against the checkpoint's own config.

        joint order    the policy counts FL, FR, RL, RR; the URDF gives us
                       RR, RL, FR, FL, hence TO_POLICY
        sign           joint angles and targets are NEGATED between the two
        defaults       hips are +/-0.1, not 0, and front and rear thighs differ
        observation    45, not the base config's 48: there is no base linear
                       velocity block, which is exactly why this checkpoint
                       ports to another simulator at all
        rates          the POLICY runs at 50 Hz; the PD underneath it runs every
                       physics step. A PD evaluated only at the policy rate is a
                       different controller and this policy would not survive it.

    Unlike the stance holder, this one can pick a foot up, so a shove it cannot
    simply stiffen against is answered by stepping.
    """

    NAMES = ["RR_hip_joint", "RR_thigh_joint", "RR_calf_joint",
             "RL_hip_joint", "RL_thigh_joint", "RL_calf_joint",
             "FR_hip_joint", "FR_thigh_joint", "FR_calf_joint",
             "FL_hip_joint", "FL_thigh_joint", "FL_calf_joint"]
    TO_POLICY = [9, 10, 11, 6, 7, 8, 3, 4, 5, 0, 1, 2]
    SIGN = -1.0
    # THESE ARE NOT THE TRAINED GAINS AND THAT IS A KNOWN DEVIATION. Every
    # legged_gym-family Go2 config specifies kp 20, kd 0.5, and that is what the
    # checkpoint assumes. Measured on THIS plant, kp 20 cannot hold the policy's
    # own stand pose: the joints sag 0.37 rad and the base settles at 0.24 m
    # instead of ~0.30, so the first observation the policy gets is already off
    # its training distribution and it crouches further from there. At kp 40 /
    # kd 2 the same scripted stand holds to 0.14 rad at 0.29 m and the policy
    # stands and steps. Raising the gains is a workaround for a plant mismatch,
    # not a fix for it -- see the note on the checkpoint in find_go2_policy.
    KP = float(os.environ.get("GO2_POLICY_KP", "40.0"))
    KD = float(os.environ.get("GO2_POLICY_KD", "2.0"))
    CTRL_DT = 0.02               # 50 Hz policy, decimation 4 over their 200 Hz PD
    ANG_VEL_SCALE = 0.25
    DOF_VEL_SCALE = 0.05
    ACTION_SCALE = 0.25

    def __init__(self, system, parser, ckpt, command=(0.0, 0.0, 0.0)):
        import numpy as np
        import torch
        self.np, self.torch = np, torch
        self.DEFAULTS = np.array([0.1, 0.8, -1.5, -0.1, 0.8, -1.5,
                                  0.1, 1.0, -1.5, -0.1, 1.0, -1.5], dtype=np.float32)
        self.EFFORT = np.array([23.7, 23.7, 45.43] * 4)   # URDF <limit effort>
        self.CMD_SCALE = np.array([2.0, 2.0, 0.25], dtype=np.float32)
        self.model = torch.jit.load(str(ckpt), map_location="cpu")
        self.model.eval()
        self.system = system
        self.motors, self.fns = [], []
        for n in self.NAMES:
            m = chrono.CastToChLinkMotorRotationTorque(parser.GetChMotor(n))
            if m is None:
                raise RuntimeError(f"no torque motor for {n}")
            fn = chrono.ChFunctionConst(0.0)
            m.SetMotorFunction(fn)
            self.motors.append(m)
            self.fns.append(fn)
        self.base = parser.GetChBody("base")
        self.command = np.array(command, dtype=np.float32)
        self.last_actions = np.zeros(12, dtype=np.float32)
        self.target = self.default_targets()
        self.next_ctrl = 0.0
        # SETTLE FIRST, THEN HAND OVER. The URDF spawns every joint at zero,
        # which is nowhere near the pose this policy was ever shown: its
        # observation block is (q - defaults), so at t=0 that is a whole radian
        # of error on eight joints and the network is being asked about a robot
        # it has never seen. Handed the scene in that state it diverges -- feet
        # four metres up, robot inverted. A second of plain PD onto the default
        # pose puts the first real observation inside the distribution.
        # Their handover, not ours: ramp the joints to a stand over RAMP seconds,
        # hold it for SETTLE, and only then let the network drive. Stepping
        # straight to the pose, or handing over from the spawn pose, puts the
        # first observation outside anything the policy was trained on and it
        # diverges -- feet metres in the air within two seconds.
        self.ramp = 0.75
        self.settle = 0.5
        self.q0 = None
        # The scripted stand. Hips at 0, which is NOT the policy's own zero-action
        # pose (+/-0.1); this is the pose their collector ramps to.
        self.stand = self.np.array([0.0, -1.0, 1.5, 0.0, -1.0, 1.5,
                                    0.0, -0.8, 1.5, 0.0, -0.8, 1.5])

    # -- conventions ---------------------------------------------------------
    def default_targets(self):
        """The policy's rest pose, in Chrono joint order and Chrono's sign."""
        out = self.np.zeros(12)
        out[self.TO_POLICY] = self.DEFAULTS
        return self.SIGN * out

    @staticmethod
    def _projected_gravity(q):
        """Gravity in the base frame: what the policy uses instead of a pose."""
        qw, qx, qy, qz = q.e0, q.e1, q.e2, q.e3
        return [-2.0 * (qx * qz - qw * qy),
                -2.0 * (qy * qz + qw * qx),
                -(1.0 - 2.0 * (qx * qx + qy * qy))]

    def _q(self):
        np = self.np
        return (np.array([m.GetMotorAngle() for m in self.motors], dtype=np.float32),
                np.array([m.GetMotorAngleDt() for m in self.motors], dtype=np.float32))

    def observe(self):
        """ang_vel(3) | gravity(3) | command(3) | dof_pos(12) | dof_vel(12) | prev(12)"""
        np = self.np
        w = self.base.GetAngVelLocal()
        ang = np.array([w.x, w.y, w.z], dtype=np.float32) * self.ANG_VEL_SCALE
        grav = np.array(self._projected_gravity(self.base.GetRot()), dtype=np.float32)
        cmd = self.command * self.CMD_SCALE
        qc, qdc = self._q()
        q = self.SIGN * qc[self.TO_POLICY]
        qd = self.SIGN * qdc[self.TO_POLICY]
        return np.concatenate([ang, grav, cmd, q - self.DEFAULTS,
                               qd * self.DOF_VEL_SCALE,
                               self.last_actions]).astype(np.float32)

    # -- the two rates -------------------------------------------------------
    def update(self):
        """Called every physics step: policy at 50 Hz, PD underneath at step rate."""
        t = self.system.GetChTime()
        if self.q0 is None:
            self.q0 = self._q()[0].astype(float)
        if t < self.ramp:
            a = t / self.ramp
            self.target = self.q0 + a * (self.stand - self.q0)
            self.next_ctrl = self.ramp + self.settle
        elif t < self.ramp + self.settle:
            self.target = self.stand
            self.next_ctrl = self.ramp + self.settle
        elif t >= self.next_ctrl:
            self.next_ctrl = t + self.CTRL_DT
            obs = self.torch.from_numpy(self.observe()).unsqueeze(0)
            with self.torch.no_grad():
                action = self.model(obs).squeeze(0).numpy().astype(self.np.float32)
            self.last_actions = action
            targets = action * self.ACTION_SCALE + self.DEFAULTS
            out = self.np.zeros(12)
            out[self.TO_POLICY] = targets
            self.target = self.SIGN * out
        qc, qdc = self._q()
        tau = self.KP * (self.target - qc) - self.KD * qdc
        tau = self.np.clip(tau, -self.EFFORT, self.EFFORT)
        for fn, v in zip(self.fns, tau):
            fn.SetConstant(float(v))


def scene_go2(system):
    """A real Unitree Go2 from URDF, its joints holding a stance while you pull a leg."""
    import pychrono.parsers as parsers
    # Contact envelope and margin, from the setup this robot's policy was
    # collected in. Chrono's defaults are much larger, and a policy feels that
    # as a foot that makes contact early and mushily.
    chrono.ChCollisionModel.SetDefaultSuggestedEnvelope(0.0025)
    chrono.ChCollisionModel.SetDefaultSuggestedMargin(0.0025)
    urdf = make_chrono_safe_urdf(GO2_URDF)
    ground = ground_plane(system)
    p = parsers.ChParserURDF(urdf)
    if "../obj/" not in open(urdf).read():
        p.EnableCollisionVisualization()   # no real visuals survived; draw the shapes
    # Without this the parsed bodies get no contact material and the robot falls
    # straight through the floor -- silently, since nothing warns about it.
    feet = chrono.ChContactMaterialData()
    feet.mu = 0.8
    feet.cr = 0.0
    p.SetDefaultContactMaterial(feet)
    # FORCE, not POSITION. A position-actuated joint is a CONSTRAINT: the solver
    # holds the commanded angle exactly, so pulling on a leg cannot move it --
    # a soft spring does nothing at all, and a stiff one only destabilises the
    # solver until the robot is flung across the scene. Neither is a robustness
    # test. Torque actuation with a PD law underneath is compliant: the leg gives
    # when you pull, and the controller pulls it back when you let go, which is
    # the thing this demo exists to show.
    p.SetAllJointsActuationType(parsers.ChParserURDF.ActuationType_FORCE)
    # SPAWN CLEAR OF THE FLOOR. At the URDF's zero joint angles the legs hang
    # straight, putting the feet 0.42 m below the base -- so the old 0.36 spawned
    # them 6.6 cm UNDERGROUND. NSC quietly pushed them out; SMC answers a 6.6 cm
    # penetration with a penalty force that throws the robot into the air at
    # 4 m/s, and it lands on its back. Measured, not guessed.
    p.SetRootInitPose(chrono.ChFramed(chrono.ChVector3d(0, 0, 0.45), chrono.QUNIT))
    p.PopulateSystem(system)

    # ChParserURDF builds collision models but leaves collision DISABLED on every
    # body, so the robot falls through the floor without a word. Here it goes back
    # on for EVERY link, so every visible part of the robot can be clicked.
    # Self-collision is masked out with Chrono's family masks: one family for the
    # whole robot, and a mask that excludes it, so a link hits the ground and
    # anything else in the scene but never another link. Adjacent links overlap
    # at their shared joint, and letting them push each other apart tears the
    # robot up.
    #
    # This used to be feet+base only, because the URDF's leg cylinders run the
    # full length of the limb (the properly sized lower-shin geometry lives in
    # the `calflower` links, which Chrono's parser cannot load) and the robot was
    # said to end up standing on its shins. Measured at GO2_STANCE, it does not:
    # base height +0.2707 m against +0.2708, worst stance error 4.1 degrees
    # either way, and the four extra contacts are calf-vs-ground pairs 5 cm apart
    # carrying 0.00 N -- proximity pairs inside the contact envelope, not load.
    # The feet still take all the weight. It costs about 11% of the step budget
    # (RTF 7.02 -> 6.26, still six times faster than real time) and it buys back
    # 12 of 17 links that could not be raycast, so could not be clicked.
    #
    # Under a drag hard enough to topple the robot it is also better behaved:
    # peak speed after release 3.62 m/s against 5.29, and the base settles at
    # +0.156 m instead of sinking to +0.070.
    #
    # The shin-standing behaviour is stance-dependent, so a much more crouched
    # GO2_STANCE could bring it back. GO2_COLLIDE = "feet+base" is the way out.
    ROBOT_FAMILY = 2
    _mode = globals().get("GO2_COLLIDE", "all")
    for b in system.GetBodies():
        if b is ground or b.IsFixed():
            continue
        if _mode == "feet+base" and not (b.GetName().endswith("_foot")
                                         or b.GetName() == "base"):
            continue
        b.EnableCollision(True)
        cm = b.GetCollisionModel()
        if cm:
            cm.SetFamily(ROBOT_FAMILY)
            cm.SetFamilyMask(~(1 << ROBOT_FAMILY) & 0x7FFF)   # signed short

    # What holds the robot up. A trained locomotion policy if there is one, and
    # the difference is not cosmetic: a stance holder can only stiffen, so a
    # shove either fails to move it or tips it over, while a policy can pick a
    # foot up and step into the push. Everything downstream is unchanged --
    # both are ticked by the loop through system.stance_holders.
    ckpt = find_go2_policy() if globals().get("GO2_CONTROL", "policy") == "policy" else None
    if ckpt:
        try:
            system.stance_holders = [Go2Policy(system, p, ckpt)]
            print(f"[go2] locomotion policy: {os.path.basename(ckpt)}")
            hint = "drag a leg; the policy steps to keep its feet"
        except Exception as exc:
            print(f"[go2] policy unavailable ({exc}); falling back to the stance PD")
            ckpt = None
    if not ckpt:
        STANCE = globals().get("GO2_STANCE", {"hip": 0.0, "thigh": 0.9, "calf": -1.8})
        holders = []
        for leg in ("FL", "FR", "RL", "RR"):
            for joint, angle in STANCE.items():
                m = p.GetChMotor(f"{leg}_{joint}_joint")
                # GetChMotor hands back the ChLinkMotor base, which only carries
                # Set/GetMotorFunction; the angle readings live on the rotation type.
                m = chrono.CastToChLinkMotorRotationTorque(m) if m else None
                if m:
                    fn = chrono.ChFunctionConst(0.0)
                    m.SetMotorFunction(fn)      # for a torque motor this IS the torque
                    holders.append(StanceHolder(m, fn, angle))
        system.stance_holders = holders   # the loop ticks these every step
        hint = "drag a leg; the joint motors fight you and pull it back"
    # "hip" was missing, so the four shoulder links were not reachable by either
    # path -- they have no collision geometry to raycast AND they were not in the
    # list pick_near_ray searches. Adding a name here costs nothing physically:
    # this list only says what the mouse and the select key are allowed to aim at.
    grabbable = [b for b in system.GetBodies()
                 if any(k in b.GetName()
                        for k in ("hip", "calf", "thigh", "foot", "base"))]
    base = [b for b in system.GetBodies() if b.GetName() == "base"][0]
    return grabbable, 0.9, hint, base


def scene_arm(system, actuated=True):
    """A real Franka Emika Panda, limp: no motors, just joint damping.

    Was three primitive boxes on revolute joints, which is a triple pendulum --
    released from a balanced vertical pose it falls and swings chaotically, and
    at fifty times real time that looked like an explosion. This is an actual
    7-DOF arm from Bullet's URDF (all-OBJ meshes, so Chrono's tiny_obj reader
    takes them directly, and every link carries inertia so the parser survives).

    Damping rather than motors is the point: "inactively controlled" means it
    gives where you push it and stays there, instead of either fighting you or
    flopping.
    """
    import pychrono.parsers as parsers
    ground_plane(system, 6.0)
    urdf = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "franka_assets", "panda_chrono.urdf")
    if not os.path.exists(urdf):
        raise SystemExit(f"Franka URDF not found at {urdf}")
    p = parsers.ChParserURDF(urdf)
    p.SetAllJointsActuationType(parsers.ChParserURDF.ActuationType_FORCE)
    # The Panda's collision geometry is OBJ triangle meshes, and mesh-mesh
    # contact is both slow and generous with contact points: upright and touching
    # nothing the arm still reported 427 contacts and an RTF of 1.34, i.e. slower
    # than real time before it had even fallen over. Convex hulls are the right
    # shape for rigid links anyway.
    p.SetAllBodiesMeshCollisionType(parsers.ChParserURDF.MeshCollisionType_CONVEX_HULL)
    mat = chrono.ChContactMaterialData()
    mat.mu = 0.6
    p.SetDefaultContactMaterial(mat)
    p.SetRootInitPose(chrono.ChFramed(chrono.ChVector3d(0, 0, 0), chrono.QUNIT))
    p.PopulateSystem(system)

    root = p.GetRootChBody()
    if root:
        root.SetFixed(True)          # bolt the base down

    # ChParserURDF builds collision models but leaves collision DISABLED, and
    # picking is a raycast against collision geometry -- so with this missing the
    # arm cannot be clicked at all and every drag is silently ignored. Same trap
    # as the Go2. Self-collision is masked off because consecutive links overlap
    # at their shared joint.
    ARM_FAMILY = 3
    for b in system.GetBodies():
        if not b.GetName().startswith("panda"):
            continue
        # The base link is fixed, and skipping fixed bodies left it outside the
        # family -- so the arm collided with its own base.
        # It now gets collision ENABLED as well, bolted down or not. A raycast
        # only sees bodies whose collision is on, so with it off panda_link0 was
        # invisible to the mouse: 0 of 14 test rays hit it, and a click on the
        # base fell straight through to the fuzzy near-ray pick. Base and ground
        # are both fixed, so the one contact this adds is free -- the solver has
        # no degrees of freedom to spend on it (2 contacts at rest before, 2
        # after, RTF unchanged).
        b.EnableCollision(True)
        cm = b.GetCollisionModel()
        if cm:
            cm.SetFamily(ARM_FAMILY)
            # One family for the whole arm, masked out of itself. Consecutive
            # links overlap at their shared joint and the hand's hull swallows
            # both fingers, so clearing this mask puts 22 self-contacts in the
            # scene before the arm has moved, halves the rate (RTF 13.2 -> 6.4)
            # and has the thing shaking itself apart at 2.0 m/s standing still.
            # The mask must keep bit 0 set or the ground stops catching the arm
            # AND the body stops being raycast-hittable (Bullet applies the same
            # group/mask filter to rayTest as to broadphase -- see pick_near_ray).
            cm.SetFamilyMask(~(1 << ARM_FAMILY) & 0x7FFF)

    # Pure damping on every actuated joint. Without it the arm is a 7-link
    # pendulum and never settles.
    dampers = []
    for link in system.GetLinks():
        m = chrono.CastToChLinkMotorRotationTorque(p.GetChMotor(link.GetName()))
        if m:
            fn = chrono.ChFunctionConst(0.0)
            m.SetMotorFunction(fn)
            cls = FreeDriveJoint if actuated else LimpJoint
            dampers.append(cls(m, fn, m.GetMotorAngle()))
    system.stance_holders = dampers

    # Everything you can SEE, not just the bodies named panda_link. The gripper
    # is `panda_hand`, `panda_leftfinger` and `panda_rightfinger`, so the old
    # startswith("panda_link") filter dropped the entire end effector -- which is
    # the "I can see it but I cannot click it" report. Collision was never the
    # problem there: all three were already hit by 14 of 14 test rays. The click
    # handler threw the hit away because the body was not in THIS list, then fell
    # back to pick_near_ray, which searches the same list, so the gripper was
    # unreachable by both paths.
    # Bodies with no visual shape stay out: panda_link8 and panda_grasptarget are
    # massless frames the URDF uses to hang the hand off link7, and a zero-mass
    # body on the end of a grab spring is a division by nothing. So does the
    # bolted-down base -- see the mouse handler in main().
    grabbable = [b for b in system.GetBodies()
                 if b.GetName().startswith("panda") and not b.IsFixed()
                 and b.GetVisualModel() is not None
                 and b.GetVisualModel().GetNumShapes() > 0]
    system.grab_omega = 22.0     # see Grabber.grab: this arm is heavy and jointed
    hint = ("hand guiding: it holds its pose, and complies while you hold a link"
            if actuated else
            "unactuated: nothing is holding it up, so it collapses under gravity")
    return (grabbable, 1.1, hint, root if root else grabbable[0])


def scene_place(system):
    """Kinematic placement: the body is moved directly, not pushed. No physics on it."""
    ground_plane(system, 30.0)
    mat = chrono.ChContactMaterialNSC()
    for i, (x, y) in enumerate(((3.0, 2.0), (-2.5, 3.5), (1.0, -3.0))):
        cone = chrono.ChBodyEasyCylinder(chrono.ChAxis_Z, 0.25, 0.7, 500, True, True, mat)
        cone.SetPos(chrono.ChVector3d(x, y, 0.35))
        cone.SetFixed(True)
        cone.GetVisualShape(0).SetColor(chrono.ChColor(0.9, 0.5, 0.05))
        system.AddBody(cone)

    body = chrono.ChBodyEasyBox(1.9, 0.9, 0.7, 600, True, False, mat)
    body.SetPos(chrono.ChVector3d(0, 0, 0.35))
    body.SetFixed(True)                      # kinematic: we set its pose outright
    body.SetName("vehicle")
    body.GetVisualShape(0).SetColor(chrono.ChColor(0.15, 0.35, 0.75))
    system.AddBody(body)
    # The camera anchor must NOT be the body being placed: following it means the
    # view moves with it and the box appears welded to the screen, which reads as
    # the controls doing nothing at all.
    marker = chrono.ChBody()
    marker.SetFixed(True); marker.EnableCollision(False)
    marker.SetPos(chrono.ChVector3d(0, 0, 0.3))
    marker.SetName("scene anchor")
    system.AddBody(marker)
    return ([body], 3.0,
            "kinematic placement: pose is set directly, and T logs it", marker)


GO2_URDF = None          # filled in by main() from --urdf or the default path


def make_chrono_safe_urdf(path):
    """Two things in a stock Go2 URDF that Chrono cannot take.

    1. Links with no <inertial>.  The Go2 has eight, collision-only cylinders
       bolted to the calves, and the parser SEGFAULTS on them rather than
       complaining.  They are GIVEN a tiny inertial rather than deleted.

       Deleting them was the obvious fix and it is wrong. Those eight are the
       `calflower` links: the lower shin, and the foot hangs off the end of
       them. Drop the link and the joint that references it and the foot
       re-attaches higher up, so the robot is standing on a leg shorter than the
       one any Go2 policy was ever trained on -- which is invisible until you
       put a trained policy on it and it crouches instead of standing. A gram
       and a 1e-6 inertia keeps the chain, keeps the geometry, and is small
       enough not to matter dynamically.
    2. Collada visuals.  Chrono reads meshes with tiny_obj, so a .dae is fed to
       a Wavefront parser, fails, and then segfaults.  The visual meshes are
       dropped and the collision primitives are drawn instead -- this URDF
       describes itself in 5 boxes, 17 cylinders and 5 spheres, which is blocky
       but complete, and it is the physics we are here to push on anyway.
    """
    import re, os
    src = open(path).read()
    out = src
    TINY = ('<inertial><origin xyz="0 0 0" rpy="0 0 0"/>'
            '<mass value="0.001"/>'
            '<inertia ixx="1e-6" ixy="0" ixz="0" iyy="1e-6" iyz="0" izz="1e-6"/>'
            '</inertial>')
    drop = []
    for block in re.findall(r"<link\b.*?</link>", src, re.S):
        name = re.search(r'name="([^"]+)"', block).group(1)
        if "<inertial" not in block:
            drop.append(name)
            fixed = block.replace("</link>", TINY + "</link>")
            out = out.replace(block, fixed)
    # Collada visuals: Chrono reads every mesh with tiny_obj, so a .dae reaches a
    # Wavefront parser and segfaults. If an .obj of the same name has been
    # converted next door, point at that; otherwise drop the visual and fall back
    # to drawing the collision primitives.
    base_dir = os.path.dirname(os.path.abspath(path))
    swapped = dropped_meshes = 0
    for vis_block in re.findall(r"<visual>.*?</visual>", out, re.S):
        fn = re.search(r'filename="([^"]+)"', vis_block)
        if not fn or fn.group(1).lower().endswith(".obj"):
            continue
        stem = os.path.splitext(os.path.basename(fn.group(1)))[0]
        obj_rel = f"../obj/{stem}.obj"
        if os.path.exists(os.path.normpath(os.path.join(base_dir, obj_rel))):
            out = out.replace(vis_block, vis_block.replace(fn.group(1), obj_rel))
            swapped += 1
        else:
            out = out.replace(vis_block, "")
            dropped_meshes += 1
    meshes = dropped_meshes
    safe = os.path.join(os.path.dirname(path), "_chrono_safe.urdf")
    open(safe, "w").write(out)
    if drop:
        print(f"[urdf] gave {len(drop)} inertia-less links a token inertial "
              f"so the chain survives ({drop[0]}, ...)")
    if swapped:
        print(f"[urdf] using {swapped} converted .obj visual meshes")
    if meshes:
        print(f"[urdf] dropped {meshes} meshes with no .obj beside them; "
              f"drawing collision shapes for those")
    return safe


# -----------------------------------------------------------------------------
# The loop: the same shape as every other part of this tutorial
# -----------------------------------------------------------------------------
SCENES = {
    "go2": scene_go2,
    "arm": scene_arm,                                   # hand-guided
    "arm-limp": lambda sysm: scene_arm(sysm, actuated=False),
    "place": scene_place,
}


def main(mode, headless_script=None, use_udp=False):
    system = chrono.ChSystemNSC()
    system.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
    system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
    system.SetSleepingAllowed(False)     # a resting body would sleep through the spring
    # The default NSC solver is PSOR at 50 iterations, which cannot resolve a
    # robot's worth of motor constraints AND its foot contacts in the same step.
    # Friction loses, and the thing creeps across the floor as though it were
    # ice. These are the settings tutorial_HIL_driver.py already uses on vehicles
    # for the same reason.
    system.SetSolverType(chrono.ChSolver.Type_BARZILAIBORWEIN)
    system.GetSolver().AsIterative().SetMaxIterations(200)

    grabbable, chase, hint, anchor = SCENES[mode](system)
    ap = anchor.GetPos()
    cam_t = [ap.x, ap.y, ap.z]
    cam_az, cam_r, cam_h = [0.55], [1.75], [chase * 0.8]   # orbit, distance, height
    kinematic = (mode == "place")
    grabber = None if kinematic else Grabber(system)

    title = f"PART 9: {mode} - reach into the scene"
    vis = irr.ChVisualSystemIrrlicht()
    vis.AttachSystem(system)
    vis.SetCameraVertical(chrono.CameraVerticalDir_Z)   # the world is Z-up
    vis.SetWindowTitle(title)
    vis.SetWindowSize(1280, 800)
    vis.Initialize()
    vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
    vis.AddTypicalLights()
    vis.AddSkyBox()
    vis.AddCamera(chrono.ChVector3d(chase * 1.6, -chase * 2.0, chase * 1.1),
                  chrono.ChVector3d(0, 0, 0.3))
    # AddCamera builds an RTSCamera, which grabs the mouse for orbit/pan/zoom --
    # so a drag moved the body AND swung the view, and the follow code below was
    # fighting it for the camera every frame. The mouse belongs to manipulation
    # here; the camera follows the subject on its own. RTSCamera::OnEvent returns
    # immediately once its input receiver is off.
    vis.GetActiveCamera().setInputReceiverEnabled(False)

    if headless_script is not None:
        console = None
    elif use_udp:
        console = Console()
    else:
        try:
            console = DirectInput(vis, title, 1280, 800)
        except Exception as exc:                      # not macOS, or no pyobjc
            print(f"[input] OS input unavailable ({exc}); falling back to a local panel")
            console = LocalInput()
    sel = 0
    held = False
    lift = 0.0          # ] / [ toggle the handle moving up / down in Z
    plane_angle = 0.0
    grab_point = None
    grab_normal = None
    seen_packet = False
    system.DoStepDynamics(STEP)          # the collision system must exist to raycast

    print(f"\n{hint}")
    print("  MOUSE on the 3D view: press to grab, drag to pull, release to drop\n"
          "  arrows move   [ ] up/down   Z grab   X select   T log   C reset\n"
          "  Q/E while dragging: rotate the drag plane - this is the depth control\n"
          "  camera (mouse is not used for it): A/D orbit   W/S zoom   R/F height\n")

    # PART 1, applied here. Without it this loop steps as fast as the machine
    # allows -- about fifty times real time on this Mac -- so a 1.2 m/s handle
    # covers 60 m/s of scene, the placement box is gone before you see it, and a
    # passive arm looks like it exploded. Everything downstream of this was being
    # tuned against a clock running fifty times too fast.
    rt_timer = chrono.ChRealtimeStepTimer()
    render_every = max(1, int(round(1.0 / (RENDER_FPS * STEP))))
    fired = set()
    n = 0
    t0 = time.perf_counter()
    break_out = False
    while vis.Run() and not break_out:
        t = system.GetChTime()
        if headless_script is not None:
            if t > headless_script["until"]:
                break
            s, th, br = headless_script["inputs"](t)
            cmds = [c for (at, c) in headless_script["commands"] if at <= t and (at, c) not in fired]
            fired.update((at, c) for (at, c) in headless_script["commands"] if at <= t)
        else:
            s, th, br = console.poll()
            cmds = console.take_commands()
            if not seen_packet and console.addr is not None:
                seen_packet = True
                if use_udp:
                    print(f"[udp] first packet from {console.addr[0]} - input is getting through")

        for c in cmds:
            if c == "n":
                sel = (sel + 1) % len(grabbable)
                print(f"[select] {grabbable[sel].GetName()}")
            elif c == "f":
                if kinematic:
                    pass
                elif held:
                    grabber.release(); held = False; print("[release]")
                else:
                    body = grabbable[sel]
                    grabber.grab(body, body.GetPos()); held = True
                    print(f"[grab] {body.GetName()}")
            elif c == "m":
                b = grabbable[sel]
                p, q = b.GetPos(), b.GetRot()
                yaw = math.degrees(math.atan2(2*(q.e0*q.e3 + q.e1*q.e2),
                                              1 - 2*(q.e2*q.e2 + q.e3*q.e3)))
                line = f"[pose] {b.GetName()}  x={p.x:+.3f} y={p.y:+.3f} z={p.z:+.3f} yaw={yaw:+.1f}deg"
                print(line)
                log = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   f"placement_{mode}.log")
                with open(log, "a") as fh:
                    fh.write(f"{t:8.3f}  {line}\n")
                print(f"        -> {log}")
            elif c == "u":
                lift = +1.0 if lift <= 0.0 else 0.0
                print(f"[lift] {'up' if lift > 0 else 'off'}")
            elif c == "d":
                lift = -1.0 if lift >= 0.0 else 0.0
                print(f"[lift] {'down' if lift < 0 else 'off'}")
            elif c == "q":
                print("[quit]")
                break_out = True
            elif c == "r":
                if not kinematic and held:
                    grabber.release(); held = False
                print("[reset]")

        # Mouse straight on the 3D window: press to pick what is under the
        # cursor, drag to pull it, release to let go.
        if isinstance(console, DirectInput) and not kinematic:
            down = console.mouse_down()
            at = console.cursor_pixel()
            if down and not console.prev_mouse and at is not None:
                r = console.ray_through(*at)
                if r:
                    got = pick_along_ray(system, r[0], r[1])
                    if got and got[0] not in grabbable:
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
                        got = pick_near_ray(grabbable, r[0], d0 / d0.Length())
                    if got:
                        body, point, normal = got
                        # `is` compares Python proxies, and CastToChBody mints a
                        # fresh one per call, so it never matched and this guard
                        # did nothing. SWIG's __eq__ compares the C++ pointer.
                        if grabber.handle is None or body != grabber.handle:
                            grabber.grab(body, point)
                            held = True
                            plane_angle = 0.0
                            fwd = r[1] - r[0]
                            fwd = fwd / fwd.Length()
                            grabber.set_plane(point, normal, fwd, plane_angle)
                            grab_normal = normal
                            grab_point = point
                            print(f"[mouse] grabbed {body.GetName()}")
            elif down and held and at is not None:
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
                    plane_angle = max(-1.2, min(1.2, plane_angle + spin * 1.5 * STEP))
                    cf = console.vis.GetActiveCamera()
                    cp, ct = cf.getAbsolutePosition(), cf.getTarget()
                    fwd = chrono.ChVector3d(ct.X - cp.X, ct.Y - cp.Y, ct.Z - cp.Z)
                    fwd = fwd / fwd.Length()
                    grabber.set_plane(grabber.body.GetPos(), grab_normal, fwd, plane_angle)
                r = console.ray_through(*at)
                if r:
                    d = (r[1] - r[0])
                    d = d / d.Length()
                    target = grabber.plane_point(r[0], d)
                    if target is not None:
                        # A near-parallel plane puts the intersection a very long
                        # way off; letting the handle jump there stretches the
                        # spring into a launch.
                        here = grabber.body.GetPos()
                        off = target - here
                        far = off.Length()
                        if far > GRAB_REACH:
                            target = here + off * (GRAB_REACH / far)
                        grabber.handle.SetPos(target)
            elif (not down) and console.prev_mouse and held:
                grabber.release(); held = False
                print("[mouse] released")
            console.prev_mouse = down

        dx = (th - br) * HANDLE_SPEED * STEP
        dy = s * HANDLE_SPEED * STEP
        dz = lift * HANDLE_SPEED * STEP
        if kinematic:
            b = grabbable[sel]
            p = b.GetPos()
            b.SetPos(chrono.ChVector3d(p.x + dx, p.y + dy, p.z + dz))
        elif held and not (isinstance(console, DirectInput) and console.prev_mouse):
            grabber.move(dx, dy, dz)

        if n % render_every == 0:
            # Keep the selected body in frame; there is no user camera control,
            # because PyChrono cannot read this window's mouse or keyboard.
            # Follow the scene's anchor, not the selected part. Chasing the
            # selection made the whole world appear to slide whenever a limb
            # moved or the selection changed.
            a = anchor.GetPos()
            cam_t[0] += (a.x - cam_t[0]) * 0.08
            cam_t[1] += (a.y - cam_t[1]) * 0.08
            cam_t[2] += (a.z - cam_t[2]) * 0.08
            look = chrono.ChVector3d(*cam_t)
            if console is not None and hasattr(console, "camera_nudge"):
                orb, zoom, rise = console.camera_nudge()
                cam_az[0] += orb * 1.4 * render_every * STEP
                cam_r[0] = max(0.25, cam_r[0] * (1.0 + zoom * 1.2 * render_every * STEP))
                cam_h[0] = max(0.05, cam_h[0] + rise * 1.2 * render_every * STEP * chase)
            d = chase * cam_r[0]
            vis.UpdateCamera(chrono.ChVector3d(look.x + d * math.sin(cam_az[0]),
                                               look.y - d * math.cos(cam_az[0]),
                                               look.z + cam_h[0]), look)
            if grabber is not None:
                grabber.draw_link()
            vis.BeginScene(); vis.Render(); vis.EndScene()
            if console is not None:
                b = grabbable[sel]
                bp = b.GetPos()
                f = grabber.force() if (grabber and held) else 0.0
                if isinstance(console, LocalInput):
                    console.draw([
                        f"mode   {mode}      t {t:6.2f} s",
                        f"sel    {b.GetName()}",
                        f"state  {'HELD  spring %.0f N' % f if held else ('kinematic' if kinematic else 'not grabbed - press Z')}",
                        f"pos    x {bp.x:+7.3f}  y {bp.y:+7.3f}  z {bp.z:+7.3f}",
                        f"in     steer {s:+.2f}  thr {th:.2f}  brk {br:.2f}  lift {lift:+.0f}",
                        "arrows move   [ ] up/down   Z grab   X select   T log   C reset",
                    ])
                elif n % (render_every * 10) == 0:
                    console.send(f"{t:.3f},{bp.x:.3f},{f:.3f},{bp.z:.3f},{s:.3f},{th:.3f},{br:.3f},"
                                 f"{'HELD' if held else b.GetName()[:8]}")
        FreeDriveJoint.guiding = held
        for h in getattr(system, "stance_holders", ()):
            h.update()
        system.DoStepDynamics(STEP)
        n += 1
        if headless_script is None:
            rt_timer.Spin(STEP)      # hold the loop to wall-clock speed

    if headless_script and headless_script.get("shot"):
        vis.BeginScene(); vis.Render(); vis.EndScene()
        vis.WriteImageToFile(headless_script["shot"])
    return system, grabbable


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    use_udp = "--udp" in sys.argv
    mode = args[0] if args else "arm"
    if mode not in SCENES:
        raise SystemExit(
            f"usage: python hil_manipulate.py [{' | '.join(SCENES)}] [--udp]\n"
            "  default: an input window opens alongside the 3D view, one command, one process\n"
            "  --udp:   take input from operator_console.py in a second terminal instead")
    if mode == "go2":
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        GO2_URDF = os.environ.get("GO2_URDF",
                                  os.path.join(here, "go2_assets/urdf/go2.urdf"))
        if not os.path.exists(GO2_URDF):
            raise SystemExit(
                f"Go2 URDF not found at {GO2_URDF}.\n"
                "  git clone https://github.com/wty-yy/go2_rl_gym\n"
                "  export GO2_URDF=go2_rl_gym/resources/robots/go2/urdf/go2.urdf")
        globals()["GO2_URDF"] = GO2_URDF
    main(mode, use_udp=use_udp)
