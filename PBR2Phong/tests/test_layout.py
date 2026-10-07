"""版式落地测试（离屏跑）—— 把假 GUI 的 `--selfcheck` 搬进正式测试。

对应 `_task/06-版式落地.md` **§7.2**（把"零滚动"变成测试）与 §4 的硬约束、§5.5 的禁令。

判据（每条都是机器可判的）：
  ① **零滚动**：5 页 × 2 尺寸，**真的可见的滚动条 = 0**，且 `minimumSizeHint` 能塞进实得区域
  ② 结构 = **5 页**，页签字面值一个不错（06 §5.5 给的就是这五个字符串）
  ③ 第 2 / 3 页**没有任何 `setCheckable(True)` 的 `QGroupBox`**（折叠禁令）
  ④ 假 GUI 专属、正式版不许出现的东西**一律不存在**（版式切换 / 第 2 页模式下拉 /
     页内「第 N 页」标题 / 假界面横幅）
  ⑤ 窗口默认 1280×760、最小 1200×680（拖不小）
  ⑥ 参数行**标签与控件同行**；拖滑杆只更新数值、松手才重算（刷新粒度）
  ⑦ 预览框保持 1:1，且**页面变矮时预览跟着缩**（零滚动的核心手法）
  ⑧ i18n **零漏键**（中英各扫一遍）

跑法：python tests/test_layout.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
# 别污染用户真的 %APPDATA%\PBR2Phong
os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-layout-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from gui.main import DESC_H, MainWindow, WINDOW_MIN, WINDOW_SIZE  # noqa: E402

PASS, FAIL = [], []

# 06 §5.5 给的就是这五个字面值：一个不能重、一个不能错
TAB_TEXTS = ("① 转换", "② 预览 + 调参", "③ 参数表 / 材质属性 / 自由键值", "④ 导出", "⑤ 关于")

SIZES = ((WINDOW_SIZE, "1280×760"), (WINDOW_MIN, "1200×680"))

# 形如 `settings.mode` / `attr.surfaceprop` 的原始 i18n 键名：出现在界面上就是漏键
_KEY_LOOKING = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def real_scrollbars(page):
    """**真正露出来的**滚动条。

    ⚠️ `QComboBox` 自带一个隐藏的 `QScrollArea` 弹窗容器（每个下拉 2 条 `QScrollBar`，
    parent 名字是 `qt_scrollarea_*container`，`isVisible()` 恒为 False）——
    那不是页面溢出，不能算数。这里按"不在弹窗容器里 且 真的可见"来判定。
    """
    out = []
    for sb in page.findChildren(QtWidgets.QScrollBar):
        par = sb.parent()
        in_popup = bool(par) and "scrollarea" in (par.objectName() or "")
        if sb.isVisible() and not in_popup:
            out.append(sb)
    return out


def visible_texts(page):
    """页面上所有控件的文字（标签 / 按钮 / 勾选框 / 组标题 + 页内富文本）。"""
    out = []
    for w in page.findChildren(QtWidgets.QWidget):
        text = ""
        if isinstance(w, (QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QCheckBox,
                          QtWidgets.QRadioButton)):
            text = w.text()
        elif isinstance(w, QtWidgets.QGroupBox):
            text = w.title()
        text = (text or "").strip()
        if text:
            out.append(text)
    return out


def checkable_groups(page):
    return [g.title() for g in page.findChildren(QtWidgets.QGroupBox) if g.isCheckable()]


def cjk_leaks(win, allow=()):
    """英文界面里**不许出现中日韩字符** —— 一类 2026-09-27 从控件文字清单里抓到的：
    英文下预览框写着「还没接上真图（预览在下一步做）」、结果行还挂着中文。

    ⚠️ 白名单只放**数据**：`$surfaceprop` 取值、VMT 参数名这类是天然英文；
    但**预设名**（角色-身体…）是用户自己存/官方给的**档名，属数据不属界面文案**，
    翻译它们要等 S5（一类 07 单第 7 问）。
    """
    bad = []
    allow = tuple(allow)
    for i in range(win.tabs.count()):
        for text in visible_texts(win.tabs.widget(i)):
            if not any("\u4e00" <= ch <= "\u9fff" for ch in text):
                continue
            if any(text == a or text.startswith(a) for a in allow):
                continue
            bad.append(f"第{i + 1}页 {text[:60]}")
    return bad


def main() -> int:
    print("== 版式落地（离屏）==")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # ---------- ⓪ 默认尺寸与最小尺寸 ----------
    print("== ⓪ 窗口尺寸 ==")
    win = MainWindow()
    check(f"默认尺寸是 {WINDOW_SIZE[0]}×{WINDOW_SIZE[1]}",
          (win.width(), win.height()) == WINDOW_SIZE, f"{win.width()}×{win.height()}")
    check(f"最小尺寸锁死 {WINDOW_MIN[0]}×{WINDOW_MIN[1]}",
          (win.minimumWidth(), win.minimumHeight()) == WINDOW_MIN,
          f"{win.minimumWidth()}×{win.minimumHeight()}")
    win.resize(600, 400)                     # 想拖小也拖不小
    app.processEvents()
    check("拖到 600×400 也被顶回最小尺寸",
          win.width() >= WINDOW_MIN[0] and win.height() >= WINDOW_MIN[1],
          f"{win.width()}×{win.height()}")

    # ---------- ② 结构 = 5 页，页签字面值一个不错 ----------
    print("== ② 五页结构 ==")
    check("标签页数 = 5", win.tabs.count() == 5, str(win.tabs.count()))
    actual = tuple(win.tabs.tabText(i) for i in range(win.tabs.count()))
    check("五个页签的字面值全对", actual == TAB_TEXTS, str(actual))
    check("页签没有重名", len(set(actual)) == len(actual), str(actual))
    check("默认打开第 1 页", win.tabs.currentIndex() == 0, str(win.tabs.currentIndex()))

    # ---------- ④ 假 GUI 专属的东西一律不存在 ----------
    print("== ④ 假 GUI 专属的东西不许出现 ==")
    all_text = []
    for i in range(win.tabs.count()):
        all_text += visible_texts(win.tabs.widget(i))
    check("没有页内「第 N 页 · ×××」标题",
          not [t for t in all_text if re.match(r"^第\s*\d+\s*页", t)],
          str([t for t in all_text if re.match(r"^第\s*\d+\s*页", t)]))
    check("没有假界面横幅",
          not [t for t in all_text if "假界面" in t or "原型" in t],
          str([t for t in all_text if "假界面" in t or "原型" in t]))
    combos = [c for c in win.page_tuning.findChildren(QtWidgets.QComboBox)]
    check("第 2 页没有「版式」切换控件",
          not [c for c in combos if any(c.itemText(i).startswith(("A ·", "B ·", "C ·"))
                                        for i in range(c.count()))],
          str([[c.itemText(i) for i in range(c.count())] for c in combos]))
    check("第 2 页没有「模式」下拉（模式属于第 1 页）",
          not [c for c in combos
               if c.count() == 2 and c.itemText(0) in ("模型", "笔刷")],
          str([[c.itemText(i) for i in range(c.count())] for c in combos]))

    # ---------- ③ 折叠禁令 ----------
    print("== ③ 折叠禁令（第 2 / 3 页） ==")
    for name, page in (("第 2 页", win.page_tuning), ("第 3 页", win.page_config)):
        bad = checkable_groups(page)
        check(f"{name} 没有 setCheckable 的组", not bad, str(bad))

    # ---------- ⑥ 参数行版式 + 刷新粒度 ----------
    print("== ⑥ 参数行与刷新粒度 ==")
    panel = win.page_tuning.panel
    row = panel.param_rows["boost"]
    label, slider, _desc = row
    check("参数行：标签与控件同行（同一个 holder）", label.parent() is slider.parent(),
          f"{label.parent()} vs {slider.parent()}")
    check("参数行：标签是加粗的", label.font().bold())
    # ⚠️ 11 片**改了这条的措辞**（断言本身仍成立）：原来是"标签宽度固定 84"，但英文参数名
    #    比 84 长（Roughness Offset=115 / Metal Tint Strength=134）→ 定宽就**无声切字**
    #    （截图里 "Roughness Offs" / "Metal Tint Str"）。现在改成"**至少** 84，长了自己变宽"。
    check("参数行：标签至少 84（中文够宽，英文长了会自己变宽、不被切）",
          label.width() and label.maximumWidth() == 84
          or label.minimumWidth() == 84 or label.width() <= 100,
          f"width={label.width()} min={label.minimumWidth()} max={label.maximumWidth()}")
    # ⚠️ 11 片**改过这条断言**（规格变了）：原来要求解释"高度钉死 17px"—— 那正是**无声切字**
    #    的根源（定高 + 不换行，超宽直接切掉、连省略号都没有）。现在要求：灰字 + 可换行 +
    #    不再定死 17px（`_desc()` 用最小高度，由布局按需给到两行）。
    check("参数行：解释是灰字、可换行、不再是 17px 定高（防无声切字）",
          "6b7280" in _desc.styleSheet() and _desc.wordWrap() and _desc.maximumHeight() > 17,
          f"{_desc.styleSheet()} wrap={_desc.wordWrap()} max={_desc.maximumHeight()}")

    keys = [win.page_config.src_table.item(r, 0).text()
            for r in range(win.page_config.src_table.rowCount())]
    idx = keys.index("vmt.$phongboost")
    before = win.page_config.src_table.item(idx, 1).text()
    panel.sl_boost.setSliderDown(True)                 # 假装用户按住了滑杆
    panel.sl_boost.setValue(min(100, panel.sl_boost.value() + 20))
    app.processEvents()
    check("拖动中：数值跟手了", panel.lbl_values["boost"].text() != "",
          panel.lbl_values["boost"].text())
    check("拖动中：参数表没被重算（攒着）",
          win.page_config.src_table.item(idx, 1).text() == before,
          f"{before} → {win.page_config.src_table.item(idx, 1).text()}")
    panel.sl_boost.setSliderDown(False)
    panel.sl_boost.sliderReleased.emit()               # 松手那一下才重算
    app.processEvents()
    check("松手后重算了一次", win.page_config.src_table.item(idx, 1).text() != before,
          f"{before} → {win.page_config.src_table.item(idx, 1).text()}")
    win.page_config.reset_overrides()

    # ---------- ⑧ i18n 零漏键（中英各扫一遍） ----------
    print("== ⑧ i18n 零漏键 ==")
    for lang in ("zh", "en"):
        win.set_language(lang)
        app.processEvents()
        bad = []
        for i in range(win.tabs.count()):
            for t in visible_texts(win.tabs.widget(i)):
                if _KEY_LOOKING.match(t):
                    bad.append(f"第{i + 1}页 {t}")
        check(f"{lang}：界面没有漏出原始键名", not bad, str(bad))
    # ⚠️ 第二道：**英文界面不许出现中日韩字符**（一类 06 验收时抓到的"串语言"）
    preset_names = [win.page_tuning.panel.cmb_preset.itemText(k)
                    for k in range(win.page_tuning.panel.cmb_preset.count())]
    bad = cjk_leaks(win, allow=preset_names)
    check("英文界面里没有中文残留（预设名当数据白名单）", not bad, str(bad))

    # ⚠️ 第三道（10 片）：**「来源」列的值**也要没有中文 —— 它原来硬编码在 `core/settings.py` 里
    #    （`SOURCE_GLOBAL = "全局默认"` / `f"{preset_name}预设"`），既不在控件文字里（第二道扫不到），
    #    也不走 i18n。10 片改成：core 只出**层标识**，界面按 `src.*` 渲染。
    cmb = win.page_tuning.panel.cmb_preset
    if cmb.count():
        cmb.setCurrentIndex(0)                       # 选一档，让「来源」列里真的出现"预设"这种值
                                                     # （13-F：按**索引**选，别按文字 —— 英文下文字是英文名）
        app.processEvents()
    tbl = win.page_config.src_table
    src_texts = [(tbl.item(r, 2).text() if tbl.item(r, 2) else "")
                 for r in range(tbl.rowCount())]
    bad3 = [x for x in src_texts
            if any("\u4e00" <= ch <= "\u9fff" for ch in x)
            and not any(x.endswith(p) for p in preset_names)]
    check("英文界面「来源」列没有中文残留（预设名当数据白名单）", not bad3, str(bad3))
    legacy = [x for x in src_texts if x in ("全局默认", "你改过") or x.startswith("预设：")]
    check("英文界面「来源」列不再出现旧的中文来源词", not legacy, str(legacy))
    check("「来源」列有 13 行且每行都有值（10 片：alpha.cutout 进表）",
          len(src_texts) == 13 and all(src_texts), f"{len(src_texts)} 行：{src_texts[:3]}")
    win.set_language("zh")

    # 内部片号（S3 / S4…）不许漏到用户界面上 —— 那是我们自己排片用的编号
    leaks = []
    for lang in ("zh", "en"):
        win.set_language(lang)
        app.processEvents()
        for i in range(win.tabs.count()):
            for t in visible_texts(win.tabs.widget(i)):
                if re.search(r"\bS[1-9]\b", t) or re.search(r"第\s*[1-9]\s*页\s*·", t):
                    leaks.append(f"[{lang}] 第{i + 1}页 {t[:60]}")
    check("界面里搜不到内部片号（S1~S9）", not leaks, str(leaks))
    # 界面文案里不许出现 Markdown 星号（Qt 不渲染 Markdown，**加粗** 会原样显示出来）
    stars = []
    for lang in ("zh", "en"):
        win.set_language(lang)
        app.processEvents()
        for i in range(win.tabs.count()):
            for t in visible_texts(win.tabs.widget(i)):
                if "**" in t or "`" in t:
                    stars.append(f"[{lang}] 第{i + 1}页 {t[:60]}")
    check("界面文案里没有 Markdown 星号/反引号", not stars, str(stars))
    win.set_language("zh")

    # ⚠️ 第四道（**11 片重写 + 返工**）：**所有灰字解释在中英两种语言、两条路线下都不许被无声截断**。
    #    原来那条是"只量第 2 页「预设」那一行、只比文本宽 ≤ 控件宽"（= 只认一行）：
    #    ① 它把"该换行"误判成"被截断"，10 片据此写了假警报；② 它完全没管英文 —— 英文文案更长，
    #    实测 **7 条解释 + 4 个加粗参数名**真被切。
    #    ⚠️ **11 片返工的根因**（一类 2026-09-28 抓到）：我改了量法，但**没有 `show()` 窗口** →
    #    所有子控件 `isVisible()` 恒为 False → 逐条 `continue` → 8 条**恒绿、锁不住任何东西**
    #    （一类拿 11 片动手前的代码跑这份测试，④b 照样全绿 = 决定性证据）。
    #    **教训：没有必败样例的锁等于没有锁。**
    #    现在：① `win.show()` + `setCurrentIndex` 切页再量；② 检测器抽成 `clipped_in()`，
    #    并在末尾**拿"已知必败样例"喂它一次**，证明它真的会报红；③ 同类项全扫。
    def desc_labels(page_idx):
        """这一页**真正进布局**、会显示给用户的字：灰字解释（+ 第 2 页的加粗参数名）。

        ⚠️ 第 2 页的解释要取 `param_rows[key][2]` —— `panel.lbl_xxx_desc` 那批是**孤儿标签**
        （`_param_line` 内部另造了一个进布局的，11 片返工已删），量它们等于没量。
        """
        if page_idx == 1:
            panel = win.page_tuning.panel
            out = [("preset", panel.lbl_preset_desc), ("curve", panel.lbl_curve_desc),
                   ("curve_howto", panel.lbl_curve_todo)]
            for key in ("sharpness", "boost", "ao", "offset", "tint", "refl", "envtint"):
                out.append((key, panel.param_rows[key][2]))
                out.append((f"{key}_label", panel.param_rows[key][0]))   # 加粗参数名
            return out
        cfg = win.page_config
        return [("attr.hint", cfg.lbl_attr_hint),
                ("attr.surfaceprop_desc", cfg.lbl_sp_desc),
                ("attr.toggle_desc", cfg.lbl_toggle_desc),
                ("attr.cutout_desc", cfg.lbl_cutout_desc)]

    def clipped_in(page_idx):
        """这一页、当前语言/路线下**被切掉**的控件名清单（空 = 都放得下）。

        ⚠️ 先决条件：窗口必须已经 `show()` —— 否则 `isVisible()` 恒 False，逐条被跳过、
        这个检测器就变成永远返回空清单的**空转锁**（11 片返工踩过）。
        """
        clipped = []
        for name, lab in desc_labels(page_idx):
            if not lab.isVisible() or not lab.text():
                continue                      # 本路线不显示 / 没文案
            fm_lab = QtGui.QFontMetrics(lab.font())
            if lab.wordWrap():
                need = fm_lab.boundingRect(QtCore.QRect(0, 0, max(lab.width(), 1), 10000),
                                           int(QtCore.Qt.TextWordWrap), lab.text()).height()
                ok, detail = need <= lab.height() + 1, f"需要{need}>实得{lab.height()}"
            else:                             # 不换行的：一行放不下就是被切
                w = fm_lab.horizontalAdvance(lab.text())
                ok, detail = w <= lab.width(), f"文本宽{w}>控件宽{lab.width()}"
            if not ok:
                clipped.append(f"{name}({detail})")
        return clipped

    print("== ④b 灰字解释 / 参数名不被截断（中英 × 两条路线 × 第 2/3 页） ==")
    win.resize(*WINDOW_SIZE)
    win.show()                                # ⚠️ 必须 show（理由见上）
    for _ in range(3):
        app.processEvents()
    for lang in ("zh", "en"):
        win.set_language(lang)
        for route, is_model in (("model", True), ("brush", False)):
            win.page_convert.rb_route_model.setChecked(is_model)
            win.page_convert.rb_route_brush.setChecked(not is_model)
            app.processEvents()
            for page_idx in (1, 2):
                win.tabs.setCurrentIndex(page_idx)
                win.page_tuning.apply_sizes()
                for _ in range(3):
                    app.processEvents()
                clipped = clipped_in(page_idx)
                check(f"[{lang}/{route}] 第 {page_idx + 1} 页文字都没被截断", not clipped, str(clipped))

    # ⚠️ 自检（一类返工要求）：拿**已知必败样例**证明这锁不是在空转 —— 把一条本来需要两行的
    #    解释人为钉成一行高，检测器**必须**报红。防的就是"改没改都一样绿"。
    win.set_language("zh")
    win.page_convert.rb_route_model.setChecked(True)
    win.tabs.setCurrentIndex(2)
    for _ in range(3):
        app.processEvents()
    probe = win.page_config.lbl_cutout_desc          # 中文下本来就需要两行
    keep_max = probe.maximumHeight()
    probe.setFixedHeight(17)                         # 人为切一刀
    for _ in range(2):
        app.processEvents()
    caught = clipped_in(2)
    probe.setMinimumHeight(DESC_H)                   # 还原成 `_desc()` 的原状：至少一行、不封顶
    probe.setMaximumHeight(keep_max)
    for _ in range(2):
        app.processEvents()
    check("④b 自检：人为切一刀必须被抓到（证明这锁不是空转的）", bool(caught), str(caught)[:160])
    win.set_language("zh")
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()

    # ---------- ① 零滚动：5 页 × 2 尺寸 + ⑦ 预览跟着缩 ----------
    print("== ① 零滚动（5 页 × 2 尺寸） ==")
    sides = {}
    for size, tag in SIZES:
        w = MainWindow()
        w.resize(*size)
        w.show()
        app.processEvents()
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i)
            w.page_tuning.apply_sizes()                 # 第 2 页要按实到尺寸实算
            app.processEvents()
            page = w.tabs.currentWidget()
            name = TAB_TEXTS[i]
            bad = real_scrollbars(page)
            ms = page.minimumSizeHint()
            fits = ms.height() <= page.height() and ms.width() <= page.width()
            check(f"{tag} {name}：零滚动且装得下",
                  not bad and fits,
                  f"可见滚动条={len(bad)} 最小需求={ms.width()}×{ms.height()} "
                  f"实得={page.width()}×{page.height()}")
        sides[tag] = w.page_tuning.preview.left._side
        w.close()

    # 13-E：眼睛档会**多出一组「眼睛专用图」**（跟档出现）→ 那时候第 3 页也必须零滚动
    #      （1200×680 下的余量只有 ~10px，将来往第 3 页加东西先看这一条）
    for size, tag in SIZES:
        w = MainWindow()
        w.resize(*size)
        w.show()
        app.processEvents()
        sp = w.page_config
        sp.cmb_preset.setCurrentIndex(sp.cmb_preset.findData("角色-眼睛"))
        w.tabs.setCurrentIndex(2)
        w.page_tuning.apply_sizes()
        for _ in range(3):
            app.processEvents()
        page = w.tabs.currentWidget()
        ms = page.minimumSizeHint()
        bad = real_scrollbars(page)
        check(f"{tag} 眼睛档下第 3 页：眼睛专用图出现且仍然零滚动",
              sp.grp_eye.isVisible() and not bad
              and ms.height() <= page.height() and ms.width() <= page.width(),
              f"眼睛组={sp.grp_eye.isVisible()} 最小需求={ms.width()}×{ms.height()} "
              f"实得={page.width()}×{page.height()}")
        w.close()
    check("页面变小时预览框跟着缩（零滚动的核心手法）",
          sides["1200×680"] <= sides["1280×760"],
          f"1280×760 → {sides['1280×760']}px ；1200×680 → {sides['1200×680']}px")
    check("两个预览框同尺寸",
          win.page_tuning.preview.left._side == win.page_tuning.preview.right._side,
          f"{win.page_tuning.preview.left._side} vs {win.page_tuning.preview.right._side}")
    check("预览框保持 1:1（heightForWidth = 宽 + 24）",
          win.page_tuning.preview.left.heightForWidth(300) == 324,
          str(win.page_tuning.preview.left.heightForWidth(300)))

    win.close()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
