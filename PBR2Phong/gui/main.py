"""PBR2Phong 的 GUI（PySide6）—— **5 页版式**（`_task/06-版式落地.md`）。

版式的**唯一参照物 = `GUI測試/假GUI/`**（`假GUI.py` + `假GUI文案.py`，用户 2026-09-27 点头过）。
本文件只负责"把假 GUI 的版式搬进来、把功能接上真逻辑"——**版式不自己发挥**。
对应关系（假 GUI 的零件 → 这里的实现）：
    第 1 页 `page_convert`       → `ConvertPage`（工具路径 / 选择模式 / 导入素材 / 命名）
    第 2 页 `page_preview`(A 版)  → `TuningPage` + `PreviewArea` + `ParamPanel`
    第 3 页 `page_config`        → `ConfigPage`（参数表 / 材质属性 / 自由键值）
    第 4 页 `page_export`        → `ExportPage`
    第 5 页 `page_about`         → `AboutPage`
    `PreviewBox` / 行高 21 的参数表 / 灰色小字解释（17px）都是照它搬的。

硬约束（06 §4，违反即返工）：
    · **零滚动**：不许用 `QScrollArea`；放不下就缩预览框
    · 窗口默认 **1280×760**、最小 **1200×680**（`setMinimumSize` 写死）
    · **参数行标签与控件同行**；常驻解释用灰字
    · 第 2 / 3 页**不许有 `setCheckable(True)` 的 `QGroupBox`**（用户原话：
      「我都说了不要把材质属性和调参模式收起来了，后面预览要实时观测的啊」）
    · 拖滑杆**只更新数值**、**松手才重算**（统一挂 `ParamPanel._on_slider_released`）
    · 中英双语、**不许漏出原始 i18n 键名**

设计准则（用户拍板，实施计划 §0）：交互设计占七成；能拖就别让人点；参数与报错都说人话；
每个参数 = 直译标签 + 一句**常驻**人话解释（中英都要有）。

⚠️ 假 GUI 上有、**正式版一律不许出现**（06 §5.5）：版式切换控件 / 第 2 页的「模式」下拉 /
页内「第 N 页 · ×××」标题 / 假界面横幅 / 那套"占位色块·拉条只改数字"的假行为。
"""

from __future__ import annotations

import math
import os
import sys
import subprocess
import threading
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402
from core import (curves, imaging, pack, phong, pipeline, settings, source_io,  # noqa: E402
                  validate as validate_mod, vtf)

# 预览图的显示上限（长边）：**只用于显示**，转换产物不受影响。
# 显示用不着原始分辨率，而且每帧对 4K 原图做 resize 会把预览拖到几十毫秒（POC 阶段实测差 20 倍）。
PREVIEW_MAX_SIDE = 512

APP_VERSION = "0.1.0-dev"

# 06 §4.2：默认 1280×760、最小 1200×680（假 GUI 同款）
WINDOW_SIZE = (1280, 760)
WINDOW_MIN = (1200, 680)
# 假 GUI：本机 Qt 默认字号偏大，第 2 页要塞下预览 + 参数，统一压到 12px
UI_FONT_PX = 12

# 常驻解释（灰字）的统一样式。⚠️ 11 片：高度**不再钉死**（钉死 + 不换行会把超宽文案无声切掉），
# `DESC_H` 改成"最少一行"的高度，由布局按需给到两行。
UI_DESC = "color:#6b7280; font-size:11px;"
UI_TODO = "color:#8a5a00; font-size:11px;"
UI_NOTE = "color:#8a9aac;"
DESC_H = 17

# 第 2 页「观感旋钮」= 那 7 根滑杆（素材级微调）：`_baseline_ctrl` / `current_overrides()`
# / 11 片的"切路线保住用户值"都按这一组算，只此一处定义。
KNOB_KEYS = ("sharpness", "boost", "ao", "offset", "tint", "refl", "envtint")

# 材质属性里可选的表面类型（官方 L4D2 VMT 里常见的值；下拉给非程序员用）
SURFACEPROPS = ("default", "plastic", "metal", "metal_box", "wood", "wood_panel", "concrete",
                "brick", "glass", "tile", "cardboard", "cloth", "dirt", "grass", "sand",
                "rubber", "wetconcrete")

# 常用开关（顺序与假 GUI 一致）
FLAG_KEYS = ("$nocull", "$translucent", "$alphatest", "$nodecal", "$halflambert")


def slider_to_boost(v: float) -> float:
    """滑杆 0..100 → `$phongboost` 0.1..100（对数手感：官方从角色 1.5 到武器 60 跨两个数量级）。"""
    return round(0.1 * (1000.0 ** (float(v) / 100.0)), 3)


def boost_to_slider(b: float) -> int:
    b = min(max(float(b), 0.1), 100.0)
    return int(round(math.log(b / 0.1) / math.log(1000.0) * 100))


# 参数行的"来源"标签配色：**按层配色**（不看文字 → 中英一致；10 片起不再拿中文字面量当键）
SOURCE_COLORS = {settings.SOURCE_KIND_GLOBAL: "#6b7280",
                 settings.SOURCE_KIND_PRESET: "#2563eb",
                 settings.SOURCE_KIND_OVERRIDE: "#b45309"}


def src_color(kind: str) -> str:
    return SOURCE_COLORS.get(kind, SOURCE_COLORS[settings.SOURCE_KIND_GLOBAL])


def hline() -> QtWidgets.QFrame:
    f = QtWidgets.QFrame()
    f.setFrameShape(QtWidgets.QFrame.HLine)
    f.setFrameShadow(QtWidgets.QFrame.Sunken)
    return f


def qimage_from_array(arr) -> QtGui.QImage:
    """uint8 的 HxW / HxWx3 / HxWx4 → `QImage`（RGBA8888）。

    ⚠️ 末尾必须 `.copy()`：`QImage` 只是**引用**那块内存，numpy 数组一被回收，
    显示的就是花屏/崩溃（POC 阶段踩过同类坑：Tk 那边是 `PhotoImage` 得留引用）。
    """
    a = np.ascontiguousarray(arr)
    if a.ndim == 2:
        a = np.dstack([a, a, a])
    if a.shape[2] == 3:
        a = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
    h, w = a.shape[:2]
    return QtGui.QImage(a.data, w, h, 4 * w, QtGui.QImage.Format_RGBA8888).copy()


# ────────────────────────── 版式零件（照假 GUI 搬） ──────────────────────────
class PreviewBox(QtWidgets.QWidget):
    """预览框：保持 1:1，左右两框同尺寸，放不下就缩（零滚动的核心手法）。

    ⚠️ 三个坑叠在一起，缺一个都做不到"页面放不下时能压下去"（假 GUI 踩过，照抄它的解法）：
      ① 不能用 `setFixedSize` —— 它把 `minimumSize` 顶死，布局再也压不动；
      ② 竖直 size policy 必须 `Ignored` —— 用 Maximum/Preferred 时 Qt 会把 sizeHint
         当**硬最小值**，页面最小高度会被顶上去；
      ③ 最小尺寸要显式压到 140 —— 否则画布 + 底部文字的最小值会一路往上涨。
    """

    MIN_SIDE = 140

    def __init__(self, caption: str = ""):
        super().__init__()
        self.caption = caption
        self.placeholder = ""          # 空框里那行字**必须走 i18n**（英文界面不许有中文）
        self._side = 246
        self._arr = None               # 要显示的图（uint8，最多 512 边 —— 见 MainWindow._preview_array）
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.canvas = QtWidgets.QLabel()
        self.canvas.setAlignment(QtCore.Qt.AlignCenter)
        self.canvas.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.canvas.setStyleSheet(
            "background:#3a4756;color:#d8e2ee;font-size:15px;border:1px solid #7a8a9c;")
        self.canvas.setWordWrap(True)
        self.canvas.setMinimumSize(1, 1)
        self.foot = QtWidgets.QLabel()
        self.foot.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(self.foot)
        self.set_side(self._side)

    def hasHeightForWidth(self) -> bool:      # noqa: N802 —— Qt 的 C++ 虚函数名
        return True

    def heightForWidth(self, w: int) -> int:  # noqa: N802
        return w + 24                          # 1:1 + 底部那行尺寸文字

    def resizeEvent(self, ev):                # noqa: N802
        super().resizeEvent(ev)
        self._render()                        # 框变大小 → 重新按新尺寸缩放显示

    def set_caption(self, caption: str):
        self.caption = caption
        self._render()

    def set_placeholder(self, text: str):
        self.placeholder = text
        self._render()

    def set_image(self, arr):
        """接真图（uint8 的 HxWx3 / HxWx4）。给 `None` = 退回占位文字。"""
        self._arr = arr
        self._render()

    @property
    def has_image(self) -> bool:
        return self._arr is not None

    @property
    def image_array(self):
        return self._arr

    def _render(self):
        """把图按 KeepAspectRatio 缩放居中显示；没有图就显示占位文字。

        ⚠️ 缩放只作用在**已经降采样过的小图**上（`MainWindow._preview_array` 最多 512 边）——
        每帧对 4K 原图做 resize 会把预览拖到几十毫秒（POC 阶段实测差 20 倍）。
        """
        if self._arr is None:
            self.canvas.setPixmap(QtGui.QPixmap())          # 先清掉旧图，免得文字和图叠着
            self.canvas.setText(f"{self.caption}\n\n{self.placeholder}" if self.placeholder
                                else self.caption)
            self.foot.setText(f"{self.caption} {self._side}×{self._side}")
            return
        pix = QtGui.QPixmap.fromImage(qimage_from_array(self._arr))
        box = self.canvas.size()
        if box.width() > 2 and box.height() > 2:
            pix = pix.scaled(box, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self.canvas.setText("")
        self.canvas.setPixmap(pix)
        h, w = self._arr.shape[:2]
        self.foot.setText(f"{self.caption} {w}×{h}")

    def set_side(self, px: int):
        px = max(self.MIN_SIDE, int(px))
        self._side = px
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Ignored)
        self.setMinimumSize(self.MIN_SIDE, self.MIN_SIDE + 24)
        self.setMaximumSize(16777215, 16777215)     # 上不封顶，让布局给多少算多少
        self._render()
        self.updateGeometry()


class PathRow(QtWidgets.QWidget):
    """一行：标签 + 只读路径框 + 「浏览…」按钮（假 GUI 的 `fixed_path_row`）。"""

    def __init__(self, label_width: int = 150):
        super().__init__()
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setMinimumWidth(label_width)
        self.ed = QtWidgets.QLineEdit()
        self.btn = QtWidgets.QPushButton()
        self.btn.setFixedWidth(76)
        h.addWidget(self.lbl)
        h.addWidget(self.ed, 1)
        h.addWidget(self.btn)


