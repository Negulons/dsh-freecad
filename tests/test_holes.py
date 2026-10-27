"""Hole/slot/curved-feature detection fixtures.

Needs FreeCAD, so it is not part of the Node test suite (CI has no FreeCAD):

    set FREECAD_USER_HOME=... & set FREECAD_USER_DATA=... & set TMP=...
    freecadcmd.exe tests/test_holes.py
"""
import math
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.join(os.path.dirname(_here), "dsh"))

import FreeCAD  # noqa: E402
import Part  # noqa: E402
import fc_common  # noqa: E402

FAILED = []


def say(*args):
    print(*args, flush=True)


def check(name, got, want):
    ok = got == want
    say(("  ok   " if ok else "  FAIL ") + name + ": %r (want %r)" % (got, want))
    if not ok:
        FAILED.append(name)


def kinds(records):
    return [r["kind"] for r in records]


def box(l, w, h):
    return Part.makeBox(l, w, h)


say("plain through hole")
holes, curved = fc_common.detect_holes(
    box(40, 40, 10).cut(Part.makeCylinder(3.5, 12, FreeCAD.Vector(20, 20, -1))))
check("count", len(holes), 1)
check("kind", kinds(holes), ["hole"])
check("diameter", round(holes[0]["diameter"], 3), 7.0)
check("through", holes[0]["through"], True)
check("curved", len(curved), 0)

say("radial hole into a shaft (entry on a curved face)")
shaft = Part.makeCylinder(20, 60)
holes, curved = fc_common.detect_holes(
    shaft.cut(Part.makeCylinder(3, 40, FreeCAD.Vector(0, -20, 30), FreeCAD.Vector(0, 1, 0))))
check("count", len(holes), 1)
check("axis", holes[0]["axisName"], "Y")
check("diameter", round(holes[0]["diameter"], 3), 6.0)

say("45 deg hole (oblique axis, depth must be exact)")
axis = FreeCAD.Vector(math.cos(math.radians(45)), 0, math.sin(math.radians(45)))
start = FreeCAD.Vector(20 - 12 * axis.x, 20, 5 - 12 * axis.z)
holes, curved = fc_common.detect_holes(
    box(40, 40, 10).cut(Part.makeCylinder(2.5, 30, start, axis)))
check("count", len(holes), 1)
check("depth", round(holes[0]["depth"], 3), 14.142)

say("obround slot (two half cylinders joined by flat walls)")
plate = box(70, 40, 10)
plate = plate.cut(Part.makeCylinder(4, 12, FreeCAD.Vector(20, 20, -1)))
plate = plate.cut(Part.makeCylinder(4, 12, FreeCAD.Vector(40, 20, -1)))
plate = plate.cut(Part.makeBox(20, 8, 12, FreeCAD.Vector(20, 16, -1)))
holes, curved = fc_common.detect_holes(plate)
check("count", len(holes), 1)
check("kind", kinds(holes), ["slot"])
check("width", round(holes[0]["width"], 3), 8.0)
check("length", round(holes[0]["length"], 3), 28.0)
check("id", holes[0]["id"], "S1")

say("counterbore stays two coaxial bores")
cbor = box(40, 40, 10)
cbor = cbor.cut(Part.makeCylinder(3, 12, FreeCAD.Vector(20, 20, -1)))
cbor = cbor.cut(Part.makeCylinder(5, 5, FreeCAD.Vector(20, 20, 5)))
holes, curved = fc_common.detect_holes(cbor)
check("count", len(holes), 2)
check("diameters", sorted(round(h["diameter"], 3) for h in holes), [6.0, 10.0])

say("bore plus a partial cylinder (the 280004 shape class)")
ring = Part.makeCylinder(29.076, 19.079)
ring = ring.cut(Part.makeCylinder(26.87, 19.079, FreeCAD.Vector(0, 0.004, 0),
                                 FreeCAD.Vector(0, 0, 1)))
ring = ring.cut(Part.makeCylinder(1.75, 30, FreeCAD.Vector(-5, 29.062831, 0),
                                 FreeCAD.Vector(1, 0, 0)))
holes, curved = fc_common.detect_holes(ring)
check("bore count", len(holes), 1)
check("bore diameter", round(holes[0]["diameter"], 2), 53.74)
check("curved count", len(curved), 1)
check("curved diameter", round(curved[0]["diameter"], 3), 3.5)
check("curved is partial", curved[0]["coverage"] < 0.5, True)

print("\n%d failure(s)" % len(FAILED))
sys.stdout.flush()
sys.exit(1 if FAILED else 0)
