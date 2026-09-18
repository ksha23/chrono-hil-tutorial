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
# PART 10: the push test -- a human-specified disturbance you can quote a number for.
#
# PART 9 (hil_manipulate.py) let a person reach in and drag a robot around with
# the mouse.  That is the right tool for "does this thing feel right", and the
# wrong tool for the question people actually ask about a controller:
#
#     "how hard can I shove it before it falls over?"
#
# A freehand drag cannot answer that, because no two drags are the same.  What a
# drag gives you is a spring whose force depends on how fast your hand moved,
# for however long you happened to hold the button.  There is no number at the
# end of it.  So this file keeps the human where they are useful -- choosing
# WHERE on the robot the disturbance lands, and in WHICH direction -- and takes
# the human out of the part that has to be repeatable:
#
#     impulse J = F * dt      a constant force F, held for a fixed window dt
#
# F and dt are both set in a UI and both printed, so "a 180 N push for 50 ms,
# 9.0 N.s, on the left shoulder, pointing +Y" is a thing you can write in a
# report, hand to someone else, and have them reproduce exactly.  Sweep F and
# you get the number that a robustness test exists to produce: the magnitude at
# which the controller stops recovering.
#
# WHAT IS REUSED FROM PART 9 (imported, not copied)
#     H.scene_go2(system)         the real Unitree Go2 from URDF, with a PD
#                                 stance controller standing in for a policy
#     H.pick_along_ray(...)       ChCollisionSystem::RayHit, the click-to-pick
#     H.DirectInput(...)          mouse and keys read from macOS, because
#                                 PyChrono cannot read the Irrlicht window
#     H.ground_plane(system)
#
# HOW THE PUSH IS APPLIED
#     ChBody force accumulators.  AddAccumulator() once per body, then every
#     step inside the window: EmptyAccumulator(i); AccumulateForce(i, F, p,
#     False) with F and p in world coordinates.  Chrono does NOT clear an
#     accumulator for you, so the Empty is not optional -- leave it out and the
#     force ramps linearly with the step count.  Verified against a free body:
#     100 N for 50 ms on 10 kg gives exactly 0.5 m/s.
#
#     Applying at a world POINT rather than at the COM is the whole reason this
#     is interesting.  A push on the shoulder is a force plus a moment, and the
#     moment is what the controller actually has trouble with.
#
# THE UI
#     Two windows, one process.  Irrlicht draws the robot and you click ON it to
#     say where the push lands; a small pygame panel carries the sliders,
#     because the Irrlicht window cannot be read from Python at all (SWIG
#     directors are off, so irr::IEventReceiver cannot be subclassed).  Keys are
#     read from the OS by H.DirectInput and therefore work no matter which of
#     the two windows has focus.
#
# RUNNING IT
#     conda run -n chrono1187 python hil_push.py
#         the interactive demo: click the robot, set direction and magnitude,
#         SPACE to fire, X to reset the robot to its stance.
#
#     conda run -n chrono1187 python hil_push.py --headless --mag 300 --dir 1,0,0
#         one scripted push, no windows, the recovery trace printed as a table.
#         Add --repeat 5 to get the run-to-run band instead of one number.
#
#     conda run -n chrono1187 python hil_push.py --sweep 250:450:25 --fresh --full
#         escalating pushes until the controller loses.  --fresh rebuilds the
#         robot for each trial, which is the only version of this number that
#         reproduces (see evaluate).  This is the deliverable.
#
# WHAT IT MEASURES, on the Go2 with PART 9's PD stance controller (15.02 kg,
# standing at base z 0.2715 m, uprightness 0.9997), pushed at the base COM for
# 50 ms, one cold-start trial per magnitude.  These reproduced digit for digit
# in a separate process:
#
#     forward +X    325 N (16.25 N.s)   recovers: -2.9 cm, up 0.889, back in 1.4 s
#                   330 N (16.50 N.s)   falls:   -20.9 cm, up -1.00, 67 cm away
#     lateral +Y    280 N (14.00 N.s)   recovers: -2.6 cm, up 0.917, back in 1.6 s
#                   290 N (14.50 N.s)   falls:   -20.1 cm, up -0.35, 47 cm away
#
# Two things to take from that.  Sideways is the weak axis by 15 percent, which
# is what a quadruped's support polygon says it should be.  And the failure is a
# CLIFF, not a slope: five newtons separates a 2.9 cm dip from ending upside
# down two thirds of a metre away.  That is a stance controller with no stepping
# reflex, exactly -- once the COM leaves the support polygon there is no
# mechanism left to bring it back, so there is no graceful degradation to see.
#
# WHERE it lands matters as much as how hard.  Same 250 N lateral push, 12.5 N.s
# every time, moved around the torso:
#
#     at the COM          recovers, -1.9 cm, up 0.963
#     15 cm forward       recovers, -1.0 cm, up 0.995     (near a front foot)
#     15 cm back          recovers, -2.0 cm, up 0.967
#     5 cm higher up      FALLS,   -20.1 cm, up -0.351
#
# Five centimetres of moment arm is the difference between a wobble and a fall,
# at an identical impulse.  That is the argument for picking the point by
# clicking on the robot rather than pushing the COM and calling it a test.
#
# WHAT YOU CAN CLICK.  Picking is a raycast against COLLISION geometry, and
# scene_go2 deliberately enables that on the torso and the four feet only: the
# URDF's leg cylinders run the full length of the limb, and with them on the
# robot stands on its shins.  So a click lands anywhere on the torso -- nose,
# tail, either shoulder, which is the moment arm that matters -- and on the
# feet, and a click on a thigh hits nothing and says so.  If PART 9 later grows
# pick-only collision geometry for the legs, this file gets it for free, because
# it imports that scene rather than copying it.
#
# CONTROLS (all work from either window)
#     click on the robot   set the application point (it sticks to that link)
#     SPACE                fire the configured push
#     X                    reset the robot to its stance and re-settle
#     C                    clear the point back to the base COM
#     left/right           azimuth, held, 60 deg/s      T   log a state line
#     up/down              elevation, held, 60 deg/s    [ ] magnitude, 150 N/s
#     A/D orbit   W/S zoom   R/F camera height
# =============================================================================

