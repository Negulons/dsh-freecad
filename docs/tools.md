# 工具与参数参考

五个工具由 `index.js` 的 `apply()` 注册。所有长度单位 **mm**，角度单位 **度**。工具名以 `freecad_` 为前缀。

---

## freecad_status

检查 FreeCADCmd 是否可用、worker 文件是否就绪。

- 参数：无
- 返回：`{ freecadCmd, exists, workerExists, version, error }`
- 用途：出图/导入异常时的第一个排查动作。

---

## freecad_inspect_step

读取 CAD 文件，返回几何统计、对象列表与圆柱孔识别结果。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `input` | string | ✅ | STEP/STP（也接受 `.stpz`、IGES、BREP）绝对路径 |
| `detail` | boolean | | 是否返回面/边明细 |
| `maxItems` | integer | | 单页条数上限，10–2000，默认 200 |
| `offset` | integer | | 跳过前多少条（0 = 从第 1 条开始），默认 0 |
| `limit` | integer | | 本页条数（面和边各自），默认 50 |
| `timeoutMs` | integer | | 本次调用超时，默认 300000，最大 1800000 |

支持的扩展名：`.step` `.stp` `.stpz` `.iges` `.igs` `.brep` `.brp`（大小写不敏感）。

返回（节选）：

```json
{
  "input": "...", "units": "mm",
  "file": { "path": "...", "name": "...", "sizeBytes": 15954, "modified": "..." },
  "objects": [ { "name": "Part__Feature", "label": "...", "typeId": "Part::Feature",
                 "stats": { ... }, "bbox": { ... } } ],
  "objectCount": 1,
  "shape": { shape_stats 结构 },
  "bbox": { "min": [...], "max": [...], "size": [...] },
  "holes": [ hole 结构 ... ],
  "curvedFeatures": [ curved 结构 ... ],
  "warnings": [],
  "detail": { "faces": [...], "facesTruncated": false, "edges": [...], "edgesTruncated": false }
}
```

- `holes` 最多 200 条，按“轴线 Z→Y→X、坐标、直径”排序，编号 `H1..Hn`（腰形孔是 `S1..Sn`）。
- `holes[i].kind`：`hole`（圆孔，含斜孔）或 `slot`（腰形孔，额外带 `width` / `length`，直径字段即宽度）。
- `holes[i].depth` 取圆柱面自身的接缝长度，斜孔也是真实轴长；`through` 只在孔贯穿整个包围盒时为真。
- `curvedFeatures`：开在曲面或过渡面上、无法按完整圆柱判定的孔（例如环件侧壁的径向孔），给 `axis` / `radius` / `coverage` / `angleDeg`，由模型决定是否标注。
- `detail.edges[i].index` 是 **1-based**，可直接用于 fillet/chamfer 的 `edges`。
- 明细很大时用 `offset`/`limit` 翻页：返回里带 `edgesTotal` / `facesTotal` 与 `nextEdgeOffset` / `nextFaceOffset`，按提示翻即可读全；每条边还带 `mid`（中点），方便和 `edgesNear` 配合。
- 模型读到的是 `output.render` 的文本，不是 JSON。本页返回的每一个面（`F<n>`，供 `freecad_measure` 的 `{"face": n}` 使用，圆柱面带直径与凹/凸）和每一条边（`#<n>`）都会列出，所以默认页设为 50 条；0.4.2 及以前默认返回 200 条却只显示前 24 条边，面编号一个都不显示。
- 多零件文件：只有真正的几何对象（`Part::Feature` 派生、且没有被其他 Part 特征引用）算零件；STEP 装配导入时生成的 `App::Part` 容器和 `App::Origin` 的轴、基准面、原点不再计入（以前会把它们算进去：零件重复、体积变成 -3.6e152、出图 HLR 报错）。嵌套装配的位置只叠加一次父级 Placement。
- 多零件文件会追加一条 `warnings`，提示“尺寸与图纸使用合并后的形状”，渲染文本里列出每个零件的名称、尺寸和体积。

---

## freecad_edit_step

几何级编辑并导出新 STEP。STEP 没有特征历史，所有操作直接作用在 B-Rep 上。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `input` | string | ✅ | 输入文件 |
| `operations` | array | ✅ | 按顺序执行，至少 1 个，见下表 |
| `output` | string | | 输出路径，默认 `<输入名>_edited.step` |
| `overwrite` | boolean | | 允许输出=输入路径，默认 `false` |
| `saveFCStd` | boolean | | 同时保存 `<输出名>.FCStd` |
| `timeoutMs` | integer | | 本次调用超时，默认 300000，最大 1800000 |

### 操作类型

