# PBR2Phong · 把 PBR 贴图转成 L4D2 能用的 Phong 材质

把 **PBR（金属度 / 粗糙度）流程**的贴图，转成 **Left 4 Dead 2（起源 1 / Source 2013）** 能用的 **Phong** 材质。
输入 = Material Bakery 烘出来的贴图集；输出 = 通道打包 PNG + **VTF** + **`.vmt`**，可以直接写进游戏的 `materials`。

> 中文说明在下，英文说明见后半（两段都是写全的，不是互指）。
> **This file is bilingual: 中文在前，English in the second half.**

---

## 一、这是什么

- **吃**：一套 PBR 贴图（底色 / 粗糙度 / 金属度 / 法线 / AO）。有 Material Bakery 的 `_mbakery.json` 认得最准；没有就按文件名认（`X-BaseColor-2k.png` 这类写法都认）。
- **出**：3 张打包好的 PNG（`_basecolor` RGBA / `_normal` RGBA / `_exp` RGB）→ 自动调 **VTFCmd** 转成 **VTF 7.4** → 生成 `.vmt` → 可以**直接部署**进 L4D2 的 `materials`。
- **界面**：**5 页**（① 转换 / ② 预览 + 调参 / ③ 参数表·材质属性 / ④ 导出 / ⑤ 关于），**零滚动**（不会有滚动条）；**中英双语**、默认跟随系统；**每个参数都带一句人话解释**（不用懂 `$phongboost`、`exponent` 这些术语）。
- **调参**：**21 档预设**（模型 11 / 笔刷 9 / 贴花 1，按模式自动过滤），参数**常驻可见**、拖一下拉条就能在旁边看到成品变化；另有曲线编辑器与材质属性面板（`$surfaceprop` 等）。

## 二、怎么跑

| 方式 | 怎么做 | 前提 |
|---|---|---|
| **A. 用发过来的包** | 双击 `PBR2Phong.exe` | 什么都不用装 |
| **B. 跑源码** | 双击工作区根目录的 `启动PBR2Phong.bat` | Python 3.11 + numpy + Pillow + PySide6 |

两种方式**都需要**下面这些东西才能真正干活（缺了界面上会有人话提示，不会崩）：

- **VTFCmd.exe** ← 装了 **VTFEdit Reloaded** 就有（程序会自动找，找不到可以在「① 转换 → 路径」里手填，会记住）
- **L4D2** ← 只有"直接写进游戏"才需要（默认路径 `D:\SteamLibrary\...`，可在设置里改）

### ⚠️ Windows 第一次运行会拦一下（SmartScreen）

可能弹出 **「Windows 已保护你的电脑 · 未知发布者」** —— 因为这个 exe **没有买代码签名证书**。
点 **「更多信息」→「仍要运行」** 就行。不放心的话：

1. 直接用源码版（`启动PBR2Phong.bat`），或
2. 自己打包（`python PBR2Phong/build_exe.py`），或
3. 翻源码看看它到底干了啥（`PBR2Phong/core/` 是全部逻辑）

> 要彻底消掉这个提示，只能买代码签名证书。这个免费开源的小工具就不花那个钱了。

## 三、它会改你硬盘上的什么