import argparse
import csv
import math
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
            "  env -u DYLD_LIBRARY_PATH python " + " ".join(sys.argv) + "\n\n"
            f"(original error: {exc})")
    raise

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import hil_manipulate as H            # PART 9: scene, picking, OS input

STEP = 2e-3
RENDER_FPS = 50
SETTLE = 1.5          # s of standing before anything is allowed to fire
MAG_MAX = 800.0       # N, the top of the magnitude slider
DUR_MAX = 0.30        # s, the top of the duration slider


# -----------------------------------------------------------------------------
# State readout: the three numbers that say whether a quadruped is still standing
# -----------------------------------------------------------------------------
# PART 9 learned this the hard way and it is worth repeating here, because it is
# the difference between a robustness test and a robustness test that lies.  The
# obvious metric -- mean joint tracking error -- reads LOW on a robot lying on
# its back, because unloaded legs track their targets beautifully.  Height and
# uprightness cannot be fooled that way.
def base_state(base):
    """(z, uprightness, speed, x, y) of the base. All copied out, never referenced.

    body.GetPos() hands back a LIVE reference into the body, so holding onto one
    and comparing it later measures exactly zero displacement, every time.
    """
    p = base.GetPos()
    v = base.GetPosDt()
    up = base.TransformDirectionLocalToParent(chrono.ChVector3d(0, 0, 1))
    return (float(p.z), float(up.z),
            math.sqrt(float(v.x) ** 2 + float(v.y) ** 2 + float(v.z) ** 2),
            float(p.x), float(p.y))


