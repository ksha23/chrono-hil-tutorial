# Four proposed recuts of the tutorial deck

Drafts, for choosing between. The deck actually in use is still
`../tutorial_HIL_driver.pptx`; nothing here replaces it until you say so.

Each option is a complete, presentable deck built from the same verified code
excerpts and the same template, so they can be compared by flipping through the
PDFs rather than by reading this file. D is the recommendation; A, B and C are
the distinct positions it was chosen from.

## Why recut at all

Three things are wrong with the current 30-slide deck, and only the first is
about the Parts 6-8 material.

**It is about seven minutes too long.** Rough model below: 15 s for a title or
closing slide, 10 s for a section header, 60 s for a bullet slide, 100 s for a
code slide, 150 s for a live demo. Disagree with those numbers and the ranking
still holds, because they are applied identically to all five.

| deck | slides | code slides | live demos | modelled |
|---|---|---|---|---|
| current | 30 | 10 | 4 | **~37 min** |
| A - why first | 26 | 7 | 4 | ~31 min |
| B - two patterns | 23 | 7 | 3 | **~27 min** |
| C - one loop | 25 | 8 | 2 | ~28 min |
| D - recommended | 26 | 7 | 4 | ~31 min |

**The motivation is on slide 26 of 30.** The crane -- a swinging load that no
controller in the repo can place, and that only a human can -- is the clearest
answer this tutorial has to "why put a human in a simulation loop". It is
currently the second-to-last thing said, filed under bonus material. The talk
opens instead with the definition of RTF, which is mechanism before anyone has
been given a reason to care.

**Ten of thirty slides are full-screen code.** Two of them are 30+ lines at
9pt. In a talk with the repo on screen and linked, those get read aloud or
skipped. Merging the pairs that belong together (the two real-time mechanisms;
sampling and sending back; the driver and its attachment) costs nothing and
buys back four slides.

## A - "Why first"

*Thesis: earn the mechanism before teaching it.*

Opens cold on the crane: the task, then the demo, then "nothing on screen was
vehicle-specific, so what does Chrono actually require of a human interface?"
-- which lands on `DriverInputs`, the whole contract in twelve lines. Only then
the roadmap, and the two hard parts. Every part of the current deck survives.

Pick this if the current content is right and only the order is wrong. It is
still the longest of the three, so it is the one most likely to overrun.

## B - "The two patterns"  (recommended)

*Thesis: the README's own thesis, followed strictly.*

The repo already says it: "The two patterns worth taking away: keeping a
simulation real-time (Part 1) and closing an external device's control loop
back to it (Part 4) ... Parts 5-8 are bonus material, not the point." This deck
does exactly that. Contract up front, Pattern 1, the keyboard as the easy case,
Pattern 2, and Parts 6-8 compressed into a single slide.

Pick this if the audience is meant to leave with something transferable rather
than a tour. It is the shortest, has the most slack for demos running long, and
is the only one with real room for questions during rather than after.

The cost is honest: the Mcity work and the crane get one slide between them.

## C - "One loop, three variables"

*Thesis: the new breadth is the argument, not an appendix.*

Reframes the whole talk around what Part 8 actually proved: the loop is the
invariant, and everything else is a variable around it -- where the numbers
come from (keyboard, wheel, socket), what they drive (car, rover, crane), and
where it happens (flat patch, Mcity). Real-time and UDP become supporting acts
in service of that.

Pick this if the goal is to show what the tutorial repo can now do, or if the
audience is more "what can Chrono do" than "teach me a pattern". It is also the
most visually varied -- a car, a rover, a crane and a real test facility.

The cost is that the two genuinely transferable patterns get less airtime.

## D - "Recommended"  (B's body behind A's cold open)

*Thesis: open with the reason, then spend the talk on what transfers.*

A's first three slides -- the crane task, the crane demo, and the question it
raises -- land on the contract slide, which now arrives as the answer to
something rather than as a definition. Everything after that is B: the two
patterns, the keyboard as the easy case, Parts 6-8 on one slide at the end.

Pick this if the argument matters more than the minute count.

## Recommendation

**D.** It gets the one thing the current deck most clearly has backwards -- the
motivation is at the end -- without giving up the body of the talk to a tour.

One correction to what I said before building it: D models at **~31 minutes,
not 30**. A's cold open costs 220 s and only ~60 s comes back from replacing
B's overview slide, so D lands where A does. If 31 is too close for comfort,
the cheapest honest cut is slide 17, the keyboard demo: the cold open has
already put a live simulation on screen, and Part 2 still keeps its code
slide. That is ~28.5 min. I have left the demo in rather than make that call
for you.

Straight **B** if you would rather not open on a demo. A cold open that fails
costs more than it earns, and it is the first thing the audience sees; B never
depends on a demo working before minute nine.

## Promoting one

Pick a letter and I will move it to `tutorial_HIL_driver.pptx` / `.pdf`, update
the repo README's description of what the deck covers, and delete this folder.