- **输出**：默认写进 `materials\custom\<材质名>\`（目录可在界面里改），同时在素材文件夹旁边留一份 `<材质名>_phong\` 本地存档（PNG + VTF + log）。
- ⚠️ **它不备份**：碰到同名文件会**先弹框问你要不要覆盖**，但**覆盖是不可撤销的**。
  （这是作者的取舍：覆盖就覆盖，大不了重调材质。**别把你自己手写的 .vmt 放在会撞名的位置。**）
- **它的配置/记忆**：`%APPDATA%\PBR2Phong`（想挪地方就设环境变量 `PBR2PHONG_HOME`）。

## 四、许可

- 本项目 = **MIT**，见 [`LICENSE`](LICENSE)。
- 分发包里含 **PySide6 / Qt（LGPLv3）**：**动态链接**、`dist/PBR2Phong/` 里那些 Qt 的 dll **可以直接替换**；详见 [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)。
- **不含** VTFCmd / VTFEdit-Reloaded —— 那是你自己另外装的工具，我们不分发它。

## 五、已知限制（先说清楚，免得当成 bug）

- **模型材质和地图笔刷都做**：模型 = `VertexLitGeneric` + Phong 高光；笔刷 = `LightmappedGeneric`（在第 ① 页「选择模式」里切）。
  ⚠️ **L4D2 的笔刷在引擎层面就没有 Phong** —— 笔刷的高光/反射走 `$envmap` + 法线图 alpha 当遮罩，明暗交给 lightmap。所以**笔刷材质看起来跟模型材质不一样，这不是 bug**。
- **一个模型多套材质**：第一版一套一套跑（同一个 `$cdmaterials` 目录跑两次，材质名分别填）；自动分批留第二版。
- 程序里**没有 3D 预览**（内嵌渲染当时被否掉了）：第 ② 页的预览是**内存里现算的 2D 贴图预览**；要在立体上看效果，用第 ① 页的「**用 HLMV 看看**」按钮（材质需先部署进 `materials/`），或直接进游戏。
- 法线贴图是**平的**（Blender 那边没烘高模就会这样）→ 程序会提醒你，但不会替你修。
- 用 HLMV 预览看到的是**实时环境光、没有 lightmap**：「材质对不对」够用，「整体明暗」要进游戏看。

---

# PBR2Phong — English

Convert **PBR (metallic/roughness) texture sets** into **Phong materials usable by Left 4 Dead 2** (Source 1 / Source 2013).
Input: a texture set baked by **Material Bakery**. Output: channel-packed PNGs + **VTF** + **`.vmt`**, optionally deployed straight into the game's `materials` folder.

## What it does

- **Reads** a PBR set (base color / roughness / metallic / normal / AO). A Material Bakery `_mbakery.json` is recognised precisely; without one it falls back to filename heuristics.
- **Writes** 3 packed PNGs (`_basecolor` RGBA / `_normal` RGBA / `_exp` RGB) → drives **VTFCmd** to produce **VTF 7.4** → generates `.vmt` → can **deploy** into L4D2 `materials`.
- **GUI**: **five pages** (Convert / Preview + Tuning / Parameter table / Export / About), **no scrolling**, **bilingual (Chinese + English)**, follows your system language, and explains every parameter in plain words.
- **Tuning**: **21 presets** (11 model / 9 brush / 1 decal, filtered by mode); parameters are **always visible** and the preview next to them updates as you drag; plus a curve editor and a material-attribute panel (`$surfaceprop` etc.).

## How to run

- **From a release package**: double-click `PBR2Phong.exe` (nothing else to install).
- **From source**: double-click `启动PBR2Phong.bat` (needs Python 3.11 + numpy + Pillow + PySide6).

You still need **VTFCmd.exe** (comes with VTFEdit Reloaded; the app auto-detects it, or set the path under Convert → Paths) and **L4D2** if you want deployment.

### ⚠️ SmartScreen

Windows may show **“Windows protected your PC — Unknown publisher”** on first run, because this exe is **not code-signed**.
Click **More info → Run anyway**. If you'd rather not: run from source, build it yourself (`python PBR2Phong/build_exe.py`), or read the code (`PBR2Phong/core/` is where all the logic lives).

## What it touches on your disk

- Writes to `materials\custom\<material name>\` (configurable) and keeps a local copy in `<name>_phong\` next to your textures.
- ⚠️ **No backups.** It asks before overwriting a file with the same name, but **overwriting cannot be undone** — the author's deliberate choice.
- Settings live in `%APPDATA%\PBR2Phong` (override with `PBR2PHONG_HOME`).

## Licence

- This project: **MIT** ([`LICENSE`](LICENSE)).
- Bundles **PySide6 / Qt (LGPLv3)**, dynamically linked and replaceable — see [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
- Does **not** bundle VTFCmd / VTFEdit-Reloaded (install those yourself).

## Known limitations

- **Both model materials and map brushes are supported**: model = `VertexLitGeneric` + Phong; brush = `LightmappedGeneric` (switch under “Mode” on page 1).
  ⚠️ **Brushes have no Phong in L4D2** at the engine level — the brush route gets its highlight/reflection from `$envmap` with the normal-map alpha as the mask, and its shading from the lightmap. So brush materials will look different from model materials; **that's not a bug**.
- Multi-material models: run once per material in v1 (same `$cdmaterials` folder, two runs).
- **No 3D preview inside the app** (embedding was declined): page 2 shows a **2D preview computed in memory**; to look at the material in 3D use the **“Look at it in HLMV”** button on page 1 (the material must be deployed into `materials/` first), or check it in-game.
- A **flat** normal map (no high-poly bake) is reported as a warning, not fixed for you.
- HLMV preview uses real-time ambient lighting and **no lightmap**: fine for checking a material, not for judging overall brightness.
