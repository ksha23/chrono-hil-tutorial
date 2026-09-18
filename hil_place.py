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
# PART 10: scene layout by hand -- the reason "reach into the scene" is useful.
#
# PART 9 (hil_manipulate.py) drags a body with a spring so that a controller has
# to fight back.  That is a robustness test.  This is the other half of the same
# capability and it is the one people actually reach for every day:
#
#     "put the truck HERE, the pallets THERE, and tell me the numbers"
#
# Every simulation study starts with a scene, and a scene starts as coordinates
# somebody typed into a config file.  Typing them is miserable: you guess, run,
# look, edit, run again.  A top-down view where you drag the objects and read the
# x,y straight off replaces that loop entirely.  The COORDINATE READOUT is the
# deliverable here, not the picture; T writes every pose to a file you can paste
# into the config that the real run will load.
#
#     conda run -n chrono1187 python hil_place.py
#
# WHY TOP-DOWN MAKES THIS EASY.  The hard part of click-and-drag in 3D is depth:
# a pixel names a ray, not a point, so something has to decide how far along the
# ray the object goes.  PART 9 solves it with a tilted drag plane you rotate with
# two keys, which works but has to be explained.  Looking down at a ground plane
# there is nothing to decide: the object keeps the z it already has, so the drag
# plane is z = const with normal (0,0,1), the cursor ray always meets it, and the
# intersection is one division.  Placement is a 2D problem and this is the view
# that admits it.
#
# WHY THE OBJECTS ARE KINEMATIC.  SetFixed(True) and SetPos() outright.  A layout
# tool must put the object exactly where you let go of it.  Simulating the drop
# means it settles, rolls a little, and the number you read is not the number you
# chose -- and then the config you paste does not reproduce the picture you laid
# out.  Physics comes back on in the run that consumes this file.
#
# SIX THINGS THAT COST HOURS ELSEWHERE IN THIS TUTORIAL, PRE-PAID HERE
#   1. ChRealtimeStepTimer is not optional.  Measured on this Mac, the loop costs
#      0.04 to 0.06 s of wall clock per second of simulated time WITH the
#      rendering, so left alone it runs 20x real time or better: a 1 m/s nudge
#      becomes 20 m/s and the object is off the map before you let go of the key.
#      Spin(STEP) once per step pins it to 1.01x.  That, and not the picking, is
#      what was wrong with the first placement demo.
#   2. SetCameraVertical(CameraVerticalDir_Z), or the ground renders as a wall.
#   3. vis.GetCameraPosition() returns (0,0,0).  Ask the Irrlicht node instead:
#      GetActiveCamera().getAbsolutePosition() / .getTarget().
#   4. AddCamera builds an RTSCamera that eats the mouse for orbit and pan, so it
#      fights the drag.  setInputReceiverEnabled(False) turns it off.
#   5. body.GetPos() is a LIVE REFERENCE.  Stash it, move the body, compare, and
#      you have compared a value with itself.  pose_of() copies on the way out.
#   6. The body a raycast returns is a FRESH SWIG proxy, so `hit is my_body` is
#      False for the same C++ object.  Match on SetTag/GetTag instead.
#
# ...and a seventh that is specific to looking straight down: DO NOT.  Irrlicht's
# CCameraSceneNode detects an up-vector parallel to the view direction and fixes
# it by nudging up.X, which silently rotates the whole image 90 degrees away from
# the basis the ray maths assumes.  CAM_TILT leans the camera a few degrees off
# vertical, which costs nothing visually and keeps the two in agreement.  With
# the tilt in place a world point projects to within about one pixel of where
# world_to_pixel() says it will, which is what makes the drag land under the
# cursor instead of near it.
#
# The mouse and keys still come from macOS rather than from Irrlicht, for the
# reason PART 9 documents (SWIG directors are off, so irr::IEventReceiver cannot
# be subclassed from Python).  That machinery is imported, not repeated.
#
# CONTROLS
#   mouse drag   pick the object under the cursor and slide it on the ground
#   Q / E        rotate the selected object about Z
#   arrows       nudge the selected object (up/down = +/-Y, left/right = -/+X)
#   Z            snap-to-grid on / off
#   [ / ]        finer / coarser grid
#   X            cycle the selection
#   T            dump every pose to place_layout.py (and the clipboard)
#   C            reset the layout
#   A/D  R/F     pan the camera in X / in Y
#   W/S          zoom in / out
#   Esc          quit
# =============================================================================

