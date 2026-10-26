# 图纸引擎

代码位置：`dsh/fc_common.py`（投影）、`dsh/fc_render.py`（版面与导出）。渲染由 FreeCAD 自带的 `matplotlib` 完成，不依赖 `reportlab`。

---

## 1. 总流程

```
shape
  └─ project_view(shape, view, hidden)      # 每个视图一次 HLR
        ├─ 用两条单位线标定 TechDraw 局部坐标 → 求逆得到标准朝向
        ├─ TechDraw.projectEx(shape, direction) → 10 组边，只取 0/3/5/8
        ├─ 直线/整圆 → 精确图元；其它曲线 → 离散(≤64 点)折线
        └─ 归一化到视图左下角 (0,0)
  └─ detect_holes(shape)                    # 孔记录（独立于视图）
  └─ build_scene(shape, views, holes, meta, options)
        ├─ 选比例 → 布置视图 → 画轮廓/中心线/总尺寸/孔表/标题栏/技术要求
        └─ 返回 Scene（渲染器无关的场景，单位 mm，页面坐标原点在左上）
  └─ export_scene(scene, base, formats)     # SVG / DXF / PDF / PNG
```

---

## 2. HLR 投影（`fc_common.py`）

### 2.1 视图定义 `VIEW_SPECS`

| 视图 | 观察方向 | 水平轴 h | 竖直轴 v | 标签 |
|---|---|---|---|---|
| front | `(0,-1,0)` | +X | +Z | 主视图 FRONT |
| top | `(0,0,1)` | +X | +Y | 俯视图 TOP |
| right | `(1,0,0)` | +Y | +Z | 右视图 RIGHT |
| left | `(-1,0,0)` | -Y | +Z | 左视图 LEFT |
| rear | `(0,1,0)` | -X | +Z | 后视图 REAR |
| bottom | `(0,0,-1)` | +X | -Y | 仰视图 BOTTOM |
| iso | `(1,-1,1)/√3` | `(1,1,0)/√2` | `(-1,1,2)/√6` | 轴测图 ISO |

第一角法布局（`fc_render.build_scene`）：右视图在主视图**左**边，俯视图在主视图**下**边，轴测图放右边。

### 2.2 坐标标定（不要删）

`TechDraw.projectEx` 返回的 2D 坐标朝向随 FreeCAD 版本和观察方向变化。实现方式：

1. 把 `h`、`v` 单位线各投影一次，得到局部 2D 向量；
2. 组成 2×2 矩阵求逆；
3. 所有投影点乘逆矩阵 → 得到“水平向右、竖直向上”的标准坐标。

> 曾经的问题：不做标定直接取局部坐标，右视图/俯视图会镜像或旋转。

### 2.3 HLR 分组过滤

`projectEx` 返回 10 组（FreeCAD 1.1.3 实测）：`0=V`、`1=V1`、`2=VN`、`3=VO`、`4=VI`、`5=H`、`6=H1`、`7=HN`、`8=HO`、`9=HI`。

- 只取 **0 / 3 / 5 / 8**（真实锐边 + 轮廓线，前四组可见、后四组隐藏）。
- 丢弃 `VN/HN`（平滑/接缝边）：圆柱纵向母线、孔的接缝线不是零件真实棱边，画出来是废线。
- `hidden=true` 才加入 5/8 组，样式为灰色虚线。

### 2.4 精确图元与离散

- `Line` → `{"type":"line"}`；闭合 `Circle` → `{"type":"circle"}`：保持精确，DXF 里就是 LINE/CIRCLE。
- 其它（B 样条、椭圆、非闭合圆弧）→ `discretize` 后重采样到 ≤64 点。
- `deflection = clamp(diag/3000, 0.02, 0.20)`，按模型尺寸自适应。

---

## 3. 孔识别（`detect_holes`）

规则（按顺序）：

1. 只处理 `Cylinder` 面；
2. 半径 > 1e-5；
3. 轴向范围用**边界边离散采样**求得（不用面参数区间，避免被裁剪面坑）；
4. 覆盖率 `face.Area / (2πr·depth) ≥ 0.60`（全圆柱面才可能是孔；半圆柱切口会被排除）；
5. 表面法向必须指向轴线（凹面）。凸圆柱是凸台，不是孔；
6. 同轴、同径、轴向重叠的面片合并（一条孔被拆成多个面时仍算一个孔）；
7. 通孔判定：`shape.isInside(entry - axis*2)` 与 `isInside(exit + axis*2)` 都为 false；
8. 排序（轴向 Z→Y→X、坐标、直径）+ 编号 `H1..Hn`（上限 200）。

返回字段见 `01-架构与数据流.md` 的 hole 结构。

---

## 4. 版面（`fc_render.build_scene`）

### 4.1 页面

| 图幅 | 宽×高 (mm，横版) |
|---|---|
| A4 | 297 × 210 |
| A3 | 420 × 297 |
| A2 | 594 × 420 |
| A1 | 841 × 594 |

- 外框：距页边 10 mm；内框：再内缩 3 mm。
- **所有图形和文字必须在内框以内**（这是硬性要求，见第 6 节）。

### 4.2 比例

`choose_scale()` 从 4:1 … 1:20 的 ISO 常用档位里挑第一个能放下的：

