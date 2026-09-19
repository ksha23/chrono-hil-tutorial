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
# TRANSMISSION, and the shift keys: the gearbox.
#
# Demos 1 and 2 treat the human interface as three numbers -- steering, throttle,
# braking -- because that is the whole ChDriver contract.  A real driver does a
# fourth thing: they choose a gear.  That does not go through ChDriver at all,
# because the gearbox is part of the *vehicle*, not part of the driver:
#
#     vehicle.GetTransmission()  ->  ChTransmission
#         .GetCurrentGear()  .GetMaxGear()  .SetGear(n)
#         .ShiftUp()         .ShiftDown()
#         .IsAutomatic()     .asAutomatic()   -> ChAutomaticTransmission or None
#         .IsManual()        .asManual()      -> ChManualTransmission or None
#
#     ChAutomaticTransmission adds
#         .SetDriveMode(FORWARD | NEUTRAL | REVERSE)   the D/N/R selector
#         .SetShiftMode(AUTOMATIC | MANUAL)            let it shift, or row it
#
# On the KEYBOARD (Demo 2), you do not have to write any of this: Chrono's own
# Irrlicht event receiver already binds those calls, and vis.AttachDriver()
# is what wires it up.  See KEYBOARD_HELP below for the mapping.
#
# For a device Chrono does not know about, nothing is wired up for you, which
# is the point of it.  Gearbox below is the adapter such a device needs: it
# turns a one-character command into the calls above, so a gear can travel
# alongside steering and throttle on whatever carries them.
# =============================================================================

import pychrono.vehicle as veh


# What Chrono's Irrlicht event receiver already binds for you, once the driver
# is attached with vis.AttachDriver(driver).  Printed at startup so nobody has
# to go looking for it in the C++ source.
KEYBOARD_HELP = """\
  driving (KEYBOARD_MODE = "cumulative")
    W/S  throttle up / down (S brakes once throttle reaches 0)
    A/D  steer left / right
    C    center steering                     R    release the pedals
    L    lock the current inputs
  driving (KEYBOARD_MODE = "held")
    W    hold to accelerate                  S    hold to brake
    A/D  hold to steer left / right          E    hold the clutch (manual only)
  camera (NOT driving controls)
    arrows  zoom and orbit the chase camera  PgUp/PgDn  raise / lower it
  gears (automatic transmission)
    Z    toggle drive mode  D <-> R          X    neutral
    T    toggle AUTO <-> MANUAL shifting
    [    shift down                          ]    shift up
  gears (manual transmission)
    [    shift down                          ]    shift up
    Q/E  clutch out / in ("cumulative" only)\
"""


class Gearbox:
    """Read and drive a vehicle's transmission, whatever kind it is.

    Handles the automatic/manual difference in one place so the rest of the
    tutorial can print `gearbox.describe()` without a branch.

    Note what is NOT here: nothing that shifts. The shift keys are bound by
    Chrono's own Irrlicht event receiver, so this tutorial never sees them --
    which is the point of the slide about what Chrono::Vehicle gives a vehicle
    for free.
    """

    def __init__(self, vehicle):
        self.transmission = vehicle.GetTransmission()
        self.auto = None
        self.manual = None
        if self.transmission is not None:
            # asAutomatic()/asManual() return None for the other kind, which is
            # how you ask "which sort of gearbox is this" without a dynamic_cast.
            self.auto = self.transmission.asAutomatic()
            self.manual = self.transmission.asManual()

    @property
    def present(self):
        return self.transmission is not None

    # -- reading ------------------------------------------------------------

    def describe(self):
        """One short string: 'D 2/3 auto', 'N', 'R', 'M 3/6'."""
        if not self.present:
            return "--"
        gear = self.transmission.GetCurrentGear()
        top = self.transmission.GetMaxGear()
        if self.auto is not None:
            mode = self.auto.GetDriveMode()
            if mode == veh.ChAutomaticTransmission.DriveMode_NEUTRAL:
                return "N"
            if mode == veh.ChAutomaticTransmission.DriveMode_REVERSE:
                return "R"
            shifting = ("auto" if self.auto.GetShiftMode() ==
                        veh.ChAutomaticTransmission.ShiftMode_AUTOMATIC else "man")
            return f"D {gear}/{top} {shifting}"
        return f"M {gear}/{top}"

    # -- setting up ---------------------------------------------------------

    def set_manual_shifting(self, manual):
        """Start in manual shifting, so ']' and '[' actually do something.

        An automatic left in AUTOMATIC mode overrides any gear you select on
        the very next step, which looks like the shift keys are broken.
        """
        if self.auto is not None:
            self.auto.SetShiftMode(
                veh.ChAutomaticTransmission.ShiftMode_MANUAL if manual
                else veh.ChAutomaticTransmission.ShiftMode_AUTOMATIC)
