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
# PART 7 support: where the driving happens.
#
# Two scenes, one interface.  `build_scene()` returns the same small record
# whichever one you pick, so the tutorial's simulation loop does not change:
#
#     terrain        a veh.RigidTerrain, already Initialize()d
#     start          a chrono.ChCoordsysd to spawn the plant at
#     name           what to put in the window title
#
#   "flat"   200 x 200 m textured patch.  No download, no assets, runs on
#            anything.  This is what Parts 1-6 have been using all along.
#
#   "mcity"  the Mcity digital twin: a real 32-acre test facility, its road
#            surface driven as a collision mesh and its buildings, poles,
#            signal heads and barriers drawn from a placement manifest.
#
# The Mcity scene is NOT shipped here and is not small.  It is generated from
# the published dataset by the converter in the Chrono tree:
#
#     cd <chrono>/src/demos/vehicle/terrain/mcity
#     python3 -m pip install usd-core
#     ./setup_mcity.sh --repo /path/to/mcity-digital-twin
#
# Point MCITY_DIR at the result (default <chrono data>/mcity).  If it is not
# there, build_scene() says so and falls back to "flat" rather than failing:
# a tutorial that cannot start is worse than one that starts smaller.
#
# =============================================================================

import json
import os

import pychrono as chrono
import pychrono.vehicle as veh


# -----------------------------------------------------------------------------
# Instanced scenery
# -----------------------------------------------------------------------------
#
# A road network describes lanes; it does not describe what the world looks
# like.  Mcity's furniture arrives as ~860 placements drawing on ~230 distinct
# assets, so the thing to avoid is loading the same mesh 40 times.
#
# Chrono's visual model is already built for this: a ChVisualShape is added to a
# body *with a frame*, and the same shape object can be added again at another
# frame.  The mesh is stored once and drawn many times.  That is the whole trick
# below, and it is the same one ChSceneryModel uses on the C++ side.


class SceneryStats:
    """What actually made it into the scene, for the one-line report."""

    def __init__(self):
        self.assets = 0
        self.instances = 0
        self.skipped = 0
        self.missing = 0
        self.triangles = 0

    def __str__(self):
        return (f"{self.instances} placements from {self.assets} meshes "
                f"(~{self.triangles / 1000.0:.0f}k triangles"
                + (f", {self.skipped} skipped" if self.skipped else "")
                + (f", {self.missing} missing" if self.missing else "") + ")")


def load_scenery(system, manifest_file, include_groups=None, max_triangles=0):
    """Add a placement manifest's geometry to `system` as one fixed body.

    include_groups   only these manifest groups (None = all).  Mcity's are
                     "Static", "TrafficPoles", "TrafficLights", "StreetLights",
                     "TrafficLightCables", "Terrain".
    max_triangles    skip any single asset heavier than this (0 = no limit).
                     A blunt but effective way to shed a few very heavy props.

    Returns SceneryStats.  Assets whose mesh file is missing are counted and
    skipped: a partially fetched asset set should still give a usable scene.
    """
    stats = SceneryStats()
    with open(manifest_file) as f:
        manifest = json.load(f)

    root = os.path.dirname(os.path.abspath(manifest_file))

    body = chrono.ChBody()
    body.SetFixed(True)              # scenery is scenery: it never moves
    body.EnableCollision(False)      # and the road surface handles contact
    body.SetName("scenery")

    # asset index -> list of (visual shape, per-asset triangle count), built lazily
    # so that an asset filtered out of every group is never read from disk.
    cache = {}

    def shapes_for(asset_index):
        if asset_index in cache:
            return cache[asset_index]
        asset = manifest["assets"][asset_index]
        shapes, tris = [], 0
        # One asset is several "parts", one per material slot, because a mesh
        # with four materials cannot be one ChVisualShapeTriangleMesh.
        for part in asset.get("parts", []):
            mesh_path = os.path.join(root, part["mesh"])
            if not os.path.exists(mesh_path):
                stats.missing += 1
                continue
            mesh = chrono.ChTriangleMeshConnected().CreateFromWavefrontFile(mesh_path, False, True)
            if mesh is None or mesh.GetNumTriangles() == 0:
                stats.missing += 1
                continue
            shape = chrono.ChVisualShapeTriangleMesh()
            shape.SetMesh(mesh)
            shape.SetName(part.get("name", asset.get("name", "part")))
            shape.SetMutable(False)  # static: lets the backend upload it once

            mat = chrono.ChVisualMaterial()
            c = part.get("colour", [1.0, 1.0, 1.0])
            mat.SetDiffuseColor(chrono.ChColor(c[0], c[1], c[2]))
            ks = part.get("ks", [0.05, 0.05, 0.05])
            mat.SetSpecularColor(chrono.ChColor(ks[0], ks[1], ks[2]))
            for key, setter in (("texture", mat.SetKdTexture),
                                ("normal", mat.SetNormalMapTexture),
                                ("roughness", mat.SetRoughnessTexture),
                                ("metallic", mat.SetMetallicTexture)):
                rel = part.get(key)
                if rel:
                    abs_path = os.path.join(root, rel)
                    if os.path.exists(abs_path):
                        setter(abs_path)
            shape.AddMaterial(mat)

            shapes.append(shape)
            tris += int(part.get("tris", mesh.GetNumTriangles()))
        cache[asset_index] = (shapes, tris)
        if shapes:
            stats.assets += 1
        return cache[asset_index]

    for inst in manifest["instances"]:
        if include_groups is not None and inst.get("group") not in include_groups:
            stats.skipped += 1
            continue
        shapes, tris = shapes_for(inst["asset"])
        if not shapes:
            stats.skipped += 1
            continue
        if max_triangles and tris > max_triangles:
            stats.skipped += 1
            continue

        p = inst["pos"]
        q = inst.get("rot", [1.0, 0.0, 0.0, 0.0])
        frame = chrono.ChFramed(chrono.ChVector3d(p[0], p[1], p[2]),
                                chrono.ChQuaterniond(q[0], q[1], q[2], q[3]))
        for shape in shapes:
            # The SAME shape object, added again at a different frame: this is
            # what keeps 860 placements from costing 860 copies of the geometry.
            body.AddVisualShape(shape, frame)
        stats.instances += 1
        stats.triangles += tris

    system.AddBody(body)
    return stats


