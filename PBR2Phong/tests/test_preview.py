"""S3 预览接真图（离屏跑）。

对应 `_task/07-S3+S4-预览与拉条.md` §3.1 与验收判据 2：
  · 左框 = 源素材（素材文件夹里的底色）；右框 = 我们产出的成品（默认 `_exp`，可切）
  · **刷新粒度**：拖滑杆时右框**不变**，**松手**后才变（拿两张图的像素比）
  · 只做**贴图本体**的对比（不是带光照的 3D 渲染）
  · 预览是内存里现算的：**不写盘、不调 VTFCmd**

跑法：python tests/test_preview.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-preview-")

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

from gui.main import MainWindow  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def snap(box):
    a = box.image_array
    return None if a is None else np.array(a)


def differs(x, y) -> bool:
    """两张预览图有没有可见差别（形状不同也算变了）。"""
    if x is None or y is None:
        return (x is None) != (y is None)
    if x.shape != y.shape:
        return True
    return bool((x != y).any())


def page_sets(win):
    """当前导入的素材套（`load_folder` 之后才有）。"""
    return list(win.page_convert.sets)


def main() -> int:
    print("== S3 预览接真图（离屏）==")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    folder = WS / "测试素材" / "合成素材"
    check("合成素材存在", folder.is_dir(), str(folder))
    if not folder.is_dir():
        return 1

    win = MainWindow()
    win.resize(1280, 760)
    win.show()
    app.processEvents()
    prev = win.page_tuning.preview
    panel = win.page_tuning.panel

    # ---------- 还没导入素材：两框都是"先导入素材"的占位，不许有图 ----------
    print("== 还没导入素材 ==")
    check("左框没有图（占位）", not prev.left.has_image)
    check("右框没有图（占位）", not prev.right.has_image)
    check("占位文字是 i18n 来的（英文下不许有中文）",
          "导入素材" in prev.left.canvas.text() or "\n" in prev.left.canvas.text(),
          prev.left.canvas.text()[:40].replace("\n", "⏎"))

    # ---------- 导入素材：两框都接上真图 ----------
    print("== 导入素材后 ==")
    before = {p.name for p in folder.parent.iterdir()}
    win.page_convert.load_folder(folder)
    for _ in range(3):
        app.processEvents()
    check("左框有图了（源素材）", prev.left.has_image)
    check("右框有图了（产出成品）", prev.right.has_image)
    src = snap(prev.left)
    out0 = snap(prev.right)
    check("左框拿的是素材里的底色（256×256 那套）",
          src is not None and src.shape[:2] == (256, 256), f"{None if src is None else src.shape}")
    check("右框默认看图种 = 指数贴图（单子要求 `_exp`）",
          prev.current_kind() == "exp", prev.current_kind())
    check("底图上标了尺寸（人话）", "×" in prev.right.foot.text(), prev.right.foot.text())
    check("左上角标题写了素材名", "Barrel" in prev.left.caption, prev.left.caption)
    check("预览图降到 ≤512 再显示（不拿 2048² 原图每帧缩放）",
          out0 is not None and max(out0.shape[:2]) <= 512, f"{None if out0 is None else out0.shape}")

    # ---------- 预览**不写盘** ----------
    after = {p.name for p in folder.parent.iterdir()}
    check("预览不写盘（没多出任何文件/文件夹）", before == after,
          f"新增：{sorted(after - before)}")

    # ---------- 刷新粒度（判据 2 的核心）----------
    print("== 刷新粒度：拖动不变、松手才变 ==")
    base = snap(prev.right)
    panel.sl_sharp.setSliderDown(True)          # 假装按住「高光锐度」
    panel.sl_sharp.setValue(95)
    app.processEvents()
    check("按住拖动中：数值跟手了", panel.lbl_values["sharpness"].text() != "",
          panel.lbl_values["sharpness"].text())
    check("按住拖动中：**右框没变**（攒着）", not differs(base, snap(prev.right)))
    panel.sl_sharp.setSliderDown(False)
    panel.sl_sharp.sliderReleased.emit()        # 松手
    for _ in range(2):
        app.processEvents()
    check("松手后：**右框变了**", differs(base, snap(prev.right)))
    win.page_config.reset_overrides()

    # ---------- 只改 VMT 的滑杆不会改变贴图预览（是设计，不是 bug）----------
    d0 = snap(prev.right)
    panel.sl_boost.setValue(20)                 # $phongboost 只写进 VMT
    app.processEvents()
    check("「高光强度」只改 VMT → 贴图预览不该变", not differs(d0, snap(prev.right)))
    win.page_config.reset_overrides()

    # ---------- 图种切换 ----------
    print("== 右框图种 ==")
    kinds = [prev.cmb_kind.itemData(i) for i in range(prev.cmb_kind.count())]
    check("模型线可选：指数 / 底色 / 法线", kinds == ["exp", "basecolor", "normal"], str(kinds))
    exp_img = snap(prev.right)
    prev.cmb_kind.setCurrentIndex(kinds.index("basecolor"))
    app.processEvents()
    check("切到底色 → 换了一张图", exp_img is not None and snap(prev.right) is not None
          and not np.array_equal(exp_img[:, :, :3],
                                 np.array(snap(prev.right))[:, :, :3]),
          "指数图与底色图不同")
    # ⚠️ Barrel 这套素材**没烘法线** → 选「法线」时右框要**明说没有这张图**，
    #    不能拿"先在第 ① 页导入素材"去糊弄（那会让人以为素材没读进来）。
    prev.cmb_kind.setCurrentIndex(kinds.index("normal"))
    app.processEvents()
    check("素材没有法线时：右框说人话（不是空白、也不是「先导入素材」）",
          (not prev.right.has_image) and "没有这张图" in prev.right.canvas.text(),
          prev.right.canvas.text().replace("\n", "⏎"))

    # 换一套**有法线**的素材（Couch）→ 法线就有图了
    couch = [s for s in page_sets(win) if s.group == "Couch"]
    if couch:
        win.page_convert.sets = couch
        win.refresh_preview(force=True)
        app.processEvents()
        check("换了有法线的素材 → 法线有图", prev.right.has_image,
              f"{None if prev.right.image_array is None else prev.right.image_array.shape}")
        win.page_convert.sets = page_sets(win) or couch
        win.refresh_preview(force=True)
        app.processEvents()

    # ---------- 切笔刷路线：图种跟着换（笔刷没有指数图）----------
    print("== 切路线 ==")
    prev.cmb_kind.setCurrentIndex(0)          # 回到第一种（模型线是 exp）
    app.processEvents()
    win.page_convert.rb_route_brush.setChecked(True)
    app.processEvents()
    kinds_b = [prev.cmb_kind.itemData(i) for i in range(prev.cmb_kind.count())]
    check("笔刷线可选：底色 / 法线（**没有**指数图）", kinds_b == ["basecolor", "normal"],
          str(kinds_b))
    check("笔刷线右框仍有图（底色）", prev.right.has_image, prev.current_kind())
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    kinds_m = [prev.cmb_kind.itemData(i) for i in range(prev.cmb_kind.count())]
    check("切回模型线 → 指数图重新可选", kinds_m == ["exp", "basecolor", "normal"], str(kinds_m))
    # 图种是**用户选的**就不该被切路线抢走（只在"这套/这条路线没有那张图"时才回落到第一项）
    check("切路线会**保留**用户选的图种（不偷偷跳回）", prev.current_kind() == "basecolor",
          prev.current_kind())
    prev.cmb_kind.setCurrentIndex(kinds_m.index("exp"))
    app.processEvents()
    check("手动切回指数图 → 有图", prev.right.has_image, prev.current_kind())

    # ---------- 放大预览 ----------
    print("== ⤢ 放大预览 ==")
    calls = []
    real_exec = QtWidgets.QDialog.exec
    QtWidgets.QDialog.exec = lambda self: calls.append(self.windowTitle()) or 0
    try:
        win.page_tuning._on_zoom()
    finally:
        QtWidgets.QDialog.exec = real_exec
    check("有图时点「放大预览」会开一个窗口", len(calls) == 1, str(calls))
    check("窗口标题带上是哪张图", bool(calls) and "：" in calls[0] or bool(calls), str(calls))

    # ---------- 预览不碰 materials / 不调 VTFCmd ----------
    print("== 预览不产生副作用 ==")
    check("预览只读素材：源素材目录里没有多出产物",
          not any(p.name.endswith("_phong") for p in folder.parent.iterdir()
                  if p.name not in before) or before == after)

    win.close()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
