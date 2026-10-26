# 安装、部署与排错

## 1. 前置条件

| 依赖 | 版本/说明 | 检查方式 |
|---|---|---|
| Windows | 10/11 | — |
| FreeCAD | 1.0 / 1.1，需 `freecadcmd.exe`（**不是** `freecad.exe`） | `"C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" --version` |
| DSH Desktop | 支持 bundle 的版本（`dsh.bundle.patch` 机制） | 能打开 profile 配置 |
| Node.js | ≥ 18（DSH 自带 Node 即可） | `node -v` |
| FreeCAD 自带 Python | 3.11，含 `matplotlib`、`PIL`（FreeCAD 1.x 安装包自带） | 见 `05-开发测试与验收.md` 的自检脚本 |

## 2. 插件在 DSH 里的挂载方式

DSH 插件 = Node 包 + bundle 声明：

`package.json`

```json
{ "name": "dsh-freecad", "version": "0.1.0", "type": "module",
  "exports": { ".": "./index.js" },
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } } }
```

`cordis.patch.yml`（包内）

```yaml
- insert:
    - id: freecad
      name: 'dsh-freecad'
```

profile 侧需要三件事（缺一不可）：

1. `plugins/dsh-freecad/` —— 插件文件实体；
2. profile `package.json`：
   - `dependencies["dsh-freecad"] = "file:./plugins/dsh-freecad"`
   - `dsh.profile.bundles` 数组包含 `"dsh-freecad"`
3. profile `cordis.patch.yml` 末尾的 `insert` 条目（同上）；
4. 在 profile 目录执行一次 `pnpm install`，生成 `node_modules/dsh-freecad`。

> **最容易踩的坑**：只把目录复制进 `node_modules/dsh-freecad` 而不写依赖清单。DSH 启动时会整理依赖，把“不在依赖树里”的包移走（会出现在 `node_modules/.ignored/` 下），表现为“重启后插件消失”。必须走 `file:` 依赖 + pnpm install。

## 3. 一键安装脚本

```powershell
cd <插件源码目录>
node scripts\install.mjs

# 或指定其它 profile
$env:DSH_PROFILE = "C:\Users\you\.dsh\profiles\other"
node scripts\install.mjs
```

脚本 `scripts/install.mjs` 的顺序与副作用：

| 步骤 | 动作 | 失败表现 |
|---|---|---|
| 1 | 复制 `index.js package.json cordis.patch.yml README.md LICENSE dsh examples` 到 `<profile>/plugins/dsh-freecad`（跳过 `__pycache__`/`.pyc`） | 退出码 1，提示缺 `index.js` 或 `dsh/fc_worker.py` |
| 2 | 写 profile `package.json` 的 `file:` 依赖与 `dsh.profile.bundles`；改动前备份 `<file>.bak-<时间戳>` | profile 无 `package.json` 时直接报错 |
| 3 | 若 profile `cordis.patch.yml` 尚无 `dsh-freecad` 条目则追加（先备份） | 找不到 patch 文件时报错 |
| 4 | 找 DSH 自带 pnpm（`~/.dsh/dsh-runtimes/*/dependencies/pnpm/bin/pnpm.cjs`），在 profile 内执行 `pnpm install --config.confirmModulesPurge=false` | 找不到 pnpm 时只警告，需手动 `pnpm install` |
| 5 | 校验 `node_modules/dsh-freecad` 存在 | `pnpm install completed but ... missing` |

可用环境变量：

- `DSH_PROFILE`：profile 根目录，默认 `~/.dsh/profiles/desktop`
- `DSH_PNPM`：pnpm 入口 cjs 路径（自定运行时用）
- `FREECAD_CMD`：FreeCADCmd 路径（插件运行时读取，不是安装脚本用）

安装完成后**必须重启 DSH Desktop**，新进程才会加载 bundle。重启后调用 `freecad_status` 验证。

## 4. 手动安装

1. 复制插件文件到 `<profile>/plugins/dsh-freecad/`（`index.js`、`package.json`、`cordis.patch.yml`、`dsh/`、`examples/`、`README.md`、`LICENSE`）。
2. profile `package.json`：
   ```json
   { "dependencies": { "dsh-freecad": "file:./plugins/dsh-freecad" },
     "dsh": { "profile": { "bundles": ["...", "dsh-freecad"] } } }
   ```
3. profile `cordis.patch.yml` 追加：
   ```yaml
   - insert:
       - id: freecad
         name: 'dsh-freecad'
   ```
4. `<profile>` 下执行 `pnpm install`。
5. 重启 DSH。

## 5. 配置 FreeCADCmd 路径

优先级：`config.freecadCmd`（profile patch 条目） > `FREECAD_CMD` 环境变量 > 内置候选：
`C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe`、`...\FreeCAD 1.0\...`、`...\FreeCAD\...`

```yaml
- insert:
    - id: freecad
      name: 'dsh-freecad'
      config:
        freecadCmd: 'D:\Apps\FreeCAD 1.1\bin\freecadcmd.exe'
```

