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
"""DEMO 3: reach into a running simulation and pull on it.

    python demos/manipulate/main.py go2        a quadruped on a locomotion policy
    python demos/manipulate/main.py arm        a Franka holding position
    python demos/manipulate/main.py arm-limp   the same arm, motors off
    python demos/manipulate/main.py place      kinematic placement, no dynamics

Everything this file does is assembled from `chronohil`; the file itself is a
loop. There is no platform-specific code here and there is none in chronohil
either, apart from one optional backend under chronohil/input/window that is
selected for you and never imported by name.
"""

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import pychrono.irrlicht as irr

from chronohil import (FreeDriveJoint, GRAB_REACH, HANDLE_SPEED,
                       LimpJoint, RENDER_FPS, STEP, StanceHolder, chrono,
                       pick_along_ray, pick_at_crosshair, pick_near_ray,
                       require_window, scene_arm, scene_go2, scene_place)
from chronohil.input import Console, LocalInput, open_window_input
from chronohil.watchdog import Watchdog
from demos.manipulate.dragging import Manipulator
import chronohil.scenes as scenes

SCENES = {
    "go2": scene_go2,
    "arm": scene_arm,                                   # hand-guided
    "arm-limp": lambda sysm: scene_arm(sysm, actuated=False),
    "place": scene_place,
}


def main(mode, headless_script=None, use_udp=False, console=None):
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
    drag = Manipulator(system, grabbable, kinematic)
    dog = Watchdog(system, STEP, drag.grabber)

    title = f"PART 9: {mode} - reach into the scene"
    vis = irr.ChVisualSystemIrrlicht()
    vis.SetCameraVertical(chrono.CameraVerticalDir_Z)   # the world is Z-up
    vis.SetWindowTitle(title)
    vis.SetWindowSize(1280, 800)
    # ATTACH AFTER INITIALIZE, so there is a moment to check the window opened.
    # Initialize() both makes the device and binds every attached system's
    # assets to it, and with the scene already attached the binding is what
    # dies first: on a display-less machine the ground plane's texture is
    # loaded through a null video driver and the process segfaults inside
    # Initialize, before any guard could run. Initialize with nothing attached
    # survives, and AttachSystem afterwards binds just the same -- rendered
    # frames from the two orderings are byte-identical on macOS and on Linux.
    vis.Initialize()
    require_window(vis, how="see demos/push/main.py --headless")
    vis.AttachSystem(system)
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

    if console is not None:
        pass            # injected, so the press/drag path can be driven by a test
    elif headless_script is not None:
        console = None
    elif use_udp:
        console = Console()
    else:
        # Returns None when this build cannot read its own 3D window, which is
        # not an error: the local input window covers every platform.
        console = open_window_input(vis, title, 1280, 800) or LocalInput()
    sel = 0
    lift = 0.0          # ] / [ toggle the handle moving up / down in Z
    plane_angle = 0.0
    grab_point = None
    grab_normal = None
    seen_packet = False
    system.DoStepDynamics(STEP)          # the collision system must exist to raycast

    print(f"\n{hint}")
    # Only list the controls this console actually has. The mouse, the drag
    # plane and the camera keys all go through the 3D window, so on a build
    # that cannot read it they are dead letters -- and printing them anyway
    # sent the reader off clicking a window that was never going to answer.
    # The question is what the console can do, not which OS this is.
    if hasattr(console, "ray_through"):
        print("  MOUSE on the 3D view: press to grab, drag to pull, release to drop\n"
              "  arrows move   [ ] up/down   Z grab   X select   T log   C reset\n"
              "  Q/E while dragging: rotate the drag plane - this is the depth control\n"
              "  camera (mouse is not used for it): A/D orbit   W/S zoom   R/F height\n")
    elif console is not None:
        print("  arrows move   [ ] up/down   Z grab   X select   T log   C reset\n"
              "  no mouse picking on this build, so Z grabs whatever X has selected\n")

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
                elif drag.held:
                    drag.release(); print("[release]")
                else:
                    body = grabbable[sel]
                    drag.toggle(body)
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
                if not kinematic and drag.held:
                    drag.release()
                print("[reset]")

        drag.mouse_update(console)

        dx = (th - br) * HANDLE_SPEED * STEP
        dy = s * HANDLE_SPEED * STEP
        dz = lift * HANDLE_SPEED * STEP
        if kinematic:
            b = grabbable[sel]
            p = b.GetPos()
            b.SetPos(chrono.ChVector3d(p.x + dx, p.y + dy, p.z + dz))
        elif drag.held and not (console is not None and hasattr(console, 'ray_through')
                                and console.prev_mouse):
            drag.move(dx, dy, dz)

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
            if not kinematic:
                drag.draw_link()
            vis.BeginScene(); vis.Render(); vis.EndScene()
            if console is not None:
                b = grabbable[sel]
                bp = b.GetPos()
                f = drag.force()
                if isinstance(console, LocalInput):
                    console.draw([
                        f"mode   {mode}      t {t:6.2f} s",
                        f"sel    {b.GetName()}",
                        f"state  {'HELD  spring %.0f N' % f if drag.held else ('kinematic' if kinematic else 'not grabbed - press Z')}",
                        f"pos    x {bp.x:+7.3f}  y {bp.y:+7.3f}  z {bp.z:+7.3f}",
                        f"in     steer {s:+.2f}  thr {th:.2f}  brk {br:.2f}  lift {lift:+.0f}",
                        "arrows move   [ ] up/down   Z grab   X select   T log   C reset",
                    ])
                elif n % (render_every * 10) == 0:
                    console.send(f"{t:.3f},{bp.x:.3f},{f:.3f},{bp.z:.3f},{s:.3f},{th:.3f},{br:.3f},"
                                 f"{'HELD' if drag.held else b.GetName()[:8]}")
        FreeDriveJoint.guiding = drag.held
        dog.sample(drag.held)
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
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__ or "")
        print(f"usage: python hil_manipulate.py [{' | '.join(SCENES)}] [--udp]\n"
              "\n"
              "  go2       a Unitree Go2 held up by a trained locomotion policy.\n"
              "            Drag a leg and it steps to keep its feet.\n"
              "  arm       a Franka Panda with its motors holding position.\n"
              "            Drag a link and it follows your hand, then returns.\n"
              "  arm-limp  the same arm with the motors off: it collapses, and\n"
              "            you pose the dead weight by hand.\n"
              "  place     kinematic placement, no dynamics.\n"
              "\n"
              "  --udp     take input from a second process instead of the\n"
              "            window (see archive/operator_console.py)\n"
              "\n"
              "In the 3D window: drag with the mouse to pull on a link, Q/E turn\n"
              "the drag plane to reach nearer or further, A/D/W/S/R/F move the\n"
              "camera, ESC quits.")
        raise SystemExit(0)
    if mode not in SCENES:
        raise SystemExit(
            f"usage: python hil_manipulate.py [{' | '.join(SCENES)}] [--udp]\n"
            "  default: an input window opens alongside the 3D view, one command, one process\n"
            "  --udp:   take input from operator_console.py in a second terminal instead")
    if mode == "go2":
        import os
        urdf = os.environ.get("GO2_URDF", scenes.GO2_URDF)
        if not os.path.exists(urdf):
            raise SystemExit(f"Go2 URDF not found at {urdf}\n"
                             "  see ASSETS.md; it should be vendored in go2_assets/")
        scenes.GO2_URDF = urdf
    main(mode, use_udp=use_udp)
