# 给 AI 的安装指令（dsh-freecad）

你正在读一份**可安装的 DSH 插件包**。请按本文档一步步执行，把插件装进**你当前运行的 DSH 实例**，然后用包内自带的 STEP 示例验证它能出图。

- 包名：`dsh-freecad` 版本 `0.2.0`
- 运行时：Windows 10/11 + DSH Desktop + FreeCAD 1.0/1.1（需要 `freecadcmd.exe`）
- 不需要联网、不需要 npm 安装、不需要编译

---

## 0. 先确认三件事（不要跳过）

```powershell
# 1) 我在哪个 profile？
echo $env:USERPROFILE
# 2) FreeCADCmd 存在吗？（路径可能是 1.0 或 1.1 或自定义）
Get-ChildItem 'C:\Program Files\FreeCAD*\bin\freecadcmd.exe' -ErrorAction SilentlyContinue | Select-Object FullName
# 3) 包解压到哪了？
#    假设解压目录为 <PACKAGE>，例如 D:\tools\dsh-freecad
```

如果第 2 步什么都没输出，说明本机没装 FreeCAD 或不在默认位置：**先告诉用户需要安装 FreeCAD，或提供 `freecadcmd.exe` 的完整路径**，再继续。

---

## 1. 安装（一条命令）

```powershell
cd <PACKAGE>
node scripts\install.mjs
```

它能自己判断 profile：默认用 `%USERPROFILE%\.dsh\profiles\desktop`；如果目标实例用的是别的 profile，加参数：

```powershell
node scripts\install.mjs --profile "C:\Users\<user>\.dsh\profiles\<name>"
```

脚本做的事（每步都会打印 `[install] ...`）：

1. 复制插件到 `<profile>\plugins\dsh-freecad`；
2. 在 `<profile>\package.json` 写入依赖 `"dsh-freecad": "file:./plugins/dsh-freecad"` 并加入 `dsh.profile.bundles`（缺 bundles 时自动补 `@deepseek-ai/dsh-base`、`@deepseek-ai/dsh-web-app`）；
3. 在 `<profile>\cordis.patch.yml` 追加挂载条目（文件不存在会新建）；
4. 有 pnpm 就走 `pnpm install`；**没有 pnpm 就直接复制到 `<profile>\node_modules\dsh-freecad`**；
5. 运行 `node index.js --self-test` 自检并打印 4 个工具名。

被修改的文件都会先备份成 `*.bak-<时间戳>`。重复执行是安全的。

**如果脚本报 `profile has no package.json`**：这个 profile 还没被 DSH 初始化过。请让用户先用该 profile 启动一次 DSH（生成 `package.json`），再重跑脚本；不要自己凭空造一个 `package.json`。

---

## 2. 重启 DSH

插件是 bundle，**必须重启 DSH Desktop** 才会加载。重启后本会话的工具列表里应出现：

- `freecad_status`
- `freecad_inspect_step`
- `freecad_edit_step`
- `freecad_step_to_drawing`

如果重启后仍看不到工具，按 `docs\03-安装部署与排错.md` 的排错表检查 `bundles` 与 `cordis.patch.yml`。

---

## 3. 配置 FreeCAD 路径（仅在自检显示找不到时）

`install.mjs` 最后会打印 `self-test: freecadCmd exists = true/false`。

- `true` → 跳过本节。
- `false` → 用下面任一方式指定（优先级从高到低）：
  1. 环境变量 `FREECAD_CMD` 指向 `freecadcmd.exe`；
  2. `<profile>\cordis.patch.yml` 里给已有条目加 config（**不要**重复插入同一个 id）：
     ```yaml
     - insert:
         - id: freecad
           name: 'dsh-freecad'
           config:
             freecadCmd: 'D:\Apps\FreeCAD 1.1\bin\freecadcmd.exe'
     ```
改完再重启一次 DSH。

---

## 4. 用包里自带的 STEP 验证可用性

包内有一个**固定的示例模型**：`<PACKAGE>\examples\demo_bracket.step`（100 × 60 × 37 mm，4×Ø9 通孔 + 1×Ø25 通孔）。

按下面顺序验证，**每一步都要看返回值**：

### 4.1 环境