import datetime
import math
import os
import subprocess
import sys
import time

try:
    import pychrono as chrono
except ImportError as exc:
    if "symbol not found" in str(exc) and os.environ.get("DYLD_LIBRARY_PATH"):
        sys.exit(
            "PyChrono failed to load because DYLD_LIBRARY_PATH points somewhere\n"
            "with an older libChrono, so its symbols win over the conda ones:\n"
            f"  DYLD_LIBRARY_PATH={os.environ['DYLD_LIBRARY_PATH']}\n\n"
            "  env -u DYLD_LIBRARY_PATH python " + " ".join(sys.argv) + "\n\n"
            f"(original error: {exc})")
    raise
import pychrono.irrlicht as irr

# PART 9 already owns the awkward parts: reading the OS mouse and keyboard,
# turning a pixel into a world ray, and raycasting the collision system.  None of
# that is reimplemented here.
import hil_manipulate as H

STEP = 2e-3
RENDER_FPS = 50
WIN_W, WIN_H = 1280, 800

CAM_TILT = 0.14      # offset in -Y per metre of height. Never 0: see the header.
CAM_H0 = 22.0        # metres above the ground
CAM_H_MIN, CAM_H_MAX = 4.0, 60.0
PAN_LIMIT = 26.0

GRID_STEPS = (0.10, 0.25, 0.50, 1.00, 2.00)
GRID_DEFAULT = 2      # index into GRID_STEPS -> 0.50 m
YAW_SNAP_DEG = 15.0

NUDGE_SPEED = 1.0     # m/s on the arrow keys
ROT_SPEED = 1.2       # rad/s on Q/E
PAN_SPEED = 0.55      # screen-heights per second
ZOOM_RATE = 0.9       # per second

GROUND_HALF = 32.0
GRID_HALF = 20.0
TAG0 = 1000           # placeable bodies get tags TAG0, TAG0+1, ...; see build_scene


# -----------------------------------------------------------------------------
# Camera maths.  world_to_pixel is the exact inverse of the ray that
# H.DirectInput.ray_through builds, so the two cannot drift apart.
# -----------------------------------------------------------------------------
def camera_basis(vis):
    """(eye, forward, right, up, tan(fov/2), aspect) from the Irrlicht node.

    vis.GetCameraPosition() reports (0,0,0) for a camera made with AddCamera, so
    the node is the only honest source.  `right` and `up` are built exactly the
    way H.DirectInput.ray_through builds them; a render-to-file check against
    Irrlicht's own output puts a projected point within ~1 px of where it lands.
    """
    cam = vis.GetActiveCamera()
    cp, ct = cam.getAbsolutePosition(), cam.getTarget()
    eye = chrono.ChVector3d(cp.X, cp.Y, cp.Z)
    tgt = chrono.ChVector3d(ct.X, ct.Y, ct.Z)
    fwd = tgt - eye
    n = fwd.Length()
    if n < 1e-9:
        return None
    fwd = fwd / n
    right = fwd.Cross(chrono.ChVector3d(0, 0, 1))
    if right.Length() < 1e-6:
        right = chrono.ChVector3d(1, 0, 0)
    right = right / right.Length()
    up = right.Cross(fwd)
    return eye, fwd, right, up, math.tan(cam.getFOV() * 0.5), cam.getAspectRatio()


