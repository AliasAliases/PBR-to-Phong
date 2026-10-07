"""离屏截 GUI 图（开发时用来"自己看一眼"界面）。

这台机器上 HLMV 那类真窗口程序起不来，但 Qt 可以走 **offscreen** 平台插件：
构造窗口 → `grab()` 成图 → 存 PNG，于是界面能不进桌面也能被看到/被核对。

`_task/06-版式落地.md` §7.3 要求：**5 页各一张（1280×760）+ 1200×680 的佐证**；
§7.6 要求**清掉 `阶段0_实测/out/gui/` 的旧截图**（不然有人点开旧图会以为没改）——
所以本脚本每次运行会**先删掉输出目录里的旧 PNG**，再重新全量截。

用法：python tests/shot_gui.py [输出目录]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from gui.main import MainWindow, WINDOW_MIN, WINDOW_SIZE  # noqa: E402

# 五个页签的名字（截图文件名用，跟 06 §5.5 的字面值对应）
PAGES = ("转换", "预览与调参", "参数表-材质属性-自由键值", "导出", "关于")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parents[2] / "阶段0_实测" / "out" / "gui"
    out.mkdir(parents=True, exist_ok=True)

    # 先清旧图：旧截图会让人以为新版没改（06 §7.6）
    stale = sorted(out.glob("*.png"))
    for p in stale:
        p.unlink()
    print(f"  清掉旧截图 {len(stale)} 张")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # ⚠️ 只在这个截图工具里指定字体：离屏字体库对"中文行里夹拉丁词"的排版会糊，
    #    指定一个中英都全的字体就能正常渲染。**应用本身不写死字体名**（界面规范要求），
    #    否则换台机器可能缺字。
    for family in ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei"):
        if family in QtGui.QFontDatabase.families():
            app.setFont(QtGui.QFont(family, 9))
            print(f"  截图字体：{family}")
            break

    win = MainWindow()
    win.resize(*WINDOW_SIZE)
    win.show()
    # ⚠️ S3 起第 2 页的预览框**接真图**了：截图前必须先导入一套素材，否则截出来是占位
    material = Path(__file__).resolve().parents[2] / "测试素材" / "合成素材"
    if material.is_dir():
        win.page_convert.load_folder(material)
        for _ in range(3):
            app.processEvents()
        print(f"  已导入素材：{material.name}（预览框里就有真图了）")

    def shot(name: str):
        """抓图前强制把布局重跑一遍，否则离屏渲染会用旧的控件几何，
        文字会跟邻居叠在一起（看起来像"字糊了"）。"""
        win.layout().activate()
        win.tabs.currentWidget().layout().activate()
        win.page_tuning.apply_sizes()          # 第 2 页的预览框按实到尺寸实算
        for _ in range(3):
            app.processEvents()
        win.repaint()
        app.processEvents()
        path = out / f"{name}.png"
        win.grab().save(str(path))
        print(f"  ✓ {path.name}  ({path.stat().st_size // 1024} KB)")

    def shoot_all(tag: str):
        for i, name in enumerate(PAGES):
            win.tabs.setCurrentIndex(i)
            for _ in range(2):
                app.processEvents()
            shot(f"{tag}-{i + 1}-{name}")

    def resize(w: int, h: int):
        win.resize(w, h)
        for _ in range(3):
            app.processEvents()

    # ---- 1280×760：5 页全截（判据 3 的主证据）----
    for _ in range(3):
        app.processEvents()
    shoot_all("zh-1280")

    # ---- 1200×680：最小尺寸的佐证（零滚动要在最小尺寸下也成立）----
    resize(*WINDOW_MIN)
    shoot_all("zh-1200")

    # ---- 英文：验证双语与「直译 + 解释」都在（判据 5）----
    resize(*WINDOW_SIZE)
    win.set_language("en")               # 右上角语言按钮的等价入口
    shoot_all("en-1280")
    # 11 片：**英文才是"灰字解释被无声切掉"的重灾区**（中文一条都不切）→ 最小尺寸也要英文佐证
    resize(*WINDOW_MIN)
    shoot_all("en-1200")
    resize(*WINDOW_SIZE)
    win.set_language("zh")

    # ---- 「这次的结果」只有真跑完才出现 ----
    # 造一个"刚跑完"的状态，专门看一眼清单与按钮的排版，免得交付了才发现挤在一起。
    win.tabs.setCurrentIndex(3)
    exp = win.page_export
    win.last_summary = (2, 0, 0)
    win.last_out_dir = str(out)
    win.last_log = str(Path(__file__).resolve())
    win.last_failures = []
    exp.refresh_result()
    for _ in range(2):
        app.processEvents()
    shot("zh-1280-4-导出-跑完后")
    win.last_summary = None
    exp.refresh_result()

    print(f"\n输出目录：{out}")

    # ---- 第 2 页：把四根拉条和曲线都动一下再截一张（证明它们是**真的**）----
    win.tabs.setCurrentIndex(1)
    panel = win.page_tuning.panel
    panel.sl_offset.setValue(78)            # 粗糙度整体偏移
    panel.sl_tint.setValue(20)              # 金属染色强度
    rect = panel.curve._rect()
    cx = rect.left() + rect.width() * 0.5
    panel.curve.mousePressEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonPress, QtCore.QPointF(cx, rect.bottom()),
        QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
    panel.curve.mouseReleaseEvent(QtGui.QMouseEvent(
        QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(cx, rect.top() + rect.height() * 0.2),
        QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier))
    for _ in range(3):
        app.processEvents()
    shot("zh-1280-2-预览与调参-调过的")
    win.page_config.reset_overrides()
    win.set_language("zh")
    for _ in range(2):
        app.processEvents()

    # ---- 第 3 页：「这个材质要透明」开关的两个态（判据 6）----
    #      先切到「道具」（该档不透明 → 开关应当是**没勾**的，证明它跟着档走），
    #      再手动勾上截一张（证明勾得动）。解释文字两态都在，说明它是常驻的。
    preset_back = win.page_config.cmb_preset.currentText()
    win.page_config.cmb_preset.setCurrentText("道具")
    for _ in range(2):
        app.processEvents()
    win.tabs.setCurrentIndex(2)
    for _ in range(2):
        app.processEvents()
    shot("zh-1280-3-参数表-材质属性-自由键值-道具档没勾")
    win.page_config.chk_cutout.setChecked(True)
    for _ in range(2):
        app.processEvents()
    shot("zh-1280-3-参数表-材质属性-自由键值-手动勾上")
    win.page_config.reset_overrides()
    win.page_config.cmb_preset.setCurrentText(preset_back)
    for _ in range(2):
        app.processEvents()

    # ---- 文字核对：把每个控件上的字 dump 成文本（比看像素可靠，截图只用来验布局）----
    dump = out / "界面文字.txt"
    rows = []
    for lang in ("zh", "en"):
        win.set_language(lang)
        for i, name in enumerate(PAGES):
            win.tabs.setCurrentIndex(i)
            app.processEvents()
            rows.append(f"===== [{lang}] {name} =====")
            for w in win.tabs.widget(i).findChildren(QtWidgets.QWidget):
                text = ""
                if isinstance(w, (QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QCheckBox,
                                  QtWidgets.QRadioButton)):
                    text = w.text()
                elif isinstance(w, QtWidgets.QGroupBox):
                    text = w.title()
                elif isinstance(w, QtWidgets.QComboBox):
                    text = " / ".join(w.itemText(k) for k in range(w.count()))
                if text:
                    rows.append(f"   [{type(w).__name__}] {text}")
    win.set_language("zh")
    rows.append("===== 标签页 =====")
    rows += [f"   {win.tabs.tabText(i)}" for i in range(win.tabs.count())]
    rows.append("===== 状态栏 =====")
    rows.append(f"   {win.btn_cancel.text()}（「开始转换」在第 4 页「导出」里，不在状态栏）")
    dump.write_text("\n".join(rows), encoding="utf-8")
    print(f"  ✓ {dump.name}  （控件文字清单，用于核对文案）")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)          # 同上：避开 Qt offscreen 收尾时的崩溃码
