"""S4 的 4 大拉条 + 曲线编辑器（离屏跑）。

对应 `_task/07-S3+S4-预览与拉条.md` §3.2 / §3.4 与验收判据 3、5：
  · **跟着模式走**：模型 4 根 = 锐度/粗糙度偏移/高光强度/金属染色；
    笔刷 4 根 = 锐度/粗糙度偏移/反射强度/反射染色 —— 切模式时**后两根换名**
  · 每根拖了都要**真的产出覆盖项**（"摆一根拖不动的条比不放更糟"）
  · **中点 = 不干预**（不动滑杆就不该凭空多出覆盖项）
  · 曲线编辑器能改东西（拖控制点 → `curve.curve_points` → 产物跟着变）
  · 笔刷线 **AO 不是拉条**（明暗交给 lightmap）

「旋钮真的改变产物」由 `test_neutral_params.py` 负责（那边有逐位一致的哈希锁）。

跑法：python tests/test_sliders.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-sliders-")

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
sys.path.insert(0, str(ROOT))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from gui.main import MainWindow  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def press(curve, x, y):
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(x, y),
                           QtCore.Qt.LeftButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    curve.mousePressEvent(ev)


def move(curve, x, y):
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(x, y),
                           QtCore.Qt.NoButton, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    curve.mouseMoveEvent(ev)


def release(curve, x, y):
    ev = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonRelease, QtCore.QPointF(x, y),
                           QtCore.Qt.LeftButton, QtCore.Qt.NoButton, QtCore.Qt.NoModifier)
    curve.mouseReleaseEvent(ev)


def main() -> int:
    print("== S4 四大拉条 + 曲线编辑器（离屏）==")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow()
    win.resize(1280, 760)
    win.show()
    app.processEvents()
    panel = win.page_tuning.panel
    cfg = win.page_config
    folder = WS / "测试素材" / "合成素材"
    check("合成素材存在", folder.is_dir(), str(folder))
    if not folder.is_dir():
        return 1
    win.page_convert.load_folder(folder)
    app.processEvents()

    # ---------- ① 模型线 4 根 ----------
    print("== 模型线：4 根 + 跟模式走 ==")
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    model_on = [r.isVisibleTo(panel) for r in panel.mode_rows["model"]]
    brush_on = [r.isVisibleTo(panel) for r in panel.mode_rows["brush"]]
    check("后两根 = 高光强度 / 金属染色（都可见）", all(model_on) and not any(brush_on),
          f"model={model_on} brush={brush_on}")
    check("前两根（锐度 / 粗糙度偏移）两模式通用，始终可见",
          panel.sl_sharp.isVisibleTo(panel) and panel.sl_offset.isVisibleTo(panel))
    check("模型线里 AO 那一行也在（它不是拉条，但模型线能调）",
          panel.row_ao.isVisibleTo(panel))
    check("第 3 根标签 = 高光强度", "高光" in panel.param_rows["boost"][0].text(),
          panel.param_rows["boost"][0].text())
    check("第 4 根标签 = 金属染色强度", "金属染色" in panel.param_rows["tint"][0].text(),
          panel.param_rows["tint"][0].text())

    # ---------- ② 中点 = 不干预 ----------
    print("== 中点 = 不干预 ==")
    cfg.reset_overrides()
    app.processEvents()
    check("四根都在中点时**没有**任何覆盖项", cfg.current_overrides() == {},
          str(cfg.current_overrides()))

    # ---------- ③ 每根拖了都真产出覆盖项 ----------
    print("== 每根拖了都产出覆盖项 ==")
    cases = [("sl_offset", 80, "curve.roughness_offset"),
             ("sl_sharp", 20, "curve.sharpness_gain"),
             ("sl_boost", 90, "vmt.$phongboost"),
             ("sl_tint", 15, "curve.metal_tint")]
    for attr, value, key in cases:
        cfg.reset_overrides()
        app.processEvents()
        ctrl = getattr(panel, attr)
        ctrl.setValue(value)
        cfg.refresh_sources()
        app.processEvents()
        ov = cfg.current_overrides()
        check(f"{attr} 拖到 {value} → 产出 {key}", key in ov, str(ov.get(key, "<没有>")))
    cfg.reset_overrides()
    app.processEvents()

    # ---------- ④ 参数表里得看得见这几根（"当前值 + 来源"是这个项目的核心）----------
    print("== 参数表看得见 ==")
    keys = [cfg.src_table.item(r, 0).text() for r in range(cfg.src_table.rowCount())]
    for key in ("curve.roughness_offset", "curve.metal_tint", "curve.envmap_gain"):
        check(f"参数表里有 {key}", key in keys, str(keys))
    panel.sl_offset.setValue(80)
    cfg.refresh_sources()
    rows = {cfg.src_table.item(r, 0).text(): cfg.src_table.item(r, 2).text()
            for r in range(cfg.src_table.rowCount())}
    check("拖过之后来源标成「你改过」", rows.get("curve.roughness_offset") == "你改过",
          str(rows.get("curve.roughness_offset")))
    cfg.reset_overrides()
    app.processEvents()

    # ---------- ⑤ 笔刷线：后两根换名，且 AO 不再是拉条 ----------
    print("== 笔刷线 ==")
    win.page_convert.rb_route_brush.setChecked(True)
    app.processEvents()
    model_on = [r.isVisibleTo(panel) for r in panel.mode_rows["model"]]
    brush_on = [r.isVisibleTo(panel) for r in panel.mode_rows["brush"]]
    check("后两根换成 反射强度 / 反射染色", all(brush_on) and not any(model_on),
          f"model={model_on} brush={brush_on}")
    check("笔刷线里 AO 那一行藏起来（笔刷明暗交给 lightmap）",
          not panel.row_ao.isVisibleTo(panel))
    check("笔刷线第 3 根标签 = 反射强度", "反射强度" in panel.param_rows["refl"][0].text(),
          panel.param_rows["refl"][0].text())
    check("笔刷线第 4 根标签 = 反射染色", "反射染色" in panel.param_rows["envtint"][0].text(),
          panel.param_rows["envtint"][0].text())
    cfg.reset_overrides()
    app.processEvents()
    panel.sl_refl.setValue(75)
    panel.sl_envtint.setValue(25)
    cfg.refresh_sources()
    app.processEvents()
    ov = cfg.current_overrides()
    check("反射强度 → curve.envmap_gain", "curve.envmap_gain" in ov, str(ov.get("curve.envmap_gain")))
    check("反射染色 → vmt.$envmaptint（且不是 [1 1 1]）",
          "vmt.$envmaptint" in ov and ov["vmt.$envmaptint"] != "[1 1 1]",
          str(ov.get("vmt.$envmaptint")))
    cfg.reset_overrides()
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()

    # ---------- ⑥ 曲线编辑器 ----------
    print("== 曲线编辑器 ==")
    curve = panel.curve
    check("默认是直线（= 没有自定义曲线 → 与改动前逐位一致）",
          curve.curve_points() == [] and curve.is_identity(), str(curve.curve_points()))
    rect = curve._rect()
    cx = rect.left() + rect.width() * 0.5          # 中间那个控制点
    press(curve, cx, rect.bottom())
    move(curve, cx, rect.top() + rect.height() * 0.25)
    release(curve, cx, rect.top() + rect.height() * 0.25)
    app.processEvents()
    pts = curve.curve_points()
    check("拖了控制点 → 产出了曲线控制点", len(pts) == 5, str(pts))
    ov = cfg.current_overrides()
    check("曲线进覆盖项 curve.curve_points", "curve.curve_points" in ov, str(ov.get("curve.curve_points")))
    check("曲线不再是直线", not curve.is_identity())
    mid_y = dict((round(x, 3), y) for x, y in pts).get(0.5)
    check("拖上去的正是中间那个点（y 变大）", mid_y is not None and mid_y > 0.5, str(mid_y))
    curve.reset()
    app.processEvents()
    check("「重置曲线」把它拨回直线", curve.curve_points() == [] and curve.is_identity())
    check("重置后覆盖项里没有 curve.curve_points",
          "curve.curve_points" not in cfg.current_overrides())

    # ---------- ⑦ 预览跟着变（曲线改了 → 右框重算）----------
    print("== 曲线改了预览也变 ==")
    import numpy as np
    img0 = np.array(win.page_tuning.preview.right.image_array)
    press(curve, cx, rect.bottom())
    move(curve, cx, rect.top() + rect.height() * 0.1)
    release(curve, cx, rect.top() + rect.height() * 0.1)
    app.processEvents()
    img1 = np.array(win.page_tuning.preview.right.image_array)
    check("曲线拖动并松手后 → 右框重算了（像素变了）", img0.shape == img1.shape
          and bool((img0 != img1).any()), f"{img0.shape} → {img1.shape}")
    cfg.reset_overrides()
    app.processEvents()

    win.close()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
