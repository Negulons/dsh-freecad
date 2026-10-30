# -*- coding: utf-8 -*-
"""FreeCADCmd worker for the DSH FreeCAD plugin.

Usage: freecadcmd.exe fc_worker.py request.json result.json

The worker never writes to stdout as its protocol; the result file is the
contract.  It always writes a result file, including on failure.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import FreeCAD  # noqa: E402
import Import  # noqa: E402
import Part  # noqa: E402

import fc_common as C  # noqa: E402
import fc_render as R  # noqa: E402


def _obj_from_request(req):
    path = req.get("input") or req.get("path")
    if not path:
        raise ValueError("Missing 'input' CAD file path")
    return os.path.abspath(os.path.expanduser(path))


def _setup_progress():
    """Stream coarse phases to a file the host can tail while the job runs."""
    target = os.environ.get("FREECAD_PLUGIN_PROGRESS")
    if not target:
        return

    def hook(message, fraction=None):
        try:
            with open(target, "a", encoding="utf-8") as fh:
                fh.write("%s\t%s\n" % (
                    "" if fraction is None else "%.3f" % float(fraction),
                    str(message).replace("\n", " ")))
                fh.flush()
        except OSError:
            pass

    C._progress_hook = hook


def do_measure(req):
    path, doc, entries, shape = _shape_doc(req)
    try:
        items = req.get("items") or req.get("measurements") or []
        result = C.measure_items(shape, items)
        result["input"] = path
        result["file"] = C.file_info(path)
        result["units"] = "mm"
        if len(entries) > 1:
            result["note"] = ("The file holds %d objects; measurements use their combined shape."
                              % len(entries))
        return result
    finally:
        FreeCAD.closeDocument(doc.Name)


def _shape_doc(req):
    path = _obj_from_request(req)
    doc, entries, shape = C.import_cad(path)
    return path, doc, entries, shape


def _entry_list(entries):
    out = []
    for e in entries:
        out.append({
            "name": e["name"],
            "label": e["label"],
            "typeId": e["typeId"],
            "stats": C.shape_stats(e["shape"]),
            "bbox": C.bbox_dict(C.tight_bbox(e["shape"])),
        })
    return out


def do_inspect(req):
    path, doc, entries, shape = _shape_doc(req)
    try:
        detail = bool(req.get("detail") or req.get("options", {}).get("detail"))
        holes, curved = C.detect_holes(shape)
        result = {
            "input": path,
            "file": C.file_info(path),
            "units": "mm",
            "objects": _entry_list(entries),
            "objectCount": len(entries),
            "shape": C.shape_stats(shape),
            "bbox": C.bbox_dict(C.tight_bbox(shape)),
            "holes": holes,
            "curvedFeatures": curved,
            "warnings": [],
        }
        if len(entries) > 1:
            result["warnings"].append(
                "The file contains %d objects; measurements and drawings use their combined shape." % len(entries)
            )
        if detail:
            result["detail"] = C.face_details(
                shape,
                max_items=int(req.get("maxItems") or 200),
                offset=int(req.get("offset") or 0),
                limit=req.get("limit"),
            )
        return result
    finally:
        FreeCAD.closeDocument(doc.Name)


def _transform_shape(shape, op):
    kind = str(op.get("type") or "").lower()
    if kind in ("translate", "move"):
        v = C.vec(op.get("vector") or [op.get("dx", 0), op.get("dy", 0), op.get("dz", 0)])
        return shape.translated(v)
    if kind in ("rotate", "rotation"):
        axis = C.normalized(C.vec(op.get("axis") or [0, 0, 1]))
        angle = float(op.get("angle", 0.0))
        center = C.vec(op.get("center") or [0, 0, 0])
        return shape.rotated(center, axis, angle)
    if kind == "scale":
        factor = float(op.get("factor", 1.0))
        if factor <= 0:
            raise ValueError("scale factor must be positive")
        return shape.scale(factor)
    if kind == "mirror":
        plane = str(op.get("plane") or "XY").upper()
        normals = {"XY": [0, 0, 1], "XZ": [0, 1, 0], "YZ": [1, 0, 0]}
        if plane not in normals:
            raise ValueError("mirror plane must be XY, XZ or YZ")
        point = C.vec(op.get("point") or [0, 0, 0])
        normal = C.vec(op.get("normal") or normals[plane])
        return shape.mirror(point, normal)
    raise ValueError("Unsupported transform operation: %r" % kind)


def _hole_cut(shape, op):
    axis = C.normalized(C.vec(op.get("axis") or [0, 0, -1]))
    entry = C.vec(op.get("center") or op.get("entry") or [0, 0, 0])
    diameter = float(op.get("diameter", 0.0))
    if diameter <= 0:
        raise ValueError("hole diameter must be positive")
    radius = diameter * 0.5
    bb = shape.BoundBox
    diag = float(bb.DiagonalLength) or 100.0
    through = bool(op.get("through", False))
    if through:
        depth = diag * 2.0 + 10.0
        start = entry - axis * 2.0
    else:
        depth = float(op.get("depth", 0.0))
        if depth <= 0:
            raise ValueError("blind hole requires a positive depth or through=true")
        start = entry - axis * 1.0
        depth += 1.0
    tool = Part.makeCylinder(radius, depth, start, axis)
    return shape.cut(tool)


def _boolean_primitive(shape, op):
    kind = str(op.get("shape") or "").lower()
    pos = C.vec(op.get("position") or [0, 0, 0])
    if kind == "box":
        size = op.get("size") or [10, 10, 10]
        tool = Part.makeBox(float(size[0]), float(size[1]), float(size[2]), pos)
    elif kind == "cylinder":
        axis = C.normalized(C.vec(op.get("axis") or [0, 0, 1]))
        tool = Part.makeCylinder(float(op.get("radius", 5)), float(op.get("height", 10)), pos, axis)
    elif kind == "sphere":
        tool = Part.makeSphere(float(op.get("radius", 5)), pos)
    else:
        raise ValueError("primitive shape must be box, cylinder or sphere")
    action = str(op.get("action") or "fuse").lower()
    if action == "cut":
        return shape.cut(tool)
    if action in ("fuse", "union", "add"):
        return shape.fuse(tool).removeSplitter()
    raise ValueError("primitive action must be cut or fuse")


def _edit_shape(shape, operations):
    log = []
    for index, op in enumerate(operations, 1):
        if not isinstance(op, dict):
            raise ValueError("operation #%d must be an object" % index)
        kind = str(op.get("type") or "").lower()
        before = C.shape_stats(shape)
        resolved_edges = None
        if kind in ("translate", "move", "rotate", "rotation", "scale", "mirror"):
            shape = _transform_shape(shape, op)
        elif kind in ("fillet", "chamfer"):
            # Chamfer callers naturally say "distance"; accept it as an alias.
            radius = float(op.get("radius") or op.get("distance") or 0.0)
            if radius <= 0:
                raise ValueError("%s radius must be positive" % kind)
            resolved = C.resolve_edges(shape, op, kind)
            if not resolved:
                raise ValueError(
                    "%s needs edges (1-based indices), edgeAt [x,y,z] or edgesNear [x,y,z]"
                    % kind)
            edges = [edge for _, edge, _ in resolved]
            if kind == "fillet":
                shape = shape.makeFillet(radius, edges)
            else:
                shape = shape.makeChamfer(radius, edges)
            resolved_edges = [info for _, _, info in resolved]
        elif kind in ("hole", "drill"):
            shape = _hole_cut(shape, op)
        elif kind in ("primitive", "boolean"):
            shape = _boolean_primitive(shape, op)
        else:
            raise ValueError("Unsupported edit operation: %r" % kind)
        if shape is None or shape.isNull():
            raise RuntimeError("operation #%d (%s) produced a null shape" % (index, kind))
        after = C.shape_stats(shape)
        entry = {
            "index": index,
            "type": kind,
            "volumeBefore": before["volume"] if before else None,
            "volumeAfter": after["volume"] if after else None,
            "valid": after["valid"] if after else None,
        }
        if resolved_edges:
            # Echo what the selector actually hit: indices shift after every
            # operation, so the caller must be able to confirm the choice.
            entry["edges"] = resolved_edges
        log.append(entry)
        shape = shape.removeSplitter()
    return shape, log


def _write_step(shape, output, doc_name="FCEdit"):
    out_doc = FreeCAD.newDocument(doc_name)
    try:
        obj = out_doc.addObject("Part::Feature", "Edited")
        obj.Shape = shape
        out_doc.recompute()
        Import.export([obj], output)
        return output
    finally:
        try:
            FreeCAD.closeDocument(out_doc.Name)
        except Exception:
            pass


def do_edit(req):
    path, doc, entries, shape = _shape_doc(req)
    try:
        operations = req.get("operations") or []
        if not operations:
            raise ValueError("At least one edit operation is required")
        before = C.shape_stats(shape)
        shape, log = _edit_shape(shape, operations)
        if shape.Volume <= 1.0e-6:
            raise RuntimeError("The edited result has no positive volume; refusing to export")
        if not shape.isValid():
            raise RuntimeError("The edited result is not a valid B-Rep; refusing to export")
        out = req.get("output")
        if not out:
            stem, _ = os.path.splitext(path)
            out = stem + "_edited.step"
        out = os.path.abspath(os.path.expanduser(out))
        overwrite = bool(req.get("overwrite", False))
        if os.path.normcase(out) == os.path.normcase(path) and not overwrite:
            raise ValueError("Refusing to overwrite the input file; pass overwrite=true or choose another output")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        _write_step(shape, out)
        result = {
            "ok": True,
            "input": path,
            "output": out,
            "operations": log,
            "before": before,
            "after": C.shape_stats(shape),
            "holes": C.detect_holes(shape)[0],
            "warnings": [],
        }
        if len(entries) > 1:
            result["warnings"].append(
                "The input holds %d parts (%s); the edit was applied to their combined "
                "shape and exported as one object, so part names and colours are not kept."
                % (len(entries), ", ".join(e["label"] for e in entries[:8])))
        if req.get("saveFCStd"):
            fcstd = os.path.splitext(out)[0] + ".FCStd"
            fc_doc = FreeCAD.newDocument("FCSave")
            try:
                obj = fc_doc.addObject("Part::Feature", "Edited")
                obj.Shape = shape
                fc_doc.recompute()
                fc_doc.saveAs(fcstd)
                result["fcstd"] = fcstd
            finally:
                FreeCAD.closeDocument(fc_doc.Name)
        return result
    finally:
        FreeCAD.closeDocument(doc.Name)


def do_drawing(req):
    path, doc, entries, shape = _shape_doc(req)
    try:
        options = dict(req.get("options") or {})
        for key in ("sheet", "scale", "views", "hiddenLines", "dimensions", "title",
                    "material", "drawingNo", "formats", "outputDir"):
            if key in req and key not in options:
                options[key] = req[key]
        formats = options.get("formats") or ["svg", "dxf", "pdf", "png"]
        if isinstance(formats, str):
            formats = [formats]
        allowed = {"svg", "dxf", "pdf", "png"}
        formats = [str(f).lower().lstrip(".") for f in formats]
        bad = [f for f in formats if f not in allowed]
        if bad:
            raise ValueError("Unsupported formats: %s" % ", ".join(bad))
        views_wanted = options.get("views") or ["front", "top", "right", "iso"]
        if isinstance(views_wanted, str):
            views_wanted = [views_wanted]
        if str(options.get("sheet") or "A3").upper() == "A4":
            # The compact A4 sheet draws only these views (see fc_render.py).
            views_wanted = [v for v in views_wanted if v in ("front", "top")]
            if "front" not in views_wanted:
                views_wanted.insert(0, "front")
        unknown = [v for v in views_wanted if v not in C.VIEW_SPECS]
        if unknown:
            raise ValueError("Unknown view(s): %s. Available: %s" % (
                ", ".join(unknown), ", ".join(C.VIEW_SPECS.keys())))
        views = {}
        for name in views_wanted:
            views[name] = C.project_view(shape, name, hidden=bool(options.get("hiddenLines", False)))
        holes = C.detect_holes(shape)[0]
        meta = {
            "title": options.get("title") or "二维加工图",
            "material": options.get("material") or "—",
            "drawingNo": options.get("drawingNo") or "",
            "header": options.get("header") or "FreeCAD 二维加工图",
            "sourceName": os.path.basename(path),
        }
        drawing = dict(options)
        drawing.setdefault("dimensions", True)
        drawing.setdefault("hiddenLines", False)
        scene, scale = R.build_scene(shape, views, holes, meta, drawing)
        out_dir = options.get("outputDir")
        if not out_dir:
            out_dir = os.path.join(os.path.dirname(path), os.path.splitext(os.path.basename(path))[0] + "_drawing")
        out_dir = os.path.abspath(os.path.expanduser(out_dir))
        os.makedirs(out_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(path))[0] + "_drawing"
        base = os.path.join(out_dir, stem)
        written = R.export_scene(scene, base, formats)
        try:
            with open(path, "rb") as src:
                source_hash = hashlib.sha256(src.read()).hexdigest()
        except OSError:
            source_hash = None
        manifest = {
            "input": path,
            "sourceName": os.path.basename(path),
            "sourceHash": source_hash,
            "outputDir": out_dir,
            "sheet": str(drawing.get("sheet") or "A3").upper(),
            "scale": scale,
            "scaleLabel": R.scale_label(scale),
            "title": meta["title"],
            "header": meta["header"],
            "material": meta["material"],
            "drawingNo": meta["drawingNo"],
            "dimensions": bool(drawing.get("dimensions", True)),
            "hiddenLines": bool(drawing.get("hiddenLines", False)),
            "views": {k: {"width": v["width"], "height": v["height"]} for k, v in views.items()},
            "holes": holes,
            "holeCount": len(holes),
            "hiddenLinesSkipped": int(getattr(scene, "hiddenSkipped", 0)),
            "files": written,
            "generatedBy": "dsh-freecad " + _plugin_version(),
            "generatedAt": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        manifest_path = os.path.join(out_dir, "drawing_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        manifest["manifest"] = manifest_path
        return manifest
    finally:
        FreeCAD.closeDocument(doc.Name)


def _plugin_version():
    """Version of this package, so manifests stop lying after every release."""
    try:
        import json as _json
        pkg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "package.json")
        with open(pkg, "r", encoding="utf-8") as fh:
            return str(_json.load(fh).get("version") or "unknown")
    except Exception:
        return "unknown"


def dispatch(req):
    action = str(req.get("action") or "").lower()
    if action in ("inspect", "read", "info"):
        return do_inspect(req)
    if action in ("edit", "modify"):
        return do_edit(req)
    if action in ("drawing", "draw", "2d"):
        return do_drawing(req)
    if action in ("measure", "measurement", "distance"):
        return do_measure(req)
    raise ValueError(
        "Unknown action %r; expected inspect, edit, drawing or measure" % action)


def _json_safe(value):
    """Normalize values that Python's JSON decoder accepts but DSH does not.

    JSON has no -0 literal distinction, so Python writes ``-0.0`` and the
    JavaScript host parses it as negative zero. DSH's lossless-JSON guard
    rejects that (as well as NaN/Infinity), so normalize at the protocol edge.
    """
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return 0.0 if value == 0 else value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def main():
    # FreeCADCmd interprets extra command-line arguments as files to open, so
    # the Node host passes the two JSON paths through the environment.
    req_path = os.environ.get("FREECAD_PLUGIN_REQUEST")
    result_path = os.environ.get("FREECAD_PLUGIN_RESULT")
    if not req_path or not result_path:
        print("FREECAD_PLUGIN_REQUEST and FREECAD_PLUGIN_RESULT must be set", file=sys.stderr)
        return 2
    result = {"ok": False, "error": "worker did not run"}
    _setup_progress()
    C._report("worker 启动")
    try:
        with open(req_path, "r", encoding="utf-8-sig") as fh:
            req = json.load(fh)
        C._report("开算: %s" % str(req.get("action") or "inspect"))
        result = {"ok": True, "data": dispatch(req)}
        C._report("完成")
    except Exception as exc:
        result = {
            "ok": False,
            "error": str(exc),
            "errorType": exc.__class__.__name__,
            "traceback": traceback.format_exc(),
        }
    try:
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(_json_safe(result), fh, ensure_ascii=False, indent=2,
                      allow_nan=False)
    except Exception:
        traceback.print_exc()
    return 0 if result.get("ok") else 1


# FreeCADCmd executes a script in its own namespace where __name__ is not
# necessarily "__main__", so call main() unconditionally.
main()
