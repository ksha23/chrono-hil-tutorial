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
# Build the tutorial deck.
#
#     python3 make_slides.py            rebuild tutorial_HIL_driver.pptx
#     python3 make_slides.py --pdf       rebuild, then export the PDF too
#     python3 make_slides.py --check     resolve every anchor, print the ranges,
#                                        write nothing
#
# WHY THIS FILE EXISTS AT ALL
#
# The deck quotes code out of the tutorial, and quoted code rots the moment
# anybody edits the tutorial.  Line numbers in slide titles went stale three
# separate times while this material was being written, every time because a
# range had been TYPED and the file underneath it had moved.  So nothing here
# is typed: every excerpt is located by anchor text and its line numbers are
# computed at build time.  Edit a demo, rerun this, and the slides are right.
#
# --check is the cheap version of that promise: it resolves every anchor and
# prints what it found, so a broken quote shows up as a failure here instead of
# on a projector.
#
# THE PDF EXPORT, WHICH IS FUSSIER THAN IT LOOKS
#
# PowerPoint for Mac has no `save` command on its `presentation` class -- check
# `sdef /Applications/Microsoft\ PowerPoint.app` and you will not find one. So
# AppleScript accepts `save ... as save as PDF`, reports success, and writes
# nothing at all. It only works if the destination is passed as a `POSIX file`
# OBJECT. A POSIX path string, or one coerced with `as text`, silently no-ops.
# That one distinction is the whole trick, so --pdf is here to keep it.
# =============================================================================

import argparse
import os
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = os.path.join(HERE, "tutorial_HIL_driver.pptx")
IMAGES = os.path.join(HERE, "images")

# -- house style, lifted from the deck this replaces --------------------------
CODE_BG = RGBColor(0x00, 0x00, 0x00)
CODE_FG = RGBColor(0xCC, 0xCC, 0xCC)
CODE_COMMENT = RGBColor(0x7F, 0xAF, 0x7F)   # comments recede, code stays legible
BOX_FILL = RGBColor(0x1F, 0x38, 0x64)
BOX_LINE = RGBColor(0x0B, 0x1E, 0x3F)
BOX_TEXT = RGBColor(0xFF, 0xFF, 0xFF)
ACCENT = RGBColor(0xC5, 0x05, 0x0C)         # UW red, for the one thing per slide
FOOTER = "University of Wisconsin - Madison"

# =============================================================================
# MEASURED NUMBERS
#
# Every number that appears on a slide lives here with the run that produced it,
# so a claim on a projector can be traced to a command.  If you cannot say where
# a number came from, it does not go on a slide.
# =============================================================================
N = {
    # hil_manipulate.py, box dragged for one wall-clock second, with and without
    # the real-time hold.
    "unpaced_m": "88.7",
    "paced_m": "1.8",
    # Go2 from URDF: triangle meshes straight from the file, then convex hulls
    # with the base link in its own collision family.
    "contacts_before": "427",
    "contacts_after": "6",
    "rtf_before": "1.34",
    "rtf_after": "0.09",
    # Friction under-resolved at the default iteration count: the robot slid on
    # what looked like a frictionless floor.
    "solver_before": "PSOR, 50 iterations",
    "solver_after": "BARZILAIBORWEIN, 200 iterations",
    "creep_after": "0.3 mm/s",
    # The grab spring is mass-scaled, so a gain tuned on a 0.154 kg Go2 calf
    # became an ejection seat on a 2.7 kg Panda link.
    "panda_k": "21,870 N/m",
    "panda_accel": "24,300 m/s^2",
    "yank_before": "35.14 m/s",
    "yank_after": "3.25 m/s",
    # hil_push.py, Go2 on a PD stance controller, impulse at the base COM.
    "push_fwd_ok": "325 N",
    "push_fwd_fail": "330 N",
    "push_lat_ok": "280 N",
    "push_lat_fail": "290 N",
    # The mouse layer, with and without the SWIG director.
    "lines_workaround": "135",
    "lines_native": "56",
}


# =============================================================================
# Excerpts: located by anchor, never by line number
# =============================================================================
class AnchorError(Exception):
    pass


