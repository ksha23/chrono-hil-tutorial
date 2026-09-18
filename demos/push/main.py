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
"""DEMO 4: how hard can you shove it.

    python demos/push/main.py                         click, aim, SPACE to fire
    python demos/push/main.py --headless --mag 300 --dir 1,0,0
    python demos/push/main.py --headless --sweep 1700:1950:50 --dir 1,0,0 --fresh

A freehand drag cannot answer "how hard can I shove it", because no two drags
are the same. So the person keeps the parts where judgement helps -- where on
the body, and in which direction -- and the magnitude is scripted:

    impulse J = F * dt      a constant force, held for a fixed window

Both are printed and logged, so a result is reproducible by someone else.

  rig.py     the push, the recovery test, and the headless sweep
  panel.py   the window with the sliders
  this file  argument parsing and the interactive loop
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import pychrono.irrlicht as irr

# Logs go beside the repository, not inside the demo folder.
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chronohil as H
import chronohil.scenes as _scenes
from chronohil import chrono

from demos.push.panel import PushInput, PushMarker, PushPanel
from demos.push.rig import (DUR_MAX, MAG_MAX, PushConfig, PushRig, RENDER_FPS, SETTLE,
                  STEP, WARMUP, angles_from_unit, base_state, cold_rig,
                  evaluate, log_record, print_trace, run_headless, run_sweep,
                  snapshot, summarize, unit_from_angles, write_trace)

def run_interactive(args):
    rig = PushRig(urdf=args.urdf, z_tol=args.z_tol, up_tol=args.up_tol,
                  timeout=args.timeout)
    rig.cfg.magnitude = args.mag
    rig.cfg.duration = args.dur
    rig.cfg.set_direction(*parse_dir(args.dir))
    marker = PushMarker(rig.system)

    title = "PART 10: push test - click the robot, then SPACE"
    vis = irr.ChVisualSystemIrrlicht()
    vis.AttachSystem(rig.system)
    vis.SetCameraVertical(chrono.CameraVerticalDir_Z)      # or the world is sideways
    vis.SetWindowTitle(title)
    vis.SetWindowSize(1280, 800)
    vis.Initialize()
    vis.AddLogo(chrono.GetChronoDataFile("logo_chrono_alpha.png"))
    vis.AddTypicalLights()
    vis.AddSkyBox()
    chase = rig.chase
    vis.AddCamera(chrono.ChVector3d(chase * 1.6, -chase * 2.0, chase * 1.1),
                  chrono.ChVector3d(0, 0, 0.3))
    # AddCamera builds an RTSCamera that eats the mouse for orbit/pan/zoom, so a
    # click meant for the robot would swing the view instead.
    vis.GetActiveCamera().setInputReceiverEnabled(False)

    try:
        console = PushInput(vis, title, 1280, 800)
    except Exception as exc:
        print(f"[input] OS input unavailable ({exc}); the panel keys still work")
        console = None
    panel = None
    if not args.no_panel:
        try:
            panel = PushPanel()
        except Exception as exc:
            print(f"[panel] pygame panel unavailable ({exc}); use the keys")

    print(f"\n[rig] Go2 from URDF, {rig.mass:.2f} kg. Settling for {SETTLE:.1f} s...")
    rig.settle()
    z, up, spd = rig.standing()
    print(f"[rig] standing: base z {z:.4f} m, uprightness {up:.4f}")
    print("\n  click ON the robot to set where the push lands\n"
          "  SPACE fire   X reset   C point back to the base COM   T log a line\n"
          "  left/right azimuth   up/down elevation   [ ] magnitude\n"
          "  camera: A/D orbit   W/S zoom   R/F height\n"
          f"  log: {args.log}\n")

    cam_t = [0.0, 0.0, 0.3]
    cam_az, cam_r, cam_h = [0.55], [1.75], [chase * 0.8]
    render_every = max(1, int(round(1.0 / (RENDER_FPS * STEP))))
    sample_every = max(1, int(round(0.01 / STEP)))
    status = "ARMED"
    n = 0
    running = True
    # The scripted hook, the same shape as hil_manipulate.main's headless_script:
    # the demo can fire itself at a fixed time and quit at another, so the whole
    # windowed path can be exercised without a person in front of it.
    t0 = rig.t()
    auto_fired = False

    while running and vis.Run():
        t = rig.t()
        if args.auto_push is not None and not auto_fired and t - t0 >= args.auto_push:
            rig.fire()
            status = "PUSHING"
            auto_fired = True
        if args.seconds and t - t0 >= args.seconds:
            break
        cmds = []
        if console is not None:
            console.poll()
            cmds += console.take_commands()
        if panel is not None:
            cmds += panel.pump(rig.cfg)

        # held keys: aim and magnitude, from the 3D window
        if console is not None:
            daz, del_, dmag = console.aim_nudge()
            if daz or del_ or dmag:
                rig.cfg.azimuth = max(-180.0, min(180.0,
                                                  rig.cfg.azimuth + daz * 60.0 * STEP))
                rig.cfg.elevation = max(-90.0, min(90.0,
                                                   rig.cfg.elevation + del_ * 60.0 * STEP))
                rig.cfg.magnitude = max(0.0, min(MAG_MAX,
                                                 rig.cfg.magnitude + dmag * 150.0 * STEP))

        for c in cmds:
            if c == "quit":
                running = False
            elif c == "fire":
                if rig.monitor.busy():
                    print("[push] still resolving the last one; X resets")
                else:
                    rig.fire()
                    status = "PUSHING"
            elif c == "reset":
                rig.reset()
                rig.monitor.reset()
                status = "ARMED"
                print("[reset] back to the standing pose")
            elif c == "clear":
                rig.cfg.set_point(rig.base, rig.base.GetPos())
                print("[point] back to the base COM")
            elif c == "log":
                z, up, spd = rig.standing()
                print(f"[state] t {t:7.3f}  z {z:.4f}  upright {up:.4f}  "
                      f"speed {spd:.3f}")
            elif c.startswith("ax"):
                ax = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0),
                      "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}[c[2:]]
                rig.cfg.set_direction(*ax)

        # Click on the 3D view picks the application point.  cursor_pixel()
        # returns None when the cursor is outside that window, which keeps most
        # panel clicks from being read as picks -- but only while the two
        # windows do not overlap.  Stack the panel over the 3D view and both
        # rects contain the cursor, so a slider drag also fired a pick and
        # printed "nothing clickable" at the person adjusting a slider.  The
        # panel is the one in front, so it wins.
        if console is not None:
            over_panel = (panel is not None and panel.os is not None
                          and panel.os.pos() is not None)
            down = console.mouse_down()
            at = console.cursor_pixel()
            if down and not console.prev_mouse and at is not None and not over_panel:
                r = console.ray_through(*at)
                got = H.pick_along_ray(rig.system, r[0], r[1]) if r else None
                if got and not got[0].IsFixed():
                    body, point, normal = got
                    rig.cfg.set_point(body, point)
                    print(f"[point] {body.GetName()} at "
                          f"({point.x:+.3f},{point.y:+.3f},{point.z:+.3f})")
                else:
                    # Worth saying out loud, because the reason for a miss is
                    # usually not "you missed": raycasting goes against COLLISION
                    # geometry, so a link with collision disabled is invisible to
                    # the click no matter how solid it looks.  scene_go2 now
                    # enables every link, so a miss here really is a miss.
                    print("[point] nothing clickable under the cursor")
            console.prev_mouse = down

        rig.step()
        n += 1

        if n % sample_every == 0 and rig.monitor.busy():
            done = rig.sample()
            if done is not None:
                log_record(args.log, done)
                rec = ("did not recover" if done["recovery_s"] is None
                       else f"recovered in {done['recovery_s']:.2f} s")
                status = f"{done['verdict']}  {rec}"
            elif rig.monitor.record:
                status = rig.monitor.record["verdict"]

        if n % render_every == 0:
            a = rig.base.GetPos()
            cam_t[0] += (a.x - cam_t[0]) * 0.08
            cam_t[1] += (a.y - cam_t[1]) * 0.08
            cam_t[2] += (a.z - cam_t[2]) * 0.08
            if console is not None:
                orb, zoom, rise = console.camera_nudge()
                cam_az[0] += orb * 1.4 * render_every * STEP
                cam_r[0] = max(0.25, cam_r[0] * (1.0 + zoom * 1.2 * render_every * STEP))
                cam_h[0] = max(0.05, cam_h[0] + rise * 1.2 * render_every * STEP * chase)
            look = chrono.ChVector3d(*cam_t)
            d = chase * cam_r[0]
            vis.UpdateCamera(chrono.ChVector3d(look.x + d * math.sin(cam_az[0]),
                                               look.y - d * math.cos(cam_az[0]),
                                               look.z + cam_h[0]), look)
            marker.update(rig.cfg, rig.pusher.active is not None)
            vis.BeginScene(); vis.Render(); vis.EndScene()
            if panel is not None:
                panel.draw(rig.cfg, status, rig.standing(), rig.records)

    if args.shot:
        marker.update(rig.cfg, False)
        vis.BeginScene(); vis.Render(); vis.EndScene()
        vis.WriteImageToFile(args.shot)
        print(f"[shot] {args.shot}")
    if panel is not None:
        panel.close()
    print(f"\n{len(rig.records)} push(es) this session; log at {args.log}")
    return rig


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def parse_dir(text):
    """'1,0,0' or 'az=30,el=-10' or '+y'."""
    text = (text or "1,0,0").strip().lower()
    presets = {"+x": (1, 0, 0), "x": (1, 0, 0), "-x": (-1, 0, 0),
               "+y": (0, 1, 0), "y": (0, 1, 0), "-y": (0, -1, 0),
               "+z": (0, 0, 1), "z": (0, 0, 1), "-z": (0, 0, -1)}
    if text in presets:
        return presets[text]
    if "=" in text:
        kv = dict(p.split("=") for p in text.split(","))
        return unit_from_angles(float(kv.get("az", 0.0)), float(kv.get("el", 0.0)))
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 3:
        raise SystemExit(f"--dir wants x,y,z or az=..,el=.. or +x; got {text!r}")
    return tuple(parts)


def parse_point(text):
    if not text:
        return None
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 3:
        raise SystemExit(f"--point wants x,y,z; got {text!r}")
    return tuple(parts)


def build_parser():
    p = argparse.ArgumentParser(
        description="PART 10: configurable impulse pushes on a quadruped, "
                    "with a recovery metric.")
    p.add_argument("--headless", action="store_true",
                   help="no windows: fire one scripted push and print the trace")
    p.add_argument("--sweep", metavar="LO:HI:STEP",
                   help="headless magnitude sweep, e.g. 60:420:60")
    p.add_argument("--trials", type=int, default=1,
                   help="sweep: repeats per magnitude, reported as a pass rate")
    p.add_argument("--fresh", action="store_true",
                   help="rebuild the robot for every trial: slower, but the "
                        "trials are then actually independent (see evaluate)")
    p.add_argument("--refine", action="store_true",
                   help="bisect between the last recovery and the first failure")
    p.add_argument("--refine-steps", type=int, default=5)
    p.add_argument("--refine-tol", type=float, default=10.0, help="N")
    p.add_argument("--full", action="store_true",
                   help="sweep the whole range instead of stopping at the first fall")
    p.add_argument("--mag", type=float, default=150.0, help="N")
    p.add_argument("--dur", type=float, default=0.05, help="s")
    p.add_argument("--dir", default="1,0,0",
                   help="x,y,z or az=30,el=-10 or +y. A leading minus needs "
                        "the equals form: --dir=-1,0,0")
    p.add_argument("--point", default=None,
                   help="world x,y,z for the application point (headless). "
                        "Same rule: --point=-0.06,0,0.27")
    p.add_argument("--repeat", type=int, default=1,
                   help="headless: fire the same push N times, resetting between")
    p.add_argument("--watch", type=float, default=3.0,
                   help="s to keep tracing after the verdict (headless)")
    p.add_argument("--trace", default=None, help="CSV of the recovery trace")
    p.add_argument("--log", default=os.path.join(HERE, "push_log.csv"))
    p.add_argument("--no-panel", action="store_true",
                   help="interactive without the pygame panel (keys only)")
    p.add_argument("--seconds", type=float, default=0.0,
                   help="interactive: quit after this many sim seconds (0 = never)")
    p.add_argument("--auto-push", type=float, default=None,
                   help="interactive: fire the configured push at this sim time")
    p.add_argument("--shot", default=None,
                   help="interactive: write a PNG of the last frame")
    p.add_argument("--urdf", default=None)
    p.add_argument("--z-tol", type=float, default=0.04,
                   help="m, base height band that counts as recovered")
    p.add_argument("--up-tol", type=float, default=0.90,
                   help="body z-axis . world z that counts as upright")
    p.add_argument("--timeout", type=float, default=6.0,
                   help="s to wait for a recovery before calling it a failure")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.sweep:
        run_sweep(args)
        return

    if args.headless:
        rig = PushRig(urdf=args.urdf, z_tol=args.z_tol, up_tol=args.up_tol,
                      timeout=args.timeout)
        rig.settle()
        print(f"\n[rig] Go2 from URDF, {rig.mass:.2f} kg total")
        direction = parse_dir(args.dir)
        point = parse_point(args.point)
        got = []
        for i in range(args.repeat):
            if i:
                rig.reset()
            print(f"\n--- push {i+1}/{args.repeat} ---")
            r = run_headless(rig, args.mag, direction, args.dur, point=point,
                             trace_path=args.trace if i == 0 else None,
                             log_path=args.log, max_wait=args.timeout + 1.0,
                             watch=args.watch)
            print_trace(rig.monitor.trace, until=max(args.watch, 2.0))
            print(f"  verdict {r['verdict']}   "
                  f"impulse {r['impulse_Ns']:.2f} N.s   "
                  f"peak dz {r['peak_dz']*100:.1f} cm   "
                  f"min upright {r['min_upright']:.3f}   "
                  f"peak drift {r['peak_drift_m']*100:.1f} cm   "
                  + ("recovery n/a" if r["recovery_s"] is None
                     else f"recovery {r['recovery_s']:.2f} s"))
            got.append(r)
        if len(got) > 1:
            print(f"\nrepeatability over {len(got)} identical pushes "
                  "(the band to quote, not the single number):")
            verdicts = {r["verdict"] for r in got}
            for key, label, scale, unit in (
                    ("peak_dz", "peak dz", 100.0, "cm"),
                    ("min_upright", "min upright", 1.0, ""),
                    ("peak_drift_m", "peak drift", 100.0, "cm"),
                    ("drift_m", "final drift", 100.0, "cm"),
                    ("recovery_s", "recovery", 1.0, "s")):
                vals = [r[key] * scale for r in got if r[key] is not None]
                if not vals:
                    continue
                print(f"  {label:<12} {min(vals):7.3f} .. {max(vals):7.3f} {unit}"
                      f"   spread {max(vals)-min(vals):.3f}")
            print(f"  verdict      {'/'.join(sorted(verdicts))}"
                  f"{'   <-- NOT STABLE, this magnitude is on the edge' if len(verdicts) > 1 else ''}")
        print(f"\n[log] {args.log}")
        return

    run_interactive(args)


if __name__ == "__main__":
    main()
