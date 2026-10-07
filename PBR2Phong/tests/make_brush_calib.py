# -*- coding: utf-8 -*-
"""生成笔刷路线的**标定材质**（施工单 `_task/01-笔刷模式.md` §8）。

**一眼可判**：同一张图，**左半 roughness = 0（最光滑）、右半 = 1（最粗糙）**，金属度全 0。
刷到方块上应当 **左半边反光、右半边哑光** —— 这是 §6.5 和 §7 #1（`$normalmapalphaenvmapmask`
在 L4D2 笔刷上到底生不生效）唯一能用的判据。

产物落在 `阶段0_实测/标定包_笔刷/`（素材 + 转好的 PNG/VTF/VMT + 说明）。
⚠️ **脚本不自动写进游戏**：写 `materials/` 前要按施工单 §5 先在 `对账.md` 登记路径。
要部署就把脚本最后打印的那条命令跑一遍（或在界面里选这套素材、勾上"直接写进游戏"）。

跑法：`python tests/make_brush_calib.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                      # 工作区根
sys.path.insert(0, str(HERE.parent))        # PBR2Phong/

import numpy as np  # noqa: E402

from core import imaging, pipeline, source_io  # noqa: E402

NAME = "pbr_brush_calib"
PKG = ROOT / "阶段0_实测" / "标定包_笔刷"
SIZE = 512


def make_textures(folder: Path) -> None:
    """造素材：左半极光滑、右半极粗糙；金属全 0；法线给一点平缓起伏（免得被判成"平法线"）。"""
    h = w = SIZE
    folder.mkdir(parents=True, exist_ok=True)
    # 底色：中性灰（反射看得最清楚）
    imaging.save(np.dstack([np.full((h, w), 140, np.uint8)] * 3), folder / f"{NAME}-BaseColor-{SIZE}.png")
    # 粗糙度：左半 0、右半 255（中间不渐变，判据更干脆）
    rough = np.zeros((h, w), np.uint8)
    rough[:, w // 2:] = 255
    imaging.save(np.dstack([rough] * 3), folder / f"{NAME}-Roughness-{SIZE}.png")
    # 金属度：全 0（这条标定只看 roughness → 遮罩）
    imaging.save(np.dstack([np.zeros((h, w), np.uint8)] * 3), folder / f"{NAME}-Metallic-{SIZE}.png")
    # 法线：R 每 8 列在 118/138 之间交替（一点平缓起伏），G=128，B=255
    nrm = np.dstack([np.full((h, w), 128, np.uint8),
                     np.full((h, w), 128, np.uint8),
                     np.full((h, w), 255, np.uint8)])
    nrm[:, ::16, 0] = 138
    nrm[:, 8::16, 0] = 118
    imaging.save(nrm, folder / f"{NAME}-Normal-{SIZE}.png")


def main() -> int:
    src = PKG / "素材"
    out = PKG / "out"
    make_textures(src)

    matset = source_io.scan_folder(src)[0]
    options = pipeline.ConvertOptions(
        source=str(src), name=NAME, cdmaterials="custom", out=str(out),
        route="brush", brush_mask=True, force=True, deploy=False)
    resolved = pipeline.resolve_options(options, "", "")
    got = pipeline.convert_set(matset, options, resolved, None, None, confirm=lambda c: True)

    vmt = (Path(got["out_dir"]) / f"{NAME}.vmt").read_text(encoding="utf-8")
    print(f"✓ 标定材质已生成：{got['out_dir']}")
    for kind, p in got["vtfs"].items():
        print(f"   VTF {kind:10s} {Path(p).name}")
    print("   VMT 内容：")
    for line in vmt.strip().splitlines():
        print(f"     {line}")
    for w in got["record"]["警告"]:
        print(f"   ⚠ {w}")

    (PKG / "怎么用.md").write_text(f"""# 笔刷标定材质 · 怎么用

## 这是什么

一张**一眼可判**的图：**左半 roughness = 0（最光滑）、右半 = 1（最粗糙）**，金属度全 0。
用途：验证两件事 ——

1. `$normalmapalphaenvmapmask`（遮罩塞法线 alpha）在 **L4D2 的笔刷**上到底生不生效；
2. 我们的 roughness → 遮罩曲线，刷到墙上是不是"光滑那半反光、粗糙那半哑光"。

## 怎么用

1. 把 `out\\` 里的 `{NAME}.vtf`、`{NAME}_basecolor.vtf`、`{NAME}_normal.vtf`、`{NAME}.vmt`
   放进游戏的 `left4dead2\\materials\\custom\\{NAME}\\`
   （或在工具界面里选 `素材\\` 这套素材、勾上"直接写进游戏"跑一遍）。
2. 开 **Hammer++**：Block 工具拉一个小方块 → 材质浏览器搜 `{NAME}` → 刷上去。
3. 选面 → Face Edit Sheet（`Shift+A`）→ 把 **Texture Scale 调到 0.5 以上**（让整张图铺不满一个面，
   左右两半都能看见）。

## 应该看到什么（预期现象）

- **左半边反光、右半边哑光**，中间一条清清楚楚的分界 —— 这就是判据。
- 如果**两边一样**（都没有反光，或都反光）：
  - 都没有反光 → `$normalmapalphaenvmapmask` 在 L4D2 笔刷上**不生效**（或没选对材质）；
  - 都反光 → 遮罩没被读到（引擎在读别的东西）→ 把现象记下来报给企划窗口。
- ⚠️ 笔刷**没有 Phong**：不要指望有跟着视角走的高光；这里看的是**反射**（cubemap）。
- ⚠️ 笔刷的明暗来自 **lightmap**，跟这张图无关 —— 别把"墙亮不亮"当成判据。
""", encoding="utf-8")
    print(f"✓ 用法说明：{PKG / '怎么用.md'}")
    print("\n要部署进游戏（写 materials/ 前先在 对账.md 登记路径）：")
    print(f'  python -m cli.convert "{src}" --route brush --name {NAME} --cdmaterials custom '
          f'--out "{out}" --deploy --yes')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