```text
调用 freecad_status
```
通过标准：返回里 `exists: true`、`workerExists: true`、`version` 是一个形如 `1.1.3` 的版本号。

### 4.2 读取

```text
调用 freecad_inspect_step，参数：
{ "input": "<PACKAGE>\\examples\\demo_bracket.step" }
```
通过标准（必须全部吻合）：

| 项 | 期望值 |
|---|---|
| `shape.bbox.size` | `[100, 60, 37]` |
| `shape.volume` | `99871.424624`（±0.01） |
| `shape.valid` | `true` |
| `objectCount` | `1` |
| `holes` 数量 | `5` |
| 孔径分布 | `4 × Ø9`、`1 × Ø25` |

### 4.3 编辑

```text
调用 freecad_edit_step，参数：
{
  "input": "<PACKAGE>\\examples\\demo_bracket.step",
  "output": "<PACKAGE>\\examples\\demo_bracket_moved.step",
  "operations": [ { "type": "translate", "vector": [10, 0, 0] } ]
}
```
通过标准：返回 `ok`，孔中心 X 从 `-38/38` 变成 `-28/48`，Ø25 孔中心变为 `[10, 0, 18.5]`。

### 4.4 出图

```text
调用 freecad_step_to_drawing，参数：
{
  "input": "<PACKAGE>\\examples\\demo_bracket_moved.step",
  "outputDir": "<PACKAGE>\\examples\\drawing",
  "sheet": "A3",
  "views": ["front", "top", "right", "iso"]
}
```
通过标准：`files` 里有 `svg`、`dxf`、`pdf`、`png` 四个文件，目录下还有 `drawing_manifest.json`；`scaleLabel` 为 `1:1`；`holes` 为 5 个。

再目视检查 `drawing\demo_bracket_moved_drawing.png`：应有右视图/主视图/俯视图/轴测图四个视图、总尺寸 100/60/37、孔表 5 行、标题栏和页眉都在图框内。

### 4.5 清理

验证完成后删除临时文件（保留原始 `demo_bracket.step`）：

```powershell
Remove-Item '<PACKAGE>\examples\demo_bracket_moved.step' -ErrorAction SilentlyContinue
Remove-Item '<PACKAGE>\examples\drawing' -Recurse -Force -ErrorAction SilentlyContinue
```

---

## 5. 完成后向用户报告什么

请把下面这份结果按实际值填好发回给用户：

```
dsh-freecad 0.1.0 安装结果
- profile:            <实际的 profile 路径>
- 安装方式:            pnpm / 直接复制
- FreeCADCmd:          <路径> (版本 <x.y.z>)
- 4 个工具是否注册:    是/否
- 示例 STEP 读取:      尺寸 ? × ? × ?，孔 ? 个，体积 ?
- 编辑+出图:           ? 个文件（svg/dxf/pdf/png）
- 目视图纸检查:        通过/问题描述
- 需要重启:            是（已完成重启）
```

---

## 6. 失败时怎么办

| 现象 | 处理 |
|---|---|
| `install.mjs` 报 path 相关错误 | 确认 `<PACKAGE>` 路径不含无法访问的字符，且当前用户对 profile 目录有写权限 |
| self-test 显示 `exists = false` | 走第 3 节配置 FreeCAD 路径 |
| 工具调用报 `spawn EPERM` | 运行 DSH 的进程不允许创建子进程（多见于沙箱/受控环境）。请换到正常桌面 DSH 会话重试，不要把这种情况当成插件缺陷 |
| worker 超时（300s） | 示例模型很小，正常 10 秒内完成；超时说明 FreeCAD 卡住，查 `freecad_status` 与 FreeCAD 安装完整性 |
| 图纸中文变方框 | 目标机缺 `msyh.ttc`/`simhei.ttf` 字体；补字体或改用 SVG/PNG 检查 |
| 一定要卸载 | 删 `<profile>\plugins\dsh-freecad`；从 profile `package.json` 移除依赖与 bundles 条目；删除 `cordis.patch.yml` 里的 freecad `insert` 条目；在 profile 内跑一次 `pnpm install`；重启 DSH |

更完整的排错与架构说明见包内 `docs\` 目录，安装参数细节见 `docs\07-安装说明（分发包）.md`。