> 不要重复插入同一个 `id`；要改配置就改已有条目加 `config`。

## 6. 升级 / 卸载

**升级**：覆盖源码目录后重新执行 `node scripts\install.mjs`，再重启 DSH。
脚本是幂等的（重复执行不会重复添加依赖/条目），并会先清空安装目录再复制，避免残留旧文件。

**卸载**：

1. 删除 `<profile>/plugins/dsh-freecad`；
2. 从 profile `package.json` 移除 `dependencies["dsh-freecad"]` 与 `bundles` 中的 `"dsh-freecad"`；
3. 从 profile `cordis.patch.yml` 移除对应 `insert` 条目；
4. profile 内 `pnpm install`（清掉符号链接）；
5. 重启 DSH。

## 7. 故障排查表

| 现象 | 原因 | 处理 |
|---|---|---|
| DSH 中看不到 `freecad_*` 工具 | 未重启 / bundle 未挂载 / patch 条目缺失 | 检查 profile `package.json` 与 `cordis.patch.yml`；重启 DSH |
| 重启后插件消失，出现 `node_modules/.ignored/dsh-freecad` | 只复制目录没写依赖，启动时被 pnpm 清理 | 重新 `node scripts\install.mjs`（写入 `file:` 依赖并 install） |
| `FreeCADCmd not found` | 路径不对/未安装 | `freecad_status` 看实际解析路径；设 `FREECAD_CMD` |
| `FreeCAD worker timed out` | 模型过大/HLR 过慢 | 先小模型；必要时调大 `TIMEOUT_MS`（`index.js`） |
| worker 立即失败，stderr 有 Python traceback | 代码/FreeCAD 版本不匹配 | 看 result.json 的 `traceback`；对照 FreeCAD 版本 |
| 中文变成方块/问号 | 缺字体 | 确认 `C:\Windows\Fonts\msyh.ttc`、`simhei.ttf`；PDF 用 matplotlib 时必须有其中一种 |
| 工具调用被 DSH 拒绝，提示非法 JSON 数值 | 结果里出现 `-0.0`/`NaN` | 不应再出现；若复现，检查 `_json_safe()` 是否被绕过 |
| 安装脚本报 `profile package.json not found` | `DSH_PROFILE` 指错目录 | 指向真实的 profile 根目录 |
| 安装脚本 pnpm 退出非 0 | 运行时缺 pnpm 或依赖冲突 | 手动在 profile 执行 `pnpm install`，看完整报错 |

## 8. 部署核对清单（每次发布前）

- [ ] `node index.js --self-test` 输出 4 个工具
- [ ] 目标机器 `freecad_status` 返回版本号
- [ ] 安装后源码目录与 `plugins/dsh-freecad` 的 `index.js`、`dsh/*.py` SHA256 一致（可选脚本见 `05-开发测试与验收.md`）
- [ ] 安装目录内无 `__pycache__`、`.pyc`
- [ ] 重启 DSH 后工具可用
- [ ] 用 `examples/demo_bracket.step` 跑一遍 inspect → edit → drawing


---

## 分发包安装说明

本包是可安装的 DSH 插件包：解压后得到 `dsh-freecad/` 目录，装进任一 DSH 实例即可使用。

- 包名/版本：`dsh-freecad 0.1.0`
- 适用：Windows 10/11、DSH Desktop、FreeCAD 1.0/1.1（需 `freecadcmd.exe`）
- License：MIT

---

## 1. 前置条件

| 依赖 | 说明 |
|---|---|
| FreeCAD | 必须带 `freecadcmd.exe`，例如 `C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe` |
| DSH Desktop | 支持 bundle 的版本 |
| Node.js | ≥ 18（用 DSH 自带的也可） |

先确认 FreeCADCmd 能跑：

```powershell
& "C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe" --version
```

## 2. 安装（推荐：自动脚本）

```powershell
# 1) 解压到任意目录，例如 D:\tools\dsh-freecad
# 2) 进入解压出的 dsh-freecad 目录
cd D:\tools\dsh-freecad

# 3) 安装到默认 profile（%USERPROFILE%\.dsh\profiles\desktop）
node scripts\install.mjs

# 或安装到指定 profile
$env:DSH_PROFILE = "C:\Users\you\.dsh\profiles\another"
node scripts\install.mjs
```

脚本会：

1. 把插件复制到 `<profile>\plugins\dsh-freecad`；
2. 在 `<profile>\package.json` 写入依赖 `"dsh-freecad": "file:./plugins/dsh-freecad"`，并加入 `dsh.profile.bundles`；
3. 在 `<profile>\cordis.patch.yml` 追加挂载条目（文件不存在时会新建）；
4. 用 DSH 自带 pnpm 执行 `pnpm install`，生成 `node_modules\dsh-freecad`；
5. 修改前把原文件备份为 `<文件名>.bak-<时间戳>`。

**装完必须重启 DSH Desktop。**

> 全新实例的 profile 里可能还没有 `package.json`。这种 profile 需要先在 DSH 里创建一次（或从其它 profile 复制一份），脚本才能写入依赖。

