"""2D drawing scene, SVG/DXF/PDF/PNG renderers for the FreeCAD plugin.

Everything is laid out in millimetres on a top-left-origin page.  The scene is
renderer-neutral so the same drawing can be exported to several formats.
"""
from __future__ import annotations

import datetime
import math
import os
import re
from xml.sax.saxutils import escape

SHEETS = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
}
MARGIN = 10.0
GAP = 18.0
INK = "#111111"
HIDDEN = "#777777"
DIM = "#1a1a1a"
CENTER = "#555555"
TITLE_FONT = "Microsoft YaHei, SimHei, Arial, sans-serif"
CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\msyhbd.ttc",
]


class Scene:
    def __init__(self, width, height):
        self.width = float(width)
        self.height = float(height)
        self.items = []

    def line(self, x1, y1, x2, y2, width=0.25, color=INK, dash=None, layer="OUTLINE"):
        self.items.append({"kind": "line", "p1": (float(x1), float(y1)),
                           "p2": (float(x2), float(y2)), "width": width,
                           "color": color, "dash": dash, "layer": layer})

    def polyline(self, points, width=0.35, color=INK, dash=None, closed=False,
                 fill=None, layer="OUTLINE"):
        pts = [(float(x), float(y)) for x, y in points]
        if len(pts) < 2:
            return
        self.items.append({"kind": "polyline", "points": pts, "width": width,
                           "color": color, "dash": dash, "closed": closed,
                           "fill": fill, "layer": layer})

    def circle(self, x, y, r, width=0.35, color=INK, dash=None, layer="OUTLINE"):
        self.items.append({"kind": "circle", "c": (float(x), float(y)),
                           "r": float(r), "width": width, "color": color,
                           "dash": dash, "layer": layer})

    def text(self, x, y, text, size=3.5, color=INK, anchor="start",
             rotation=0.0, bold=False, layer="TEXT"):
        self.items.append({"kind": "text", "p": (float(x), float(y)),
                           "text": str(text), "size": float(size),
                           "color": color, "anchor": anchor,
                           "rotation": float(rotation), "bold": bold,
                           "layer": layer})

    def rect(self, x, y, w, h, width=0.35, color=INK, fill=None, layer="FRAME"):
        self.polyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)],
                      width=width, color=color, closed=True, fill=fill, layer=layer)


def fmt_num(value):
    s = "%.2f" % float(value)
    s = s.rstrip("0").rstrip(".")
    return s


def scale_label(scale):
    if scale >= 1:
        if abs(scale - round(scale)) < 1e-9:
            return "%d:1" % int(round(scale))
        return "%s:1" % fmt_num(scale)
    inv = 1.0 / scale
    if abs(inv - round(inv)) < 1e-9:
        return "1:%d" % int(round(inv))
    return "1:%s" % fmt_num(inv)


def choose_scale(sheet, dims):
    """Pick the largest ISO-like scale that fits the available drawing area."""
    W, H = SHEETS.get(sheet, SHEETS["A3"])
    title_top = H - 48.0
    avail_w = W - 2 * MARGIN - 18.0
    avail_h = title_top - MARGIN - 22.0
    scales = [4.0, 3.0, 2.5, 2.0, 1.5, 1.0, 0.8, 0.7, 0.6, 0.5, 0.4,
              0.35, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05]
    for s in scales:
        total_w, total_h = dims(s)
        if total_w <= avail_w and total_h <= avail_h:
            return s
    return 0.05


def _arrow(scene, x, y, dx, dy, size=2.2, color=DIM):
    """Small open arrowhead at (x,y), pointing in direction (dx,dy)."""
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    # two swept-back wings
    a = math.radians(22)
    for sign in (1, -1):
        wx = -ux * math.cos(a) + sign * -uy * math.sin(a)
        wy = -uy * math.cos(a) + sign * ux * math.sin(a)
        scene.line(x, y, x + wx * size, y + wy * size, 0.2, color, layer="DIM")


def dim_h(scene, x1, x2, y, label, ext_from=None, color=DIM):
    """Horizontal dimension at y, extension lines from ext_from (optional)."""
    if x2 < x1:
        x1, x2 = x2, x1
    scene.line(x1, y, x2, y, 0.22, color, layer="DIM")
    _arrow(scene, x1, y, -1, 0, color=color)
    _arrow(scene, x2, y, 1, 0, color=color)
    if ext_from is not None:
        scene.line(x1, ext_from, x1, y + 2.0, 0.18, color, layer="DIM")
        scene.line(x2, ext_from, x2, y + 2.0, 0.18, color, layer="DIM")
    scene.text((x1 + x2) * 0.5, y - 1.4, label, 3.0, color, "middle", layer="DIM")


