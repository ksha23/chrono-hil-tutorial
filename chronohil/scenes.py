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
"""The scenes the demos put on screen."""

import os

from .chrono_env import chrono
from .config import GRAB_OMEGA
from .controllers import (FreeDriveJoint, LimpJoint, LockedJoint,
                          StanceHolder, joint_readers)
from .policy import Go2Policy, find_go2_policy
from .paths import FRANKA_URDF, GO2_URDF as _GO2_URDF_DEFAULT
from .urdf import make_chrono_safe_urdf

GO2_URDF = _GO2_URDF_DEFAULT

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
            # A policy that catches itself does it with fast, hard joint moves,
            # and the default 200 iterations cannot resolve the resulting
            # contacts: past about 450 N of shove the solver goes non-finite
            # instead of the robot falling over, which reads as "the demo
            # crashed". At 600 it survives to 500 N and the cost is small --
            # 8 s of sim goes from 1.4 s to 4.5 s of wall clock, still comfortably
            # faster than real time. Beyond ~700 N it diverges again; that is a
            # solver limit, not the policy failing, and it should be reported as one.
            it = system.GetSolver().AsIterative()
            if it:
                it.SetMaxIterations(max(600, it.GetMaxIterations()))
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
    urdf = FRANKA_URDF
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
        raw = p.GetChMotor(link.GetName())
        # BOTH kinds. The arm's seven joints are revolute and the gripper's two
        # are prismatic, and casting only to the rotation type skips the fingers
        # entirely -- see joint_readers() for what that looked like on screen.
        m = (chrono.CastToChLinkMotorRotationTorque(raw)
             or chrono.CastToChLinkMotorLinearForce(raw))
        if m:
            fn = chrono.ChFunctionConst(0.0)
            m.SetMotorFunction(fn)
            pos, _ = joint_readers(m)
            # The gripper holds shut in BOTH modes. "Unactuated" is a statement
            # about the seven arm joints, which is what the demo is about; a
            # dead gripper does not slide open and shed its fingers, and this
            # one would, because ChLinkMotorLinear ignores the URDF's travel
            # limits and damping alone does not hold a position.
            prismatic = chrono.CastToChLinkMotorLinearForce(raw) is not None
            # The gripper is LOCKED, not free-driven. FreeDriveJoint's target
            # follows the joint while you are dragging, which is what makes the
            # ARM posable by hand -- and what walked the fingers shut by 16.63 mm
            # over twelve seconds of dragging, monotonically, because the creep
            # never reverses.
            cls = (LockedJoint if prismatic
                   else (FreeDriveJoint if actuated else LimpJoint))
            dampers.append(cls(m, fn, pos()))
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


# GO2_URDF is set at the top from chronohil.paths. It stays overridable so a
# caller can point at another copy of the robot.
