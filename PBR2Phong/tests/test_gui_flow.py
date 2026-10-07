"""GUI 全流程测试（离屏跑）：**"用户能自己从头跑完一遍"的机械版**。

模拟的操作顺序 —— 和真人点的一模一样：
    拖入素材文件夹 → 手填命名两栏 → 取消"写进游戏" → 点「开始转换」→ 等后台线程跑完
然后断言：表格状态变成"完成"、进度到 100%、三张 PNG + 三个 VTF + VMT 都真的落地了。

跑法：python tests/test_gui_flow.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
# 配置记忆测试要用一个**临时配置目录**，别污染用户真的 %APPDATA%\PBR2Phong
_TMP_HOME = Path(tempfile.mkdtemp(prefix="pbr2phong-home-"))
os.environ["PBR2PHONG_HOME"] = str(_TMP_HOME)

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from core import settings  # noqa: E402
from gui.main import Cancelled, ConvertWorker, MainWindow  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def need_l4d2_model():
    """公开仓库前提（14-D）：真实模型来自 **L4D2 安装** → 缺了就说明并跳过（返回 `None`），不许报红。

    哪些套件需要什么前提见 `README-工程说明.md`（"跑测试的前提"一节）。
    """
    mdl = Path(r"D:\SteamLibrary\steamapps\common\Left 4 Dead 2"
               r"\left4dead2\models\custom\school_gate.mdl")
    if mdl.is_file():
        return mdl
    print("   ⏭ 跳过 13-B 那几条：没找到 L4D2 的真实模型 school_gate.mdl（**公开仓库里属正常**）")
    print(f"      期望位置：{mdl}")
    return None


def preset_keys(cmb) -> list:
    """下拉里的**档位键**（13-F：显示名随语言变，键永远是中文原名 —— 认档位要认键）。"""
    return [cmb.itemData(i) or cmb.itemText(i) for i in range(cmb.count())]


def pick_preset(cmb, key: str):
    """按**键**选档（`setCurrentText` 在英文界面下会选不中 —— 那里文字是英文显示名）。"""
    idx = cmb.findData(key)
    if idx < 0:
        idx = cmb.findText(key)          # 兜底：万一某项没有 itemData
    if idx >= 0:
        cmb.setCurrentIndex(idx)
    return idx


# 形如 `settings.mode` / `attr.surfaceprop` 的**原始 i18n 键名**。
# 控件上出现它 = `t()` 里没这个键（或拼错了），界面上就会直接把键名怼给用户 —— 踩过一次。
_KEY_LOOKING = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def leaked_keys(win):
    """把四个页面上所有控件的文字扫一遍，找出"看起来像原始键名"的那些。"""
    out = []
    for i in range(win.tabs.count()):
        for w in win.tabs.widget(i).findChildren(QtWidgets.QWidget):
            text = ""
            if isinstance(w, (QtWidgets.QLabel, QtWidgets.QPushButton, QtWidgets.QCheckBox)):
                text = w.text()
            elif isinstance(w, QtWidgets.QGroupBox):
                text = w.title()
            text = (text or "").strip()
            if text and _KEY_LOOKING.match(text):
                out.append(f"第{i + 1}页 [{type(w).__name__}] {text}")
    return out


def main() -> int:
    print("== GUI 全流程（离屏）==")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow()
    win.resize(960, 700)
    win.show()
    app.processEvents()

    folder = WS / "测试素材" / "合成素材"
    check("合成素材存在", folder.is_dir(), str(folder))
    if not folder.is_dir():
        return 1

    page = win.page_convert
    exp = win.page_export
    # ⓪ 06 §2：**五页**结构 + 「开始转换」在第 4 页「导出」、没导入素材时必须是灰的
    check("标签页变成五页", win.tabs.count() == 5, str(win.tabs.count()))
    check("第 2 页叫「预览 + 调参」", "调参" in win.tabs.tabText(1), win.tabs.tabText(1))
    check("第 3 页是「参数表 / 材质属性 / 自由键值」",
          "参数表" in win.tabs.tabText(2), win.tabs.tabText(2))
    check("第 4 页是「导出」", "导出" in win.tabs.tabText(3), win.tabs.tabText(3))
    check("第 5 页是「关于」", "关于" in win.tabs.tabText(4), win.tabs.tabText(4))
    # §3/06 §4.4 硬规定：第 2、3 页不许再有任何"勾了才显示"的折叠组
    # （用户原话：后面预览要实时观测的啊）
    foldable = [g.title() for p in (win.page_tuning, win.page_config)
                for g in p.findChildren(QtWidgets.QGroupBox) if g.isCheckable()]
    check("第 2 / 3 页没有可折叠的组", not foldable, str(foldable))
    check("「调参模式」开关已消失", not hasattr(win.page_settings, "_on_advanced_toggled"))
    check("「材质属性」开关已消失", not hasattr(win.page_settings, "_on_attr_toggled"))
    # 界面上不许出现原始 i18n 键名（`t()` 少了键就会把键名怼给用户 —— S2.5 踩过一次）
    check("中文界面没有漏出原始键名", not leaked_keys(win), str(leaked_keys(win)))
    # 曲线那一行现在是**真的编辑器**（07 S4），不再是一句"还没做"的说明
    panel = win.page_tuning.panel
    win.page_settings.refresh_sources()
    check("曲线编辑器是真的（有控制点绘制，不是空壳）",
          hasattr(panel, "curve") and hasattr(panel.curve, "curve_points")
          and len(panel.curve._effective()) >= 3, str(panel.curve._effective()))
    check("没导入素材时「开始转换」是灰的", not win.btn_start.isEnabled())
    check("「开始转换」在第 4 页（不再是状态栏那个）",
          exp.isAncestorOf(win.btn_start), str(win.btn_start.parent()))
    # ① 拖入文件夹（直接调 load_folder，等同于拖放落到那个分支）
    page.load_folder(folder)
    app.processEvents()
    check(f"识别出素材（{len(page.sets)} 套）", len(page.sets) >= 1)
    check("导入素材后「开始转换」亮起", win.btn_start.isEnabled())
    check("表格按素材填了行", page.table.rowCount() == len(page.sets))
    check("还没跑过时不显示结果清单", not exp.grp_result.isVisibleTo(exp))

    # ② 手填命名两栏（走"还没有模型"那条路）
    page.rb_manual.setChecked(True)
    page.ed_cdm.setText("custom/gui_flow")
    page.ed_mat.setText("GuiFlow")
    app.processEvents()
    check("实时显示拼出的最终路径",
          "custom/gui_flow/GuiFlow" in page.lbl_final_path.text(), page.lbl_final_path.text())

    # ③ 只导出不部署（别动用户的游戏目录）—— 03 §3：这个开关跟「开始转换」一起在第 3 页
    exp.chk_deploy.setChecked(False)

    # ③b **13-B**：模型里的材质名要**看得见、选得中**（多材质模型"跑两次"时不用去别处翻 .mdl）
    # ⚠️ 14-D：这个模型来自 **L4D2 安装** → 缺了就说明并跳过（公开仓库里别人机器上必然没有），
    #    不许报红 —— "缺依赖一片红"会把真正的回归淹掉。
    mdl = need_l4d2_model()
    if mdl is None:
        pass
    else:
        page.ed_model.setText(str(mdl))
        app.processEvents()
        hint = page.lbl_model_hint.text()
        # ⚠️ 别硬编码材质名：用户 2026-10-07 把这个模型从"双材质"重导成了 `School_Gate00/01/02`
        #    （2026-09-25 那次是 `school_gate` + `school_gate_windows`）→ **从模型里读出什么就断言什么**。
        from core import naming as _naming
        want = [t for t in _naming.read_mdl(mdl).textures if t.lower() != "no_material"]
        check("13-B：① 页读模型会把**全部**材质名列出来",
              bool(want) and all(n in hint for n in want), f"模型里={want} 提示={hint[:160]}")
        # ⚠️ 13-B 返工（一类 2026-10-01）：这条**原来锁的是错的措辞**（"要分几次跑"）——
        #    实测是"一次转换就给每个名字各写一份 VMT、都指向本次这套贴图"，只有"不同材质槽配
        #    不同贴图"才需要分开跑。现在锁**正确的那半句**，并断言那句错的短语已经消失。
        # 15-C：多槽模型现在有**两种**说法 —— 「共用一套贴图」（13-B 的措辞）与「逐槽各配一套」
        #       → 两条都锁住（13-B 那条改成在"共用"模式下读，措辞要求逐字不变）
        page.rb_slots_shared.setChecked(True)
        app.processEvents()
        hint_shared = page.lbl_model_hint.text()
        check("13-B：共用一套贴图时说清「每个名字各写一份 VMT、都指向这次的贴图」",
              "各写一份 VMT" in hint_shared and "都指向" in hint_shared
              and "不同贴图" in hint_shared and "分几次跑" not in hint_shared,
              hint_shared.replace("\n", " / ")[:220])
        page.rb_slots_each.setChecked(True)
        app.processEvents()
        hint_each = page.lbl_model_hint.text()
        check("15-C：逐槽模式的说法换成「每个槽各写一份 VMT（各指各自贴图）」",
              "每个槽" in hint_each and "各指各自贴图" in hint_each, hint_each.replace("\n", " / ")[:220])
        check("13-B：材质名**可以选中复制**（不用去别处翻 MDL）",
              bool(page.lbl_model_hint.textInteractionFlags() & QtCore.Qt.TextSelectableByMouse),
              str(page.lbl_model_hint.textInteractionFlags()))
        page.ed_model.clear()
        app.processEvents()

    # ④ 点「开始转换」
    # ⚠️ 14-E：**这一段之后全都要真出 VTF** → 缺 VTFCmd（公开仓库 / CI 常态）就在这里**说明并打住**，
    #    前面那些纯界面检查照跑（不报红、也不假装跑过）。
    from core import vtf as _vtf
    if not _vtf.find_vtfcmd():
        print("   ⏭ 跳过转换段（从这里往后）：本机没有 VTFCmd.exe —— 界面检查已全部跑完")
        print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项（转换段已跳过）")
        return 1 if FAIL else 0
    # ⚠️ 13-C：`测试素材/GuiFlow_phong/` 里有上次留下的产物（指纹已变）→ 新闸门会**先问**
    #    （以前是死代码，直接静默覆盖）。这里**模拟用户点「覆盖」**，并把"它真的问了"记下来；
    #    不这么做，测试会卡在那个模态对话框上（worker 在 `_confirm` 里等 300s）。
    conflicts_seen = []

    def auto_overwrite(conflicts):
        conflicts_seen.append(list(conflicts))
        win.worker.provide_answer(True)              # 等价于用户在对话框上点「覆盖」

    win._on_conflicts = auto_overwrite
    win.start_conversion()
    check("开始后「开始转换」禁用、「取消」可用",
          not win.btn_start.isEnabled() and win.btn_cancel.isEnabled())

    deadline = time.time() + 300
    while win.worker is not None and win.worker.isRunning() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    for _ in range(5):
        app.processEvents()

    # 15-G（用户原话："目前的导入素材框里为啥要加个进度？？？转换结果都在导出页能看完了
    #       还用专门切回第一页检查？"）：第 ① 页那张表**一条状态都不留**，结果在第 ④ 页。
    headers = [page.table.horizontalHeaderItem(c).text() for c in range(page.table.columnCount())]
    print(f"     第①页表头：{headers}")
    print(f"     状态栏：{win.lbl_status.text()}  进度 {win.progress.value()}%")
    check("15-G：第 ① 页表格没有「进度」列", "进度" not in headers and "Progress" not in headers,
          str(headers))
    check("15-G：第 ① 页表格也没有「状态」列",
          "状态" not in headers and "Status" not in headers, str(headers))
    check("15-G：第 ① 页表格里没有任何状态字",
          not any(page.table.item(r, c) and page.table.item(r, c).text() in
                  (win.t("status.ready"), win.t("status.done_one"),
                   win.t("status.failed"), win.t("status.skipped"))
                  for r in range(page.table.rowCount())
                  for c in range(page.table.columnCount())),
          str([page.table.item(0, c).text() for c in range(page.table.columnCount())]))
    win.tabs.setCurrentIndex(3)                      # 人停在「④ 导出」页：**没切回第 1 页**
    app.processEvents()
    check("15-G：人在第 ④ 页（没切回第 ① 页）", win.tabs.currentIndex() == 3,
          str(win.tabs.currentIndex()))
    slots = [exp.tbl_result.item(r, 0).text() for r in range(exp.tbl_result.rowCount())]
    stats = [exp.tbl_result.item(r, 2).text() for r in range(exp.tbl_result.rowCount())]
    used = [exp.tbl_result.item(r, 1).text() for r in range(exp.tbl_result.rowCount())]
    print(f"     ④ 页结果表：{list(zip(slots, used, stats))}")
    check("15-G：第 ④ 页按材质槽逐行列出结果", bool(slots), str(slots))
    check("15-G：每槽都有状态", bool(stats) and all(s == win.t("status.done_one") for s in stats),
          str(stats))
    check("15-G：清单里有材质名 GuiFlow", any("GuiFlow" in s for s in slots), str(slots))
    check("进度到 100%", win.progress.value() == 100, str(win.progress.value()))
    check("结束后按钮恢复", win.btn_start.isEnabled() and not win.btn_cancel.isEnabled())
    # 13-C：GUI 侧证据 —— 撞上已有产物时，**真的把冲突交到用户面前了**（码 `exists`，不是人话）
    check("13-C：GUI 撞上已有产物时把冲突交给了用户（模拟点「覆盖」）",
          bool(conflicts_seen) and all(why in ("exists", "in_materials")
                                       for _rel, why in conflicts_seen[0]),
          str(conflicts_seen)[:200])

    out = folder.parent / "GuiFlow_phong"
    for name in ("GuiFlow_basecolor.png", "GuiFlow_normal.png", "GuiFlow_exp.png"):
        check(f"{name} 已生成", (out / name).is_file())
    for name in ("GuiFlow_basecolor.vtf", "GuiFlow_normal.vtf", "GuiFlow_exp.vtf"):
        check(f"vtf/{name} 已生成", (out / "vtf" / name).is_file())
    check("GuiFlow.vmt 已生成", (out / "GuiFlow.vmt").is_file())
    check("phong_input.json 已生成", (out / "phong_input.json").is_file())

    # 14-A：`log.txt` 必须是**人能读**的（core 只写码 → UI 层补一版渲染过的）
    log_txt = (out / "log.txt").read_text(encoding="utf-8-sig", errors="replace")
    rec = json.loads((out / "phong_input.json").read_text(encoding="utf-8-sig"))
    rec_warns = rec.get("警告") or []
    check("14-A：log.txt 里**没有裸的 code**（警告已渲染成人话）", '"code":' not in log_txt,
          str([ln.strip() for ln in log_txt.splitlines() if '"code"' in ln][:2]))
    check("14-A：机器凭据 `phong_input.json` 里仍是**码**（铁律：core 只写码）",
          all(isinstance(w, dict) and "code" in w for w in rec_warns) if rec_warns else True,
          str(rec_warns)[:160])
    check("14-A：每条警告在 log.txt 里都能找到对应的人话",
          all(any(i18n.warning(w, lg) in log_txt for lg in ("zh", "en")) for w in rec_warns)
          if rec_warns else True, f"原文={str(rec_warns)[:120]}")
    check("14-A：.vmt 那段还在（日志没被写残）", "--- .vmt ---" in log_txt)

    # ④b 结果清单 + log 摘要（03 §3 第 3 页：打开输出目录 / 打开日志 / 复制失败原因）
    check("跑完后出现结果清单", exp.grp_result.isVisibleTo(exp))
    check("汇总行与状态栏一致", exp.lbl_result.text() == win.lbl_status.text(),
          exp.lbl_result.text())
    check("清单里列了素材名",
          any("GuiFlow" in (exp.tbl_result.item(r, 0).text() or "")
              for r in range(exp.tbl_result.rowCount())),
          str([exp.tbl_result.item(r, 0).text() for r in range(exp.tbl_result.rowCount())]))
    check("清单里带了日志路径",
          bool(win.last_log) and win.last_log in exp.lbl_log_path.text(), exp.lbl_log_path.text())
    check("「打开输出目录」可用且指向产物",
          exp.btn_open_out.isEnabled() and win.last_out_dir == str(out), str(win.last_out_dir))
    check("「打开日志」可用", exp.btn_open_log.isEnabled(), str(win.last_log))
    check("没有失败项 → 「复制失败原因」禁用", not exp.btn_copy_fail.isEnabled())
    exp.copy_failures()                               # 点一下真的不炸，且真的进剪贴板
    check("复制失败原因走通了", bool(QtWidgets.QApplication.clipboard().text()),
          QtWidgets.QApplication.clipboard().text())

    # ⑤ 界面上改参数，真的会写进产物吗？（这是"接线对不对"的关键断言）
    sp = win.page_settings
    sp.cmb_sp.setCurrentIndex(sp.cmb_sp.findData("plastic"))
    sp.toggles["$nocull"].setChecked(True)
    sp.param_rows["boost"][1].setValue(80)           # 高光强度 → $phongboost ≈ 63
    app.processEvents()
    ov = sp.current_overrides()
    check("改过的东西进了覆盖项", "vmt.$phongboost" in ov and "vmt.$surfaceprop" in ov
          and "vmt.$nocull" in ov, str(ov))
    src = sp.src_table
    sources = [src.item(r, 2).text() for r in range(src.rowCount())]
    check("来源表出现『你改过』", any(s == "你改过" for s in sources), str(sources[:4]))

    page.ed_mat.setText("GuiFlow2")                  # 换个名字，免得被"跳过已成功"拦下
    win.start_conversion()
    deadline = time.time() + 300
    while win.worker is not None and win.worker.isRunning() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    for _ in range(5):
        app.processEvents()

    out2 = folder.parent / "GuiFlow2_phong"
    vmt2 = (out2 / "GuiFlow2.vmt").read_text(encoding="utf-8", errors="replace") \
        if (out2 / "GuiFlow2.vmt").is_file() else ""
    check("$phongboost 真的写进了 VMT", "$phongboost" in vmt2, vmt2.replace("\n", " ")[:120])
    check("$surfaceprop plastic 写进了 VMT", "$surfaceprop" in vmt2 and "plastic" in vmt2)
    check("$nocull 写进了 VMT", "$nocull" in vmt2)
    boost_value = win.page_settings.param_rows["boost"][1].value()
    expect = __import__("gui.main", fromlist=["x"]).slider_to_boost(boost_value)
    check(f"$phongboost 的值对得上滑杆（{expect}）", str(expect) in vmt2 or f"{expect:.0f}" in vmt2)

    # ⑤b 03 §2.5 ④ 刷新粒度：**拖动只更新数值、松手才重算**
    sl = sp.param_rows["boost"][1]
    keys = [sp.src_table.item(r, 0).text() for r in range(sp.src_table.rowCount())]
    idx = keys.index("vmt.$phongboost")
    before = sp.src_table.item(idx, 1).text()
    sl.setSliderDown(True)                           # 假装用户按住了滑杆
    sl.setValue(min(100, sl.value() + 20))
    app.processEvents()
    check("拖动中：数值显示跟手了", sp.lbl_values["boost"].text() != "",
          sp.lbl_values["boost"].text())
    check("拖动中：来源表没被重算（攒着）", sp.src_table.item(idx, 1).text() == before,
          f"{before} → {sp.src_table.item(idx, 1).text()}")
    sl.setSliderDown(False)
    sl.sliderReleased.emit()                         # 松手那一下才重算
    app.processEvents()
    check("松手后重算了一次", sp.src_table.item(idx, 1).text() != before,
          f"{before} → {sp.src_table.item(idx, 1).text()}")

    # ⑥ 「恢复继承」要把所有改动清掉
    sp.reset_overrides()
    app.processEvents()
    check("恢复继承后没有覆盖项", sp.current_overrides() == {}, str(sp.current_overrides()))
    check("恢复继承后来源表没有『你改过』",
          all(sp.src_table.item(r, 2).text() != "你改过" for r in range(sp.src_table.rowCount())))

    # ⑦ 配置记忆：改过的东西关掉再开还在吗？
    check("首次运行把配置目录建好了", (Path(win.config_root) / "config.json").is_file(),
          win.config_root)
    check("五套内置预设已导出", len(settings.load_presets(win.config_root)) >= 5)
    win.set_language("en")                           # 右上角语言按钮的等价入口
    check("英文界面没有漏出原始键名", not leaked_keys(win), str(leaked_keys(win)))
    exp.chk_deploy.setChecked(False)
    win.save_prefs()
    prefs = settings.load_gui_prefs(win.config_root)
    check("偏好写进了 gui.json", prefs.get("语言") == "en" and prefs.get("直接写进游戏") is False,
          str(prefs))
    win2 = MainWindow()                              # 新开一个窗口 = 模拟"下次打开程序"
    app.processEvents()
    check("新窗口读回了语言", win2.lang == "en", win2.lang)
    check("新窗口读回了勾选", win2.page_export.chk_deploy.isChecked() is False)
    check("新窗口读回了上次素材目录",
          win2.page_convert.folder is not None and len(win2.page_convert.sets) == len(page.sets),
          str(win2.page_convert.folder))

    # ⑧ 保存预设：自己存一套，能出现在下拉里、能解析出值
    settings.save_preset(win.config_root, "我的测试预设", {"vmt.$phongboost": 7.5}, desc="t")
    sp.reload_presets(keep="我的测试预设")
    app.processEvents()
    check("自定义预设出现在下拉里", sp.cmb_preset.findData("我的测试预设") >= 0,
          str(preset_keys(sp.cmb_preset)))
    r_custom = settings.resolve("我的测试预设", {}, {}, sp._presets)
    check("自定义预设的值生效", r_custom.values.get("vmt.$phongboost") == 7.5,
          str(r_custom.values.get("vmt.$phongboost")))
    check("切到自定义预设后来源表指向它",
          any("我的测试预设" in (sp.src_table.item(r, 2).text() or "")
              for r in range(sp.src_table.rowCount())))

    # ⑨ 工具路径：VTFCmd 能自动找到；手动指定优先；且真会被用上
    #    （03 §3：这条路径按新布局挪到了**第 1 页**）
    check("VTFCmd 自动找到了（本机装了 VTFEdit Reloaded）",
          "VTFCmd" in page.current_vtfcmd(), page.current_vtfcmd())
    page.ed_vtfcmd.setText(r"C:\假路径\VTFCmd.exe")
    check("手动指定会盖过自动检测", page.current_vtfcmd() == r"C:\假路径\VTFCmd.exe")
    check("没手动指定时 hint 会自动找", "没找到" not in page.lbl_vtfcmd.text(), page.lbl_vtfcmd.text())
    check("VTFCmd 路径框在第 1 页（不是第 2 页）", page.isAncestorOf(page.ed_vtfcmd))
    page.ed_vtfcmd.setText("")
    check("清空后又回到自动检测", "VTFCmd" in page.current_vtfcmd())

    # ⑩ 取消：慢阶段之间要有检查点，否则按了取消要傻等一整套跑完
    w0 = ConvertWorker([], None, None, None, None, {})
    w0._cancel = True
    try:
        w0._progress(0, "通道打包", 0.1)
        check("取消检查点会中断当前素材", False, "没抛 Cancelled")
    except Cancelled:
        check("取消检查点会中断当前素材", True)
    w0._cancel = False
    w0._progress(0, "通道打包", 0.1)                 # 没取消时不能乱抛
    check("没按取消时检查点放行", True)

    # ⑪ 透明开关跟着档走（09 单）：切到「植被」自动勾上，切走自动去掉 ——
    #    不这么拨的话，从「植被」切走会留一条**看不见的** $alphatest 覆盖项。
    if sp.cmb_preset.findData("植被") >= 0 and sp.cmb_preset.findData("道具") >= 0:
        pick_preset(sp.cmb_preset, "植被")
        app.processEvents()
        check("切到「植被」档 → 透明开关自动勾上", sp.chk_cutout.isChecked() is True)
        check("「植被」档勾着不算「你改过」（它是预设自带的）",
              "alpha.cutout" not in sp.current_overrides(),
              str(sp.current_overrides()))
        pick_preset(sp.cmb_preset, "道具")
        app.processEvents()
        check("从「植被」切到「道具」→ 开关自动去掉",
              sp.chk_cutout.isChecked() is False)
        check("切档后不会凭空产出 alpha.cutout 覆盖项",
              "alpha.cutout" not in sp.current_overrides(),
              str(sp.current_overrides()))
    else:
        check("模型路线里有「植被」「道具」两档", False, str(preset_keys(sp.cmb_preset)))

    # ⑫ 10 片 §2.1：切档 = 把这一档的**材质属性整组**重放（表面类型 + 5 个常用开关 + 要透明），
    #    而**观感旋钮（滑杆 / 曲线）不跟档走**（它们是素材级微调）。
    switch_ok = True
    if switch_ok:
        win.page_convert.rb_route_brush.setChecked(True)          # 笔刷路线才有玻璃/金属这些档
        app.processEvents()
        brush_names = preset_keys(sp.cmb_preset)
        switch_ok = all(n in brush_names for n in ("玻璃·窗户", "贴花", "金属"))
    if switch_ok:
        pick_preset(sp.cmb_preset, "贴花")
        app.processEvents()
        check("切到「贴花」→ 反射遮罩建议取消勾选", win.page_convert.chk_brush_mask.isChecked() is False)
        pick_preset(sp.cmb_preset, "玻璃·窗户")
        app.processEvents()
        check("切到「玻璃·窗户」→ 反射遮罩建议勾上", win.page_convert.chk_brush_mask.isChecked() is True)
        check("切到「玻璃·窗户」→ 表面类型变成 glass",
              sp.cmb_sp.currentData() == "glass", str(sp.cmb_sp.currentData()))
        check("整组跟档走**不算「你改过」**（继承值不是覆盖项）",
              not [k for k in sp.current_overrides()
                   if k in ("vmt.$surfaceprop", "alpha.cutout") or k.startswith("vmt.$")],
              str(sp.current_overrides())[:160])

        # 判据 3：观感旋钮保持用户值（切档不许顺手动它们）
        panel = win.page_tuning.panel
        panel.sl_sharp.setValue(80)
        app.processEvents()
        sharp = sp.current_overrides().get("curve.sharpness_gain")
        check("先调开「高光锐度」→ 记进覆盖项", sharp is not None, str(sharp))
        pick_preset(sp.cmb_preset, "金属")
        app.processEvents()
        check("切档之后「高光锐度」还是用户的值（观感旋钮不跟档走）",
              sp.current_overrides().get("curve.sharpness_gain") == sharp,
              f"{sharp} → {sp.current_overrides().get('curve.sharpness_gain')}")
        check("同一刀切档后表面类型跟着换（metal）",
              sp.cmb_sp.currentData() == "metal", str(sp.cmb_sp.currentData()))
        win.page_config.reset_overrides()
    else:
        check("笔刷路线里有「玻璃·窗户」「贴花」「金属」三档", False,
              str(preset_keys(sp.cmb_preset)))

    # ⑫b **11 片 §2.2**：切**路线**（模型 ↔ 笔刷）也不动观感旋钮 —— 只重放材质属性。
    #     做法：先记下"你真的动过的" → 重放新档继承值 → 再把你的值盖回去。
    #     ⚠️ 没动过的**跟着新路线走**（否则界面显示旧值、产出却是新档继承值 = 假控件）。
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    panel.sl_sharp.setValue(80)
    panel.sl_offset.setValue(70)
    panel.curve.set_points([(0.0, 0.0), (0.25, 0.25), (0.5, 0.2), (0.75, 0.75), (1.0, 1.0)])
    app.processEvents()
    before = dict(sp.current_overrides())
    check("切路线前：锐度 / 粗糙度偏移 / 曲线点都记进覆盖项",
          all(k in before for k in ("curve.sharpness_gain", "curve.roughness_offset",
                                    "curve.curve_points")),
          str(before)[:200])
    win.page_convert.rb_route_brush.setChecked(True)
    app.processEvents()
    after = dict(sp.current_overrides())
    check("切到笔刷路线：「高光锐度」还是用户的值",
          after.get("curve.sharpness_gain") == before.get("curve.sharpness_gain"),
          f"{before.get('curve.sharpness_gain')} → {after.get('curve.sharpness_gain')}")
    check("切到笔刷路线：「粗糙度整体偏移」还是用户的值",
          after.get("curve.roughness_offset") == before.get("curve.roughness_offset"),
          f"{before.get('curve.roughness_offset')} → {after.get('curve.roughness_offset')}")
    check("切到笔刷路线：曲线点还在",
          after.get("curve.curve_points") == before.get("curve.curve_points"),
          str(after.get("curve.curve_points"))[:120])
    check("切到笔刷路线：滑杆位置没被拨回（锐度还在 80）",
          panel.sl_sharp.value() == 80, str(panel.sl_sharp.value()))
    inh = sp._inherited()
    check("切路线后材质属性整组 = **新档**继承值（表面类型 + 5 开关 + 要透明）",
          (sp.cmb_sp.currentData() or "") == str(inh.get("vmt.$surfaceprop", ""))
          and all(bool(cb.isChecked()) == bool(inh.get(f"vmt.{k}")) for k, cb in sp.toggles.items())
          and bool(sp.chk_cutout.isChecked()) == bool(inh.get("alpha.cutout", False)),
          f"sp={sp.cmb_sp.currentData()} vs 继承 {inh.get('vmt.$surfaceprop')}")
    check("切路线**不会**凭空多出「你改过」的材质属性覆盖项",
          not [k for k in after if k.startswith("vmt.$") or k == "alpha.cutout"],
          str(after)[:200])
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    back = dict(sp.current_overrides())
    check("切回模型路线：锐度 / 偏移 / 曲线点一个都没丢（来回切都不丢）",
          all(back.get(k) == before.get(k) for k in
              ("curve.sharpness_gain", "curve.roughness_offset", "curve.curve_points")),
          str(back)[:200])
    win.page_config.reset_overrides()

    # ⑬ 10 片 §2.2：alpha.cutout 进参数表 —— 勾了要看得见「你改过」（判据 4）
    win.set_language("zh")                    # 前面几段把它切到英文过，这里看中文口径
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    pick_preset(sp.cmb_preset, "道具")
    app.processEvents()
    keys = [sp.src_table.item(r, 0).text() for r in range(sp.src_table.rowCount())]
    check("参数表 13 行且含 alpha.cutout", len(keys) == 13 and "alpha.cutout" in keys, str(keys))
    row_i = sp.src_table.rowCount() - 1
    check("alpha.cutout 默认没勾 → 来源是「全局默认」",
          sp.src_table.item(row_i, 2).text() == "全局默认", sp.src_table.item(row_i, 2).text())
    sp.chk_cutout.setChecked(True)
    app.processEvents()
    check("勾上 alpha.cutout → 参数表来源变「你改过」",
          sp.src_table.item(row_i, 2).text() == "你改过", sp.src_table.item(row_i, 2).text())
    check("勾上 alpha.cutout → 当前值变 True",
          sp.src_table.item(row_i, 1).text() == "True", sp.src_table.item(row_i, 1).text())
    sp.reset_overrides()
    pick_preset(sp.cmb_preset, "植被")
    app.processEvents()

    # ⑭ 15-D：多文件夹拖入要**累加**（用户原话："我想通过放置多个文件夹进去达成添加素材都不行"）
    drop_root = Path(tempfile.mkdtemp(prefix="pbr2phong-drop-"))
    d1, d2 = drop_root / "SetA", drop_root / "SetB"
    for d, stem in ((d1, "DropA"), (d2, "DropB")):
        d.mkdir(parents=True)
        (d / f"{stem}-BaseColor-8.png").write_bytes(b"x")   # scan_folder 只看后缀，不读内容
    before = len(page.sets)

    def drop(paths):
        """真发一个 drop 事件（= 用户把文件夹拖进那个框），走的就是 `eventFilter` 那条路。"""
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(str(p)) for p in paths])
        ev = QtGui.QDropEvent(QtCore.QPointF(8, 8), QtCore.Qt.CopyAction, mime,
                              QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
        page.eventFilter(page.drop, ev)
        app.processEvents()

    drop([d1, d2])
    check("15-D：一次拖 2 个目录 → 两套都加进来了", len(page.sets) - before == 2,
          f"{before} → {len(page.sets)}")
    check("15-D：表格跟着长（行数 = 套数）", page.table.rowCount() == len(page.sets))
    check("15-D：状态行说「已加 N 套 / 共 M 套」",
          f"共 {len(page.sets)} 套" in page.lbl_recognized.text(), page.lbl_recognized.text())
    drop([d1])                                          # 同一个目录再拖一次
    check("15-D：同一目录拖两次 → 仍是一套（按绝对路径去重）", len(page.sets) - before == 2,
          f"{before} → {len(page.sets)}")
    page.table.selectRow(0)
    page.remove_selected()
    app.processEvents()
    check("15-D：删掉一套后剩一套", len(page.sets) - before == 1, f"剩 {len(page.sets) - before}")
    check("15-D：表格也跟着掉一行", page.table.rowCount() == len(page.sets))

    # ⑮ 15-C：材质槽 ↔ 素材（真模型 + 每个槽一套素材）
    mdl = need_l4d2_model()
    if mdl is None:
        print("   ⏭ 跳过 15-C 那段：没找到 L4D2 的真实模型 school_gate.mdl（公开仓库里属正常）")
    else:
        from core import naming as _naming
        slots_all = [t for t in _naming.read_mdl(mdl).textures if t.lower() != "no_material"]
        slots_tmp = Path(tempfile.mkdtemp(prefix="pbr2phong-slots-"))
        for idx, slot in enumerate(slots_all):
            d = slots_tmp / slot
            d.mkdir(parents=True)
            # 每套给个**不一样的亮度** → 后面"切槽预览像素会变"才测得出真东西
            from core import imaging as _im
            _im.save(np.dstack([np.full((8, 8), 40 + 60 * idx, np.uint8)] * 3),
                     d / f"{slot}-BaseColor-8.png")
        page.load_folder(slots_tmp)                 # 一次导入好几套（15-D 的累加）
        page.ed_model.setText(str(mdl))
        app.processEvents()
        check("15-C：模型有多个槽 → 出现「材质槽 ↔ 素材」这一块",
              page.grp_slots.isVisibleTo(page), str(page.grp_slots.isVisibleTo(page)))
        shown = [page.slot_table.item(r, 0).text() for r in range(page.slot_table.rowCount())]
        check("15-C：列出**全部**材质槽（不止第一个）", set(shown) == set(slots_all),
              f"模型里={slots_all} 表里={shown}")
        check("15-C：默认「每个槽各配一套素材」", page.rb_slots_each.isChecked())
        jobs = page.slot_jobs() or []
        check("15-C：按「素材组名 ↔ 槽名」自动填好了",
              len(jobs) == len(slots_all) and {j[0] for j in jobs} == set(slots_all),
              str([(s, ms.group) for s, ms in jobs]))
        page.rb_slots_shared.setChecked(True)
        app.processEvents()
        check("15-C：切「所有槽共用一套贴图」→ 不再按槽分活", page.slot_jobs() is None)
        page.rb_slots_each.setChecked(True)
        page.ed_model.clear()                       # 清掉模型 → 这一块要收起来（免得赖着不走）
        app.processEvents()
        check("15-C：模型清空后这一块收起（槽名不留残影）",
              not page.grp_slots.isVisibleTo(page) and not page._model_names,
              str(page._model_names))

        # ⑯ 15-C **返工**（用户 2026-10-08 实机）：底色改名成认不出的 → 手选之后
        #    预览与转换必须**用同一份数据**（以前预览读另一份 → "我明明选了还说没有"）
        print("== 15-C 返工：手选底色 ==")
        from gui.main import SlotPickerDialog
        from core import source_io as _sio

        rw = Path(tempfile.mkdtemp(prefix="pbr2phong-rework-"))
        d = rw / "School_Gate00"
        d.mkdir(parents=True)
        from core import imaging as _imaging
        for name in ("School_Gate00-Roughness-8.png", "School_Gate00-shaded-8.png"):
            _imaging.save(np.dstack([np.full((8, 8), 128, np.uint8)] * 3), d / name)
        renamed = d / "School_Gate00-shaded-8.png"                  # ← 底色改名成**认不出的**
        check("15-C 返工：改名的底色确实认不出来（前提对）",
              _sio.parse_filename(renamed.name)[0] is None,
              str(_sio.parse_filename(renamed.name)))

        page.sets.clear()                           # 前面那几段留下的同名素材别混进来
        page._set_folders.clear()
        page._added_folders.clear()
        page.slot_state.clear()
        page.current_slot = ""
        page.load_folder(rw)
        page.ed_model.setText(str(mdl))
        app.processEvents()
        slot = "School_Gate00"
        target = (page.slot_state.get(slot) or {}).get("set")
        check("15-C 返工：这一套落在槽上（自动匹配到组名）", target is not None, str(target))
        check("15-C 返工：自动匹配来的那套**没有**底色（缺陷现场）",
              target is not None and target.get("shader.base_color") is None,
              str(None if target is None else sorted(target.images)))
        # 15-C 缺陷 D：**认不出的那张必须被看见**（列在表里 + 状态行说出来）
        check("15-C D：认不出的图进了 `unknown`（不再被静默丢掉）",
              target is not None and [Path(p).name for p in target.unknown] == [renamed.name],
              str(None if target is None else [Path(p).name for p in target.unknown]))
        page.table.selectRow(0)
        app.processEvents()
        cell = page.table.item(0, 2).text()
        check("15-C D：导入表里列出它、并标明「认不出是什么」",
              renamed.name in cell and "认不出" in cell, cell[:80])
        check("15-C D：状态行如实说「有 1 张没认出」",
              "1 张没认出" in page.lbl_recognized.text(), page.lbl_recognized.text())
        check("15-C D：「指定类型…」按钮在有认不出的图时可用", page.btn_assign_type.isEnabled())

        # 打开配图窗（不走文件对话框：直接喂文件夹），只手动选「基础色」那一栏
        dlg = SlotPickerDialog(win, slot, parent=page, target=target, folder=d)
        base_row = dlg.rows[0]
        check("15-C 返工：认不出类型时**醒目提示**「基础色必填」",
              dlg.lbl_warn.isVisible() or bool(dlg.lbl_warn.text()),
              f"visible={dlg.lbl_warn.isVisible()} text={dlg.lbl_warn.text()[:40]}")
        check("15-C 返工：认不出的那栏自动预选是空的（等人手选）",
              base_row[1].currentData() is None, str(base_row[1].currentData()))
        base_row[1].setCurrentIndex(base_row[1].findData(str(renamed)))
        boxes = []
        old_info = QtWidgets.QMessageBox.information
        QtWidgets.QMessageBox.information = staticmethod(
            lambda *a, **k: boxes.append([str(x) for x in a]))
        try:
            dlg.on_ok()
        finally:
            QtWidgets.QMessageBox.information = old_info
        check("15-C 返工：选好基础色后确定放行（没弹拦截框）",
              not boxes and dlg.result_set is not None, str(boxes)[:120])
        check("15-C 返工：改的就是**同一份**素材数据（不是另造一份）",
              dlg.result_set is target, f"{dlg.result_set} vs {target}")

        page.slot_state[slot]["set"] = dlg.result_set
        page.slot_state[slot]["label"] = dlg.result_label
        page.slot_state[slot]["folder"] = d
        page.current_slot = slot
        page.rebuild_slots()
        win.page_tuning.preview.cmb_kind.setCurrentIndex(
            win.page_tuning.preview.cmb_kind.findData("basecolor"))
        win.refresh_preview(force=True)
        app.processEvents()
        check("15-C 返工：预览与转换同源（预览拿的就是槽那套）",
              page.slot_set() is target, str(page.slot_set()))
        check("15-C 返工：预览**立刻**能看到那张底色（不再是「没有这张图」）",
              win.page_tuning.preview.right.has_image,
              win.page_tuning.preview.right.canvas.text()[:60].replace("\n", "⏎"))
        rw_jobs = {s: ms for s, ms in (page.slot_jobs() or [])}
        check("15-C 返工：转换那一路拿到的也是同一份、且已带底色",
              rw_jobs.get(slot) is target
              and rw_jobs[slot].get("shader.base_color") == renamed,
              str(rw_jobs.get(slot) and rw_jobs[slot].get("shader.base_color")))

        # ③ 基础色留空 → 确定必须被拦住（人话）
        dlg2 = SlotPickerDialog(win, slot, parent=page, target=None, folder=d)
        boxes2 = []
        QtWidgets.QMessageBox.information = staticmethod(
            lambda *a, **k: boxes2.append([str(x) for x in a]))
        try:
            dlg2.on_ok()
        finally:
            QtWidgets.QMessageBox.information = old_info
        check("15-C 返工：基础色没选 → 确定被拦住",
              len(boxes2) == 1 and dlg2.result_set is None, str(boxes2)[:160])
        check("15-C 返工：拦住时说人话（点名「基础色」）",
              bool(boxes2) and "基础色" in boxes2[0][2], str(boxes2)[:160])

        # 15-C 缺陷 D：**手工指定类型**这条路（单独造一套，免得跟上面对上）
        da = Path(tempfile.mkdtemp(prefix="pbr2phong-assign-")) / "School_Gate02"
        da.mkdir(parents=True)
        _imaging.save(np.dstack([np.full((8, 8), 200, np.uint8)] * 3),
                      da / "School_Gate02-Roughness-8.png")
        weird = da / "School_Gate02-basemap-weird-1k.png"
        _imaging.save(np.dstack([np.full((8, 8), 90, np.uint8)] * 3), weird)
        page.sets.clear()
        page._set_folders.clear()
        page._added_folders.clear()
        page.load_folder(da.parent)
        page.table.selectRow(0)
        app.processEvents()
        ms2 = page.sets[0]
        check("15-C D：这一套认不出那张进了 unknown", [Path(p).name for p in ms2.unknown] == [weird.name],
              str([Path(p).name for p in ms2.unknown]))

        def fake_exec(self):                      # 「确定」= 选成底色的那个类型
            self.cmb_type.setCurrentIndex(self.cmb_type.findData("shader.base_color"))
            self.on_ok()
            return 1

        real_exec2 = QtWidgets.QDialog.exec
        QtWidgets.QDialog.exec = fake_exec
        try:
            page.assign_type_dialog(preselect=weird.name)
        finally:
            QtWidgets.QDialog.exec = real_exec2
        app.processEvents()
        check("15-C D：手工指定类型后它变成正常素材（进了 images）",
              ms2.get("shader.base_color") == weird, str(ms2.get("shader.base_color")))
        check("15-C D：指定完就不再算「没认出」（unknown 清掉、状态行也不再提）",
              not ms2.unknown and "没认出" not in page.lbl_recognized.text(),
              f"unknown={ms2.unknown} 状态行={page.lbl_recognized.text()}")
        check("15-C D：表格里它挪到「认到的图」那一格、不再挂在「没认出的」",
              weird.name not in page.table.item(0, 2).text()
              and "底色" in page.table.item(0, 1).text(),
              f"{page.table.item(0, 1).text()} ｜ {page.table.item(0, 2).text()}")
        page.ed_model.clear()
        app.processEvents()

        # ⑰ 15-H：第 ②/③ 页按材质槽分开编辑
        print("== 15-H：逐槽参数 ==")
        per = Path(tempfile.mkdtemp(prefix="pbr2phong-perslot-"))
        for idx, slot in enumerate(slots_all):
            d = per / slot
            d.mkdir(parents=True)
            _imaging.save(np.dstack([np.full((8, 8), 40 + 60 * idx, np.uint8)] * 3),
                          d / f"{slot}-BaseColor-8.png")
        page.sets.clear()
        page._set_folders.clear()
        page._added_folders.clear()
        page.slot_state.clear()
        page.current_slot = ""
        page.load_folder(per)
        page.ed_model.setText(str(mdl))
        app.processEvents()
        cfg = win.page_config
        preview = win.page_tuning.preview
        check("15-H：第 ② 页出现「正在编辑的槽」", win.page_tuning.cmb_slot.isVisibleTo(win.page_tuning))
        check("15-H：第 ③ 页也有，且列全部槽",
              cfg.cmb_slot.isVisibleTo(cfg)
              and [cfg.cmb_slot.itemData(i) for i in range(cfg.cmb_slot.count())] == slots_all,
              str([cfg.cmb_slot.itemData(i) for i in range(cfg.cmb_slot.count())]))
        a, b = slots_all[0], slots_all[1]
        check("15-H：默认编辑第一个槽", page.current_slot == a, page.current_slot)
        # 15-H 返工：切换器要在**右边**（贴参数列），不许横在页面顶部
        win.tabs.setCurrentIndex(1)                  # 先真的切到第 ② 页，布局才算得出来
        for _ in range(3):
            app.processEvents()
        pos = win.page_tuning.cmb_slot.mapTo(win.page_tuning, QtCore.QPoint(0, 0))
        check("15-H 返工：切换器贴在**右边**那一列（在预览区右侧）",
              pos.x() > win.page_tuning.preview.width(),
              f"槽下拉 x={pos.x()} 预览宽={win.page_tuning.preview.width()}")
        win.tabs.setCurrentIndex(0)
        app.processEvents()
        # 15-H 返工2：第 ③ 页那个槽下拉要在**左边**（第 ② 页的保持右边）
        win.tabs.setCurrentIndex(2)
        for _ in range(3):
            app.processEvents()
        pos3 = cfg.cmb_slot.mapTo(cfg, QtCore.QPoint(0, 0))
        check("15-H 返工2：第 ③ 页的槽下拉在**左边**",
              pos3.x() < cfg.width() // 2, f"x={pos3.x()} 页宽={cfg.width()}")
        win.tabs.setCurrentIndex(0)
        app.processEvents()
        cfg.cmb_sp.setCurrentIndex(cfg.cmb_sp.findData("metal"))
        app.processEvents()
        check("15-H：表面类型记在 A 槽名下",
              win.overrides_for(a).get("vmt.$surfaceprop") == "metal", str(win.overrides_for(a)))
        win.set_edit_slot(b)
        app.processEvents()
        check("15-H：切到 B 槽 → B 没被 A 的表面类型污染",
              win.overrides_for(b).get("vmt.$surfaceprop") is None, str(win.overrides_for(b)))
        check("15-H：界面也回到继承值（不是 A 那个）",
              cfg.cmb_sp.currentData() != "metal", str(cfg.cmb_sp.currentData()))
        panel.sl_sharp.setSliderDown(True)
        panel.sl_sharp.setValue(90)
        panel.sl_sharp.setSliderDown(False)
        panel.sl_sharp.sliderReleased.emit()
        app.processEvents()
        check("15-H：B 槽自己的锐度被记下来",
              "curve.sharpness_gain" in win.overrides_for(b), str(win.overrides_for(b)))
        win.set_edit_slot(a)
        app.processEvents()
        check("15-H：切回 A 槽 → A 的表面类型还在", cfg.cmb_sp.currentData() == "metal",
              str(cfg.cmb_sp.currentData()))
        check("15-H：A 槽的滑杆**没落到** B 槽（A 的锐度不是 B 那个 90）",
              panel.param_rows["sharpness"][1].value() != 90,
              f"A 的锐度={panel.param_rows['sharpness'][1].value()} B 的=90")
        check("15-H：A 槽自己没有那条锐度覆盖",
              "curve.sharpness_gain" not in win.overrides_for(a), str(win.overrides_for(a)))
        win.set_edit_slot(b)
        app.processEvents()
        img_b = np.array(preview.right.image_array) if preview.right.has_image else None
        win.set_edit_slot(a)
        app.processEvents()
        img_a = np.array(preview.right.image_array) if preview.right.has_image else None
        check("15-H：切槽后预览像素随之变化", img_a is not None and img_b is not None
              and not np.array_equal(img_a, img_b), f"A/B 都出图={img_a is not None and img_b is not None}")
        page.ed_model.clear()
        app.processEvents()
        check("15-H：模型清空 → 切换器收起",
              not win.page_tuning.cmb_slot.isVisibleTo(win.page_tuning)
              and not cfg.cmb_slot.isVisibleTo(cfg))

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"   失败：{f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    # 用 os._exit 直接退：Qt 的 offscreen 插件在解释器收尾时会崩一下，
    # 导致明明全绿却返回 1（会让脚本化的调用误判）。
    code = main()
    sys.stdout.flush()
    os._exit(code)
