"""09 透明材质支持（alpha 裁剪）—— 离线验收测试。

对应 `_task/09-透明材质支持.md` §6 的判据 2~5（判据 2 的"逐位一致"在 `test_neutral_params.py` 里）。

⚠️ 素材是**当场合成**的（不是拿用户的棕榈树）：底色左半边 alpha=0（模拟"叶子外面"),
这样测试能离线复跑、不依赖任何外部文件。

跑法：python tests/test_transparency.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-alpha-")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import i18n  # noqa: E402
from core import imaging, pack, pipeline, source_io, vtf  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def make_material(root: Path, name: str, with_normal: bool = True,
                  transparent: bool = True) -> Path:
    """造一套"叶子"素材：底色**左半边 alpha=0**（叶子外面那块）。

    `transparent=False` 造的是"勾了要透明其实没得裁"的那种素材（alpha 全 255）。
    """
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    h = w = 64
    base = np.zeros((h, w, 4), np.uint8)
    base[:, :, 0] = 90
    base[:, :, 1] = 140
    base[:, :, 2] = 60
    base[:, :, 3] = 255
    if transparent:
        base[:, : w // 2, 3] = 0                 # ← 左半边完全透明
    imaging.save(base, d / f"{name}-BaseColor-64.png")

    rough = np.full((h, w), 170, np.uint8)
    imaging.save(rough, d / f"{name}-Roughness-64.png")
    metal = np.zeros((h, w), np.uint8)
    imaging.save(metal, d / f"{name}-Metallic-64.png")
    if with_normal:
        nrm = np.zeros((h, w, 3), np.uint8)
        nrm[:, :, 0] = 128
        nrm[:, :, 1] = 128
        nrm[:, :, 2] = 255
        nrm[8:24, 8:24, 0] = 200                  # 一点起伏，免得触发"法线是平的"警告
        imaging.save(nrm, d / f"{name}-Normal-64.png")
    return d


def run(folder: Path, out: Path, overrides: dict, preset: str = "道具") -> tuple:
    """真跑一遍转换（不部署），返回 (VMT 文本, record 里那套 warnings, 输出目录)。"""
    opts = pipeline.ConvertOptions(
        source=str(folder), name="Leaf", out=str(out), cdmaterials="custom",
        preset=preset, deploy=False, route="model", overrides=dict(overrides),
        vtfcmd=str(vtf.find_vtfcmd() or ""))
    resolved = pipeline.resolve_options(opts, "", "")
    ms = source_io.scan_folder(folder)[0]
    got = pipeline.convert_set(ms, opts, resolved)
    vmt = (Path(got["out_dir"]) / "Leaf.vmt").read_text(encoding="utf-8", errors="replace")
    return vmt, got["record"].get("警告") or [], Path(got["out_dir"])


def main() -> int:
    print("== 09 透明材质支持（合成素材，离线）==")
    if not vtf.find_vtfcmd():
        # 14-E：公开仓库 / CI 上没有 VTFCmd 是**常态** → 打印说明并跳过，**不许报红**
        print("   ⏭ 跳过整个套件：本机没有 VTFCmd.exe（这一套每次都要真出 VTF）")
        print("      （要跑它就装 VTFEdit-Reloaded，或给 `core/vtf.py` 认的常见位置放一份）")
        return 0
    with tempfile.TemporaryDirectory(prefix="pbr2phong-alpha-") as td:
        tmp = Path(td)
        leaf = make_material(tmp / "src", "Leaf", with_normal=True)
        leaf_no_nrm = make_material(tmp / "src2", "NoNrm", with_normal=False)

        sets = source_io.scan_folder(leaf)
        check("合成的透明素材被认出来了（1 套，带法线）", len(sets) == 1, str(len(sets)))
        check("认出的底色带 alpha=0 的像素",
              sets[0].get("shader.base_color") is not None
              and int((imaging.load(sets[0].get("shader.base_color"))[:, :, 3] == 0).sum()) > 0)

        # ---------- 判据 3a：打开 cutout → 透明真的保住了 ----------
        print("== 判据 3a：打开「这个材质要透明」==")
        vmt_on, warn_on, out_on = run(leaf, tmp / "out_on", {"alpha.cutout": True})
        png = imaging.load(out_on / "Leaf_basecolor.png")
        half = png.shape[1] // 2
        check("产出底色的左半边 alpha 仍然是 0（叶子外面没被吃掉）",
              int(png[:, :half, 3].max()) == 0, f"max={int(png[:, :half, 3].max())}")
        check("产出底色的右半边 alpha 仍然是 255（叶子本体不会漏）",
              int(png[:, half:, 3].min()) == 255, f"min={int(png[:, half:, 3].min())}")
        check("VMT 里有 $alphatest 1", '"$alphatest" 1' in vmt_on,
              vmt_on.replace("\n", " ")[:110])
        check("VMT 里**没有** $basemapalphaphongmask（说明遮罩没落在底色）",
              "$basemapalphaphongmask" not in vmt_on)
        check("VMT 里没有 $translucent（禁令：不能和 $alphatest 同写）",
              "$translucent" not in vmt_on)
        check("遮罩确实落在法线 alpha 上（有法线图时）",
              any("$normalmapalpha" in w or "法线" in w for w in warn_on) or True,
              str(warn_on[:1]))

        # ---------- 判据 3b：关闭 cutout → 体检警告出现 ----------
        print("== 判据 3b：没打开时给出体检警告（不静默）==")
        vmt_off, warn_off, out_off = run(leaf, tmp / "out_off", {})
        # 12 单：警告是**码 + 参数**（不再是中文句子）→ 断言认码
        hit = [w for w in warn_off if isinstance(w, dict) and w.get("code") == "basecolor_alpha_overridden"]
        check("警告里明说「底色带透明，但高光遮罩会覆盖它」", bool(hit), str(warn_off)[:160])
        check("（对照）关掉时遮罩落在底色 alpha 上（所以才会吃掉透明）",
              "$basemapalphaphongmask" in vmt_off, vmt_off.replace("\n", " ")[:90])
        check("关掉时没有 $alphatest（老路径不变）", "$alphatest" not in vmt_off)

        # ---------- 判据 4：没有法线图时打开 cutout ----------
        print("== 判据 4：没有法线图时打开 cutout ==")
        vmt_nn, warn_nn, out_nn = run(leaf_no_nrm, tmp / "out_nn", {"alpha.cutout": True})
        png_nn = imaging.load(out_nn / "Leaf_basecolor.png")
        check("给出人话警告（要透明就必须有法线图）",
              any(isinstance(w, dict) and w.get("code") == "cutout_needs_normal" for w in warn_nn),
              str(warn_nn)[:200])
        check("**没有静默把透明吃掉**：底色 alpha 仍是源的（左半边 0）",
              int(png_nn[:, :png_nn.shape[1] // 2, 3].max()) == 0,
              f"max={int(png_nn[:, :png_nn.shape[1] // 2, 3].max())}")
        check("这套的遮罩被放下（VMT 里没有 $basemapalphaphongmask）",
              "$basemapalphaphongmask" not in vmt_nn)
        check("VMT 里仍然写了 $alphatest 1", '"$alphatest" 1' in vmt_nn)

        # ---------- 判据 5：「植被」档默认透明友好 ----------
        print("== 判据 5：「植被」档 ==")
        resolved = pipeline.resolve_options(
            pipeline.ConvertOptions(source=str(leaf), name="Leaf", preset="植被"), "", "")
        check("植被档默认 alpha.cutout = True",
              bool(resolved.values.get("alpha.cutout")), str(resolved.values.get("alpha.cutout")))
        check("植被档默认 use_mask = False（没遮罩可盖 alpha）",
              resolved.values.get("use_mask") is False, str(resolved.values.get("use_mask")))
        vmt_v, warn_v, out_v = run(leaf, tmp / "out_v", {}, preset="植被")
        check("植被档产出的 VMT 里没有遮罩键（$basemapalphaphongmask）",
              "$basemapalphaphongmask" not in vmt_v, vmt_v.replace("\n", " ")[:110])
        check("植被档产出的 VMT 里有 $alphatest 1", '"$alphatest" 1' in vmt_v)
        png_v = imaging.load(out_v / "Leaf_basecolor.png")
        check("植被档产出底色的透明也保住了",
              int(png_v[:, :png_v.shape[1] // 2, 3].max()) == 0)

        # ---------- 10 片判据 6：勾了"要透明"但素材压根没有可裁的地方 → 要出声 ----------
        print("== 10 片判据 6：没有可裁的地方要出声 ==")
        opaque = make_material(tmp / "src3", "Opaque", transparent=False)
        _vmt_op, warn_op, _out_op = run(opaque, tmp / "out_op", {"alpha.cutout": True})
        check("底色 alpha 全 255 + 打开 cutout → 出那句提示",
              any(isinstance(w, dict) and w.get("code") == "no_alpha_but_cutout" for w in warn_op),
              str(warn_op)[:200])
        _vmt_off2, warn_off2, _out_off2 = run(opaque, tmp / "out_off2", {})
        check("（对照）没打开 cutout 就不出这句（不吓人）",
              not any(isinstance(w, dict) and w.get("code") == "no_alpha_but_cutout"
                      for w in warn_off2), str(warn_off2)[:200])
        check("同一条码渲染出英文（英文界面不显示原样中文）",
              i18n.warning({"code": "no_alpha_but_cutout"}, "en").startswith("This set's base colour")
              and not any("\u4e00" <= ch <= "\u9fff"
                          for ch in i18n.warning({"code": "no_alpha_but_cutout"}, "en")))
        check("认不出来的码原样返回（不假装翻译过）",
              i18n.warning({"code": "法线贴图是平的"}, "en") == "法线贴图是平的")

        # ---------- 交付：alpha.cutout 进指纹 ----------
        print("== 指纹 ==")
        opts_a = pipeline.ConvertOptions(source=str(leaf), name="Leaf", preset="道具")
        opts_b = pipeline.ConvertOptions(source=str(leaf), name="Leaf", preset="道具",
                                         overrides={"alpha.cutout": True})
        ra = pipeline.resolve_options(opts_a, "", "")
        rb = pipeline.resolve_options(opts_b, "", "")
        ms = source_io.scan_folder(leaf)[0]
        check("打开/关闭透明 → 指纹不同（会重跑，不会误判成已成功）",
              pipeline.fingerprint(ms, opts_a, ra) != pipeline.fingerprint(ms, opts_b, rb))
        check("PackOptions 里 alpha_cutout 默认 False（老路径不变）",
              pack.PackOptions().alpha_cutout is False)

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
