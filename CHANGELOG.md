# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

全部问题都在 Windows 11 + FreeCAD 1.1.4 便携版 + DeepSeek Harness Desktop 0.2.1-rc.3 上复现过，
修复后同一环境下重测通过；每一条都有对应的回归测试（在 0.4.2 代码上失败，修复后通过）。

### Fixed

- **DXF 上下颠倒。** 版面坐标是 y 向下（与 SVG 相同），DXF 世界坐标是 y 向上，写出时没翻转：
  页眉跑到底部、标题栏跑到顶部、俯视图在主视图上方、零件轮廓整体镜像——偏偏是给 CAM 用的格式。
  现在 `render_dxf` 统一做 `y → 页高 − y`；文字对齐改回基线（与 SVG/PDF 一致）。
- **SVG 竖直尺寸数字方向反了**（从上往下读，PDF/PNG 是从下往上）。`rotate()` 取反。
- **DSH 里点"停止"关不掉 FreeCAD。** `execute()` 没接 DSH 传入的 `exec.signal`，取消后
  `freecadcmd` 照常跑完并写出全部文件，而 DSH 会一直等工具结束。现在 abort 会结束子进程并等它退出。
- **单次 `timeoutMs` 在 DSH 里不生效。** dsh-base 默认挂载的 tool-call-timeout-policy 按工具*声明的*
  `timeoutMs`（5 分钟）强制超时，所以调用参数里给 10 分钟也会在 5 分钟时报"tool call timed out"，
  而 FreeCAD 还在后台把文件写完。工具改为声明 30.5 分钟上限，实际预算由插件按调用参数执行；
  `freecad_inspect_step` 也补上了 `timeoutMs` 参数。
- **多零件 STEP 基本不可用。** 导入时把 `App::Part` 容器和 `App::Origin` 的轴/基准面/原点都当成零件：
  两零件的装配被报成 10 个对象、体积 -3.6e152，出图报 `HLR projection failed ... command not done`，
  连一次平移编辑都被拒绝（"no positive volume"）。现在只取真正的几何对象，跳过无限大的形状。
- **嵌套装配里零件位置被算两次**（`Shape` 已含自身 Placement，又乘了一次全局 Placement）：
  App::Part 内 y=50 的零件出现在 y=100。
- **模型看不到它需要的编号。** 模型读到的是渲染文本而不是 JSON：
  - `freecad_inspect_step` 不列面编号（`freecad_measure` 恰恰要按面编号量）；现在每个面都列出，
    圆柱面带直径与凹/凸。
  - 一页 200 条边只显示前 24 条，提示却是"下一页 offset=200"，第 25–200 条永远看不到；
    现在本页每一条都列出，默认页改为 50 条。
  - 多零件文件现在列出每个零件的名称、尺寸和体积。
  - `freecad_edit_step` 现在逐步列出操作和实际命中的边（0.3.0 的说明里写了但渲染里没有），
    并显示 warnings。
- **夹角最大只报 90°。** 两条共顶点的直边夹 135° 报成 45°。现在共顶点时给 0–180° 的射线夹角；
  两个面另给 `normalAngle`（外法线夹角 0–180°），`value` 保持两平面夹角 0–90° 以兼容旧调用。
- **有腰形孔时孔号跳号**（S1、H2、H3，没有 H1）。圆孔和腰形孔分别计数。
- **孔表 X/Y 列对 X、Y 轴向的孔填错。** X 轴孔中心 (20,10,15) 在孔表里显示为 X=10、Y=15。
  孔表改为 X / Y / Z 三列模型坐标，沿孔轴的那一列写 "—"；表宽不变。
- **自动比例不合国标。** 候选里有 0.8/0.7/0.6/0.35/0.15，会印出 1:1.25、1:1.43、1:1.67、1:2.86、1:6.67；
  仓库自带的示例件就是 1:1.67。现在只取 GB/T 14690 的优先与允许比例（示例件变为 1:2）。
- `edit` 处理多零件文件时会提示"合并成一个对象导出，零件名和颜色不保留"，不再静默。
- `scripts/install.mjs` 结尾的 `Ø` 是 GBK 乱码（`脴`）。

### Tests

- `tests/test_renderer.py`：DXF 方向（文字、直线、圆、多段线）、文字对齐、SVG 旋转方向、孔表三列、
  国标比例，共新增 10 条（CI 运行）。
- `tests/test_host.mjs`：工具声明的超时高于参数上限、渲染文本列全面/边/零件/命中边/夹角、
  abort 与单次超时能在几秒内杀掉卡住的子进程、`execute()` 转发 `exec.signal`（CI 运行）。
- `tests/test_geometry.py`（新，需要 FreeCAD）：多零件导入、嵌套 Placement、多零件编辑与出图、
  孔号、夹角、示例件比例与 DXF 方向，共 23 条断言。

## 0.4.2 — 打包脚本跨平台

### Fixed

- `scripts/package.mjs` 不再调用 Windows PowerShell 的 `Compress-Archive`，改用项目自带的
  ZIP 写入器 `scripts/zip.mjs`（Node 内置 `zlib` + 手写 CRC32/中央目录，零依赖）。
  之前打包只能在 Windows 上跑，`ci` 在 ubuntu-latest 上必然在这一步失败。
- 同一份源码现在在各平台产出一致的归档：固定时间戳、条目名统一正斜杠、
  修掉 Windows 下 `scripts/install.mjs` 因路径分隔符不同而重复入包的问题。

无运行时行为变化（只影响构建）。

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
