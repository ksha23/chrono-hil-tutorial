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


def named(spec, path):
    """Attach a file name to an excerpt so a slide can say where it came from."""
    return (spec[0], spec[1], spec[2], path)


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


def note_height(lines, size=16):
    """How tall a note really is once it wraps.

    Counting logical lines under-reserves: one long sentence becomes two or
    three lines on the slide, and the last one lands on the footer. At 16pt the
    note box fits roughly 105 characters per line.
    """
    per = max(40, int(105 * 16.0 / size))
    rows = sum(1 + max(0, (len(ln.replace("`", "")) - 1)) // per for ln in lines)
    return 0.30 * rows + 0.18


def note_box(slide, lines, top, size=16, height=None):
    h = height if height is not None else note_height(lines, size)
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


def place_shots(slide, shots, top=3.15, height=2.55):
    """A centred row of screenshots in the space the bullets do not use.

    Scaled to a common height so a wide top-down shot and a tall arm shot do not
    fight each other for the same band of slide.
    """
    if not shots:
        return
    paths = [os.path.join(IMAGES, f) for f in shots]
    paths = [q for q in paths if os.path.exists(q)]
    if not paths:
        return
    from PIL import Image as _Im
    widths = []
    for q in paths:
        iw, ih = _Im.open(q).size
        widths.append(height * iw / float(ih))
    gap = 0.30
    x = (13.33 - (sum(widths) + gap * (len(widths) - 1))) / 2.0
    for q, w in zip(paths, widths):
        slide.shapes.add_picture(q, Inches(x), Inches(top), Inches(w), Inches(height))
        x += w + gap


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
    E["kbd_call"] = excerpt("tutorial_HIL_driver.py",
                            'if KEYBOARD_MODE == "held":',
                            "driver.SetKeyboardMode(veh.ChInteractiveDriver.KeyboardMode_HELD)")
    E["keyboard"] = excerpt("tutorial_HIL_driver.py",
                            'elif INPUT_SOURCE == "keyboard":',
                            "driver.SetKeyboardMode(veh.ChInteractiveDriver.KeyboardMode_HELD)")
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

    def bullets(head, items, note=None, size=20, shots=None):
        s = new(CONTENT)
        title_of(s, head)
        body = None
        for ph in s.placeholders:
            if ph.placeholder_format.idx != 0:
                body = ph
                break
        tf = body.text_frame
        tf.word_wrap = True
        # Rough line budget: a 20pt bullet wraps at about 78 characters in the
        # content placeholder, and the slide holds roughly 13 such lines above
        # the note. Shrink rather than overflow.
        est = sum(1 + len(it[0] if isinstance(it, tuple) else it) // 78
                  for it in items)
        while size > 13 and est > (13 if not note else 11) * (20.0 / size):
            size -= 1
        gap = 9 if size >= 18 else 5
        for i, item in enumerate(items):
            par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            par.space_after = Pt(gap)
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
        note_h = note_height(note)
        avail = 7.05 - top - note_h - 0.15
        # Shrink to fit rather than overflow: a slide that runs off the bottom
        # is worse than a slide in 8pt.
        while size > 7 and nlines * (size + 1.2) / 72.0 > avail:
            size -= 1
        height = min(avail, nlines * (size + 1.2) / 72.0 + 0.34)
        code_box(s, joined, top, height, size)
        note_box(s, note, top + height + 0.12)
        finish(s)
        return s

    def api_slide(head, api_lines, call_spec, note, size=11):
        """The interface first, the call site second.

        A slide that quotes only this tutorial teaches this tutorial. What an
        audience can actually carry home is the API surface -- the handful of
        calls that exist whatever you are simulating -- so that goes on top,
        copied from the Chrono header. The excerpt underneath is there to prove
        the surface is really used, not to be studied.
        """
        s = new(TITLE_ONLY)
        body = list(api_lines)
        if call_spec is not None:
            body += ["", f"# ---- and how this tutorial calls it "
                         f"({call_spec[3]}, lines {call_spec[1]} to {call_spec[2]}) "
                         + "-" * 6]
            body += call_spec[0].split("\n")
        title_of(s, head)
        joined = "\n".join(body)
        nlines = len(body)
        top = 1.32
        note_h = note_height(note)
        avail = 7.05 - top - note_h - 0.15
        while size > 7 and nlines * (size + 1.2) / 72.0 > avail:
            size -= 1
        height = min(avail, nlines * (size + 1.2) / 72.0 + 0.34)
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
        place_shots(s, shots)
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

    bullets("Why a person at all",
            ["A gantry crane. Four bodies, two speed motors, one distance "
             "constraint. No vehicle, no terrain, no tires.",
             "The payload hangs free and NOTHING damps the swing but the operator.",
             ("accelerate hard and the load swings", 1),
             ("it keeps swinging until someone drives the trolley back under it", 1),
             "`status()` reports the swing angle, so the console scores how badly "
             "you are doing without your having to watch the window."],
            shots=["crane_swing.png"],
            note=["No controller in this tutorial can land that load, which is the "
                  "cleanest answer to 'why not just automate it'. It also settles "
                  "the generality question early: if the pattern reaches a crane, "
                  "it is not a Chrono::Vehicle feature."])

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
            note=[f"Unpaced, a box being dragged by hand travelled "
                  f"{N['unpaced_m']} m in one wall-clock second instead of "
                  f"{N['paced_m']} m. The physics was right both times. Only one of "
                  f"them was usable by a person."])

    api_slide("Holding wall-clock time: the pacing surface",
              ["// chrono/core/ChRealtimeStep.h",
               "class ChRealtimeStepTimer : public ChTimer {",
               "    void Spin(double step);    // sleep off whatever is left of `step`",
               "};",
               "",
               "// chrono_vehicle/ChVehicle.h -- same policy, applied inside Advance()",
               "void   ChVehicle::EnableRealtime(bool val);",
               "double ChVehicle::GetRTF() const;   // wall / simulated, per step",
               "",
               "// The pattern, whatever is being simulated:",
               "//     while running:",
               "//         inputs = read_human()      # never blocking",
               "//         sys.DoStepDynamics(step)",
               "//         if time to draw: render()",
               "//         timer.Spin(step)           # give the wall clock its due"],
              named(E["rt_spin"], "tutorial_HIL_driver.py"),
              ["Two calls. Everything else about real time is arithmetic around them.",
               "Per-step timers never recover time lost on a slow step. If you need "
               "the sim to catch up after a stall, pace against TOTAL elapsed time "
               "instead, which is the third mode in this tutorial."])

    showtime(['`REALTIME = "none"`: watch the drift column run away',
              '`REALTIME = "vehicle"`: drift pinned near zero, RTF at 1',
              "Same physics in both runs. The only difference is whether the "
              "process sleeps."],
             note=["The drift column is the honest one. RTF can look fine on "
                   "average while the sim has already lost a second of wall clock."])

    bullets("You can only sleep if you have slack",
            ["Holding the clock is two problems, and only one of them is a call:",
             ("do not run FAST  -  sleep off the slack", 1),
             ("do not run SLOW  -  make the step cheap enough to HAVE slack", 1),
             "The budget is fixed: one step of wall clock, minus what you spend "
             "drawing, minus what you leave as margin for a bad step.",
             "What follows is the set of levers Chrono gives you for the second "
             "problem, in rough order of how much they usually buy."],
            note=["Reach for them in this order. People tend to start at the "
                  "solver, which is near the bottom of the list and the easiest "
                  "place to spend an afternoon for nothing."])

    bullets("The levers, in rough order of payoff",
            ["1.  `Step size`. Everything scales with steps per second. The largest "
             "step that stays stable is the single biggest lever there is.",
             "2.  `Collision geometry`. Primitives beat convex hulls beat triangle "
             "meshes, by a lot. Most imported assets arrive as the slowest option.",
             "3.  `Which pairs are tested at all`. Families and masks remove whole "
             "classes of pair from the broadphase, including self-collision.",
             "4.  `Active domains`. Let the expensive physics happen only where it "
             "matters: deformable terrain near the wheels, fluid near the hull.",
             "5.  `Solver type and iteration cap`. Iterations buy convergence and "
             "cost time, and you pay out of the same step you wanted to sleep in.",
             "6.  `Threads`, `sleeping bodies`, and `model reduction` for elastic "
             "subassemblies.",
             "7.  `Render less often than you step`. Drawing is not free, and the "
             "eye does not need 500 Hz."],
            note=["None of this is specific to having a human in the loop. It "
                  "becomes urgent when there is one, because a batch job that runs "
                  "at 0.6x real time is merely slow, and an interactive one is broken."])

    api_slide("The levers, by name",
              ["// the step, and how it is integrated",
               "sys.DoStepDynamics(step);",
               "sys.SetTimestepperType(ChTimestepper::Type::...);",
               "",
               "// the solver: type, and how long it is allowed to work",
               "sys.SetSolverType(ChSolver::Type::BARZILAIBORWEIN);",
               "sys.GetSolver()->AsIterative()->SetMaxIterations(n);",
               "",
               "// what the collision system is asked to do",
               "model->SetFamily(i);  model->SetFamilyMask(mask);  // skip whole pairs",
               "ChCollisionModel::SetDefaultSuggestedEnvelope(e);   // contact envelope",
               "ChCollisionModel::SetDefaultSuggestedMargin(m);",
               "",
               "// where the expensive physics is allowed to happen",
               "SCMTerrain::AddActiveDomain(body, ...);   // deform near the wheels only",
               "ChFsiSystemSPH::SetActiveDomain(box);     // fluid where it matters only",
               "",
               "// spend less on what is not moving, or not detailed",
               "sys.SetNumThreads(n_chrono, n_collision, n_eigen);  // three pools",
               "sys.SetSleepingAllowed(true);             // bodies at rest drop out",
               "ChModalAssembly::DoModalReduction(...);   // internal DOFs -> a few modes"],
              None,
              ["Every one of these is a real-time decision before it is a fidelity "
               "decision, and most of them are one line."])

    bullets("Two that do not look like performance problems",
            ["`Under-resolved friction reads as a frictionless floor.` A solver that "
             "runs out of iterations before the tangential constraints converge does "
             "not report an error: the thing just slides, and you go hunting through "
             "friction coefficients instead of iteration counts.",
             "`Imported collision geometry is authored for a different question.` A "
             "planner's mesh answers 'do these two overlap', once. A dynamics loop "
             "asks every step, for every pair, and the file does not know which job "
             "it is doing.",
             "Switching one quadruped's URDF triangle meshes to convex hulls, and "
             "masking self-collision, took it from `427 contacts` standing still to "
             "`6`, and from slower than real time to roughly fifteen times faster."],
            note=["Both of these cost days somewhere. They are worth naming out "
                  "loud because neither presents as a speed problem, and the "
                  "instinct in both cases sends you somewhere useless."])

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

    api_slide("Feeding driver input: the ChDriver surface",
              ["// chrono_vehicle/ChDriver.h -- what EVERY driver exposes, human or not",
               "class ChDriver {",
               "    void SetSteering(double s);   // -1 .. +1",
               "    void SetThrottle(double t);   //  0 .. 1",
               "    void SetBraking(double b);    //  0 .. 1",
               "    void SetClutch(double c);     //  0 .. 1",
               "    DriverInputs GetInputs() const;",
               "    virtual void Synchronize(double time);  // read the world",
               "    virtual void Advance(double step);      // advance own state",
               "};",
               "",
               "// Two ways in, and the vehicle cannot tell them apart:",
               "//   subclass ChDriver and write the setters from your own device, or",
               "//   take ChInteractiveDriver and let it read a keyboard or a joystick.",
               "// Either way the vehicle only ever sees a DriverInputs struct."],
              named(E["kbd_call"], "tutorial_HIL_driver.py"),
              ["Query the driver BEFORE `Synchronize`: the human's numbers have to "
               "be in hand before the modules read each other for this step.",
               "`KeyboardMode`: `CUMULATIVE` nudges an input and leaves it there; "
               "`HELD` follows the keys currently down, like a driving game. HELD "
               "was added to Chrono for this tutorial and ships in build 1187."])

    bullets("Input devices Chrono already speaks",
            ["`ChInteractiveDriver` covers two CLASSES of device, not two devices:",
             ("`InputMode_KEYBOARD`  -  with `KeyboardMode_HELD` or `_CUMULATIVE`", 1),
             ("`InputMode_JOYSTICK`  -  anything the windowing layer enumerates as one", 1),
             "A joystick is mapped by a JSON file, not by code: "
             "`SetJoystickConfigFile(path)`",
             ("mapped axes: steering, throttle, brake, CLUTCH", 1),
             ("mapped buttons: shift up/down, reverse, gears 1-9, manual-gearbox toggle, "
              "plus one user callback", 1),
             "Four configs ship in `data/vehicle/joystick/`: Default, Logitech "
             "RumblePad 2, Xbox One, and Wheel+Pedals+Shifters",
             "Each control names its own DEVICE, so a wheel, a pedal box and an "
             "H-shifter enumerating as three separate USB devices all map at once"],
            note=["So a G923-class rig is a config file, not a port. The mapping and "
                  "the semantics are Chrono's and cross-platform; enumerating the "
                  "device is delegated to the windowing layer, so which platforms "
                  "see your wheel follows that layer, and I have not tested it here.",
                  "All of it is exposed to PyChrono."])

    bullets("And for a device Chrono does not know about",
            ["Subclass `ChDriver`, read whatever you like, and obey three rules:",
             "1.  `NEVER BLOCK.` A simulation that waits on a human is not "
             "real-time. Late input means hold the last value, not stall the loop.",
             "2.  `SAMPLE ONCE PER STEP, THEN HOLD.` Read at the top of the step "
             "and reuse that value for the whole step, or the physics sees inputs "
             "change for reasons the operator can neither perceive nor reproduce.",
             "3.  `SEND SOMETHING BACK.` With no return path the operator is "
             "driving open loop, which is not human-in-the-loop by our definition.",
             "Obey those and the transport does not matter: a socket, a serial "
             "port, shared memory, a ROS topic, another simulator."],
            note=["This tutorial ships one of these, an operator console on UDP, "
                  "so a second machine can drive the simulation and watch telemetry "
                  "come back."])

    showtime(["`INPUT_SOURCE = \"keyboard\"`, `KEYBOARD_MODE = \"held\"`",
              "W/A/S/D drive. The arrow keys are the chase camera, not the car.",
              "Try `\"cumulative\"` and feel the difference a key-state API makes."],
             shots=["hmmwv.png"],
             note=["This is the whole definition satisfied in one window: input "
                   "reaches the state, the state comes back on screen, and the "
                   "timer holds the pace."])

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

    api_slide("Turning a click into a body: the ray-cast surface",
              ["// chrono/collision/ChCollisionSystem.h",
               "struct ChRayhitResult {",
               "    bool hit;",
               "    ChVector3d abs_hitPoint;     // where, in world coordinates",
               "    ChVector3d abs_hitNormal;    // the surface normal there",
               "    double dist_factor;          // 0 .. 1 along the segment",
               "    ChCollisionModel* hitModel;  // -> CastToChBody() for the body",
               "};",
               "",
               "virtual bool RayHit(const ChVector3d& from,",
               "                    const ChVector3d& to,",
               "                    ChRayhitResult& result) const;",
               "",
               "// A ray sees COLLISION geometry, never visual geometry. A link you",
               "// can see but whose collision is off is invisible to every click.",
               "// That one sentence accounted for every 'it will not pick' bug here."],
              named(E["pick"], "hil_manipulate.py"),
              ["Exposed in PyChrono already, and exact: the same primitive a native "
               "mouse handler would call. Screen pixel to ray is your arithmetic; "
               "ray to body is Chrono's."])

    api_slide("Turning a pull into physics: force, or constraint",
              ["// A human pulling on something is one of exactly two things.",
               "",
               "// 1. A FORCE, when you want a push of known size (chrono/physics/ChBody.h)",
               "unsigned int idx = body->AddAccumulator();       // ONCE per body",
               "body->EmptyAccumulator(idx);                     // your job, EVERY step",
               "body->AccumulateForce(idx, force, appl_point, local);",
               "body->AccumulateTorque(idx, torque, local);",
               "",
               "// 2. A CONSTRAINT, when you want a hand (chrono/physics/ChLinkTSDA.h)",
               "spring->Initialize(handle, body, local, point1, point2);",
               "spring->SetRestLength(0.0);",
               "spring->SetSpringCoefficient(k);   // k = m*w^2   scale with the MASS",
               "spring->SetDampingCoefficient(c);  // c = 2*m*w    critically damped",
               "sys.AddLink(spring);"],
              named(E["spring"], "hil_manipulate.py"),
              ["Chrono never clears an accumulator for you, and `AddAccumulator()` "
               "appends, so calling it per push leaks a slot and every stale slot "
               "keeps contributing.",
               f"Gains must scale with what is being pulled. A stiffness tuned on a "
               f"0.154 kg Go2 calf gave a 2.7 kg Panda link `{N['panda_k']}`, which "
               f"is `{N['panda_accel']}`: through the floor in a single step."])

    showtime(["Drag a leg while the stance controller fights back",
              "Drag a Franka link, hand-guided or fully unactuated",
              f"Yanking a link into the floor: `{N['yank_before']}` before the "
              f"gains were bounded, `{N['yank_after']}` after"],
             shots=["demo_go2.png", "demo_arm.png"],
             note=["This is the clearest case of the definition on the whole "
                   "deck: you pull, the controller resists, you feel it resist, "
                   "and you pull differently."])

    api_slide("Taking the human out of the part that must repeat",
              ["# The pattern, not the API: decide which half of the human's input",
               "# has to be repeatable, and script only that half.",
               "#",
               "#   the person keeps:   WHERE on the body, and WHICH DIRECTION",
               "#   the machine keeps:  a constant force F held for a fixed window dt",
               "#",
               "#   impulse  J = F * dt      both printed, both logged",
               "#",
               "# A freehand drag cannot answer 'how hard can I shove it', because",
               "# no two drags are the same: the force depends on how fast a hand",
               "# moved and how long a button was held. There is no number at the end.",
               "# Script the magnitude and you get one you can put in a report."],
              named(E["push"], "hil_push.py"),
              ["This is the human-ON-the-loop half of the taxonomy: the person sets "
               "up the experiment and reads the verdict, and is deliberately not in "
               "the inner loop, because being in it would destroy repeatability."])

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
        -- A presentation left open from an earlier run stays the "active" one,
        -- and you export THAT: a stale PDF with a plausible page count.
        close every presentation saving no
        delay 1
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