# -----------------------------------------------------------------------------
# Scenes
# -----------------------------------------------------------------------------
#
# Two-step, because of an ordering problem that is easy to trip over: the
# vehicle owns the ChSystem, the scene needs that system to add bodies to, and
# the vehicle has to be told where to spawn BEFORE it is initialized.  So the
# spawn pose is resolved first, from files alone, and the geometry is added
# afterwards:
#
#     plan = plan_scene("mcity", 0.5)      # start pose, no system needed
#     ... build the vehicle at plan.start ...
#     plan.build(vehicle.GetSystem())      # terrain and scenery
#
# plan_scene() is also where the fallback happens, so a missing Mcity download
# is reported once, up front, rather than halfway through startup.

# Detail levels, coarsest first.  "ground" is the one to reach for on a laptop:
# it keeps the real road surface and its elevation and draws none of the props.
MCITY_GROUPS = {
    "ground": [],
    "light": ["TrafficPoles", "TrafficLights", "StreetLights"],
    "full": None,  # every group in the manifest
}

# A pose on a real Mcity lane, read once from the published OpenDRIVE network:
# road 29, right-hand lane, facing along the carriageway.
MCITY_START_X = 158.923
MCITY_START_Y = 62.991
MCITY_START_YAW = 1.285431


def _road_material(system):
    """Contact material for the driving surface, in the formulation the system uses.

    ChContactMaterialData describes the surface once and produces the SMC or NSC
    material to match, which matters here because Part 8's plants do not all use
    the same contact method: hand an SMC material to an NSC system and the ground
    ends up with no contact at all, so the plant falls through it.

    Friction 0.9 and restitution 0.01 are the road tuning the Chrono HIL scenes
    use.  The Young's modulus only reaches the SMC formulation, and 2e7 is far
    softer than the default, which a road does not need and which only makes the
    solver work harder.
    """
    minfo = chrono.ChContactMaterialData()
    minfo.mu = 0.9
    minfo.cr = 0.01
    minfo.Y = 2e7
    return minfo.CreateMaterial(system.GetContactMethod())


def _ground_height_near(obj_file, x, y, radius=2.0, default=274.26):
    """Highest ground-mesh vertex within `radius` of (x, y).

    RigidTerrain answers height queries by raycasting the collision system, and
    that system is not built until the first DoStepDynamics.  Asking during setup
    misses, and GetHeight returns its miss value of zero, which on a site whose
    datum is 274 m drops the vehicle out of the world.  Reading the mesh directly
    sidesteps the ordering entirely.
    """
    best = None
    with open(obj_file) as f:
        for line in f:
            if not line.startswith("v "):
                continue
            _, sx, sy, sz = line.split()[:4]
            vx, vy, vz = float(sx), float(sy), float(sz)
            if abs(vx - x) < radius and abs(vy - y) < radius:
                if best is None or vz > best:
                    best = vz
    return best if best is not None else default


