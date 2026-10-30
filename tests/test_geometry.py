"""Import / measure / edit / drawing fixtures that need FreeCAD.

Not part of CI (no FreeCAD there).  Run by hand:

    freecadcmd tests/test_geometry.py

Each block is a regression found against FreeCAD 1.1.4 on Windows.
"""
import math
import os
import re
import shutil
import sys
import tempfile

_here = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
sys.path.insert(0, os.path.join(os.path.dirname(_here), "dsh"))

import FreeCAD  # noqa: E402
import Import  # noqa: E402
import Part  # noqa: E402
import fc_common as C  # noqa: E402
import fc_render as R  # noqa: E402
# fc_worker calls main() on import; without the request/result environment it
# prints one line to stderr and returns, leaving the functions usable.
import fc_worker as W  # noqa: E402

V = FreeCAD.Vector
FAILED = []
TMP = tempfile.mkdtemp(prefix="dsh-freecad-geom-")


def say(*args):
    print(*args, flush=True)


def check(name, got, want):
    ok = got == want
    say(("  ok   " if ok else "  FAIL ") + name + ": %r (want %r)" % (got, want))
    if not ok:
        FAILED.append(name)


def bbox6(shape):
    b = shape.BoundBox
    return [round(v, 3) for v in (b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax)]


def two_part_step():
    """Base plate + pin as two top-level objects (imports as an App::Part)."""
    path = os.path.join(TMP, "two_parts.step")
    doc = FreeCAD.newDocument("TwoParts")
    a = doc.addObject("Part::Feature", "Base")
    a.Shape = Part.makeBox(50, 50, 5)
    a.Label = "Base_Plate"
    b = doc.addObject("Part::Feature", "Pin")
    b.Shape = Part.makeCylinder(3, 20, V(25, 25, 5))
    b.Label = "Locating_Pin"
    doc.recompute()
    Import.export([a, b], path)
    FreeCAD.closeDocument(doc.Name)
    return path


say("multi-part STEP: origin features and containers are not parts")
path = two_part_step()
doc, entries, shape = C.import_cad(path)
check("entries", sorted(e["label"] for e in entries), ["Base_Plate", "Locating_Pin"])
check("volume", round(shape.Volume, 3), round(50 * 50 * 5 + math.pi * 9 * 20, 3))
check("bbox", bbox6(shape), [0.0, 0.0, 0.0, 50.0, 50.0, 25.0])
FreeCAD.closeDocument(doc.Name)

say("nested placement is applied once (App::Part at +100 X, child at +50 Y)")
doc = FreeCAD.newDocument("Nested")
asm = doc.addObject("App::Part", "Asm")
asm.Placement.Base = V(100, 0, 0)
box = doc.addObject("Part::Feature", "Box")
box.Shape = Part.makeBox(10, 10, 10)
box.Placement.Base = V(0, 50, 0)
asm.addObject(box)
doc.recompute()
check("global bbox", bbox6(C._object_global_shape(box)), [100.0, 50.0, 0.0, 110.0, 60.0, 10.0])
FreeCAD.closeDocument(doc.Name)

say("multi-part STEP: edit, inspect and drawing all work")
out = os.path.join(TMP, "two_parts_edited.step")
result = W.do_edit({"input": path, "output": out,
                    "operations": [{"type": "translate", "vector": [1, 0, 0]}]})
check("edit volume kept", round(result["after"]["volume"], 3), round(result["before"]["volume"], 3))
check("edit warns about merging", any("2 parts" in w for w in result["warnings"]), True)
check("edited file exists", os.path.isfile(out), True)
info = W.do_inspect({"input": path})
check("inspect objectCount", info["objectCount"], 2)
drawing = W.do_drawing({"input": path, "outputDir": os.path.join(TMP, "dwg"),
                        "formats": ["svg", "dxf"]})
check("drawing formats", sorted(drawing["files"]), ["dxf", "svg"])