def dim_v(scene, y1, y2, x, label, ext_from=None, color=DIM):
    if y2 < y1:
        y1, y2 = y2, y1
    scene.line(x, y1, x, y2, 0.22, color, layer="DIM")
    _arrow(scene, x, y1, 0, -1, color=color)
    _arrow(scene, x, y2, 0, 1, color=color)
    if ext_from is not None:
        scene.line(ext_from, y1, x + 2.0, y1, 0.18, color, layer="DIM")
        scene.line(ext_from, y2, x + 2.0, y2, 0.18, color, layer="DIM")
    scene.text(x - 1.4, (y1 + y2) * 0.5, label, 3.0, color, "middle",
               rotation=90, layer="DIM")


def _place_view(scene, view, x, y, scale, hidden=False):
    """Draw one projected view; (x,y) is the top-left of its extents."""
    def tx(p):
        return x + p[0] * scale, y + (view["height"] - p[1]) * scale

    def draw_exact(entities, width, color, dash, layer):
        for entity in entities:
            if entity["type"] == "line":
                p1 = tx(entity["p1"])
                p2 = tx(entity["p2"])
                scene.line(p1[0], p1[1], p2[0], p2[1], width, color, dash, layer)
            elif entity["type"] == "circle":
                cx, cy = tx(entity["c"])
                scene.circle(cx, cy, entity["r"] * scale, width, color, dash, layer)

    for poly in view["visible"]:
        scene.polyline([tx(p) for p in poly], 0.38, INK, layer="OUTLINE")
    draw_exact(view.get("exactVisible") or [], 0.38, INK, None, "OUTLINE")
    if hidden:
        for poly in view["hidden"]:
            scene.polyline([tx(p) for p in poly], 0.22, HIDDEN,
                           dash="3,1.5", layer="HIDDEN")
        draw_exact(view.get("exactHidden") or [], 0.22, HIDDEN,
                   "3,1.5", "HIDDEN")
    # view label
    scene.text(x + view["width"] * scale * 0.5,
               y + view["height"] * scale + 7.0,
               "%s  %s" % (view["label"], view["labelEn"]), 3.0, INK, "middle",
               layer="TEXT")
    return tx


def _hole_point(hole, view_name, view):
    # Lazy import keeps this module usable without FreeCAD for tests.
    from fc_common import project_point
    return project_point(hole["center"], view_name, view["rawBBox"])


def add_hole_centers(scene, view, holes, view_name, tx, scale):
    for hole in holes:
        if hole.get("axisName") != {"top": "Z", "bottom": "Z", "front": "Y",
                                     "rear": "Y", "right": "X", "left": "X"}.get(view_name):
            continue
        try:
            p = _hole_point(hole, view_name, view)
        except Exception:
            continue
        cx, cy = tx(p)
        r = max(hole["radius"] * scale, 2.5) + 3.0
        scene.line(cx - r, cy, cx + r, cy, 0.18, CENTER, dash="8,2,1,2",
                   layer="CENTER")
        scene.line(cx, cy - r, cx, cy + r, 0.18, CENTER, dash="8,2,1,2",
                   layer="CENTER")


def _group_holes(holes):
    groups = {}
    order = []
    for h in holes:
        key = (round(h["diameter"], 4), bool(h["through"]),
               round(h.get("depth", 0), 3) if not h["through"] else None)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(h)
    return [(key, groups[key]) for key in order]


def _hole_callout(scene, x, y, text):
    scene.line(x - 5.0, y + 1.2, x, y, 0.18, DIM, layer="DIM")
    scene.text(x - 1.0, y - 0.3, text, 2.8, DIM, "end", layer="DIM")


def _draw_hole_labels(scene, view, holes, view_name, tx, scale, x_right, y_top):
    want = {"top": "Z", "bottom": "Z", "front": "Y", "rear": "Y",
            "right": "X", "left": "X"}.get(view_name)
    if not want:
        return
    groups = [(k, hs) for k, hs in _group_holes(holes) if hs[0].get("axisName") == want]
    if not groups:
        return
    lx = x_right + 10.0
    ly = y_top + 4.0
    for key, hs in groups:
        d = key[0]
        if key[1]:
            label = ("%d×Ø%s THRU" % (len(hs), fmt_num(d)))
        else:
            label = ("%d×Ø%s ↧%s" % (len(hs), fmt_num(d), fmt_num(key[2])))
        try:
            hp = _hole_point(hs[0], view_name, view)
            hx, hy = tx(hp)
        except Exception:
            hx, hy = lx - 8, ly + 2
        _hole_callout(scene, lx, ly, label)
        scene.line(lx - 8.0, ly + 1.2, hx, hy, 0.16, DIM, dash="2,1.5",
                   layer="DIM")
        ly += 6.5


