# 架构

`dsh-freecad` 是一个 **DSH bundle 插件**：Node 侧只做工具注册、参数校验和文件搬运，全部 CAD 计算交给本机 `freecadcmd` 里的 Python（FreeCAD 1.x + OCC + TechDraw HLR），结果以 JSON 文件回传。

## 1. 进程模型

```
DSH Desktop (Node)
  └─ cordis bundle: dsh-freecad          ← 由 profile 的 cordis.patch.yml 插入
       index.js  (host 半侧)              export name / inject / apply(ctx, config)
         │  注册 4 个工具、校验参数、解析路径
         │  child_process.spawn(freecadcmd, [dsh/fc_worker.py])
         │  env: FREECAD_PLUGIN_REQUEST=<临时目录>/request.json
         │       FREECAD_PLUGIN_RESULT =<临时目录>/result.json
         ▼
       freecadcmd (FreeCAD 1.x, 无 GUI, 自带 Python 3.11)
         └─ dsh/fc_worker.py   入口：分派 inspect / edit / drawing
              ├─ dsh/fc_common.py   导入、统计、孔识别、HLR 投影
              └─ dsh/fc_render.py   Scene + SVG/DXF/PDF/PNG 渲染

  浏览器
  └─ lib/client.js (client 半侧)         设置页「FreeCAD」，读写 freecadPath
```

要点：

- **不共享 Python 环境**。FreeCAD 的解释器里有 `FreeCAD`/`Part`/`TechDraw`/`Import`/`matplotlib`/`PIL`，但没有 DSH 的 Node 环境；两侧只通过 JSON 文件通信，所以宿主不需要匹配版本的 Python。
- **每次调用新起一个进程**。无常驻服务、无状态残留；调用结束后临时目录被删。
- **重工具互斥**。`inspect`/`edit`/`drawing` 的 `isConcurrencySafe: () => false`，`freecad_status` 为 `true`。

## 2. 两个半侧

DSH 插件可以同时有 host 半侧和浏览器半侧；本插件两者都有：

| 半侧 | 文件 | 职责 |
|---|---|---|
| host | `index.js` | 注册工具、校验参数、解析 `freecadcmd`、spawn worker、把结果转成模型可读的文本 |
| client | `lib/client.js` | 在 **设置 → FreeCAD** 贡献一页：`freecadPath` 输入框 + 两个下载链接 |

浏览器半侧通过 `window.__ModuleLoader__.load({ id, factory })` 注册，`apply(ctx)` 里用
`ctx.slots.inject('settings.section', …)` + `ctx.configForms.whileServed(['freecad'], …)` 挂载。
**`apply()` 的返回值必须严格是 `undefined` 或一个销毁函数**——返回其他任何值，cordis 会抛
`TypeError: Invalid effect` 并让整个条目启动失败（0.2.0 修过这个 bug）。

## 3. 为什么用 JSON 文件而不是 stdout / 命令行参数

| 约束 | 做法 | 原因 |
|---|---|---|
| `freecadcmd script.py arg1 arg2` 会把额外参数当成要打开的 CAD 文件 | 请求/结果路径走环境变量 | 实测传参报 `no supported file format` |
| FreeCAD 自己会往 stdout 打印大量日志 | 结果写文件，协议不依赖 stdout | 避免日志污染协议 |
| Windows 控制台多次转码导致中文乱码 | 请求按 UTF-8 读（容忍 BOM），结果 `ensure_ascii=False` 写 UTF-8 | 中文标题/材料名稳定 |
| `freecadcmd` 执行脚本时 `__name__` 不保证是 `__main__` | `fc_worker.py` 末尾**无条件**调用 `main()` | `if __name__ == "__main__"` 守卫在 FreeCADCmd 下不生效 |

## 4. 请求 / 结果协议

`request.json`（Node → Python）：

```json
{ "action": "inspect" }
{ "action": "edit",    "input": "...", "output": "...", "operations": [ ... ], "overwrite": false, "saveFCStd": false }
{ "action": "drawing", "input": "...", "outputDir": "...", "options": { "sheet": "A3", "views": ["front","top","right","iso"] } }
```

`action` 别名：`inspect|read|info`、`edit|modify`、`drawing|draw|2d`。

