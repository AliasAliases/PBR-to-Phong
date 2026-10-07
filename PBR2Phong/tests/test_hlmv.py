# -*- coding: utf-8 -*-
"""施工单 `_task/02-HLMV按钮.md` 的单测：路径解析四态 + `Popen` 参数表 + 人话提示。

判据（§6）：
  1. 路径解析：默认 / 已配置 / 缺失（+ 我加的"配了但不在→回退默认"）= 四种都要出人话文案
  2. `Popen` 参数表：断言里要能看出**没捕获输出、没 `-screenshot`、没等待**
  3. 找不到 `hlmv.exe` 时界面给的是人话，不是 traceback
  4. 回归不掉（既有 185 项）—— 由外部跑其它套件

跑法：`python tests/test_hlmv.py`
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))          # PBR2Phong/

from PySide6 import QtWidgets  # noqa: E402

import gui.main as gui_main  # noqa: E402
from core import settings  # noqa: E402

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


def test_resolve():
    print("\n== §6.1 路径解析（四种来源）==")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        default = settings.default_hlmv_path(root)
        check("默认路径 = <L4D2>\\bin\\hlmv.exe", default.endswith("bin\\hlmv.exe") or default.endswith("bin/hlmv.exe"),
              default)

        # ① 没配 + 默认不在 → missing
        path, kind = settings.resolve_hlmv_path("", root)
        check("① 没配、默认也不在 → missing 且路径为空", (path, kind) == ("", "missing"), f"{path} / {kind}")

        # ② 没配 + 默认在 → default
        (root / "bin").mkdir()
        (root / "bin" / "hlmv.exe").write_bytes(b"MZ")
        path, kind = settings.resolve_hlmv_path("", root)
        check("② 没配、默认在 → default 并用默认路径", kind == "default" and path == default, f"{path} / {kind}")

        # ③ 配了 + 文件在 → configured
        mine = root / "我的HLMV.exe"
        mine.write_bytes(b"MZ")
        path, kind = settings.resolve_hlmv_path(str(mine), root)
        check("③ 配了且在 → configured，用指定的那个", kind == "configured" and path == str(mine),
              f"{path} / {kind}")

        # ④ 配了 + 不在 + 默认在 → fallback_default（悄悄退回默认，但界面要说明）
        path, kind = settings.resolve_hlmv_path(str(root / "不存在.exe"), root)
        check("④ 配了但不在 → fallback_default 并退回默认", kind == "fallback_default" and path == default,
              f"{path} / {kind}")

        # ⑤ 配了 + 不在 + 默认也不在 → missing
        (root / "bin" / "hlmv.exe").unlink()
        path, kind = settings.resolve_hlmv_path(str(root / "不存在.exe"), root)
        check("⑤ 两边都不在 → missing", (path, kind) == ("", "missing"), f"{path} / {kind}")

        # 人话文案：四种都用同一套 key，且都带路径
        for k, key in (("configured", "hlmv.hint_configured"), ("default", "hlmv.hint_default"),
                       ("fallback_default", "hlmv.hint_fallback_default"), ("missing", "hlmv.hint_missing")):
            zh = gui_main.i18n.t(key, "zh", path="X:\\L4D2\\bin\\hlmv.exe")
            en = gui_main.i18n.t(key, "en", path="X:\\L4D2\\bin\\hlmv.exe")
            check(f"人话文案 {k}：中英都有、都带路径",
                  "hlmv.exe" in zh and "hlmv.exe" in en and zh != en, f"{zh[:40]}…")


def test_gui_and_popen():
    print("\n== §6.2/6.3 GUI 接线 + Popen 参数表 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-hlmv-")
    QtWidgets.QMessageBox.information = staticmethod(_fake_box("info"))
    QtWidgets.QMessageBox.warning = staticmethod(_fake_box("warn"))
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = gui_main.MainWindow()
    win.show()
    app.processEvents()
    page = win.page_convert

    check("转换页有路径那一组（HLMV 路径框 + 浏览 + 按钮）",
          all(hasattr(page, n) for n in ("grp_paths", "ed_hlmv", "btn_hlmv_pick", "btn_hlmv_run")))
    # 03 §2.5 ③：HLMV 与 VTFCmd 两格**合成一个「路径」组**（不再各组一个框）
    check("两格路径合成了一个组",
          page.grp_paths.isAncestorOf(page.ed_hlmv)
          and page.grp_paths.isAncestorOf(page.ed_vtfcmd)
          and not hasattr(page, "grp_tools"))
    check("这一组的标题是「路径」", page.grp_paths.title() == win.t("paths.title"),
          page.grp_paths.title())
    check("按钮文案是「用 HLMV 看看」", page.btn_hlmv_run.text() == win.t("hlmv.run"),
          page.btn_hlmv_run.text())
    check("提示里有默认路径（本机装了 L4D2 就能自动找到）",
          "hlmv.exe" in page.lbl_hlmv_hint.text(), page.lbl_hlmv_hint.text())

    # ③ 找不到 HLMV：必须是人话，不是 traceback
    BOXES.clear()
    page.hlmv_path = lambda: ("", "missing")
    page.ed_model.setText("")                      # 故意连模型也没填
    page.run_hlmv()
    check("找不到 HLMV 时弹的是人话（含默认路径 + 让他指定）",
          len(BOXES) == 1 and "hlmv.exe" in BOXES[0][2] and "浏览" in BOXES[0][2],
          str(BOXES)[:160])

    # 有 HLMV 但没模型 → 另一句人话
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "hlmv.exe"
        exe.write_bytes(b"MZ")
        page.hlmv_path = lambda: (str(exe), "configured")
        BOXES.clear()
        page.ed_model.setText("")
        page.run_hlmv()
        check("没有模型时提示「先选一个 .mdl」",
              len(BOXES) == 1 and ".mdl" in BOXES[0][2], str(BOXES)[:160])

        # ② 正常路径：抓 Popen 参数，验"没捕获、没 -screenshot、没等待"
        mdl = Path(tmp) / "school_gate.mdl"
        mdl.write_bytes(b"IDST")
        page.ed_model.setText(str(mdl))
        calls = []

        class FakeProc:
            def __init__(self, args, **kw):
                calls.append((list(args), dict(kw)))

            def wait(self, *a, **k):
                raise AssertionError("不许等 HLMV（施工单 §4）")

            def communicate(self, *a, **k):
                raise AssertionError("不许抓 HLMV 的输出（施工单 §4）")

        real_popen = gui_main.subprocess.Popen
        gui_main.subprocess.Popen = FakeProc
        try:
            BOXES.clear()
            page.run_hlmv()
        finally:
            gui_main.subprocess.Popen = real_popen

        check("启动了一次，且没弹任何框", len(calls) == 1 and not BOXES, f"calls={calls} boxes={BOXES}")
        if calls:
            args, kw = calls[0]
            check("参数 = [hlmv.exe, 模型.mdl]", args == [str(exe), str(mdl)], str(args))
            check("**没加 `-screenshot`**", not any("-screenshot" in str(a) for a in args), str(args))
            check("**没捕获输出**（无 capture_output/stdout/stderr）",
                  not ({"capture_output", "stdout", "stderr"} & set(kw)), str(kw))
            check("没有多余关键字参数", kw == {}, str(kw))
        check("状态栏说了「已启动 HLMV」", "HLMV" in win.lbl_status.text(), win.lbl_status.text())

    # 配置文件里记住了 HLMV 路径
    win.save_prefs()
    prefs = settings.load_gui_prefs(win.config_root)
    check("HLMV 路径进了 gui.json", "HLMV路径" in prefs, str(prefs.get("HLMV路径")))
    win.close()


def main() -> int:
    print("== HLMV 按钮单测（施工单 _task/02）==")
    test_resolve()
    test_gui_and_popen()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"   失败：{f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
