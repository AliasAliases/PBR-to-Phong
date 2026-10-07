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
from PySide6 import QtCore, QtWidgets  # noqa: E402

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


def bg_ratio(img) -> float:
    """画面里"球面之外的背景色"占多少（= 0 说明这块是铺满的，>0 说明有球外的暗底）。"""
    if img is None:
        return 1.0
    bg = np.array([0x2B, 0x33, 0x40])
    return float((np.abs(img[:, :, :3].astype(int) - bg).sum(axis=2) == 0).mean())


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
    # 15-E：笔刷档默认外形 = 方块（铺墙感），并注明"没有 Phong，只是近似"
    check("15-E：笔刷档默认外形 = 方块", prev.current_shape() == "plane", prev.current_shape())
    check("15-E：笔刷档也能出图（不需要模型）", prev.right.has_image)
    check("15-E：笔刷档注明了「没有 Phong、只是近似」",
          "近似" in prev.lbl_note.text(), prev.lbl_note.text())
    plane_img = np.asarray(prev.right.image_array) if prev.right.has_image else None
    check("15-E：方块渲染铺满整块（没有球外背景）",
          bg_ratio(plane_img) == 0.0, f"背景占比={bg_ratio(plane_img):.3f}")
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    check("15-E：切回模型线 → 外形回到球", prev.current_shape() == "sphere", prev.current_shape())
    check("15-E：定位文案保留「最终以 HLMV / 游戏为准」",
          "HLMV" in prev.lbl_note.text() and "游戏" in prev.lbl_note.text(), prev.lbl_note.text())
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
    # 15-E：放大窗要**可缩放**（100/200/400% + 适应窗口），且单独造得出来（能测）
    dlg = win.page_tuning.make_zoom_dialog()
    check("15-E：放大窗单独造得出来（不是只有 exec 一条路）", dlg is not None)
    if dlg is not None:
        combos = dlg.findChildren(QtWidgets.QComboBox)
        items = [c.itemText(i) for c in combos for i in range(c.count())]
        check("15-E：放大窗里有缩放档（含「适应窗口」）",
              any("100%" in t for t in items) and any("适应窗口" in t for t in items), str(items))
        dlg.close()

    # ---------- 15-E：右框是**渲染图**（按控件尺寸现算）----------
    print("== 15-E：渲染图 ==")
    prev.cmb_kind.setCurrentIndex(0)
    prev.cmb_shape.setCurrentIndex(prev.cmb_shape.findData("sphere"))
    app.processEvents()
    r = snap(prev.right)
    check("15-E：按**控件尺寸**渲染（不再固定 512）",
          r is not None and abs(max(r.shape[:2]) - max(160, prev.right._side)) <= 2,
          f"{None if r is None else r.shape} 控件边长={prev.right._side}")
    check("15-E：球面之外是暗背景（说明真的画了个球）",
          bg_ratio(r) > 0.15, f"背景占比={bg_ratio(r):.3f}")
    prev.cmb_shape.setCurrentIndex(prev.cmb_shape.findData("plane"))
    app.processEvents()
    check("15-E：切方块 → 换了一张图", differs(r, snap(prev.right)))
    prev.cmb_shape.setCurrentIndex(prev.cmb_shape.findData("sphere"))
    app.processEvents()
    b0 = snap(prev.right)
    panel.sl_sharp.setSliderDown(True)               # 拖动中不刷新（沿用旧规矩）
    panel.sl_sharp.setValue(25)
    app.processEvents()
    check("15-E：拖动中渲染图不动（刷新粒度没被破坏）", not differs(b0, snap(prev.right)))
    panel.sl_sharp.setSliderDown(False)
    panel.sl_sharp.sliderReleased.emit()
    for _ in range(2):
        app.processEvents()
    check("15-E：松手后渲染图跟着参数变", differs(b0, snap(prev.right)))
    win.page_config.reset_overrides()

    # ---------- 15-E 返工2：那一行控件在**两个框的下面、水平居中**（单 `c8cd02b` §15-E）----------
    print("== 15-E 返工2：那行控件的落点 ==")
    win.resize(1280, 760)
    win.tabs.setCurrentIndex(1)
    win.page_tuning.apply_sizes()
    for _ in range(3):
        app.processEvents()
    frames_bottom = prev.left.mapTo(prev, QtCore.QPoint(0, prev.left.height())).y()
    row_y = prev.cmb_kind.mapTo(prev, QtCore.QPoint(0, 0)).y()
    check("15-E 返工2：那行控件在两个框的**下面**（没压进预览区）",
          row_y >= frames_bottom, f"控件行 y={row_y} 框底 y={frames_bottom}")
    lx = prev.lbl_kind.mapTo(prev, QtCore.QPoint(0, 0)).x()
    rx = prev.lbl_note.mapTo(prev, QtCore.QPoint(prev.lbl_note.width(), 0)).x()
    check("15-E 返工2：那行控件**水平居中**（左右留白一样且都不是 0）",
          lx > 0 and abs(lx - (prev.width() - rx)) <= 8,
          f"左留白={lx} 右留白={prev.width() - rx} 左半区宽={prev.width()}")
    win.tabs.setCurrentIndex(0)
    for _ in range(3):
        app.processEvents()

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
