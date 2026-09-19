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
# The terrain the driving happens on.
#
# A 200 x 200 m textured patch.  No download, no assets, runs on anything, and
# it is what Demos 1 and 2 drive on.  `plan_scene()` returns a small record:
#
#     start          a chrono.ChCoordsysd to spawn the plant at
#     name           what to put in the window title
#     build(system)  add the terrain, and hand back the veh.RigidTerrain
#
# =============================================================================

import pychrono as chrono
import pychrono.vehicle as veh


def _road_material(system):
    """Contact material for the driving surface, in the formulation the system uses.

    ChContactMaterialData describes the surface once and produces the SMC or NSC
    material to match, which matters here because PLANT's two plants do not both
    use the same contact method: hand an SMC material to an NSC system and the
    ground ends up with no contact at all, so the plant falls through it.

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


class ScenePlan:
    """A resolved scene: where to spawn, and how to build the rest of it later.

    Two-step, because of an ordering problem that is easy to trip over: the
    vehicle owns the ChSystem, the terrain needs that system to be added to,
    and the vehicle has to be told where to spawn BEFORE it is initialized.
    So the spawn pose is resolved first, without a system, and the geometry is
    added afterwards:

        plan = plan_scene(0.5)               # start pose, no system needed
        ... build the vehicle at plan.start ...
        plan.build(vehicle.GetSystem())      # terrain
    """

    def __init__(self, name, start):
        self.name = name
        self.start = start

    def build(self, system):
        """Add the terrain to `system`, and return it already initialized."""
        terrain = veh.RigidTerrain(system)
        patch = terrain.AddPatch(_road_material(system), chrono.CSYSNORM, 200.0, 200.0)
        patch.SetTexture(veh.GetVehicleDataFile("terrain/textures/tile4.jpg"), 200, 200)
        patch.SetColor(chrono.ChColor(0.8, 0.8, 0.5))
        terrain.Initialize()
        return terrain


def plan_scene(spawn_height):
    """Resolve the scene to a spawn pose and a build plan, without a ChSystem.

    spawn_height   how far above the ground the plant should start
    """
    return ScenePlan("flat terrain",
                     chrono.ChCoordsysd(chrono.ChVector3d(0, 0, spawn_height),
                                        chrono.QUNIT))