class ConvertPage(QtWidgets.QWidget):
    """① 转换页（假 GUI `page_convert` 的版式）。

    从上到下：**工具路径（HLMV + VTFCmd）** + **选择模式**（并排两格）→ **导入素材**（拖框 +
    识别结果 + 逐套表格）→ **命名（决定材质路径）**（拖入 `.mdl` 自动读 + 两栏 + 校验模型）。
    """

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.sets: list = []
        self.folder = None                  # 选了哪个素材文件夹（没选时 set_output 要用）
        self._model_names: list = []        # 从 .mdl 读出来的材质名
        self._model_cdm = ""

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        # ---- 工具路径 + 选择模式：并排两格（假 GUI 的 3:2 分栏）----
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        # ⚠️ HLMV 有硬规格：`Popen` 脱离式、**不捕获输出、不等待、不加 `-screenshot`**
        #    （见 `_task/02-HLMV按钮.md` §3/§4）。
        self.grp_paths = QtWidgets.QGroupBox()
        pv = QtWidgets.QVBoxLayout(self.grp_paths)
        pv.setSpacing(6)
        row_hlmv = PathRow()
        self.lbl_hlmv, self.ed_hlmv, self.btn_hlmv_pick = row_hlmv.lbl, row_hlmv.ed, row_hlmv.btn
        self.ed_hlmv.textChanged.connect(self.refresh_hlmv_hint)
        self.btn_hlmv_pick.clicked.connect(self.pick_hlmv)
        self.btn_hlmv_run = QtWidgets.QPushButton()
        self.btn_hlmv_run.clicked.connect(self.run_hlmv)
        row_hlmv.layout().addWidget(self.btn_hlmv_run)
        pv.addWidget(row_hlmv)
        self.lbl_hlmv_hint = QtWidgets.QLabel()
        self.lbl_hlmv_hint.setWordWrap(True)
        pv.addWidget(self.lbl_hlmv_hint)
        self.lbl_hlmv_desc = QtWidgets.QLabel()
        self.lbl_hlmv_desc.setWordWrap(True)
        pv.addWidget(self.lbl_hlmv_desc)

        row_tool = PathRow()
        self.lbl_tools, self.ed_vtfcmd, self.btn_vtfcmd = row_tool.lbl, row_tool.ed, row_tool.btn
        self.btn_vtfcmd.clicked.connect(self.pick_vtfcmd)
        self.ed_vtfcmd.textChanged.connect(self.refresh_vtfcmd_hint)
        pv.addWidget(row_tool)
        self.lbl_vtfcmd = QtWidgets.QLabel()
        self.lbl_vtfcmd.setWordWrap(True)
        pv.addWidget(self.lbl_vtfcmd)
        pv.addStretch(1)
        grid.addWidget(self.grp_paths, 0, 0)

        # ---- 选择模式：模型（VertexLitGeneric + Phong）还是笔刷（LightmappedGeneric）----
        # 规格见 `_task/01-笔刷模式.md`：L4D2 的笔刷**没有 Phong**，出底色 + 法线（+ 可选反射遮罩），
        # 明暗靠 lightmap，材质在 Hammer 的材质浏览器里直接选（不需要 .mdl）。
        self.grp_route = QtWidgets.QGroupBox()
        rt = QtWidgets.QVBoxLayout(self.grp_route)
        rt.setSpacing(6)
        self.rb_route_model = QtWidgets.QRadioButton()
        self.rb_route_brush = QtWidgets.QRadioButton()
        self.rb_route_model.setChecked(True)
        rt.addWidget(self.rb_route_model)
        rt.addWidget(self.rb_route_brush)
        self.chk_brush_mask = QtWidgets.QCheckBox()
        self.chk_brush_mask.setChecked(True)           # v1 范围含遮罩 → 默认勾上
        self.chk_brush_mask.setEnabled(False)          # 只有笔刷路线才有意义
        rt.addWidget(self.chk_brush_mask)
        self.lbl_route_hint = QtWidgets.QLabel()
        self.lbl_route_hint.setWordWrap(True)
        rt.addWidget(self.lbl_route_hint)
        rt.addStretch(1)
        grid.addWidget(self.grp_route, 0, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        lay.addLayout(grid)

        # ---- 导入素材（拖框 + 识别结果 + 逐套表格）----
        self.grp_import = QtWidgets.QGroupBox()
        vi = QtWidgets.QVBoxLayout(self.grp_import)
        vi.setSpacing(6)
        drop_row = QtWidgets.QHBoxLayout()
        self.drop = QtWidgets.QLabel()
        self.drop.setAlignment(QtCore.Qt.AlignCenter)
        self.drop.setMinimumHeight(56)
        self.drop.setAcceptDrops(True)
        self.drop.installEventFilter(self)
        self.drop.setStyleSheet(
            "border:2px dashed #8a9aac;border-radius:6px;color:#5b6b7c;background:#f2f5f8;")
        self.btn_choose = QtWidgets.QPushButton()
        self.btn_choose.clicked.connect(self.choose_folder)
        drop_row.addWidget(self.drop, 1)
        drop_row.addWidget(self.btn_choose)
        vi.addLayout(drop_row)
        self.lbl_recognized = QtWidgets.QLabel()
        self.lbl_recognized.setStyleSheet("color:#1c6b2f;")
        vi.addWidget(self.lbl_recognized)

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        vi.addWidget(self.table, 1)
        lay.addWidget(self.grp_import, 1)

        # ---- 命名（决定材质路径）：拖入 .mdl 自动读，没有就两栏手填 + 实时显示最终路径 ----
        self.grp_naming = QtWidgets.QGroupBox()
        nv = QtWidgets.QVBoxLayout(self.grp_naming)
        rb_row = QtWidgets.QHBoxLayout()
        self.rb_model = QtWidgets.QRadioButton()
        self.rb_manual = QtWidgets.QRadioButton()
        self.rb_model.setChecked(True)
        rb_row.addWidget(self.rb_model)
        rb_row.addWidget(self.rb_manual)
        rb_row.addStretch(1)
        nv.addLayout(rb_row)

        self.naming_stack = QtWidgets.QStackedWidget()
        # A：读 .mdl
        page_a = QtWidgets.QWidget()
        va = QtWidgets.QVBoxLayout(page_a)
        va.setContentsMargins(0, 0, 0, 0)
        ar = QtWidgets.QHBoxLayout()
        self.ed_model = QtWidgets.QLineEdit()
        self.btn_model = QtWidgets.QPushButton()
        self.btn_model.clicked.connect(self.pick_model)
        ar.addWidget(self.ed_model, 1)
        ar.addWidget(self.btn_model)
        self.btn_validate = QtWidgets.QPushButton()
        self.btn_validate.clicked.connect(self.check_model)
        ar.addWidget(self.btn_validate)
        va.addLayout(ar)
        self.lbl_model_hint = QtWidgets.QLabel()
        self.lbl_model_hint.setWordWrap(True)
        # 13-B：材质名要能**选中复制** —— 多材质模型"跑两次"时，用户得把名字逐个抄到下一次里，
        #       不该逼他再去别处翻 .mdl（`实施计划.md` §5.5.1：信息只存一处）
        self.lbl_model_hint.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        va.addWidget(self.lbl_model_hint)
        # B：手填两栏
        page_b = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(page_b)
        form.setContentsMargins(0, 0, 0, 0)
        self.lbl_cdm = QtWidgets.QLabel()
        self.ed_cdm = QtWidgets.QLineEdit("custom")
        self.lbl_mat = QtWidgets.QLabel()
        self.ed_mat = QtWidgets.QLineEdit()
        form.addRow(self.lbl_cdm, self.ed_cdm)
        form.addRow(self.lbl_mat, self.ed_mat)
        self.naming_stack.addWidget(page_a)
        self.naming_stack.addWidget(page_b)
        nv.addWidget(self.naming_stack)
        self.lbl_final_path = QtWidgets.QLabel()
        f = self.lbl_final_path.font()
        f.setBold(True)
        self.lbl_final_path.setFont(f)
        nv.addWidget(self.lbl_final_path)
        self.lbl_naming_hint = QtWidgets.QLabel()
        self.lbl_naming_hint.setWordWrap(True)
        nv.addWidget(self.lbl_naming_hint)
        lay.addWidget(self.grp_naming)

        self.rb_model.toggled.connect(self._on_mode_changed)
        self.rb_route_model.toggled.connect(self._on_route_changed)
        self.ed_cdm.textChanged.connect(self.refresh_path)
        self.ed_mat.textChanged.connect(self.refresh_path)
        self.ed_model.textChanged.connect(lambda _t: self.read_model(quiet=True))

    # -- 拖放 ----------------------------------------------------------
    def eventFilter(self, obj, ev):          # noqa: N802 —— Qt 的 C++ 虚函数名
        if obj is self.drop:
            if ev.type() == QtCore.QEvent.DragEnter and ev.mimeData().hasUrls():
                ev.acceptProposedAction()
                return True
            if ev.type() == QtCore.QEvent.Drop:
                for url in ev.mimeData().urls():
                    p = Path(url.toLocalFile())
                    if p.is_dir():
                        self.load_folder(p)
                        break
                    # 「能拖就别点」：模型也支持拖进来（用户的动作 = 拖素材夹 + 拖 .mdl）
                    if p.is_file() and p.suffix.lower() == ".mdl":
                        self.rb_model.setChecked(True)
                        self.ed_model.setText(str(p))
                        self.read_model()
                        self.win.log_key("scan.dropped_model", name=p.name)
                        break
                return True
        return super().eventFilter(obj, ev)

    # -- 动作 ----------------------------------------------------------
    def choose_folder(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, self.win.t("btn.choose_folder"))
        if d:
            self.load_folder(Path(d))

    def load_folder(self, folder: Path):
        self.folder = folder
        try:
            self.sets = source_io.scan_folder(folder)
        except Exception as e:  # noqa: BLE001 —— 读不了也不能崩，说人话
            self.sets = []
            QtWidgets.QMessageBox.warning(self, self.win.t("app.title"),
                                          self.win.t("err.empty_folder", path=f"{folder}\n\n{e}"))
            return
        self.table.setRowCount(len(self.sets))
        for i, ms in enumerate(self.sets):
            got = ms.summary()
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(ms.group))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(self.win.t("status.ready")))
            self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(""))
            self.table.setItem(i, 3, QtWidgets.QTableWidgetItem(got))
        self.win.set_recognized(len(self.sets))
        if self.sets:
            self.win.log_key("scan.done", n=len(self.sets))
            if hasattr(self.win, "page_tuning"):          # 导入完 → 预览接上真图
                self.win.refresh_preview(force=True)
        else:
            # ⚠️ 这里是用户**第一个动作**就会撞到的地方：拖错文件夹（比如拖了上一级）时
            #    原来只把标签变回"还没有选择素材"，看起来像拖拽功能坏了 —— 必须明说没认到。
            self.win.log_key("scan.none")
            QtWidgets.QMessageBox.information(self, self.win.t("app.title"),
                                              self.win.t("err.empty_folder", path=str(folder)))

    # -- 命名 ----------------------------------------------------------
    def pick_model(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.win.t("naming.model_path"), "", "Source model (*.mdl)")
        if p:
            self.ed_model.setText(p)
            self.read_model()

    def read_model(self, quiet=False):
        """读 .mdl 拿权威的 $cdmaterials 与材质名（编译后就冻在里面了）。"""
        path = Path(self.ed_model.text().strip())
        if not path.is_file():
            if not quiet:
                self.lbl_model_hint.setText(
                    self.win.t("naming.read_fail", why=path.name or "—"))
            return None
        try:
            cdm, names, _mdl = pipeline.names_from_model(path)
        except Exception as e:  # noqa: BLE001
            self.lbl_model_hint.setText(self.win.t("naming.read_fail", why=e))
            return None
        text = self.win.t("naming.read_ok", cdm=cdm or "—", names="、".join(names) or "—")
        if len(names) >= 2:
            # 13-B：多材质模型 —— 把"一次只配一套贴图、这几个名字要分几次跑"说在名字旁边
            text += "\n" + self.win.t("naming.multi_materials", n=len(names))
        self.lbl_model_hint.setText(text)
        self._model_names = names
        self._model_cdm = cdm
        self.refresh_path()
        return names

    def _on_mode_changed(self):
        self.naming_stack.setCurrentIndex(0 if self.rb_model.isChecked() else 1)
        self.refresh_path()

    def _on_route_changed(self):
        """切路线：只有笔刷才谈得上"出不出反射遮罩"；切回模型时禁用（但保留勾选状态）。"""
        brush = self.rb_route_brush.isChecked()
        self.chk_brush_mask.setEnabled(brush)
        self.lbl_route_hint.setText(self.win.t("route.hint_brush" if brush else "route.hint_model"))
        if hasattr(self.win, "page_tuning"):               # 换路线 → 出图种类也换（指数图只有模型线有）
            self.win.page_tuning.panel.apply_route("brush" if brush else "model")   # 后两根换名
            if hasattr(self.win, "page_config"):           # 预设也换一套（模型 11 档 ↔ 笔刷 9+1 档）
                self.win.page_config.on_route_changed("brush" if brush else "model")
            self.win.refresh_preview(force=True)

    def current_route(self) -> tuple:
        """返回 (路线, 要不要笔刷遮罩)：("model"|"brush", bool)。"""
        brush = self.rb_route_brush.isChecked()
        return ("brush" if brush else "model"), bool(brush and self.chk_brush_mask.isChecked())

    # ---- 模型浏览器（HLMV）------------------------------------------------
    def hlmv_path(self) -> tuple:
        """返回 (hlmv.exe 路径 or ""，来源种类)。来源种类见 `settings.resolve_hlmv_path`。"""
        return settings.resolve_hlmv_path(self.ed_hlmv.text().strip(),
                                          pipeline.DEFAULT_MATERIALS.parent.parent)

    def default_hlmv(self) -> str:
        return settings.default_hlmv_path(pipeline.DEFAULT_MATERIALS.parent.parent)

    def refresh_hlmv_hint(self, *_a):
        path, kind = self.hlmv_path()
        self.lbl_hlmv_hint.setText(
            self.win.t(f"hlmv.hint_{kind}", path=path or self.default_hlmv()))

    def pick_hlmv(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.win.t("hlmv.label"), "", "HLMV (hlmv.exe);;exe (*.exe)")
        if p:
            self.ed_hlmv.setText(p)

    def run_hlmv(self):
        """起 HLMV 看当前模型。

        ⚠️ 施工单 `_task/02` §3/§4 的硬规格：`Popen` 脱离式启动，**不捕获输出、不等待、
        不加 `-screenshot`**（早先"HLMV 一律 exit=1"就是等待式/捕获式调用造成的假象）。
        """
        mdl = Path(self.ed_model.text().strip())
        exe, kind = self.hlmv_path()
        if kind == "missing":
            QtWidgets.QMessageBox.information(
                self, self.win.t("app.title"),
                self.win.t("hlmv.hint_missing", path=self.default_hlmv()))
            return
        if not mdl.is_file():
            QtWidgets.QMessageBox.information(self, self.win.t("app.title"),
                                              self.win.t("hlmv.no_model"))
            return
        try:
            subprocess.Popen([exe, str(mdl)])        # 故意不接 stdout/stderr、不 wait
        except OSError as e:                         # 起不来就说人话
            QtWidgets.QMessageBox.warning(self, self.win.t("app.title"),
                                          self.win.t("hlmv.failed", why=e))
            return
        self.win.log_key("hlmv.started", name=mdl.name)

    # ---- 工具路径：VTFCmd（PNG → VTF）----
    def pick_vtfcmd(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.win.t("settings.vtfcmd"), "", "VTFCmd (VTFCmd.exe)")
        if p:
            self.ed_vtfcmd.setText(p)

    def current_vtfcmd(self) -> str:
        """用户指定的；没指定就自动找（找不到返回空串）。"""
        text = self.ed_vtfcmd.text().strip()
        if text:
            return text
        found = vtf.find_vtfcmd()
        return str(found) if found else ""

    def refresh_vtfcmd_hint(self, *_a):
        path = self.current_vtfcmd()
        self.lbl_vtfcmd.setText(self.win.t("settings.vtfcmd_found", path=path) if path
                                else self.win.t("settings.vtfcmd_missing"))

    def refresh_path(self):
        cdm, name, _names = self.current_naming()
        rel = f"{cdm.strip('/')}/{name}" if cdm.strip("/") else name
        self.lbl_final_path.setText(self.win.t("naming.final_path", path=rel or "—"))
        self.win.set_output(None)

    def current_naming(self) -> tuple:
        """返回 (cdmaterials, 贴图基名, [材质名...])。"""
        names = getattr(self, "_model_names", None) or []
        if self.rb_model.isChecked():
            cdm = getattr(self, "_model_cdm", "") or ""
            base = self.ed_mat.text().strip() or (names[0] if names else "")
            return cdm, base, names
        cdm = self.ed_cdm.text().strip()
        name = self.ed_mat.text().strip()
        return cdm, name, ([name] if name else [])

    def check_model(self):
        """「校验模型」：拿编译好的 .mdl 当权威，查产物位置 / 贴图存在 / 大小写 / 未赋材质面。"""
        path = Path(self.ed_model.text().strip())
        if not path.is_file():
            QtWidgets.QMessageBox.information(self, self.win.t("app.title"),
                                              self.win.t("validate.need_model"))
            return
        try:
            rep = validate_mod.validate_model(path, self.win.materials_root)
        except Exception as e:  # noqa: BLE001
            QtWidgets.QMessageBox.warning(self, self.win.t("app.title"), str(e))
            return
        hard = [f for f in rep.findings if f.level == "拒绝"]
        if not rep.findings:
            body = self.win.t("validate.ok")
        else:
            body = self.win.t("validate.problems", n=len(rep.findings)) + "\n\n" + \
                   "\n".join(f"  · {f}" for f in rep.findings)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(self.win.t("validate.done"))
        box.setText(f"{path.name}\n$cdmaterials = {rep.cdmaterials}   材质 = {rep.textures}\n\n{body}")
        box.setIcon(QtWidgets.QMessageBox.Critical if hard else
                    (QtWidgets.QMessageBox.Warning if rep.findings else
                     QtWidgets.QMessageBox.Information))
        box.exec()

    def retranslate(self):
        self.grp_paths.setTitle(self.win.t("paths.title"))
        self.win.t_into(self.lbl_hlmv, "hlmv.label")
        self.win.t_into(self.btn_hlmv_pick, "naming.browse")
        self.win.t_into(self.btn_hlmv_run, "hlmv.run")
        self.win.t_into(self.lbl_hlmv_desc, "hlmv.run_desc")
        self.refresh_hlmv_hint()
        self.win.t_into(self.lbl_tools, "settings.vtfcmd")
        self.win.t_into(self.btn_vtfcmd, "naming.browse")
        self.ed_vtfcmd.setPlaceholderText(self.win.t("settings.vtfcmd"))
        self.refresh_vtfcmd_hint()

        self.grp_route.setTitle(self.win.t("route.title"))
        self.win.t_into(self.rb_route_model, "route.model")
        self.win.t_into(self.rb_route_brush, "route.brush")
        self.win.t_into(self.chk_brush_mask, "route.mask")
        self.lbl_route_hint.setText(self.win.t(
            "route.hint_brush" if self.rb_route_brush.isChecked() else "route.hint_model"))

        self.grp_import.setTitle(self.win.t("import.title"))
        self.drop.setText(self.win.t("drop.hint"))
        self.win.t_into(self.btn_choose, "btn.choose_folder")

        self.grp_naming.setTitle(self.win.t("naming.title"))
        self.rb_model.setText(self.win.t("naming.mode_model"))
        self.rb_manual.setText(self.win.t("naming.mode_manual"))
        self.win.t_into(self.btn_model, "naming.browse")
        self.win.t_into(self.lbl_model_hint, "naming.auto_hint")
        self.win.t_into(self.btn_validate, "btn.validate")
        self.win.t_into(self.lbl_cdm, "naming.cdmaterials")
        self.win.t_into(self.lbl_mat, "naming.material_name")
        self.win.t_into(self.lbl_naming_hint, "naming.manual_hint")
        self.table.setHorizontalHeaderLabels([
            self.win.t("table.material"), self.win.t("table.status"),
            self.win.t("table.progress"), self.win.t("table.note")])
        self.win.set_recognized(len(self.sets))
        self.refresh_path()