def world_to_pixel(vis, p, width=WIN_W, height=WIN_H):
    """Where a world point lands in the window, or None if it is behind us."""
    b = camera_basis(vis)
    if b is None:
        return None
    eye, fwd, right, up, tan_v, aspect = b
    v = p - eye
    t = v ^ fwd                      # ^ is the dot product on ChVector3d
    if t <= 1e-6:
        return None
    ndc_x = (v ^ right) / (t * tan_v * aspect)
    ndc_y = (v ^ up) / (t * tan_v)
    return ((ndc_x + 1.0) * 0.5 * width, (1.0 - ndc_y) * 0.5 * height)


def ray_plane_z(origin, far, z):
    """Where a ray meets the horizontal plane at height z.

    This is the whole reason for the top-down view.  The plane normal is (0,0,1),
    so the intersection is one division and it is well conditioned for every
    pixel on screen -- no degenerate grazing angles, no reach clamp, no plane to
    rotate.  Compare Grabber.set_plane / plane_point in PART 9, which exist only
    because an arbitrary view direction has none of those guarantees.
    """
    d = far - origin
    n = d.Length()
    if n < 1e-9:
        return None
    d = d / n
    if abs(d.z) < 1e-6:
        return None                       # looking along the plane
    t = (z - origin.z) / d.z
    if t <= 0:
        return None                       # plane is behind the camera
    return chrono.ChVector3d(origin.x + d.x * t, origin.y + d.y * t, z)


class RayCaster:
    """The pixel-to-ray maths from PART 9, with no OS input attached.

    H.DirectInput.ray_through only needs .vis, .cw and .ch, so borrowing the
    function itself is exact reuse: the interactive path and the headless test
    path run the identical code, which is the point.
    """

    ray_through = H.DirectInput.ray_through

    def __init__(self, vis, width=WIN_W, height=WIN_H):
        self.vis, self.cw, self.ch = vis, width, height


# -----------------------------------------------------------------------------
# The scene.  Distinguishable objects, because "arrange the scene" is only
# meaningful if you can tell the pieces apart from above.
# -----------------------------------------------------------------------------
#     name        kind   dims                     start x,y     colour
SCENE = [
    ("truck",     "box", (4.80, 2.00, 1.90), (  0.0,   0.0), (0.16, 0.38, 0.78)),
    ("trailer",   "box", (6.00, 2.20, 2.40), ( -8.5,   0.0), (0.18, 0.55, 0.45)),
    ("crate",     "box", (1.60, 1.60, 1.60), ( -4.0,   7.0), (0.72, 0.62, 0.28)),
    ("pallet_a",  "box", (1.20, 1.20, 0.20), (  6.0,   4.5), (0.58, 0.42, 0.24)),
    ("pallet_b",  "box", (1.20, 1.20, 0.20), (  6.0,   6.5), (0.58, 0.42, 0.24)),
    ("barrel_a",  "cyl", (0.45, 1.00),       (  3.0,  -6.0), (0.82, 0.22, 0.18)),
    ("barrel_b",  "cyl", (0.45, 1.00),       (  4.4,  -6.8), (0.82, 0.22, 0.18)),
    ("cone_1",    "cyl", (0.30, 0.70),       (  9.0,  -2.0), (0.96, 0.46, 0.04)),
    ("cone_2",    "cyl", (0.30, 0.70),       (  9.0,   0.0), (0.96, 0.46, 0.04)),
    ("cone_3",    "cyl", (0.30, 0.70),       (  9.0,   2.0), (0.96, 0.46, 0.04)),
    ("cone_4",    "cyl", (0.30, 0.70),       ( -9.5,  -5.5), (0.96, 0.46, 0.04)),
]


