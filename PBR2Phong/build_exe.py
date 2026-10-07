# -*- coding: utf-8 -*-
"""打一个「能发给别人」的 **onedir** 包（实施计划 §9.6 / 阶段 6）。

用法（命令行里，工程目录下）：
    python build_exe.py            # 打包
    python build_exe.py --check    # 只打印会用的参数，不真打

产物：`<工作区>/dist/PBR2Phong/` —— 双击里面的 `PBR2Phong.exe` 就能跑。

## 两个关键选择（写下来免得以后有人改错）

**为什么 `--onedir` 而不是 `--onefile`**
分发包里带着 PySide6 / Qt（**LGPLv3**）。LGPL 的常见合规姿势就是「**动态链接 + 让用户可替换 Qt**」
—— `--onedir` 把 Qt 的 `.dll` 平平地放在 exe 旁边，用户能直接换；`--onefile` 会压成一个 exe、
每次启动解压到临时目录，既慢又没法替换 Qt。**这也是用户拍板的决策 B（接受体积，因为要开源）。**

**为什么 `--windowed`（不弹黑框）**
面向普通用户，不该有控制台窗口。出错的痕迹走 `log.txt`（GUI「关于」页可打开）与
`%APPDATA%\\PBR2Phong`。代价：**启动期崩溃看不到 traceback** → 真出问题要临时用 `--console` 重打一次。

**没有 `--add-data`**：内置默认与五套预设都在代码里（`core/settings.py` + `core/phong.py`），
运行时配置落在 `%APPDATA%\\PBR2Phong`，所以不需要额外数据文件。
**不捆绑 VTFCmd**：它是外部工具（VTFEdit-Reloaded 带，LGPL-2.1 **不随我们分发**），程序会自动找。

## 14-B：三件套**随包**（许可合规的硬要求）

分发包里带 **PySide6 / Qt（LGPLv3）**。**动态链接这半截我们做对了**（Qt 的 dll 就在 exe 旁边、可替换），
但 **LGPLv3 还要求"随包附许可文本与声明"** —— 所以打包完成后把工作区根的
`README.md` / `LICENSE` / `THIRD_PARTY_LICENSES.md` **拷进 `dist/PBR2Phong/`**（见 `copy_bundle_docs()`）。
⚠️ 少了这一步，"能发给别人"在法律意义上不成立 —— 别删这个函数。
⚠️ **版权行 / 三件套改了就要重打**：包里是**拷贝**，不会跟着源文件走。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../PBR to Phong/PBR2Phong
ROOT = HERE.parent                              # 工作区根
DIST = ROOT / "dist"
WORK = ROOT / "build" / "pbr2phong"
SPEC = ROOT / "build"

# 这些 Qt 模块我们一个都没 import（PySide6 默认会把一大堆拉进来）→ 剔掉给包减重。
# ⚠️ 保守起见，**不要**排除这几个：QtCore / QtGui / QtWidgets（必需）、
#    QtSvg* 与 QtNetwork（QtWidgets 的图标与插件可能用到）、QtOpenGLWidgets（日后上 GPU 预览的退路）。
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtRemoteObjects",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtStateMachine",
    "PySide6.QtTextToSpeech", "PySide6.QtScxml", "PySide6.QtOpenGL", "PySide6.QtOpenGLFunctions",
    "tkinter", "matplotlib", "pandas", "IPython", "pytest",
]


def build_args() -> list:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir",                      # 见文件头：合 Qt LGPL，可替换
        "--windowed",                    # 面向普通用户，不弹黑框
        "--name", "PBR2Phong",
        "--paths", str(HERE),            # 让 `import i18n` / `from core import …` 能被解析
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(SPEC),
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    args.append(str(HERE / "run_gui.py"))
    return args


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return str(n)


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


# 14-B：随包三件套（许可合规）。**这是硬要求**，不是装饰 —— 包里带着 Qt（LGPLv3）。
BUNDLE_DOCS = ("README.md", "LICENSE", "THIRD_PARTY_LICENSES.md")


def copy_bundle_docs(pkg: Path) -> list:
    """把三件套拷进包里。返回 (文件, 字节) 列表；缺哪个就明说（不静默）。"""
    copied = []
    for name in BUNDLE_DOCS:
        src = ROOT / name
        if not src.is_file():
            print(f"  ⚠️ 缺 {name}（{src}）—— 包里就没有它，许可合规会不完整")
            continue
        shutil.copy2(src, pkg / name)
        copied.append((name, (pkg / name).stat().st_size))
    return copied


def main() -> int:
    args = build_args()
    if "--check" in sys.argv:
        print(" ".join(f'"{a}"' if " " in a else a for a in args))
        return 0

    print("PyInstaller 参数：")
    print("  " + " ".join(f'"{a}"' if " " in a else a for a in args))
    print("\n开始打包（第一次通常 1~3 分钟）…\n")
    rc = subprocess.call(args, cwd=str(HERE))
    if rc != 0:
        print(f"\n✗ PyInstaller 失败，退出码 {rc}")
        return rc

    exe = DIST / "PBR2Phong" / "PBR2Phong.exe"
    if not exe.is_file():
        print(f"\n✗ 打包结束但没找到 {exe}")
        return 1

    pkg = exe.parent
    # 14-B：三件套随包（LGPLv3 要求 —— 包里带 Qt，必须附许可文本与声明）
    docs = copy_bundle_docs(pkg)
    print(f"\n✓ 包好了：{pkg}")
    print(f"  入口：{exe.name}（{human(exe.stat().st_size)}）")
    print(f"  随包三件套：{'、'.join(f'{n}（{human(s)}）' for n, s in docs) or '**一份都没有**'}")
    print(f"  整包：{human(dir_size(pkg))}，文件 {sum(1 for _ in pkg.rglob('*') if _.is_file())} 个")

    # 最大的几坨是啥（一般是 Qt 的 dll / numpy），列出来心里有数
    big = sorted((f for f in pkg.rglob("*") if f.is_file()),
                 key=lambda f: f.stat().st_size, reverse=True)[:6]
    print("  最大的几个文件：")
    for f in big:
        print(f"    {human(f.stat().st_size):>9}  {f.relative_to(pkg)}")

    print("\n自检三步（别只看「打好了」）：")
    print("  1) python tests/check_exe.py      —— 真启动一次并抓窗口图（证明能起 GUI）")
    print("  2) 双击 dist\\PBR2Phong\\PBR2Phong.exe，照 GUI自测清单.md 走一遍")
    print("  3) 把 dist\\PBR2Phong 整个文件夹拷到别人机器上试（这是「能发给别人」的真正判据）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