`result.json`（Python → Node）：

```json
{ "ok": true,  "data": { ... } }
{ "ok": false, "error": "可读首行错误", "errorType": "ValueError", "traceback": "..." }
```

Node 侧（`runWorker`）的行为：

1. 找不到可执行文件 → `FreeCADCmd not found …`（并提示去设置页配路径）
2. 5 分钟未结束 → 杀进程并抛超时
3. 结果文件缺失 → `FreeCAD produced no result (exit N)` + stderr
4. `ok:false` → `FreeCAD worker failed: <error>`，模型看到的是 Python 侧首行错误

**数值规范化**：`_json_safe()` 在写结果前把 `-0.0` 归一为 `0.0`、把 `NaN/Infinity` 转为 `null`。
DSH 的 lossless-JSON 守卫会拒绝负零与 NaN——这是真实踩过的坑（FreeCAD 对某些面返回 `-0.0`，整次调用被拒）。改动这一层时不要删。

## 5. 路径与工作目录

- 输入/输出参数由 Node 侧 `path.resolve()` 解析（相对路径按 DSH 进程 cwd），再传给 Python。
- Python 侧统一 `os.path.abspath(os.path.expanduser(...))`，并自动 `makedirs` 输出目录。
- 工具不接受目录：`input` 必须是文件。

## 6. 文档与对象生命周期

- 每次任务 `FreeCAD.newDocument("FCImport")` → `Import.insert()` → 读取 → `finally: FreeCAD.closeDocument()`；异常路径也关闭。
- 编辑导出时新建 `FCEdit` 文档放结果 shape，`Import.export()` 后立即关闭。
- 多对象 STEP：所有对象按 `getGlobalPlacement()` 烘焙到世界坐标后 `makeCompound()` 成一个 shape 参与测量与出图，并在 `warnings` 里提示。

## 7. 关键设计决策

| 决策 | 原因 |
|---|---|
| 用 `Import.insert` 而非 `Import.open` | insert 在指定文档内工作，关闭文档即彻底释放 |
| 包围盒用 `optimalBoundingBox()`，失败才退回 `BoundBox` | `BoundBox` 被 B 样条控制点撑大（19 mm 的衬套会报 145 mm），毁掉自动比例 |
| 孔识别只认**凹**全圆柱面（覆盖率 ≥ 0.60、法向指向轴心） | 避免把凸台/外圆柱当孔；覆盖率过滤半圆柱切口 |
| 孔深用**边离散采样**而不是 `Face.ParameterRange` | 面参数区间可能超出被裁剪的实际面，会把孔深算大 |
| 同轴同径相邻孔面合并 | 一条孔被拆成多个面时仍应计为一个孔 |
| 通孔用 `shape.isInside()` 检查两端轴线延长点 | 比「深度≈板厚」可靠，能识别局部通孔 |
| 投影坐标系**用两条单位线标定后求逆** | `TechDraw.projectEx` 的局部 2D 朝向随方向/版本变化，不能假设 |
| HLR 只取 `projectEx` 的第 0/3/5/8 组 | 第 1/2/6/7 组是平滑/接缝边（圆柱纵向母线），不是真实棱边 |
| 直线与整圆保留为精确图元 | DXF 里是真正的 LINE/CIRCLE，CAM 能识别孔，不会炸成上千条线段 |
| 样条按 ≤64 点重采样 | OCC `discretize` 可能给数千点，文件暴涨而无可见收益 |
| 编辑默认不覆盖输入 | 防呆：几何级布尔一旦出错，原文件仍在 |
| 图纸按目录写，另存 `drawing_manifest.json`（含来源 SHA256） | 图纸是可再生产物，用 manifest 追溯 |
| PDF/PNG 用 matplotlib 的 Agg 后端 | FreeCADCmd 无 GUI，页面自带的 `exportPDF/exportSvg` 在 headless 下不可用 |

## 8. 数据结构速查

### 8.1 shape_stats（inspect/edit 都返回）

```json
{
  "shapeType": "Solid", "valid": true,
  "solids": 1, "shells": 1, "faces": 14, "edges": 33, "vertices": 24,
  "volume": 99871.424624, "area": 18943.9,
  "bbox": { "min": [..], "max": [..], "size": [100, 60, 37] },
  "centerOfMass": [x, y, z]
}
```