def add_grid(system, half=GRID_HALF, spacing=2.0):
    """A metre grid drawn on the ground, as visual shapes on one body.

    Reading coordinates off a bare plane is guesswork; with a grid you can see
    "about x=6" before the panel confirms it.  One body carrying many shapes
    rather than many bodies: nothing here needs to be picked or simulated.
    """
    body = chrono.ChBody()
    body.SetFixed(True)
    body.EnableCollision(False)
    body.SetName("grid")
    faint = chrono.ChColor(0.55, 0.57, 0.60)
    axis = chrono.ChColor(0.95, 0.95, 0.35)
    n = int(half / spacing)
    for i in range(-n, n + 1):
        v = i * spacing
        major = (i == 0)
        for lx, ly, px, py in ((2 * half, 0.04, 0.0, v), (0.04, 2 * half, v, 0.0)):
            s = chrono.ChVisualShapeBox(lx, ly, 0.02)
            s.SetColor(axis if major else faint)
            body.AddVisualShape(s, chrono.ChFramed(
                chrono.ChVector3d(px, py, 0.012), chrono.QUNIT))
    system.AddBody(body)
    return body


def build_scene(system):
    """Ground, grid and the placeable objects.  Everything placeable is FIXED."""
    H.ground_plane(system, GROUND_HALF)
    add_grid(system)
    mat = chrono.ChContactMaterialNSC()
    items = []
    for i, (name, kind, dims, (x, y), col) in enumerate(SCENE):
        if kind == "box":
            sx, sy, sz = dims
            # collide=True: the raycast is how the mouse finds this object, and a
            # body with no collision model is invisible to RayHit.
            b = chrono.ChBodyEasyBox(sx, sy, sz, 600, True, True, mat)
            z = sz * 0.5
            radius = 0.5 * math.hypot(sx, sy)
        else:
            r, h = dims
            b = chrono.ChBodyEasyCylinder(chrono.ChAxis_Z, r, h, 500, True, True, mat)
            z = h * 0.5
            radius = r
        b.SetName(name)
        # A raycast hands back a body through CastToChBody, and SWIG builds a
        # FRESH Python proxy for it every time -- so `hit_body is my_body` is
        # False even when they are the same C++ object, silently, and the pick
        # looks like it found nothing.  Tag the bodies and compare tags.
        b.SetTag(TAG0 + i)
        b.SetFixed(True)              # kinematic: SetPos is the only thing that moves it
        b.SetPos(chrono.ChVector3d(x, y, z))
        b.GetVisualShape(0).SetColor(chrono.ChColor(*col))
        system.AddBody(b)
        items.append({"body": b, "name": name, "tag": TAG0 + i, "z": z,
                      "radius": radius, "colour": col, "home": (x, y, 0.0),
                      "x": x, "y": y, "yaw": 0.0})
    return items


def make_halo(system):
    """A bright disc under whichever object is selected."""
    body = chrono.ChBody()
    body.SetFixed(True)
    body.EnableCollision(False)
    body.SetName("selection halo")
    shape = chrono.ChVisualShapeCylinder(1.5, 0.03)
    shape.SetColor(chrono.ChColor(1.0, 0.92, 0.25))
    body.AddVisualShape(shape)
    system.AddBody(body)
    return body, shape


# -----------------------------------------------------------------------------
# Pose bookkeeping
# -----------------------------------------------------------------------------
def snap_to(v, g):
    return round(v / g) * g


def apply_pose(item, snap, grid):
    """Push the item's logical x,y,yaw onto the body, snapped if snapping is on.

    The logical position is kept separate from the applied one on purpose.  If
    the arrow keys nudged the SNAPPED value it would round straight back to the
    same cell every step and the object would never move; accumulating off-grid
    and snapping only on the way out makes the arrows step cell to cell.
    """
    x, y, yaw = item["x"], item["y"], item["yaw"]
    if snap:
        x, y = snap_to(x, grid), snap_to(y, grid)
        s = math.radians(YAW_SNAP_DEG)
        yaw = snap_to(yaw, s)
    item["body"].SetPos(chrono.ChVector3d(x, y, item["z"]))
    item["body"].SetRot(chrono.QuatFromAngleZ(yaw))


