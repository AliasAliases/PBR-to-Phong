"""一次跑齐 13 个套件 —— 但**默认只打一行汇总**（14-E）。

用户原话（2026-10-07）："**现在的问题是我不想每次实现一个功能就要你们经常全量测试，很TM烧token啊**"
→ 全量测试交给这个脚本 + GitHub Actions；日常只跑受影响的套件（地图在 `_task/README.md`）。

用法（cwd 随便，脚本自己会切到 `PBR2Phong`）：
    python PBR2Phong/tests/run_all.py                  # 一行汇总；失败才列失败套件与那几条 ✗
    python PBR2Phong/tests/run_all.py --verbose        # 逐套件把输出全打出来（以前那样）
    python PBR2Phong/tests/run_all.py --only test_pipeline,test_warnings
    python PBR2Phong/tests/run_all.py --list           # 只列套件名

⚠️ **退出码以脚本自己解析的"通过 N 项，失败 M 项"为准**，不看子进程退出码
    —— Qt 在解释器收尾时会崩，脚本明明全绿却返回 1（老经验）。
⚠️ 缺依赖（VTFCmd / L4D2 / 语料）的套件会**自己说明并跳过**，不算失败（公开仓库 / CI 上属正常）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../PBR2Phong/tests
ROOT = HERE.parent                              # .../PBR2Phong（跑测试的 cwd）

SUITES = [
    "test_pipeline", "test_gui_flow", "test_first_run", "test_brush", "test_hlmv",
    "test_layout", "test_vtf_encoding", "test_neutral_params", "test_preview",
    "test_sliders", "test_presets", "test_transparency", "test_warnings",
]
SUMMARY = re.compile(r"通过\s*(\d+)\s*项，失败\s*(\d+)\s*项")


def child_env() -> dict:
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("QT_QPA_PLATFORM", "offscreen")     # 离屏跑 GUI，不需要桌面
    fonts = Path(r"C:\Windows\Fonts")
    if fonts.is_dir():
        env.setdefault("QT_QPA_FONTDIR", str(fonts))   # 没有它 Qt 会把中文画成方框（Linux/CI 上不存在）
    return env


def run_one(name: str) -> dict:
    proc = subprocess.run([sys.executable, str(HERE / f"{name}.py")], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=child_env())
    out = (proc.stdout or "") + (proc.stderr or "")
    hits = SUMMARY.findall(out)
    # 整片跳过（例如缺 VTFCmd 的 test_transparency）：打印了 ⏭、没有汇总、也没抛异常 → 不算失败
    whole_skip = ("⏭" in out) and not hits and ("Traceback" not in out)
    passed, failed = (int(hits[-1][0]), int(hits[-1][1])) if hits else (0, 0 if whole_skip else 1)
    bad = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("✗")]
    skip = [ln.strip() for ln in out.splitlines() if "⏭" in ln]
    return {"name": name, "passed": passed, "failed": failed, "out": out,
            "bad": bad, "skip": skip, "crashed": (not hits) and not whole_skip}


def main() -> int:
    argv = sys.argv[1:]
    if "--list" in argv:
        print("\n".join(SUITES))
        return 0
    verbose = "--verbose" in argv
    only = ""
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            only = argv[i + 1]
        elif a.startswith("--only="):
            only = a.split("=", 1)[1]
    names = [n.strip() for n in only.split(",") if n.strip()] or SUITES
    unknown = [n for n in names if n not in SUITES]
    if unknown:
        print(f"不认识套件名：{unknown}\n可选：{', '.join(SUITES)}")
        return 2

    results = []
    for n in names:
        r = run_one(n)
        results.append(r)
        if verbose:
            print(f"\n===== {n} =====")
            print(r["out"].rstrip())

    total = sum(r["passed"] + r["failed"] for r in results)
    red = [r for r in results if r["failed"] or r["crashed"]]
    print(f"{len(results)} 套件 · {total} 项 · 失败 {len(red)}")
    if red:
        for r in red:
            why = "没跑出汇总（崩了）" if r["crashed"] else f"失败 {r['failed']} 项"
            print(f"  ✗ {r['name']}：{why}")
            for ln in r["bad"][:5]:
                print(f"      {ln}")
            if r["crashed"]:
                tail = [ln for ln in r["out"].splitlines() if ln.strip()][-4:]
                for ln in tail:
                    print(f"      | {ln.strip()}")
    if not verbose:
        skipped = sum(1 for r in results for _ in r["skip"])
        if skipped:
            print(f"（另有 {skipped} 处「⏭ 跳过」：缺 VTFCmd / L4D2 / 官方语料 —— 公开仓库与 CI 上属正常；"
                  f"要看细节加 --verbose）")
    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
