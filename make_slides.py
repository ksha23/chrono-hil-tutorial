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
import re
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
CODE_TYPE = RGBColor(0xF0, 0xA0, 0x40)     # Chrono types, in the Chrono orange
CODE_CALL = RGBColor(0x7F, 0xC7, 0xE8)     # the calls, which are the point of the slide
CODE_STR = RGBColor(0xD8, 0xA0, 0xC0)
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
    # hil_push.py, impulse at the base COM, 50 ms window. Same rig, same robot,
    # two controllers: a PD holding a stance, and the trained locomotion policy.
    "push_fwd_ok": "325 N",
    "push_fwd_fail": "330 N",
    "push_lat_ok": "280 N",
    "push_lat_fail": "290 N",
    "pol_fwd_ok": "1850 N",
    "pol_fwd_fail": "1900 N",
    "pol_lat_ok": "1100 N",
    "pol_lat_fail": "1200 N",
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


# A line of code on a slide is mostly punctuation and plumbing. What the
# audience is meant to read is the type names and the calls, so those get the
# colour and everything else gets out of the way.
_TOKENS = re.compile(r"""
      (?P<str>\"[^\"]*\"|\'[^\']*\')
    | (?P<type>\bCh[A-Z][A-Za-z0-9_]*)
    | (?P<call>\b[A-Za-z_][A-Za-z0-9_]*(?=\s*\())
""", re.VERBOSE)


def _comment_split(line):
    """Split a line into (code, comment), ignoring markers inside strings."""
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "#":
            return line[:i], line[i:]
        elif c == "/" and line[i:i + 2] == "//":
            return line[:i], line[i:]
        i += 1
    return line, ""


def _emit(par, text, colour, size):
    if not text:
        return
    r = par.add_run()
    r.text = text
    r.font.name = "Consolas"
    r.font.size = Pt(size)
    r.font.color.rgb = colour


def code_line(par, line, size):
    """Write one line as coloured runs."""
    code, comment = _comment_split(line)
    pos = 0
    for m in _TOKENS.finditer(code):
        _emit(par, code[pos:m.start()], CODE_FG, size)
        kind = m.lastgroup
        _emit(par, m.group(),
              {"str": CODE_STR, "type": CODE_TYPE, "call": CODE_CALL}[kind], size)
        pos = m.end()
    _emit(par, code[pos:], CODE_FG, size)
    _emit(par, comment, CODE_COMMENT, size)
    if not line:
        _emit(par, " ", CODE_FG, size)


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
        code_line(par, ln, size)
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


