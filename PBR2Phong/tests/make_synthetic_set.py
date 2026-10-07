"""造一套**合成 PBR 素材**，用来在没有真实烘焙产物时把链路跑通。

放在 `PBR2Phong/tests/` 下是因为它是测试夹具，不是产品代码。
真实素材到位后（用户会给 Material Bakery 的输出），直接用 `cli.convert` 指向真素材即可。

用法：python tests/make_synthetic_set.py [输出根目录]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import imaging  # noqa: E402


def _ramp(w: int, h: int, lo=0, hi=255) -> np.ndarray:
    return np.tile(np.linspace(lo, hi, w, dtype=np.uint8)[None, :], (h, 1))


def _ridges(w: int, h: int) -> np.ndarray:
    y = np.arange(h)[:, None]
    dh = np.cos(2 * np.pi * 6 * y / h) * (2 * np.pi * 6 / h) * 60
    ny, nz = -dh, np.ones_like(dh)
    nx = np.zeros_like(dh)
    n = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    out = np.zeros((h, w, 3), np.uint8)
    out[:, :, 0] = np.clip(128 + nx / n * 127, 0, 255)
    out[:, :, 1] = np.clip(128 + ny / n * 127, 0, 255)
    out[:, :, 2] = np.clip(128 + nz / n * 127, 0, 255)
    return out


def _checker(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    tile = (((xx // 32) + (yy // 32)) % 2).astype(np.uint8)
    out = np.zeros((h, w, 3), np.uint8)
    out[:, :, 0] = np.where(tile, 220, 40)
    out[:, :, 1] = np.where(tile, 90, 30)
    out[:, :, 2] = np.where(tile, 60, 20)
    return out


def _radial(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt((xx - w / 2) ** 2 + (yy - h / 2) ** 2)
    return np.clip(255 - d / (max(w, h) / 2) * 255, 0, 255).astype(np.uint8)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).resolve().parents[2] / "测试素材" / "合成素材"
    size = 512
    group_a = root / "Couch"
    imaging.save(_checker(size, size), group_a / f"Couch-BaseColor-{size}.png")
    imaging.save(_ramp(size, size), group_a / f"Couch-Roughness-{size}.png")
    imaging.save(np.where(_ramp(size, size) > 127, 255, 0).astype(np.uint8),
                 group_a / f"Couch-Metallic-{size}.png")
    imaging.save(_ridges(size, size), group_a / f"Couch-Normal-{size}.png")
    imaging.save(_radial(size, size), group_a / f"Couch-AmbientOcclusion-{size}.png")

    # 第二套：故意用"老写法"文件名（前缀与类型粘在一起）+ 缺 AO，用来验警告与解析
    group_b = root / "Barrel"
    imaging.save(_checker(256, 256), group_b / "BarrelBaseColor-256.png")
    imaging.save(_ramp(256, 256), group_b / "BarrelRoughness-256.png")
    imaging.save(np.full((256, 256), 255, np.uint8), group_b / "BarrelMetallic-2k.png")

    print(f"合成素材已生成：{root}")
    for p in sorted(root.rglob("*.png")):
        print(f"   {p.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
