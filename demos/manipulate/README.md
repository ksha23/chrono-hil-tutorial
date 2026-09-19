# Demo 3: reaching into the scene

Click a body in the 3D window and pull on it while its controller keeps
working. The point is not the dragging; it is that something is actively
holding the robot up and has to answer what you do.

```bash
python demos/manipulate/main.py go2        # a quadruped on a trained locomotion policy
python demos/manipulate/main.py arm        # a Franka Panda, motors holding position
python demos/manipulate/main.py arm-limp   # the same arm, motors off
python demos/manipulate/main.py place      # kinematic placement, no dynamics
python demos/manipulate/main.py --help
```

`go2` is the one to open first.

## What to press

**On the 3D view**, where in-window input is available: press to grab, drag to
pull, release to drop. **Q/E while dragging** rotate the drag plane, which is
the depth control -- without it you can swing a leg across the view but never
pull it toward you. **A/D** orbit the camera, **W/S** zoom, **R/F** raise and
lower it. **ESC** quits.

Not every build can read its own 3D window (see `chronohil/input/window/`). On
one that cannot, a small input window opens instead and the demo prints only
the keys that window actually has: **arrows** move the handle, **[ ]** move it
up and down, **Z** grabs whatever **X** has selected, **T** logs a pose,
**C** resets.

## What to look for

- **`go2`**: drag a leg and the policy picks a foot up and steps to keep its
  balance. That is a policy, not a PD: a stance controller can only stiffen.
- **`arm`**: the Panda complies while you hold a link and keeps the pose you
  left it in, which is how a real collaborative arm behaves in hand-guiding
  mode. Let go and it locks.
- **`arm-limp`**: the same arm with nothing holding it up. It collapses, and
  you pose dead weight.
- **The orange line** from the held body to the handle is the spring. Watch its
  length: that is how hard you are pulling.

## Two things that are easy to get wrong

- **A ray sees COLLISION geometry, never visual geometry.** A link you can see
  but whose collision is off is invisible to every click. That accounted for
  every "it will not pick" bug here.
- **The spring's gains must scale with the mass being pulled.** A stiffness
  that feels right on a 134 kg ball is a catapult on a 0.154 kg shin. The
  gains are built from the body's mass as `k = m*w^2` and `c = 2*m*w`, with a
  floor on the mass -- `chronohil/config.py` has the measurements behind both.

## The files here

| | |
|---|---|
| `main.py` | the simulation loop, the camera, and the console readout |
| `dragging.py` | `Manipulator`: what the person has hold of, by mouse or by key |

Everything else comes from `chronohil/` -- the picking, the spring, the
controllers and the scenes. There is no platform-specific code in either file.
