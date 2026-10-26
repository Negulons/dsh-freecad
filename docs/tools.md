# 工具与参数参考

四个工具由 `index.js` 的 `apply()` 注册。所有长度单位 **mm**，角度单位 **度**。工具名以 `freecad_` 为前缀。

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
| `maxItems` | integer | | 明细条数上限，10–2000，默认 200 |

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
  "warnings": [],
  "detail": { "faces": [...], "facesTruncated": false, "edges": [...], "edgesTruncated": false }
}
```

- `holes` 最多 200 条，按“轴线 Z→Y→X、坐标、直径”排序，编号 `H1..Hn`。
- `detail.edges[i].index` 是 **1-based**，可直接用于 fillet/chamfer 的 `edges`。
- 多对象文件会追加一条 `warnings`，提示“尺寸与图纸使用合并后的形状”。

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

### 安全与校验

- 每个操作后检查：shape 非空、体积 > 1e-6、`isValid()`；任一失败 → 抛错并**不写输出文件**。
- `fillet/chamfer` 不给 `edges`、给 `[]` 或 `"all"` → 直接报错（避免误操作全部边）。
- 边索引越界时报 `fillet edge index out of range 1..N: ...`。
- 输出路径与输入相同且未传 `overwrite:true` → 拒绝。
- 返回：`{ input, output, operations:[{index,type,volumeBefore,volumeAfter,valid}], before, after, holes, fcstd? }`

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

行为细节：

- **A4 是紧凑版式**：固定 1:2，只画 `front`/`top`；若请求里给了 `right/iso` 会被过滤（请求 `front` 会兜底补上）。需要右视图/轴测图请用 A3 及以上。
- 视图标签为“主视图 FRONT / 俯视图 TOP / 右视图 RIGHT / 轴测图 ISO”等。
- 输出文件：`<输入名>_drawing.{svg,dxf,pdf,png}` + `drawing_manifest.json`。
- 返回即 manifest 内容（另加 `manifest` 字段指向清单文件路径）。

> 自动图只标注**总尺寸 + 孔表 + 孔中心线**。凸台直径、台阶高、板厚等定形尺寸不在自动范围，正式生产图需人工补标（见 `06-待办与已知限制.md`）。

---

## 通用行为

| 项 | 值 |
|---|---|
| 超时 | 重工具 300 s；`freecad_status` 30 s |
| 并发安全 | 重工具 `false`，否则可能同时启动多个 FreeCAD |
| 卡片类型 | `edit`/`drawing` 声明 `presentCall`（kind: write），便于 UI 显示写操作 |
| 渲染摘要 | 每个工具 `output.render` 返回一段中文摘要文本给模型，不直接展示 JSON |
| 错误文本 | 首行是可读原因（中文/英文混排），后续行可能带 traceback |

## 常见错误字符串与含义

| 错误 | 含义 | 处理 |
|---|---|---|
| `FreeCADCmd not found at ...` | 路径解析失败 | 设 `FREECAD_CMD` 或配置 `freecadCmd` |
| `Plugin worker missing: .../dsh/fc_worker.py` | 安装不完整 | 重装或检查 `dsh/` 目录 |
| `FreeCAD worker timed out after 300s` | 大模型 HLR/布尔超时 | 缩小模型/提高超时（改 `TIMEOUT_MS`） |
| `Unsupported CAD format '.stl'` | 扩展名不在白名单 | 转成 STEP/IGES/BREP |
| `No solid/surface geometry was imported` | 文件无实体 | 检查文件是否为空/仅装配壳 |
| `fillet requires an explicit list of 1-based edge indices` | 未给边 | 先 `inspect` 取边索引 |
| `Refusing to overwrite the input file` | 输出=输入 | 换输出名或 `overwrite:true` |
| `The edited result is not a valid B-Rep` | 布尔/圆角失败 | 减小半径、换边、分步执行 |