class PreviewArea(QtWidgets.QWidget):
    """② 预览区：**两个独立大框**（左＝源素材，右＝产出成品），同尺寸、保持 1:1。

    ⚠️ 右框的重算**只挂在 `ParamPanel._on_slider_released`**（别另接一套 `valueChanged`）：
    拖动时只更新数值，松手才重算（用户 2026-09-27 拍板的刷新粒度）。
    ⚠️ 只做**贴图本体的对比**，不是带光照的 3D 渲染（δ 渲染器无排期）。
    """

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setMinimumSize(120, 144)        # 预览可压到 120：否则它会把页面最小高度顶上去
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        h = QtWidgets.QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        self.left = PreviewBox()
        self.right = PreviewBox()
        h.addWidget(self.left, 1)
        h.addWidget(self.right, 1)
        v.addLayout(h, 1)
        kind_row = QtWidgets.QHBoxLayout()
        kind_row.setContentsMargins(0, 0, 0, 0)
        self.lbl_kind = QtWidgets.QLabel()
        self.cmb_kind = QtWidgets.QComboBox()
        self.cmb_kind.currentIndexChanged.connect(self._on_kind_changed)
        kind_row.addWidget(self.lbl_kind)
        kind_row.addWidget(self.cmb_kind)
        kind_row.addStretch(1)
        v.addLayout(kind_row)

    # ---- 真图 ----
    def set_kinds(self, kinds: list, current: str = ""):
        """右框能看哪几张图（模型路线 = 指数/底色/法线；笔刷路线 = 底色/法线）。"""
        self.cmb_kind.blockSignals(True)
        self.cmb_kind.clear()
        for kind in kinds:
            self.cmb_kind.addItem(self.win.t(f"preview.kind_{kind}"), kind)
        idx = self.cmb_kind.findData(current)
        self.cmb_kind.setCurrentIndex(max(0, idx))
        self.cmb_kind.blockSignals(False)

    def current_kind(self) -> str:
        return self.cmb_kind.currentData() or "basecolor"

    def _on_kind_changed(self, *_a):
        self.win.refresh_preview(force=True)

    def set_images(self, src, out, src_name: str = "", out_name: str = ""):
        self.left.set_image(src)
        self.right.set_image(out)
        if src_name:
            self.left.set_caption(src_name)
        if out_name:
            self.right.set_caption(out_name)

    def set_side(self, px: int):
        for box in (self.left, self.right):
            box.set_side(px)

    def retranslate(self):
        if self.left.has_image:
            self.cmb_kind.blockSignals(True)
            for i in range(self.cmb_kind.count()):
                kind = self.cmb_kind.itemData(i)
                self.cmb_kind.setItemText(i, self.win.t(f"preview.kind_{kind}"))
            self.cmb_kind.blockSignals(False)
        else:
            self.left.set_caption(self.win.t("preview.src"))
            self.right.set_caption(self.win.t("preview.out"))
            for box in (self.left, self.right):
                box.set_placeholder(self.win.t("preview.need_import"))
        self.win.t_into(self.lbl_kind, "preview.kind")


class CurveEditor(QtWidgets.QWidget):
    """粗糙度映射的曲线编辑器（07 §3.4）：在 0..1 的方框里**上下拖控制点**改映射形状。

    它改的是"粗糙度 → 指数"那条映射**在既有公式之前**的形状（`r' = LUT(r)`），
    由 `core/curves.py` 的 `lut_from_points` / `apply_lut` 算，**不动既有公式与常数**。

    · 控制点 x 固定（0 / .25 / .5 / .75 / 1），只让上下拖 —— 少一个自由度，不容易拖乱。
    · 拖动中只重画；**松手才发 `changed`**（与拉条同一套"拖动只更新、松手才重算"）。
    · 双击 = 恢复直线（= 没有自定义曲线 = 与改动前逐位一致）。
    """

    changed = QtCore.Signal()
    HEIGHT = 92
    N = 5

    def __init__(self):
        super().__init__()
        self.points: list = []          # [(x, y), ...]；空 = 直线
        self._drag = None
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(150)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setStyleSheet("background:#f2f5f8;border:1px solid #8a9aac;")

    # ---- 数据 ----
    def set_points(self, points):
        self.points = [(float(x), float(y)) for x, y in (points or [])]
        self.update()

    def curve_points(self) -> list:
        """要写进覆盖项的 `curve.curve_points`（**直线 = 空列表**，不留多余覆盖项）。"""
        if not self.points or self.is_identity():
            return []
        return [[round(x, 4), round(y, 4)] for x, y in self.points]

    def is_identity(self) -> bool:
        return all(abs(y - x) < 0.01 for x, y in self._effective())

    def reset(self):
        self.points = []
        self.update()
        self.changed.emit()

    def _identity(self) -> list:
        return [(i / (self.N - 1), i / (self.N - 1)) for i in range(self.N)]

    def _effective(self) -> list:
        return self.points if self.points else self._identity()

    # ---- 画 ----
    def _rect(self):
        pad = 8
        return QtCore.QRectF(pad, pad, max(1, self.width() - 2 * pad),
                             max(1, self.height() - 2 * pad))

    def paintEvent(self, ev):          # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self._rect()
        p.fillRect(self.rect(), QtGui.QColor("#f2f5f8"))
        p.setPen(QtGui.QPen(QtGui.QColor("#c9d4de"), 1, QtCore.Qt.DotLine))
        for i in range(1, 4):
            x = rect.left() + rect.width() * i / 4.0
            p.drawLine(QtCore.QPointF(x, rect.top()), QtCore.QPointF(x, rect.bottom()))
            y = rect.top() + rect.height() * i / 4.0
            p.drawLine(QtCore.QPointF(rect.left(), y), QtCore.QPointF(rect.right(), y))
        lut = curves.lut_from_points(self._effective(), 64)
        path = QtGui.QPainterPath()
        for i, v in enumerate(lut):
            x = rect.left() + rect.width() * i / float(len(lut) - 1)
            y = rect.bottom() - rect.height() * float(v)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        p.setPen(QtGui.QPen(QtGui.QColor("#2563eb"), 2))
        p.drawPath(path)
        for x, y in self._effective():
            c = QtCore.QPointF(rect.left() + rect.width() * x,
                               rect.bottom() - rect.height() * y)
            held = self._drag is not None and abs(self._drag[0] - x) < 1e-6
            p.setBrush(QtGui.QColor("#b45309" if held else "#ffffff"))
            p.setPen(QtGui.QPen(QtGui.QColor("#b45309"), 2))
            p.drawEllipse(c, 4.5, 4.5)

    # ---- 鼠标 ----
    def _nearest_x(self, pos_x: float):
        rect = self._rect()
        best = None
        for x, _y in self._effective():
            cx = rect.left() + rect.width() * x
            if best is None or abs(cx - pos_x) < abs(best[1] - pos_x):
                best = (x, cx)
        return best[0] if best else None

    def _y_at(self, pos_y: float) -> float:
        rect = self._rect()
        return float(np.clip((rect.bottom() - pos_y) / rect.height(), 0.0, 1.0))

    def _move_to(self, pos):
        if self._drag is None:
            return
        x0 = self._drag
        y = self._y_at(pos.y())
        self.points = [(x, (y if abs(x - x0) < 1e-6 else yy))
                       for x, yy in self._effective()]
        self._drag = x0

    def mousePressEvent(self, ev):     # noqa: N802
        self._drag = self._nearest_x(ev.position().x())
        self._move_to(ev.position())
        self.update()

    def mouseMoveEvent(self, ev):      # noqa: N802
        if self._drag is not None:
            self._move_to(ev.position())
            self.update()

    def mouseReleaseEvent(self, ev):   # noqa: N802
        if self._drag is not None:
            self._move_to(ev.position())
            self._drag = None
            self.update()
            self.changed.emit()        # ⚠️ **松手才生效**（同拉条的刷新粒度）

    def mouseDoubleClickEvent(self, ev):   # noqa: N802
        self.reset()


def envtint_from_slider(v: int) -> str:
    """「反射染色」滑杆 0..100 → `$envmaptint "[r g b]"`。

    左 = 冷（偏蓝）、**中间 50 = `[1 1 1]` 不干预**、右 = 暖·亮。
    """
    t = (float(v) - 50.0) / 50.0
    r = 1.0 + t * (0.25 if t >= 0 else -0.2)
    g = 1.0 + t * (0.15 if t >= 0 else -0.1)
    b = 1.0 + t * (-0.15 if t >= 0 else 0.2)
    return "[%s %s %s]" % tuple(f"{x:g}" for x in (r, g, b))


def slider_from_envtint(text: str) -> int:
    """`$envmaptint "[r g b]"` → 滑杆位置（拿 R 反推）。认不出来就当"不干预"= 50。"""
    try:
        nums = [float(x) for x in str(text).strip().strip("[]").replace(",", " ").split()]
        r = nums[0]
    except (ValueError, IndexError):
        return 50
    return int(round(50 + np.clip((r - 1.0) / (0.25 if r >= 1.0 else 0.2), -1.0, 1.0) * 50))


