"""S4 的中性旋钮回归 —— **默认值下产物必须逐位一致**。

对应 `_task/07-S3+S4-预览与拉条.md` §3.3 的三条硬约束：
  ① 默认值（0 / 1.0 / 空曲线）下输出**逐位一致** —— 本文件用"**改动前录下来的产物哈希**"当锁；
  ② **只加不改** —— 见 `core/curves.py` 末尾那段（新增函数，既有公式与常数一个没动）；
  ③ 值走**覆盖项**、**参与指纹**。

哈希是怎么来的：**动 `core/pack.py` 之前**先跑一遍 `pack.build()`，把三张输出图的
sha256 前 12 位记下来（见交付文档 §2）。所以这个测试锁的不只是"新字段默认值没影响"，
而是**整条既有管线没有漂移**。

跑法：python tests/test_neutral_params.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from core import curves, pack, pipeline, settings, source_io  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def digest(arr) -> str:
    if arr is None:
        return "None"
    return hashlib.sha256(np.ascontiguousarray(arr).tobytes()).hexdigest()[:12]


# ⚠️ 2026-09-27 改动 core/pack.py **之前**录的基准（逐位一致锁）。
# 📌 勘误（同一天自测抓到的）：`("Couch","brush")` 的 basecolor 基准原先录成 `bb518233aefd` ——
#    那次我造基准用时少传了一个 `ao_amount=0.0`（笔刷路线真正的取值），所以录的是"带 AO 压暗"的版本。
#    正确的基准 = `f5e6a843a3b4`。**它可信**的依据：这一路里真正被本片改过的是**遮罩那条路**，
#    而 Couch/brush 的 `normal`（遮罩就塞在它的 alpha 里）= `60d4c709fa5f`，与改动前**逐位相同**。
BASELINE = {
    ("Barrel", "model"): {"basecolor": "08ed29a7dd46", "exp": "06499b1bbbc1", "normal": "None"},
    ("Barrel", "brush"): {"basecolor": "d0f795f71f5a", "exp": "06499b1bbbc1", "normal": "None"},
    ("Couch", "model"): {"basecolor": "8ec187aa8c7c", "normal": "aea17d3118b8", "exp": "9f815f0f39a5"},
    ("Couch", "brush"): {"basecolor": "f5e6a843a3b4", "normal": "60d4c709fa5f", "exp": "9f815f0f39a5"},
}


def opts_for(route: str) -> pack.PackOptions:
    return pack.options_from_values({}, route=route)


def main() -> int:
    print("== S4 中性旋钮（默认值逐位一致）==")
    folder = WS / "测试素材" / "合成素材"
    check("合成素材存在", folder.is_dir(), str(folder))
    if not folder.is_dir():
        return 1
    sets = {s.group: s for s in source_io.scan_folder(folder)}

    print("== ① 默认值下与改动前逐位一致 ==")
    for (group, route), want in BASELINE.items():
        ms = sets.get(group)
        if ms is None:
            check(f"{group} 素材在", False, str(sorted(sets)))
            continue
        got = pack.build(ms, opts_for(route)).images()
        for kind, wanted in want.items():
            got_hash = digest(got.get(kind))
            check(f"{group}/{route} {kind} 逐位一致", got_hash == wanted,
                  f"{got_hash} vs 基准 {wanted}")

    print("== ② 只在「不干预」时才原样返回（连数组都不复制）==")
    x = np.arange(256, dtype=np.uint8).reshape(1, -1)
    check("偏移 0 → 原样返回同一个对象", curves.apply_roughness_offset(x, 0.0) is x)
    check("空曲线 → 原样返回同一个对象", curves.apply_roughness_points(x, ()) is x)
    check("染色 1.0 → 原样返回同一个对象", curves.scale_metal_tint(x, 1.0) is x)
    check("`options_from_values({})` == 出厂 PackOptions()",
          pack.options_from_values({}) == pack.PackOptions(),
          f"{pack.options_from_values({})}")

    print("== ③ 旋钮真的能改变产物 ==")
    ms = sets["Couch"]
    base = pack.build(ms, opts_for("model")).images()

    off = pack.options_from_values({"curve.roughness_offset": 0.2}, route="model")
    got_off = pack.build(ms, off).images()
    check("粗糙度偏移 +0.2 → 指数图变了", digest(got_off["exp"]) != digest(base["exp"]),
          f"{digest(base['exp'])} → {digest(got_off['exp'])}")
    check("粗糙度偏移 +0.2 → 遮罩（底色 alpha）也变了",
          digest(got_off["basecolor"]) != digest(base["basecolor"]))
    check("粗糙度偏移 +0.2 → 法线不受影响",
          digest(got_off["normal"]) == digest(base["normal"]))

    pts = [(0.0, 0.0), (0.5, 0.75), (1.0, 1.0)]          # 自定义曲线：把中间抬亮
    got_curve = pack.build(ms, pack.options_from_values({"curve.curve_points": pts},
                                                        route="model")).images()
    check("自定义曲线 → 指数图变了", digest(got_curve["exp"]) != digest(base["exp"]),
          f"{digest(base['exp'])} → {digest(got_curve['exp'])}")

    tint = pack.build(ms, pack.options_from_values({"curve.metal_tint": 0.0},
                                                   route="model")).images()
    g_base = int(base["exp"][:, :, 1].max())
    g_tint = int(tint["exp"][:, :, 1].max())
    check("金属染色 0.0 → exp 的 G 通道被压到 0", g_base > 0 and g_tint == 0,
          f"G: {g_base} → {g_tint}")
    check("金属染色 0.0 → exp 的 R 通道（指数）不受影响",
          digest(base["exp"][:, :, 0]) == digest(tint["exp"][:, :, 0]))

    brush_base = pack.build(ms, opts_for("brush")).images()
    gain = pack.build(ms, pack.options_from_values({"curve.envmap_gain": 0.5},
                                                   route="brush")).images()
    # ⚠️ Couch 有法线 → 笔刷的遮罩塞在**法线的 alpha** 里，不是底色（底色那格不会变）
    check("反射强度 0.5 → 笔刷的反射遮罩变了（在法线 alpha 里）",
          digest(gain["normal"]) != digest(brush_base["normal"]),
          f"{digest(brush_base['normal'])} → {digest(gain['normal'])}")
    barrel = pack.build(sets["Barrel"], opts_for("brush")).images()
    barrel_gain = pack.build(sets["Barrel"], pack.options_from_values(
        {"curve.envmap_gain": 0.5}, route="brush")).images()
    check("没有法线时遮罩回退到底色 alpha，反射强度照样生效",
          digest(barrel_gain["basecolor"]) != digest(barrel["basecolor"]),
          f"{digest(barrel['basecolor'])} → {digest(barrel_gain['basecolor'])}")

    print("== ④ 三层继承 + 指纹 ==")
    for key, want in (("curve.roughness_offset", 0.0), ("curve.metal_tint", 1.0),
                      ("curve.envmap_gain", 1.0), ("curve.curve_points", [])):
        check(f"全局默认里有 {key}（= {want!r}）",
              key in settings.GLOBAL_DEFAULTS and settings.GLOBAL_DEFAULTS[key] == want,
              str(settings.GLOBAL_DEFAULTS.get(key, "<缺失>")))
    check("公式本体那两个键仍然**不能**被素材级覆盖",
          settings.CURVE_KEYS == ("curve.roughness_to_exponent", "curve.mask_formula"),
          str(settings.CURVE_KEYS))

    r0 = settings.resolve("", {}, {}, {})
    r1 = settings.resolve("", {"curve.roughness_offset": 0.2}, {}, {})
    check("覆盖项生效且来源标成「你改过」",
          r1.values.get("curve.roughness_offset") == 0.2
          and r1.source_of("curve.roughness_offset") == "你改过",
          f"{r1.values.get('curve.roughness_offset')} / {r1.source_of('curve.roughness_offset')}")

    o0 = pipeline.ConvertOptions(source=str(folder), name="X")
    o1 = pipeline.ConvertOptions(source=str(folder), name="X",
                                 overrides={"curve.roughness_offset": 0.2})
    fp0 = pipeline.fingerprint(ms, o0, r0)
    fp1 = pipeline.fingerprint(ms, o1, r1)
    check("中性参数**参与指纹**（改了它 → 指纹变）", fp0 != fp1, f"{fp0} → {fp1}")
    fp2 = pipeline.fingerprint(ms, o0, r0)
    check("同样的参数 → 指纹稳定", fp0 == fp2, f"{fp0} / {fp2}")

    print("== ⑤ 滑杆换算（中点 = 不干预）==")
    check("偏移滑杆 50 → 0.0", curves.offset_from_slider(50) == 0.0,
          str(curves.offset_from_slider(50)))
    check("偏移 0.0 → 滑杆 50", curves.slider_from_offset(0.0) == 50)
    check("偏移两端是 ∓0.35",
          (curves.offset_from_slider(0), curves.offset_from_slider(100)) == (-0.35, 0.35),
          f"{curves.offset_from_slider(0)} / {curves.offset_from_slider(100)}")
    check("染色滑杆 50 → 1.0", curves.tint_from_slider(50) == 1.0,
          str(curves.tint_from_slider(50)))
    check("反射强度滑杆 50 → 1.0", curves.gain_from_slider(50) == 1.0,
          str(curves.gain_from_slider(50)))
    check("锐度滑杆 50 → 1.0（既有行为没动）", curves.sharpness_from_slider(50) == 1.0,
          str(curves.sharpness_from_slider(50)))

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
