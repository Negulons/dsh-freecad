# 开发、测试与验收

## 1. 环境自检

FreeCADCmd 里的 Python 必须能导入这些模块：

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" -c "import FreeCAD, Part, TechDraw, Import, matplotlib, PIL; print(FreeCAD.Version()[0:3])"
```

没有 `-c` 也可写临时脚本，注意 FreeCADCmd 不接受额外参数（会把参数当 CAD 文件）。

## 2. 开发时直接验证工具（不经过模型）

`test/call_tool.mjs` 直接加载 `index.js`、注册工具、执行一个工具、打印 JSON：

```powershell
node index.js --self-test                                  # 只列工具名与必填参数
node test\call_tool.mjs freecad_status
node test\call_tool.mjs freecad_inspect_step "{\"input\":\"<STEP 绝对路径>\"}"
node test\call_tool.mjs freecad_inspect_step args.json    # 参数文件（UTF-8）
node test\call_tool.mjs freecad_step_to_drawing args.json
```

`args.json` 形如：

```json
{ "input": "C:\\work\\demo_bracket.step",
  "outputDir": "C:\\work\\out",
  "sheet": "A3",
  "views": ["front","top","right","iso"] }
```

> PowerShell 内联 JSON 的转义很痛苦，**优先用参数文件**。

## 3. 样例模型

`examples/demo_bracket.step`（100 × 60 × 37 mm，含 Ø25 通孔、4×Ø9 盲孔）与 `examples/demo_bracket.FCStd` 仅用于冒烟验证，与任何真实项目无关。

期望的 inspect 结果：1 solid、尺寸 100 × 60 × 37、5 个孔。

## 4. 独立验收结论（历史记录）

`notes/qa-acceptance.md`：58 个用例全部通过，覆盖

- 四个工具正常路径（Inspect 尺寸/体积/孔数核对、edit 各操作、输出 STEP 回读、FCStd 生成、drawing 四格式与 manifest、A4 紧凑版式）
- 错误路径（文件不存在、边索引 0/越界、非法操作、空 operations、同路径覆盖、负缩放、零直径、缺深度、非法格式/视图）
- 安装脚本幂等与失败路径
- 源码未在测试期间变化

已知验收限制（报告原文要点）：验收是在“源码 + 真实 FreeCADCmd worker”的 harness 上执行的，不等同于 DSH 进程内加载后的行为；DSH 内加载需重启后单独验证。

`notes/drawing-and-packaging-review.md`：图纸与交付包审查报告。报告中的 3 个 P1（关键定形尺寸缺失、圆柱接缝线混入可见轮廓、标题栏/孔表压内框）已在后续版本修复；实现方式见 `04-图纸引擎.md`（HLR 只取 0/3/5/8 组、标题栏内缩 3 mm），自动标注范围的现状见 `06-待办与已知限制.md`。

## 5. 代码修改注意事项（踩过的坑）

| 坑 | 现象 | 正确做法 |
|---|---|---|
| FreeCADCmd 下 `__name__` 不是 `__main__` | 守卫不执行，脚本什么都不做 | 入口脚本无条件调用 `main()` |
| 命令行传参 | `no supported file format` | 用环境变量或文件传参 |
| 结果里有 `-0.0` / `NaN` | DSH 拒绝整次工具结果 | 结果写出前过 `_json_safe()` |
| `Part.Shape.BoundBox` 被样条控制点撑大 | 包围盒离谱、比例错 | 用 `optimalBoundingBox()` |
| `TechDraw.projectEx` 局部朝向不稳定 | 视图镜像/旋转 | 单位线标定后求逆 |
| `projectEx` 的第 1/2/6/7 组 | 圆柱母线、接缝线混进轮廓 | 只取 0/3/5/8 组 |
| `shape.mirrored` 不存在 | mirror 操作抛 AttributeError | FreeCAD 1.x 用 `shape.mirror(point, normal)` |
| `fillet`/`chamfer` 不给边 | 静默作用到不该动的边 | 强制显式 1-based 边索引 |
| Page 对象的 `exportSvg/exportPDF/exportDXF` | headless 下不存在 | 自绘 Scene + 自写导出 |
| 分页排版里 `scene.items` 被归并 | 图框重复、标题栏压框 | 分页各自独立 Scene，最后一页才放详情 |

## 6. 回归测试建议

1. **金标对照**：对 `examples/demo_bracket.step` 固定参数出一套图，人工核对尺寸、视图关系、孔表数值与位置。
2. **数值回归**：inspect 的 `shape.volume`、`holes` 列表与已知值比较（样例：体积 99871.424624 mm³，5 孔）。
3. **格式回归**：DXF 能被 FreeCAD `importDXF.insert` 重新导入，对象数量在合理范围（样例 1.5k 量级，不是 1.6 万）。
4. **版面闸门**：凡是走 Scene 的排版，出图前必须 `layout_check.check_scene()` 全绿。
5. **安装回归**：在临时 profile 上跑 `install.mjs` 两次，确认幂等、备份文件生成、依赖正确。
6. **纯排版单元测试**：`python tests/test_renderer.py`（无 FreeCAD、无 matplotlib 也能跑，CI 里就是这么做的）。
   覆盖孔表分块（>10 孔不再截断）与隐藏线去重（对称件吐回的"影子"隐藏线必须丢掉），
   这两类 bug 靠肉眼很难发现，只能靠断言。

## 7. 发布到 npm（实操记录，2026-10）

账号 `negulons` 开了 2FA，所以**普通登录态发不出去**：`PUT /dsh-freecad` 会回
`403 Two-factor authentication or granular access token with bypass 2fa enabled is required`。
`--otp=`、`NPM_CONFIG_OTP` 这两条在 pnpm 下都不生效，别浪费时间。

正确做法：

1. 在 <https://www.npmjs.com/settings/~/tokens> 建 **Granular Access Token**：
   `Packages and scopes = Read and write`、勾 **Bypass 2FA**、有效期 7 天。
   （npm 已公告 2027-01 取消 bypass-2FA 直发，长期应改用 CI + trusted publishing。）
2. **token 要写进 pnpm 自己的凭据文件**，写 `~/.npmrc` 会被忽略：

   ```
   C:\Users\<user>\AppData\Local\pnpm\config\auth.ini
   //registry.npmjs.org/:_authToken=npm_xxx
   ```

   这是本次踩的最大坑：`pnpm whoami` 一直是 `negulons`（读的是旧网页登录 token），
   而真正的发布请求带着旧 token，于是一直 403。
3. `pnpm publish --access public --no-git-checks`。
4. **别凭 CLI 输出下结论。** registry 的 packument 有几分钟 CDN 缓存，刚发完
   `GET /<pkg>/<version>` 可能还是 404、`dist-tags.latest` 还是旧值。用轮询确认：

   ```bash
   curl -s https://registry.npmjs.org/-/package/dsh-freecad/dist-tags
   curl -s -o /dev/null -w '%{http_code}\n' https://registry.npmjs.org/dsh-freecad/0.2.1
   ```

   本次 0.2.1 从 publish 到 `latest` 生效约 **5 分钟**。在这之前重发会得到
   `403 You cannot publish over the previously published versions`——那句 403 其实说明
   **已经发上去了**。
5. 首次发布会自动生成一个 `0.0.0-stage` 占位版本（"Temporary package placeholder for
   staged publishing"），所以 npm 页面会显示「N Versions」，属正常现象。
6. README 里的图片必须用**绝对 URL**（`raw.githubusercontent.com`）。用相对路径时 npm
   会解析成 `https://www.npmjs.com/package/docs/images/...`，全部裂图。

## 8. 验收环境记录（历史）

| 项 | 值 |
|---|---|
| OS | Windows 10/11 |
| Node | v24.19.0 |
| FreeCAD | 1.1.3（Git shallow），Python 3.11.14，matplotlib 3.10.8，PIL 12.0.0 |
| DSH | 桌面版（bundle 机制） |
| profile | `%USERPROFILE%\.dsh\profiles\desktop` |

FreeCAD 1.0 未实测；代码里保留了 1.0 候选路径，如果 1.0 的 `TechDraw.projectEx` 分组或 `optimalBoundingBox` 行为不同，需要回归后再声明支持。