| `type`（别名） | 参数 | 语义 |
|---|---|---|
| `translate` / `move` | `vector:[dx,dy,dz]` 或 `dx/dy/dz` | 平移 |
| `rotate` / `rotation` | `center:[x,y,z]`, `axis:[x,y,z]`, `angle` | 绕任意轴旋转 |
| `scale` | `factor` > 0 | 绕原点等比缩放 |
| `mirror` | `plane:"XY"/"XZ"/"YZ"`（可选 `point`、`normal` 覆盖） | 镜像；`normal` 优先于 `plane` |
| `hole` / `drill` | `center`(入口点), `axis`(切入方向, 默认 `[0,0,-1]`), `diameter`, `depth` 或 `through:true` | 圆柱切除成孔 |
| `primitive` / `boolean` | `shape:"box"/"cylinder"/"sphere"`, `action:"cut"/"fuse"`, 定位尺寸 | 与基础实体做布尔 |
| `fillet` | `radius`, `edges:[1-based...]` | 倒圆角（必须显式给边） |
| `chamfer` | `radius`（别名 `distance`）, `edges:[...]` | 倒角 |

`primitive` 的尺寸参数：

- `box`：`size:[X,Y,Z]` + `position`
- `cylinder`：`radius` + `height` + `position` + `axis`
- `sphere`：`radius` + `position`

### 按位置选边（推荐）

边索引在每次编辑后都会重排（第一个操作砍掉两条边，后面所有编号就都变了），所以倒圆角/倒角除了 `edges`，还可以按位置选：

| 参数 | 说明 |
|---|---|
| `edgeAt` | `[x,y,z]`，选**离该点最近的一条边** |
| `edgesNear` | `[x,y,z]`，选该点附近的**所有**边（默认半径 0.5 mm，可用 `edgesNearRadius` 调整） |

返回的 `operations[i].edges` 会回显实际命中的边（编号、长度、起止点、中点），可以据此确认选对了没有。点不在任何边附近时，错误信息会给出“最近的边 #n，距离 x mm”，据此改点或加大半径。

### 安全与校验

- 每个操作后检查：shape 非空、体积 > 1e-6、`isValid()`；任一失败 → 抛错并**不写输出文件**。
- `fillet/chamfer` 不给 `edges`、给 `[]` 或 `"all"` → 直接报错（避免误操作全部边）。
- 边索引越界时报 `fillet edge index out of range 1..N: ...`。
- 输出路径与输入相同且未传 `overwrite:true` → 拒绝。
- 返回：`{ input, output, operations:[{index,type,volumeBefore,volumeAfter,valid,edges?}], before, after, holes, warnings, fcstd? }`；渲染文本逐步列出每个操作和它实际命中的边。
- 多零件输入：编辑作用在合并后的形状上，导出为**一个**对象，零件名和颜色不保留；`warnings` 会说明这一点。

> 注意：`chamfer` 的 JSON Schema 里描述字段叫 `radius`（`distance` 是别名），模型/用户写 `distance` 也能工作。

---

## freecad_step_to_drawing

HLR 投影 → 第一角法二维加工图。

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `input` | string | — ✅ | 输入 CAD 文件 |
| `outputDir` | string | `<输入目录>/<输入名>_drawing` | 输出目录 |
| `formats` | string[] | `["svg","dxf","pdf","png"]` | 可选子集 |
| `sheet` | `"A4"|"A3"|"A2"|"A1"` | `"A3"` | 图幅（横版） |
| `views` | string[] | `["front","top","right","iso"]` | 可用：`front top right left rear bottom iso` |
| `scale` | number | `0` = 自动 | `0.5` 表示 1:2，`2` 表示 2:1 |
| `hiddenLines` | boolean | `false` | 是否画虚线隐藏线 |
| `dimensions` | boolean | `true` | 是否画总尺寸 |
| `title` | string | `二维加工图` | 标题栏标题 |
| `header` | string | `FreeCAD 二维加工图` | 左上角页眉 |
| `material` | string | `—` | 标题栏材料 |
| `drawingNo` | string | 空 | 图号 |
| `timeoutMs` | integer | `300000` | 本次调用超时，最大 1800000 |

行为细节：

- **A4 是紧凑版式**：固定 1:2，只画 `front`/`top`；若请求里给了 `right/iso` 会被过滤（请求 `front` 会兜底补上）。需要右视图/轴测图请用 A3 及以上。
- 自动比例只取 GB/T 14690 的优先与允许比例：5:1 4:1 2.5:1 2:1 1:1 1:1.5 1:2 1:2.5 1:3 1:4 1:5 1:6 1:10 1:15 1:20 1:25 1:30 1:40 1:50。手工给的 `scale` 原样使用。
- 孔表列为 孔号 / 直径 / 数量 / 轴 / 深度 / X / Y / Z，坐标是模型坐标系下的孔中心；沿孔轴方向的那一列写 “—”（那只是孔深中点）。
- DXF 使用世界坐标 y 向上（页面左下角为原点），与 SVG/PDF/PNG 的版面一致；竖直尺寸数字三种格式都从下往上读。
- 视图标签为“主视图 FRONT / 俯视图 TOP / 右视图 RIGHT / 轴测图 ISO”等。
- 输出文件：`<输入名>_drawing.{svg,dxf,pdf,png}` + `drawing_manifest.json`。
- 返回即 manifest 内容（另加 `manifest` 字段指向清单文件路径）。

