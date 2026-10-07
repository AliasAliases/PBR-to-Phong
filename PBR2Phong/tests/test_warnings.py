"""12 单（警告英文化）：警告 = **码 + 参数**，人话在 i18n 层渲染。

判据（`_task/12-警告英文化.md` §6）：
  ② **英文下不出现中日韩字符的警告** —— 做法是**遍历全部警告码**各渲染一遍扫 CJK（不抽查）
  ③ `phong_input.json` 里存的是**码**（这份 json 里不该有中文句子）
  ④ **中文文案与改造前逐字一致** —— 锚点表 `warning_anchors_zh.json` 是**从改造前的源码 dump
     机械生成**的（`阶段0_实测/out/warn_dump.txt` → 见 12 片交付文），逐条比对
  ⑤ 渲染链路完整（GUI / CLI 都按语言渲染；`log.txt` 只存码 —— 见交付文说明）
  ⑥ 触发条件没变：同一素材触发的**码**与改造前一致

跑法：python tests/test_warnings.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]          # PBR2Phong
WS = ROOT.parent
sys.path.insert(0, str(ROOT))

import i18n  # noqa: E402
from core import imaging, pack, source_io  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


# 带参数的码 → 渲染用的样例参数（值本身不参与锚点比对：比对时占位符会被归一化）
SAMPLE_ARGS = {
    "mask_size_mismatch": {"w": 2048, "h": 1024},
    "brush_dropped_envmap_params": {"n": 3},
    "brush_mask_carrier_key": {"carrier": "normal", "key": "$normalmapalphaenvmapmask"},
    "brush_forbidden_keys": {"keys": "['$phong']"},
    "other_shader_kept_base_only": {"shader": "EyeRefract"},
}


def norm(text: str) -> str:
    """占位符归一化：`{w}×{h}` / `{len(x)}` 都变成 `{}` —— 只比字面文案，不比参数名。"""
    return re.sub(r"\{[^}]*\}", "{}", text)


def render(w, lang):
    """渲染一条警告；**旧代码（12 单之前）的 `warning()` 只认字符串** → 容错成一句话。

    这样反向实验里能拿到"干净的红"，而不是 `WARNINGS_EN.get(dict)` 抛 TypeError 把整份测试崩掉。
    """
    try:
        return i18n.warning(w, lang)
    except Exception as e:  # noqa: BLE001
        return f"<渲染失败：{type(e).__name__}>"


def main() -> int:
    print("== 12 单：警告 = 码 + 参数 ==")
    anchors = json.loads((Path(__file__).resolve().parent / "warning_anchors_zh.json")
                         .read_text(encoding="utf-8"))["锚点"]
    # ⚠️ 护栏（反向实验要的是**干净报红**，不是 AttributeError 崩掉）：
    #    在 12 单动手前的代码上跑这份测试时，`i18n` 里根本没有 `WARNING_TEXT`。
    table = getattr(i18n, "WARNING_TEXT", {}) or {}

    # ---------- 判据 ④：中文逐字一致（拿改造前的 dump 机械生成的锚点表比） ----------
    print("== 判据 ④：中文文案与改造前逐字一致（27 条锚点） ==")
    bad, leftover = [], []
    for code, old_zh in anchors.items():
        # ⚠️ 比的是**模板**（把 `{w}×{h}` 这类占位符都归一成 `{}`）：渲染后的值当然不等于锚点
        tpl = (table.get(code) or {}).get("zh") or ""
        if norm(tpl) != old_zh:
            bad.append(f"{code}\n      新: {norm(tpl)}\n      旧: {old_zh}")
        for lang in (i18n.LANG_ZH, i18n.LANG_EN):
            got = render({"code": code, "args": SAMPLE_ARGS.get(code, {})}, lang)
            if "{" in got or "}" in got:
                leftover.append(f"[{lang}] {code}: {got[:70]}")
    check(f"锚点表里 {len(anchors)} 条中文逐字一致（模板级比对）", not bad, "\n   ".join(bad)[:400])
    check("带参数的码渲染后不残留 {} （参数位填得上，中英各一遍）", not leftover,
          "\n   ".join(leftover)[:300])

    # ---------- 判据 ②：遍历全部码 → 英文渲染不许出现中日韩字 ----------
    print("== 判据 ②：遍历全部码，英文渲染无中日韩字 ==")
    leaks, incomplete = [], []
    for code, entry in table.items():
        if not entry.get("zh") or not entry.get("en"):
            incomplete.append(code)
            continue
        en = render({"code": code, "args": SAMPLE_ARGS.get(code, {})}, i18n.LANG_EN)
        if cjk(en):
            leaks.append(f"{code}: {en[:60]}")
    check(f"全部 {len(table)} 条码都中英齐备", not incomplete, str(incomplete))
    check(f"全部 {len(table)} 条码的英文渲染都没有中日韩字", not leaks,
          "\n   ".join(leaks)[:300])

    # ---------- 逐码覆盖：源码里 emit 的码 ↔ 表里的码，双向对齐 ----------
    print("== 逐码覆盖：源码 emit 的码与表一一对应 ==")
    emitted = set()
    for name in ("pack.py", "pipeline.py"):
        src = (ROOT / "core" / name).read_text(encoding="utf-8")
        emitted |= set(re.findall(r'warn\("([a-z0-9_]+)"', src))
    check("源码里 emit 的每个码都在表里（没有漏翻译的新警告）", emitted <= set(table),
          str(sorted(emitted - set(table))))
    check("表里每条码都有 emit 点（没有用不上的死码）", set(table) <= emitted,
          str(sorted(set(table) - emitted)))
    check(f"码数 = {len(table)}（27 条产生点）", len(table) == 27, str(len(table)))

    # ---------- 旧格式兼容 + 认不出的码 ----------
    print("== 兼容：历史 json 里的中文整句 / 认不出的码 ==")
    legacy = "这套素材的底色没有透明区域 —— 勾了也不会裁掉任何东西。"
    check("旧记录里的中文整句：中文原样返回", render(legacy, i18n.LANG_ZH) == legacy)
    check("旧记录里的中文整句：英文查旧表（不假装翻译过、也不漏中文）",
          render(legacy, i18n.LANG_EN).startswith("This set's base colour")
          and not cjk(render(legacy, i18n.LANG_EN)))
    check("认不出的码：原样给码（不假装翻译过）",
          render({"code": "nope_not_a_code"}, i18n.LANG_EN) == "nope_not_a_code")

    # ---------- 判据 ③ + ⑥：真跑一条链路，看 json 里存的是码、且码与改造前同源 ----------
    print("== 判据 ③/⑥：产出的警告是码（json 里没有中文句子） ==")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        h = w = 8
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), tmp / "F-BaseColor-8.png")
        res = pack.build(source_io.scan_folder(tmp)[0], pack.PackOptions())
        codes = [x.get("code") if isinstance(x, dict) else str(x) for x in res.warnings]
        check("没有贴图那几条仍然照旧触发（触发条件没变）",
              set(codes) == {"no_roughness_map", "no_metallic_map", "no_ao_map", "no_normal_map"},
              str(sorted(codes)))
        dumped = json.dumps(res.warnings, ensure_ascii=False)
        check("写进 json 的是**码 + 参数**，dump 出来一个中文都没有", not cjk(dumped), dumped[:160])
        check("每条警告都带 code 与 args（可被 i18n 渲染）",
              all(isinstance(x, dict) and "code" in x and "args" in x for x in res.warnings),
              str(res.warnings)[:160])

        d2 = tmp / "sub"
        d2.mkdir()
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), d2 / "G-BaseColor-8.png")
        imaging.save(np.dstack([np.full((h, w), 128, np.uint8)] * 3), d2 / "G-Roughness-8.png")
        imaging.save(np.dstack([np.full((h, w), 128, np.uint8)] * 2
                               + [np.full((h, w), 255, np.uint8)]), d2 / "G-Normal-8.png")
        codes2 = [x.get("code") if isinstance(x, dict) else str(x) for x in pack.build(source_io.scan_folder(d2)[0],
                                                pack.PackOptions()).warnings]
        check("平法线 / 常量粗糙度那两条仍按同样的码触发",
              "normal_is_flat" in codes2 and "roughness_is_constant" in codes2, str(sorted(codes2)))

    # ---------- 判据 ⑤：渲染链路（GUI / CLI 都过 i18n；log.txt 只存码） ----------
    print("== 判据 ⑤：渲染链路 ==")
    gui_src = (ROOT / "gui" / "main.py").read_text(encoding="utf-8")
    cli_src = (ROOT / "cli" / "convert.py").read_text(encoding="utf-8")
    # 14-A：`log.txt` 由 **UI 层**重写成可读版（core 里只写码 → 铁律不破）
    check("GUI 结果区走 i18n 渲染（不是把码/字典直接怼给用户）",
          "i18n.render_warnings(" in gui_src or "i18n.warning(w, lang)" in gui_src)
    check("14-A：GUI 会把 log.txt 重写成可读版（readable_log_text）",
          "i18n.readable_log_text(" in gui_src)
    check("14-A：CLI 同样重写 log.txt", "i18n.readable_log_text(" in cli_src)
    check("14-A：可读化只在 UI 层 —— core 里没有 readable_log_text / 没有 i18n 导入",
          "readable_log_text" not in (ROOT / "core" / "pipeline.py").read_text(encoding="utf-8")
          and "import i18n" not in (ROOT / "core" / "pack.py").read_text(encoding="utf-8"))
    check("CLI 也过 i18n（不是直接 print 那个 dict）",
          "i18n.warning(w, i18n.LANG_ZH)" in cli_src)
    same = {"code": "no_ao_map", "args": {}}
    check("同一条码：中英两种说法不同、且英文无中日韩字",
          render(same, i18n.LANG_ZH) != render(same, i18n.LANG_EN)
          and not cjk(render(same, i18n.LANG_EN)))

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        for f in FAIL:
            print("   失败：" + f)
        return 1
    print("✓ 全绿")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
