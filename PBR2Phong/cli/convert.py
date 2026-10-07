"""端到端命令行（阶段 1 垂直切片 + 阶段 3 的批量与确定性）。

**真正的实现全在 `core/pipeline.py`** —— GUI 与 CLI 共用同一份，避免两边算出不同结果。
本文件只负责三件事：解析参数、打印人话、返回退出码。

用法：
    python -m cli.convert <素材目录> --name <材质名> --cdmaterials <目录> [--preset 武器]
                          [--out 输出目录] [--deploy] [--materials <L4D2 materials>]
                          [--model 模型.mdl] [--force] [--set 键=值 ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402 —— CLI 是 UI 层：警告的**人话**在这里渲染（core 只出码）
from core import naming, phong, pipeline, source_io, vtf  # noqa: E402

DEFAULT_MATERIALS = pipeline.DEFAULT_MATERIALS


# 13-E：core 抛的是**带码**的异常（core 不产人话）→ 人话在 CLI 这一层给
_WHY_ZH = {
    "eye.iris": "眼睛档需要一张虹膜图（必填）—— 用 --set eye.iris=<图片路径> 指定",
    "eye.ao": "眼睛 AO 那张图找不到（路径不对或文件没了）—— 清掉或用 --set eye.ao=<图片路径> 重指",
}


def _why(e) -> str:
    """异常 → 一句人话（认不出的码就原样给）。"""
    return _WHY_ZH.get(getattr(e, "code", ""), str(e))


def _ask(conflicts) -> bool:
    """同名冲突：停下来说人话，问一句「覆盖 / 跳过」。

    ⚠️ core 给的是**码**（`exists` / `in_materials`），人话在这一层过（core 不产出人话）。
    ⚠️ 非交互（管道 / 脚本 / 没 stdin）时 fail-closed：**默认不覆盖**，并提示加 `--force`。
    """
    why_zh = {"exists": "已有同名文件", "in_materials": "materials 里已有同名文件"}
    print("目标位置已有同名文件：")
    for rel, why in conflicts:
        print(f"   {rel}（{why_zh.get(why, why)}）")
    try:
        return input("覆盖它们？(y/N) ").strip().lower() == "y"
    except EOFError:
        print("   （这里没有可以问答的终端 → 按「不覆盖」处理；要覆盖请加 --force 或 --yes）")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="PBR 贴图 → L4D2 Phong 贴图 + VMT + VTF")
    ap.add_argument("source", nargs="?", default="",
                    help="素材文件夹（Material Bakery 的产物目录）；只列模型材质名时可以不给")
    ap.add_argument("--name", default="", help="贴图基名（默认取组名）")
    ap.add_argument("--model", "--mdl", dest="model", default="",
                    help="已编译的 .mdl（路径或模型名）→ 读出权威的 $cdmaterials 与材质名，"
                         "一个材质名生成一个 VMT（多材质槽共用一套贴图的常见情况）。"
                         "多材质模型会把名字全部列出来（`--mdl` 是同义写法）")
    ap.add_argument("--list-materials", action="store_true",
                    help="**只列**这个模型里的材质名（不转换、不写任何文件）—— 多材质模型"
                         "「跑两次」时用它取名字，不用去别处翻 .mdl")
    ap.add_argument("--cdmaterials", default="custom", help="materials 下的子目录（用 --model 时以模型为准）")
    ap.add_argument("--preset", default=phong.DEFAULT_PRESET, choices=list(phong.PRESETS))
    ap.add_argument("--group", default="", help="素材目录里有多套时，只处理指定组名")
    ap.add_argument("--out", default="", help="输出目录（默认 <素材目录同级>/<名字>_phong）")
    ap.add_argument("--ao", type=float, default=None, help="AO 压进底色的比例（0 = 不压；默认取配置）")
    ap.add_argument("--darken", action="store_true", help="改走压黑派（默认方案 A 不压黑）")
    ap.add_argument("--no-flip-normal", action="store_true", help="不翻法线绿通道（默认翻）")
    ap.add_argument("--config", default="", help="config.json 所在目录（全局默认那一层）")
    ap.add_argument("--presets-dir", default="", help="presets/ 所在目录（自定义预设）")
    ap.add_argument("--set", dest="sets", action="append", default=[],
                    metavar="键=值", help="素材级覆盖，可重复，如 --set vmt.$phongboost=30")
    ap.add_argument("--force", action="store_true",
                    help="忽略 phong_input.json 全部重跑；**且遇到同名产物直接覆盖**（不再问）")
    ap.add_argument("--deploy", action="store_true", help="顺便写进 L4D2 的 materials")
    ap.add_argument("--yes", action="store_true", help="遇到同名文件直接覆盖（不再问）")
    ap.add_argument("--materials", default=str(DEFAULT_MATERIALS))
    ap.add_argument("--models-root", default=str(Path(DEFAULT_MATERIALS).parent / "models"),
                    help="用模型名搜索 .mdl 时去哪个目录找")
    ap.add_argument("--route", default="model", choices=("model", "brush"),
                    help="model = 模型材质（VertexLitGeneric + Phong，默认）；"
                         "brush = 笔刷材质（LightmappedGeneric，给 Hammer 铺墙用）")
    ap.add_argument("--no-brush-mask", dest="brush_mask", action="store_false", default=True,
                    help="笔刷路线：**不出** envmap 反射遮罩（默认出 —— v1 范围含遮罩）。"
                         "想要最小版本（只底色+法线）才加这个")
    args = ap.parse_args()

    if not args.source and not args.list_materials:
        print("没给素材文件夹。用法：python -m cli.convert <素材文件夹> [选项]；"
              "只想看模型里有哪些材质名 → python -m cli.convert --mdl <模型> --list-materials")
        return 2

    # ---- 13-B：先把 `.mdl` 解析掉（`--list-materials` 只要这一步，不需要参数/素材） ----
    vmt_names, cdm_override = None, None
    if args.model and args.route == "brush":
        print("⚠️ 笔刷路线忽略 --model：笔刷材质名 = 贴图基名（在 Hammer 材质浏览器里直接选）")
        args.model = ""
    if args.model:
        p = Path(args.model)
        if not p.is_file():
            found = naming.find_models_with_name(Path(args.models_root), args.model)
            if not found:
                print(f"找不到模型：{args.model}")
                return 2
            p = found[0]
        cdm_override, vmt_names, mdl = pipeline.names_from_model(p)
        print(f"从模型读出：{p.name} → $cdmaterials={cdm_override}  材质={vmt_names}")
        if mdl.missing_materials:
            print(f"   ⚠️ 模型里有未赋材质的面：{mdl.missing_materials}")
        if not vmt_names:
            print("   ⚠️ 模型里没读到材质名，回退到普通命名")
            vmt_names = None
        elif len(vmt_names) >= 2:
            # ⚠️ 13-B 返工（一类 2026-10-01 实测更正）：一次转换就**给每个材质名各写一份 VMT**、
            #    都指向本次这套贴图（`core/pipeline.py` 的 `vmt_paths = [... for n in names]`）；
            #    只有"不同材质槽要配不同贴图"时才需要分开跑。**别再说"请分几次跑"**。
            print(f"   这个模型有 {len(vmt_names)} 个材质名 —— 本次会给每个名字各写一份 VMT，"
                  "都指向你这次的贴图；只有要给不同材质配不同贴图时，才需要分开跑"
                  "（每次用 --name 指定那一套）")
    if args.list_materials:
        if not args.model:
            print("--list-materials 要配 --mdl/--model 用："
                  "python -m cli.convert --mdl <模型> --list-materials")
            return 2
        print("（只列材质名：没有转换、没有写任何文件）")
        return 0

    options = pipeline.ConvertOptions(
        source=args.source, name=args.name, cdmaterials=args.cdmaterials, preset=args.preset,
        out=args.out, deploy=args.deploy, materials=args.materials, force=args.force,
        yes=args.yes, ao=args.ao, darken=args.darken, no_flip_normal=args.no_flip_normal,
        sets=tuple(args.sets), route=args.route, brush_mask=args.brush_mask)

    try:
        resolved = pipeline.resolve_options(options, args.config, args.presets_dir)
    except (KeyError, ValueError) as e:
        print(f"参数有问题：{e}")
        return 2
    print(f"参数：{resolved.report_line()}")

    sets = source_io.scan_folder(args.source)
    if not sets:
        print(f"这个文件夹里没认出任何可用素材：{args.source}")
        return 2
    if args.group:
        sets = [s for s in sets if s.group == args.group]
        if not sets:
            print(f"没找到组名是「{args.group}」的素材")
            return 2

    print(f"认出 {len(sets)} 套素材：")
    for s in sets:
        print(f"   {s.summary()}")

    ok = skipped = failed = 0
    failures = []
    for matset in sets:
        print(f"\n=== 转换 {matset.group} ===")
        try:
            got = pipeline.convert_set(matset, options, resolved, vmt_names, cdm_override,
                                       confirm=(lambda c: True) if args.yes else _ask)
        except Exception as e:  # noqa: BLE001
            failed += 1
            why = _why(e)
            failures.append((matset.group, why))
            print(f"  ✗ 失败：{why}")
            continue
        if got["skipped"]:
            skipped += 1
            if got.get("skip_reason") == "conflict":
                n = len(got.get("conflicts") or [])
                print(f"  ⏭ 跳过：目标目录已有 {n} 个同名产物，你没让覆盖"
                      "（要覆盖加 --force 或 --yes）")
            else:
                print("  ⏭ 跳过（指纹一致且产物都在；要重跑加 --force）")
            continue
        ok += 1
        print(f"  输出目录：{got['out_dir']}")
        for kind, p in got["pngs"].items():
            print(f"   PNG {kind:9s} {Path(p).name}")
        for kind, p in got["vtfs"].items():
            print(f"   VTF {kind:9s} {vtf.read_info(p)}")
        print(f"   VMT {[n for n, _ in got['vmts']]}   记录 {pipeline.RECORD_NAME}")
        for w in got["record"]["警告"]:
            # 12 单：记录里存的是**码 + 参数**（core 不产人话）→ 这里按语言渲染成人话
            print(f"   ⚠ {i18n.warning(w, i18n.LANG_ZH)}")
        # 14-A：`log.txt` 也重写成**人能读**的版本（core 只写码 → 可读化在 UI 层）
        try:
            out = Path(got["out_dir"])
            vmts = got.get("vmts") or []
            vmt_text = Path(vmts[0][1]).read_text(encoding="utf-8", errors="replace") if vmts else ""
            (out / "log.txt").write_text(
                i18n.readable_log_text(got.get("record") or {}, i18n.LANG_ZH, vmt_text),
                encoding="utf-8-sig")
        except OSError:
            print("   （日志没能重写成可读版：写不进去；phong_input.json 不受影响）")
        if got["deployed"]:
            done = got["deployed"]
            print(f"   ✓ 已写入 materials（{len(done)} 个文件）：" +
                  "、".join(f"{d.action}{d.dest}" for d in done))

    print(f"\n===== 汇总：成功 {ok} / 跳过 {skipped} / 失败 {failed} =====")
    for group, why in failures:
        print(f"   失败：{group} —— {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