def _title_block(scene, W, H, meta, scale, sheet, filename):
    tw = 168.0 if W > 350 else 145.0
    th = 32.0
    # Keep the block inside the 3 mm inner frame: a title block or table that
    # crosses the frame reads as a drafting error.
    inner_right = W - MARGIN - 3.0
    inner_top = H - MARGIN - 3.0
    x = inner_right - tw
    y = inner_top - th
    scene.rect(x, y, tw, th, 0.5, INK, layer="TITLE")
    # rows: 5 + 9 + 9 + 9
    scene.line(x, y + 10, x + tw, y + 10, 0.3, INK, layer="TITLE")
    scene.line(x, y + 20, x + tw, y + 20, 0.25, INK, layer="TITLE")
    scene.line(x, y + 26, x + tw, y + 26, 0.25, INK, layer="TITLE")
    if tw < 160:
        split1 = x + 84
        split2 = x + 110
    else:
        split1 = x + 104
        split2 = x + 132
    scene.line(split1, y + 10, split1, y + th, 0.25, INK, layer="TITLE")
    scene.line(split2, y + 10, split2, y + th, 0.25, INK, layer="TITLE")
    scene.text(x + 3, y + 7.0, meta.get("title") or "二维加工图", 5.0, INK, "start",
               bold=True, layer="TITLE")
    scene.text(x + tw - 3, y + 7.0, meta.get("subtitle") or filename, 3.0, INK,
               "end", layer="TITLE")
    scene.text(x + 3, y + 17.0, "材料  %s" % (meta.get("material") or "—"), 3.2,
               INK, layer="TITLE")
    scene.text(split1 + 3, y + 17.0, "比例  %s" % scale_label(scale), 3.2, INK,
               layer="TITLE")
    scene.text(split2 + 3, y + 17.0, "图号  %s" % (meta.get("drawingNo") or "—"),
               3.0, INK, layer="TITLE")
    scene.text(x + 3, y + 24.0, "未注公差 GB/T 1804-m    单位 mm    去除毛刺", 2.7,
               INK, layer="TITLE")
    bottom_y = y + 29.2
    scene.text(x + 3, bottom_y, "投影法  第一角法", 2.7, INK, layer="TITLE")
    scene.text(split1 + 3, bottom_y, "日期  %s" % datetime.date.today().isoformat(),
               2.7, INK, layer="TITLE")
    scene.text(split2 + 3, bottom_y, "张  1/1", 2.7, INK, layer="TITLE")


def _hole_xy(hole):
    ax = hole.get("axisName")
    c = hole.get("center") or [0, 0, 0]
    if ax == "Z":
        return c[0], c[1]
    if ax == "X":
        return c[1], c[2]
    if ax == "Y":
        return c[0], c[2]
    return None, None


def _hole_table(scene, holes, W, H, bbox=None, x=None, y=None):
    """A compact hole table, normally above the title block; A4 places it top-right."""
    if not holes:
        return
    rows = list(holes[:10])
    col_w = [13.0, 15.0, 10.0, 9.0, 18.0, 26.0, 26.0]
    total_w = sum(col_w)
    row_h = 6.5
    title_h = 8.0
    table_h = title_h + row_h * (len(rows) + 1)
    inner_right = W - MARGIN - 3.0
    inner_top = H - MARGIN - 3.0
    if x is None:
        x = inner_right - total_w
    if y is None:
        y = inner_top - 32.0 - 8.0 - table_h
    scene.text(x, y - 3.0, "孔表 / HOLE TABLE", 3.0, INK, "start", bold=True)
    scene.rect(x, y, total_w, table_h, 0.35, INK, layer="TITLE")
    scene.line(x, y + title_h, x + total_w, y + title_h, 0.25, INK, layer="TITLE")
    headers = ["孔号", "直径", "数量", "轴", "深度", "X", "Y"]
    spans = {}
    if bbox is not None:
        spans = {"X": bbox.XLength, "Y": bbox.YLength, "Z": bbox.ZLength}
    for i, (cw, text) in enumerate(zip(col_w, headers)):
        cx = x + sum(col_w[:i])
        scene.text(cx + cw * 0.5, y + 5.6, text, 2.7, INK, "middle", layer="TITLE")
    for r, hole in enumerate(rows):
        ry = y + title_h + row_h * r
        scene.line(x, ry, x + total_w, ry, 0.18, INK, layer="TITLE")
        hx, hy = _hole_xy(hole)
        span = spans.get(hole.get("axisName"))
        d = float(hole.get("depth") or 0)
        # A local through-hole (e.g. through a 12 mm plate on a taller part)
        # must still state its effective cutting depth; only a hole spanning
        # the whole part is simply marked 通.
        depth = "通" if (hole.get("through") and span and d >= span - 1e-3) else fmt_num(d)
        values = [
            hole.get("id") or "",
            fmt_num(hole.get("diameter", 0)),
            "1",
            hole.get("axisName") or "",
            depth,
            fmt_num(hx) if hx is not None else "—",
            fmt_num(hy) if hy is not None else "—",
        ]
        for i, (cw, value) in enumerate(zip(col_w, values)):
            cx = x + sum(col_w[:i])
            scene.text(cx + cw * 0.5, ry + row_h - 2.0, value, 2.6, INK,
                       "middle", layer="TITLE")
    for i in range(1, len(col_w)):
        cx = x + sum(col_w[:i])
        scene.line(cx, y + title_h, cx, y + table_h, 0.18, INK, layer="TITLE")