class ParamPanel(QtWidgets.QWidget):
    """② 右侧参数列（假 GUI A 版：预览在左、参数竖排在右，**固定 440px**）。

    版式要点（06 §4.3）：**标签与控件同行**，常驻解释用灰字钉死 17px；
    「其他参数」那一组把三根条的子行做成一行的"标签 + 滑杆 + 跟手数值" + 一行解释。
    """

    PANEL_W = 440

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.param_rows: dict = {}
        self.lbl_values: dict = {}
        self._baseline_ctrl: dict = {}
        self.setFixedWidth(self.PANEL_W)

        g = QtWidgets.QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(2)

        # ① 预设行（下拉 + 保存为预设）+ 常驻解释
        self.lbl_preset = QtWidgets.QLabel()
        self.cmb_preset = QtWidgets.QComboBox()
        # ⚠️ 13-F：**键与显示名要分开** —— 这里先按原名填（`itemData` = 中文原名），
        #    显示名由 `refresh_preset_texts()` 在 retranslate 时按语言换。
        #    踩过：原来这里 `addItems(...)` 没有 itemData → 英文下 `currentData()` 取不到键、
        #    回退到显示名 "Character · Body" 去 resolve → 直接 KeyError。
        for _n in phong.PRESETS:
            self.cmb_preset.addItem(_n, _n)
        self.btn_save_preset = QtWidgets.QPushButton()
        self.btn_save_preset.setMaximumHeight(26)
        self.btn_save_preset.clicked.connect(lambda: self.win.page_config.save_current_preset())
        g.addWidget(self.lbl_preset, 0, 0)
        g.addWidget(self.cmb_preset, 0, 1, 1, 2)
        g.addWidget(self.btn_save_preset, 0, 3)
        self.lbl_preset_desc = self._desc()
        g.addWidget(self.lbl_preset_desc, 1, 0, 1, 4)

        # ② 高光锐度（傻瓜模式唯一参数，永远可见）
        self.lbl_sharp = self._bold()
        self.sl_sharp = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sl_sharp.setRange(0, 100)
        self.sl_sharp.setValue(50)
        self.lbl_sharp_val = self._readout()
        self.lbl_sharp_desc = self._desc()
        g.addWidget(self.lbl_sharp, 2, 0)
        g.addWidget(self.sl_sharp, 2, 1, 1, 2)
        g.addWidget(self.lbl_sharp_val, 2, 3)
        g.addWidget(self.lbl_sharp_desc, 3, 0, 1, 4)
        self.param_rows["sharpness"] = (self.lbl_sharp, self.sl_sharp, self.lbl_sharp_desc)
        self.lbl_values["sharpness"] = self.lbl_sharp_val

        # 4 个快速档位：不想调滑杆的直接点一个
        steps = QtWidgets.QWidget()
        sh = QtWidgets.QHBoxLayout(steps)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(6)
        self.lbl_steps = QtWidgets.QLabel()
        sh.addWidget(self.lbl_steps)
        self.step_buttons = {}
        for name, gain in curves.SHARPNESS_STEPS.items():
            btn = QtWidgets.QPushButton(name)
            btn.setMaximumHeight(24)
            btn.clicked.connect(lambda _checked=False, gg=gain: self._apply_step(gg))
            sh.addWidget(btn)
            self.step_buttons[name] = btn
        sh.addStretch(1)
        g.addWidget(steps, 4, 0, 1, 4)

        # ③ **4 大拉条 + 曲线**（原「调参模式」的折叠已按用户要求拆掉 → 常驻展开）
        #    07 §3.2：**跟着模式走** —— 模型 4 根 = 锐度 / 粗糙度偏移 / 高光强度 / 金属染色；
        #    笔刷 4 根 = 锐度 / 粗糙度偏移 / 反射强度 / 反射染色。**前两根两模式通用。**
        self.grp_other = QtWidgets.QGroupBox()
        ov = QtWidgets.QVBoxLayout(self.grp_other)
        ov.setContentsMargins(6, 1, 6, 1)
        ov.setSpacing(1)

        def _slider(value=50):
            s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            s.setRange(0, 100)
            s.setValue(value)
            return s

        # 通用第 2 根：粗糙度整体偏移（50 = 不干预）
        # ⚠️ 11 片返工：这里原来还有 `self.lbl_offset_desc = self._desc()` 一类**孤儿标签** ——
        #    解释由 `_param_line()` 内部另造一个并进布局（`param_rows[key][2]`），那 6 个
        #    从没进过任何布局，却**骗过两次测量**（10 片的假警报、11 片的量法）→ 已删。
        self.sl_offset = _slider()
        self.lbl_offset_val = self._readout()
        ov.addWidget(self._param_line("offset", self.sl_offset, self.lbl_offset_val))

        # 跟着模式换的后两根
        self.sl_boost = _slider()
        self.lbl_boost_val = self._readout()
        row_boost = self._param_line("boost", self.sl_boost, self.lbl_boost_val)
        self.sl_tint = _slider()
        self.lbl_tint_val = self._readout()
        row_tint = self._param_line("tint", self.sl_tint, self.lbl_tint_val)
        self.sl_refl = _slider()
        self.lbl_refl_val = self._readout()
        row_refl = self._param_line("refl", self.sl_refl, self.lbl_refl_val)
        self.sl_envtint = _slider()
        self.lbl_envtint_val = self._readout()
        row_envtint = self._param_line("envtint", self.sl_envtint, self.lbl_envtint_val)
        for row in (row_boost, row_tint, row_refl, row_envtint):
            ov.addWidget(row)
        self.mode_rows = {"model": [row_boost, row_tint],
                          "brush": [row_refl, row_envtint]}

        # 环境光遮蔽：**模型线专属**（笔刷线故意不把 AO 烘进底色，明暗交给 lightmap）
        self.sl_ao = _slider()
        self.lbl_ao_val = self._readout()
        self.row_ao = self._param_line("ao", self.sl_ao, self.lbl_ao_val)
        ov.addWidget(self.row_ao)

        # 曲线编辑器（原来是摆一句"还没做"的空壳，本片做成真的）
        self.lbl_curve = self._bold()
        self.lbl_curve_todo = QtWidgets.QLabel()      # 复用：改成放"怎么用"的说明
        self.lbl_curve_todo.setStyleSheet(UI_DESC)
        self.lbl_curve_todo.setWordWrap(True)         # 11 片：同 `_desc()` —— 定高会把英文切掉
        self.lbl_curve_todo.setMinimumHeight(DESC_H)
        self.lbl_curve_desc = self._desc()
        self.curve = CurveEditor()
        self.btn_curve_reset = QtWidgets.QPushButton()
        self.btn_curve_reset.setMaximumHeight(22)
        self.btn_curve_reset.clicked.connect(self.curve.reset)
        curve_holder = QtWidgets.QWidget()
        ch = QtWidgets.QVBoxLayout(curve_holder)
        ch.setContentsMargins(0, 1, 0, 1)
        ch.setSpacing(1)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.lbl_curve)
        head.addStretch(1)
        head.addWidget(self.btn_curve_reset)
        ch.addLayout(head)
        ch.addWidget(self.curve)
        ch.addWidget(self.lbl_curve_desc)
        ch.addWidget(self.lbl_curve_todo)
        self.param_rows["curve"] = (self.lbl_curve, self.curve, self.lbl_curve_desc)
        ov.addWidget(curve_holder)
        # 08 单附带项①：常驻说清"哪几根只改 vmt、所以预览不会变"（tooltip 不算"界面上有"）
        self.lbl_vmt_only = QtWidgets.QLabel()
        self.lbl_vmt_only.setStyleSheet(UI_TODO)
        self.lbl_vmt_only.setWordWrap(True)
        ov.addWidget(self.lbl_vmt_only)
        g.addWidget(self.grp_other, 5, 0, 1, 4)

        g.setRowStretch(6, 1)
        g.setColumnStretch(1, 1)

        # 刷新粒度（06 §4.5 / 07 §3.1）：**拖动只更新数值、松手才重算**。
        # 连接放在所有 setValue 之后 —— 否则构造期的 setValue 会回调到还没建好的页面。
        for key, ctrl in (("sharpness", self.sl_sharp), ("boost", self.sl_boost),
                          ("ao", self.sl_ao), ("offset", self.sl_offset),
                          ("tint", self.sl_tint), ("refl", self.sl_refl),
                          ("envtint", self.sl_envtint)):
            ctrl.valueChanged.connect(lambda _v, k=key: self._on_slider_value(k))
            ctrl.sliderReleased.connect(self._on_slider_released)
        self.curve.changed.connect(self._on_slider_released)
        self.apply_route("model")

    # ---- 跟着模式走 ----
    def apply_route(self, route: str):
        """切模式时把"后两根"换掉（前两根 + 曲线两模式通用；AO 只在模型线）。"""
        route = "brush" if route == "brush" else "model"
        for key, rows in self.mode_rows.items():
            for row in rows:
                row.setVisible(key == route)
        self.row_ao.setVisible(route == "model")

    # ---- 小工具 ----
    def _bold(self) -> QtWidgets.QLabel:
        lab = QtWidgets.QLabel()
        f = lab.font()
        f.setBold(True)
        lab.setFont(f)
        return lab

    def _desc(self) -> QtWidgets.QLabel:
        """一行灰字解释（**可换行**，最少留一行的高度）。

        ⚠️ 11 片改：原来这里是 `setFixedHeight(17)` + 不换行 → 文本超宽会被**无声切掉、
        连省略号都没有**。实测（1200×680 / 1280×760，切页后量）：中文一条都不切，
        **英文切 7 条** —— `preset_desc` 490>440、`curve_desc` 551>422、`curve_howto` 735>422、
        `boost` 472>422、`offset` 484>422、`tint` 782>422、`attr.surfaceprop_desc` 1365>816。
        现在改成"自动换行 + 最小一行高"，由布局按需给到两行（英文最长的那几条正好两行）。
        """
        lab = QtWidgets.QLabel()
        lab.setStyleSheet(UI_DESC)
        lab.setWordWrap(True)
        lab.setMinimumHeight(DESC_H)
        return lab

    def _readout(self) -> QtWidgets.QLabel:
        lab = QtWidgets.QLabel()
        lab.setFixedWidth(44)
        lab.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        return lab

    def _param_line(self, key: str, slider, readout, todo=None, desc=None) -> QtWidgets.QWidget:
        """一个参数 = **[加粗标签] + [滑杆] + [跟手数值] 同行** + 一行常驻解释（灰字）。"""
        if desc is None:                     # ⚠️ 必须**先造出来再存引用** —— 否则
            desc = self._desc()              #    param_rows 里存的是 None，retranslate 会炸
        holder = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(holder)
        v.setContentsMargins(0, 1, 0, 1)
        v.setSpacing(1)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        label = self._bold()
        # 11 片：原来是 `setFixedWidth(84)` —— 中文够（"环境光遮蔽"5 字），但**英文参数名更长**
        # （Roughness Offset 115 / Specular Strength 123 / Metal Tint Strength 134 …）会被**无声切掉**
        # （截图里就是 "Roughness Offs" / "Metal Tint Str"）。改成"至少 84，长了就自己变宽"。
        label.setMinimumWidth(84)
        head.addWidget(label)
        if slider is not None:
            head.addWidget(slider, 1)
        if readout is not None:
            head.addWidget(readout)
        v.addLayout(head)
        if todo is not None:
            v.addWidget(todo)
        v.addWidget(desc)
        if key != "curve":
            self.param_rows[key] = (label, slider, desc)
            if readout is not None:
                self.lbl_values[key] = readout
        else:
            self.lbl_curve = label
        return holder

    # ---- 数值显示 / 刷新粒度 ----
    def _value_text(self, key: str) -> str:
        """滑杆当前值 → 人话（跟 `current_overrides` 用同一套换算，免得两处对不上）。"""
        ctrl = self.param_rows.get(key, (None, None, None))[1]
        if not isinstance(ctrl, QtWidgets.QSlider):
            return ""
        v = ctrl.value()
        if key == "sharpness":
            return f"{curves.sharpness_from_slider(v):.2f}"
        if key == "boost":
            return f"{slider_to_boost(v)}"
        if key == "ao":
            return f"{v}%"
        if key == "offset":
            return f"{curves.offset_from_slider(v):+.2f}"       # 带符号，一眼看出往哪偏
        if key == "tint":
            return f"{curves.tint_from_slider(v):.2f}"
        if key == "refl":
            return f"{curves.gain_from_slider(v):.2f}"
        if key == "envtint":
            return envtint_from_slider(v)
        return str(v)

    def _sync_value_label(self, key: str):
        """只给**真滑杆**刷数值 —— 曲线那一行的控件是说明文字，别被刷成空白。"""
        lbl = self.lbl_values.get(key)
        ctrl = self.param_rows.get(key, (None, None, None))[1]
        if lbl is not None and isinstance(ctrl, QtWidgets.QSlider):
            lbl.setText(self._value_text(key))

    def sync_all_values(self):
        for key in self.lbl_values:
            self._sync_value_label(key)

    def _on_slider_value(self, key: str):
        """拖动中：只把数值显示刷新掉（**不重算**）；不是拖出来的（键盘/滚轮/程序改值）
        就照旧立刻重算 —— 否则用键盘调参的人会觉得界面是死的。"""
        self._sync_value_label(key)
        ctrl = self.param_rows.get(key, (None, None, None))[1]
        if not isinstance(ctrl, QtWidgets.QSlider) or not ctrl.isSliderDown():
            self.win.page_config.refresh_sources()

    def _on_slider_released(self):
        """松手：重算一次（06 §4.5）。**S3 的右侧预览框也挂在这里**，别另接一套。"""
        self.sync_all_values()
        self.win.page_config.refresh_sources()

    def _apply_step(self, gain: float):
        self.sl_sharp.setValue(curves.slider_from_sharpness(gain))
        self.win.page_config.refresh_sources()

    def set_presets(self, names, current: str):
        """预设下拉的内容由 `ConfigPage` 统一管（它才知道配置目录里有哪些自存预设）。

        ⚠️ 13-F：**显示名 ≠ 键**。内置 21 档在英文界面下显示英文名，但 `itemData` 永远是中文原名
        （预设名是持久化数据：`phong_input.json` / `presets/*.json` 的「名称」/ `phong.PRESETS` 的键）；
        用户自存的档名一律原样显示。
        """
        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        for n in names:
            self.cmb_preset.addItem(i18n.preset_display(n, self.win.lang), n)
        idx = self.cmb_preset.findData(current)
        self.cmb_preset.setCurrentIndex(max(0, idx))
        self.cmb_preset.blockSignals(False)

    def refresh_preset_texts(self):
        """13-F：切语言时**只换下拉里的显示文字** —— 不动选中项、更不碰参数（切语言不该重置滑杆）。"""
        cmb = self.cmb_preset
        cmb.blockSignals(True)
        cur = cmb.currentData()
        for i in range(cmb.count()):
            key = cmb.itemData(i)
            if key is None:              # ⚠️ 没 data 的项**不动**（宁可不翻，也别把键翻没了）
                continue
            cmb.setItemText(i, i18n.preset_display(key, self.win.lang))
        idx = cmb.findData(cur)
        if idx >= 0:
            cmb.setCurrentIndex(idx)
        cmb.blockSignals(False)

    def retranslate(self):
        w = self.win
        w.t_into(self.lbl_preset, "settings.preset")
        w.t_into(self.btn_save_preset, "btn.save_preset")
        w.t_into(self.lbl_preset_desc, "settings.preset_desc")
        self.refresh_preset_texts()          # 13-F：预设显示名跟着语言换（内置翻、自存档不翻）
        w.t_into(self.lbl_steps, "settings.steps")
        for name, btn in self.step_buttons.items():
            btn.setText(w.t(f"step.{name}"))
        self.grp_other.setTitle(w.t("settings.mode"))
        for key in ("sharpness", "boost", "ao", "offset", "tint", "refl", "envtint", "curve"):
            info = i18n.param(key, w.lang)
            label, _ctrl, desc = self.param_rows[key]
            label.setText(info["label"])
            desc.setText(info["desc"])
        w.t_into(self.btn_curve_reset, "curve.reset")
        w.t_into(self.lbl_curve_todo, "curve.hint")
        w.t_into(self.lbl_vmt_only, "settings.vmt_only_hint")
        self.sync_all_values()