### 8.2 hole

```json
{
  "id": "H3", "axis": [0,0,1], "axisName": "Z",
  "diameter": 25.0, "radius": 12.5,
  "depth": 37.0, "through": true,
  "center": [0,0,18.5], "entry": [0,0,0], "exit": [0,0,37],
  "coverage": 1.0
}
```

### 8.3 view（`fc_common.project_view` 返回）

```json
{
  "name": "front", "label": "主视图", "labelEn": "FRONT",
  "visible": [[[x,y], ...]], "hidden": [],
  "exactVisible": [{"type":"line","p1":[..],"p2":[..]}, {"type":"circle","c":[..],"r":12.5}],
  "exactHidden": [],
  "bbox": [0,0,w,h], "width": 100.0, "height": 37.0, "rawBBox": [..]
}
```

坐标已归一化到视图左下角，渲染器只做缩放和平移。

### 8.4 drawing_manifest.json

输出目录下固定生成：`input`、`sourceName`、`sourceHash`（SHA256）、`outputDir`、`sheet`、`scale`、
`scaleLabel`、`title`/`header`/`material`/`drawingNo`、`dimensions`、`hiddenLines`、`views{宽高}`、
`holes`、`files{}`、`generatedBy`、`generatedAt`。

## 9. 配置与优先级

host 半侧只认一个字段，声明为 **volatile**（保存即重新应用插件配置）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `freecadPath` | string | `freecadcmd` 的路径；接受 **exe 路径 / bin 目录 / 安装根目录** 三种写法 |

解析顺序：

1. 设置页「设置 → FreeCAD」写入的 `freecadPath`
2. profile 的 `cordis.patch.yml` 里 `config.freecadPath`（或旧写法 `config.settings.freecadPath`）
3. 环境变量 `FREECAD_CMD`
4. 内置候选：`C:\Program Files\FreeCAD 1.1|1.0|FreeCAD\bin\freecadcmd.exe`

配置从 `apply(ctx, config)` 拿到；volatile 字段是 schemastery 的 ref，读值用 `config.freecadPath.get()`。

**profile patch 必须把插件写成顶层条目**（`- id: freecad` / `name: dsh-freecad`），不能放进
`- insert:` 块。DSH 的设置编辑器只会给「顶层、且没有 `insert` 键」的行写 config；写进 insert 块
的条目每次保存都会被拒（`settings/rejected: Configuration for "freecad" is overridden by ...`）。

便携版 FreeCAD 还要一处约定：它把用户目录放在自己旁边，在受保护/只读目录下会报
`Could not create directories`。宿主因此对「非 Program Files」的 `freecadcmd` 自动注入
`FREECAD_USER_HOME` / `FREECAD_USER_DATA` / `TMP`（指向系统临时目录），安装版不动，用户配置不受影响。
旧的非 volatile 写法仍然兼容，所以两种配置文件都能用。

## 10. 超时与中止

- 工具级 `timeoutMs = 5 * 60_000`；`freecad_status` 为 30 s。
- 宿主取消（abort signal）会 kill 子进程并抛 `FreeCAD worker aborted`。
- 大装配的 HLR 可能超时：先用小模型验证，再上大文件（见 [limitations.md](limitations.md)）。

## 11. 代码地图

| 文件 | 行数 | 职责 |
|---|---|---|
| `index.js` | ~700 | 四个工具的 JSON Schema、参数校验、`freecadcmd` 探测、spawn、结果格式化、`Config` 导出 |
| `lib/client.js` | ~350 | 设置页组件与注册 |
| `dsh/fc_worker.py` | ~410 | 入口、分派、request/result 编解码 |
| `dsh/fc_common.py` | ~800 | 导入、shape 统计、孔识别、面边明细、HLR 投影 |
| `dsh/fc_render.py` | ~840 | 图纸引擎：图幅、视图排版、尺寸、孔表、标题栏、四种导出 |
| `scripts/install.mjs` | ~240 | 装进 profile（备份、依赖、bundle、patch、pnpm） |
| `scripts/package.mjs` | ~124 | 打可分发的 zip |
