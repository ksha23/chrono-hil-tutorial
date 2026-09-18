"""Can a person actually perturb every part they can see?

    python tests_parts.py go2
    python tests_parts.py arm

This is the regression that keeps coming back, in three different disguises: a
name whitelist that missed a link, a mass-scaled spring too weak to move a 40 g
foot, and a gripper with no controller at all. Each time, every other test
passed.

IT MEASURES ROTATION AS WELL AS TRANSLATION, because measuring only the centre
of mass says "stuck" for a link that is doing exactly what it should. The
Panda's first link sits 4 cm from its own yaw axis: pull it and the joint turns
18 degrees while the centre of mass travels 12 mm. That is not a stuck link,
that is a shoulder.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chronohil.scenes as scenes
from chronohil import GRAB_REACH, Grabber, STEP, chrono
from chronohil.controllers import FreeDriveJoint

SCENE = sys.argv[1] if len(sys.argv) > 1 else "go2"
MOVED_MM = 30.0        # a part that shifts this far has plainly responded
TURNED_DEG = 3.0       # ...or turned this far, which counts just as much


def build():
    s = chrono.ChSystemNSC()
    s.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
    s.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
    s.SetSleepingAllowed(False)
    s.SetSolverType(chrono.ChSolver.Type_BARZILAIBORWEIN)
    s.GetSolver().AsIterative().SetMaxIterations(600)
    fn = scenes.scene_go2 if SCENE == "go2" else scenes.scene_arm
    grabbable = fn(s)[0]
    for _ in range(int(2.0 / STEP)):
        for h in s.stance_holders:
            h.update()
        s.DoStepDynamics(STEP)
    return s, grabbable


def angle_of(body):
    q = body.GetRot()
    return 2.0 * math.acos(max(-1.0, min(1.0, q.e0)))


names = [b.GetName() for b in build()[1]]
print(f"{'body':20s} {'mass kg':>8s} {'moved mm':>9s} {'turned deg':>11s}   verdict")
bad = []
for name in names:
    s, _ = build()
    tgt = [b for b in s.GetBodies() if b.GetName() == name][0]
    p = tgt.GetPos()
    start, a0 = (p.x, p.y, p.z), angle_of(tgt)
    grab = Grabber(s)
    grab.grab(tgt, tgt.GetPos())
    for i in range(int(2.5 / STEP)):
        t = i * STEP
        want = chrono.ChVector3d(start[0] + min(GRAB_REACH, 0.30 * t), start[1],
                                 start[2] + min(GRAB_REACH, 0.20 * t))
        here = grab.body.GetPos()
        off = want - here
        if off.Length() > GRAB_REACH:
            want = here + off * (GRAB_REACH / off.Length())
        grab.handle.SetPos(want)
        FreeDriveJoint.guiding = True      # the demo sets this while you hold
        for h in s.stance_holders:
            h.update()
        s.DoStepDynamics(STEP)
    q = tgt.GetPos()
    moved = math.sqrt(sum((a - b) ** 2 for a, b in
                          zip((q.x, q.y, q.z), start))) * 1000.0
    turned = math.degrees(abs(angle_of(tgt) - a0))
    ok = moved > MOVED_MM or turned > TURNED_DEG
    if not ok:
        bad.append(name)
    print(f"{name:20s} {tgt.GetMass():8.3f} {moved:9.1f} {turned:11.1f}   "
          f"{'ok' if ok else 'UNRESPONSIVE'}")

print(f"\n{SCENE}: {len(names) - len(bad)}/{len(names)} parts respond to a drag")
if bad:
    print("UNRESPONSIVE:", bad)
sys.exit(1 if bad else 0)
