# Contributing

Thanks for looking. This is a small, single-maintainer plugin; the most useful
contributions are **bug reports with a minimal STEP file** and **fixes to the
Python drawing layer**.

## Layout

```
index.js            host half: tool registration, argument validation, spawning freecadcmd
lib/client.js       browser half: the "FreeCAD" page under DSH → Settings
dsh/fc_common.py    geometry helpers: shape loading, hole detection, HLR projection, face/edge details
dsh/fc_render.py    drawing engine: sheet, views, dimensions, hole table, title block, exporters
dsh/fc_worker.py    headless entry point: reads the request JSON, dispatches, writes the result JSON
examples/           synthetic part used by the docs and manual tests
scripts/install.mjs installs this package into a DSH profile
docs/               architecture, tools, drawing engine, troubleshooting, development, limitations
```

The host half never imports FreeCAD. All geometry happens in `freecadcmd`'s own
Python environment, which is why the plugin works without a matching Python
version on the host.

## Running it against a live DSH install

```bash
node scripts/install.mjs            # into ~/.dsh/profiles/desktop
node scripts/install.mjs --profile "C:\Users\me\.dsh\profiles\other"
```

Then **restart DSH** (a bundle is only mounted at startup) and check:

```
freecad_status                      # should print the FreeCAD version
```

If it reports "not found", open **DSH → Settings → FreeCAD** and point it at
`freecadcmd.exe`; the value is stored in the profile and picked up on the next
tool call (no restart needed).

## Manual test checklist

There is no CI yet, so every change to `dsh/*.py` must clear this list by hand:

1. `node index.js --self-test` — argument validation and schema smoke test.
2. `freecad_status` reports a real FreeCAD version.
3. `freecad_inspect_step examples/demo_bracket.step` → 5 holes, bounding box
   100 × 60 × 37 mm, volume ≈ 133 000 mm³.
4. `freecad_step_to_drawing examples/demo_bracket.step` → four formats written,
   sheet renders without overlapping text, hole table lists H1–H5.
5. `freecad_edit_step` on a copy: translate by +10 Z, then inspect it again and
   confirm the bounding box moved.
6. Delete `out/` and confirm nothing was written outside the requested directory.

If you touch the drawing engine, **open the PNG and look at it**. A green test
list does not mean the sheet is legible.

## Style

- JavaScript: no dependencies, ESM, 2-space indent, `node --check index.js`.
- Python: stdlib + the modules shipped with FreeCAD only (no `pip install`),
  4-space indent, `python -m py_compile dsh/*.py`.
- User-facing errors are English in `index.js`, Chinese in the drawing output
  (the drawings target Chinese machining conventions).

## Commits and pull requests

- One concern per PR; "fix drawing layout" and "add a tool" do not belong together.
- Update `CHANGELOG.md` under `## Unreleased` for anything user-visible.
- **`README.md` (Chinese) and `README.en.md` (English) must change together.**
  A PR that edits one and not the other will be asked to update both; the two
  files are meant to be structural mirrors.
- Never commit a customer's CAD file. `examples/` is for synthetic parts only —
  if a bug needs a real model, reduce it to a minimal synthetic shape first.

## Reporting bugs

Include the output of `freecad_status`, the FreeCAD version, the OS, the exact
tool arguments, and (if possible) a minimal STEP file that reproduces the issue.
For drawing problems, attach the PNG — a screenshot beats a description.
