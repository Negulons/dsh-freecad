# dsh-freecad

[![CI](https://github.com/Negulons/dsh-freecad/actions/workflows/ci.yml/badge.svg)](https://github.com/Negulons/dsh-freecad/actions/workflows/ci.yml)
[![npm](https://img.shields.io/npm/v/dsh-freecad.svg)](https://www.npmjs.com/package/dsh-freecad)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English](README.en.md) · 中文

让 AI 读写你本机的 CAD 文件：**读取 STEP/STP、按几何方式编辑立体模型、生成第一角法二维图**。
几何计算全部在 FreeCAD 自己的进程里完成，插件只负责工具注册、参数校验和文件传递——不需要在 DSH 里装 Python，也不上传任何模型。

![示例图纸](https://cdn.jsdelivr.net/gh/Negulons/dsh-freecad@main/docs/images/demo-bracket-drawing.png)

*`examples/demo_bracket.step` 经 `freecad_step_to_drawing` 生成的 A3 图纸（SVG/DXF/PDF/PNG 四格式同时输出）。*

## 它是什么，不是什么

**是**：一个把「大模型说的话」变成「FreeCAD 能执行的几何操作」的薄桥接层。你可以在对话里说「把这个零件转成加工图」「在这里加一个 Ø8 通孔」「把这条边倒 R2 圆角」，模型去调对应的工具。

**不是**：

- **不是生产级出图工具。** 图纸目前只标总宽/总高 + 孔表，凸台直径、台阶高度、孔位这类特征尺寸要人工补；没有剖视图、局部放大、形位公差、粗糙度。**不要直接拿去下厂。** 完整清单见 [docs/limitations.md](docs/limitations.md)。
- **不是 CAD 内核。** 所有几何都靠 FreeCAD；FreeCAD 打不开的文件，这里也打不开。
- **不是云端服务。** 没有网络请求，没有遥测，模型不出本机。

## 环境要求

| 依赖 | 要求 |
| --- | --- |
| 操作系统 | **Windows 10/11（已实测）**；Linux / macOS 需手动指定 `freecadcmd` 路径 |
| FreeCAD | 1.0 或 1.1，且带 `freecadcmd`（官方安装包与便携版都有） |
| DSH | 支持 bundle 的版本（`dsh.bundle.patch` 机制） |
| Node.js | 18+（DSH 自带即可） |

已验证组合：**Windows 11 + FreeCAD 1.1.4（便携版）+ DSH Desktop**。其他组合请自行测试并欢迎反馈。

## 安装

插件是普通 DSH bundle，装进某个 profile 后**必须重启 DSH** 才会挂载。

### 方式 A：在 DSH 插件页安装（推荐，已实测）

打开 DSH 的 **插件** 页，输入 `dsh-freecad` 搜索并安装，然后重启 DSH。插件页会自己写好 profile 的依赖、`dsh.profile.bundles` 与 `cordis.patch.yml` 条目，不需要手工改任何文件。

> 这条路径已在干净的 DSH 实例上验证通过。若重启后「设置 → FreeCAD」没出现，再重启一次（浏览器半侧 bundle 只在启动时注册）。

### 方式 B：npm + 安装脚本

```bash
npm i dsh-freecad     # 或 pnpm add dsh-freecad
node node_modules/dsh-freecad/scripts/install.mjs
```

`install.mjs` 会：把包装进 `<profile>/plugins/dsh-freecad`；在 `package.json` 里写入 `file:` 依赖并加进 `dsh.profile.bundles`；在 `cordis.patch.yml` 追加一条**顶层**的 `id: freecad` 行；执行 `pnpm install`（没有 pnpm 时退化为直接复制到 `node_modules`）。**被改动的文件都会先备份为 `*.bak-<时间戳>`。**

### 方式 C：从源码安装（开发用）

```bash
git clone <this-repo> dsh-freecad
cd dsh-freecad
node scripts/install.mjs                        # 默认装进 ~/.dsh/profiles/desktop
node scripts/install.mjs --profile "C:/Users/me/.dsh/profiles/other"
```

改完源码重跑这条命令即可覆盖安装（同样先备份）。

> 手工编辑时注意：那条配置必须写在**顶层**，不能包进 `- insert:` 块。DSH 的设置编辑器只会给「顶层、且没有 `insert` 键」的条目写 `config`；写进 insert 块的条目在设置页点保存会一直报「没有保存成功」（服务端返回 `settings/rejected`）。插件页与安装脚本都按顶层写。

### 装完之后

**重启 DSH。** 新进程才会加载 bundle。重启后在对话里说「检查一下 FreeCAD 状态」，或直接调用 `freecad_status`：

```
FreeCADCmd: C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe
来源: default | 存在: true | worker: true
版本: FreeCAD 1.1.4
```

## 指定 FreeCAD 路径

打开 **DSH → 设置 → FreeCAD**，填入 `freecadcmd` 的完整路径（例如便携版）：

![设置 → FreeCAD](https://cdn.jsdelivr.net/gh/Negulons/dsh-freecad@main/docs/images/settings-freecad.png)

```
D:\Tools\FreeCAD_1.1.4-Windows-x86_64-py311\bin\freecadcmd.exe
```

保存后**立即生效，不需要重启**——这个字段是 volatile 配置，保存即重新应用插件配置。该页还提供两个下载入口：官方 GitHub Releases 与清华 TUNA 镜像（国内可用）。

路径的解析顺序：**设置页 → profile 配置 `config.freecadPath` → 环境变量 `FREECAD_CMD` → `C:\Program Files\FreeCAD 1.1|1.0|FreeCAD\bin\freecadcmd.exe`**。前两者都接受「exe 路径 / bin 目录 / 安装根目录」三种写法。

## 工具

| 工具 | 作用 |
| --- | --- |
| `freecad_status` | 检查 `freecadcmd` 路径、版本、worker 是否就绪。**出问题时先调它。** |
| `freecad_inspect_step` | 读取 STEP/STP/IGES/BREP：包围盒、体积、面积、面/边/顶点数、对象列表、圆柱孔识别（直径/轴向/通孔/深度/中心）；`detail: true` 返回面与边明细，用 `offset`/`limit` 翻页读全。 |
| `freecad_edit_step` | 平移/旋转/缩放/镜像、钻通孔或盲孔、盒/圆柱/球布尔增删、倒圆角或倒角（按 1-based 索引，或按位置 `edgesNear` / `edgeAt`——索引每次编辑后会重排）；导出新 STEP（默认不覆盖输入），可选同时存 FCStd。 |
| `freecad_step_to_drawing` | HLR 隐藏线消除 → 第一角法主视图/俯视图/右视图/轴测图，自动图幅与比例、总尺寸、孔中心线、孔表（超 10 孔自动分栏续排）、标题栏，导出 SVG / DXF / PDF / PNG。 |
| `freecad_measure` | 不改模型，直接量：点/面/边之间的距离（含 `planeOffset` 两平面间距）、两面或两直边夹角、圆柱/圆边直径。量完就能拿去标图。 |

所有长度单位为 **mm**。参数细节见 [docs/tools.md](docs/tools.md)。

## 快速上手

```text
你：读一下 examples/demo_bracket.step，告诉我它有几个孔、多大。
你：把它转成 A3 加工图，带轴测图，输出 PNG 和 DXF。
你：在顶面中心加一个 Ø8 通孔，倒 C1 角，另存一份。
```

对应三次工具调用，产物落在工作目录下（默认 `<输入名>_drawing/` 与 `<原名>_edited.step`）。

## 已知问题与排错

**便携版 FreeCAD 启动报 `Could not create directories. Failed with: Access is denied.`**
0.2.4 起宿主会自动处理：只要 `freecadcmd` 不在 `Program Files` 下，就把 `FREECAD_USER_HOME` /
`FREECAD_USER_DATA` / `TMP` 指到安装目录旁的 `dsh-user/`（不可写时退回系统临时目录）。若你要指定自己的目录（例如保留 FreeCAD 偏好设置），
显式设置这三个变量即可覆盖：

```
FREECAD_USER_HOME=D:\Tools\FreeCAD\home
FREECAD_USER_DATA=D:\Tools\FreeCAD\data
TMP=TEMP=D:\Tools\FreeCAD\temp
```

**`freecad_status` 说 not found，但 FreeCAD 明明装了**
默认只找 `C:\Program Files\...`。用设置页指定路径，或设 `FREECAD_CMD`。

**图纸里尺寸很少**
这是当前设计：只标总宽/总高 + 孔表。需要更多尺寸时，让模型在对话里读几何后补充标注，或参考 `docs/drawing-engine.md` 自己扩展。

**改了 `dsh/*.py` 没生效**
worker 每次调用都重新加载，通常不需要重启；如果改了 `index.js` 或 `lib/client.js`，**必须重启 DSH**。

更多见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [architecture.md](docs/architecture.md) | 三层结构、请求/结果协议、为什么几何放在 FreeCAD 进程里 |
| [tools.md](docs/tools.md) | 四个工具每个参数的语义与坑 |
| [drawing-engine.md](docs/drawing-engine.md) | HLR 投影、视图布局、尺寸、孔表、标题栏的实现 |
| [troubleshooting.md](docs/troubleshooting.md) | 安装、部署、常见错误 |
| [development.md](docs/development.md) | 改代码、人工验收清单 |
| [limitations.md](docs/limitations.md) | 已知限制与待办（**先读这个再报 bug**） |

## 贡献

欢迎 issue 与 PR，尤其是「最小 STEP 复现文件 + 截图」。规则见 [CONTRIBUTING.md](CONTRIBUTING.md)：一次 PR 只做一件事；**中英文 README 必须同步**；客户图纸一律不得提交。

## 许可证

[MIT](LICENSE) © 2026 蓝色大肥鱼 (dsh-freecad)。

本插件不打包、不分发 FreeCAD。运行时依赖 FreeCAD（LGPL-2.1-or-later）及其自带的 Python 环境（Pillow、matplotlib），详见 [NOTICE](NOTICE)。
