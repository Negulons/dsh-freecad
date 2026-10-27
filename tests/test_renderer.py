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


if __name__ == "__main__":
    unittest.main(verbosity=2)