def excerpt(path, start, end=None, extra=0, strip_blank=True):
    """Pull a block out of a source file by anchor text.

    start/end are substrings.  end is matched only at or after start, so a
    common phrase does not drag the block backwards.  Returns
    (text, first_line, last_line) with 1-based inclusive line numbers.
    """
    full = os.path.join(HERE, path)
    with open(full) as fh:
        lines = fh.read().split("\n")

    lo = None
    for i, ln in enumerate(lines):
        if start in ln:
            lo = i
            break
    if lo is None:
        raise AnchorError(f"{path}: start anchor not found: {start!r}")

    if end is None:
        hi = lo + extra
    else:
        hi = None
        for i in range(lo, len(lines)):
            if end in lines[i]:
                hi = i + extra
                break
        if hi is None:
            raise AnchorError(f"{path}: end anchor not found after line {lo+1}: {end!r}")
    hi = min(hi, len(lines) - 1)

    block = lines[lo:hi + 1]
    if strip_blank:
        while block and not block[0].strip():
            block, lo = block[1:], lo + 1
        while block and not block[-1].strip():
            block, hi = block[:-1], hi - 1

    # Dedent by the common indent so the code fills the box.
    indents = [len(b) - len(b.lstrip()) for b in block if b.strip()]
    cut = min(indents) if indents else 0
    block = [b[cut:] if b.strip() else "" for b in block]
    return "\n".join(block), lo + 1, hi + 1


def cite(*specs):
    """Render 'Lines 12 to 40' / 'Lines 12 to 40, 71 to 88' for a slide title."""
    parts = []
    for _, lo, hi in specs:
        parts.append(f"{lo} to {hi}")
    return "Lines " + ", ".join(parts)


# =============================================================================
# Slide plumbing
# =============================================================================
def clear(prs):
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        rId = sld.get("{http://schemas.openxmlformats.org/officeDocument/2006/"
                      "relationships}id")
        prs.part.drop_rel(rId)
        ids.remove(sld)


def layout(prs, name):
    for lay in prs.slide_masters[0].slide_layouts:
        if lay.name == name:
            return lay
    raise KeyError(name)


def chrome(prs, slide, page):
    """Footer and page number, as textboxes -- the layouts do not carry them."""
    tb = slide.shapes.add_textbox(Inches(0.34), Inches(7.27), Inches(12.73), Inches(0.21))
    tb.name = "Footer"
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = FOOTER
    r.font.size = Pt(10)
    tb = slide.shapes.add_textbox(Inches(11.21), Inches(7.27), Inches(1.87), Inches(0.21))
    tb.name = "PageNo"
    p = tb.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = str(page)
    r.font.size = Pt(10)


def rich(par, text, base_size=16):
    """Write text where `backticked` spans become Consolas runs."""
    for i, chunk in enumerate(text.split("`")):
        if not chunk:
            continue
        r = par.add_run()
        r.text = chunk
        r.font.size = Pt(base_size if i % 2 == 0 else base_size - 2)
        if i % 2 == 1:
            r.font.name = "Consolas"


def note_box(slide, lines, top, size=16, height=None):
    h = height if height is not None else 0.34 * len(lines) + 0.2
    tb = slide.shapes.add_textbox(Inches(0.44), Inches(top), Inches(12.46), Inches(h))
    tb.name = "NoteBox"
    tf = tb.text_frame
    tf.word_wrap = True
    for i, ln in enumerate(lines):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.space_after = Pt(4)
        rich(par, ln, size)
    return tb


def code_box(slide, code, top, height, size=10):
    tb = slide.shapes.add_textbox(Inches(0.0), Inches(top), Inches(13.33), Inches(height))
    tb.name = "CodeBox"
    tb.fill.solid()
    tb.fill.fore_color.rgb = CODE_BG
    tf = tb.text_frame
    tf.word_wrap = False
    tf.margin_left = Inches(0.35)
    tf.margin_top = Inches(0.10)
    for i, ln in enumerate(code.split("\n")):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.space_after = Pt(0)
        r = par.add_run()
        r.text = ln if ln else " "
        r.font.name = "Consolas"
        r.font.size = Pt(size)
        stripped = ln.strip()
        r.font.color.rgb = CODE_COMMENT if stripped.startswith("#") else CODE_FG
    return tb


def title_of(slide, text, size=26):
    ph = slide.shapes.title
    ph.text_frame.text = text
    for par in ph.text_frame.paragraphs:
        for r in par.runs:
            r.font.size = Pt(size)
    return ph


def box(slide, x, y, w, h, head, body=None, fill=BOX_FILL, size=18):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.color.rgb = BOX_LINE
    sh.line.width = Pt(1)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    par = tf.paragraphs[0]
    par.alignment = PP_ALIGN.CENTER
    r = par.add_run()
    r.text = head
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.color.rgb = BOX_TEXT
    for ln in (body or []):
        par = tf.add_paragraph()
        par.alignment = PP_ALIGN.CENTER
        r = par.add_run()
        r.text = ln
        r.font.size = Pt(size - 4)
        r.font.color.rgb = BOX_TEXT
    return sh