def build_scene(shape, views, holes, meta, options):
    sheet = str(options.get("sheet") or "A3").upper()
    W, H = SHEETS.get(sheet, SHEETS["A3"])
    hidden = bool(options.get("hiddenLines", False))
    view_names = [v for v in (options.get("views") or ["front", "top", "right", "iso"])
                  if v in views]
    # dedupe, preserve order
    seen = set()
    view_names = [v for v in view_names if not (v in seen or seen.add(v))]
    if not view_names:
        view_names = ["front"]
    front = views.get("front") or views[view_names[0]]
    top = views.get("top")
    right = views.get("right")

    def dims(scale):
        fw = front["width"] * scale
        fh = front["height"] * scale
        tw = top["width"] * scale if top else 0
        th = top["height"] * scale if top else 0
        rw = right["width"] * scale if right else 0
        rh = right["height"] * scale if right else 0
        iw = views["iso"]["width"] * scale if "iso" in views else 0
        ih = views["iso"]["height"] * scale if "iso" in views else 0
        total_w = rw + (GAP if rw else 0) + fw + (GAP + iw if iw else 0) + 40
        total_h = fh + (GAP + th if top else 0) + 24
        if "iso" in views:
            total_h = max(total_h, ih + 24)
        return total_w, total_h

    # A4 is narrow; use a compact left view block and put the hole table
    # top-right so it cannot collide with the views or the title block.
    compact = sheet == "A4"
    if compact:
        # A4 is intended for front + top only; extra views cannot fit beside
        # the table. Ignore right/iso here rather than overlapping content.
        view_names = [v for v in view_names if v in ("front", "top")]
        right = None if compact else right
        if not view_names:
            view_names = ["front"]
    scale = float(options.get("scale") or 0)
    if compact:
        # Fixed 1:2 keeps the compact A4 sheet collision-free.
        scale = 0.5
    elif scale <= 0:
        scale = choose_scale(sheet, dims)
    # center the block in the drawing area above the title block
    block_w, block_h = dims(scale)
    avail_w = W - 2 * MARGIN
    x0 = 50.0 if compact else max(MARGIN + 6, MARGIN + (avail_w - block_w) * 0.5 + 6)
    y0 = 48.0

    scene = Scene(W, H)
    scene.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN, 0.7, INK,
               layer="FRAME")
    scene.rect(MARGIN + 3, MARGIN + 3, W - 2 * MARGIN - 6, H - 2 * MARGIN - 6,
               0.25, INK, layer="FRAME")
    # filename / title strip
    scene.text(MARGIN + 7, MARGIN + 9, meta.get("header") or "FreeCAD 二维加工图",
               4.0, INK, "start", bold=True, layer="TEXT")
    scene.text(W - MARGIN - 7, MARGIN + 9,
               "%s   %s" % (meta.get("sourceName") or "", scale_label(scale)),
               3.0, INK, "end", layer="TEXT")

    positions = {}
    if right:
        rw, rh = right["width"] * scale, right["height"] * scale
        positions["right"] = (x0, y0 + (front["height"] * scale - rh) * 0.5)
        front_x = x0 + rw + GAP
    else:
        front_x = x0
    fw, fh = front["width"] * scale, front["height"] * scale
    positions["front"] = (front_x, y0)
    if top:
        tw, th = top["width"] * scale, top["height"] * scale
        positions["top"] = (front_x, y0 + fh + GAP)
    if "iso" in views:
        iw, ih = views["iso"]["width"] * scale, views["iso"]["height"] * scale
        ix = front_x + fw + GAP
        iy = y0
        positions["iso"] = (ix, iy)

    for name in view_names:
        if name not in positions:
            # place unknown views in a free row below
            positions[name] = (x0, y0 + block_h + 10)
        view = views[name]
        x, y = positions[name]
        tx = _place_view(scene, view, x, y, scale, hidden)
        if name != "iso":
            add_hole_centers(scene, view, holes, name, tx, scale)
            if options.get("dimensions", True):
                dim_h(scene, x, x + view["width"] * scale,
                      y + view["height"] * scale + 13.0,
                      fmt_num(view["width"]), ext_from=y + view["height"] * scale)
                dim_v(scene, y, y + view["height"] * scale,
                      x + view["width"] * scale + 14.0,
                      fmt_num(view["height"]), ext_from=x + view["width"] * scale)
    if compact:
        _hole_table(scene, holes, W, H, shape.BoundBox, x=W - MARGIN - 3.0 - 117.0, y=48.0)
    else:
        _hole_table(scene, holes, W, H, shape.BoundBox)

    # notes in the lower-left area, away from the title block
    note_y = H - 40.0
    scene.text(MARGIN + 8, note_y, "技术要求 / NOTES", 3.4, INK, bold=True)
    notes = [
        "1. 未注尺寸公差按 GB/T 1804-m，未注角度公差按 GB/T 11335-m。",
        "2. 锐边倒钝，去除毛刺；未注圆角 R0.5。",
        "3. 图中尺寸单位为 mm，第一角投影。",
    ]
    for i, note in enumerate(notes):
        scene.text(MARGIN + 8, note_y + 6.0 + i * 5.0, note, 2.8, INK)

    _title_block(scene, W, H, meta, scale, sheet, meta.get("sourceName") or "")
    return scene, scale


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def _svg_path(points, closed=False):
    d = "M %s %s" % (fmt_num(points[0][0]), fmt_num(points[0][1]))
    for x, y in points[1:]:
        d += " L %s %s" % (fmt_num(x), fmt_num(y))
    if closed:
        d += " Z"
    return d


