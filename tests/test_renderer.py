"""Renderer unit tests that need neither FreeCAD nor matplotlib.

Run with:  python tests/test_renderer.py
The renderer is a plain module (no FreeCAD import at module level), so the
geometry-free layout logic can be checked on any Python 3.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dsh"))

import fc_render as R  # noqa: E402


def make_holes(count, diameter=6.0, through=True, depth=8.0):
    holes = []
    for i in range(count):
        holes.append({
            "id": "H%d" % (i + 1),
            "diameter": diameter,
            "radius": diameter / 2.0,
            "axisName": "Z",
            "through": through,
            "depth": depth,
            "center": [i * 10.0, 0.0, 0.0],
        })
    return holes


def texts(scene):
    return [item["text"] for item in scene.items if item["kind"] == "text"]


def layer_items(scene, layer):
    return [item for item in scene.items if item.get("layer") == layer]


class HoleTableTests(unittest.TestCase):
    def test_five_holes_fit_one_block(self):
        scene = R.Scene(*R.SHEETS["A3"])
        R._hole_table(scene, make_holes(5), scene.width, scene.height)
        labels = texts(scene)
        self.assertEqual(labels.count("孔号"), 1)
        self.assertNotIn("共 5 孔", " ".join(labels))
        for i in range(1, 6):
            self.assertIn("H%d" % i, labels)

    def test_twelve_holes_page_into_two_blocks(self):
        scene = R.Scene(*R.SHEETS["A3"])
        holes = make_holes(12)
        R._hole_table(scene, holes, scene.width, scene.height)
        labels = texts(scene)
        # every hole reaches the sheet: the old code silently kept ten
        for i in range(1, 13):
            self.assertIn("H%d" % i, labels)
        self.assertEqual(labels.count("孔号"), 2)
        self.assertTrue((("共 12 孔") in " ".join(labels)))

    def test_many_holes_never_exceed_three_blocks(self):
        scene = R.Scene(*R.SHEETS["A3"])
        holes = make_holes(40)
        R._hole_table(scene, holes, scene.width, scene.height)
        labels = texts(scene)
        self.assertEqual(labels.count("孔号"), 3)
        for i in range(1, 41):
            self.assertIn("H%d" % i, labels)

    def test_table_stays_inside_the_sheet(self):
        scene = R.Scene(*R.SHEETS["A3"])
        R._hole_table(scene, make_holes(24), scene.width, scene.height)
        left = min(p[0] for item in scene.items if item["kind"] == "polyline"
                   for p in item["points"])
        right = max(p[0] for item in scene.items if item["kind"] == "polyline"
                    for p in item["points"])
        self.assertGreaterEqual(left, R.MARGIN)
        self.assertLessEqual(right, scene.width - R.MARGIN)


class HiddenLineTests(unittest.TestCase):
    def make_view(self, hidden):
        return {
            "width": 20.0,
            "height": 10.0,
            "label": "主视图",
            "labelEn": "FRONT",
            "visible": [[(0.0, 0.0), (20.0, 0.0)], [(0.0, 0.0), (0.0, 10.0)]],
            "hidden": hidden,
        }

    def test_hidden_edges_on_top_of_visible_ones_are_dropped(self):
        # Symmetric parts hand OCCT's hidden geometry straight back as a copy
        # of the visible outline; drawing both is what produced doubled lines.
        view = self.make_view([[(0.0, 0.0), (20.0, 0.0)]])
        scene = R.Scene(*R.SHEETS["A3"])
        R._place_view(scene, view, 50.0, 50.0, 1.0, hidden=True)
        self.assertEqual(layer_items(scene, "HIDDEN"), [])
        self.assertEqual(scene.hiddenSkipped, 1)
        self.assertTrue(layer_items(scene, "OUTLINE"))

    def test_genuine_hidden_edges_are_kept(self):
        view = self.make_view([[(4.0, 2.0), (16.0, 2.0)]])
        scene = R.Scene(*R.SHEETS["A3"])
        R._place_view(scene, view, 50.0, 50.0, 1.0, hidden=True)
        hidden = layer_items(scene, "HIDDEN")
        self.assertEqual(len(hidden), 1)
        self.assertEqual(hidden[0]["dash"], "3,1.5")
        self.assertEqual(scene.hiddenSkipped, 0)

    def test_reversed_endpoints_still_match(self):
        view = self.make_view([[(20.0, 0.0), (0.0, 0.0)]])
        scene = R.Scene(*R.SHEETS["A3"])
        R._place_view(scene, view, 50.0, 50.0, 1.0, hidden=True)
        self.assertEqual(layer_items(scene, "HIDDEN"), [])

    def test_hidden_matching_a_sharp_visible_edge_is_dropped(self):
        # Sharp edges come back as exact lines, not polylines; a back face that
        # projects onto the same place must still be recognised as a duplicate.
        view = self.make_view([[(10.0, 0.0), (20.0, 5.0)]])
        view["exactVisible"] = [
            {"type": "line", "p1": (10.0, 0.0), "p2": (20.0, 5.0)},
        ]
        view["exactHidden"] = [
            {"type": "line", "p1": (20.0, 5.0), "p2": (10.0, 0.0)},
        ]
        scene = R.Scene(*R.SHEETS["A3"])
        R._place_view(scene, view, 50.0, 50.0, 1.0, hidden=True)
        self.assertEqual(layer_items(scene, "HIDDEN"), [])
        self.assertEqual(scene.hiddenSkipped, 2)

    def test_hidden_circle_matching_visible_circle_is_dropped(self):
        view = self.make_view([])
        view["exactVisible"] = [{"type": "circle", "c": (5.0, 5.0), "r": 2.0}]
        view["exactHidden"] = [{"type": "circle", "c": (5.0, 5.0), "r": 2.0}]
        scene = R.Scene(*R.SHEETS["A3"])
        R._place_view(scene, view, 50.0, 50.0, 1.0, hidden=True)
        self.assertEqual(layer_items(scene, "HIDDEN"), [])
        self.assertEqual(scene.hiddenSkipped, 1)

    def test_hidden_off_draws_nothing_extra(self):
        view = self.make_view([[(4.0, 2.0), (16.0, 2.0)]])
        scene = R.Scene(*R.SHEETS["A3"])
        R._place_view(scene, view, 50.0, 50.0, 1.0, hidden=False)
        self.assertEqual(layer_items(scene, "HIDDEN"), [])


def _dxf_entities(path):
    """Parse the ENTITIES section of an R12 DXF into (type, {code: [values]})."""
    with open(path, encoding="gbk") as fh:
        rows = fh.read().split("\n")
    pairs = list(zip(rows[0::2], rows[1::2]))
    start = next(i for i, (c, v) in enumerate(pairs) if c == "2" and v == "ENTITIES")
    out = []
    for code, value in pairs[start + 1:]:
        if code == "0":
            if value in ("ENDSEC", "EOF"):
                break
            out.append((value, {}))
        elif out:
            out[-1][1].setdefault(code, []).append(value)
    return out


class DxfOrientationTests(unittest.TestCase):
    """The scene is y-down (like SVG); DXF is y-up.  0.4.2 wrote y unchanged."""

    def render(self, scene):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "t.dxf")
        R.render_dxf(scene, path)
        return _dxf_entities(path)

    def test_top_of_page_has_the_largest_dxf_y(self):
        scene = R.Scene(*R.SHEETS["A3"])
        scene.text(20, 19, "HEADER")            # near the top edge of the sheet
        scene.text(380, 280, "TITLE")           # near the bottom edge
        scene.line(10, 10, 410, 10)             # top frame line
        scene.circle(50, 250, 5)
        ents = self.render(scene)
        texts = {d["1"][0]: float(d["20"][0]) for t, d in ents if t == "TEXT"}
        self.assertAlmostEqual(texts["HEADER"], 297 - 19)
        self.assertAlmostEqual(texts["TITLE"], 297 - 280)
        self.assertGreater(texts["HEADER"], texts["TITLE"])
        line = next(d for t, d in ents if t == "LINE")
        self.assertEqual((float(line["20"][0]), float(line["21"][0])), (287.0, 287.0))
        circle = next(d for t, d in ents if t == "CIRCLE")
        self.assertAlmostEqual(float(circle["20"][0]), 47.0)

    def test_polyline_vertices_are_flipped(self):
        scene = R.Scene(*R.SHEETS["A4"])
        scene.polyline([(0, 0), (10, 20)])
        ents = self.render(scene)
        ys = [float(d["20"][0]) for t, d in ents if t == "VERTEX"]
        self.assertEqual(ys, [210.0, 190.0])

    def test_vertical_dimension_text_reads_bottom_to_top(self):
        # rotation=90 is counter-clockwise on the sheet (as PDF/PNG draw it);
        # DXF angles are counter-clockwise too once y points up.
        scene = R.Scene(*R.SHEETS["A3"])
        R.dim_v(scene, 50, 100, 200, "37")
        ents = self.render(scene)
        label = next(d for t, d in ents if t == "TEXT" and d["1"][0] == "37")
        self.assertEqual(float(label["50"][0]), 90.0)

    def test_text_alignment_stays_on_the_baseline(self):
        scene = R.Scene(*R.SHEETS["A3"])
        scene.text(100, 100, "mid", anchor="middle")
        scene.text(100, 100, "end", anchor="end")
        ents = self.render(scene)
        for _, d in (e for e in ents if e[0] == "TEXT"):
            self.assertEqual(d["73"], ["0"])
            # the alignment point is the same flipped point
            self.assertEqual(float(d["21"][0]), 297 - 100)


class SvgRotationTests(unittest.TestCase):
    def test_svg_rotation_matches_the_pdf_direction(self):
        import tempfile
        scene = R.Scene(*R.SHEETS["A3"])
        R.dim_v(scene, 50, 100, 200, "37")
        path = os.path.join(tempfile.mkdtemp(), "t.svg")
        R.render_svg(scene, path)
        with open(path, encoding="utf-8") as fh:
            svg = fh.read()
        # SVG rotate() is clockwise in its y-down space: CCW on the sheet is -90
        self.assertIn('transform="rotate(-90 ', svg)


class HoleTableColumnTests(unittest.TestCase):
    def table_rows(self, holes):
        scene = R.Scene(*R.SHEETS["A3"])
        R._hole_table(scene, holes, scene.width, scene.height)
        labels = texts(scene)
        start = labels.index("孔号")
        header = labels[start:start + 8]
        rows = labels[start + 8:]
        return header, [rows[i:i + 8] for i in range(0, len(rows), 8)]

    def test_columns_name_the_coordinate_they_hold(self):
        holes = [
            {"id": "H1", "diameter": 5, "axisName": "X", "through": True,
             "depth": 40, "center": [20.0, 10.0, 15.0]},
            {"id": "H2", "diameter": 6, "axisName": "Z", "through": True,
             "depth": 10, "center": [30.0, 12.0, 5.0]},
        ]
        header, rows = self.table_rows(holes)
        self.assertEqual(header[5:], ["X", "Y", "Z"])
        # X-axis hole: X is along the axis, so it is blank; Y=10, Z=15
        self.assertEqual(rows[0][5:], ["—", "10", "15"])
        self.assertEqual(rows[1][5:], ["30", "12", "—"])

    def test_table_width_is_unchanged(self):
        scene = R.Scene(*R.SHEETS["A3"])
        R._hole_table(scene, make_holes(3), scene.width, scene.height, x=100.0, y=60.0)
        frame = [i for i in scene.items if i["kind"] == "polyline" and i.get("closed")][0]
        xs = [p[0] for p in frame["points"]]
        self.assertAlmostEqual(max(xs) - min(xs), 117.0)


class ScaleTests(unittest.TestCase):
    # GB/T 14690: preferred and permitted scales only
    ALLOWED = {"5:1", "4:1", "2.5:1", "2:1", "1:1", "1:1.5", "1:2", "1:2.5", "1:3",
               "1:4", "1:5", "1:6", "1:10", "1:15", "1:20", "1:25", "1:30", "1:40",
               "1:50"}

    def test_every_auto_scale_is_a_standard_one(self):
        labels = {R.scale_label(s) for s in R.STANDARD_SCALES}
        self.assertEqual(labels, self.ALLOWED)

    def test_choose_scale_never_returns_an_odd_ratio(self):
        # The bundled demo bracket (block about 1.7x the sheet area at 1:1)
        # used to come out at 1:1.67.
        for size in (5, 37, 60, 100, 180, 260, 400, 900, 3000, 9000):
            scale = R.choose_scale("A3", lambda s, size=size: (size * 2.4 * s, size * 1.4 * s))
            self.assertIn(R.scale_label(scale), self.ALLOWED, size)

    def test_largest_fitting_scale_wins(self):
        # fits at 1:1 -> 1:1, not 1:1.5
        self.assertEqual(R.scale_label(R.choose_scale("A3", lambda s: (300 * s, 150 * s))), "1:1")
        # 1:1 too wide, 1:1.5 fits
        self.assertEqual(R.scale_label(R.choose_scale("A3", lambda s: (450 * s, 150 * s))), "1:1.5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
