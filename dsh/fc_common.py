# -*- coding: utf-8 -*-
"""Shared FreeCAD helpers for the DSH FreeCAD plugin.

All lengths are millimetres.  This module is executed by FreeCADCmd's bundled
Python (3.11) and therefore may import FreeCAD / Part / TechDraw / Import.
"""
from __future__ import annotations

import math
import os
from collections import OrderedDict

import FreeCAD
import Import
import Part
import TechDraw


EPS = 1.0e-7

VIEW_SPECS = OrderedDict([
    ("front", {
        "direction": (0.0, -1.0, 0.0),
        "h": (1.0, 0.0, 0.0),
        "v": (0.0, 0.0, 1.0),
        "zh": "主视图",
        "en": "FRONT",
        "axis": "Y",
    }),
    ("top", {
        "direction": (0.0, 0.0, 1.0),
        "h": (1.0, 0.0, 0.0),
        "v": (0.0, 1.0, 0.0),
        "zh": "俯视图",
        "en": "TOP",
        "axis": "Z",
    }),
    ("right", {
        "direction": (1.0, 0.0, 0.0),
        "h": (0.0, 1.0, 0.0),
        "v": (0.0, 0.0, 1.0),
        "zh": "右视图",
        "en": "RIGHT",
        "axis": "X",
    }),
    ("left", {
        "direction": (-1.0, 0.0, 0.0),
        "h": (0.0, -1.0, 0.0),
        "v": (0.0, 0.0, 1.0),
        "zh": "左视图",
        "en": "LEFT",
        "axis": "X",
    }),
    ("rear", {
        "direction": (0.0, 1.0, 0.0),
        "h": (-1.0, 0.0, 0.0),
        "v": (0.0, 0.0, 1.0),
        "zh": "后视图",
        "en": "REAR",
        "axis": "Y",
    }),
    ("bottom", {
        "direction": (0.0, 0.0, -1.0),
        "h": (1.0, 0.0, 0.0),
        "v": (0.0, -1.0, 0.0),
        "zh": "仰视图",
        "en": "BOTTOM",
        "axis": "Z",
    }),
    ("iso", {
        "direction": (0.5773502691896258, -0.5773502691896258, 0.5773502691896258),
        "h": (0.7071067811865476, 0.7071067811865476, 0.0),
        "v": (-0.4082482904638631, 0.4082482904638631, 0.8164965809277261),
        "zh": "轴测图",
        "en": "ISO",
        "axis": None,
    }),
])


def vec(value):
    """Return a FreeCAD.Vector from a JSON-ish sequence or Vector."""
    if isinstance(value, FreeCAD.Vector):
        return value
    if isinstance(value, dict):
        return FreeCAD.Vector(float(value.get("x", 0.0)),
                              float(value.get("y", 0.0)),
                              float(value.get("z", 0.0)))
    if value is None:
        return FreeCAD.Vector(0.0, 0.0, 0.0)
    return FreeCAD.Vector(float(value[0]), float(value[1]), float(value[2]))


def vlist(v, ndigits=6):
    if v is None:
        return None
    return [round(float(v.x), ndigits), round(float(v.y), ndigits), round(float(v.z), ndigits)]


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def length(v):
    return math.sqrt(dot(v, v))


def normalized(v, fallback=None):
    n = length(v)
    if n < EPS:
        if fallback is None:
            raise ValueError("zero-length vector")
        return vec(fallback)
    return FreeCAD.Vector(v.x / n, v.y / n, v.z / n)


def bbox_list(bb):
    if bb is None:
        return None
    if bb.XLength > 1.0e100 or bb.YLength > 1.0e100 or bb.ZLength > 1.0e100:
        return None
    return [round(float(bb.XMin), 6), round(float(bb.YMin), 6), round(float(bb.ZMin), 6),
            round(float(bb.XMax), 6), round(float(bb.YMax), 6), round(float(bb.ZMax), 6)]


def bbox_dict(bb):
    values = bbox_list(bb)
    if values is None:
        return None
    return {
        "min": values[:3],
        "max": values[3:],
        "size": [round(values[3] - values[0], 6),
                 round(values[4] - values[1], 6),
                 round(values[5] - values[2], 6)],
    }


def tight_bbox(shape):
    """Return a tight bounding box.

    Part.Shape.BoundBox is padded by B-spline control points on some imported
    STEP models (a 19 mm bushing can report a 145 mm envelope).  FreeCAD's
    optimalBoundingBox() follows the actual geometry, so prefer it and fall
    back to BoundBox only when OCC cannot compute it.
    """
    try:
        bb = shape.optimalBoundingBox()
        if bb is not None and bb.isValid():
            return bb
    except Exception:
        pass
    return shape.BoundBox


