# 待办与已知限制

按优先级排列。接手人可据此排期；每条都标了影响面和实现提示。

---

## A. 功能缺口（用户能感知）

### A1. 自动图纸只标总尺寸 + 孔表（高）
现状：`build_scene` 每个视图只画总宽/总高，孔靠孔表与分组标注。
影响：凸台直径、台阶高度、板厚、定位尺寸要人工补，正式生产图不能直接用。
提示：可以从 `detect_holes` 之外再增一类特征识别（轴向圆柱面=凸台，平面台阶=厚度变化），或提供“从选中边/面提取尺寸”的显式工具。

### A2. 非圆孔/异形孔不识别（中）
现状：`detect_holes` 只认圆柱面（凹、覆盖率 ≥0.6）。
影响：腰形孔、D 形孔、切槽不会出现在孔表。
提示：按“平面内环”识别更通用：取视图内闭周围环（外环包含、内环不包含于实体面），按周环形状分类。

### A3. 孔表固定 10 行（中）
`_hole_table` 里 `rows = holes[:10]`。manifest 里有全部孔，但图上只列 10 个。
提示：改成按可用高度分栏，或超限时输出续表。

### A4. PDF 文字不可检索（中）
matplotlib 的 Type3 子集绘制，视觉正确但不能搜索/复制。
提示：换 cairo/pdfkit 或改为嵌入 TrueType 子集；也可在 SVG→PDF 路径上用图形库重排。

### A5. 剖视图 / 局部放大 / 形位公差 / 粗糙度 / BOM 缺失（中）
目前只有正交视图和轴测图。
提示：FreeCAD 1.x 有 `TechDraw` 的 SectionView 能力，但 headless 可用性需先验证；局部放大可以基于已投影的精确图元做窗口裁剪 + 比例变换。

### A6. 三视图页未接入版面闸门（中）
`tools/layout_check.py` 目前用于专门的分页排版；`fc_render.build_scene` 的三视图输出还没有调用它。
影响：三视图可能出现文字压框/越框（这正是用户反馈过的问题类型）。
提示：在 `build_scene` 末尾调用 `check_scene`，失败时抛错（或在 manifest 里带 `layoutOK:false` 并提示）。

### A7. 大装配性能（中）
单次调用 5 分钟上限；大模型 HLR 很慢。
提示：先做 LOD（用简化 shape 做视图）、缓存 `project_view` 结果、按视图并行子进程。

### A8. 剖切与多实体分色（低）
多实体（多体 STEP）目前合并为一个 compound 出图，无法区分不同零件的线型。

---

## B. 工程与质量

### B1. 无自动化单测（高）
现状：只有 `node index.js --self-test` 与人工冒烟；独立 58 用例来自外部 QA 的手工 harness，没有进入仓库。
提示：把 QA 用例固化为 `test/` 下的脚本（可复用 `call_tool.mjs`），CI 用 `examples/` 的样例跑金标对比。

### B2. FreeCAD 1.0 未实测（中）
代码保留了 1.0 路径，但只在 1.1.3 上验证过。
提示：在 1.0 上跑一遍 `projectEx` 分组与 `optimalBoundingBox`，必要时做版本分支。

### B3. 平台仅 Windows（中）
默认路径、GBK DXF、字体均是 Windows 假设。
提示：Linux/macOS 需要：可执行文件探测（`which freecadcmd`）、字体回退（Noto Sans CJK）、DXF 可选 UTF-8 或 GBK 配置项。

### B4. 超时不可配置（低）
`TIMEOUT_MS` 写死 300 s。
提示：提到 `config.timeoutMs`。

### B5. 版本号手工维护（低）
`package.json` 与 `drawing_manifest.json` 的 `generatedBy` 都是手写 `0.1.0`。
提示：worker 从 `package.json` 读取版本。

---

## C. 文档与开源整理（交接人决定）

- README 目前是中文、面向使用者的说明，对外开源前要确认目标读者（是否补英文版）。
- `notes/` 下的验收/审查报告包含内部环境路径与本机信息，公开前需要脱敏或移出仓库。
- `tools/` 下为某次具体出图任务编写的一次性脚本（特定的分页排版、轮廓分析、版面闸门），**与插件运行时无关**；公开前要评估：保留作示例 / 移入 `examples/` / 不进仓库。
- `test/` 目录里混有大量临时参数文件与产物，公开前应清理。

---

## D. 已解决的问题（留作知识，不要重复踩）

| 问题 | 解决方式 |
|---|---|
| 重启后插件被 pnpm 清理掉 | 用 `file:` 依赖 + `pnpm install`，不直接复制到 `node_modules` |
| 圆柱接缝线出现在视图里 | HLR 只取 `projectEx` 的 0/3/5/8 组 |
| 标题栏/孔表压内框 | 标题栏与表格统一从内框（距边 13 mm）内缩排布 |
| `-0.0` 导致 DSH 拒绝结果 | 结果写出前 `_json_safe()` 规范化 |
| 包围盒被样条撑大 | `optimalBoundingBox()` |
| `mirror` 用不存在的 `shape.mirrored` | 用 `shape.mirror(point, normal)` |
| A4 放不下右视图/轴测图 | A4 降级为 front/top 固定 1:2 |
