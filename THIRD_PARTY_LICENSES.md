# 第三方组件与许可 / Third-party components and licences

> 这份文件是给**拿到分发包的人**看的：包里除了我们自己的代码，还带了别的东西，各自有自己的许可。
> This file is for **people who received a release package**: it bundles third-party components with their own licences.

**一句话**：本项目自身是 **MIT**（见 `LICENSE`）；分发包里最大的一块是 **PySide6 / Qt（LGPLv3）** ——
它**不是**我们写的，我们**动态链接**它并且**允许你替换**它。
**TL;DR**: this project is MIT; the release bundles **PySide6 / Qt (LGPLv3)**, dynamically linked and replaceable.

---

## 1. PySide6 / Qt —— LGPLv3（分发包里体积最大的一块）

- 组件：`PySide6`（Qt for Python 的官方绑定）+ `shiboken6` + Qt 的运行时库（`Qt6Core.dll` / `Qt6Gui.dll` / `Qt6Widgets.dll` / `plugins\` 等）。
- 许可：**GNU Lesser General Public License v3.0（LGPLv3）**
  - 许可全文：https://www.gnu.org/licenses/lgpl-3.0.txt
  - Qt 官方对 LGPL 的说明：https://www.qt.io/licensing/open-source-lgpl-obligations
  - 源码获取：https://download.qt.io/official_releases/QtForPython/ 与 https://code.qt.io/
- 我们怎么满足 LGPL：
  1. **动态链接**：Qt 是 exe 旁边的 `.dll`，**没有被静态链接进 exe**；
  2. **允许替换**：你可以用自己编译/其他版本的 Qt 同名 dll **直接替换** `dist/PBR2Phong/` 里的那些文件；
  3. **附许可与出处**：本文件 + 上面两个链接；
  4. 本项目**没有**修改 Qt / PySide6 的源码。
- 如果你想彻底摆脱这一块：本项目是开源的，你可以自己用系统 Python + pip 装 PySide6 跑源码版（那样 PySide6 由你自己安装与维护）。

## 2. numpy —— BSD 3-Clause

- 用途：所有贴图运算（通道搬运、指数曲线、缩放）。
- 许可全文：https://numpy.org/doc/stable/license.html

## 3. Pillow (PIL) —— MIT-CMU / HPND

- 用途：读写 PNG。
- 许可全文：https://github.com/python-pillow/Pillow/blob/main/LICENSE

## 4. 我们自己写的部分 —— MIT

- `PBR2Phong/`（`core/` `cli/` `gui/` `tests/`）、`启动PBR2Phong.bat`、文档。
- 见仓库根目录的 `LICENSE`。

## 5. ⚠️ 我们没有分发、但你可能会用到的外部工具

| 工具 | 谁提供 | 许可 | 我们怎么用它 |
|---|---|---|---|
| **VTFCmd.exe**（VTFEdit Reloaded 自带） | 你自己安装 | **LGPL-2.1** | 只是**调用**它把 PNG 转成 VTF。**不随本包分发**。 |
| **vtex.exe**（L4D2 自带） | Steam / 游戏本体 | 随游戏 | 备用后端（VTFCmd 不在时才考虑） |
| **HLMV / HLMV++** | 游戏本体 / 第三方 | 随游戏 | 只是启动它让你看材质，不捆绑 |

> 结论：**本仓库不含任何 GPL/LGPL 代码，也不含 Valve 的二进制**。分发包里唯一的 LGPL 组件是 Qt/PySide6（见 §1）。
> Bottom line: this repository ships no GPL/LGPL *code* of its own and no Valve binaries; the only LGPL component in the release is Qt/PySide6 (§1).
