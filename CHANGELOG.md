# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## 0.4.1 — 改走 OIDC 发布

### Changed

- 新增 `.github/workflows/publish.yml`：npm 发布从"granular token + bypass 2FA"改为
  **Trusted Publishing（GitHub OIDC）**。不再需要任何长期密钥，发布时自动带 provenance，
  也不再受 2027-01 起 npm 取消 bypass-2FA 直发的影响。
- `docs/development.md` 第 7 节重写：OIDC 为首选路径，token 降为兜底。

无代码行为变化。

## 0.4.0 — 孔识别的三类盲区

### Fixed

- **腰形孔（长圆孔）现在能认**。两段平行的半圆柱 + 平直侧壁合成一条记录：直径=宽、
  `length`=全长，孔表里记 `S1`、形状写 `宽×长`，标注写 `2× 8×28 通槽`。
- **斜孔深度不再多算**。深度改用圆柱面自身的接缝长度，而不是参数区间——以前 45° 孔会
  报出被上表面切掉之后整段的长度。
- **开在曲面/过渡面上的孔不再消失**。以前这类孔（例如环件侧壁的径向孔）直接漏检；
  现在单独归到 `curvedFeatures`，给轴向、半径、覆盖率、包角，由模型决定要不要标。
- **孔表不再压住视图**。选比例时把孔表那一列扣掉，表格固定在右上角；3:1 之类的大比例
  以前会把表格叠在俯视图上。

### Internal

- `detect_holes` 改为「先聚类、后过滤」：半径/轴线/轴向范围相近的面先合成候选再判覆盖率，
  否则半圆柱面永远过不了 0.6 门槛。
- 新增 `tests/test_holes.py`（22 条断言：通孔、径向孔、斜孔、腰形孔、沉头孔、曲面孔），
  依赖 FreeCAD，手动跑：`freecadcmd tests/test_holes.py`。

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