class ScenePlan:
    """A resolved scene: where to spawn, and how to build the rest of it later."""

    def __init__(self, kind, name, start, mcity_dir=None, detail=None):
        self.kind = kind
        self.name = name
        self.start = start
        self.mcity_dir = mcity_dir
        self.detail = detail
        self.note = ""

    def build(self, system):
        """Add the terrain (and, for Mcity, the scenery) to `system`.

        Returns the veh.RigidTerrain, already initialized.
        """
        if self.kind == "flat":
            terrain = veh.RigidTerrain(system)
            patch = terrain.AddPatch(_road_material(system), chrono.CSYSNORM, 200.0, 200.0)
            patch.SetTexture(veh.GetVehicleDataFile("terrain/textures/tile4.jpg"), 200, 200)
            patch.SetColor(chrono.ChColor(0.8, 0.8, 0.5))
            terrain.Initialize()
            return terrain

        ground_obj = os.path.join(self.mcity_dir, "mcity_ground.obj")
        manifest = os.path.join(self.mcity_dir, "mcity_scene.json")

        terrain = veh.RigidTerrain(system)
        # The road surface is the drawn geometry, not an analytic plane under it.
        # Mcity also publishes an OpenDRIVE network, and its elevation profile
        # differs from the artist's road mesh by -0.24 to +0.29 m at the 5th and
        # 95th percentiles, which is enough to watch a car float and sink.  Using
        # the mesh for both makes them the same surface by construction.
        #
        # Visualization is on only at "ground" detail, where nothing else would
        # draw the road.  Above that the scenery draws these same triangles, and
        # drawing them twice z-fights.
        draw_ground = (self.detail == "ground")
        terrain.AddPatch(_road_material(system), chrono.CSYSNORM, ground_obj, False, 0, draw_ground)
        terrain.Initialize()

        groups = MCITY_GROUPS[self.detail]
        if groups != []:
            self.note = str(load_scenery(system, manifest, include_groups=groups))
        return terrain


def plan_scene(scene, spawn_height, mcity_dir=None, mcity_detail="light"):
    """Resolve a scene to a spawn pose and a build plan, without a ChSystem.

    scene          "flat" | "mcity"
    spawn_height   how far above the ground the plant should start
    mcity_dir      converted Mcity directory (None = <chrono data>/mcity)
    mcity_detail   "ground" | "light" | "full"

    Falls back to flat terrain, with an explanation, if the Mcity scene was
    asked for but has not been built.  A tutorial that starts smaller is better
    than one that does not start.
    """
    flat = ScenePlan("flat", "flat terrain",
                     chrono.ChCoordsysd(chrono.ChVector3d(0, 0, spawn_height), chrono.QUNIT))

    if scene == "flat":
        return flat
    if scene != "mcity":
        raise ValueError(f"unknown SCENE {scene!r}")
    if mcity_detail not in MCITY_GROUPS:
        raise ValueError(f"unknown MCITY_DETAIL {mcity_detail!r}; "
                         f"pick one of {sorted(MCITY_GROUPS)}")

    if mcity_dir is None:
        mcity_dir = os.path.join(chrono.GetChronoDataPath(), "mcity")
    manifest = os.path.join(mcity_dir, "mcity_scene.json")
    ground_obj = os.path.join(mcity_dir, "mcity_ground.obj")

    if not (os.path.exists(manifest) and os.path.exists(ground_obj)):
        print(f"\n[scene] SCENE = 'mcity', but there is no converted scene in {mcity_dir}")
        print("[scene] The Mcity assets are a third-party dataset, generated rather than shipped:")
        print("[scene]     cd <chrono>/src/demos/vehicle/terrain/mcity")
        print("[scene]     python3 -m pip install usd-core")
        print("[scene]     ./setup_mcity.sh --repo /path/to/mcity-digital-twin")
        print("[scene] Set MCITY_DIR if you built it somewhere else.")
        print("[scene] Falling back to flat terrain.\n")
        return flat

    z = _ground_height_near(ground_obj, MCITY_START_X, MCITY_START_Y)
    start = chrono.ChCoordsysd(
        chrono.ChVector3d(MCITY_START_X, MCITY_START_Y, z + spawn_height),
        chrono.QuatFromAngleZ(MCITY_START_YAW))
    return ScenePlan("mcity", f"Mcity ({mcity_detail})", start, mcity_dir, mcity_detail)