def place_side_shot(slide, path, tight, left=7.95, top=1.62):
    """One figure down the right-hand side, scaled to fill that column.

    A single portrait-ish image under a short bullet list wastes the whole
    right half of the slide and comes out postage-stamp sized. Beside the text
    it gets two to three times the area for free. Wide-and-short images are the
    exception and stay below, where they can use the full width.
    """
    from PIL import Image as _Im
    iw, ih = _Im.open(path).size
    box_w = 13.33 - left - 0.43
    box_h = (6.05 if tight else 6.95) - top
    scale = min(box_w / iw, box_h / ih)
    w, h = iw * scale, ih * scale
    slide.shapes.add_picture(path, Inches(left + (box_w - w) / 2.0),
                             Inches(top + (box_h - h) / 2.0), Inches(w), Inches(h))


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
    gap = 0.30
    aspects = []
    for q in paths:
        iw, ih = _Im.open(q).size
        aspects.append(iw / float(ih))
    # A row of four would happily run off both edges at a fixed height, so the
    # height is whatever makes the row fit the usable width.
    usable = 12.40 - gap * (len(paths) - 1)
    height = min(height, usable / sum(aspects))
    widths = [height * a for a in aspects]
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

    def bullets(head, items, note=None, size=20, shots=None, cite=None):
        """A bullet slide.

        `note` used to render as a box along the bottom edge. On a slide that is
        already a list, that reads as an orphaned bullet somebody could not fit
        in, so notes are now simply appended to the list they were commenting
        on. `cite` is the one thing that still belongs in small print at the
        foot of a slide, because a citation is not content.
        """
        if note:
            items = list(items) + list(note)
            note = None
        s = new(CONTENT)
        title_of(s, head)
        body = None
        for ph in s.placeholders:
            if ph.placeholder_format.idx != 0:
                body = ph
                break
        tf = body.text_frame
        tf.word_wrap = True
        # One figure that is not wide-and-short goes beside the text, which
        # means the text column narrows and every bullet wraps sooner.
        side_path = None
        if shots:
            paths = [os.path.join(IMAGES, f) for f in shots]
            paths = [q for q in paths if os.path.exists(q)]
            if len(paths) == 1:
                from PIL import Image as _Im
                iw, ih = _Im.open(paths[0]).size
                if iw / float(ih) < 2.2:
                    side_path = paths[0]
        body_w = 7.05 if side_path else 11.96
        # Setting width alone on an INHERITED placeholder makes python-pptx
        # write a partial xfrm, and the position collapses to the slide origin:
        # the bullets end up on top of the title. Pin all four, reading the
        # inherited values first.
        bl, bt, bh = body.left, body.top, body.height
        body.left, body.top, body.height = bl, bt, bh
        body.width = Inches(body_w)
        # Rough line budget: a 20pt bullet wraps at about 105 characters across
        # the full-width placeholder, proportionally fewer in a narrow column,
        # and the slide holds roughly 13 such lines above the note. Shrink
        # rather than overflow.
        per_line = max(30, int(105 * body_w / 11.96))
        est = sum(1 + len(it[0] if isinstance(it, tuple) else it) // per_line
                  for it in items)
        # Two jobs, two numbers. Shrinking text wants the true wrap width (105);
        # deciding where a figure may go wants a pessimistic one, because being
        # wrong there puts a picture through a paragraph. Sharing one number
        # meant every fix for one broke the other.
        per_fig = max(24, int(78 * body_w / 11.96))
        est_fig = sum(1 + len(it[0] if isinstance(it, tuple) else it) // per_fig
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
        if side_path:
            place_side_shot(s, side_path, cite)
        elif shots:
            # Put the figure under the text, not on top of it. Text starts at
            # 1.44 in; a line costs size*1.25 pt plus the paragraph gap.
            text_bottom = (1.44 + est_fig * (size * 1.25) / 72.0
                           + len(items) * gap / 72.0)
            top = max(3.05, text_bottom + 0.30)
            room = (6.15 if cite else 7.00) - top
            if room > 0.9:
                place_shots(s, shots, top=top, height=min(2.55, room))
        if cite:
            note_box(s, cite, 6.30, size=13)
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
        while size > 7 and nlines * (size * 1.25) / 72.0 > avail:
            size -= 1
        height = min(avail, nlines * (size * 1.25) / 72.0 + 0.30)
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
        while size > 7 and nlines * (size * 1.25) / 72.0 > avail:
            size -= 1
        height = min(avail, nlines * (size * 1.25) / 72.0 + 0.30)
        code_box(s, joined, top, height, size)
        note_box(s, note, top + height + 0.12)
        finish(s)
        return s

    def showtime(name, what, why, lines, note=None, shots=None):
        """A demo slide that says what it is and why anyone should care.

        "Demo Time" on its own tells an audience nothing, and a demo nobody has
        been given a reason to watch is a pause in the talk. Delegates to
        bullets so it inherits the same shrink-to-fit and the same figure
        placement, which is below the text rather than through it.
        """
        return bullets(f"Demo Time: {name}",
                       [f"`WHAT`  {what}", f"`WHY`   {why}"] + list(lines),
                       note=note, shots=shots)

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

    bullets("What this talk covers",
            ["1.  `What counts as human-in-the-loop`, and what it demands of a "
             "simulator. A definition we will hold every demo against.",
             "2.  `The clock.` Why pacing comes first, and the levers Chrono gives "
             "you for buying enough slack to pace at all.",
             "3.  `Getting a person's input into the state.` The driver surface, the "
             "input devices Chrono already speaks, and what to do about the ones it "
             "does not.",
             "4.  `Reaching into the scene.` Picking a body, pulling on it, and a "
             "one-line gap in PyChrono that this talk closes.",
             "Four demos along the way, and the code is all in one repository you "
             "can clone."],
            note=["The order is deliberate. The clock comes before the input, "
                  "because input into a simulation that cannot hold real time is "
                  "not human-in-the-loop, whatever else it is."])

    bullets("The four demos",
            ["1.  `Does the clock matter.` The same drive twice, paced and unpaced.",
             "2.  `A person driving.` Keyboard into a vehicle, the textbook case.",
             "3.  `Reaching in.` Drag a quadruped's leg while a trained "
             "locomotion policy fights you, and a Franka arm with the motors on or off.",
             "4.  `How hard can you shove it.` A measured impulse at a point you "
             "choose, and the magnitude where recovery stops."],
            shots=["hmmwv.png", "demo_go2.png", "demo_arm.png", "demo_push.png"])

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

    bullets("What a person in the loop is for",
            ["`Measuring the person.` Human factors: what does an operator do when "
             "the controls are delayed, when an assist takes authority, when a "
             "hazard appears late?",
             "`Training the person.` Here the simulator IS the product, and the "
             "fidelity bar is whether it feels like the real thing.",
             "`Collecting data from the person.` Demonstrations for imitation "
             "learning, driver models, reference trajectories no controller would "
             "have produced.",
             "`Testing the machine against a person.` Someone perturbs a controller "
             "in ways a scripted test would never have thought to try.",
             "`Judging the machine by feel.` Reach in, pull on it, see whether it "
             "behaves plausibly. Faster than any metric at answering 'something is "
             "wrong here'.",
             "`Designing shared control.` When authority is split between a person "
             "and a controller, neither half can be evaluated alone.",
],
            note=["Two different jobs hide in that list. Sometimes the person is "
                  "the SUBJECT being measured; sometimes the person is the "
                  "CONTROLLER, because nothing else can do the task. Either way the "
                  "simulator has to hold wall-clock time, or you are measuring the "
                  "simulator instead of the person."])

    bullets("A study Chrono has already carried",
            ["Remote car-following under latency. Forty participants, four groups "
             "of ten. Uplink delayed their inputs, downlink delayed the video back.",
             "`Chrono::Vehicle` ego and lead dynamics, `SynChrono` between the two "
             "nodes, `Chrono::Sensor` for the forward camera on three monitors at "
             "60 Hz, `Chrono::HIL` for a Logitech G29 wheel and pedals.",
             "Mitigation cut driving incidents 72%, though not significantly, and "
             "significantly lowered steering entropy at high speed. Adaptation "
             "across the three latency trials dominated the effect."],
            shots=["hil_rig.png", "remote_driving_study.png"],
            cite=["Ma, McDonald, Sha, Zhang, Xu, Negrut. \"Evaluating a "
                  "delay-compensated shared-control system in high- and low-speed "
                  "remote car-following.\""])

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
             ("do not run SLOW  -  make the step cheap enough to have slack (the real work)", 1)])

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

    showtime("does the clock actually matter",
             "the same scripted drive twice, once pacing to wall clock and once not",
             "it turns the real-time requirement from an assertion into a column "
             "you can watch run away",
             ['`REALTIME = "none"`: watch the drift column run away',
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
    note_box(s, ["The left column is the privileged one, and it is privileged for "
                 "a reason: vehicles are this lab's bread and butter, so they are "
                 "what got a purpose-built human-input class. That machinery lives "
                 "in Chrono::Vehicle, so a crane or a robot cannot reach it.",
                 "The middle column is the general one, and it is how everything "
                 "that is not a vehicle gets a person into its loop.",
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
              ["Note WHERE this lives: `ChDriver` and `ChInteractiveDriver` are in "
               "Chrono::VEHICLE, not in core. Vehicles are what this lab does most, "
               "so vehicles are what got a first-class human-input class, a keyboard "
               "mode, and a joystick mapping. Nothing else in Chrono has one.",
               "Query the driver BEFORE `Synchronize`: the human's numbers have to "
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
             "H-shifter enumerating as three separate USB devices all map at once",
             "Not hypothetical: the remote-driving study on slide 5 ran on a "
             "Logitech G29 wheel and pedal set through this path"],
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

    showtime("a person driving the vehicle",
             "keyboard straight into ChInteractiveDriver, HMMWV on rigid terrain",
             "the whole definition satisfied in one window, and the baseline every "
             "other demo is measured against",
             ["`INPUT_SOURCE = \"keyboard\"`, `KEYBOARD_MODE = \"held\"`",
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

    showtime("reaching in and pulling on a robot",
             "click a link and drag it while its controller fights to stay standing",
             "human input as a FORCE rather than as driver inputs, which is how "
             "everything that is not a vehicle gets a person in its loop",
             ["Drag a leg while the locomotion policy steps to keep its feet",
              "Drag a Franka link, hand-guided or fully unactuated",
              "The same drag works on a 0.15 kg shin and a 2.7 kg arm link, "
              "because the spring is built from the mass it is pulling"],
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

    showtime("how hard can you shove it",
             "click where the push lands, set direction and magnitude, fire a "
             "measured impulse, and find the magnitude where recovery stops",
             "robustness testing that produces a NUMBER, so the result can go in a "
             "report and somebody else can reproduce it",
             ["`The rig measures the controller.` Same robot, same push, same "
              "50 ms window, two things holding it up:",
              (f"a PD holding a stance: `{N['push_fwd_ok']}` recovers, "
               f"`{N['push_fwd_fail']}` does not", 1),
              (f"a trained locomotion policy: `{N['pol_fwd_ok']}` recovers, "
               f"`{N['pol_fwd_fail']}` does not", 1),
              f"Sideways is weaker for both: `{N['push_lat_ok']}`/"
              f"`{N['push_lat_fail']}` for the stance, `{N['pol_lat_ok']}`/"
              f"`{N['pol_lat_fail']}` for the policy.",
              "The difference is that the stance can only stiffen. The policy "
              "picks a foot up and steps into the shove, and will be carried five "
              "metres doing it rather than fall over.",
              "Same impulse, applied 5 cm higher up the torso: the verdict flips"],
             shots=["demo_push.png"],
             note=["That last line is the reason a human is still in this one. "
                   "Where to push is a judgement call, and it changes the answer "
                   "as much as how hard you push does."])

    # =========================================================================
    # 28-30. Close
    # =========================================================================
    bullets("Where to go next",
            ["This tutorial   `github.com/ksha23/chrono-hil-tutorial`",
             ("every part, the demos, and the SWIG director patch under "
              "`experimental/`", 1),
             "Chrono   `projectchrono.org`   `github.com/projectchrono/chrono`",
             ("`conda install -c projectchrono pychrono`", 1),
             "Chrono::HIL   `github.com/zzhou292/chrono-HIL`",
             ("driving rigs, steering wheels, multi-user sessions, the same three "
              "floats", 1),
             "Joystick and wheel mappings   `data/vehicle/joystick/`",
             ("copy the nearest config, change the axis and button numbers", 1)],
            note=["The gap this talk found is small and specific, which is the good "
                  "kind: one line to let Python receive the event, and a utility on "
                  "top of primitives Chrono already exposes. Upstream PR to follow."])

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