def axis_name(axis):
    a = normalized(axis)
    vals = [abs(a.x), abs(a.y), abs(a.z)]
    idx = vals.index(max(vals))
    return ("X", "Y", "Z")[idx] if max(vals) > 0.9 else "OTHER"


def canonical_axis(axis):
    """Orient an axis so its dominant component is positive."""
    a = normalized(axis)
    vals = [abs(a.x), abs(a.y), abs(a.z)]
    idx = vals.index(max(vals))
    if (a.x, a.y, a.z)[idx] < 0.0:
        a = FreeCAD.Vector(-a.x, -a.y, -a.z)
    return a


def safe_is_valid(shape):
    try:
        return bool(shape.isValid())
    except Exception:
        return None


def shape_stats(shape):
    if shape is None or shape.isNull():
        return None
    solids = 0
    shells = 0
    faces = 0
    edges = 0
    vertices = 0
    try:
        solids = len(shape.Solids)
    except Exception:
        pass
    try:
        shells = len(shape.Shells)
    except Exception:
        pass
    try:
        faces = len(shape.Faces)
    except Exception:
        pass
    try:
        edges = len(shape.Edges)
    except Exception:
        pass
    try:
        vertices = len(shape.Vertexes)
    except Exception:
        pass
    volume = 0.0
    try:
        volume = float(shape.Volume)
    except Exception:
        try:
            volume = sum(float(s.Volume) for s in shape.Solids)
        except Exception:
            volume = 0.0
    try:
        area = float(shape.Area)
    except Exception:
        area = 0.0
    try:
        com = vlist(shape.CenterOfMass)
    except Exception:
        com = None
    if com is None:
        try:
            total = sum(float(s.Volume) for s in shape.Solids)
            if total > 1.0e-9:
                acc = FreeCAD.Vector(0, 0, 0)
                for s in shape.Solids:
                    acc += FreeCAD.Vector(s.CenterOfMass) * float(s.Volume)
                com = vlist(acc * (1.0 / total))
        except Exception:
            com = None
    return {
        "shapeType": getattr(shape, "ShapeType", "Unknown"),
        "valid": safe_is_valid(shape),
        "solids": solids,
        "shells": shells,
        "faces": faces,
        "edges": edges,
        "vertices": vertices,
        "volume": round(volume, 6),
        "area": round(area, 6),
        "bbox": bbox_dict(tight_bbox(shape)),
        "centerOfMass": com,
    }


def file_info(path):
    st = os.stat(path)
    return {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "sizeBytes": int(st.st_size),
        "modified": __import__("datetime").datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }


def _object_global_shape(obj):
    """Copy the object's shape and bake its global placement into the copy."""
    shape = obj.Shape
    if shape is None or shape.isNull():
        return None
    copy = shape.copy()
    try:
        placement = obj.getGlobalPlacement()
    except Exception:
        placement = getattr(obj, "Placement", None)
    if placement is not None:
        try:
            copy.transformShape(placement.toMatrix())
        except Exception:
            pass
    return copy