> 自动图只标注**总尺寸 + 孔表 + 孔中心线**。凸台直径、台阶高、板厚等定形尺寸不在自动范围，正式生产图需人工补标（见 `06-待办与已知限制.md`）。

---

## freecad_measure

在**不改动文件**的前提下量尺寸：点/面/边之间的距离、两面或两直边夹角、圆柱面或圆边的直径。量出来的数字可以直接写进图纸标注。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `input` | string | ✅ | STEP/STP 绝对路径 |
| `items` | array | ✅ | 测量项列表，见下 |
| `timeoutMs` | integer | | 本次调用超时，默认 300000，最大 1800000 |

每个测量项：

```json
{ "kind": "distance|angle|radius",
  "a": { "point": [x,y,z] } | { "face": 3 } | { "edge": 12 },
  "b": { ... }   // distance/angle 必填
}
```

返回（节选）：

```json
{ "count": 2, "resolved": 2, "units": "mm",
  "measurements": [
    { "index": 1, "kind": "distance", "value": 12.0, "unit": "mm",
      "a": "face", "b": "face", "planeOffset": 12.0,
      "closest": { "a": [...], "b": [...] }, "delta": [0, 0, 12] },
    { "index": 2, "kind": "radius", "value": 25.0, "radius": 12.5, "what": "diameter" }
  ] }
```

- 两个平面互相贴合时 `distance` 会是 0，此时看 **`planeOffset`**（两平面间距），板厚就是这么量的。
- 单个测量项出错**不会**毁掉整批：该项返回 `{"index": n, "error": "..."}`，`resolved` 告诉你有几项成功。
- 直径：`{"face": 圆柱面索引}` 或 `{"edge": 圆边索引}`。
- 夹角：
  - 两条直边**共顶点**时，`value` 是从该顶点出发的两条射线夹角，范围 0–180°（`sharedVertex: true`）；不共点时按两条直线取锐角 0–90°。0.4.2 及以前一律折成 0–90°，135° 会报成 45°。
  - 两个面：`value` 仍是两平面夹角 0–90°（兼容旧行为），另给 `normalAngle`：两条外法线的夹角 0–180°，用它区分 45° 和 135° 的斜面；平行反向的两面为 180°。
  - 点不能参与夹角；面和边不能混用。

## 通用行为

| 项 | 值 |
|---|---|
| 超时 | 默认 300 s，每次调用可用 `timeoutMs` 调到最大 1800 s；`freecad_status` 30 s。工具对 DSH 声明的 `timeoutMs` 是 1830 s 的上限（DSH 的 tool-call-timeout-policy 按它强制超时），实际预算由插件自己的计时器按调用参数执行 |
| 取消 | DSH 的 `exec.signal` 会传到 worker：点停止即结束 `freecadcmd` 子进程，并等它退出后清理临时目录 |
| 进度 | worker 把阶段写进进度文件；返回里的 `timing.elapsedMs` / `timing.phases` 给出耗时与阶段，超时错误会带上最后几个阶段 |
| 并发安全 | 重工具 `false`，否则可能同时启动多个 FreeCAD |
| 卡片类型 | `edit`/`drawing` 声明 `presentCall`（kind: write），便于 UI 显示写操作 |
| 渲染摘要 | 每个工具 `output.render` 返回一段中文摘要文本给模型，不直接展示 JSON |
| 错误文本 | 首行是可读原因（中文/英文混排），后续行可能带 traceback |

## 常见错误字符串与含义

| 错误 | 含义 | 处理 |
|---|---|---|
| `FreeCADCmd not found at ...` | 路径解析失败 | 设 `FREECAD_CMD` 或配置 `freecadCmd` |
| `Plugin worker missing: .../dsh/fc_worker.py` | 安装不完整 | 重装或检查 `dsh/` 目录 |
| `FreeCAD worker timed out after 300s` | 大模型 HLR/布尔超时 | 缩小模型，或在调用里传更大的 `timeoutMs`（最大 1800000） |
| `FreeCAD worker aborted` | 用户在 DSH 里取消了这次调用 | 无需处理；子进程已结束 |
| `Unsupported CAD format '.stl'` | 扩展名不在白名单 | 转成 STEP/IGES/BREP |
| `No solid/surface geometry was imported` | 文件无实体 | 检查文件是否为空/仅装配壳 |
| `fillet requires an explicit list of 1-based edge indices` | 未给边 | 先 `inspect` 取边索引 |
| `Refusing to overwrite the input file` | 输出=输入 | 换输出名或 `overwrite:true` |
| `The edited result is not a valid B-Rep` | 布尔/圆角失败 | 减小半径、换边、分步执行 |