def render_svg(scene, path):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" '
           'viewBox="0 0 %s %s">' % (fmt_num(scene.width), fmt_num(scene.height),
                                     fmt_num(scene.width), fmt_num(scene.height)),
           '<rect width="100%" height="100%" fill="#ffffff"/>']
    for item in scene.items:
        kind = item["kind"]
        if kind in ("line", "polyline"):
            if kind == "line":
                pts = [item["p1"], item["p2"]]
                closed = False
                fill = None
            else:
                pts = item["points"]
                closed = item["closed"]
                fill = item.get("fill")
            dash = ' stroke-dasharray="%s"' % item["dash"] if item["dash"] else ""
            fill_attr = ' fill="%s"' % fill if fill else ' fill="none"'
            out.append('<path d="%s" fill="%s" stroke="%s" stroke-width="%s"%s '
                       'stroke-linecap="round" stroke-linejoin="round"/>'
                       % (_svg_path(pts, closed), fill or "none", item["color"],
                          fmt_num(item["width"]), dash))
        elif kind == "circle":
            dash = ' stroke-dasharray="%s"' % item["dash"] if item["dash"] else ""
            out.append('<circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" '
                       'stroke-width="%s"%s/>'
                       % (fmt_num(item["c"][0]), fmt_num(item["c"][1]),
                          fmt_num(item["r"]), item["color"],
                          fmt_num(item["width"]), dash))
        elif kind == "text":
            anchor = {"start": "start", "middle": "middle", "end": "end"}.get(
                item["anchor"], "start")
            weight = ' font-weight="bold"' if item["bold"] else ""
            transform = ""
            if abs(item["rotation"]) > 1e-9:
                transform = ' transform="rotate(%s %s %s)"' % (
                    fmt_num(item["rotation"]), fmt_num(item["p"][0]),
                    fmt_num(item["p"][1]))
            out.append('<text x="%s" y="%s" font-family="%s" font-size="%s" '
                       'fill="%s" text-anchor="%s"%s%s>%s</text>'
                       % (fmt_num(item["p"][0]), fmt_num(item["p"][1]),
                          TITLE_FONT, fmt_num(item["size"]), item["color"],
                          anchor, weight, transform, escape(item["text"])))
    out.append("</svg>")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    return path