class TuningPage(QtWidgets.QWidget):
    """② 预览 + 调参（06 §3：**A 版 = 左右分栏** —— 预览在左、参数竖排在右）。

    ⚠️ 必须**子类化**并重写 `resizeEvent`：PySide6 里给实例打补丁
    `widget.resizeEvent = fn` 是无效的（虚函数在 C++ 侧分派），假 GUI 踩过这个坑。
    """

    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(16, 10, 16, 10)
        v.setSpacing(8)

        top = QtWidgets.QHBoxLayout()
        top.addStretch(1)
        self.btn_zoom = QtWidgets.QPushButton()
        self.btn_zoom.clicked.connect(self._on_zoom)
        top.addWidget(self.btn_zoom)
        v.addLayout(top)

        self.preview = PreviewArea(win)
        self.panel = ParamPanel(win)
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.preview, 1)
        holder = QtWidgets.QWidget()          # 参数列内容矮 → 竖直居中（下压会留一大片空白）
        hv = QtWidgets.QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.addStretch(1)
        hv.addWidget(self.panel)
        hv.addStretch(1)
        row.addWidget(holder)
        v.addLayout(row, 1)

    def _on_zoom(self):
        """「放大预览」：把当前右框那张图放大到一个窗口里看（本片一起做真）。"""
        box = self.preview.right if self.preview.right.has_image else self.preview.left
        arr = box.image_array
        if arr is None:
            QtWidgets.QMessageBox.information(self, self.win.t("preview.zoom_title"),
                                              self.win.t("preview.need_import"))
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"{self.win.t('preview.zoom_title')} —— {box.caption}")
        v = QtWidgets.QVBoxLayout(dlg)
        lab = QtWidgets.QLabel()
        lab.setAlignment(QtCore.Qt.AlignCenter)
        lab.setPixmap(QtGui.QPixmap.fromImage(qimage_from_array(arr)))
        scroll = QtWidgets.QScrollArea()          # ⚠️ 只在这个**弹窗**里用，页面里仍然零滚动
        scroll.setWidget(lab)
        scroll.setWidgetResizable(True)
        v.addWidget(scroll, 1)
        h, w = arr.shape[:2]
        size_lab = QtWidgets.QLabel(f"{w}×{h}")
        size_lab.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(size_lab)
        dlg.resize(min(1280, w + 80), min(900, h + 140))
        dlg.exec()

    def refresh_preview(self, force: bool = False):
        """预览接真图的总入口（真正干活的是 `MainWindow.refresh_preview`）。"""
        self.win.refresh_preview(force=force)

    def apply_sizes(self):
        """按实到尺寸算预览框边长 —— **放不下就缩预览框**（零滚动的核心手法）。

        取预览容器自己的高度来算（布局已经把它定好了），不猜任何魔法常数。
        """
        prev = self.preview
        if prev.width() <= 0 or prev.height() <= 0:
            return
        avail = max(120, prev.height() - 26)          # 减掉框底下那行尺寸文字
        side = max(120, min(avail, (max(120, prev.width()) - 10) // 2))
        prev.set_side(side)

    def resizeEvent(self, ev):                        # noqa: N802
        super().resizeEvent(ev)
        self.apply_sizes()

    def retranslate(self):
        self.win.t_into(self.btn_zoom, "preview.zoom")
        self.btn_zoom.setToolTip(self.win.t("preview.hint"))
        self.preview.retranslate()
        self.panel.retranslate()
        self.apply_sizes()


class ConfigPage(QtWidgets.QWidget):
    """③ 参数表 / 材质属性 / 自由键值（06 §2 第 3 页）。

    这三块都是**纯配置**、不需要看着预览改，所以从第 2 页拆出来 —— 假 GUI 实测：
    六段同页 → 面板最小高 832px，而 1200×680 只有 679px 可用，预览会被压成负值。

    参数模型（三层继承 / 覆盖项 / 预设）**只有这一处**是权威：滑杆在第 2 页，
    所以通过 `self.panel` 读它们。
    """

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.panel: ParamPanel | None = None      # 由 MainWindow 接上第 2 页的参数列
        self._presets: dict = {}
        self.config_root = ""

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        # ④ 参数表：参数 | 当前值 | 来源（9 行固定列 + 表下「恢复继承」）
        self.grp_param = QtWidgets.QGroupBox()
        pv = QtWidgets.QVBoxLayout(self.grp_param)
        pv.setContentsMargins(8, 4, 8, 4)
        pv.setSpacing(3)
        self.src_table = QtWidgets.QTableWidget(0, 3)
        self.src_table.verticalHeader().setVisible(False)
        self.src_table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        self.src_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents)
        self.src_table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents)
        self.src_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.src_table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.src_table.setShowGrid(False)
        self.src_table.setStyleSheet("font-size:11px;")
        self.src_table.verticalHeader().setDefaultSectionSize(21)   # 行高钉死，否则表会涨到 300px+
        pv.addWidget(self.src_table)
        self.btn_restore = QtWidgets.QPushButton()
        self.btn_restore.setMaximumHeight(26)
        self.btn_restore.clicked.connect(self.reset_overrides)
        pv.addWidget(self.btn_restore)
        v.addWidget(self.grp_param)

        two = QtWidgets.QGridLayout()
        two.setHorizontalSpacing(16)
        two.setVerticalSpacing(8)
        two.addWidget(self._build_attr(), 0, 0)
        two.addWidget(self._build_eye(), 1, 0)      # 13-E：只对「角色-眼睛」档出现（跟档走）
        two.addWidget(self._build_kv(), 0, 1)
        two.setColumnStretch(0, 1)
        two.setColumnStretch(1, 1)
        v.addLayout(two, 1)

    # ---- ⑤ 材质属性（**常驻展开**，不做折叠）----
    def _build_attr(self) -> QtWidgets.QGroupBox:
        self.grp_attr = QtWidgets.QGroupBox()
        av = QtWidgets.QVBoxLayout(self.grp_attr)
        av.setContentsMargins(8, 4, 8, 4)
        av.setSpacing(3)
        self.lbl_attr_hint = QtWidgets.QLabel()
        self.lbl_attr_hint.setWordWrap(True)
        self.lbl_attr_hint.setStyleSheet(UI_DESC)
        av.addWidget(self.lbl_attr_hint)

        sp_row = QtWidgets.QWidget()
        sl = QtWidgets.QHBoxLayout(sp_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(8)
        self.lbl_sp = QtWidgets.QLabel()
        self.cmb_sp = QtWidgets.QComboBox()
        self.cmb_sp.addItem("", "")
        for name in sorted(SURFACEPROPS):
            self.cmb_sp.addItem(name, name)      # ⚠️ addItems 不设 itemData，findData 会找不到
        self.cmb_sp.currentIndexChanged.connect(self._on_attr_changed)
        sl.addWidget(self.lbl_sp)
        sl.addWidget(self.cmb_sp, 1)
        av.addWidget(sp_row)
        self.lbl_sp_desc = QtWidgets.QLabel()
        self.lbl_sp_desc.setStyleSheet(UI_DESC)
        # 11 片：这条**原来不换行** —— 英文文案 1365px 一行放不下会被切，而且它会把
        # 本组框的最小宽顶到 1365 → 英文第 3 页横向最小需求 1745 > 可用 1196（零滚动本来就破）。
        self.lbl_sp_desc.setWordWrap(True)
        av.addWidget(self.lbl_sp_desc)

        self.lbl_toggles = QtWidgets.QLabel()
        av.addWidget(self.lbl_toggles)
        tog = QtWidgets.QWidget()
        th = QtWidgets.QHBoxLayout(tog)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(10)
        self.toggles = {}
        for key in FLAG_KEYS:
            cb = QtWidgets.QCheckBox(key)
            cb.stateChanged.connect(self._on_attr_changed)
            self.toggles[key] = cb
            th.addWidget(cb)
        th.addStretch(1)
        av.addWidget(tog)
        self.lbl_toggle_desc = QtWidgets.QLabel()
        self.lbl_toggle_desc.setWordWrap(True)
        self.lbl_toggle_desc.setStyleSheet(UI_DESC)
        av.addWidget(self.lbl_toggle_desc)

        # 09 单：材质本身要透明（alpha 裁剪）—— 挨着常用开关，**常驻可见**（不做折叠）
        cut_row = QtWidgets.QWidget()
        ch = QtWidgets.QHBoxLayout(cut_row)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(8)
        self.chk_cutout = QtWidgets.QCheckBox()
        self.chk_cutout.stateChanged.connect(self._on_attr_changed)
        ch.addWidget(self.chk_cutout)
        ch.addStretch(1)
        av.addWidget(cut_row)
        self.lbl_cutout_desc = QtWidgets.QLabel()
        self.lbl_cutout_desc.setWordWrap(True)
        self.lbl_cutout_desc.setStyleSheet(UI_DESC)
        av.addWidget(self.lbl_cutout_desc)
        av.addStretch(1)
        return self.grp_attr

    # ---- ⑤b 眼睛专用图（13-E：**只对「角色-眼睛」档出现**，跟档走、不做折叠）----
    def _build_eye(self) -> QtWidgets.QGroupBox:
        """`$Iris`（必填）/ `$AmbientOcclTexture`（选填）—— 眼睛专用图**只能用户给**：
        PBR 那几张（底色/粗糙度/金属度/法线）烘不出虹膜构图（`_task/13` §2.7③）。
        ⚠️ 不许做成"勾了才显示"：按档直接出现/消失（与"材质属性整组跟档重放"同一机制）。
        """
        self.grp_eye = QtWidgets.QGroupBox()
        ev = QtWidgets.QVBoxLayout(self.grp_eye)
        ev.setContentsMargins(8, 4, 8, 4)
        ev.setSpacing(3)
        # ⚠️ 14-E：这里**不再**单独放一行灰字提示 —— 它整块多占约 19px，在别的字体环境（CI 的英文 runner）
        #    上会把第 3 页顶出 1200×680（实测 637 > 623）。说明并进**组标题**（`eye.title`），省一行。
        row_iris = PathRow(label_width=110)
        self.lbl_iris, self.ed_iris, self.btn_iris = row_iris.lbl, row_iris.ed, row_iris.btn
        self.btn_iris.clicked.connect(lambda: self._pick_eye_image(self.ed_iris))
        self.ed_iris.textChanged.connect(self._on_attr_changed)
        ev.addWidget(row_iris)
        row_ao = PathRow(label_width=110)
        self.lbl_ao, self.ed_ao, self.btn_ao = row_ao.lbl, row_ao.ed, row_ao.btn
        self.btn_ao.clicked.connect(lambda: self._pick_eye_image(self.ed_ao))
        self.ed_ao.textChanged.connect(self._on_attr_changed)
        ev.addWidget(row_ao)
        self.grp_eye.setVisible(False)               # 默认藏起来；选到眼睛档才出现
        return self.grp_eye

    def _pick_eye_image(self, ed):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.win.t("eye.pick"), ed.text().strip(), self.win.t("eye.filter"))
        if p:
            ed.setText(p)

    def _sync_eye_rows(self):
        """13-E：眼睛专用图**跟着当前档位走**（只有「角色-眼睛」档、且模型路线才显示）。"""
        if not hasattr(self, "grp_eye"):
            return
        self.grp_eye.setVisible(self.current_preset() == "角色-眼睛" and self.route() == "model")

    # ---- ⑥ 自由键值（进阶，写给懂 VMT 的人）----
    def _build_kv(self) -> QtWidgets.QGroupBox:
        self.grp_kv = QtWidgets.QGroupBox()
        kv = QtWidgets.QVBoxLayout(self.grp_kv)
        kv.setContentsMargins(8, 4, 8, 4)
        kv.setSpacing(3)
        self.kv_table = QtWidgets.QTableWidget(0, 2)
        self.kv_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.kv_table.verticalHeader().setVisible(False)
        self.kv_table.setMaximumHeight(96)
        self.kv_table.setStyleSheet("font-size:11px;")
        kv.addWidget(self.kv_table)
        btns = QtWidgets.QWidget()
        kh = QtWidgets.QHBoxLayout(btns)
        kh.setContentsMargins(0, 0, 0, 0)
        kh.setSpacing(6)
        self.btn_add_kv = QtWidgets.QPushButton()
        self.btn_add_kv.setMaximumHeight(26)
        self.btn_add_kv.clicked.connect(lambda: self.add_kv("", ""))
        self.btn_del_kv = QtWidgets.QPushButton()
        self.btn_del_kv.setMaximumHeight(26)
        self.btn_del_kv.clicked.connect(self._remove_kv)
        kh.addWidget(self.btn_add_kv)
        kh.addWidget(self.btn_del_kv)
        kh.addStretch(1)
        kv.addWidget(btns)
        self.lbl_kv_empty = QtWidgets.QLabel()
        self.lbl_kv_empty.setStyleSheet(UI_NOTE)
        kv.addWidget(self.lbl_kv_empty)
        kv.addStretch(1)
        self.kv_table.itemChanged.connect(lambda _i: self.refresh_sources())
        return self.grp_kv

    # ---- 覆盖项（"你改过"的那些）--------------------------------------
    def _inherited(self) -> dict:
        """继承下来的值（不含任何覆盖）—— 用来判断哪些项真的"被你改过"。"""
        try:
            return settings.resolve(self.current_preset(), {}, {},
                                    getattr(self, "_presets", {})).values
        except Exception:  # noqa: BLE001
            return {}

    def replay_preset_attrs(self):
        """把「材质属性」**整组**拨回这一档的继承值：表面类型 + 5 个常用开关 + 要透明。

        10 片（`_task/10` §2.1）：预设档 = **一套完整策略**，切档就把它带的材质属性整体重放。
        ⚠️ **只动这一组** —— 滑杆 / 曲线（`curve.*`）**不跟档走**，那是用户的素材级微调
        （「恢复继承」才是把滑杆也拨回去的地方）。
        ⚠️ 全程 `blockSignals(True)`：拨回继承值**不算**「你改过」，否则切一下档就凭空多出 6 条覆盖项。
        """
        inh = self._inherited()
        self._sync_eye_rows()        # 13-E：眼睛专用图跟着档走（这一函数是"切档/切路线/启动"的必经之路）
        self.cmb_sp.blockSignals(True)
        idx = self.cmb_sp.findData(inh.get("vmt.$surfaceprop", ""))
        self.cmb_sp.setCurrentIndex(max(0, idx))
        self.cmb_sp.blockSignals(False)
        for key, cb in self.toggles.items():
            cb.blockSignals(True)
            cb.setChecked(bool(inh.get(f"vmt.{key}")))
            cb.blockSignals(False)
        # 09 单：透明裁剪开关也跟着继承（「植被」档自带 True → 切到那一档会自动勾上）
        self.chk_cutout.blockSignals(True)
        self.chk_cutout.setChecked(bool(inh.get("alpha.cutout", False)))
        self.chk_cutout.blockSignals(False)

    def _apply_inherited_to_controls(self):
        """把滑杆/开关拨回继承值（点「恢复继承」、换路线重载预设时用）。"""
        if self.panel is None:
            return
        inh = self._inherited()
        panel = self.panel
        keys = KNOB_KEYS
        for key in keys:
            panel.param_rows[key][1].blockSignals(True)
        panel.param_rows["sharpness"][1].setValue(
            curves.slider_from_sharpness(inh.get("curve.sharpness_gain", 1.0)))
        panel.param_rows["boost"][1].setValue(
            boost_to_slider(inh.get("vmt.$phongboost", 5.0)))
        panel.param_rows["ao"][1].setValue(int(round(inh.get("basecolor.ao_amount", 0.5) * 100)))
        # 4 大拉条里的另外三根（+ 笔刷那两根）—— 中点 = 不干预
        panel.param_rows["offset"][1].setValue(
            curves.slider_from_offset(inh.get("curve.roughness_offset", 0.0)))
        panel.param_rows["tint"][1].setValue(
            curves.slider_from_tint(inh.get("curve.metal_tint", 1.0)))
        panel.param_rows["refl"][1].setValue(
            curves.slider_from_gain(inh.get("curve.envmap_gain", 1.0)))
        panel.param_rows["envtint"][1].setValue(
            slider_from_envtint(inh.get("vmt.$envmaptint", "[1 1 1]")))
        for key in keys:
            panel.param_rows[key][1].blockSignals(False)
        panel.curve.set_points(inh.get("curve.curve_points") or [])
        self.replay_preset_attrs()
        # ⚠️ 滑杆是有量化的（滑杆位置 → 数值 → 滑杆位置不一定回到原位），
        #    所以"有没有被改过"要拿**滑杆位置**跟基线比，不能拿还原出来的数值跟继承值比
        #    —— 否则点一次「恢复继承」就会凭空多出一个覆盖项（踩过）。
        panel._baseline_ctrl = {
            key: panel.param_rows[key][1].value() for key in KNOB_KEYS}
        panel.sync_all_values()

    def current_overrides(self) -> dict:
        """界面上"你改过"的那些项 → 素材级覆盖字典（与继承值相同的就不算改过）。"""
        if self.panel is None:
            return {}
        panel = self.panel
        base = panel._baseline_ctrl
        ov = {}

        if panel.param_rows["sharpness"][1].value() != base.get("sharpness"):
            ov["curve.sharpness_gain"] = curves.sharpness_from_slider(
                panel.param_rows["sharpness"][1].value())
        if panel.param_rows["boost"][1].value() != base.get("boost"):
            ov["vmt.$phongboost"] = slider_to_boost(panel.param_rows["boost"][1].value())
        if panel.param_rows["ao"][1].value() != base.get("ao"):
            ov["basecolor.ao_amount"] = round(panel.param_rows["ao"][1].value() / 100.0, 3)
        # 4 大拉条里那几根"中性旋钮"（中点 = 不干预 → 不动就不产出覆盖项）
        if panel.param_rows["offset"][1].value() != base.get("offset"):
            ov["curve.roughness_offset"] = curves.offset_from_slider(
                panel.param_rows["offset"][1].value())
        if panel.param_rows["tint"][1].value() != base.get("tint"):
            ov["curve.metal_tint"] = curves.tint_from_slider(
                panel.param_rows["tint"][1].value())
        if panel.param_rows["refl"][1].value() != base.get("refl"):
            ov["curve.envmap_gain"] = curves.gain_from_slider(
                panel.param_rows["refl"][1].value())
        if panel.param_rows["envtint"][1].value() != base.get("envtint"):
            ov["vmt.$envmaptint"] = envtint_from_slider(
                panel.param_rows["envtint"][1].value())
        points = panel.curve.curve_points()      # 直线 = 空 → 不留多余覆盖项
        if points:
            ov["curve.curve_points"] = points
        # 材质属性（必填）：只在**和继承值不一样**时才产出覆盖项 —— 否则参数表会把它标成"你改过"，
        # 而它其实只是跟着预设/全局默认（08 单改"必填"时顺手修掉这个来源不准的问题）。
        inh = self._inherited()
        sp = self.cmb_sp.currentData() or ""
        if sp and sp != str(inh.get("vmt.$surfaceprop", "")):
            ov["vmt.$surfaceprop"] = sp
        # 常用开关同理（10 片 §2.1：材质属性整组跟档走之后，"勾着"很可能**就是这一档的继承值**
        # —— 那不算你改过；反过来，把这一档带来的开关**手动取消**也要说得出话（写 0））。
        for key, cb in self.toggles.items():
            want = bool(cb.isChecked())
            if want != bool(inh.get(f"vmt.{key}")):
                ov[f"vmt.{key}"] = 1 if want else 0
        # 09 单：透明裁剪 —— 只有**和继承值不同**才算"你改过"（「植被」档自带 True，
        # 切到那一档时它显示勾着，但那不是用户改的）
        cut = bool(self.chk_cutout.isChecked())
        if cut != bool(inh.get("alpha.cutout", False)):
            ov["alpha.cutout"] = cut
        for row in range(self.kv_table.rowCount()):
            item = self.kv_table.item(row, 0)
            if not (item and item.text().strip()):
                continue
            name = item.text().strip()
            if not name.startswith("vmt."):
                name = "vmt." + name
            value_item = self.kv_table.item(row, 1)
            ov[name] = value_item.text().strip() if value_item else ""
        # 13-E：眼睛专用图（虹膜必填 / 眼睛 AO 选填）—— 进了覆盖项才会进 `phong_input.json` 与指纹
        for key, ed in (("eye.iris", self.ed_iris), ("eye.ao", self.ed_ao)):
            val = ed.text().strip()
            if val and val != str(inh.get(key, "")):
                ov[key] = val
        return ov

    def reset_overrides(self):
        self.kv_table.setRowCount(0)
        for cb in self.toggles.values():
            cb.setChecked(False)
        self.cmb_sp.setCurrentIndex(0)
        self.ed_iris.clear()                  # 13-E：眼睛专用图也一起清
        self.ed_ao.clear()
        if self.panel is not None:
            self.panel.curve.reset()          # 曲线也拨回直线（它会自己触发一次重算）
        self._apply_inherited_to_controls()
        self.refresh_sources()

    def _on_attr_changed(self, *_a):
        self.refresh_sources()

    # ---- 自由键值 ----
    def add_kv(self, key: str, value: str):
        r = self.kv_table.rowCount()
        self.kv_table.insertRow(r)
        self.kv_table.setItem(r, 0, QtWidgets.QTableWidgetItem(key))
        self.kv_table.setItem(r, 1, QtWidgets.QTableWidgetItem(value))
        self._refresh_kv_empty()

    def _remove_kv(self):
        """「删除选中」**真按选中来** —— 没选中就提示"先选一行"，
        别静默删最后一行（假 GUI 为了"不选也有反应"那样做过，正式版不许，见 06 §5/§8）。"""
        rows = sorted({i.row() for i in self.kv_table.selectedIndexes()}, reverse=True)
        if not rows and self.kv_table.currentRow() >= 0:
            rows = [self.kv_table.currentRow()]
        if not rows:
            if self.kv_table.rowCount():
                QtWidgets.QMessageBox.information(self, self.win.t("app.title"),
                                                  self.win.t("attr.kv_need_select"))
            return
        for r in rows:
            self.kv_table.removeRow(r)
        self._refresh_kv_empty()
        self.refresh_sources()

    def _refresh_kv_empty(self):
        self.lbl_kv_empty.setVisible(self.kv_table.rowCount() == 0)

    # ---- 预设：内置 + 用户自己存的（放在配置目录的 presets/*.json）----
    def current_preset(self) -> str:
        """当前预设的**键**（13-F：英文界面下 `currentText()` 是显示名，键在 `itemData` 里）。"""
        if not self.panel:
            return phong.DEFAULT_PRESET
        name = self.panel.cmb_preset.currentData() or self.panel.cmb_preset.currentText()
        return name or phong.DEFAULT_PRESET

    def route(self) -> str:
        return self.win.page_convert.current_route()[0]

    def preset_names(self) -> list:
        """当前路线能用的预设 + 用户自己存的。

        ⚠️ 预设**按路线过滤**（08 单 S5）：模型档是 VLG 的 Phong 参数、笔刷档是 LMG 的，
        混在一起选会产出四不像的 VMT（比如把 $phong* 写进 LightmappedGeneric 里）。
        """
        base = phong.presets_for_route(self.route())
        return base + [n for n in self._presets if n not in base and n not in phong.PRESETS]

    def on_route_changed(self, route: str):
        """切路线 = 换一整套预设（模型的 11 档 ↔ 笔刷的 9 档 + 贴花 1）。

        ⚠️ **11 片 §2.2：切路线不动"你调过"的观感旋钮。** 原来这里只有 `reload_presets()`，
        它会连 `_apply_inherited_to_controls()` 一起跑 → 滑杆 / 曲线被拨回**新档的继承值**，
        用户辛苦调的那几根全没了。现在改成：**先记下你动过的那几根 → 重放新档继承值 →
        再把你的值盖回去**。

        ⚠️ 只盖**真的动过**的（滑杆位置 ≠ 继承基线），没动过的**跟着新档走** —— 反过来做的话，
        界面显示的是旧值、真正产出的是新档继承值（**假控件**），来源列也会凭空多出「你改过」。
        曲线点（`curve.curve_points`）同理：有就保住，没有就让新档说了算。
        """
        touched = self._touched_controls()
        self.reload_presets()                      # 内含 `_apply_inherited_to_controls`（新档继承值 + 重放材质属性）
        self._put_back_touched(touched)

    def _touched_controls(self) -> dict:
        """用户**真的动过**的观感旋钮（滑杆位置 ≠ 继承基线）+ 曲线点；切路线时用来保住它们。"""
        if self.panel is None:
            return {}
        panel = self.panel
        base = panel._baseline_ctrl or {}
        out = {key: panel.param_rows[key][1].value() for key in KNOB_KEYS
               if base and panel.param_rows[key][1].value() != base.get(key)}
        points = panel.curve.curve_points()
        if points:
            out["curve_points"] = points
        return out

    def _put_back_touched(self, touched: dict):
        """把上一步记下的用户值盖回控件（`blockSignals`，免得又被当成"刚改过"）。"""
        if self.panel is None or not touched:
            return
        panel = self.panel
        for key in KNOB_KEYS:
            if key in touched:
                sl = panel.param_rows[key][1]
                sl.blockSignals(True)
                sl.setValue(int(touched[key]))
                sl.blockSignals(False)
        if "curve_points" in touched:
            panel.curve.set_points(touched["curve_points"])
        panel.sync_all_values()

    def _on_preset_changed(self, name: str):
        """切预设：顺手把这一档建议的「给笔刷出反射遮罩」勾上/去掉，再重算。

        例：玻璃·窗户 官方 15/16 都开 envmap → 这档默认勾；贴花不反光 → 这档默认不勾。
        """
        # ⚠️ 13-F：这个回调收到的是**显示名**（英文界面下是 "Glass · Window"）→
        #    查 `phong.PRESETS` 必须换回**键**（`itemData`），否则英文界面下这条提示会失效。
        key = self.panel.cmb_preset.currentData() or name if self.panel else name
        hint = (phong.PRESETS.get(key) or {}).get("brush_mask")
        chk = self.win.page_convert.chk_brush_mask
        if hint is not None and chk.isEnabled():
            chk.setChecked(bool(hint))
        # 10 片（`_task/10` §2.1）：切档 = 把这一档的**材质属性整组**重放一遍
        # （表面类型 + 5 个常用开关 + 要透明）。⚠️ 滑杆 / 曲线不跟档走 —— 它们是素材级微调。
        self.replay_preset_attrs()
        self.refresh_sources()

    def reload_presets(self, keep: str = ""):
        self._presets = settings.load_presets(self.config_root) if self.config_root else {}
        cur = keep or self.current_preset()
        names = self.preset_names()
        if self.panel is not None:
            self.panel.set_presets(names, cur)
            if not getattr(self, "_preset_sig_wired", False):
                # 只接一次：每次 reload 都接会攒出一堆重复回调（切一下预设算好几遍）
                self.panel.cmb_preset.currentTextChanged.connect(self._on_preset_changed)
                self._preset_sig_wired = True
        self._apply_inherited_to_controls()
        self.refresh_sources()

    def save_current_preset(self):
        """把**当前生效的全部参数**存成一套命名预设（存整套，不存差异 —— 自包含更好懂）。"""
        name, ok = QtWidgets.QInputDialog.getText(
            self, self.win.t("btn.save_preset"), self.win.t("preset.name_prompt"))
        if not (ok and str(name).strip()):
            return
        name = str(name).strip()
        r = settings.resolve(self.current_preset(), self.current_overrides(), {}, self._presets)
        try:
            settings.save_preset(self.config_root, name, r.values,
                                 desc=self.win.t("settings.saved_preset_desc"))
        except OSError as e:
            QtWidgets.QMessageBox.warning(self, self.win.t("btn.save_preset"), str(e))
            return
        self.reload_presets(keep=name)
        self.win.log_key("preset.saved", name=name)

    def _source_text(self, r, key: str) -> str:
        """「来源」列的显示文字（10 片：走 i18n —— core 只给"层"，措辞由界面定）。

        ⚠️ 13-F：`src.preset` 里带的预设名 —— **内置 21 档翻成英文**（`i18n.preset_display`），
        并和**用户自存档**分开说（`src.preset` / `src.preset_custom`）；
        自存的档名原样显示（那是用户的数据，不能替他翻译）。
        """
        kind = r.source_kind(key)
        if kind == settings.SOURCE_KIND_PRESET:
            name = r.preset_name
            builtin = i18n.preset_is_builtin(name)
            return self.win.t("src.preset" if builtin else "src.preset_custom",
                              name=i18n.preset_display(name, self.win.lang))
        if kind == settings.SOURCE_KIND_OVERRIDE:
            return self.win.t("src.override")
        return self.win.t("src.global")

    def refresh_sources(self):
        """参数表：每行 = **参数 | 当前值 | 来源**（来源带配色）。行高与总高都钉死。"""
        if self.panel is not None:
            self.panel.sync_all_values()
        r = settings.resolve(self.current_preset(), self.current_overrides(), {},
                             getattr(self, "_presets", {}))
        keys = ["mask_carrier", "use_exponent_texture", "vmt.$phongboost",
                "vmt.$phongfresnelranges", "vmt.$surfaceprop", "basecolor.ao_amount",
                "basecolor.darken_metal", "normal.flip_green", "curve.sharpness_gain",
                # 07 S4 新增的三根中性旋钮 —— 拖了它们就得在"当前值 + 来源"里看得见
                "curve.roughness_offset", "curve.metal_tint", "curve.envmap_gain",
                # 10 片：透明裁剪开关也在这一页 —— 勾了它就该在"来源"里看见「你改过」
                "alpha.cutout"]
        keys = [k for k in keys if k in r.values or r.values.get(k) is not None]
        rows = len(keys)
        self.src_table.setRowCount(rows)
        for i, k in enumerate(keys):
            kind = r.source_kind(k)
            self.src_table.setItem(i, 0, QtWidgets.QTableWidgetItem(k))
            self.src_table.setItem(i, 1, QtWidgets.QTableWidgetItem(str(r.values.get(k))))
            item = QtWidgets.QTableWidgetItem(self._source_text(r, k))
            item.setForeground(QtGui.QColor(src_color(kind)))
            self.src_table.setItem(i, 2, item)
        # 总高钉死（多留一行），否则表下的「恢复继承」会压住最后一行（假 GUI 实测）
        self.src_table.setFixedHeight(
            self.src_table.horizontalHeader().height() + 21 * rows + 2)
        # 参数一变就顺手把预览重算掉 —— 这里**不是拖动路径**（拖动只在松手时走到这儿），
        # 所以刷新粒度天然正确；没变的话 `refresh_preview` 内部有缓存，不会白算。
        if hasattr(self.win, "page_tuning"):
            self.win.refresh_preview()

    # ---- 兼容旧引用：滑杆这些东西的正主在第 2 页 ----
    @property
    def param_rows(self) -> dict:
        return self.panel.param_rows if self.panel else {}

    @property
    def lbl_values(self) -> dict:
        return self.panel.lbl_values if self.panel else {}

    @property
    def cmb_preset(self):
        return self.panel.cmb_preset

    @property
    def step_buttons(self) -> dict:
        return self.panel.step_buttons if self.panel else {}

    def retranslate(self):
        w = self.win
        self.grp_param.setTitle(w.t("settings.param_table"))
        self.src_table.setHorizontalHeaderLabels([
            w.t("settings.param_table"), w.t("settings.value_table"), w.t("settings.source")])
        w.t_into(self.btn_restore, "btn.restore_inherit")
        self.grp_attr.setTitle(w.t("attr.title"))
        w.t_into(self.lbl_attr_hint, "attr.hint")
        w.t_into(self.lbl_sp, "attr.surfaceprop")
        self.cmb_sp.setItemText(0, w.t("attr.surfaceprop_default"))
        w.t_into(self.lbl_sp_desc, "attr.surfaceprop_desc")
        w.t_into(self.lbl_toggles, "attr.toggles")
        w.t_into(self.lbl_toggle_desc, "attr.toggle_desc")
        w.t_into(self.chk_cutout, "attr.cutout")
        w.t_into(self.lbl_cutout_desc, "attr.cutout_desc")
        self.grp_kv.setTitle(w.t("attr.custom"))
        self.kv_table.setHorizontalHeaderLabels([w.t("attr.key"), w.t("attr.value")])
        w.t_into(self.btn_add_kv, "btn.add")
        w.t_into(self.btn_del_kv, "btn.remove")
        w.t_into(self.lbl_kv_empty, "attr.kv_empty")
        # 13-E：眼睛专用图那组的文案（默认藏着，选到眼睛档才出现）
        self.grp_eye.setTitle(w.t("eye.title"))
        w.t_into(self.lbl_iris, "eye.iris")
        w.t_into(self.lbl_ao, "eye.ao")
        w.t_into(self.btn_iris, "naming.browse")
        w.t_into(self.btn_ao, "naming.browse")
        self._refresh_kv_empty()
        self.refresh_sources()


