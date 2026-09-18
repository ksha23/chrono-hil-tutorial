# Vendored assets and where they came from

Third-party robot descriptions and one trained policy are committed here so the
demos run straight after a clone. Nothing in these directories is ours.

## `go2_assets/` -- Unitree Go2

| what | source | licence |
|---|---|---|
| `urdf/go2.urdf` and `obj/*.obj` | [`wty-yy/go2_rl_gym`](https://github.com/wty-yy/go2_rl_gym) | MIT |
| `go2_policy.pt` | same repo, `deploy/pre_train/go2/go2_cts_150k.pt` | MIT |

The meshes were `.dae` upstream. Chrono reads every mesh with a Wavefront
parser, so a Collada file reaches it and segfaults; they were converted to
`.obj` with trimesh and the originals are not kept. The URDF still names the
`.dae` files and the loader swaps in the `.obj` beside them.

`go2_policy.pt` is a legged_gym-family actor: 45 observations in, 12 joint
targets out, run at 50 Hz over a PD at the physics rate. It is the unmodified
upstream checkpoint, not fine-tuned.

## `franka_assets/` -- Franka Emika Panda

| what | source | licence |
|---|---|---|
| `panda.urdf`, `meshes/` | `franka_ros`, generated from `panda_arm_hand.urdf.xacro` | Apache-2.0 |
| `panda_chrono.urdf` | the same URDF, sanitised for Chrono's parser | Apache-2.0 |