# ---------------------------------------------------------------------------
# DXF R12 (AC1009), GBK/ANSI_936
# ---------------------------------------------------------------------------

DXF_COLORS = {"OUTLINE": 7, "HIDDEN": 8, "CENTER": 8, "DIM": 1,
              "TEXT": 7, "FRAME": 7, "TITLE": 7}


def _dxf_text(s):
    s = str(s).replace("Ø", "%%c").replace("⌀", "%%c").replace("↧", "DP")
    return s.replace("\n", " ")


def render_dxf(scene, path):
    def pair(code, value):
        return "%s\n%s\n" % (code, value)

    def line_entity(x1, y1, x2, y2, layer="OUTLINE"):
        return ("0\nLINE\n8\n%s\n10\n%s\n20\n%s\n11\n%s\n21\n%s\n"
                % (layer, fmt_num(x1), fmt_num(y1), fmt_num(x2), fmt_num(y2)))

    def polyline_entity(points, closed, layer="OUTLINE"):
        # R12 POLYLINE keeps one projected edge as one CAD polyline instead
        # of exploding it into thousands of separate LINE entities.
        flag = 1 if closed else 0
        s = "0\nPOLYLINE\n8\n%s\n66\n1\n70\n%s\n" % (layer, flag)
        for px, py in points:
            s += "0\nVERTEX\n8\n%s\n10\n%s\n20\n%s\n30\n0\n" % (
                layer, fmt_num(px), fmt_num(py))
        s += "0\nSEQEND\n8\n%s\n" % layer
        return s

    def circle_entity(cx, cy, r, layer="OUTLINE"):
        return "0\nCIRCLE\n8\n%s\n10\n%s\n20\n%s\n40\n%s\n" % (
            layer, fmt_num(cx), fmt_num(cy), fmt_num(r))

    def text_entity(x, y, height, value, anchor="start", rotation=0.0,
                    layer="TEXT"):
        align = {"start": (0, 0), "middle": (1, 2), "end": (2, 2)}.get(anchor,
                                                                       (0, 0))
        s = "0\nTEXT\n8\n%s\n10\n%s\n20\n%s\n30\n0\n40\n%s\n1\n%s\n50\n%s\n" % (
            layer, fmt_num(x), fmt_num(y), fmt_num(height), _dxf_text(value),
            fmt_num(rotation))
        s += "72\n%s\n" % align[0]
        s += "73\n%s\n" % align[1]
        # R12 permits one alignment point (group 11/21/31), placed after both
        # alignment codes.  Repeating it makes some DXF readers raise.
        if align[0] or align[1]:
            s += "11\n%s\n21\n%s\n31\n0\n" % (fmt_num(x), fmt_num(y))
        return s

    lines = []
    lines.append("0\nSECTION\n2\nHEADER\n")
    lines.append("9\n$ACADVER\n1\nAC1009\n")
    lines.append("9\n$DWGCODEPAGE\n3\nANSI_936\n")
    lines.append("9\n$INSUNITS\n70\n4\n")
    lines.append("0\nENDSEC\n")
    layers = []
    for name, color in DXF_COLORS.items():
        lt = "DASHED" if name == "HIDDEN" else ("CENTER" if name == "CENTER" else "CONTINUOUS")
        layers.append("0\nLAYER\n2\n%s\n70\n0\n62\n%s\n6\n%s\n" % (name, color, lt))
    lines.append("0\nSECTION\n2\nTABLES\n")
    lines.append("0\nTABLE\n2\nLTYPE\n70\n3\n")
    lines.append("0\nLTYPE\n2\nCONTINUOUS\n70\n0\n3\nSolid line\n72\n65\n73\n0\n40\n0.0\n")
    lines.append("0\nLTYPE\n2\nDASHED\n70\n0\n3\nDashed __ __\n72\n65\n73\n2\n40\n3.0\n49\n2.0\n49\n-1.0\n")
    lines.append("0\nLTYPE\n2\nCENTER\n70\n0\n3\nCenter ____ _ ____\n72\n65\n73\n4\n40\n8.0\n49\n6.0\n49\n-1.0\n49\n1.0\n49\n-1.0\n")
    lines.append("0\nENDTAB\n")
    lines.append("0\nTABLE\n2\nLAYER\n70\n%s\n" % len(layers))
    lines.extend(layers)
    lines.append("0\nENDTAB\n")
    lines.append("0\nTABLE\n2\nSTYLE\n70\n1\n")
    lines.append("0\nSTYLE\n2\nSTANDARD\n70\n0\n40\n0.0\n41\n1.0\n50\n0.0\n71\n0\n42\n2.5\n3\nsimhei.ttf\n4\n\n")
    lines.append("0\nENDTAB\n")
    lines.append("0\nENDSEC\n")
    lines.append("0\nSECTION\n2\nENTITIES\n")
    for item in scene.items:
        kind = item["kind"]
        layer = item.get("layer", "OUTLINE")
        if layer not in DXF_COLORS:
            layer = "OUTLINE"
        if kind == "line":
            lines.append(line_entity(item["p1"][0], item["p1"][1],
                                     item["p2"][0], item["p2"][1], layer))
        elif kind == "polyline":
            lines.append(polyline_entity(item["points"], item["closed"], layer))
        elif kind == "circle":
            lines.append(circle_entity(item["c"][0], item["c"][1], item["r"], layer))
        elif kind == "text":
            lines.append(text_entity(item["p"][0], item["p"][1], item["size"],
                                     item["text"], item["anchor"],
                                     item["rotation"], layer))
    lines.append("0\nENDSEC\n0\nEOF\n")
    data = "".join(lines)
    with open(path, "w", encoding="gbk", errors="replace", newline="\n") as fh:
        fh.write(data)
    return path


