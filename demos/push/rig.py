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
"""The push itself: configure it, fire it, and decide whether it was survived.

No UI in this file. run_headless() and run_sweep() below are the whole demo
without a person, which is how the numbers in the talk were produced.
"""

import copy
import csv
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import chronohil as H
import chronohil.scenes as _scenes
from chronohil import chrono

STEP = 2e-3
RENDER_FPS = 50
SETTLE = 1.5
MAG_MAX = 800.0       # N, the top of the magnitude slider
DUR_MAX = 0.30        # s, the top of the duration slider
WARMUP = 0.0

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


# -- the two argument parsers, here rather than in main.py, because run_sweep
#    below needs them and main.py imports this file, not the other way round ---
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
        # The robot is vendored; chronohil.paths resolves it. HERE used to be
        # the repository root and is now this demo's own folder, so anything
        # built from it points at a directory with no assets in it.
        _scenes.GO2_URDF = urdf or os.environ.get("GO2_URDF", _scenes.GO2_URDF)
        if not os.path.exists(_scenes.GO2_URDF):
            raise SystemExit(f"Go2 URDF not found at {_scenes.GO2_URDF}\n"
                             "  see ASSETS.md; it should be vendored in go2_assets/")

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