def pose_of(body):
    """(x, y, z, yaw_deg), copied out.

    GetPos() hands back a LIVE REFERENCE into the body.  Stashing it and
    comparing later measures nothing at all, because both sides moved.
    """
    p, q = body.GetPos(), body.GetRot()
    yaw = math.degrees(math.atan2(2 * (q.e0 * q.e3 + q.e1 * q.e2),
                                  1 - 2 * (q.e2 * q.e2 + q.e3 * q.e3)))
    return (p.x, p.y, p.z, yaw)


def readout(items):
    """The deliverable: [(name, x, y, z, yaw_deg)] as the bodies actually are."""
    return [(it["name"],) + pose_of(it["body"]) for it in items]


def layout_text(items, t=None):
    """A block you can paste into a config, which is the whole point of the tool."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    head = f"# hil_place layout  {stamp}"
    if t is not None:
        head += f"  (t = {t:.2f} s)"
    lines = [head, "LAYOUT = [",
             "    # name           x         y         z       yaw_deg"]
    for name, x, y, z, yaw in readout(items):
        lines.append(f'    ("{name}",{" " * max(1, 12 - len(name))}'
                     f'{x:+9.3f}, {y:+9.3f}, {z:+8.3f}, {yaw:+8.1f}),')
    lines.append("]")
    return "\n".join(lines) + "\n"


def dump_layout(items, path, t=None):
    text = layout_text(items, t)
    with open(path, "w") as fh:
        fh.write(text)
    try:                                    # macOS: make it paste-ready as well
        subprocess.run(["pbcopy"], input=text, text=True, timeout=2, check=False)
        clipped = " (and the clipboard)"
    except Exception:
        clipped = ""
    print("\n" + text + f"-> {path}{clipped}\n")
    return text


# -----------------------------------------------------------------------------
# Input.  DirectInput comes from PART 9; ScriptedInput is the same surface fed
# from a table, so the headless tests exercise the real loop and not a copy.
# -----------------------------------------------------------------------------
class ScriptedInput:
    """Same duck type as H.DirectInput, driven by functions of sim time."""

    def __init__(self, script):
        self.script = script
        self.commands = []
        self.fired = set()
        self.prev_mouse = False
        self.addr = ("script", 0)
        self.t = 0.0

    def set_time(self, t):
        self.t = t
        for at, c in self.script.get("commands", ()):
            if at <= t and (at, c) not in self.fired:
                self.fired.add((at, c))
                self.commands.append(c)

    def _mouse(self):
        fn = self.script.get("mouse")
        return fn(self.t) if fn else None

    def mouse_down(self):
        m = self._mouse()
        return bool(m and m[2])

    def cursor_pixel(self):
        m = self._mouse()
        return (m[0], m[1]) if m else None

    def poll(self):
        fn = self.script.get("inputs")
        return fn(self.t) if fn else (0.0, 0.0, 0.0)

    def take_commands(self):
        c, self.commands = self.commands, []
        return c

    def plane_spin(self):
        fn = self.script.get("spin")
        return fn(self.t) if fn else 0.0

    def camera_nudge(self):
        fn = self.script.get("camera")
        return fn(self.t) if fn else (0.0, 0.0, 0.0)

    def send(self, text):
        pass


class Panel:
    """A pygame window that shows every object's x,y live.

    Irrlicht's GUI environment is not usefully wrapped in Python, but pygame and
    Irrlicht coexist in one process (PART 9 relies on the same thing), so the
    readout gets a real window with real text.  It is display only: the keys are
    read from the OS by DirectInput whether this window has focus or not, so you
    can leave the mouse on the 3D view and still type.
    """

    ROW = 19

    def __init__(self, n_rows):
        import pygame
        self.pg = pygame
        pygame.init()
        self.w = 560
        self.h = 96 + self.ROW * n_rows + 52
        self.screen = pygame.display.set_mode((self.w, self.h))
        pygame.display.set_caption("hil_place - coordinates")
        self.font = pygame.font.SysFont("menlo,dejavusansmono,monospace", 13)
        self.bold = pygame.font.SysFont("menlo,dejavusansmono,monospace", 13, bold=True)
        self.last = 0.0

    def pump(self):
        """macOS marks a window that never drains its queue as unresponsive."""
        for ev in self.pg.event.get():
            if ev.type == self.pg.QUIT:
                return False
        return True

    def draw(self, header, rows, sel, footer, min_dt=1.0 / 15):
        now = time.perf_counter()
        if now - self.last < min_dt:
            return
        self.last = now
        pg = self.pg
        sc = self.screen
        sc.fill((16, 17, 21))
        y = 10
        for line in header:
            sc.blit(self.bold.render(line, True, (235, 235, 220)), (12, y))
            y += self.ROW
        y += 4
        sc.blit(self.font.render(
            "     name             x          y          z       yaw",
            True, (120, 130, 145)), (12, y))
        y += self.ROW
        pg.draw.line(sc, (52, 56, 66), (12, y), (self.w - 12, y))
        y += 5
        for i, (name, x, xy, z, yaw, col) in enumerate(rows):
            if i == sel:
                pg.draw.rect(sc, (40, 46, 62), (8, y - 2, self.w - 16, self.ROW))
            pg.draw.rect(sc, tuple(int(255 * c) for c in col), (14, y + 3, 9, 9))
            txt = (f"{'>' if i == sel else ' '} {name:<12s}"
                   f"{x:+10.3f} {xy:+10.3f} {z:+9.3f} {yaw:+8.1f}")
            sc.blit(self.font.render(txt, True,
                                     (245, 245, 235) if i == sel else (198, 200, 205)),
                    (28, y))
            y += self.ROW
        y += 6
        pg.draw.line(sc, (52, 56, 66), (12, y), (self.w - 12, y))
        y += 6
        for line in footer:
            sc.blit(self.font.render(line, True, (135, 145, 160)), (12, y))
            y += self.ROW
        pg.display.flip()


# -----------------------------------------------------------------------------
# The loop
# -----------------------------------------------------------------------------
def main(headless_script=None, use_panel=True, out_path=None):
    system = chrono.ChSystemNSC()
    system.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
    system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
    system.SetSleepingAllowed(False)

    items = build_scene(system)
    by_tag = {it["tag"]: it for it in items}
    halo, halo_shape = make_halo(system)
    if out_path is None:
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "place_layout.py")

    title = "PART 10: place - top-down scene layout"
    vis = irr.ChVisualSystemIrrlicht()
    vis.AttachSystem(system)
    vis.SetCameraVertical(chrono.CameraVerticalDir_Z)      # the world is Z-up
    vis.SetWindowTitle(title)
    vis.SetWindowSize(WIN_W, WIN_H)
    vis.Initialize()
    vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
    vis.AddTypicalLights()
    vis.AddSkyBox()
    cam_t = [0.0, 0.0]
    cam_h = [CAM_H0]
    vis.AddCamera(chrono.ChVector3d(0, -CAM_TILT * CAM_H0, CAM_H0),
                  chrono.ChVector3d(0, 0, 0))
    # AddCamera builds an RTSCamera which claims the mouse for orbit and pan, so
    # every drag would also swing the view.  The mouse belongs to placement here.
    vis.GetActiveCamera().setInputReceiverEnabled(False)

    caster = RayCaster(vis, WIN_W, WIN_H)

    panel = None
    if headless_script is not None:
        console = ScriptedInput(headless_script)
    else:
        try:
            console = H.DirectInput(vis, title, WIN_W, WIN_H)
        except Exception as exc:
            sys.exit(f"[input] OS mouse/keys unavailable ({exc}).\n"
                     "        hil_place needs them: it is a mouse tool.")
        if use_panel:
            try:
                panel = Panel(len(items))
            except Exception as exc:
                print(f"[panel] pygame panel unavailable ({exc}); "
                      "the console readout still works")

    sel = 0
    snap = True
    grid_i = GRID_DEFAULT
    drag = None          # {"item", "off_x", "off_y"} while the mouse holds something
    system.DoStepDynamics(STEP)      # the collision system has to exist to raycast
    for it in items:
        apply_pose(it, snap, GRID_STEPS[grid_i])

    if headless_script is None:
        print("\ndrag the objects into place and read the coordinates off the panel")
        print("  mouse drag  move   Q/E rotate   arrows nudge   Z snap   [ ] grid\n"
              "  X select    T dump poses to place_layout.py    C reset   Esc quit\n"
              "  camera: A/D pan X   R/F pan Y   W/S zoom\n")

    # PART 1, and it is load bearing.  Without it the loop runs ~50x real time, a
    # 1 m/s nudge becomes 50 m/s, and an object leaves the map between frames.
    rt_timer = chrono.ChRealtimeStepTimer()
    render_every = max(1, int(round(1.0 / (RENDER_FPS * STEP))))
    n = 0
    stop = False
    wall0 = time.perf_counter()

    while vis.Run() and not stop:
        t = system.GetChTime()
        setter = getattr(console, "set_time", None)
        if setter:
            setter(t)
            if t > headless_script["until"]:
                break
        s_in, th, br = console.poll()
        grid = GRID_STEPS[grid_i]

        for c in console.take_commands():
            if c == "n":
                sel = (sel + 1) % len(items)
                print(f"[select] {items[sel]['name']}")
            elif c == "f":
                snap = not snap
                for it in items:
                    apply_pose(it, snap, grid)
                print(f"[snap] {'on at %.2f m' % grid if snap else 'off'}")
            elif c == "u":
                grid_i = min(len(GRID_STEPS) - 1, grid_i + 1)
                grid = GRID_STEPS[grid_i]
                for it in items:
                    apply_pose(it, snap, grid)
                print(f"[grid] {grid:.2f} m")
            elif c == "d":
                grid_i = max(0, grid_i - 1)
                grid = GRID_STEPS[grid_i]
                for it in items:
                    apply_pose(it, snap, grid)
                print(f"[grid] {grid:.2f} m")
            elif c == "m":
                dump_layout(items, out_path, t)
            elif c == "r":
                drag = None
                for it in items:
                    it["x"], it["y"], it["yaw"] = it["home"]
                    apply_pose(it, snap, grid)
                print("[reset] layout restored")
            elif c == "q":
                stop = True

        # -- the mouse: press picks, drag slides, release drops -----------------
        down = console.mouse_down()
        at = console.cursor_pixel()
        picked_now = None
        if down and not console.prev_mouse and at is not None:
            r = caster.ray_through(*at)
            if r:
                got = H.pick_along_ray(system, r[0], r[1])
                if got:
                    hit = by_tag.get(got[0].GetTag())    # NOT `is`; see build_scene
                    if hit is not None:
                        sel = items.index(hit)
                        picked_now = hit
                        # Grab where you clicked, not the centre: catching the
                        # corner of the trailer should not teleport its middle
                        # under the cursor.  The cursor ray meets the object's own
                        # z-plane, so the offset is exact rather than projected.
                        g = ray_plane_z(r[0], r[1], hit["z"])
                        if g is not None:
                            drag = {"item": hit,
                                    "off_x": hit["x"] - g.x, "off_y": hit["y"] - g.y}
                            print(f"[pick] {hit['name']}")
        elif down and drag is not None and at is not None:
            r = caster.ray_through(*at)
            if r:
                g = ray_plane_z(r[0], r[1], drag["item"]["z"])
                if g is not None:
                    drag["item"]["x"] = g.x + drag["off_x"]
                    drag["item"]["y"] = g.y + drag["off_y"]
        elif (not down) and console.prev_mouse and drag is not None:
            p = pose_of(drag["item"]["body"])
            print(f"[drop] {drag['item']['name']}  x={p[0]:+.3f}  y={p[1]:+.3f}")
            drag = None
        console.prev_mouse = down

        # -- keys that move the selection --------------------------------------
        it = items[sel]
        spin = console.plane_spin() if hasattr(console, "plane_spin") else 0.0
        if spin:
            it["yaw"] += spin * ROT_SPEED * STEP
        if drag is None:
            # Screen right IS world +X and screen up IS world +Y in this view
            # (verified against the rendered image), so the arrows map straight
            # through with no sign to remember.
            it["x"] += s_in * NUDGE_SPEED * STEP       # right arrow -> +X
            it["y"] += (th - br) * NUDGE_SPEED * STEP  # up arrow    -> +Y
        for j in items:
            apply_pose(j, snap, grid)

        # -- render ------------------------------------------------------------
        if n % render_every == 0:
            if hasattr(console, "camera_nudge"):
                ox, zoom, rise = console.camera_nudge()
                span = cam_h[0] * render_every * STEP * PAN_SPEED
                cam_t[0] = max(-PAN_LIMIT, min(PAN_LIMIT, cam_t[0] + ox * span))
                cam_t[1] = max(-PAN_LIMIT, min(PAN_LIMIT, cam_t[1] + rise * span))
                cam_h[0] = max(CAM_H_MIN, min(CAM_H_MAX, cam_h[0] * (
                    1.0 + zoom * ZOOM_RATE * render_every * STEP)))
            vis.UpdateCamera(
                chrono.ChVector3d(cam_t[0], cam_t[1] - CAM_TILT * cam_h[0], cam_h[0]),
                chrono.ChVector3d(cam_t[0], cam_t[1], 0.0))
            sp = items[sel]["body"].GetPos()
            halo.SetPos(chrono.ChVector3d(sp.x, sp.y, 0.02))
            try:
                halo_shape.GetGeometry().r = items[sel]["radius"] + 0.55
            except Exception:
                pass
            vis.BeginScene(); vis.Render(); vis.EndScene()

            if panel is not None:
                if not panel.pump():
                    stop = True
                rows = [(nm, x, y, z, yaw, items[i]["colour"])
                        for i, (nm, x, y, z, yaw) in enumerate(readout(items))]
                panel.draw(
                    [f"hil_place   t {t:6.2f} s    snap "
                     f"{('ON  %.2f m' % grid) if snap else 'off      '}"
                     f"    cam z {cam_h[0]:4.1f}",
                     f"selected  {items[sel]['name']}"
                     f"{'   [dragging]' if drag else ''}"],
                    rows, sel,
                    ["drag to move   Q/E rotate   arrows nudge   Z snap   [ ] grid",
                     "X select   T dump to place_layout.py   C reset   Esc quit"])

        # Every STEP, not every render frame: a pick is an edge that lives for a
        # single step, so sampling at 50 Hz would see it one time in ten.
        hook = headless_script.get("on_frame") if headless_script else None
        if hook:
            hook({"t": t, "n": n, "items": items, "sel": sel, "drag": drag,
                  "picked": picked_now, "readout": readout(items),
                  "vis": vis, "caster": caster, "cursor": at, "down": down,
                  "snap": snap, "grid": grid, "system": system})

        system.DoStepDynamics(STEP)
        n += 1
        if headless_script is None:
            rt_timer.Spin(STEP)          # hold the loop to wall-clock speed

    wall = time.perf_counter() - wall0
    if headless_script and headless_script.get("shot"):
        vis.BeginScene(); vis.Render(); vis.EndScene()
        vis.WriteImageToFile(headless_script["shot"])
    if headless_script is None:
        dump_layout(items, out_path, system.GetChTime())
    return {"system": system, "items": items, "vis": vis, "caster": caster,
            "readout": readout(items), "sel": sel, "steps": n,
            "wall": wall, "sim": system.GetChTime()}


if __name__ == "__main__":
    main(use_panel="--no-panel" not in sys.argv)
