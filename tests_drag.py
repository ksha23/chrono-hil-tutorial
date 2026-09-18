"""Drive the demo's real press/drag/release code and report where the body went.

    python tests_drag.py arm
    python tests_drag.py go2


The mouse path is what every headless test misses, and it is where the last
three bugs lived. mouse_down() is polled once per physics step, so counting
those calls is a clock that needs nothing from the demo.
"""
import sys, importlib.util
sys.path.insert(0, "/Users/kylesha/chrono-hil-tutorial")
from chronohil.chrono_env import chrono
from chronohil import STEP

MODE = sys.argv[1] if len(sys.argv) > 1 else "arm"


class ScriptedCursor:
    """Presses at 1 s, drags +X by 25 cm, releases at 4 s."""

    def __init__(self):
        self.n = 0
        self.prev_mouse = False
        self.x0 = self.y0 = None

    @property
    def t(self):
        return self.n * STEP

    def mouse_down(self):
        self.n += 1                      # once per physics step
        return 1.0 <= self.t < 4.0

    def cursor_pixel(self):
        return (640, 400)

    def ray_through(self, px, py, reach=60.0):
        x = self.x0 + (min(0.25, 0.14 * (self.t - 1.0)) if self.t >= 1.0 else 0.0)
        return (chrono.ChVector3d(x, self.y0, 3.0),
                chrono.ChVector3d(x, self.y0, -3.0))

    plane_spin = lambda self: 0.0
    camera_nudge = lambda self: (0.0, 0.0, 0.0)
    poll = lambda self: (0.0, 0.0, 0.0)
    take_commands = lambda self: []
    send = lambda self, *a, **k: None
    addr = ("test", 0)


spec = importlib.util.spec_from_file_location(
    "dm", "/Users/kylesha/chrono-hil-tutorial/demos/manipulate/main.py")
dm = importlib.util.module_from_spec(spec)
sys.modules["dm"] = dm
sys.argv = ["main.py", MODE]
try:
    spec.loader.exec_module(dm)
except SystemExit:
    pass

cur = ScriptedCursor()
real = dm.SCENES[MODE]
seen = {}


def wrapped(system, *a, **k):
    out = real(system, *a, **k)
    tgt = max(out[0], key=lambda b: b.GetPos().z)
    p = tgt.GetPos()
    cur.x0, cur.y0 = p.x, p.y
    seen["name"] = tgt.GetName()
    seen["start"] = (p.x, p.y, p.z)
    return out


dm.SCENES = dict(dm.SCENES, **{MODE: wrapped})
system, grabbable = dm.main(MODE, console=cur,
                            headless_script={"until": 6.0,
                                             "inputs": lambda t: (0.0, 0.0, 0.0),
                                             "commands": []})
end = [b for b in system.GetBodies() if b.GetName() == seen["name"]][0].GetPos()
sx, sy, sz = seen["start"]
moved = ((end.x - sx) ** 2 + (end.y - sy) ** 2 + (end.z - sz) ** 2) ** 0.5
print(f"mode={MODE} target={seen['name']}")
print(f"  start ({sx:+.4f},{sy:+.4f},{sz:+.4f})  end ({end.x:+.4f},{end.y:+.4f},{end.z:+.4f})")
print(f"  MOVED {moved:.4f} m  after a scripted 25 cm drag")
