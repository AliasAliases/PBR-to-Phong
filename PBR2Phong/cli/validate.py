"""校验模型（命令行）：拿模型当权威，检查产物对不对得上。

用法：
    python -m cli.validate <模型.mdl | 模型名> [...] [--models <L4D2 models 目录>]
    python -m cli.validate --all            # 校验 models\\custom 下的全部模型
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import naming, validate  # noqa: E402

L4D2 = Path(r"D:\SteamLibrary\steamapps\common\Left 4 Dead 2")
DEFAULT_MODELS = L4D2 / "left4dead2" / "models"
DEFAULT_MATERIALS = L4D2 / "left4dead2" / "materials"


def main() -> int:
    ap = argparse.ArgumentParser(description="用编译好的 .mdl 校验材质产物")
    ap.add_argument("models", nargs="*", help="模型路径或模型名（会自动在 models 下找）")
    ap.add_argument("--all", action="store_true", help="校验 models\\custom 下的全部模型")
    ap.add_argument("--models", dest="models_root", default=str(DEFAULT_MODELS))
    ap.add_argument("--materials", default=str(DEFAULT_MATERIALS))
    args = ap.parse_args()

    targets = []
    for name in args.models:
        p = Path(name)
        if p.is_file():
            targets.append(p)
        else:
            found = naming.find_models_with_name(args.models_root, name)
            if not found:
                print(f"找不到模型：{name}（在 {args.models_root} 下也没搜到）")
                return 2
            targets.extend(found)
    if args.all:
        targets.extend(sorted((Path(args.models_root) / "custom").rglob("*.mdl")))
    if not targets:
        ap.print_help()
        return 1

    bad = 0
    for model in targets:
        print(f"\n===== {model.name} =====")
        try:
            rep = validate.validate_model(model, args.materials)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ 读不了：{e}")
            bad += 1
            continue
        print(f"  $cdmaterials = {rep.cdmaterials}")
        print(f"  材质（{len(rep.textures)}）= {rep.textures}")
        print(f"  查了 {rep.vmt_checked} 个 VMT、{rep.vtf_checked} 张贴图")
        if not rep.findings:
            print("  ✓ 没发现问题")
        for f in rep.findings:
            print(f"  {f}")
            if f.level == "拒绝":
                bad += 1
    print(f"\n共校验 {len(targets)} 个模型，拒绝级问题 {bad} 处")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