class ExportPage(QtWidgets.QWidget):
    """④ 导出（假 GUI `page_export` 的版式）。

    这一页只干"落地"一件事：输出位置 / 部署目录 / 同名冲突提示 + 导出方式（只导出不部署、
    开始转换）+ 这次的结果（清单 + log 摘要 + 三个按钮）。
    """

    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        # 输出位置 / 部署目录 / 同名冲突提示（都是只读的，说明"会落到哪"）
        self.grp_output = QtWidgets.QGroupBox()
        go = QtWidgets.QGridLayout(self.grp_output)
        go.setHorizontalSpacing(10)
        self.lbl_out_dir = QtWidgets.QLabel()
        self.ed_out_dir = QtWidgets.QLineEdit()
        self.ed_out_dir.setReadOnly(True)
        self.lbl_deploy_dir = QtWidgets.QLabel()
        self.ed_deploy_dir = QtWidgets.QLineEdit()
        self.ed_deploy_dir.setReadOnly(True)
        self.lbl_conflict_hint = QtWidgets.QLabel()
        self.lbl_conflict_hint.setWordWrap(True)
        self.lbl_conflict_hint.setStyleSheet(UI_TODO)
        go.addWidget(self.lbl_out_dir, 0, 0)
        go.addWidget(self.ed_out_dir, 0, 1)
        go.addWidget(self.lbl_deploy_dir, 1, 0)
        go.addWidget(self.ed_deploy_dir, 1, 1)
        go.addWidget(self.lbl_conflict_hint, 2, 0, 1, 2)
        go.setColumnStretch(1, 1)
        grid.addWidget(self.grp_output, 0, 0)

        # 导出方式：只导出不部署 + 开始转换（未导入素材时禁用）
        self.grp_export = QtWidgets.QGroupBox()
        vo = QtWidgets.QVBoxLayout(self.grp_export)
        self.chk_deploy = QtWidgets.QCheckBox()
        self.chk_deploy.setChecked(True)
        vo.addWidget(self.chk_deploy)
        self.lbl_deploy_desc = QtWidgets.QLabel()
        self.lbl_deploy_desc.setWordWrap(True)
        self.lbl_deploy_desc.setStyleSheet(UI_DESC)
        vo.addWidget(self.lbl_deploy_desc)
        self.btn_start = QtWidgets.QPushButton()      # 03 §2 决策 A：没导入素材时禁用
        self.btn_start.setDefault(True)
        self.btn_start.setEnabled(False)
        self.btn_start.setMinimumHeight(40)
        vo.addWidget(self.btn_start)
        self.lbl_start_hint = QtWidgets.QLabel()
        self.lbl_start_hint.setStyleSheet("color:#7a7a7a;")
        vo.addWidget(self.lbl_start_hint)
        vo.addStretch(1)
        grid.addWidget(self.grp_export, 0, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        v.addLayout(grid)

        # 这次的结果（跑完才出现；没跑过就不摆一个空壳）
        self.grp_result = QtWidgets.QGroupBox()
        rv = QtWidgets.QVBoxLayout(self.grp_result)
        self.txt_result = QtWidgets.QPlainTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setMinimumHeight(140)
        rv.addWidget(self.txt_result)
        self.lbl_result = QtWidgets.QLabel()
        self.lbl_result.setWordWrap(True)
        rv.addWidget(self.lbl_result)
        row = QtWidgets.QHBoxLayout()
        self.btn_open_out = QtWidgets.QPushButton()
        self.btn_open_out.clicked.connect(self.open_output)
        self.btn_open_log = QtWidgets.QPushButton()
        self.btn_open_log.clicked.connect(self.open_log)
        self.btn_copy_fail = QtWidgets.QPushButton()
        self.btn_copy_fail.clicked.connect(self.copy_failures)
        for b in (self.btn_open_out, self.btn_open_log, self.btn_copy_fail):
            row.addWidget(b)
        row.addStretch(1)
        rv.addLayout(row)
        v.addWidget(self.grp_result)
        self.grp_result.setVisible(False)
        v.addStretch(1)

    # ---- 结果区那三个动作 ----
    def open_output(self):
        d = getattr(self.win, "last_out_dir", None)
        if d and Path(d).is_dir():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(d)))

    def open_log(self):
        path = getattr(self.win, "last_log", None)
        if path and Path(path).is_file():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))
            return
        QtWidgets.QMessageBox.information(self, self.win.t("about.log"),
                                          self.win.t("about.no_log"))

    def copy_failures(self):
        fails = getattr(self.win, "last_failures", []) or []
        text = "\n".join(f"{g}：{why}" for g, why in fails) if fails else self.win.t("result.no_fail")
        QtWidgets.QApplication.clipboard().setText(text)
        self.win.log_key("result.copied")

    def _result_lines(self) -> list:
        """结果清单：**直接读第 1 页那张表**，不另存一份状态（免得两边对不上）。"""
        t = self.win.page_convert.table
        out = []
        for i in range(t.rowCount()):
            cells = []
            for c in (0, 1, 3):
                it = t.item(i, c)
                cells.append(it.text() if it else "")
            name, status, note = cells
            if not name:
                continue
            out.append(f"{name} ｜ {status}" + (f" ｜ {note}" if note else ""))
        return out

    def refresh_result(self):
        """结果清单：跑完才出现；语言切换后文字要跟着变。"""
        w = self.win
        ran = getattr(w, "last_summary", None)
        self.grp_result.setVisible(bool(ran))
        if not ran:
            # ⚠️ 这里**必须把上一次的文字清掉**：整组虽然藏着，但切到英文后那个隐藏的
            #    QLabel 里还留着中文（一类 2026-09-27 从控件文字清单里抓到过）——
            #    "藏着的控件"一样算界面残留。清掉最省事，也顺手把三个按钮复位。
            self.txt_result.setPlainText("")
            self.lbl_result.setText("")
            for b in (self.btn_open_out, self.btn_open_log, self.btn_copy_fail):
                b.setEnabled(False)
            return
        ok, skip, fail = ran
        lines = self._result_lines()
        if w.last_log:
            lines.append("")
            lines.append(f"{w.t('about.log')}: {w.last_log}")
        self.txt_result.setPlainText("\n".join(lines))
        self.lbl_result.setText(w.t("status.done", ok=ok, skip=skip, fail=fail))
        self.btn_open_out.setEnabled(bool(w.last_out_dir and Path(w.last_out_dir).is_dir()))
        self.btn_open_log.setEnabled(bool(w.last_log and Path(w.last_log).is_file()))
        self.btn_copy_fail.setEnabled(bool(w.last_failures))

    def retranslate(self):
        w = self.win
        self.grp_output.setTitle(w.t("export.output_title"))
        w.t_into(self.lbl_out_dir, "export.out_dir")
        w.t_into(self.lbl_deploy_dir, "export.deploy_dir")
        w.t_into(self.lbl_conflict_hint, "export.conflict_hint")
        self.grp_export.setTitle(w.t("export.only_title"))
        w.t_into(self.chk_deploy, "output.deploy")
        w.t_into(self.lbl_deploy_desc, "output.deploy_desc")
        w.t_into(self.btn_start, "btn.start")
        w.t_into(self.lbl_start_hint, "export.start_hint")
        self.grp_result.setTitle(w.t("export.result_title"))
        w.t_into(self.btn_open_out, "btn.open_out")
        w.t_into(self.btn_open_log, "btn.open_log")
        w.t_into(self.btn_copy_fail, "btn.copy_fail")
        self.refresh_result()


