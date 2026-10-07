"""首次运行 / 空状态防呆 —— 阶段 5 验收「用户能自己从头跑完一遍」的机械部分。

为什么单独一个文件：**最容易翻车的恰恰是最开始那几下** —— 程序刚装好、
一张素材都没选的时候点按钮、拖错文件夹。这里用一个**全新的空配置目录**
（`PBR2PHONG_HOME` 指到临时目录）模拟"第一次双击启动"。

跑法：python tests/test_first_run.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

from core import imaging, settings  # noqa: E402
from gui.main import MainWindow  # noqa: E402

PASS: list = []
FAIL: list = []

BOXES: list = []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def _fake_box(kind):
    def f(parent, title, text, *a, **k):
        BOXES.append((kind, str(title), str(text)))
        return QtWidgets.QMessageBox.Ok
    return f


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="pbr2phong-firstrun-"))
    # ★ 关键：指到一个还不存在的目录 = "这台机器第一次运行"
    os.environ["PBR2PHONG_HOME"] = str(tmp / "home")
    os.environ.pop("PBR2PHONG_LANG", None)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # 弹框会被替换掉：既不死等用户点，又能断言"到底说了什么人话"
    QtWidgets.QMessageBox.information = staticmethod(_fake_box("info"))
    QtWidgets.QMessageBox.warning = staticmethod(_fake_box("warn"))
    QtWidgets.QMessageBox.critical = staticmethod(_fake_box("crit"))

    print("== ① 第一次双击：配置目录还不存在 ==")
    win = MainWindow()
    win.show()
    app.processEvents()
    root = Path(win.config_root)
    check("配置目录被建出来", root.is_dir(), str(root))
    check("内置 config.json 导出了", (root / "config.json").is_file())
    check("内置预设导出了（≥5 套）", len(settings.load_presets(str(root))) >= 5,
          str(sorted(settings.load_presets(str(root)))))
    check("预设下拉不是空的", win.page_settings.cmb_preset.count() >= 5,
          str(win.page_settings.cmb_preset.count()))
    check("标签页文字都填上了（没有空标签）",
          all(win.tabs.tabText(i).strip() for i in range(win.tabs.count())),
          str([win.tabs.tabText(i) for i in range(win.tabs.count())]))
    check("状态栏是「就绪」，不是调试信息",
          win.lbl_status.text() == win.t("status.ready"), win.lbl_status.text())
    # ⚠️ 03 §2 决策 A（2026-09-26 改）：「开始转换」移到第 2 页，且**没导入素材时禁用** ——
    #    所以这里从原来的"可点"改成"必须是灰的"。
    check("还没导入素材 → 开始转换是灰的、取消也不可点",
          not win.btn_start.isEnabled() and not win.btn_cancel.isEnabled())
    check("表格是空的", win.page_convert.table.rowCount() == 0)
    check("没跑过时不显示结果清单",
          not win.page_export.grp_result.isVisibleTo(win.page_export))

    print("== ② 什么都没选就点「开始转换」/「校验模型」 ==")
    BOXES.clear()
    win.start_conversion()
    app.processEvents()
    check("说了「先选一个素材文件夹」", len(BOXES) == 1 and "文件夹" in BOXES[0][2], str(BOXES))
    check("没有偷偷起后台线程", win.worker is None)
    check("按钮状态没被搞坏（没素材就一直是灰的）",
          not win.btn_start.isEnabled() and not win.btn_cancel.isEnabled())
    BOXES.clear()
    win.page_convert.check_model()
    check("校验模型说了「先选 .mdl」", len(BOXES) == 1 and ".mdl" in BOXES[0][2], str(BOXES))

    print("== ③ 拖错文件夹（里面没有能认的贴图） ==")
    empty = tmp / "空文件夹"
    empty.mkdir(parents=True)
    (empty / "readme.txt").write_text("no textures here", encoding="utf-8")
    BOXES.clear()
    win.page_convert.load_folder(empty)
    app.processEvents()
    check("明确说了「这个文件夹里没找到能认的贴图」",
          len(BOXES) == 1 and "没找到能认的贴图" in BOXES[0][2], str(BOXES)[:200])
    check("弹框给了正确做法（选直接放 PNG 的那层）", "PNG" in BOXES[0][2])
    check("状态栏也说了没认到", "没认到" in win.lbl_status.text(), win.lbl_status.text())
    check("标签回到「还没有选择素材」",
          win.page_convert.lbl_recognized.text() == win.t("label.recognized_empty"),
          win.page_convert.lbl_recognized.text())
    BOXES.clear()
    win.start_conversion()
    check("空文件夹时开始转换仍被拦住", len(BOXES) == 1 and win.worker is None, str(BOXES))

    print("== ④ 认到素材了，但还没填材质名 ==")
    good = tmp / "素材"
    good.mkdir()
    imaging.save(np.dstack([np.full((8, 8), 180, np.uint8)] * 3), good / "FirstRun-BaseColor-8.png")
    BOXES.clear()
    win.page_convert.load_folder(good)
    app.processEvents()
    check("认到 1 套素材", len(win.page_convert.sets) == 1, str(len(win.page_convert.sets)))
    check("认到时没有弹框（正常情况别烦人）", not BOXES, str(BOXES))
    check("标签写「已识别 1 套素材」", "1" in win.page_convert.lbl_recognized.text(),
          win.page_convert.lbl_recognized.text())
    win.page_convert.ed_mat.setText("")
    win.page_convert.rb_model.setChecked(True)         # 默认就是这条，显式写出来
    BOXES.clear()
    win.start_conversion()
    check("没材质名时说了「先填材质名（或用 .mdl 自动读）」",
          len(BOXES) == 1 and "材质名" in BOXES[0][2], str(BOXES)[:200])
    check("也没起后台线程", win.worker is None)

    print("== ⑤ 切换语言：整屏（含状态栏）都得跟着换 ==")
    before = win.lbl_status.text()
    win.set_language("en")                           # 右上角语言按钮的等价入口
    app.processEvents()
    check("状态栏那句也跟着翻译了（不是残留中文）",
          win.lbl_status.text() == win.t("scan.done", n=1) and win.lbl_status.text() != before,
          f"{before!r} → {win.lbl_status.text()!r}")
    check("标签页也换语言了", "转换" not in win.tabs.tabText(0), win.tabs.tabText(0))
    check("右上角按钮的文字也换成了原生写法", win.btn_lang.text() == "简体中文", win.btn_lang.text())
    win.set_language("zh")
    app.processEvents()
    check("切回中文也正常", "转换" in win.tabs.tabText(0), win.tabs.tabText(0))

    print("== ⑥ 关掉窗口：偏好要记住 ==")
    win.resize(1000, 700)
    win.close()
    app.processEvents()
    prefs = settings.load_gui_prefs(str(root))
    check("gui.json 写得出来", (root / "gui.json").is_file(), str(root / "gui.json"))
    check("gui.json 里有语言/预设/窗口大小",
          {"语言", "预设", "窗口大小"} <= set(prefs or {}), str(prefs))

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"   失败：{f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)          # 同 test_gui_flow：避开 Qt offscreen 收尾时的崩溃码
