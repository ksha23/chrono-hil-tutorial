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
# PART 6 support: the gearbox.
#
# Parts 1-5 treat the human interface as three numbers -- steering, throttle,
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
# On the KEYBOARD (Part 2), you do not have to write any of this: Chrono's own
# Irrlicht event receiver already binds those calls, and vis.AttachDriver()
# is what wires it up.  See KEYBOARD_HELP below for the mapping.
#
# For a device Chrono does not know about (Part 4), nothing is wired up for
# you -- which is the point of Part 4.  Gearbox below is the small adapter that
# turns a one-character command from such a device into the calls above, so the
# operator console can shift gears over the same UDP socket it already uses for
# steering and throttle.
# =============================================================================

import pychrono.vehicle as veh


# What Chrono's Irrlicht event receiver already binds for you, once the driver
# is attached with vis.AttachDriver(driver).  Printed at startup so nobody has
# to go looking for it in the C++ source.
KEYBOARD_HELP = """\
  gears (automatic transmission)
    Z    toggle drive mode  D <-> R          X    neutral
    T    toggle AUTO <-> MANUAL shifting
    [    shift down                          ]    shift up
  gears (manual transmission)
    [    shift down                          ]    shift up
    Q/E  clutch out / in
  driver
    C    center steering                     R    release the pedals\
"""


class Gearbox:
    """Read and drive a vehicle's transmission, whatever kind it is.

    Handles the automatic/manual difference in one place so the rest of the
    tutorial can say `gearbox.command("up")` without caring, and can print
    `gearbox.describe()` without a branch.
    """

    #: single-character commands, as sent by operator_console.py
    COMMANDS = {
        "u": "up",        # shift up
        "d": "down",      # shift down
        "f": "forward",   # drive mode D
        "n": "neutral",   # drive mode N
        "r": "reverse",   # drive mode R
        "m": "mode",      # toggle automatic <-> manual shifting
    }

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

    # -- driving ------------------------------------------------------------

    def command(self, what):
        """Apply one command by name; unknown names are ignored.

        Ignoring rather than raising is deliberate: these arrive off a socket
        from a device we do not control, and a typo on the operator's end
        should not take the simulation down.
        """
        if not self.present:
            return
        if what == "up":
            self.transmission.ShiftUp()
        elif what == "down":
            self.transmission.ShiftDown()
        elif self.auto is None:
            return  # the rest of the commands only mean something on an automatic
        elif what == "forward":
            self.auto.SetDriveMode(veh.ChAutomaticTransmission.DriveMode_FORWARD)
        elif what == "neutral":
            self.auto.SetDriveMode(veh.ChAutomaticTransmission.DriveMode_NEUTRAL)
        elif what == "reverse":
            self.auto.SetDriveMode(veh.ChAutomaticTransmission.DriveMode_REVERSE)
        elif what == "mode":
            am = veh.ChAutomaticTransmission.ShiftMode_AUTOMATIC
            mm = veh.ChAutomaticTransmission.ShiftMode_MANUAL
            self.auto.SetShiftMode(mm if self.auto.GetShiftMode() == am else am)

    def command_char(self, ch):
        """Apply one single-character command (the UDP wire form)."""
        name = self.COMMANDS.get(ch)
        if name:
            self.command(name)

    def set_manual_shifting(self, manual):
        """Start in manual shifting, so ']' and '[' actually do something.

        An automatic left in AUTOMATIC mode overrides any gear you select on
        the very next step, which looks like the shift keys are broken.
        """
        if self.auto is not None:
            self.auto.SetShiftMode(
                veh.ChAutomaticTransmission.ShiftMode_MANUAL if manual
                else veh.ChAutomaticTransmission.ShiftMode_AUTOMATIC)