class AboutPage(QtWidgets.QWidget):
    """⑤ 关于：版本 / 许可 / 日志与配置目录 / 术语表（术语表下一步 S6 再扩）。"""

    def __init__(self, win):
        super().__init__()
        self.win = win
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(8)
        self.lbl_app = QtWidgets.QLabel()
        f = self.lbl_app.font()
        f.setBold(True)
        self.lbl_app.setFont(f)
        v.addWidget(self.lbl_app)
        self.lbl_desc = QtWidgets.QLabel()
        self.lbl_desc.setWordWrap(True)
        v.addWidget(self.lbl_desc)
        self.lbl_ver = QtWidgets.QLabel()
        v.addWidget(self.lbl_ver)
        self.lbl_lic = QtWidgets.QLabel()
        self.lbl_lic.setWordWrap(True)
        v.addWidget(self.lbl_lic)

        log_row = QtWidgets.QHBoxLayout()
        self.lbl_log = QtWidgets.QLabel()
        log_row.addWidget(self.lbl_log, 1)
        self.btn_log = QtWidgets.QPushButton()
        self.btn_log.clicked.connect(self.open_log)
        log_row.addWidget(self.btn_log)
        v.addLayout(log_row)

        cfg_row = QtWidgets.QHBoxLayout()
        self.lbl_cfg = QtWidgets.QLabel()
        cfg_row.addWidget(self.lbl_cfg, 1)
        self.btn_cfg = QtWidgets.QPushButton()
        self.btn_cfg.clicked.connect(self.open_config)
        cfg_row.addWidget(self.btn_cfg)
        v.addLayout(cfg_row)

        v.addWidget(hline())
        self.lbl_glossary = QtWidgets.QLabel()
        f2 = self.lbl_glossary.font()
        f2.setBold(True)
        self.lbl_glossary.setFont(f2)
        v.addWidget(self.lbl_glossary)
        self.table = QtWidgets.QTableWidget(len(i18n.GLOSSARY), 2)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setWordWrap(True)
        for i, (term, _zh, _en) in enumerate(i18n.GLOSSARY):
            self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(term))
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(""))
        v.addWidget(self.table, 1)

    def open_log(self):
        """打开最近一次转换的 log.txt（没有就提示先转换一次）。"""
        path = getattr(self.win, "last_log", None)
        if path and Path(path).is_file():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))
            return
        QtWidgets.QMessageBox.information(self, self.win.t("about.log"),
                                          self.win.t("about.no_log"))

    def open_config(self):
        root = Path(self.win.config_root)
        root.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(root)))

    def retranslate(self):
        self.lbl_app.setText(self.win.t("app.title"))
        self.lbl_desc.setText(self.win.t("app.subtitle"))
        self.lbl_ver.setText(self.win.t("about.version", v=APP_VERSION))
        self.lbl_lic.setText(self.win.t("about.license"))
        self.win.t_into(self.lbl_log, "about.log")
        self.win.t_into(self.btn_log, "btn.open_log")
        self.win.t_into(self.lbl_cfg, "about.config_dir")
        self.win.t_into(self.btn_cfg, "btn.open_config")
        self.win.t_into(self.lbl_glossary, "about.glossary")
        self.table.setHorizontalHeaderLabels([self.win.t("about.col_term"),
                                              self.win.t("about.col_explain")])
        lang = self.win.lang
        for i, (_term, zh, en) in enumerate(i18n.GLOSSARY):
            self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(zh if lang == i18n.LANG_ZH else en))


class Cancelled(Exception):
    """用户在阶段中途按了取消 —— 靠进度回调抛出，让慢阶段不用等跑完。"""


class ConvertWorker(QtCore.QThread):
    """后台**串行**转换（实施计划 §9.1）：GUI 不卡、可取消、逐行更新表格。

    冲突询问要跨线程：worker 发信号让主线程弹框，然后**阻塞等回答**
    （主线程在跑事件循环，不会被 worker 卡住，所以不会死锁）。
    """

    progressed = QtCore.Signal(int, str, float)     # 行号, 阶段名, 0..1
    row_done = QtCore.Signal(int, str, str)         # 行号, 状态, 说明
    ask_conflicts = QtCore.Signal(list)
    all_done = QtCore.Signal(int, int, int)         # 成功 / 跳过 / 失败

    def __init__(self, sets, options, resolved, vmt_names, cdm_override, labels):
        super().__init__()
        self.sets = sets
        self.options = options
        self.resolved = resolved
        self.vmt_names = vmt_names
        self.cdm_override = cdm_override
        self.labels = labels
        self.out_dirs = []                 # 给"打开日志"用
        self.failures = []                 # [(材质组, 原因)]，给"复制失败原因"用
        self._cancel = False
        self._answer = None
        self._gate = threading.Event()

    def cancel(self):
        self._cancel = True

    def _progress(self, row: int, stage: str, frac: float):
        self.progressed.emit(row, stage, frac)
        if self._cancel:
            raise Cancelled()              # 慢阶段（VTFCmd）之间插一个取消检查点

    def provide_answer(self, ok: bool):
        self._answer = ok
        self._gate.set()

    def _confirm(self, conflicts):
        self._answer = None
        self._gate.clear()
        self.ask_conflicts.emit(list(conflicts))
        self._gate.wait(300)                      # 等用户在对话框上点一下
        return bool(self._answer)

    def _why(self, e) -> str:
        """13-E：core 抛的是**带码**的异常（core 不产人话）→ 在界面这层渲染成人话。

        `MissingInput`（缺用户必须提供的图）走 i18n；其它异常原样给（老行为）。
        """
        code = getattr(e, "code", "")
        key = {"eye.iris": "eye.need_iris", "eye.ao": "eye.need_ao"}.get(code)
        if key:
            return i18n.t(key, self.labels.get("lang", i18n.LANG_ZH))
        return str(e)

    def run(self):
        ok = skip = fail = 0
        for i, matset in enumerate(self.sets):
            if self._cancel:
                skip += 1
                self.row_done.emit(i, self.labels["skipped"], self.labels["cancelled"])
                continue
            try:
                got = pipeline.convert_set(
                    matset, self.options, self.resolved, self.vmt_names, self.cdm_override,
                    confirm=self._confirm,
                    progress=lambda stage, frac, row=i: self._progress(row, stage, frac))
            except Cancelled:
                skip += 1
                self.row_done.emit(i, self.labels["skipped"], self.labels["cancelled"])
                continue
            except Exception as e:  # noqa: BLE001 —— 单个失败不影响其它
                fail += 1
                why = self._why(e)
                self.failures.append((matset.group, why))
                self.row_done.emit(i, self.labels["failed"], why)
                continue
            if got["skipped"]:
                skip += 1
                # 13-C：跳过的**原因**要说出来 —— "指纹一致"（老行为，不用解释）vs
                #      "撞上同名产物、你没让覆盖"（必须说，否则用户以为白跑了）
                reason = (self.labels.get("skip_conflict", "")
                          if got.get("skip_reason") == "conflict" else "")
                self.row_done.emit(i, self.labels["skipped"], reason)
            else:
                ok += 1
                self.out_dirs.append(str(got["out_dir"]))
                # 10 片：警告**是数据**，界面按当前语言过一道（12 单起是"码 + 参数"）
                lang = self.labels.get("lang", i18n.LANG_ZH)
                note = ("；" if lang == i18n.LANG_ZH else "; ").join(
                    i18n.render_warnings(got["record"].get("警告"), lang))
                # 14-A：`log.txt` 也得是**人话**（core 只写码 → 可读化在 UI 层做）
                self._write_readable_log(got, lang)
                self.row_done.emit(i, self.labels["done_one"], note)
        self.all_done.emit(ok, skip, fail)

    def _write_readable_log(self, got, lang: str):
        """14-A：把这一套的 `log.txt` 重写成**当前语言可读**的版本。

        ⚠️ `core` 写的仍是"码"（铁律：core 不许产出人话）；这一步在 UI 层补上。
        ⚠️ fail-soft：日志写不出来**不能**把这次转换算成失败（`phong_input.json` 才是机器凭据）。
        """
        try:
            out = Path(got["out_dir"])
            vmts = got.get("vmts") or []
            vmt_text = Path(vmts[0][1]).read_text(encoding="utf-8", errors="replace") if vmts else ""
            (out / "log.txt").write_text(
                i18n.readable_log_text(got.get("record") or {}, lang, vmt_text),
                encoding="utf-8-sig")
        except OSError:
            pass