def label(slide, x, y, w, text, size=14, align=PP_ALIGN.CENTER, color=None):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.5))
    tf = tb.text_frame
    tf.word_wrap = True
    par = tf.paragraphs[0]
    par.alignment = align
    rich(par, text, size)
    if color is not None:
        for r in par.runs:
            r.font.color.rgb = color
    return tb


def arrow(slide, x, y, w, h, shape=MSO_SHAPE.RIGHT_ARROW, fill=None):
    sh = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill or RGBColor(0x8A, 0x92, 0xA0)
    sh.line.fill.background()
    return sh


# =============================================================================
# The deck
# =============================================================================
def build(check_only=False):
    # ---- every quote, resolved from the source as it stands right now -------
    E = {}
    E["report"] = excerpt("tutorial_HIL_driver.py",
                          "# Console report: how far is the sim from wall time?",
                          "rtf = (d_wall / d_sim) if d_sim > 0 else 0.0")
    E["rt_setup"] = excerpt("tutorial_HIL_driver.py",
                            "# Real-time setup (PART 1)",
                            "cum_timer = CumulativeRealtimeTimer()")
    E["rt_spin"] = excerpt("tutorial_HIL_driver.py",
                           "# PART 1: spin in place for real time to catch up",
                           "cum_timer.spin(system.GetChTime())")
    E["keyboard"] = excerpt("tutorial_HIL_driver.py",
                            'elif INPUT_SOURCE == "keyboard":',
                            "driver.SetKeyboardMode(veh.ChInteractiveDriver.KeyboardMode_HELD)")
    E["udp"] = excerpt("tutorial_HIL_driver.py", "class UdpInput:",
                       "self.sock.setblocking(False)")
    E["pick"] = excerpt("hil_manipulate.py", "def pick_along_ray(system, start, end):",
                        "chrono.ChVector3d(nrm.x, nrm.y, nrm.z))")
    E["spring"] = excerpt("hil_manipulate.py", "omega = getattr(self.system,",
                          "self.system.AddLink(self.spring)")
    E["push"] = excerpt("hil_push.py", "def fire(self, cfg, t):",
                        "body.AccumulateForce(idx, force,")
    E["native"] = excerpt("experimental/native_pick.py", "class MouseReceiver",
                          "elif ev.MouseInput.Event == irr.EMIE_LMOUSE_LEFT_UP:", extra=1)

    if check_only:
        print(f"{'excerpt':12s}  {'lines':>14s}   first line")
        for k, (text, lo, hi) in E.items():
            head = text.split("\n")[0][:56]
            print(f"{k:12s}  {lo:5d} to {hi:5d}   {head}")
        return

    prs = Presentation(DECK)
    clear(prs)
    TITLE_SLIDE = layout(prs, "Title Slide")
    SECTION = layout(prs, "Section Header")
    CONTENT = layout(prs, "Title and Content")
    TITLE_ONLY = layout(prs, "Title Only")
    page = [0]

    def new(lay):
        page[0] += 1
        s = prs.slides.add_slide(lay)
        return s

    def finish(s):
        chrome(prs, s, page[0])

    def section(head, sub):
        s = new(SECTION)
        s.shapes.title.text_frame.text = head
        for ph in s.placeholders:
            if ph.placeholder_format.idx != 0:
                ph.text_frame.text = sub
                break
        finish(s)
        return s

    def bullets(head, items, note=None, size=20):
        s = new(CONTENT)
        title_of(s, head)
        body = None
        for ph in s.placeholders:
            if ph.placeholder_format.idx != 0:
                body = ph
                break
        tf = body.text_frame
        tf.word_wrap = True
        for i, item in enumerate(items):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            par.space_after = Pt(9)
            if isinstance(item, tuple):
                text, lvl = item
                par.level = lvl
                rich(par, text, size - 2 * lvl)
            else:
                rich(par, item, size)
        if note:
            note_box(s, note, 6.05)
        finish(s)
        return s

    def code_slide(head, specs, note, size=10, top=1.32):
        s = new(TITLE_ONLY)
        title_of(s, f"{head} ({cite(*specs)})")
        joined = "\n\n".join(sp[0] for sp in specs)
        nlines = len(joined.split("\n"))
        note_h = 0.34 * len(note) + 0.2
        avail = 7.10 - top - note_h - 0.15
        # Shrink to fit rather than overflow: a slide that runs off the bottom
        # is worse than a slide in 8pt.
        while size > 7 and nlines * (size + 1.2) / 72.0 > avail:
            size -= 1
        height = min(avail, nlines * (size + 1.2) / 72.0 + 0.22)
        code_box(s, joined, top, height, size)
        note_box(s, note, top + height + 0.12)
        finish(s)
        return s

    def showtime(lines, note=None, shots=None):
        s = new(CONTENT)
        title_of(s, "Show Time")
        body = None
        for ph in s.placeholders:
            if ph.placeholder_format.idx != 0:
                body = ph
                break
        tf = body.text_frame
        tf.word_wrap = True
        for i, ln in enumerate(lines):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            par.space_after = Pt(10)
            rich(par, ln, 20)
        if shots:
            # A row of screenshots in the space the bullets do not use. Scaled to
            # a common height so a wide top-down shot and a tall arm shot do not
            # fight each other.
            paths = [os.path.join(IMAGES, f) for f in shots]
            paths = [q for q in paths if os.path.exists(q)]
            if paths:
                from PIL import Image as _Im
                H_IN = 2.55
                widths = []
                for q in paths:
                    iw, ih = _Im.open(q).size
                    widths.append(H_IN * iw / float(ih))
                gap = 0.30
                total = sum(widths) + gap * (len(widths) - 1)
                x = (13.33 - total) / 2.0
                for q, w in zip(paths, widths):
                    s.shapes.add_picture(q, Inches(x), Inches(3.15),
                                         Inches(w), Inches(H_IN))
                    x += w + gap
        if note:
            note_box(s, note, 6.05)
        finish(s)
        return s

    # =========================================================================
    # 1. Title
    # =========================================================================
    s = new(TITLE_SLIDE)
    s.shapes.title.text_frame.text = "Chrono support for human-in-the-loop simulation"
    for ph in s.placeholders:
        if ph.placeholder_format.idx != 0:
            tf = ph.text_frame
            tf.text = "Kyle Sha"
            p = tf.add_paragraph()
            p.text = "Simulation-Based Engineering Lab"
            break
    finish(s)

    # =========================================================================
    # 2-6. What we mean by it
    # =========================================================================
    section("What counts as human-in-the-loop",
            "the definition this tutorial works to, and the three things it "
            "demands of a simulator")

    bullets("The definition this tutorial works to",
            ["A simulation is human-in-the-loop when all three of these hold:",
             ("1.  a person's action changes the state of a RUNNING simulation,", 1),
             ("2.  the simulation's response changes what that person does next, and", 1),
             ("3.  the cycle closes fast enough that they can keep reacting.", 1),
             "Each clause is load-bearing:",
             ("drop 1 and you have a visualisation  -  you are watching, not acting", 1),
             ("drop 2 and the person is driving blind  -  open loop, not a loop", 1),
             ("drop 3 and you have a batch job with a joystick attached", 1)],
            note=["Nothing in that definition mentions vehicles. That is the whole "
                  "point of the tutorial: a car, a crane, a gearbox and a "
                  "quadruped's leg all satisfy it, and they satisfy it the same way."])

    # -- the loop diagram ----------------------------------------------------
    s = new(TITLE_ONLY)
    title_of(s, "The loop, and the clock around it")
    box(s, 0.60, 2.30, 3.30, 1.30, "Person", ["sees, decides, acts"])
    box(s, 5.02, 2.30, 3.30, 1.30, "Chrono", ["DoStepDynamics(step)"])
    box(s, 9.44, 2.30, 3.30, 1.30, "Screen + telemetry", ["what came back"])
    arrow(s, 4.00, 2.75, 0.92, 0.40)
    arrow(s, 8.42, 2.75, 0.92, 0.40)
    label(s, 3.60, 1.75, 1.72, "steering, a force, a click", 13)
    label(s, 8.02, 1.75, 1.72, "position, speed, contact", 13)
    arrow(s, 0.60, 4.15, 12.14, 0.42, MSO_SHAPE.LEFT_ARROW)
    label(s, 0.60, 4.62, 12.14,
          "what they see changes what they do next  -  this arrow is what makes it a LOOP", 15)
    box(s, 3.30, 5.45, 6.70, 0.80,
        "and every lap has to fit inside one wall-clock step", [], fill=ACCENT, size=16)
    note_box(s, ["Break the first arrow and it is a movie. Break the return "
                 "arrow and it is a recording session. Break the clock and the "
                 "person cannot stay in the loop at all, which is why the clock "
                 "comes first in this tutorial."], 6.42)
    finish(s)

    bullets("Not everything interactive is in the loop",
            ["IN the loop  -  a person's input is a term in the dynamics, every step",
             ("driving the HMMWV; dragging a robot's limb while its controller resists", 1),
             "ON the loop  -  a person configures and triggers, then watches it play out",
             ("the push rig: you choose where and how hard, the impulse itself is scripted", 1),
             "Neither  -  interactive, but nothing is reacting",
             ("the top-down placement tool: kinematic, no dynamics, a scene-authoring tool", 1)],
            note=["Worth saying out loud, because 'interactive' and 'in the loop' "
                  "get used interchangeably and only one of them has a clock in it. "
                  "All three are useful. Only the first two are what the phrase means."])

    # =========================================================================
    # 7-13. The clock
    # =========================================================================
    section("Requirement 3 comes first: the clock",
            "it decides whether the other two requirements are worth anything")

    bullets("What real time means in Chrono",
            ["Chrono integrates as fast as it can. It has no notion of wall-clock time.",
             "`RTF = wall time / simulated time`",
             ("`RTF < 1`  -  faster than real time. You have slack, and can sleep.", 1),
             ("`RTF = 1`  -  exactly real time.", 1),
             ("`RTF > 1`  -  slower than real time. No amount of sleeping fixes this.", 1),
             "So holding the clock is two separate problems:",
             ("do not run FAST  -  sleep off the slack (easy, one call)", 1),
             ("do not run SLOW  -  make the step cheap enough to have slack (the real work)", 1)],
            note=[f"Unpaced, a dragged box in the manipulation demo travelled "
                  f"{N['unpaced_m']} m in one wall-clock second instead of "
                  f"{N['paced_m']} m. The physics was right. The experience was useless."])

    code_slide("Measure it, then hold it",
               [E["report"], E["rt_setup"], E["rt_spin"]],
               ["`ChRealtimeStepTimer.Spin(step)` sleeps off whatever is left of the "
                "step. `vehicle.EnableRealtime(True)` does the same thing from "
                "inside `Advance()`.",
                "Per-step timers never recover time lost on a slow step, so a "
                "cumulative timer is offered too: it paces against total elapsed "
                "time and can catch up."])

    showtime(['`REALTIME = "none"`: watch the drift column run away',
              '`REALTIME = "vehicle"`: drift pinned near zero, RTF at 1',
              "Same physics in both runs. The only difference is whether the "
              "process sleeps."],
             note=["The drift column is the honest one. RTF can look fine on "
                   "average while the sim has already lost a second of wall clock."])

    bullets("You can only sleep if you have slack",
            ["Everything from here is about the second problem: making a step cheap.",
             "The two that actually moved the number on these demos:",
             ("contact  -  how much geometry the collision system is asked to resolve", 1),
             ("the solver  -  how many iterations each step is allowed", 1),
             "They pull against each other. Iterations buy stability and cost time; "
             "cheaper geometry buys time and can cost fidelity.",
             "The budget is fixed: one step of wall clock, minus what you want to "
             "leave for rendering."],
            note=["Both numbers on the next two slides came out of the same "
                  "robot, a Unitree Go2 loaded from URDF, on a laptop."])

    bullets("Where the time goes: contact",
            [f"Triangle meshes straight from the URDF: `{N['contacts_before']} contacts` "
             f"standing still, `RTF {N['rtf_before']}`  -  slower than real time, "
             f"before any human touches it",
             "The robot was resolving its own thighs against its own shins, every step.",
             f"Convex hulls, plus the base link in its own collision family: "
             f"`{N['contacts_after']} contacts`, `RTF {N['rtf_after']}`",
             "Same robot, same controller, same step size. Roughly 15x the slack."],
            note=["A URDF collision mesh is authored for a planner that asks "
                  "'do these overlap'. A real-time dynamics loop asks it every "
                  "step, for every pair. Those are different jobs and the file "
                  "does not know which one you are doing."])

    bullets("Where the time goes: the solver",
            [f"`{N['solver_before']}`: the robot slid across the floor as if "
             f"friction were switched off.",
             "It was not a friction bug. Friction was under-resolved: the solver "
             "ran out of iterations before the tangential constraints converged.",
             f"`{N['solver_after']}`: creep fell to `{N['creep_after']}`.",
             "Iterations are the price of stability, and you pay for them out of "
             "the same wall-clock step you wanted to sleep in."],
            note=["This one is worth knowing because it does not look like a "
                  "performance problem. It looks like wrong physics, and it "
                  "sends you hunting through friction coefficients."])

    # =========================================================================
    # 14-20. A path into the state
    # =========================================================================
    section("Requirement 1: a path into the state",
            "how a person's action actually reaches the equations")

    s = new(TITLE_ONLY)
    title_of(s, "Three ways a person's input enters a Chrono simulation")
    box(s, 0.50, 2.05, 3.90, 1.70, "As driver inputs",
        ["ChDriver / ChInteractiveDriver", "steering, throttle, braking"])
    box(s, 4.72, 2.05, 3.90, 1.70, "As a force or constraint",
        ["AccumulateForce, ChLinkTSDA", "on any body, any scene"])
    box(s, 8.94, 2.05, 3.90, 1.70, "As a pose you set",
        ["SetPos / SetRot", "kinematic placement"])
    label(s, 0.50, 3.90, 3.90, "the vehicle demos  (Parts 2-4)", 15)
    label(s, 4.72, 3.90, 3.90, "the drag and push demos  (Parts 9-10)", 15)
    label(s, 8.94, 3.90, 3.90, "the placement tool", 15)
    label(s, 0.50, 4.45, 3.90, "IN the loop", 15, color=ACCENT)
    label(s, 4.72, 4.45, 3.90, "IN the loop", 15, color=ACCENT)
    label(s, 8.94, 4.45, 3.90, "not in the loop", 15)
    note_box(s, ["The middle column is the general one. A vehicle has a driver "
                 "class because somebody wrote one; every other plant in this "
                 "tutorial takes its human input as a force, which is why the "
                 "same pattern reaches a crane, a gearbox and a quadruped.",
                 "The right-hand column is honest about itself: nothing reacts "
                 "to a pose you set, so nothing closes the loop."], 5.15)
    finish(s)

    code_slide("The keyboard, and what a keypress means",
               [E["keyboard"]],
               ["`CUMULATIVE` (the old default): a keypress NUDGES the input, and it "
                "stays where you left it. Fine for a test script, strange under a hand.",
                "`HELD`: the input follows the keys currently down, like a driving "
                "game. That mode was added to Chrono for this tutorial and ships "
                "in PyChrono 10.0.0 build 1187."])

    showtime(["`INPUT_SOURCE = \"keyboard\"`, `KEYBOARD_MODE = \"held\"`",
              "W/A/S/D drive. The arrow keys are the chase camera, not the car.",
              "Try `\"cumulative\"` and feel the difference a key-state API makes."],
             shots=["hmmwv.png"],
             note=["This is the whole definition satisfied in one window: input "
                   "reaches the state, the state comes back on screen, and the "
                   "timer holds the pace."])

    # -- UDP diagram ---------------------------------------------------------
    s = new(TITLE_ONLY)
    title_of(s, "A device Chrono does not know about")
    box(s, 0.77, 2.84, 4.70, 1.59, "Operator machine", ["operator_console.py"])
    box(s, 7.87, 2.84, 4.70, 1.59, "Simulation machine", ["tutorial_HIL_driver.py"])
    arrow(s, 5.62, 2.95, 2.10, 0.38)
    label(s, 5.47, 2.40, 2.40, "steering, throttle, braking, gear", 13)
    arrow(s, 5.62, 3.90, 2.10, 0.38, MSO_SHAPE.LEFT_ARROW)
    label(s, 5.47, 4.30, 2.40, "speed, RTF, lateral accel, gear", 13)
    note_box(s, ["Plain UDP datagrams, two processes, optionally two machines. "
                 "Chrono never learns what is on the other end: a console, a "
                 "phone, a motion platform, a wheel rig, another simulator.",
                 "The return arrow is the part people skip, and it is the one "
                 "that makes the operator's device part of the loop instead of "
                 "a remote control."], 5.30)
    finish(s)

    code_slide("Reading a device Chrono does not know about",
               [E["udp"]],
               ["Non-blocking is the whole trick: the simulation must never wait "
                "on a human. A late datagram means 'hold the last input', not "
                "'stall the loop'.",
                "Sample ONCE per step and hold it, or one physics step sees a "
                "different input than the next one for no reason the operator "
                "can perceive."])

    showtime(["Two terminals on one laptop over localhost, or two machines over a LAN",
              "The console shows telemetry coming back while you drive"],
             shots=["showtime_udp.png"],
             note=["If the console's numbers stop moving, the loop is open and "
                   "the operator is guessing. That is the failure this arrow "
                   "exists to prevent."])

    # =========================================================================
    # 21-27. Reaching into the scene
    # =========================================================================
    section("Reaching into the scene with a mouse",
            "what Chrono provides today, the one line it is missing, and what "
            "that buys")

    bullets("What Chrono gives you today",
            ["`ChRealtimeStepTimer`  -  the pacing, exposed to Python",
             "`ChInteractiveDriver`  -  keyboard and joystick input, with `KeyboardMode::HELD`",
             "`ChCollisionSystem::RayHit`  -  click-to-pick, exposed to Python",
             "`AccumulateForce`, `ChLinkTSDA`  -  a human's pull as a term in the dynamics",
             "`ChVisualSystemIrrlicht::AddUserEventReceiver(IEventReceiver*)`  -  "
             "the socket for any input device, and it IS bound in Python",
             "What is NOT there: any built-in mouse pick-and-drag. No module in "
             "the tree implements one."],
            note=["That last line is the gap this tutorial walks into. Everything "
                  "needed to build one is already exposed; what is missing is the "
                  "ability to receive the mouse event in the first place."])

    code_slide("The gap, and the one line that closes it",
               [("# chrono_swig/interface/irrlicht/ChModuleIrrlicht.i\n"
                 "+%feature(\"director\") irr::IEventReceiver;\n"
                 "%include \"IEventReceiver.h\"\n"
                 "\n"
                 "# The module ALREADY compiles with directors enabled:\n"
                 "#     %module(directors=\"1\", threads=\"1\") irrlicht\n"
                 "# and AddUserEventReceiver is ALREADY bound. Without the\n"
                 "# director, though, Python gets an abstract class:\n"
                 "#     >>> ci.IEventReceiver()\n"
                 "#     AttributeError: No constructor defined - class is abstract\n"
                 "# so there is a socket, and nothing you can plug into it.",
                 0, 0)] + [E["native"]],
               [f"Without it, reading the mouse means going around Chrono to the "
                f"operating system: `{N['lines_workaround']} lines`, macOS only, "
                f"and it breaks when another window takes focus.",
                f"With it, the same capability is `{N['lines_native']} lines` of "
                f"ordinary PyChrono. Upstream PR to follow this talk."],
               top=1.32)
    # The patch block above is hand-written, not quoted, so drop its fake range
    # from the title rather than cite lines 0 to 0.
    t = prs.slides[-1].shapes.title.text_frame
    t.paragraphs[0].runs[0].text = (
        f"The gap, and the one line that closes it "
        f"(native_pick.py lines {E['native'][1]} to {E['native'][2]})")

    code_slide("Picking a body, then pulling on it",
               [E["pick"], E["spring"]],
               ["`RayHit` is the pick. It is already in PyChrono and it is exact: "
                "the same primitive a native mouse handler would call.",
                "The spring is the part that has to be got right. Gains must scale "
                f"with the mass being pulled: a stiffness tuned on a Go2 calf gave a "
                f"Panda link `{N['panda_k']}`, which is `{N['panda_accel']}` and "
                f"straight through the floor in one step."])

    showtime(["Drag a leg while the stance controller fights back",
              "Drag a Franka link, hand-guided or fully unactuated",
              f"Yanking a link into the floor: `{N['yank_before']}` before the "
              f"gains were bounded, `{N['yank_after']}` after"],
             shots=["demo_go2.png", "demo_arm.png"],
             note=["This is the clearest case of the definition on the whole "
                   "deck: you pull, the controller resists, you feel it resist, "
                   "and you pull differently."])

    code_slide("Taking the human out of the part that must repeat",
               [E["push"]],
               ["A freehand drag cannot answer 'how hard can I shove it', because "
                "no two drags are the same. The force depends on how fast your "
                "hand moved and how long you held the button.",
                "So the person keeps WHERE and WHICH DIRECTION, and the impulse "
                "`J = F * dt` is scripted and printed. That is a number you can "
                "put in a report and hand to somebody else."])

    showtime([f"Forward at the base COM: `{N['push_fwd_ok']}` recovers, "
              f"`{N['push_fwd_fail']}` does not",
              f"Sideways: `{N['push_lat_ok']}` recovers, `{N['push_lat_fail']}` does not",
              "Same impulse, applied 5 cm higher up the torso: the verdict flips"],
             shots=["demo_push.png"],
             note=["That last line is the reason a human is still in this one. "
                   "Where to push is a judgement call, and it changes the answer "
                   "as much as how hard you push does."])

    # =========================================================================
    # 28-30. Close
    # =========================================================================
    bullets("How far this goes",
            ["`PART 6`  -  change gear. A gear is not a fourth float: it belongs to "
             "the transmission, and the human sets it through a different API.",
             "`PART 7`  -  drive somewhere real. `SCENE = \"mcity\"` puts the car in "
             "the Mcity digital twin.",
             "`PART 8`  -  control something that is not a car. `PLANT = \"rover\"` "
             "or `\"crane\"`, same three floats, no vehicle class involved.",
             "`PARTS 9-10`  -  reach into the scene: drag a limb, push a robot, "
             "place a scene."],
            note=["The through-line: the loop never changed. What changed was "
                  "where the human's numbers were injected."])

    bullets("Where this goes next",
            ["`Chrono::HIL` (github.com/zzhou292/chrono-HIL)  -  driving rigs, "
             "steering wheels, multi-user sessions, the same three floats",
             "The SWIG director change, as an upstream PR",
             "A mouse pick-and-drag utility, so that every PyChrono user does not "
             "write the same 56 lines",
             "Policy in the loop: a learned controller on one side, a person "
             "perturbing it on the other"],
            note=["The gap this talk found is small and specific, which is the "
                  "good kind: one line to receive the event, and a utility on "
                  "top of primitives Chrono already has."])

    s = new(SECTION)
    s.shapes.title.text_frame.text = "Any questions?"
    for ph in s.placeholders:
        if ph.placeholder_format.idx != 0:
            ph.text_frame.text = FOOTER
            break
    finish(s)

    s = new(layout(prs, "Blank"))
    tb = s.shapes.add_textbox(Inches(1.2), Inches(2.9), Inches(10.9), Inches(1.6))
    par = tb.text_frame.paragraphs[0]
    par.alignment = PP_ALIGN.CENTER
    r = par.add_run()
    r.text = "Thank you."
    r.font.size = Pt(44)
    par = tb.text_frame.add_paragraph()
    par.alignment = PP_ALIGN.CENTER
    r = par.add_run()
    r.text = "github.com/ksha23/chrono-hil-tutorial"
    r.font.size = Pt(20)
    r.font.name = "Consolas"
    finish(s)

    # ---- metadata: nothing inherited from whatever template this began as ---
    cp = prs.core_properties
    cp.title = "Chrono support for human-in-the-loop simulation"
    cp.author = "Kyle Sha"
    cp.last_modified_by = "Kyle Sha"
    cp.comments = ""
    cp.category = ""
    cp.keywords = ""
    cp.subject = ""

    prs.save(DECK)
    print(f"[deck] {len(prs.slides.__iter__.__self__._sldIdLst)} slides -> {DECK}")
    for k, (_, lo, hi) in E.items():
        print(f"       cited {k:10s} lines {lo} to {hi}")


