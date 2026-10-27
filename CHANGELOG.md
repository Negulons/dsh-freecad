# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 0.3.0 — tools an LLM can actually steer: measure, page, pick edges by position

Everything here targets one failure mode: the model has a tool but cannot get the
few numbers it needs to decide anything.

### Added

- `freecad_measure`: read-only measurement. Distance between points/faces/edges,
  angle between two faces or two straight edges, diameter of a cylindrical face or
  a circular edge.
  - Two touching faces measure `distance: 0`, so the result also carries
    `planeOffset` (plane-to-plane distance) — that is how you get plate thickness.
  - One bad item no longer voids the batch: it comes back as `{index, error}` and
    `resolved` reports how many succeeded.
- `freecad_edit_step` can pick edges by position: `edgesNear: [x,y,z]` (every edge
  nearby), `edgeAt: [x,y,z]` (the nearest one), `edgesNearRadius`. Indexes renumber
  after every operation, so this is the robust path.
  - `operations[i].edges` echoes the edges that were actually hit (index, length,
    endpoints, midpoint) so the model can confirm the choice.
  - A miss reports the nearest edge and its distance instead of "no match".
- `freecad_inspect_step` pages properly: `offset` / `limit`, plus `edgesTotal` /
  `facesTotal` and `nextEdgeOffset` / `nextFaceOffset`; every edge also reports `mid`.
- Per-call `timeoutMs` (default 300 s, max 1800 s). The worker streams phases to a
  progress file, results carry `timing.elapsedMs` and `timing.phases`, and timeout
  errors now name the last phases instead of only saying it timed out.

### Verified on `examples/demo_bracket.step`

- `planeOffset` gives plate thickness 12.000 mm; a cylindrical face gives Ø25.000;
  two points give 86.833 mm.
- `edgesNear [50,30,11.9]` hits 3 edges; fillet R1 drops volume 99871.42 → 99834.68 mm³.
- `offset: 8, limit: 5` returns edges #9–#13 with `nextEdgeOffset: 13`.

## 0.2.6 — hole table keeps every row, hidden lines stop duplicating outlines

### Fixed

- The hole table had a hard 10-row cap (`holes[:10]` in `fc_render.py`): a part with more
  holes silently lost rows. It now continues in extra blocks (10 rows each, at most three)
  and the caption says `共 N 孔`.
- Shadow hidden lines: for symmetric extrusions OCCT hands back one hidden edge per visible
  one, so `hiddenLines: true` drew dashed line work on top of solid outlines. Hidden edges
  fully covered by visible geometry (polylines, sharp-edge lines and circles alike) are now
  dropped. Sample drawing: 12 of 47 HIDDEN segments sat on OUTLINE, now 0.
- `drawing_manifest.json` no longer claims `generatedBy: dsh-freecad 0.1.0`; it reads the
  version from `package.json` and reports `holeCount` plus `hiddenLinesSkipped`.

### Added

- `tests/test_renderer.py`: ten layout-only unit tests (hole-table pagination, hidden-line
  deduplication, reversed endpoints) that need neither FreeCAD nor matplotlib; CI runs them.

## 0.2.5 — lead with the plugins page

### Changed

- Install instructions now lead with "open the DSH **Plugins** page and search `dsh-freecad`", which was
  verified end-to-end on a clean instance. The manual npm/`install.mjs` and from-source paths moved down
  and stay documented, including the top-level-vs-`insert` pitfall of `cordis.patch.yml`.

## 0.2.4 — portable FreeCAD actually starts

### Fixed

- Portable (7z) FreeCAD was still unusable: the user-directory redirect pointed at
  `%TEMP%`, and FreeCAD 1.1.4 aborts there with
  `Unknown runtime error occurred while initializing FreeCAD`. The redirect now goes to
  `dsh-user/` beside the install (the portable convention, measured working), with the temp
  directory kept as the fallback for read-only installs. `freecad_status` should now report
  the real version instead of `printed no FreeCAD version`.

## 0.2.3 — README images behind a CDN

### Fixed

- README screenshots moved from `raw.githubusercontent.com` to `cdn.jsdelivr.net`
  (`gh/Negulons/dsh-freecad@main/...`). `raw.githubusercontent.com` is commonly
  unreachable from mainland China, so the images showed as broken for exactly the
  audience this plugin is written for.

## 0.2.2 — package metadata

### Fixed

- `package.json` now carries `repository`, `homepage`, `bugs` and `funding`, so
  the npm package page links back to this repository instead of looking like a
  detached tarball.

## 0.2.1 — docs patch

### Fixed

- The two README screenshots used repo-relative paths, which npm renders as
  `https://www.npmjs.com/package/...` and therefore showed as broken images on
  the package page. They now use absolute `raw.githubusercontent.com` URLs, so
  the same Markdown works on GitHub and on npm.

## 0.2.0 — first public release

### Added

- **Settings page**: DSH → Settings → FreeCAD. It sets the `freecadcmd`
  executable path (volatile, so a save re-applies the plugin configuration
  immediately) and links to the official GitHub releases and the TUNA mirror.
  The value overrides the profile config, the `FREECAD_CMD` environment variable
  and the built-in `C:\Program Files\FreeCAD …` candidates, in that order.
- `NOTICE`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `.gitignore`.
- English README (`README.en.md`); documentation reorganised into
  `docs/{architecture,tools,drawing-engine,troubleshooting,development,limitations}.md`.

### Changed

- Plugin version `0.1.0` → `0.2.0`; the three tools and their parameters are
  unchanged from the last internal build.
- Installer consolidated into `scripts/install.mjs` (zero dependencies; falls back
  to copying into `node_modules` when `pnpm` is unavailable).
- Copyright holder named in `LICENSE`.

### Fixed

- **The plugin failed to activate** with `TypeError: Invalid effect`. `apply()`
  returned a value; cordis treats anything that is neither `undefined`/`null`
  nor a disposer function as an invalid effect, which aborted the whole entry —
  the tools never registered and the settings page never appeared.
- `freecad_status` now says where to configure the path ("set the FreeCAD path in
  DSH → Settings → FreeCAD") instead of only listing the default candidates.

### Known limitations

- Windows-first: `freecadcmd` discovery covers the standard Windows install
  locations. Linux and macOS work only when the path is configured by hand.
- Drawings carry overall width/height and a hole table. Feature dimensions
  (boss diameter, step heights, hole positions per view), sections, detail views,
  GD&T and surface finish symbols are not generated.
- The hole table lists at most 10 holes per sheet.
- Holes are detected from cylindrical faces only; slots, D-shaped holes and
  pockets do not appear in the table.
- No automated test suite yet.
