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
import os
import socket
import sys
import time

import pychrono as chrono
import pychrono.irrlicht as irr

UDP_PORT = 9870
STEP = 2e-3
RENDER_FPS = 50
HANDLE_SPEED = 1.2        # m/s at full stick
SPRING_K = 4000.0
SPRING_C = 120.0


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
         "q": 12, "e": 14}
    EDGE = {"z": "f", "x": "n", "c": "r", "t": "m", "rbracket": "u", "lbracket": "d"}

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
        n = surf_n
        ln = n.Length()
        n = n / ln if ln > 1e-9 else chrono.ChVector3d(0, 0, 1)
        # At angle 0 the plane should face the camera as squarely as it can while
        # still containing the surface normal, so take the component of the view
        # direction perpendicular to n. (Using n x cam_fwd instead leaves the
        # plane edge-on to the camera, and the cursor ray never meets it.)
        dot_fn = cam_fwd.x * n.x + cam_fwd.y * n.y + cam_fwd.z * n.z
        base = cam_fwd - n * dot_fn
        if base.Length() < 1e-6:
            base = n.Cross(chrono.ChVector3d(0, 0, 1))
        if base.Length() < 1e-6:
            base = n.Cross(chrono.ChVector3d(1, 0, 0))
        base = base / base.Length()
        # rotate that about the surface normal: base and n x base are orthonormal
        pn = base * math.cos(angle) + n.Cross(base) * math.sin(angle)
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
        self.spring = chrono.ChLinkTSDA()
        self.spring.Initialize(self.handle, body, False, point, point)
        self.spring.SetRestLength(0.0)
        self.spring.SetSpringCoefficient(SPRING_K)
        self.spring.SetDampingCoefficient(SPRING_C)
        self.system.AddLink(self.spring)

    def release(self):
        if self.spring is not None:
            self.system.RemoveLink(self.spring)
            self.spring = None
        self.body = None

    def held(self):
        return self.spring is not None

    def move(self, dx, dy, dz):
        p = self.handle.GetPos()
        self.handle.SetPos(chrono.ChVector3d(p.x + dx, p.y + dy, p.z + dz))

    def force(self):
        return abs(self.spring.GetForce()) if self.spring else 0.0


# -----------------------------------------------------------------------------
# Scenes
# -----------------------------------------------------------------------------
def ground_plane(system, size=20.0):
    mat = chrono.ChContactMaterialNSC()
    mat.SetFriction(0.8)
    g = chrono.ChBodyEasyBox(size, size, 1.0, 1000, True, True, mat)
    g.SetPos(chrono.ChVector3d(0, 0, -0.5))
    g.SetFixed(True)
    g.GetVisualShape(0).SetTexture(chrono.GetChronoDataFile("textures/concrete.jpg"), 8, 8)
    system.AddBody(g)
    return g


def scene_go2(system):
    """A real Unitree Go2 from URDF, its joints holding a stance while you pull a leg."""
    import pychrono.parsers as parsers
    urdf = make_chrono_safe_urdf(GO2_URDF)
    ground_plane(system)
    p = parsers.ChParserURDF(urdf)
    if "../obj/" not in open(urdf).read():
        p.EnableCollisionVisualization()   # no real visuals survived; draw the shapes
    # Without this the parsed bodies get no contact material and the robot falls
    # straight through the floor -- silently, since nothing warns about it.
    feet = chrono.ChContactMaterialData()
    feet.mu = 0.8
    feet.cr = 0.0
    p.SetDefaultContactMaterial(feet)
    p.SetAllJointsActuationType(parsers.ChParserURDF.ActuationType_POSITION)
    p.SetRootInitPose(chrono.ChFramed(chrono.ChVector3d(0, 0, 0.36), chrono.QUNIT))
    p.PopulateSystem(system)

    # ChParserURDF builds collision models but leaves collision DISABLED on every
    # body, so the robot falls through the floor without a word. Turn it on for the
    # feet only: enabling it everywhere makes adjacent links collide with each
    # other and the robot tears itself apart.
    for b in system.GetBodies():
        if b.GetName().endswith("_foot"):
            b.EnableCollision(True)

    # A stance, held by the joint motors. This stands in for a locomotion policy:
    # the point of the demo is that something is actively holding a pose while a
    # human pulls on it, not which controller is doing the holding.
    STANCE = {"hip": 0.0, "thigh": 0.9, "calf": -1.8}
    for leg in ("FL", "FR", "RL", "RR"):
        for joint, angle in STANCE.items():
            m = p.GetChMotor(f"{leg}_{joint}_joint")
            if m:
                m.SetMotorFunction(chrono.ChFunctionConst(angle))
    grabbable = [b for b in system.GetBodies()
                 if any(k in b.GetName() for k in ("calf", "thigh", "foot", "base"))]
    base = [b for b in system.GetBodies() if b.GetName() == "base"][0]
    return (grabbable, 0.9,
            "drag a leg; the joint motors fight you and pull it back", base)