# ---------------------------------------------------------------------------
# PDF / PNG via matplotlib
# ---------------------------------------------------------------------------

def _font_props(bold=False):
    from matplotlib.font_manager import FontProperties
    paths = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + CJK_FONT_CANDIDATES
    for p in paths:
        if os.path.exists(p):
            return FontProperties(fname=p)
    return FontProperties(family="sans-serif")


def _render_mpl(scene, path, fmt="pdf", dpi=150):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    W, H = scene.width / 25.4, scene.height / 25.4
    fig = plt.figure(figsize=(W, H), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, scene.width)
    ax.set_ylim(scene.height, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")
    pt_per_mm = 72.0 / 25.4
    normal = _font_props(False)
    bold = _font_props(True)
    for item in scene.items:
        kind = item["kind"]
        if kind == "line":
            ax.plot([item["p1"][0], item["p2"][0]],
                    [item["p1"][1], item["p2"][1]],
                    color=item["color"], linewidth=item["width"] * pt_per_mm,
                    solid_capstyle="round",
                    linestyle=(0, tuple(float(x) for x in item["dash"].split(",")))
                    if item["dash"] else "-", zorder=2)
        elif kind == "polyline":
            pts = item["points"]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if item["closed"]:
                xs.append(pts[0][0])
                ys.append(pts[0][1])
            ax.plot(xs, ys, color=item["color"],
                    linewidth=item["width"] * pt_per_mm, solid_capstyle="round",
                    linestyle=(0, tuple(float(x) for x in item["dash"].split(",")))
                    if item["dash"] else "-", zorder=2)
        elif kind == "circle":
            ax.add_patch(Circle(item["c"], item["r"], fill=False,
                                edgecolor=item["color"],
                                linewidth=item["width"] * pt_per_mm, zorder=2))
        elif kind == "text":
            ha = {"start": "left", "middle": "center", "end": "right"}.get(
                item["anchor"], "left")
            ax.text(item["p"][0], item["p"][1], item["text"],
                    fontsize=item["size"] * pt_per_mm,
                    fontproperties=bold if item["bold"] else normal,
                    color=item["color"], ha=ha, va="baseline",
                    rotation=item["rotation"], rotation_mode="anchor", zorder=3)
    fig.savefig(path, format=fmt, dpi=dpi, facecolor="white",
                bbox_inches=None, pad_inches=0)
    plt.close(fig)
    return path


def render_pdf(scene, path):
    return _render_mpl(scene, path, "pdf", 300)


def render_png(scene, path, dpi=180):
    return _render_mpl(scene, path, "png", dpi)


def export_scene(scene, base_no_ext, formats):
    written = {}
    requested = [f.lower().lstrip(".") for f in formats]
    for fmt in requested:
        try:
            if fmt == "svg":
                written["svg"] = render_svg(scene, base_no_ext + ".svg")
            elif fmt == "dxf":
                written["dxf"] = render_dxf(scene, base_no_ext + ".dxf")
            elif fmt == "pdf":
                written["pdf"] = render_pdf(scene, base_no_ext + ".pdf")
            elif fmt == "png":
                written["png"] = render_png(scene, base_no_ext + ".png")
        except Exception as exc:
            raise RuntimeError("failed to write %s: %s" % (fmt, exc))
    return written

def render_multipage_pdf(scenes, path, dpi=300):
    """Write several scenes as pages of one PDF (all pages keep their real size)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Circle

    normal = _font_props(False)
    bold = _font_props(True)
    pt_per_mm = 72.0 / 25.4
    with PdfPages(path) as pdf:
        for scene in scenes:
            fig = plt.figure(figsize=(scene.width / 25.4, scene.height / 25.4), dpi=dpi)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(0, scene.width)
            ax.set_ylim(scene.height, 0)
            ax.set_aspect("equal")
            ax.axis("off")
            fig.patch.set_facecolor("white")
            for item in scene.items:
                kind = item["kind"]
                if kind in ("line", "polyline"):
                    if kind == "line":
                        xs = [item["p1"][0], item["p2"][0]]
                        ys = [item["p1"][1], item["p2"][1]]
                    else:
                        pts = item["points"]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        if item["closed"]:
                            xs.append(pts[0][0])
                            ys.append(pts[0][1])
                    ax.plot(xs, ys, color=item["color"],
                            linewidth=item["width"] * pt_per_mm,
                            solid_capstyle="round",
                            linestyle=(0, tuple(float(x) for x in item["dash"].split(",")))
                            if item["dash"] else "-", zorder=2)
                elif kind == "circle":
                    ax.add_patch(Circle(item["c"], item["r"], fill=False,
                                        edgecolor=item["color"],
                                        linewidth=item["width"] * pt_per_mm, zorder=2))
                elif kind == "text":
                    ha = {"start": "left", "middle": "center", "end": "right"}.get(
                        item["anchor"], "left")
                    ax.text(item["p"][0], item["p"][1], item["text"],
                            fontsize=item["size"] * pt_per_mm,
                            fontproperties=bold if item["bold"] else normal,
                            color=item["color"], ha=ha, va="baseline",
                            rotation=item["rotation"], rotation_mode="anchor", zorder=3)
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    return path


def render_multipage_png(scenes, path, dpi=150):
    """Stacked preview of all pages, for quick viewing without a PDF reader."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    widths = [s.width for s in scenes]
    heights = [s.height for s in scenes]
    total_w = sum(widths) + 10.0 * (len(scenes) - 1)
    total_h = max(heights)
    from matplotlib.patches import Circle
    fig = plt.figure(figsize=(total_w / 25.4, total_h / 25.4), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, total_w)
    ax.set_ylim(total_h, 0)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")
    normal = _font_props(False)
    bold = _font_props(True)
    pt_per_mm = 72.0 / 25.4
    ox = 0.0
    for scene in scenes:
        ax.add_patch(plt.Rectangle((ox, 0), scene.width, scene.height,
                                   facecolor="white", edgecolor="#888888", lw=0.3))
        for item in scene.items:
            kind = item["kind"]
            if kind in ("line", "polyline"):
                if kind == "line":
                    xs = [item["p1"][0] + ox, item["p2"][0] + ox]
                    ys = [item["p1"][1], item["p2"][1]]
                else:
                    pts = item["points"]
                    xs = [p[0] + ox for p in pts]
                    ys = [p[1] for p in pts]
                    if item["closed"]:
                        xs.append(pts[0][0] + ox)
                        ys.append(pts[0][1])
                ax.plot(xs, ys, color=item["color"],
                        linewidth=item["width"] * pt_per_mm,
                        solid_capstyle="round",
                        linestyle=(0, tuple(float(x) for x in item["dash"].split(",")))
                        if item["dash"] else "-", zorder=2)
            elif kind == "circle":
                ax.add_patch(Circle((item["c"][0] + ox, item["c"][1]), item["r"],
                                    fill=False, edgecolor=item["color"],
                                    linewidth=item["width"] * pt_per_mm, zorder=2))
            elif kind == "text":
                ha = {"start": "left", "middle": "center", "end": "right"}.get(
                    item["anchor"], "left")
                ax.text(item["p"][0] + ox, item["p"][1], item["text"],
                        fontsize=item["size"] * pt_per_mm,
                        fontproperties=bold if item["bold"] else normal,
                        color=item["color"], ha=ha, va="baseline",
                        rotation=item["rotation"], rotation_mode="anchor", zorder=3)
        ox += scene.width + 10.0
    fig.savefig(path, format="png", dpi=dpi, facecolor="white",
                bbox_inches=None, pad_inches=0)
    plt.close(fig)
    return path