class MainWindow(QtWidgets.QMainWindow):
    """5 页主窗口：① 转换 ② 预览 + 调参 ③ 参数表 / 材质属性 / 自由键值 ④ 导出 ⑤ 关于。"""

    def __init__(self):
        super().__init__()
        # 语言优先级：环境变量（开发/截图用）> 配置 > 跟随系统
        self.lang_pref = os.environ.get("PBR2PHONG_LANG") or i18n.LANG_SYSTEM
        self.lang = i18n.resolve_language(self.lang_pref)
        self.resize(*WINDOW_SIZE)
        self.setMinimumSize(*WINDOW_MIN)           # 06 §4.2：别让用户拖更小（零滚动的前提）
        f = QtGui.QFont()                          # 假 GUI 同款：统一 12px
        f.setPixelSize(UI_FONT_PX)
        self.setFont(f)

        self.tabs = QtWidgets.QTabWidget()
        self.page_convert = ConvertPage(self)
        self.page_tuning = TuningPage(self)             # ② 预览 + 调参（A 版左右分栏）
        self.page_config = ConfigPage(self)             # ③ 参数表 / 材质属性 / 自由键值
        self.page_export = ExportPage(self)             # ④ 导出
        self.page_about = AboutPage(self)               # ⑤ 关于
        for page in (self.page_convert, self.page_tuning, self.page_config,
                     self.page_export, self.page_about):
            self.tabs.addTab(page, "")
        self.tabs.setCurrentIndex(0)                    # 防呆②：默认打开「① 转换」
        self.setCentralWidget(self.tabs)

        # 兼容旧引用：预览面板 / 参数模型（正主分别在 page_tuning 与 page_config）
        self.page_compare = self.page_tuning.preview
        self.page_settings = self.page_config                     # 参数模型（预设/覆盖项/参数表）
        self.page_tuning.settings = self.page_config              # 旧名，供页面互引用
        self.page_config.panel = self.page_tuning.panel           # 参数列的正主在第 2 页
        # 08 单附带项：表格换选中行 → 预览跟着换（只重算那一套，缓存按素材组名分）
        self.page_convert.table.itemSelectionChanged.connect(
            lambda: self.refresh_preview() if hasattr(self, "page_tuning") else None)

        # 状态栏：进度 + 状态 + 取消（「开始转换」不在这里，见第 4 页「导出」）
        bar = self.statusBar()
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(260)
        bar.addWidget(self.progress)
        self.lbl_status = QtWidgets.QLabel()
        bar.addWidget(self.lbl_status, 1)
        self.btn_start = self.page_export.btn_start       # 按钮在第 4 页「导出」，这里只留引用
        self.btn_start.setEnabled(False)                  # 决策 A：没导入素材时禁用
        self.btn_cancel = QtWidgets.QPushButton()
        self.btn_cancel.setEnabled(False)
        bar.addPermanentWidget(self.btn_cancel)

        self.worker = None
        self.materials_root = Path(pipeline.DEFAULT_MATERIALS)
        # 配置记忆：整机一份的配置目录（首次运行会把内置默认与预设导过去）
        self.config_root = str(settings.ensure_config_root())
        self.prefs = settings.load_gui_prefs(self.config_root)
        self.last_log = None
        self.last_out_dir = None           # 结束汇总：打开输出目录 / 打开日志 / 复制失败原因
        self.last_failures = []
        self.last_summary = None           # (成功, 跳过, 失败)；None = 还没跑过
        self.page_config.config_root = self.config_root
        self.btn_start.clicked.connect(self.start_conversion)
        self.btn_cancel.clicked.connect(self.cancel_conversion)

        self._build_lang_button()

        self.retranslate()
        self.apply_prefs()
        self.page_config.reload_presets(self.prefs.get("预设", ""))
        self.set_recognized(0)
        self.set_output(None)
        self.log_key("status.ready")        # 状态栏默认显示"就绪"，别露调试信息

    # -- 配置记忆 ------------------------------------------------------
    def apply_prefs(self):
        """把上次的设置套回来（语言 / 预设 / 勾选 / 上次素材目录 / 窗口大小）。"""
        p = self.prefs or {}
        lang = p.get("语言")
        if lang in i18n.LANG_CHOICES:
            self.lang_pref = lang
            self.lang = i18n.resolve_language(lang)
            self.retranslate()          # 右上角按钮的文字在 retranslate 里同步
        self.page_export.chk_deploy.setChecked(bool(p.get("直接写进游戏", True)))
        self.page_convert.ed_vtfcmd.setText(str(p.get("VTFCmd路径", "")))
        self.page_convert.refresh_vtfcmd_hint()
        self.page_convert.ed_hlmv.setText(str(p.get("HLMV路径", "")))
        self.page_convert.refresh_hlmv_hint()
        folder = p.get("上次素材目录")
        if folder and Path(str(folder)).is_dir():
            self.page_convert.load_folder(Path(str(folder)))
        size = p.get("窗口大小")
        if isinstance(size, list) and len(size) == 2:
            self.resize(max(WINDOW_MIN[0], int(size[0])), max(WINDOW_MIN[1], int(size[1])))

    def collect_prefs(self) -> dict:
        page = self.page_convert
        return {
            "语言": self.lang_pref,
            "预设": self.page_config.current_preset(),
            "直接写进游戏": self.page_export.chk_deploy.isChecked(),
            "VTFCmd路径": page.ed_vtfcmd.text().strip(),
            "HLMV路径": page.ed_hlmv.text().strip(),
            "上次素材目录": str(page.folder) if page.folder else "",
            "窗口大小": [self.width(), self.height()],
        }

    def save_prefs(self):
        try:
            settings.save_gui_prefs(self.config_root, self.collect_prefs())
        except OSError:
            pass

    def closeEvent(self, ev):          # noqa: N802 —— Qt 的 C++ 虚函数名
        self.save_prefs()
        super().closeEvent(ev)

    # -- 小工具 --------------------------------------------------------
    def t(self, key, **fmt) -> str:
        return i18n.t(key, self.lang, **fmt)

    def t_into(self, widget, key):
        widget.setText(self.t(key))

    def _sync_start_enabled(self):
        """03 §2 决策 A：「开始转换」只在**导入了素材**、且当前没有任务在跑时可点。"""
        busy = self.worker is not None and self.worker.isRunning()
        self.btn_start.setEnabled(bool(self.page_convert.sets) and not busy)

    def set_recognized(self, n: int):
        self.page_convert.lbl_recognized.setText(
            self.t("label.recognized", n=n) if n else self.t("label.recognized_empty"))
        self._sync_start_enabled()

    # -- 预览（S3）：把当前参数现算成图显示出来 —— **不落盘、不调 VTFCmd** ----
    def preview_kinds(self) -> list:
        """右框能看哪几张图：模型线有指数贴图，笔刷线没有（它只出底色 + 法线）。"""
        route, _mask = self.page_convert.current_route()
        return ["exp", "basecolor", "normal"] if route == "model" else ["basecolor", "normal"]

    @staticmethod
    def _preview_array(arr, max_side: int = PREVIEW_MAX_SIDE):
        """降到 ≤max_side 再交给界面（**只为显示**，转换产物一个像素都不动）。"""
        if arr is None:
            return None
        h, w = arr.shape[:2]
        if max(h, w) <= max_side:
            return arr
        k = max_side / float(max(h, w))
        return imaging.resample(arr, max(1, int(round(w * k))), max(1, int(round(h * k))))

    def refresh_preview(self, force: bool = False):
        """左框＝素材里的底色，右框＝**当前参数下现算的产出**（内存里算，不写盘）。

        刷新粒度（用户 2026-09-27 拍板）：拖滑杆**只更新数值**，**松手才重算** ——
        所以这个函数只被 `ParamPanel._on_slider_released`、预设/属性变化、切路线、
        导入素材、切语言这些地方调用，**绝不挂 valueChanged**。
        """
        prev = self.page_tuning.preview
        kinds = self.preview_kinds()
        # ⚠️ 第一次进来时下拉还是空的，`current_kind()` 的兜底值（basecolor）**不算用户的选择** ——
        #    默认该是单子要求的 `_exp`（模型线）/ `basecolor`（笔刷线），也就是 `kinds[0]`。
        keep = prev.current_kind() if (prev.cmb_kind.count() and prev.current_kind() in kinds) \
            else kinds[0]
        prev.set_kinds(kinds, current=keep)
        page = self.page_convert
        # 08 单附带项：**预览跟着第 1 页表格的选中项走**（多套素材时不再固定看第一套）；
        # 没选中就看第一套。缓存按"素材组名"分，所以换选中项只重算那一套。
        row = page.table.currentRow() if page.table.rowCount() else -1
        ms = page.sets[row] if 0 <= row < len(page.sets) else (page.sets[0] if page.sets else None)
        if ms is None:
            for box in (prev.left, prev.right):
                box.set_placeholder(self.t("preview.need_import"))
            prev.set_images(None, None)
            self._preview_key = None
            return
        src = None
        try:
            base_path = ms.get("shader.base_color")
            if base_path is not None:
                src = self._preview_array(imaging.load(base_path))
        except Exception as e:  # noqa: BLE001 —— 读出问题也不能把界面搞崩
            self.log(f"{ms.group}: {e}")
        route, brush_mask = page.current_route()
        kind = prev.current_kind()
        overrides = self.page_config.current_overrides()
        key = (ms.group, route, bool(brush_mask), kind,
               self.page_config.current_preset(),
               tuple(sorted((k, str(v)) for k, v in overrides.items())))
        if force or key != getattr(self, "_preview_key", None):
            out = None
            try:
                options = pipeline.ConvertOptions(
                    source=str(page.folder or ""), name="preview", cdmaterials="custom",
                    preset=self.page_config.current_preset(), overrides=overrides,
                    route=route, brush_mask=brush_mask)
                resolved = pipeline.resolve_options(options, self.config_root, self.config_root)
                # ⚠️ 与真转换**共用** pack.options_from_values —— 预览不能自己拼一份，
                #    两条路一旦漂移，预览就会骗人（项目铁律：转换逻辑只在 core 里实现一次）。
                res = pack.build(ms, pack.options_from_values(
                    resolved.values, route=route, brush_mask=brush_mask))
                out = self._preview_array(res.images().get(kind))
            except Exception as e:  # noqa: BLE001 —— 算不出来就在框里说清楚，别崩
                self._preview_err = str(e)
                self.log(f"{ms.group}: {e}")
            self._preview_out = out
            self._preview_key = key
        # ⚠️ 选了这套素材**没有的那张图**（比如没烘法线）时，右框说人话，别拿
        #    "先导入素材"去糊弄（那会让人以为素材没读进来）。
        if getattr(self, "_preview_out", None) is None:
            prev.right.set_placeholder(self.t("preview.none"))
        else:
            prev.right.set_placeholder(self.t("preview.need_import"))
        prev.set_images(
            src, getattr(self, "_preview_out", None),
            src_name=f"{self.t('preview.src')}：{ms.group}",
            out_name=f"{self.t('preview.out')}：{self.t(f'preview.kind_{kind}')}")

    def set_output(self, _path=None):
        """输出位置 / 部署目录：本地永远留档，另外（默认）直接写进游戏。"""
        page = self.page_convert
        cdm, name, _names = page.current_naming()
        if page.folder and name:
            local = Path(page.folder).parent / f"{name}_phong"
            self.page_export.ed_out_dir.setText(str(local))
        else:
            self.page_export.ed_out_dir.setText(self.t("label.output_choose"))
        rel = cdm.strip("/")
        deploy = Path(self.materials_root) / rel if rel else Path(self.materials_root)
        self.page_export.ed_deploy_dir.setText(str(deploy))

    # -- 转换（后台线程）------------------------------------------------
    def start_conversion(self):
        page = self.page_convert
        if not page.sets:
            QtWidgets.QMessageBox.information(self, self.t("app.title"), self.t("err.no_folder"))
            return
        cdm, name, vmt_names = page.current_naming()
        if not name:
            QtWidgets.QMessageBox.information(self, self.t("app.title"), self.t("err.need_name"))
            return
        route, brush_mask = page.current_route()
        # 13-E：眼睛档**预检** —— 缺虹膜图当场说人话（别等后台线程抛异常再报）
        if self.page_config.current_preset() == "角色-眼睛" and route == "model" \
                and not self.page_config.ed_iris.text().strip():
            QtWidgets.QMessageBox.information(self, self.t("app.title"), self.t("eye.need_iris"))
            return
        options = pipeline.ConvertOptions(
            source=str(page.folder or ""), name=name, cdmaterials=cdm or "custom",
            preset=self.page_config.current_preset(),
            deploy=self.page_export.chk_deploy.isChecked(),
            overrides=self.page_config.current_overrides(),
            vtfcmd=self.page_convert.current_vtfcmd(),
            route=route, brush_mask=brush_mask)
        try:
            resolved = pipeline.resolve_options(options, self.config_root, self.config_root)
        except (KeyError, ValueError) as e:
            QtWidgets.QMessageBox.warning(self, self.t("app.title"), str(e))
            return
        self.save_prefs()
        self.worker = ConvertWorker(
            list(page.sets), options, resolved, vmt_names or None, cdm or None,
            {"done_one": self.t("status.done_one"), "failed": self.t("status.failed"),
             "skipped": self.t("status.skipped"), "cancelled": self.t("status.cancelled"),
             "skip_conflict": self.t("skip.conflict"),          # 13-C：撞名跳过要说原因
             "lang": self.lang})
        self.worker.progressed.connect(self._on_progress)
        self.worker.row_done.connect(self._on_row_done)
        self.worker.ask_conflicts.connect(self._on_conflicts)
        self.worker.all_done.connect(self._on_finished)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setValue(0)
        self.worker.start()

    def cancel_conversion(self):
        if self.worker:
            self.worker.cancel()
            self.log_key("status.cancelling")

    def _on_progress(self, row: int, stage: str, frac: float):
        page = self.page_convert
        page.table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{stage} {frac * 100:.0f}%"))
        page.table.setItem(row, 1, QtWidgets.QTableWidgetItem(stage))
        total = max(1, len(page.sets))
        self.progress.setValue(int((row + frac) / total * 100))
        self.log_key("status.working", name=page.table.item(row, 0).text(), stage=stage)

    def _on_row_done(self, row: int, status: str, note: str):
        page = self.page_convert
        page.table.setItem(row, 1, QtWidgets.QTableWidgetItem(status))
        page.table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
        page.table.setItem(row, 3, QtWidgets.QTableWidgetItem(note))

    def _on_conflicts(self, conflicts):
        # 13-C：core 给的是**码**（`exists` / `in_materials`）→ 人话在这一层渲染（core 不产人话）
        why_keys = {"exists": "conflict.why_exists", "in_materials": "conflict.why_in_materials"}
        rows = []
        for rel, why in conflicts:
            why_text = self.t(why_keys[why]) if why in why_keys else str(why)
            rows.append(f"  · {rel} — {why_text}")
        text = "\n".join(rows)
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(self.t("conflict.title"))
        box.setText(self.t("conflict.body", list=text))
        yes = box.addButton(self.t("conflict.overwrite"), QtWidgets.QMessageBox.YesRole)
        box.addButton(self.t("conflict.skip"), QtWidgets.QMessageBox.NoRole)
        box.exec()
        if self.worker:
            self.worker.provide_answer(box.clickedButton() is yes)

    def _on_finished(self, ok: int, skip: int, fail: int):
        self.progress.setValue(100)
        self.log_key("status.done", ok=ok, skip=skip, fail=fail)
        if self.worker:
            if self.worker.out_dirs:
                self.last_out_dir = self.worker.out_dirs[-1]
                self.last_log = str(Path(self.worker.out_dirs[-1]) / "log.txt")
            self.last_failures = list(self.worker.failures)
        self.last_summary = (ok, skip, fail)
        self.page_export.refresh_result()
        self.save_prefs()
        self._sync_start_enabled()                        # 03 §2：有素材才重新亮起
        self.btn_cancel.setEnabled(False)

    def log_key(self, key: str, **fmt):
        """记一条**带 key** 的状态消息（切语言时会被重新翻译）。"""
        self.log(self.t(key, **fmt), key=key, **fmt)

    def log(self, text: str, key: str | None = None, **fmt):
        """状态栏 = 最近一条消息。带 `key` 的消息在切换语言时会**重新翻译**，
        否则切到英文后状态栏会残留上一句中文（双语是这阶段的硬要求，不能半截）。
        自由文本（错误原因等）没有 key → 原样留着。"""
        self._log = getattr(self, "_log", [])
        self._log.append(text)
        self._status = (key, fmt)
        self.lbl_status.setText(str(text)[:120])

    # -- 语言切换：标签栏右上角的小按钮（两态：中文 ⇄ English）-----------------

    def _build_lang_button(self):
        """右上角一个小按钮，显示"点了会切到哪种语言"。

        为什么不是下拉、也不放参数页：语言只有两种，一个按钮最省事（用户 2026-09-25 定）。
        初始仍是「跟随系统」；用户点过一次之后才变成显式的 zh / en。
        语言名用**原生写法**（中文写"简体中文"、英文写"English"）—— 这两种写法不该被翻译。
        """
        self.btn_lang = QtWidgets.QPushButton()
        self.btn_lang.setFlat(True)
        self.btn_lang.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_lang.clicked.connect(self.toggle_language)
        corner = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(corner)
        row.setContentsMargins(0, 0, 8, 0)
        row.setSpacing(0)
        row.addWidget(self.btn_lang)
        self.tabs.setCornerWidget(corner, QtCore.Qt.TopRightCorner)
        self._sync_lang_button()

    def _sync_lang_button(self):
        """按钮文字 = **点了会切过去**的那个语言（中文界面显示 English，反之显示简体中文）。"""
        target = i18n.LANG_EN if self.lang == i18n.LANG_ZH else i18n.LANG_ZH
        self.btn_lang.setText(i18n.LANGUAGE_NAMES[target][target])
        self.btn_lang.setToolTip(self.t("settings.language_desc"))

    def toggle_language(self, *_):
        self.set_language(i18n.LANG_EN if self.lang == i18n.LANG_ZH else i18n.LANG_ZH)

    def set_language(self, pref: str):
        """切语言（pref 取 `i18n.LANG_CHOICES` 里的一项）。**按钮与测试共用这一个入口。**"""
        if pref not in i18n.LANG_CHOICES:
            return
        self.lang_pref = pref
        self.lang = i18n.resolve_language(pref)
        self.retranslate()

    def retranslate(self):
        self.setWindowTitle(self.t("app.window_title"))
        for i, key in enumerate(("tab.convert", "tab.tuning", "tab.config",
                                 "tab.export", "tab.about")):
            self.tabs.setTabText(i, self.t(key))
        for page in (self.page_convert, self.page_tuning, self.page_config,
                     self.page_export, self.page_about):
            page.retranslate()
        self.t_into(self.btn_cancel, "btn.cancel")
        if hasattr(self, "btn_lang"):        # 语言按钮也在右上角，切语言时文字要跟着翻
            self._sync_lang_button()
        # 状态栏那句也得跟着换语言（不然切到英文后底部还挂着中文）
        key, fmt = getattr(self, "_status", (None, {}))
        if key:
            self.lbl_status.setText(self.t(key, **fmt)[:120])
        self.refresh_preview()          # 预览框的标题（源素材/产出成品/图种）也要跟着换语言
        self.page_tuning.apply_sizes()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