## 3. 安装（手动）

把解压出的 `dsh-freecad` 整个目录复制到 `<profile>\plugins\dsh-freecad`，然后：

**a. 改 `<profile>\package.json`**

```json
{
  "dependencies": { "dsh-freecad": "file:./plugins/dsh-freecad" },
  "dsh": { "profile": { "bundles": ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-web-app", "dsh-freecad"] } }
}
```

**b. 在 `<profile>\cordis.patch.yml` 末尾追加**（没有该文件就新建）

```yaml
- insert:
    - id: freecad
      name: 'dsh-freecad'
```

**c. 在 profile 目录执行**

```powershell
pnpm install
```

**d. 重启 DSH Desktop。**

## 4. 指定 FreeCADCmd 路径

最省事的办法是在 DSH 里打开 **设置 → FreeCAD**，把 `freecadcmd.exe` 的完整路径填进去并保存（同一栏里还有两个下载入口：官方 GitHub Releases 和清华 TUNA 镜像）。该项写入插件配置的 `freecadPath`，保存后下一次工具调用即生效，无需重启。

解析优先级从高到低：

1. 设置 → FreeCAD 里填的路径（`freecadPath`）；
2. profile `cordis.patch.yml` 里 `freecad` 条目的 `config.freecadCmd`；
3. 环境变量 `FREECAD_CMD`；
4. 常见安装位置自动探测，最后查 PATH。

也可以直接编辑条目（编辑已有条目的 config，不要重复插入同一个 `id`）：

```yaml
- insert:
    - id: freecad
      name: 'dsh-freecad'
      config:
        freecadCmd: 'D:\Apps\FreeCAD 1.1\bin\freecadcmd.exe'
```

## 5. 验证安装

重启后：

1. 在对话里说“检查 FreeCAD 状态”，或直接调用 `freecad_status`，应返回版本号；
2. 用包内样例验证全链路：

```text
读取 <包目录>\examples\demo_bracket.step，列出尺寸和所有孔。
把它导出成 A3 二维加工图。
```

预期：尺寸 100 × 60 × 37 mm、5 个孔（4×Ø9 + 1×Ø25），并生成 SVG/DXF/PDF/PNG 四种图纸加 `drawing_manifest.json`。

## 6. 升级

用新包覆盖原目录后重新执行 `node scripts\install.mjs`，再重启 DSH。脚本是幂等的：会先清空安装目录再复制，不会重复添加依赖或挂载条目。

## 7. 卸载

1. 删除 `<profile>\plugins\dsh-freecad`；
2. 从 `<profile>\package.json` 删掉 `dsh-freecad` 的依赖项与 bundles 条目；
3. 从 `<profile>\cordis.patch.yml` 删掉对应 `insert` 条目；
4. 在 profile 目录执行 `pnpm install`；
5. 重启 DSH。

## 8. 排错

| 现象 | 处理 |
|---|---|
| 重启后工具列表里没有 `freecad_*` | 检查 profile 的 `bundles` 与 `cordis.patch.yml` 是否都包含 dsh-freecad，然后重启 |
| 重启后插件消失，出现 `node_modules\.ignored\dsh-freecad` | 只复制了目录没有写依赖，DSH 启动时清理掉了。重新执行 `install.mjs`，不要手动往 `node_modules` 里拷贝 |
| `FreeCADCmd not found` | 调 `freecad_status` 看解析到的路径，再设 `FREECAD_CMD` 或配置 `freecadCmd` |
| 图纸中文变方框 | 目标机缺少 `msyh.ttc` / `simhei.ttf`，补字体或改用 PNG/SVG |
| `install.mjs` 报 `profile package.json not found` | `DSH_PROFILE` 指向的目录不对，或该 profile 还没初始化 |
| 大模型出图超时 | 单次调用上限 5 分钟，先缩小模型或用简化实体验证 |

## 9. 包内容

```text
dsh-freecad/
  index.js              DSH 工具层（4 个工具）
  package.json          包元数据与 bundle 声明
  cordis.patch.yml      DSH bundle 挂载定义
  dsh/
    fc_worker.py        FreeCADCmd 入口与业务分派
    fc_common.py        导入、统计、孔识别、HLR 投影
    fc_render.py        图纸场景与 SVG/DXF/PDF/PNG 渲染
  examples/
    demo_bracket.step   示例模型（100×60×37，5 孔）
    demo_bracket.FCStd
  scripts/
    install.mjs         安装到 DSH profile
    package.mjs         重新打这个包
  docs/                 架构、工具参考、部署、图纸引擎、开发测试、待办
  README.md             功能与用法
  LICENSE               MIT
```

## 10. 完整性校验

包内附 `SHA256SUMS.txt`（每个文件的 SHA-256）与 `dsh-freecad-0.1.0.manifest.json`（文件清单与 zip 自身的哈希）。校验方法：

```powershell
Get-FileHash .\dsh-freecad-0.1.0.zip -Algorithm SHA256
```

与 `manifest.json` 中 `zip.sha256` 对比即可。