def export_pdf():
    """Drive PowerPoint to write the PDF, then strip the metadata it adds."""
    import subprocess
    import tempfile

    script = tempfile.NamedTemporaryFile("w", suffix=".scpt", delete=False)
    script.write('''on run argv
    set srcPath to item 1 of argv
    set dstPath to item 2 of argv
    tell application "Microsoft PowerPoint"
        activate
        open POSIX file srcPath
        delay 3
        set pres to active presentation
        -- POSIX file OBJECT, not a path string: a string here silently does nothing
        save pres in (POSIX file dstPath) as save as PDF
        delay 2
        close pres saving no
    end tell
end run
''')
    script.close()
    raw = os.path.join(HERE, "_deck_raw.pdf")
    subprocess.run(["osascript", script.name, DECK, raw], check=True)
    os.unlink(script.name)
    if not os.path.exists(raw):
        raise SystemExit("[pdf] PowerPoint wrote nothing")

    import pymupdf
    d = pymupdf.open(raw)
    d.set_metadata({})          # the export carries Quartz/template metadata
    d.del_xml_metadata()
    out = DECK.replace(".pptx", ".pdf")
    d.save(out, garbage=4, deflate=True)
    pages = d.page_count
    d.close()
    os.unlink(raw)
    print(f"[pdf] {pages} pages -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="resolve every anchor and print the ranges; write nothing")
    ap.add_argument("--pdf", action="store_true",
                    help="also export tutorial_HIL_driver.pdf via PowerPoint")
    args = ap.parse_args()
    try:
        build(check_only=args.check)
    except AnchorError as exc:
        print(f"[anchor] {exc}", file=sys.stderr)
        sys.exit(1)
    if args.pdf and not args.check:
        export_pdf()
