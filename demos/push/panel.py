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
"""The configurator window: direction, magnitude, and what came back.

A separate window because PyChrono cannot read its own. See
chronohil/input/window/native.py for the one line that would remove the need.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from chronohil import chrono
from chronohil.input.window import open_panel_pointer, open_window_input

from demos.push.rig import DUR_MAX, MAG_MAX

class PushInput:
    """The 3D window's input, with this demo's keys and its aiming helper.

    Composition, not inheritance: which backend is behind this is decided by
    chronohil.input.window, and a demo has no business naming one. Whatever it
    returns exposes the same surface, so this forwards to it.
    """

    EDGE = {"space": "fire", "x": "reset", "c": "clear", "t": "log"}

    def __init__(self, vis, title, w, h):
        self.back = open_window_input(vis, title, w, h, edges=self.EDGE)
        if self.back is None:
            raise RuntimeError("no in-window input on this build")
        self.prev_mouse = False

    # -- forwarded ----------------------------------------------------------
    def __getattr__(self, name):
        return getattr(self.back, name)

    def poll(self):
        self.back.poll()
        return (0.0, 0.0, 0.0)

    def aim_nudge(self):
        """(d_azimuth, d_elevation, d_magnitude) from the arrows and brackets."""
        k = self.back._key
        return ((-1.0 if k("left") else 0.0) + (1.0 if k("right") else 0.0),
                (-1.0 if k("down") else 0.0) + (1.0 if k("up") else 0.0),
                (-1.0 if k("lbracket") else 0.0) + (1.0 if k("rbracket") else 0.0))


PANEL_TITLE = "PART 10: push configurator"


# -----------------------------------------------------------------------------
# The panel's mouse, read from macOS rather than from pygame
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
        pygame.display.set_caption(PANEL_TITLE)
        self.screen = pygame.display.set_mode((self.W, self.H_))
        self.f = pygame.font.SysFont("Menlo, Monaco, monospace", 13)
        self.fb = pygame.font.SysFont("Menlo, Monaco, monospace", 15, bold=True)
        self.drag = None
        self.sliders = []     # filled by draw(), used by the next pump()
        self.buttons = []
        self.commands = []
        self.prev_down = False
        try:
            self.os = open_panel_pointer(PANEL_TITLE, self.W, self.H_)
        except Exception as exc:     # no OS cursor on this platform
            print(f"[panel] OS mouse unavailable ({exc}); using pygame events")
            self.os = None

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
                continue
            if self.os is not None:
                # Polled below instead.  Handling both sources would double-fire
                # every button on the runs where pygame does happen to see the
                # press, and the keys are already read OS-wide by PushInput.
                continue
            self._pump_event(cfg, e)
        if self.os is not None:
            self._pump_os(cfg)
        out, self.commands = self.commands, []
        return out

    def _pump_os(self, cfg):
        """The same hit tests, driven by polled state instead of by events."""
        down = self.os.down()
        if down and not self.prev_down:
            at = self.os.pos()
            if at is not None:
                for rect, key, lo, hi, x0, w in self.sliders:
                    if rect.collidepoint(at):
                        self.drag = (key, lo, hi, x0, w)
                        self._set(cfg, at[0])
                        break
                else:
                    for rect, cmd in self.buttons:
                        if rect.collidepoint(at):
                            self.commands.append(cmd)
                            break
        elif down and self.drag is not None:
            at = self.os.pos(inside_only=False)
            if at is not None:
                self._set(cfg, at[0])
        elif not down:
            self.drag = None
        self.prev_down = down

    def _pump_event(self, cfg, e):
        pg = self.pg
        if e.type == pg.MOUSEBUTTONDOWN and e.button == 1:
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