```
avail_w = W - 2*10 - 18
avail_h = (H - 48) - 10 - 22
```

`dims(scale)` 估算 右视图+18+主视图+18+轴测图 的宽，和 主视图+18+俯视图 的高。A4 固定 1:2。

### 4.3 内容

| 元素 | 说明 |
|---|---|
| 视图标签 | 视图下方居中，“主视图 FRONT” |
| 总尺寸 | 每个非轴测视图下方总宽、右侧总高（`dimensions:false` 关闭） |
| 孔中心线 | 按孔的轴向匹配对应视图，画十字中心线（`8,2,1,2` 虚线） |
| 孔标注 | 视右侧按“直径+通/盲”分组，形如 `4×Ø9 THRU`、`1×Ø6 ↧8`（↧ 在 DXF 中写作 `DP`） |
| 孔表 | 右上（A4 在右下角上方），列：孔号/直径/数量/轴/深度/X/Y；只有孔贯穿整个轴向跨度时才写“通”，否则写实际切削深度 |
| 标题栏 | 右下：标题、文件、材料、比例、图号、未注公差、投影法、日期、张数 |
| 技术要求 | 左下三条固定文字（未注公差、锐边倒钝、单位 mm + 第一角投影） |

### 4.4 场景模型 `Scene`

渲染器无关的图元列表，单位 mm，坐标原点在页面左上、y 向下：

```python
scene.line(x1, y1, x2, y2, width=0.25, color="#111111", dash=None, layer="OUTLINE")
scene.polyline(points, width, color, dash, closed, fill, layer)
scene.circle(x, y, r, ...)
scene.text(x, y, text, size=3.5, color, anchor="start|middle|end", rotation=0, bold=False, layer="TEXT")
scene.rect(x, y, w, h, ...)
```

layer：`OUTLINE` / `HIDDEN` / `CENTER` / `DIM` / `TEXT` / `FRAME` / `TITLE`（DXF 按 layer 映射颜色与线型）。

---

## 5. 导出格式

| 格式 | 实现 | 特性 | 限制 |
|---|---|---|---|
| SVG | 手写 XML，`width="420mm" viewBox="0 0 420 297"` | 纯矢量，1 mm = 1 单位，可直接进激光/刻字/Illustrator | 依赖系统字体，不嵌字 |
| DXF | 手写 R12 `AC1009`，`$DWGCODEPAGE=ANSI_936`，GBK 写入 | LINE / CIRCLE / POLYLINE + TEXT，图层与线型齐全 | 中文需目标 CAD 支持 GBK 代码页；`Ø→%%c`，`↧→DP` |
| PDF | matplotlib `PdfPages`，300 dpi 矢量 | 页面尺寸真实（420×297 mm），中文正常 | 中文以 Type3 子集绘制，**不可检索/复制** |
| PNG | matplotlib Agg，默认 180 dpi | 预览/贴图 | 位图 |

多页支持：`render_multipage_pdf(scenes, path)` 把多个 `Scene` 合成一个多页 PDF；`render_multipage_png(scenes, path)` 生成横向排版的预览图。

---

## 6. 版面自检（重要）

用户明确要求过：**交付的图纸内容必须在图框内**。为此有 `tools/layout_check.py`：

```python
from layout_check import check_scene
ok, problems = check_scene(scene, title="page2")
# ok: bool; problems: 每条是一句中文描述（越框/压线/重叠/引线穿字）
```

检查内容：

- 文字是否越出内框 / 压在外框线上；
- 文字之间是否重叠（用 matplotlib `TextPath` 计算真实字宽，与导出结果一致）；
- 表格/详图块之间是否重叠；
- 引线是否穿过无关文字（从 callout 标签引出的引线允许接触它自己的标签，标记 `GATE-EXEMPT`）。

**工作流要求**：生成 → `check_scene` → 全部 OK 才写出图片；未通过不产出文件，并打印问题清单。三视图页（`build_scene`）目前还没有接入这个闸门，只有专门的分页排版脚本用了它（见 `06-待办与已知限制.md`）。

---

## 7. 字体

| 用途 | 字体文件 |
|---|---|
| 粗体 PDF/PNG | `C:\Windows\Fonts\msyhbd.ttc` |
| 常规 PDF/PNG | `C:\Windows\Fonts\msyh.ttc` → `simhei.ttf` → `msyhbd.ttc` |
| SVG | `Microsoft YaHei, SimHei, Arial, sans-serif` |
| DXF | 文字样式引用 `simhei.ttf` |

跨机器交付：目标机需有对应字体；或在 CAD 中把文字转曲后再发 PDF/SVG。

---

## 8. 已知限制

- 自动标注只有总尺寸 + 孔表；定形尺寸（凸台直径、台阶高、板厚、倒角/圆角规格）需要人工补标。
- 不生成剖视图、局部放大、形位公差、表面粗糙度、BOM。
- 非圆孔（异形孔、腰形孔）不会被 `detect_holes` 识别为孔（只认圆柱面），需要在图中人工标注。
- 孔表最多列 10 行（超出部分不显示，但 `holes` 数据完整保存在 manifest）。
- 大装配的 HLR 很慢，可能触发 300 s 超时。
- PDF 文字不可选；需要可检索文字时要另外做（见 `06-待办与已知限制.md`）。