def scene_arm(system):
    """A passive serial arm: no motors at all, so it moves only because you move it."""
    ground_plane(system, 10.0)
    mat = chrono.ChContactMaterialNSC()
    prev = chrono.ChBodyEasyCylinder(chrono.ChAxis_Z, 0.12, 0.20, 2000, True, False, mat)
    prev.SetPos(chrono.ChVector3d(0, 0, 0.10))
    prev.SetFixed(True)
    system.AddBody(prev)
    z = 0.20
    grabbable = []
    for i, length in enumerate((0.45, 0.40, 0.30)):
        link = chrono.ChBodyEasyBox(0.09, 0.09, length, 800, True, True, mat)
        link.SetPos(chrono.ChVector3d(0, 0, z + length / 2))
        link.SetName(f"link{i+1}")
        system.AddBody(link)
        joint = chrono.ChLinkLockRevolute()
        axis = chrono.QuatFromAngleX(math.pi / 2) if i % 2 == 0 else chrono.QuatFromAngleY(math.pi / 2)
        joint.Initialize(prev, link, chrono.ChFramed(chrono.ChVector3d(0, 0, z), axis))
        system.AddLink(joint)
        prev, z = link, z + length
        grabbable.append(link)
    return (grabbable, 1.4,
            "no motors anywhere: the arm is limp and moves only where you put it",
            grabbable[0])


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
    return ([body], 3.0,
            "kinematic placement: pose is set directly, and T logs it", body)


GO2_URDF = None          # filled in by main() from --urdf or the default path


def make_chrono_safe_urdf(path):
    """Two things in a stock Go2 URDF that Chrono cannot take.

    1. Links with no <inertial>.  The Go2 has eight, collision-only cylinders
       bolted to the calves, and the parser SEGFAULTS on them rather than
       complaining.  Dropped here, along with the joints that reference them.
    2. Collada visuals.  Chrono reads meshes with tiny_obj, so a .dae is fed to
       a Wavefront parser, fails, and then segfaults.  The visual meshes are
       dropped and the collision primitives are drawn instead -- this URDF
       describes itself in 5 boxes, 17 cylinders and 5 spheres, which is blocky
       but complete, and it is the physics we are here to push on anyway.
    """
    import re, os
    src = open(path).read()
    out = src
    drop = []
    for block in re.findall(r"<link\b.*?</link>", src, re.S):
        name = re.search(r'name="([^"]+)"', block).group(1)
        if "<inertial" not in block:
            drop.append(name)
            out = out.replace(block, "")
    for joint in re.findall(r"<joint\b.*?</joint>", out, re.S):
        if any(f'"{d}"' in joint for d in drop):
            out = out.replace(joint, "")
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
        print(f"[urdf] dropped {len(drop)} inertia-less links Chrono segfaults on ({drop[0]}, ...)")
    if swapped:
        print(f"[urdf] using {swapped} converted .obj visual meshes")
    if meshes:
        print(f"[urdf] dropped {meshes} meshes with no .obj beside them; "
              f"drawing collision shapes for those")
    return safe


# -----------------------------------------------------------------------------
# The loop: the same shape as every other part of this tutorial
# -----------------------------------------------------------------------------
SCENES = {"go2": scene_go2, "arm": scene_arm, "place": scene_place}


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

    render_every = max(1, int(round(1.0 / (RENDER_FPS * STEP))))
    fired = set()
    n = 0
    t0 = time.perf_counter()
    while vis.Run():
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
                    if got:
                        body, point, normal = got
                        if body is not grabber.handle:
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
                    plane_angle = max(-1.2, min(1.2,
                        plane_angle + spin * 1.5 * STEP * render_every))
                    cf = console.vis.GetActiveCamera()
                    cp, ct = cf.getAbsolutePosition(), cf.getTarget()
                    fwd = chrono.ChVector3d(ct.X - cp.X, ct.Y - cp.Y, ct.Z - cp.Z)
                    fwd = fwd / fwd.Length()
                    grabber.set_plane(grab_point, grab_normal, fwd, plane_angle)
                r = console.ray_through(*at)
                if r:
                    d = (r[1] - r[0])
                    d = d / d.Length()
                    target = grabber.plane_point(r[0], d)
                    if target is not None:
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
        system.DoStepDynamics(STEP)
        n += 1

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