def import_cad(path):
    """Import a STEP/IGES/BREP file into a new document.

    Returns (doc, entries, combined_shape).  The caller owns the document and
    must close it.  Entries keep the source object plus a shape in world/global
    coordinates.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError("CAD file not found: %s" % path)
    ext = os.path.splitext(path)[1].lower()
    supported = {".step", ".stp", ".stpz", ".iges", ".igs", ".brep", ".brp"}
    if ext not in supported:
        raise ValueError(
            "Unsupported CAD format %r. This plugin reads STEP files (.step/.stp); "
            "IGES and BREP are accepted by FreeCAD as well." % ext
        )
    doc = FreeCAD.newDocument("FCImport")
    try:
        Import.insert(os.path.abspath(path), doc.Name)
        doc.recompute()
        entries = []
        for obj in list(doc.Objects):
            try:
                shape = _object_global_shape(obj)
            except Exception:
                shape = None
            if shape is not None and not shape.isNull():
                entries.append({
                    "name": obj.Name,
                    "label": obj.Label,
                    "typeId": obj.TypeId,
                    "obj": obj,
                    "shape": shape,
                })
        if not entries:
            raise ValueError("No solid/surface geometry was imported from %s" % path)
        shapes = [e["shape"] for e in entries]
        combined = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)
        return doc, entries, combined
    except Exception:
        try:
            FreeCAD.closeDocument(doc.Name)
        except Exception:
            pass
        raise


def _sample_face_t(face, surface, axis):
    """Axial extent of a face, measured on its trimmed boundary edges.

    Face.valueAt() uses the underlying surface parameter range, which can
    extend well past the trimmed face; edge sampling is exact for the solid.
    """
    values = []
    try:
        for edge in face.Edges:
            try:
                pts = edge.discretize(0.05)
            except Exception:
                pts = [edge.Vertexes[0].Point, edge.Vertexes[-1].Point]
            for p in pts:
                values.append(dot(p - surface.Center, axis))
    except Exception:
        pass
    if not values:
        try:
            for v in face.Vertexes:
                values.append(dot(v.Point - surface.Center, axis))
        except Exception:
            pass
    if not values:
        try:
            values.append(dot(face.CenterOfMass - surface.Center, axis))
        except Exception:
            values.append(0.0)
    return min(values), max(values)


def _face_normal_sample(face):
    """A point and normal that lie inside the trimmed face."""
    try:
        pr = face.ParameterRange
        u = (pr[0] + pr[1]) * 0.5
        v = (pr[2] + pr[3]) * 0.5
        return face.valueAt(u, v), face.normalAt(u, v)
    except Exception:
        pass
    try:
        return face.CenterOfMass, face.normalAt(0.5, 0.5)
    except Exception:
        return face.CenterOfMass, FreeCAD.Vector(0, 0, 1)


def _through_hole(shape, entry, exit, axis):
    """A hole is through when the centreline is outside the solid at both ends."""
    try:
        a = shape.isInside(entry - axis * 2.0, 1.0e-4, True)
        b = shape.isInside(exit + axis * 2.0, 1.0e-4, True)
        return (not a) and (not b)
    except Exception:
        return False


def detect_holes(shape, max_holes=200):
    """Detect concave full-cylinder faces and return machining hole records."""
    raw = []
    try:
        faces = list(shape.Faces)
    except Exception:
        faces = []
    for face in faces:
        try:
            surface = face.Surface
        except Exception:
            continue
        if surface.__class__.__name__ != "Cylinder":
            continue
        try:
            axis = canonical_axis(surface.Axis)
            radius = float(surface.Radius)
            if radius <= 1.0e-5:
                continue
            tmin, tmax = _sample_face_t(face, surface, axis)
            depth = tmax - tmin
            if depth <= 1.0e-4:
                continue
            # A full cylinder has one of the largest possible surface areas.
            expected = 2.0 * math.pi * radius * depth
            coverage = float(face.Area) / expected if expected > 0 else 0.0
            if coverage < 0.60:
                continue
            # Concave cylinder => hole.  The face normal points toward the axis.
            p, normal = _face_normal_sample(face)
            radial = p - surface.Center
            radial = radial - axis * dot(radial, axis)
            if length(radial) < 1.0e-6:
                continue
            if dot(normal, normalized(radial)) > -1.0e-4:
                continue
            entry = surface.Center + axis * tmin
            exit = surface.Center + axis * tmax
            center = surface.Center + axis * ((tmin + tmax) * 0.5)
            raw.append({
                "axis": axis,
                "radius": radius,
                "diameter": radius * 2.0,
                "tmin": tmin,
                "tmax": tmax,
                "depth": depth,
                "center": center,
                "entry": entry,
                "exit": exit,
                "through": _through_hole(shape, entry, exit, axis),
                "coverage": coverage,
                "area": float(face.Area),
                "surfaceCenter": FreeCAD.Vector(surface.Center),
            })
        except Exception:
            continue

    # Merge coaxial, same-diameter pieces (e.g. one hole split into two faces).
    merged = []
    for cand in raw:
        target = None
        for hole in merged:
            if abs(hole["radius"] - cand["radius"]) > 0.02:
                continue
            if abs(dot(hole["axis"], cand["axis"])) < 0.9995:
                continue
            delta = cand["surfaceCenter"] - hole["surfaceCenter"]
            perp = delta - cand["axis"] * dot(delta, cand["axis"])
            if length(perp) > 0.08:
                continue
            if cand["tmax"] < hole["tmin"] - 1.0 or cand["tmin"] > hole["tmax"] + 1.0:
                continue
            target = hole
            break
        if target is None:
            merged.append(dict(cand))
        else:
            target["tmin"] = min(target["tmin"], cand["tmin"])
            target["tmax"] = max(target["tmax"], cand["tmax"])
            target["depth"] = target["tmax"] - target["tmin"]
            target["center"] = target["surfaceCenter"] + target["axis"] * ((target["tmin"] + target["tmax"]) * 0.5)
            target["entry"] = target["surfaceCenter"] + target["axis"] * target["tmin"]
            target["exit"] = target["surfaceCenter"] + target["axis"] * target["tmax"]
            target["area"] += cand["area"]
            target["coverage"] = max(target["coverage"], cand["coverage"])

    holes = []
    for hole in merged:
        expected = 2.0 * math.pi * hole["radius"] * hole["depth"]
        hole["coverage"] = hole["area"] / expected if expected > 0 else 0.0
        hole["through"] = _through_hole(shape, hole["entry"], hole["exit"], hole["axis"])
        holes.append(hole)

    def sort_key(h):
        ax = axis_name(h["axis"])
        priority = {"Z": 0, "Y": 1, "X": 2}.get(ax, 3)
        c = h["center"]
        return (priority, round(c.x, 4), round(c.y, 4), round(c.z, 4), round(h["diameter"], 4))

    holes.sort(key=sort_key)
    holes = holes[:max_holes]
    out = []
    for idx, hole in enumerate(holes, 1):
        out.append({
            "id": "H%d" % idx,
            "axis": vlist(hole["axis"]),
            "axisName": axis_name(hole["axis"]),
            "diameter": round(hole["diameter"], 6),
            "radius": round(hole["radius"], 6),
            "depth": round(hole["depth"], 6),
            "through": bool(hole["through"]),
            "center": vlist(hole["center"]),
            "entry": vlist(hole["entry"]),
            "exit": vlist(hole["exit"]),
            "coverage": round(float(hole["coverage"]), 4),
        })
    return out


def _project_unit_local(direction, unit_vec):
    """Project a unit line and return its local 2D vector."""
    direction = normalized(vec(direction))
    line = Part.makeLine(FreeCAD.Vector(0, 0, 0), vec(unit_vec) * 10.0)
    groups = TechDraw.projectEx(line, direction)
    pts = []
    for group in list(groups)[:5]:
        try:
            for edge in group.Edges:
                for p in (edge.Vertexes[0].Point, edge.Vertexes[-1].Point):
                    pts.append((float(p.x), float(p.y)))
        except Exception:
            continue
    if not pts:
        raise RuntimeError("TechDraw projection calibration failed for direction %s" % (vlist(direction),))
    far = max(pts, key=lambda p: p[0] * p[0] + p[1] * p[1])
    return (far[0] / 10.0, far[1] / 10.0)


def _edge_polyline(edge, deflection):
    try:
        curve_type = edge.Curve.__class__.__name__
    except Exception:
        curve_type = ""
    if curve_type == "Line":
        try:
            pts = [edge.Vertexes[0].Point, edge.Vertexes[-1].Point]
        except Exception:
            pts = edge.discretize(deflection)
    else:
        pts = edge.discretize(deflection)
    out = []
    for p in pts:
        q = (float(p.x), float(p.y))
        if not out or abs(q[0] - out[-1][0]) > 1.0e-6 or abs(q[1] - out[-1][1]) > 1.0e-6:
            out.append(q)
    return out


def _resample(points, limit=64):
    """Cap a tessellated curve while preserving both endpoints.

    OCC's ``discretize`` can return thousands of points for a projected
    circle (and even for short BSpline edges), which bloats SVG/DXF output by
    an order of magnitude without adding visible detail.
    """
    if len(points) <= limit:
        return points
    out = [points[0]]
    step = (len(points) - 1) / float(limit - 1)
    for i in range(1, limit - 1):
        p = points[int(round(i * step))]
        if p != out[-1]:
            out.append(p)
    if points[-1] != out[-1]:
        out.append(points[-1])
    return out


def _edge_exact(edge, to_canonical):
    """Return a renderer-neutral exact 2D entity, or None.

    Lines and full circles are the overwhelming majority of mechanical
    drawing geometry.  Keeping them exact makes the DXF cleaner and lets a
    CAD/CAM package recognize holes and straight edges.
    """
    try:
        curve_type = edge.Curve.__class__.__name__
    except Exception:
        return None
    try:
        if curve_type == "Line":
            p1 = edge.Vertexes[0].Point
            p2 = edge.Vertexes[-1].Point
            return {"type": "line", "p1": to_canonical(p1),
                    "p2": to_canonical(p2)}
        if curve_type == "Circle" and edge.isClosed():
            curve = edge.Curve
            center = curve.Center
            return {"type": "circle", "c": to_canonical(center),
                    "r": float(curve.Radius)}
    except Exception:
        return None
    return None


def project_view(shape, view_name, hidden=True):
    """HLR-project a shape and return canonical 2D polylines.

    TechDraw's local 2D orientation is version/direction dependent, so the
    projection basis is calibrated with two unit lines and inverted.
    """
    spec = VIEW_SPECS[view_name]
    direction = normalized(vec(spec["direction"]))
    hvec = normalized(vec(spec["h"]))
    vvec = normalized(vec(spec["v"]))
    h_local = _project_unit_local(direction, hvec)
    v_local = _project_unit_local(direction, vvec)
    det = h_local[0] * v_local[1] - v_local[0] * h_local[1]
    if abs(det) < 1.0e-9:
        raise RuntimeError("degenerate projection basis for view %s" % view_name)
    inv = (
        (v_local[1] / det, -v_local[0] / det),
        (-h_local[1] / det, h_local[0] / det),
    )

    try:
        groups = TechDraw.projectEx(shape, direction)
    except Exception as exc:
        raise RuntimeError("HLR projection failed for view %s: %s" % (view_name, exc))
    try:
        diag = float(shape.BoundBox.DiagonalLength)
    except Exception:
        diag = 100.0
    deflection = max(0.02, min(0.20, diag / 3000.0))

    def to_canonical(p):
        # local -> canonical: inv * [x,y]
        x, y = float(p.x), float(p.y)
        return (inv[0][0] * x + inv[0][1] * y,
                inv[1][0] * x + inv[1][1] * y)

    visible = []
    hidden_lines = []
    exact_visible = []
    exact_hidden = []
    all_pts = []
    # TechDraw.projectEx returns V, V1, VN, VO, VI, H, H1, HN, HO, HI.
    # V/VO and H/HO carry real sharp edges and silhouettes.  VN/HN carry
    # smooth/seam edges such as the longitudinal seam of a cylinder; those are
    # not drawn on a machining view because they are not real part edges.
    keep_groups = (0, 3, 5, 8)
    for gi, group in enumerate(groups):
        if gi not in keep_groups:
            continue
        is_hidden = gi >= 5
        if is_hidden and not hidden:
            continue
        try:
            edges = list(group.Edges)
        except Exception:
            continue
        for edge in edges:
            exact = _edge_exact(edge, to_canonical)
            if exact is not None:
                if exact["type"] == "circle":
                    cx, cy = exact["c"]
                    r = exact["r"]
                    all_pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
                else:
                    all_pts.extend([exact["p1"], exact["p2"]])
                if is_hidden:
                    exact_hidden.append(exact)
                else:
                    exact_visible.append(exact)
                continue
            raw = _edge_polyline(edge, deflection)
            if len(raw) < 2:
                continue
            pts = []
            for x, y in raw:
                cx = inv[0][0] * x + inv[0][1] * y
                cy = inv[1][0] * x + inv[1][1] * y
                pts.append((cx, cy))
            pts = _resample(pts, 64)
            all_pts.extend(pts)
            if is_hidden:
                hidden_lines.append(pts)
            else:
                visible.append(pts)

    if not all_pts:
        bbox = (0.0, 0.0, 0.0, 0.0)
    else:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        bbox = (min(xs), min(ys), max(xs), max(ys))

    # Normalize to the lower-left of the projected extents.
    minx, miny = bbox[0], bbox[1]

    def shift(p):
        return (p[0] - minx, p[1] - miny)

    visible = [[shift(p) for p in line] for line in visible]
    hidden_lines = [[shift(p) for p in line] for line in hidden_lines]
    for entity in exact_visible + exact_hidden:
        if entity["type"] == "line":
            entity["p1"] = shift(entity["p1"])
            entity["p2"] = shift(entity["p2"])
        else:
            entity["c"] = shift(entity["c"])
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    _report("投影完成: %s %s (%d 可见 / %d 隐藏)" % (
        spec["zh"], view_name, len(visible), len(hidden_lines)))
    return {
        "name": view_name,
        "label": spec["zh"],
        "labelEn": spec["en"],
        "visible": visible,
        "hidden": hidden_lines,
        "exactVisible": exact_visible,
        "exactHidden": exact_hidden,
        "bbox": (0.0, 0.0, float(width), float(height)),
        "width": float(width),
        "height": float(height),
        "rawBBox": tuple(round(v, 6) for v in bbox),
    }


def project_point(point, view_name, view_bbox):
    """Canonical in-view coordinates for a 3D point."""
    spec = VIEW_SPECS[view_name]
    p = vec(point)
    h = normalized(vec(spec["h"]))
    v = normalized(vec(spec["v"]))
    return (dot(p, h) - view_bbox[0], dot(p, v) - view_bbox[1])


def hole_view_name(hole, available):
    ax = hole.get("axisName")
    if ax == "Z":
        for name in ("top", "bottom"):
            if name in available:
                return name
    elif ax == "X":
        for name in ("right", "left"):
            if name in available:
                return name
    elif ax == "Y":
        for name in ("front", "rear"):
            if name in available:
                return name
    return None


def _progress_hook(message, fraction=None):
    """Worker replaces this with a file writer so the host can report progress."""
    return None


def _report(message, fraction=None):
    try:
        _progress_hook(message, fraction)
    except Exception:
        pass


def _selector_geometry(shape, selector, role):
    """Turn a {point|face|edge} selector into FreeCAD geometry."""
    if not isinstance(selector, dict):
        raise ValueError("%s must be an object like {\"face\": 3} or {\"point\": [x,y,z]}" % role)
    if "point" in selector:
        p = selector["point"]
        if not isinstance(p, (list, tuple)) or len(p) != 3:
            raise ValueError("%s.point needs three numbers" % role)
        return "point", FreeCAD.Vector(float(p[0]), float(p[1]), float(p[2]))
    for key, collection in (("face", shape.Faces), ("edge", shape.Edges)):
        if key in selector:
            try:
                index = int(selector[key])
            except (TypeError, ValueError):
                raise ValueError("%s.%s must be an integer" % (role, key))
            if index < 1 or index > len(collection):
                raise ValueError("%s.%s out of range 1..%d" % (role, key, len(collection)))
            return key, collection[index - 1]
    raise ValueError("%s needs one of point / face / edge" % role)


def _shape_of(kind, geo):
    if kind == "point":
        return Part.Vertex(geo)
    if kind == "face":
        return geo
    if kind == "edge":
        return geo
    raise ValueError("unsupported selector kind %r" % kind)


def _distance_between(shape_of_a, shape_of_b):
    result = shape_of_b.distToShape(shape_of_a)
    distance = float(result[0])
    points = result[1] or []
    detail = {}
    if points:
        try:
            pb, pa = points[0][0], points[0][1]
            detail["closestOnB"] = vlist(pb)
            detail["closestOnA"] = vlist(pa)
        except Exception:
            pass
    return distance, detail


def measure_items(shape, items):
    """Answer distance / angle / radius questions without touching the model.

    One bad item must not void the rest: an LLM that guessed a face index wrong
    still needs the measurements that did resolve, plus the reason this one did
    not -- otherwise it has to re-ask everything to make progress.
    """
    if not isinstance(items, list) or not items:
        raise ValueError("items must be a non-empty list of measurements")
    out = []
    for n, item in enumerate(items, 1):
        try:
            out.append(_measure_one(shape, n, item))
        except Exception as exc:
            out.append({
                "index": n,
                "kind": str((item or {}).get("kind") or "distance"),
                "error": str(exc),
            })
    ok = sum(1 for record in out if "error" not in record)
    return {"count": len(out), "resolved": ok, "measurements": out}


def _plane_offset(face_a, face_b):
    """Signed plane-to-plane offset for two planar faces, else None."""
    try:
        if face_a.Surface.__class__.__name__ != "Plane":
            return None
        if face_b.Surface.__class__.__name__ != "Plane":
            return None
        na = normalized(face_a.Surface.Axis)
        nb = normalized(face_b.Surface.Axis)
        if abs(abs(dot(na, nb)) - 1.0) > 1e-6:
            return None  # not parallel: an offset is meaningless
        delta = face_b.Surface.Position - face_a.Surface.Position
        return abs(dot(delta, na))
    except Exception:
        return None


def _measure_one(shape, n, item):
    if not isinstance(item, dict):
        raise ValueError("measurement #%d must be an object" % n)
    kind = str(item.get("kind") or item.get("type") or "distance").lower()
    if kind in ("distance", "dist", "gap"):
        kind = "distance"
    elif kind in ("angle", "degrees"):
        kind = "angle"
    elif kind in ("radius", "diameter", "size"):
        kind = "radius"
    else:
        raise ValueError("measurement #%d: unknown kind %r" % (n, kind))
    record = {"index": n, "kind": kind}
    if kind == "distance":
        ka, ga = _selector_geometry(shape, item.get("a"), "a")
        kb, gb = _selector_geometry(shape, item.get("b"), "b")
        distance, detail = _distance_between(_shape_of(ka, ga), _shape_of(kb, gb))
        record.update({"value": round(distance, 4), "unit": "mm", "a": ka, "b": kb})
        if ka == "face" and kb == "face":
            # Two coplanar/adjacent faces measure 0 mm, which is useless for the
            # question an engineer actually asks ("how thick is this plate?").
            # Report the plane-to-plane offset alongside it.
            try:
                offset = _plane_offset(ga, gb)
                if offset is not None:
                    record["planeOffset"] = round(offset, 4)
            except Exception:
                pass
        pa = detail.get("closestOnA")
        pb = detail.get("closestOnB")
        if pa and pb:
            record["closest"] = {"a": pa, "b": pb}
            record["delta"] = [round(pa[i] - pb[i], 4) for i in range(3)]
        return record
    if kind == "angle":
        ka, ga = _selector_geometry(shape, item.get("a"), "a")
        kb, gb = _selector_geometry(shape, item.get("b"), "b")

        def direction(kind_, geo):
            if kind_ == "face":
                _, nrm = _face_normal_sample(geo)
                return normalized(nrm)
            if kind_ == "edge":
                curve = geo.Curve
                if hasattr(curve, "Direction"):
                    return normalized(curve.Direction)
                raise ValueError("angle needs a straight edge or a face, not a %s edge"
                                 % curve.__class__.__name__)
            raise ValueError("angle does not accept a bare point")

        na = direction(ka, ga)
        nb = direction(kb, gb)
        value = math.degrees(math.acos(max(-1.0, min(1.0, abs(dot(na, nb))))))
        record.update({
            "value": round(value, 4),
            "unit": "deg",
            "a": ka, "b": kb,
            "normalA": vlist(na), "normalB": vlist(nb),
        })
        return record
    target = item.get("a") or item.get("item")
    kind_, geo = _selector_geometry(shape, target, "a")
    if kind_ == "face":
        surf = geo.Surface
        name = surf.__class__.__name__
        if name == "Cylinder":
            record.update({
                "value": round(float(surf.Radius) * 2.0, 4),
                "unit": "mm",
                "what": "diameter",
                "radius": round(float(surf.Radius), 4),
                "axis": vlist(normalized(surf.Axis)),
                "axisCenter": vlist(surf.Center),
            })
        elif name == "Sphere":
            record.update({
                "value": round(float(surf.Radius) * 2.0, 4),
                "unit": "mm",
                "what": "diameter",
                "radius": round(float(surf.Radius), 4),
                "center": vlist(surf.Center),
            })
        else:
            raise ValueError("radius needs a cylindrical or spherical face, got %s" % name)
    elif kind_ == "edge":
        curve = geo.Curve
        name = curve.__class__.__name__
        if name == "Circle":
            record.update({
                "value": round(float(curve.Radius) * 2.0, 4),
                "unit": "mm",
                "what": "diameter",
                "radius": round(float(curve.Radius), 4),
                "center": vlist(curve.Center),
                "normal": vlist(normalized(curve.Axis)),
                "length": round(float(geo.Length), 4),
            })
            try:
                record["arcDegrees"] = round(
                    math.degrees(float(geo.Length) / float(curve.Radius)), 3)
            except Exception:
                pass
        else:
            raise ValueError("radius needs a circular edge, got %s" % name)
    else:
        raise ValueError("radius does not accept a bare point")
    return record


def resolve_edges(shape, op, kind="edge"):
    """Resolve 1-based indices or positional selectors into concrete edges.

    Index lists are brittle after an earlier operation renumbers the B-Rep, so
    callers may instead point at geometry: ``edgeAt`` picks the nearest edge and
    ``edgesNear`` picks every edge within ``radius`` of a point.
    """
    edges = list(shape.Edges)
    picked = []

    def add(index):
        if index not in picked:
            picked.append(index)

    raw = op.get("edges")
    if raw not in (None, [], "all"):
        try:
            indices = [int(e) for e in raw]
        except (TypeError, ValueError):
            raise ValueError("%s edge indices must be integers" % kind)
        bad = [e for e in indices if e < 1 or e > len(edges)]
        if bad:
            raise ValueError("%s edge index out of range 1..%d: %s"
                             % (kind, len(edges), ", ".join(str(e) for e in bad)))
        for index in indices:
            add(index)

    def edge_distance(edge, point):
        try:
            return float(edge.distToShape(Part.Vertex(point))[0])
        except Exception:
            return float((edge.CenterOfMass - point).Length)

    iff = op.get("edgeAt")
    if iff is not None:
        if not isinstance(iff, (list, tuple)) or len(iff) != 3:
            raise ValueError("edgeAt needs [x, y, z]")
        point = vec(iff)
        best = None
        for index, edge in enumerate(edges, 1):
            d = edge_distance(edge, point)
            if best is None or d < best[1]:
                best = (index, d)
        if best is None:
            raise ValueError("the shape has no edges to select")
        add(best[0])

    near = op.get("edgesNear")
    if near is not None:
        if not isinstance(near, (list, tuple)) or len(near) != 3:
            raise ValueError("edgesNear needs [x, y, z]")
        point = vec(near)
        radius = float(op.get("edgesNearRadius") or op.get("searchRadius") or 0.5)
        if radius <= 0:
            raise ValueError("edgesNearRadius must be positive")
        hits = 0
        closest = None
        for index, edge in enumerate(edges, 1):
            d = edge_distance(edge, point)
            if closest is None or d < closest[1]:
                closest = (index, d)
            if d <= radius:
                add(index)
                hits += 1
        if not hits:
            # A miss is almost always "the point is not on the edge", so say by
            # how much instead of only that nothing matched.
            hint = ""
            if closest is not None:
                hint = "；最近的边是 #%d，距离 %.3f mm" % (closest[0], closest[1])
            raise ValueError(
                "edgesNear [%.3f, %.3f, %.3f] 半径 %.3f mm 内没有任何边%s"
                "。可以加大 edgesNearRadius，或用 edgeAt，或按编号给 edges"
                % (point.x, point.y, point.z, radius, hint))

    selected = []
    for index in picked:
        edge = edges[index - 1]
        info = {"index": index, "length": round(float(edge.Length), 4)}
        try:
            info["start"] = vlist(edge.Vertexes[0].Point)
            info["end"] = vlist(edge.Vertexes[-1].Point)
        except Exception:
            pass
        try:
            info["mid"] = vlist(edge.CenterOfMass)
        except Exception:
            pass
        try:
            info["curve"] = edge.Curve.__class__.__name__
        except Exception:
            pass
        selected.append((index, edge, info))
    return selected


def face_details(shape, max_items=100, include_faces=True, include_edges=True,
                 offset=0, limit=None):
    """Face/edge inventory with real pagination.

    ``offset``/``limit`` page through everything; ``max_items`` stays as the
    hard ceiling for one response so a huge B-Rep cannot blow up the transcript.
    """
    result = {}
    page_size = int(limit if limit is not None else max_items)
    page_size = max(1, min(page_size, int(max_items) if max_items else page_size))
    start = max(0, int(offset or 0))
    if include_faces:
        faces = []
        all_faces = list(shape.Faces)
        for idx, face in enumerate(all_faces, 1):
            if idx <= start:
                continue
            if len(faces) >= page_size:
                break
            try:
                surf = face.Surface.__class__.__name__
            except Exception:
                surf = "Unknown"
            item = {
                "index": idx,
                "surface": surf,
                "area": round(float(face.Area), 6),
                "bbox": bbox_dict(face.BoundBox),
                "centerOfMass": vlist(face.CenterOfMass),
            }
            try:
                if surf == "Cylinder":
                    s = face.Surface
                    item["radius"] = round(float(s.Radius), 6)
                    item["axis"] = vlist(normalized(s.Axis))
                    item["axisCenter"] = vlist(s.Center)
                    try:
                        p, n = _face_normal_sample(face)
                        ax = normalized(s.Axis)
                        radial = p - s.Center
                        radial = radial - ax * dot(radial, ax)
                        item["concave"] = bool(dot(n, normalized(radial)) < 0)
                    except Exception:
                        item["concave"] = None
            except Exception:
                pass
            faces.append(item)
        result["faces"] = faces
        result["facesTotal"] = len(all_faces)
        result["facesTruncated"] = len(all_faces) > start + len(faces)
        result["nextFaceOffset"] = start + len(faces) if result["facesTruncated"] else None
    if include_edges:
        edges = []
        all_edges = list(shape.Edges)
        for idx, edge in enumerate(all_edges, 1):
            if idx <= start:
                continue
            if len(edges) >= page_size:
                break
            try:
                curve = edge.Curve.__class__.__name__
            except Exception:
                curve = "Unknown"
            item = {
                "index": idx,
                "curve": curve,
                "length": round(float(edge.Length), 6),
                "bbox": bbox_dict(edge.BoundBox),
            }
            try:
                item["start"] = vlist(edge.Vertexes[0].Point)
                item["end"] = vlist(edge.Vertexes[-1].Point)
            except Exception:
                pass
            try:
                item["mid"] = vlist(edge.CenterOfMass)
            except Exception:
                pass
            try:
                if curve == "Circle":
                    c = edge.Curve
                    item["center"] = vlist(c.Center)
                    item["radius"] = round(float(c.Radius), 6)
                    item["axis"] = vlist(normalized(c.Axis))
            except Exception:
                pass
            edges.append(item)
        result["edges"] = edges
        result["edgesTotal"] = len(all_edges)
        result["edgesTruncated"] = len(all_edges) > start + len(edges)
        result["nextEdgeOffset"] = start + len(edges) if result["edgesTruncated"] else None
    result["offset"] = start
    result["limit"] = page_size
    return result