def unit_from_angles(az_deg, el_deg):
    """Azimuth about +Z (0 deg = +X, 90 deg = +Y), elevation up from horizontal."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    c = math.cos(el)
    return (c * math.cos(az), c * math.sin(az), math.sin(el))


def angles_from_unit(vx, vy, vz):
    n = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
    vx, vy, vz = vx / n, vy / n, vz / n
    return (math.degrees(math.atan2(vy, vx)),
            math.degrees(math.asin(max(-1.0, min(1.0, vz)))))


# -----------------------------------------------------------------------------
# The push itself
# -----------------------------------------------------------------------------
class PushConfig:
    """Direction and magnitude, held separately, exactly as the UI presents them.

    Direction is stored as azimuth/elevation because that is what a person can
    steer with two sliders, and read back out as a unit vector because that is
    what goes in the log.  The application point is stored in the LOCAL frame of
    whatever link was clicked, so it stays glued to that piece of the robot as
    the robot moves; converting to world only happens at the instant of firing.
    """

    def __init__(self, body, azimuth=0.0, elevation=0.0, magnitude=150.0,
                 duration=0.05):
        self.body = body
        self.local_point = chrono.ChVector3d(0, 0, 0)
        self.azimuth = azimuth
        self.elevation = elevation
        self.magnitude = magnitude
        self.duration = duration

    # -- where ---------------------------------------------------------------
    def set_point(self, body, world_point):
        self.body = body
        self.local_point = body.TransformPointParentToLocal(world_point)

    def world_point(self):
        return self.body.TransformPointLocalToParent(self.local_point)

    # -- which way -----------------------------------------------------------
    def direction(self):
        return chrono.ChVector3d(*unit_from_angles(self.azimuth, self.elevation))

    def set_direction(self, vx, vy, vz):
        self.azimuth, self.elevation = angles_from_unit(vx, vy, vz)

    # -- how hard ------------------------------------------------------------
    def force(self):
        return self.direction() * self.magnitude

    def impulse(self):
        """N.s -- the one number that makes two pushes comparable."""
        return self.magnitude * self.duration

    def describe(self):
        d = self.direction()
        p = self.world_point()
        return (f"{self.magnitude:.0f} N for {self.duration*1000:.0f} ms "
                f"= {self.impulse():.2f} N.s  dir ({d.x:+.2f},{d.y:+.2f},{d.z:+.2f}) "
                f"az {self.azimuth:+.0f} el {self.elevation:+.0f}  "
                f"on {self.body.GetName()} at ({p.x:+.3f},{p.y:+.3f},{p.z:+.3f})")


class Pusher:
    """Holds the force on for a fixed window, then takes it off.

    One accumulator per body, created once and reused.  AddAccumulator() appends
    to a list, so calling it per push would leak a slot per push and every stale
    slot would keep contributing whatever was last put in it.
    """

    def __init__(self):
        self._slots = {}
        self.active = None       # (body, world_force, local_point, t_end)
        self.fired_at = None

    def _slot(self, body):
        key = id(body)
        if key not in self._slots:
            self._slots[key] = body.AddAccumulator()
        return self._slots[key]

    def fire(self, cfg, t):
        body = cfg.body
        self.active = (body, cfg.force(), chrono.ChVector3d(cfg.local_point),
                       t + cfg.duration)
        self.fired_at = t
        return self._slot(body)

    def update(self, t):
        """Call every step, BEFORE DoStepDynamics. Returns True while pushing."""
        if self.active is None:
            return False
        body, force, local, t_end = self.active
        idx = self._slot(body)
        body.EmptyAccumulator(idx)            # Chrono never clears these for you
        if t >= t_end:
            self.active = None
            return False
        # The point travels with the link: a shove on the shoulder stays on the
        # shoulder even as the shoulder is being shoved away.
        body.AccumulateForce(idx, force, body.TransformPointLocalToParent(local),
                             False)
        return True

    def cancel(self):
        if self.active is not None:
            body = self.active[0]
            body.EmptyAccumulator(self._slot(body))
            self.active = None


# -----------------------------------------------------------------------------
# Did it recover?
# -----------------------------------------------------------------------------
class RecoveryMonitor:
    """Baseline before the push, deviation after it, and a time to get back.

    "Recovered" is deliberately a sustained condition, not an instant one: the
    base has to be back near its standing height, still upright, and no longer
    moving, and it has to hold all three for HOLD seconds.  A robot that sails
    through the right height on its way to the floor should not count.
    """

    def __init__(self, base, z_tol=0.04, up_tol=0.90, speed_tol=0.20,
                 hold=0.40, timeout=6.0):
        self.base = base
        self.z_tol, self.up_tol, self.speed_tol = z_tol, up_tol, speed_tol
        self.hold, self.timeout = hold, timeout
        self.reset()

    def reset(self):
        self.armed = False
        self.frozen = False
        self.record = None
        self.trace = []
        self.good_since = None

    def arm(self, t, cfg):
        z, up, spd, x, y = base_state(self.base)
        p = cfg.world_point()
        d = cfg.direction()
        self.armed = True
        self.frozen = False
        self.good_since = None
        self.trace = []
        self.record = {
            "t_fire": t,
            "body": cfg.body.GetName(),
            "px": float(p.x), "py": float(p.y), "pz": float(p.z),
            "dx": float(d.x), "dy": float(d.y), "dz": float(d.z),
            "azimuth": cfg.azimuth, "elevation": cfg.elevation,
            "magnitude_N": cfg.magnitude, "duration_s": cfg.duration,
            "impulse_Ns": cfg.impulse(),
            "z0": z, "up0": up, "x0": x, "y0": y,
            "eval_from": t + cfg.duration,
            "peak_dz": 0.0, "min_z": z, "min_upright": up, "peak_speed": 0.0,
            "drift_m": 0.0, "peak_drift_m": 0.0,
            "recovery_s": None, "verdict": "PUSHING",
        }
        return self.record

    def sample(self, t):
        """Call at the trace rate. Returns the record once it has settled."""
        if not self.armed:
            return None
        r = self.record
        z, up, spd, x, y = base_state(self.base)
        dt = t - r["t_fire"]
        drift = math.hypot(x - r["x0"], y - r["y0"])
        # Past the verdict the trace keeps growing but the summary numbers do
        # not, so the reported peak always belongs to the window that was judged.
        if self.frozen:
            self.trace.append((dt, z, up, spd, drift))
            return None
        r["peak_dz"] = max(r["peak_dz"], abs(z - r["z0"]))
        r["min_z"] = min(r["min_z"], z)
        r["min_upright"] = min(r["min_upright"], up)
        r["peak_speed"] = max(r["peak_speed"], spd)
        r["drift_m"] = drift                      # where it ended up
        r["peak_drift_m"] = max(r["peak_drift_m"], drift)   # how far it got
        self.trace.append((dt, z, up, spd, drift))

        if r["verdict"] not in ("PUSHING", "RECOVERING"):
            return None
        if t < r["eval_from"]:
            return None
        r["verdict"] = "RECOVERING"

        good = (abs(z - r["z0"]) <= self.z_tol and up >= self.up_tol
                and spd <= self.speed_tol)
        if good:
            if self.good_since is None:
                self.good_since = t
            elif t - self.good_since >= self.hold:
                r["recovery_s"] = self.good_since - r["t_fire"]
                r["verdict"] = "RECOVERED"
                r["final_z"], r["final_upright"] = z, up
                return r
        else:
            self.good_since = None

        if dt > self.timeout:
            r["verdict"] = "FAILED"
            r["final_z"], r["final_upright"] = z, up
            return r
        return None

    def busy(self):
        return (self.armed and not self.frozen
                and self.record["verdict"] in ("PUSHING", "RECOVERING"))


# -----------------------------------------------------------------------------
# Reset: put every moving body back where it started
# -----------------------------------------------------------------------------
# Repeatability is the entire point of this file, so "run the next push from the
# same initial condition" has to be exact, not approximate.  Snapshotting the
# pose and velocity of every non-fixed body and writing them back is exact; the
# PD stance law is stateless, so there is nothing else to restore.
def snapshot(system):
    return [(b, chrono.ChVector3d(b.GetPos()), chrono.ChQuaterniond(b.GetRot()))
            for b in system.GetBodies() if not b.IsFixed()]


def restore(system, snap):
    zero = chrono.ChVector3d(0, 0, 0)
    for b, pos, rot in snap:
        b.SetPos(chrono.ChVector3d(pos))
        b.SetRot(chrono.ChQuaterniond(rot))
        b.SetPosDt(chrono.ChVector3d(zero))
        b.SetAngVelParent(chrono.ChVector3d(zero))
        b.SetPosDt2(chrono.ChVector3d(zero))
    # Poses and velocities are not all of the state.  The contact container is
    # carrying the contacts from whatever the robot was doing a moment ago, and
    # the NSC solver warm-starts from the impulses cached against them.
    system.GetContactContainer().RemoveAllContacts()
    # There is one more layer of history underneath that this cannot reach.
    # Bullet's persistent manifolds hold the cached impulses, and the only call
    # that would clear them, system.GetCollisionSystem().Clear(), SEGFAULTS: it
    # drops the collision models out of the world and nothing rebinds them.  Do
    # not try it again.  What is left is a residual push-to-push variation of
    # about 10 percent on the deviation metrics, quantified in PushRig.settle.
    system.Update()


# -----------------------------------------------------------------------------
# The rig: system + robot + pusher + monitor, shared by every entry point
# -----------------------------------------------------------------------------
WARMUP = 1        # reset cycles before the first push; see PushRig.settle


class PushRig:
    def __init__(self, urdf=None, z_tol=0.04, up_tol=0.90, timeout=6.0,
                 warmup=WARMUP):
        H.GO2_URDF = urdf or os.environ.get(
            "GO2_URDF", os.path.join(HERE, "go2_assets/urdf/go2.urdf"))
        if not os.path.exists(H.GO2_URDF):
            raise SystemExit(
                f"Go2 URDF not found at {H.GO2_URDF}.\n"
                "  git clone https://github.com/wty-yy/go2_rl_gym\n"
                "  export GO2_URDF=go2_rl_gym/resources/robots/go2/urdf/go2.urdf")

        system = chrono.ChSystemNSC()
        system.SetGravitationalAcceleration(chrono.ChVector3d(0, 0, -9.81))
        system.SetCollisionSystemType(chrono.ChCollisionSystem.Type_BULLET)
        # A body at rest would otherwise sleep straight through the push.
        system.SetSleepingAllowed(False)
        # PSOR at 50 iterations cannot resolve a robot's motor constraints and
        # its foot contacts in the same step; friction loses and the robot skates.
        system.SetSolverType(chrono.ChSolver.Type_BARZILAIBORWEIN)
        system.GetSolver().AsIterative().SetMaxIterations(200)

        self.system = system
        self.warmup = warmup
        self.pickable, self.chase, self.hint, self.base = H.scene_go2(system)
        self.pusher = Pusher()
        self.monitor = RecoveryMonitor(self.base, z_tol=z_tol, up_tol=up_tol,
                                       timeout=timeout)
        self.cfg = PushConfig(self.base)
        self.records = []
        self.mass = sum(b.GetMass() for b in system.GetBodies() if not b.IsFixed())
        # The collision system does not exist until the first step, and
        # pick_along_ray needs it.
        system.DoStepDynamics(STEP)
        self.snap = None

    # -- time --------------------------------------------------------------
    def t(self):
        return self.system.GetChTime()

    def step(self):
        """One physics step, with the push and the stance controller on top."""
        self.pusher.update(self.t())
        for h in getattr(self.system, "stance_holders", ()):
            h.update()
        self.system.DoStepDynamics(STEP)

    def settle(self, seconds=SETTLE, warmup=None):
        """Stand still, take the reference state, then normalise onto it.

        The trailing reset() is not redundant: reset() is restore-then-resettle,
        and resettling from a restored state lands a millimetre or two from the
        raw snapshot, so without a cycle here the FIRST push of a session would
        start from a different pose than every later one.

        HOW REPEATABLE THIS ACTUALLY IS, measured rather than assumed.  Hash
        every non-fixed body's pose and velocity plus every motor angle just
        before firing and it is BIT-IDENTICAL on every push of a session.  The
        outcome still is not.  The same 300 N push comes out as either

            peak dz 2.46 cm   min upright 0.940   recovery 0.94 s
            peak dz 2.16 cm   min upright 0.953   recovery 0.89 s

        and which one you get depends on how many pushes came before.  That
        residual is Bullet's persistent manifolds: they cache the contact
        impulses the NSC solver warm-starts from, they are not part of any state
        Python can see or reset (restore() says why), and they carry a little of
        the last push into the next one.  It is worth about 10 percent on the
        deviation metrics and about 0.05 s on the recovery time.  Away from the
        edge that is cosmetic.  AT the edge it is not: 334 N recovered 2 times
        out of 5 from a bit-identical start.  That is why --sweep takes --trials
        and reports a pass RATE, and why the threshold below is quoted as a band
        rather than a number.  A single-sample bisection down to the newton
        would have been a made-up number, and it looked like a real one.
        """
        warmup = self.warmup if warmup is None else warmup
        if self.snap is None:
            for _ in range(int(round(seconds / STEP))):
                self.step()
            self.snap = snapshot(self.system)
        for _ in range(max(1, warmup)):
            self.reset(resettle=seconds)

    def reset(self, resettle=SETTLE):
        """Back to the standing pose, so the next push starts from the same state."""
        self.pusher.cancel()
        self.monitor.reset()
        if self.snap is not None:
            restore(self.system, self.snap)
        for _ in range(int(round(resettle / STEP))):
            self.step()

    # -- the push ----------------------------------------------------------
    def fire(self):
        self.pusher.fire(self.cfg, self.t())
        rec = self.monitor.arm(self.t(), self.cfg)
        print(f"[push] {self.cfg.describe()}")
        return rec

    def sample(self):
        done = self.monitor.sample(self.t())
        if done is not None:
            self.records.append(done)
            print(f"[{done['verdict'].lower()}] {summarize(done)}")
            self.monitor.frozen = True     # verdict is in; the trace goes on
        return done

    def standing(self):
        z, up, spd, x, y = base_state(self.base)
        return z, up, spd


def summarize(r):
    rec = "n/a" if r["recovery_s"] is None else f"{r['recovery_s']:.2f} s"
    return (f"{r['magnitude_N']:.0f} N / {r['impulse_Ns']:.2f} N.s  "
            f"peak dz {r['peak_dz']*100:.1f} cm  min upright {r['min_upright']:.3f}  "
            f"peak speed {r['peak_speed']:.2f} m/s  "
            f"drift {r['peak_drift_m']*100:.1f} cm peak / {r['drift_m']*100:.1f} cm final  "
            f"recovery {rec}")


LOG_FIELDS = ["t_fire", "body", "px", "py", "pz", "dx", "dy", "dz",
              "azimuth", "elevation", "magnitude_N", "duration_s", "impulse_Ns",
              "z0", "up0", "peak_dz", "min_z", "min_upright", "peak_speed",
              "drift_m", "peak_drift_m", "recovery_s", "verdict"]


def log_record(path, r):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(r)


def write_trace(path, trace):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t_since_push_s", "base_z_m", "uprightness", "speed_mps",
                    "drift_m"])
        for row in trace:
            w.writerow([f"{v:.5f}" for v in row])


# -----------------------------------------------------------------------------
# Headless: scripted pushes, no windows, numbers on stdout
# -----------------------------------------------------------------------------
def run_headless(rig, mag, direction, duration, point=None, trace_path=None,
                 log_path=None, quiet=False, max_wait=8.0, watch=0.0):
    """One push, run to a verdict, then traced for `watch` more seconds."""
    rig.cfg.magnitude = mag
    rig.cfg.duration = duration
    rig.cfg.set_direction(*direction)
    if point is not None:
        rig.cfg.set_point(rig.base, chrono.ChVector3d(*point))

    z, up, spd = rig.standing()
    if not quiet:
        print(f"[pre]  base z {z:.4f} m  uprightness {up:.4f}  speed {spd:.3f} m/s")
    if z < 0.20 or up < 0.8:
        print("[warn] the robot was not standing before the push; result is meaningless")

    rig.fire()
    every = max(1, int(round(0.01 / STEP)))          # 100 Hz trace
    n = 0
    t_end = rig.t() + max_wait
    done = None
    while done is None and rig.t() < t_end:
        rig.step()
        n += 1
        if n % every == 0:
            done = rig.sample()
    if done is None:
        done = rig.monitor.record
        done["verdict"] = "FAILED"
        z, up, _, _, _ = base_state(rig.base)
        done["final_z"], done["final_upright"] = z, up
        rig.monitor.frozen = True
        rig.records.append(done)
        print(f"[failed] {summarize(done)}")
    # Keep watching past the verdict: a recovery that is declared at 0.9 s and
    # then falls over at 2 s is a thing a plot has to be able to show.
    t_watch = done["t_fire"] + watch
    while rig.t() < t_watch:
        rig.step()
        n += 1
        if n % every == 0:
            rig.sample()
    if log_path:
        log_record(log_path, done)
    if trace_path:
        write_trace(trace_path, rig.monitor.trace)
        if not quiet:
            print(f"[trace] {trace_path}")
    return done


def print_trace(trace, step=0.25, until=4.0):
    print(f"    {'t-t_push':>9}  {'base z':>8}  {'upright':>8}  "
          f"{'speed':>7}  {'drift':>7}")
    nxt = 0.0
    for dt, z, up, spd, drift in trace:
        if dt + 1e-9 < nxt or dt > until:
            continue
        print(f"    {dt:9.2f}  {z:8.4f}  {up:8.4f}  {spd:7.3f}  {drift:7.3f}")
        nxt += step


def cold_rig(args, template=None):
    """A brand new rig, built and settled from nothing. The independent sample.

    Building the robot again costs about two seconds, which buys the one thing
    reset() cannot: no shared contact history at all (restore() says why).
    """
    quiet = open(os.devnull, "w")
    keep, sys.stdout = sys.stdout, quiet
    try:
        rig = PushRig(urdf=args.urdf, z_tol=args.z_tol, up_tol=args.up_tol,
                      timeout=args.timeout)
        rig.settle()
    finally:
        sys.stdout = keep
        quiet.close()
    if template is not None:
        # Carry the application point over. It is stored in the base's local
        # frame, so it transfers to the new robot unchanged; a point picked on
        # some other link cannot be, and falls back to the base.
        rig.cfg.local_point = chrono.ChVector3d(template.cfg.local_point)
    return rig


def evaluate(rig, mag, direction, args, point, trials):
    """Fire the same push `trials` times. Returns (n_recovered, trials, records).

    Trials, not one shot.  Right at the edge the same push from a bit-identical
    start goes both ways (PushRig.settle has the measurement), so a single
    sample there is a coin flip dressed up as a measurement.

    AND THE TRIALS HAVE TO BE INDEPENDENT, which by default they are not.  Five
    reset-and-fire trials in one session come back with min_upright equal to
    THREE DECIMAL PLACES -- they are five copies of one sample, because they all
    inherit the same Bullet contact cache.  That makes 5/5 look like strong
    evidence when it is one observation wearing a hat, and it is how a push that
    recovers cleanly from a cold start can read 0/3 in the middle of a sweep.
    --fresh rebuilds the robot for every trial, which is slower and is the only
    version of this number worth quoting to anyone.
    """
    got = []
    for _ in range(trials):
        if getattr(args, "fresh", False):
            use = cold_rig(args, template=rig)
        else:
            use = rig
            use.reset()
        got.append(run_headless(use, mag, direction, args.dur, point=point,
                                log_path=args.log, quiet=True,
                                max_wait=args.timeout + 1.0))
    return sum(1 for r in got if r["verdict"] == "RECOVERED"), trials, got


def sweep_row(mag, dur, n_ok, n, got):
    """One line of the sweep table: the worst trial, plus the pass rate."""
    worst = min(got, key=lambda r: r["min_upright"])
    recs = [r["recovery_s"] for r in got if r["recovery_s"] is not None]
    rec = "   --   " if not recs else (f"{min(recs):6.2f}  " if len(recs) == 1
                                       else f"{min(recs):.2f}-{max(recs):.2f}")
    verdict = ("RECOVERED" if n_ok == n else
               "FAILED" if n_ok == 0 else f"MIXED {n_ok}/{n}")
    print(f"{mag:6.0f} {mag*dur:7.2f} {worst['peak_dz']*100:8.1f}cm "
          f"{worst['min_upright']:8.3f} {worst['peak_drift_m']*100:7.1f}cm "
          f"{rec:>8}  {n_ok}/{n}  {verdict}")


def run_sweep(args):
    """Escalating magnitudes until the controller loses, then squeeze the edge."""
    lo, hi, stepn = (float(v) for v in args.sweep.split(":"))
    rig = PushRig(urdf=args.urdf, z_tol=args.z_tol, up_tol=args.up_tol,
                  timeout=args.timeout)
    rig.settle()
    direction = parse_dir(args.dir)
    point = parse_point(args.point)
    trials = max(1, args.trials)
    print(f"\n[rig] Go2 from URDF, {rig.mass:.2f} kg total, stance PD holding it up")
    z, up, spd = rig.standing()
    print(f"[rig] settled at base z {z:.4f} m, uprightness {up:.4f}\n")
    print(f"sweeping {lo:.0f}:{hi:.0f}:{stepn:.0f} N for {args.dur*1000:.0f} ms, "
          f"{trials} trial(s) each, direction {direction}, "
          f"at {'base COM' if point is None else point}")
    print("(peak dz / min up / drift are the WORST trial at that magnitude)\n")
    header = (f"{'N':>6} {'N.s':>7} {'peak dz':>9} {'min up':>8} {'drift':>8} "
              f"{'recov':>8}  rate  verdict")
    print(header)
    print("-" * len(header))

    results = []
    always_ok, first_loss, always_bad = None, None, None
    mag = lo
    while mag <= hi + 1e-6:
        n_ok, n, got = evaluate(rig, mag, direction, args, point, trials)
        results.extend(got)
        sweep_row(mag, args.dur, n_ok, n, got)
        if n_ok == n and first_loss is None:
            always_ok = mag
        if n_ok < n and first_loss is None:
            first_loss = mag
        if n_ok == 0 and always_bad is None:
            always_bad = mag
            if not args.full:
                break
        mag += stepn

    if first_loss is None:
        print(f"\nno failure up to {hi:.0f} N ({hi*args.dur:.2f} N.s). "
              "raise the top of the sweep.")
        return rig, results, None

    # The bracket to squeeze is [always recovers, always falls], and both ends
    # have to be believed at `trials` samples before the bisection means anything.
    a = always_ok
    b = always_bad if always_bad is not None else first_loss
    if args.refine and a is not None:
        print(f"\nbisecting between {a:.0f} N ({trials}/{trials} recovered) and "
              f"{b:.0f} N (0/{trials} recovered)")
        for _ in range(args.refine_steps):
            if b - a <= args.refine_tol:
                break
            mid = 0.5 * (a + b)
            n_ok, n, got = evaluate(rig, mid, direction, args, point, trials)
            results.extend(got)
            sweep_row(mid, args.dur, n_ok, n, got)
            if n_ok == n:
                a = mid
            elif n_ok == 0:
                b = mid
            else:
                # A mixed result IS the answer: this is the edge, and no amount
                # of further bisection makes it a sharper number.
                print(f"\nRECOVERY THRESHOLD is a BAND, not a number.\n"
                      f"  always recovers  <= {a:.0f} N ({a*args.dur:.2f} N.s)\n"
                      f"  coin flip        at {mid:.0f} N ({mid*args.dur:.2f} N.s), "
                      f"{n_ok}/{n} recovered\n"
                      f"  always falls     >= {b:.0f} N ({b*args.dur:.2f} N.s)")
                if args.log:
                    print(f"[log] {args.log}")
                return rig, results, (a, b)

    ok = ("nothing in this sweep" if a is None
          else f"{a:.0f} N ({a*args.dur:.2f} N.s)")
    print(f"\nRECOVERY THRESHOLD: always recovers at {ok}, "
          f"always falls at {b:.0f} N ({b*args.dur:.2f} N.s)")
    if a is None:
        print("  the bottom of the sweep already failed -- lower --sweep LO")
    if getattr(args, "fresh", False):
        print("  (cold start per trial: deterministic, and reproduced digit for "
              "digit in a separate process)")
    elif trials == 1:
        print("  (one warm trial per magnitude -- rerun with --fresh before "
              "quoting this to anyone; see evaluate() for why --trials alone "
              "is not enough)")
    if args.log:
        print(f"[log] {args.log}")
    return rig, results, (a, b)


# -----------------------------------------------------------------------------
# Input: the PART 9 OS reader, with the keys this demo needs
# -----------------------------------------------------------------------------
class PushInput(H.DirectInput):
    """H.DirectInput with a different keymap.

    Subclassed rather than patched: DirectInput._key and .poll read self.K and
    self.EDGE, so overriding the two class attributes is the whole change, and
    PART 9's own keymap is left alone.
    """

    K = dict(H.DirectInput.K, space=49, x=7, c=8, t=17,
             lbracket=33, rbracket=30)
    EDGE = {"space": "fire", "x": "reset", "c": "clear", "t": "log"}

    def poll(self):
        for name, cmd in self.EDGE.items():
            now = self._key(name)
            if now and not self.prev[name]:
                self.commands.append(cmd)
            self.prev[name] = now
        return (0.0, 0.0, 0.0)

    def aim_nudge(self):
        """(d_azimuth, d_elevation, d_magnitude) from the arrows and brackets."""
        return ((-1.0 if self._key("left") else 0.0) + (1.0 if self._key("right") else 0.0),
                (-1.0 if self._key("down") else 0.0) + (1.0 if self._key("up") else 0.0),
                (-1.0 if self._key("lbracket") else 0.0) + (1.0 if self._key("rbracket") else 0.0))


# -----------------------------------------------------------------------------
# The panel: pygame, because the Irrlicht window cannot be read
# -----------------------------------------------------------------------------
class PushPanel:
    """Direction and magnitude, adjustable and displayed as numbers.

    pygame gets its own window and reads its own events natively, which is the
    only way to have a slider at all here.  It coexists with Irrlicht in one
    process; create it AFTER vis.Initialize() so Irrlicht gets the GL context
    first.
    """

    W, H_ = 430, 640
    BG = (18, 20, 24)
    FG = (226, 230, 236)
    DIM = (128, 136, 148)
    ACC = (255, 140, 40)
    OK = (90, 210, 130)
    BAD = (240, 90, 90)

    def __init__(self):
        import pygame
        self.pg = pygame
        pygame.init()
        pygame.display.set_caption("PART 10: push configurator")
        self.screen = pygame.display.set_mode((self.W, self.H_))
        self.f = pygame.font.SysFont("Menlo, Monaco, monospace", 13)
        self.fb = pygame.font.SysFont("Menlo, Monaco, monospace", 15, bold=True)
        self.drag = None
        self.sliders = []     # filled by draw(), used by the next pump()
        self.buttons = []
        self.commands = []

    # -- widgets -------------------------------------------------------------
    def _slider(self, y, label, value, lo, hi, text, key):
        pg, s = self.pg, self.screen
        x0, w = 14, self.W - 28
        s.blit(self.f.render(label, True, self.DIM), (x0, y))
        s.blit(self.f.render(text, True, self.FG),
               (self.W - 14 - self.f.size(text)[0], y))
        track = pg.Rect(x0, y + 20, w, 8)
        pg.draw.rect(s, (52, 58, 68), track, border_radius=4)
        frac = 0.0 if hi <= lo else max(0.0, min(1.0, (value - lo) / (hi - lo)))
        pg.draw.rect(s, self.ACC, pg.Rect(x0, y + 20, int(w * frac), 8),
                     border_radius=4)
        pg.draw.circle(s, self.FG, (int(x0 + w * frac), y + 24), 7)
        self.sliders.append((pg.Rect(x0 - 8, y + 12, w + 16, 24), key, lo, hi, x0, w))
        return y + 44

    def _buttons(self, y, items):
        pg, s = self.pg, self.screen
        x = 14
        for label, cmd in items:
            w = max(46, self.f.size(label)[0] + 16)
            r = pg.Rect(x, y, w, 24)
            pg.draw.rect(s, (44, 50, 60), r, border_radius=5)
            s.blit(self.f.render(label, True, self.FG),
                   (x + (w - self.f.size(label)[0]) // 2, y + 5))
            self.buttons.append((r, cmd))
            x += w + 6
        return y + 32

    # -- the frame -----------------------------------------------------------
    def draw(self, cfg, status, state, records):
        pg, s = self.pg, self.screen
        self.sliders, self.buttons = [], []
        s.fill(self.BG)
        y = 12
        s.blit(self.fb.render("PUSH CONFIGURATOR", True, self.FG), (14, y))
        y += 26

        d = cfg.direction()
        y = self._slider(y, "azimuth  (deg about +Z, 0 = +X)",
                         cfg.azimuth, -180, 180, f"{cfg.azimuth:+7.1f}", "az")
        y = self._slider(y, "elevation  (deg above horizon)",
                         cfg.elevation, -90, 90, f"{cfg.elevation:+7.1f}", "el")
        txt = f"unit  ({d.x:+.3f}, {d.y:+.3f}, {d.z:+.3f})"
        s.blit(self.f.render(txt, True, self.ACC), (14, y))
        y += 20
        y = self._buttons(y, [("+X", "ax+x"), ("-X", "ax-x"), ("+Y", "ax+y"),
                              ("-Y", "ax-y"), ("+Z", "ax+z"), ("-Z", "ax-z")])
        y += 6

        y = self._slider(y, "magnitude  (N)", cfg.magnitude, 0, MAG_MAX,
                         f"{cfg.magnitude:7.1f} N", "mag")
        y = self._slider(y, "duration  (s)", cfg.duration, 0.01, DUR_MAX,
                         f"{cfg.duration*1000:6.0f} ms", "dur")
        s.blit(self.fb.render(f"impulse  {cfg.impulse():.2f} N.s", True, self.ACC),
               (14, y))
        y += 26

        p = cfg.world_point()
        s.blit(self.f.render("application point  (click the 3D view)", True, self.DIM),
               (14, y))
        y += 18
        s.blit(self.f.render(f"  {cfg.body.GetName()}", True, self.FG), (14, y))
        y += 17
        s.blit(self.f.render(f"  ({p.x:+.3f}, {p.y:+.3f}, {p.z:+.3f}) m", True, self.FG),
               (14, y))
        y += 26

        pg.draw.line(s, (52, 58, 68), (14, y), (self.W - 14, y))
        y += 12
        z, up, spd = state
        col = self.OK if (z > 0.20 and up > 0.8) else self.BAD
        s.blit(self.f.render(f"base height   {z:7.4f} m", True, col), (14, y)); y += 18
        s.blit(self.f.render(f"uprightness   {up:7.4f}", True, col), (14, y)); y += 18
        s.blit(self.f.render(f"base speed    {spd:7.3f} m/s", True, self.FG), (14, y))
        y += 24

        scol = {"RECOVERED": self.OK, "FAILED": self.BAD}.get(status.split()[0], self.ACC)
        s.blit(self.fb.render(status, True, scol), (14, y))
        y += 26
        y = self._buttons(y, [("FIRE  (space)", "fire"), ("RESET  (x)", "reset")])
        y += 6
        for r in records[-4:]:
            rec = "--" if r["recovery_s"] is None else f"{r['recovery_s']:.2f}s"
            line = (f"{r['magnitude_N']:5.0f}N {r['impulse_Ns']:5.2f}Ns "
                    f"up {r['min_upright']:.2f} {r['verdict'][:4]} {rec}")
            s.blit(self.f.render(line, True, self.DIM), (14, y))
            y += 16
        pg.display.flip()

    # -- events --------------------------------------------------------------
    def pump(self, cfg):
        pg = self.pg
        for e in pg.event.get():
            if e.type == pg.QUIT:
                self.commands.append("quit")
            elif e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
                for rect, key, lo, hi, x0, w in self.sliders:
                    if rect.collidepoint(e.pos):
                        self.drag = (key, lo, hi, x0, w)
                        self._set(cfg, e.pos[0])
                        break
                else:
                    for rect, cmd in self.buttons:
                        if rect.collidepoint(e.pos):
                            self.commands.append(cmd)
                            break
            elif e.type == pg.MOUSEBUTTONUP and e.button == 1:
                self.drag = None
            elif e.type == pg.MOUSEMOTION and self.drag:
                self._set(cfg, e.pos[0])
            elif e.type == pg.KEYDOWN:
                if e.key == pg.K_SPACE:
                    self.commands.append("fire")
                elif e.key == pg.K_x:
                    self.commands.append("reset")
                elif e.key == pg.K_c:
                    self.commands.append("clear")
                elif e.key == pg.K_t:
                    self.commands.append("log")
        out, self.commands = self.commands, []
        return out

    def _set(self, cfg, px):
        key, lo, hi, x0, w = self.drag
        frac = max(0.0, min(1.0, (px - x0) / float(w)))
        val = lo + frac * (hi - lo)
        if key == "az":
            cfg.azimuth = round(val, 1)
        elif key == "el":
            cfg.elevation = round(val, 1)
        elif key == "mag":
            cfg.magnitude = round(val, 1)
        elif key == "dur":
            cfg.duration = round(val, 3)

    def close(self):
        try:
            self.pg.quit()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Markers: the point and the arrow, drawn the only way Chrono lets you here
# -----------------------------------------------------------------------------
# pychrono.irrlicht exposes no drawSegment/drawSphere, so a marker is a fixed,
# collision-free body carrying a visual shape, repositioned every frame.  The
# cylinder's height is mutable through GetGeometry().h, which is what makes an
# arrow whose length can track the magnitude.
class PushMarker:
    def __init__(self, system):
        self.dot = chrono.ChBody()
        self.dot.SetFixed(True); self.dot.EnableCollision(False)
        self.dot.SetName("push point")
        sph = chrono.ChVisualShapeSphere(0.025)
        sph.SetColor(chrono.ChColor(1.0, 0.85, 0.1))
        self.dot.AddVisualShape(sph)
        system.AddBody(self.dot)

        self.shaft = chrono.ChVisualShapeCylinder(0.010, 1.0)
        self.shaft.SetColor(chrono.ChColor(1.0, 0.35, 0.05))
        self.arrow = chrono.ChBody()
        self.arrow.SetFixed(True); self.arrow.EnableCollision(False)
        self.arrow.SetName("push arrow")
        self.arrow.AddVisualShape(self.shaft)
        system.AddBody(self.arrow)

    def update(self, cfg, firing):
        p = cfg.world_point()
        d = cfg.direction()
        self.dot.SetPos(p)
        length = 0.10 + 0.40 * min(1.0, cfg.magnitude / MAG_MAX)
        self.shaft.GetGeometry().h = length
        self.shaft.SetColor(chrono.ChColor(1.0, 0.1, 0.05) if firing
                            else chrono.ChColor(1.0, 0.55, 0.1))
        # The arrow sits BEHIND the point and aims at it, so it reads as a shove
        # into the robot rather than a spike coming out of it.
        centre = p - d * (length * 0.5)
        ez = d
        ref = chrono.ChVector3d(0, 0, 1)
        if abs(ez.z) > 0.99:
            ref = chrono.ChVector3d(1, 0, 0)
        ex = ref.Cross(ez); ex = ex / ex.Length()
        ey = ez.Cross(ex)
        rot = chrono.ChMatrix33d()
        rot.SetFromDirectionAxes(ex, ey, ez)
        self.arrow.SetPos(centre)
        self.arrow.SetRot(rot.GetQuaternion())


# -----------------------------------------------------------------------------
# The interactive demo
# -----------------------------------------------------------------------------
def run_interactive(args):
    import pychrono.irrlicht as irr

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
        # returns None when the cursor is outside that window, which is exactly
        # what keeps panel clicks from being read as picks.
        if console is not None:
            down = console.mouse_down()
            at = console.cursor_pixel()
            if down and not console.prev_mouse and at is not None:
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
                    # geometry, and scene_go2 only enables it on the torso and
                    # the four feet (the leg cylinders run the full length of the
                    # limb, so switching them on makes the robot stand on its
                    # shins).  A click on a thigh therefore hits nothing at all.
                    print("[point] nothing clickable under the cursor "
                          "(only the torso and the feet have collision geometry)")
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