say("slot + round holes are numbered S1, H1, H2")
plate = Part.makeBox(100, 40, 10)
plate = plate.cut(Part.makeCylinder(4, 12, V(20, 20, -1)))
plate = plate.cut(Part.makeCylinder(4, 12, V(40, 20, -1)))
plate = plate.cut(Part.makeBox(20, 8, 12, V(20, 16, -1)))
plate = plate.cut(Part.makeCylinder(3, 12, V(70, 20, -1)))
plate = plate.cut(Part.makeCylinder(3, 12, V(85, 20, -1)))
holes, _ = C.detect_holes(plate)
check("ids", [h["id"] for h in holes], ["S1", "H1", "H2"])

say("angles keep 45 and 135 apart")
p0, p1 = V(0, 0, 0), V(10, 0, 0)
c45 = math.cos(math.radians(45))


def edge_angle(direction):
    wire = Part.Wire([Part.makeLine(p0, p1), Part.makeLine(p1, p1 + direction * 10)])
    return C.measure_items(wire, [{"kind": "angle", "a": {"edge": 1}, "b": {"edge": 2}}])["measurements"][0]


check("edges at 135", edge_angle(V(c45, c45, 0))["value"], 135.0)
check("edges at 45", edge_angle(V(-c45, c45, 0))["value"], 45.0)
check("edges at 90", edge_angle(V(0, 1, 0))["value"], 90.0)
skew = Part.makeCompound([Part.makeLine(V(0, 0, 0), V(10, 0, 0)),
                          Part.makeLine(V(0, 5, 3), V(-10, 15, 3))])
m = C.measure_items(skew, [{"kind": "angle", "a": {"edge": 1}, "b": {"edge": 2}}])["measurements"][0]
check("disjoint edges fold to the acute angle", (m["value"], m["sharedVertex"]), (45.0, False))

block = Part.makeBox(20, 20, 20)
chamfered = block.makeChamfer(5, [e for e in block.Edges
                                  if abs(e.CenterOfMass.x - 20) < 1e-6 and abs(e.CenterOfMass.z - 20) < 1e-6])


def face_index(shape, normal):
    for i, f in enumerate(shape.Faces, 1):
        n = C._face_normal_sample(f)[1]
        if (n - normal).Length < 1e-6:
            return i
    raise AssertionError("no face with normal %s" % normal)


top = face_index(chamfered, V(0, 0, 1))
slope = face_index(chamfered, V(c45, 0, c45))
bottom = face_index(chamfered, V(0, 0, -1))
m = C.measure_items(chamfered, [{"kind": "angle", "a": {"face": top}, "b": {"face": slope}},
                                {"kind": "angle", "a": {"face": top}, "b": {"face": bottom}}])
check("chamfer face: plane angle", m["measurements"][0]["value"], 45.0)
check("chamfer face: normal angle", m["measurements"][0]["normalAngle"], 45.0)
check("opposite faces: normals 180 apart", m["measurements"][1]["normalAngle"], 180.0)

say("demo bracket: unchanged results, standard scale, DXF right way up")
sample = os.path.join(os.path.dirname(_here), "examples", "demo_bracket.step")
info = W.do_inspect({"input": sample})
check("demo holes", len(info["holes"]), 5)
check("demo ids", [h["id"] for h in info["holes"]], ["H1", "H2", "H3", "H4", "H5"])
check("demo size", info["bbox"]["size"], [100.0, 60.0, 37.0])
drawing = W.do_drawing({"input": sample, "outputDir": os.path.join(TMP, "demo"), "formats": ["dxf"]})
check("demo scale", drawing["scaleLabel"], "1:2")
dxf = open(drawing["files"]["dxf"], encoding="gbk").read()


def dxf_text_y(label):
    block = dxf[:dxf.index(label)].rsplit("\nTEXT\n", 1)[1]
    return float(re.search(r"\n20\n([-\d.]+)\n", block).group(1))


check("header above title block", dxf_text_y("FreeCAD") > dxf_text_y("材料"), True)
check("front view above top view (first angle)", dxf_text_y("主视图") > dxf_text_y("俯视图"), True)

shutil.rmtree(TMP, ignore_errors=True)
print("\n%d failure(s)" % len(FAILED))
sys.stdout.flush()
sys.exit(1 if FAILED else 0)
