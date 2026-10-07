# -*- coding: utf-8 -*-
"""笔刷路线（`LightmappedGeneric`）单测 + 端到端 + 产物自检。

对应施工单 `_task/01-笔刷模式.md` §6 的验收判据：
  1. 曲线锚点/上限、金属 `max` 兜底、uint8 强校验、**VMT 零禁令键**
  2. VMT 实物：`LightmappedGeneric` + 必需参数
  3. **遮罩真的写进去了**：把产出的法线图 alpha 解回来，与 roughness 逐像素对，报误差
  4. 端到端自检：**从产物核对回源素材**（用 `阶段0_实测/vtfio.py` 解 VTF）
  6. 回归：模型线既有套件不许变红（由外部跑 test_pipeline / test_gui_flow / test_first_run）

跑法：`python tests/test_brush.py`（需要 VTFCmd，和 test_gui_flow 一样）
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                      # PBR2Phong/
sys.path.insert(0, str(HERE.parents[1] / "阶段0_实测"))     # 解 VTF 用的 vtfio

import numpy as np  # noqa: E402

from core import brush, imaging, pipeline, source_io, vtf  # noqa: E402

PASS: list = []
FAIL: list = []
NUMBERS: dict = {}


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def _make_set(folder: Path, name: str = "BrushWall") -> None:
    """造一套像 Material Bakery 产物的素材（RGB 三通道灰度图 + 一张有起伏的法线）。"""
    h = w = 16
    imaging.save(np.dstack([np.full((h, w), 180, np.uint8)] * 3), folder / f"{name}-BaseColor-16.png")
    rough = np.full((h, w), 128, np.uint8)
    rough[:, :4] = 0                                   # 左四列极光滑 → 遮罩应接近曲线上限
    rough[:, 12:] = 230                                # 最右四列很粗糙 → 遮罩应为 0
    imaging.save(np.dstack([rough] * 3), folder / f"{name}-Roughness-16.png")
    imaging.save(np.dstack([np.zeros((h, w), np.uint8)] * 3), folder / f"{name}-Metallic-16.png")
    nrm = np.dstack([np.full((h, w), 128, np.uint8),
                     np.full((h, w), 128, np.uint8),
                     np.full((h, w), 255, np.uint8)])
    nrm[0, 0, 0] = 200                                 # 一点真起伏（免得被判成"平法线"）
    nrm[0, 0, 1] = 40                                  # 绿通道给个非 128 的值，方便验"翻绿"
    imaging.save(nrm, folder / f"{name}-Normal-16.png")


# ---------------------------------------------------------------- §6.1 曲线与守卫

def test_curve():
    print("\n== §6.1 遮罩曲线 / 数值守卫 ==")
    u8 = lambda v: np.array([[v]], np.uint8)           # noqa: E731
    top = int(brush.envmap_mask(u8(0))[0, 0])
    check("锚点①：roughness=0 → 顶到曲线上限 112", top == 112, str(top))
    zero = int(brush.envmap_mask(u8(204))[0, 0])
    check("锚点②：roughness 超过归零点 → 0", zero == 0, str(zero))
    mid = int(brush.envmap_mask(u8(128))[0, 0])
    check("中段值在 0 与上限之间", 0 < mid < 112, str(mid))
    NUMBERS["曲线中段(r=128)"] = mid
    nr = int(brush.envmap_mask(u8(120))[0, 0])
    nz = int(brush.envmap_mask(u8(147))[0, 0])
    check("归零点 = 1−108/255（120/255 还有一点、147/255 刚好归零）", nr > 0 and nz == 0, f"{nr} / {nz}")
    ramp = brush.envmap_mask(np.arange(0, 256, 8, dtype=np.uint8).reshape(1, -1))
    check("随粗糙度单调不增", bool(np.all(np.diff(ramp[0].astype(int)) <= 0)), str(ramp[0][:5]))
    metal = int(brush.envmap_mask(u8(204), u8(255))[0, 0])
    check("金属 max 兜底：粗糙的金属也全反光", metal == 255, str(metal))
    try:
        brush.envmap_mask(np.full((2, 2), 0.5, np.float32))
        check("uint8 强校验：传 float 要报错", False, "居然没报错")
    except ValueError:
        check("uint8 强校验：传 float 要报错", True)


# ---------------------------------------------------------------- §6.2 VMT 实物

def test_vmt():
    print("\n== §6.2 VMT 组装 / 零禁令键 ==")
    keys = {k.lower(): v for k, v in brush.params("custom/W")}
    check("默认（出遮罩）写 $envmap env_cubemap", keys.get("$envmap") == "env_cubemap", str(sorted(keys)))
    check("默认遮罩载体 = 法线 alpha → $normalmapalphaenvmapmask 1",
          keys.get("$normalmapalphaenvmapmask") == 1, str(sorted(keys)))
    check("底图 = <prefix>_basecolor", keys.get("$basetexture") == "custom/W_basecolor")
    check("法线 = <prefix>_normal", keys.get("$bumpmap") == "custom/W_normal")

    off = {k.lower(): v for k, v in brush.params("custom/W", use_mask=False)}
    check("显式关遮罩 → 不写 $envmap*", not any(k.startswith("$envmap") for k in off), str(sorted(off)))

    nb = {k.lower(): v for k, v in brush.params("custom/W", has_normal=False, mask_carrier="basecolor")}
    check("没法线 → 退到底色 alpha：$basealphaenvmapmask 1", nb.get("$basealphaenvmapmask") == 1,
          str(sorted(nb)))

    preset_like = [("$phong", 1), ("$phongboost", 60), ("$phongexponenttexture", "x_exp"),
                   ("$basemapalphaphongmask", 1), ("$invertphongmask", 1), ("$envmapmask", "x_mask"),
                   ("$envmaplightscale", 1), ("$envmap", "env_cubemap"), ("$envmaptint", "[1 1 1]"),
                   ("$model", 1), ("$surfaceprop", "plastic")]
    text = brush.render("custom/W", has_normal=True, mask_carrier="normal",
                        use_mask=True, extra=preset_like)
    bad = brush.forbidden_keys_in(text)
    check("零禁令键（$phong*/$envmapmask/$envmaplightscale/继承的 $envmap* 全被丢）", not bad, str(bad))
    check("$surfaceprop 这类通用属性留下", "$surfaceprop" in text)
    check("第一行是 LightmappedGeneric", text.splitlines()[0].strip() == '"LightmappedGeneric"',
          text.splitlines()[0])
    NUMBERS["VMT 实物"] = text
    print("    —— 交付用的 VMT 实物 ——")
    for line in text.strip().splitlines():
        print(f"    {line}")


# ---------------------------------------------------------------- §6.3/6.4 端到端 + 自检

def _run(src: Path, tmp: Path, matset, **kw):
    kw.setdefault("name", "BrushWall")
    opts = pipeline.ConvertOptions(source=str(src), cdmaterials="custom",
                                   out=str(tmp / "out"), materials=str(tmp / "materials"),
                                   deploy=True, force=True, route="brush", **kw)
    resolved = pipeline.resolve_options(opts, "", "")
    return opts, pipeline.convert_set(matset, opts, resolved, None, None, confirm=lambda c: True)


def test_end_to_end():
    print("\n== §6.3 / §6.4 端到端 + 产物自检 ==")
    if not vtf.find_vtfcmd():
        # 14-E：缺 VTFCmd 是公开仓库 / CI 的常态 → 说明并跳过这一段（不报红）
        print("   ⏭ 跳过端到端段：本机没有 VTFCmd.exe（这段要真出 VTF）")
        return
    try:
        import vtfio                                 # 阶段0_实测/vtfio.py：解 VTF 顶层 mip
    except ImportError:
        # ⚠️ 14-D：`阶段0_实测/` **不传**（公开仓库里没有）→ 缺了就**说明并跳过**，不许崩、也不许报红
        print("   ⏭ 跳过产物自检：本机没有 `阶段0_实测/vtfio.py`（公开仓库里不传那个目录）")
        print("      （照样能自己看：产物目录里的 `*_basecolor.vtf` 用 VTFEdit 打开即可）")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "素材"
        src.mkdir()
        _make_set(src)
        (tmp / "materials").mkdir()
        matset = source_io.scan_folder(src)[0]

        # ---- ① 默认：底色 + 法线 + 遮罩 ----
        _o, got = _run(src, tmp, matset)
        out = Path(got["out_dir"])
        check("出底色 PNG + 法线 PNG", (out / "BrushWall_basecolor.png").is_file()
              and (out / "BrushWall_normal.png").is_file())
        check("**不**出指数 PNG（笔刷用不上）", not (out / "BrushWall_exp.png").exists())
        check("VTF 只有底色 + 法线", sorted(got["vtfs"]) == ["basecolor", "normal"],
              str(sorted(got["vtfs"])))
        vmt_text = (out / "BrushWall.vmt").read_text(encoding="utf-8")
        check("产出的 .vmt 零禁令键", not brush.forbidden_keys_in(vmt_text),
              str(brush.forbidden_keys_in(vmt_text)))
        check("产出的 .vmt 写的是 $normalmapalphaenvmapmask 1",
              "$normalmapalphaenvmapmask" in vmt_text.lower())
        check("部署进 materials：2 VTF + 1 VMT",
              sorted(p.name for p in (tmp / "materials" / "custom").iterdir()) ==
              ["BrushWall.vmt", "BrushWall_basecolor.vtf", "BrushWall_normal.vtf"],
              str(sorted(p.name for p in (tmp / "materials" / "custom").iterdir())))
        check("记录里路线=brush、遮罩=True",
              got["record"].get("路线") == "brush" and got["record"].get("笔刷遮罩") is True,
              f"{got['record'].get('路线')} / {got['record'].get('笔刷遮罩')}")

        # ---- ③ 把法线 VTF 的 alpha 解回来，跟 roughness 逐像素对 ----
        _hdr, rgba = vtfio.read_top_mip(out / "vtf" / "BrushWall_normal.vtf")
        alpha = np.asarray(rgba)[:, :, 3]
        rough_u8 = np.rint(imaging.load(src / "BrushWall-Roughness-16.png")[:, :, :3]
                           .mean(axis=2)).astype(np.uint8)
        want = brush.envmap_mask(rough_u8, np.zeros_like(rough_u8))
        diff = np.abs(alpha.astype(int) - want.astype(int))
        NUMBERS["遮罩逐像素误差(法线alpha vs 曲线)"] = (int(diff.max()), float(diff.mean()))
        check("法线 alpha == 曲线算出的遮罩（DXT5 alpha，误差 ≤2）",
              int(diff.max()) <= 2, f"max={int(diff.max())} mean={float(diff.mean()):.2f}")
        check("极光滑那几列最亮、最粗糙那几列为 0",
              int(alpha[:, 0].mean()) > 100 and int(alpha[:, 14].mean()) == 0,
              f"{int(alpha[:,0].mean())} / {int(alpha[:,14].mean())}")

        # ---- ④ 从产物核对回源素材（exp8 式自检）----
        _h1, base_rgba = vtfio.read_top_mip(out / "vtf" / "BrushWall_basecolor.vtf")
        _h2, nrm_rgba = vtfio.read_top_mip(out / "vtf" / "BrushWall_normal.vtf")
        src_base = imaging.load(src / "BrushWall-BaseColor-16.png")
        src_nrm = imaging.load(src / "BrushWall-Normal-16.png")
        b_diff = float(np.abs(base_rgba[:, :, :3].astype(int) - src_base[:, :, :3].astype(int)).mean())
        n_rb = float(np.abs(nrm_rgba[:, :, [0, 2]].astype(int)
                            - src_nrm[:, :, [0, 2]].astype(int)).mean())
        n_g = float(np.abs(nrm_rgba[:, :, 1].astype(int) - (255 - src_nrm[:, :, 1].astype(int))).mean())
        NUMBERS["底色 DXT5 往返平均差"] = round(b_diff, 2)
        NUMBERS["法线 R/B 未动"] = round(n_rb, 2)
        NUMBERS["法线绿通道 = 源取反"] = round(n_g, 2)
        check("底色往返平均差不超 2", b_diff <= 2.0, f"{b_diff:.2f}")
        check("法线 R/B 一个字节没动", n_rb <= 1.0, f"{n_rb:.2f}")
        check("法线绿通道 == 源取反（Blender→Source 翻绿）", n_g <= 2.0, f"{n_g:.2f}")
        check("法线 B 通道 ≥ 128（朝向正确）", int(nrm_rgba[:, :, 2].min()) >= 120,
              str(int(nrm_rgba[:, :, 2].min())))

        # ---- ⑤ 关掉遮罩：只出底色 + 法线 ----
        _o2, got2 = _run(src, tmp, matset, name="NoMask", brush_mask=False)
        vmt2 = (Path(got2["out_dir"]) / "NoMask.vmt").read_text(encoding="utf-8")
        check("关遮罩：VMT 里没有 envmap 家族", "envmap" not in vmt2.lower(),
              vmt2.replace("\n", " ")[:120])
        check("关遮罩：记录里 笔刷遮罩=False", got2["record"].get("笔刷遮罩") is False)

        # ---- ⑥ 指纹把路线/遮罩算进去了 ----
        fp_on = pipeline.fingerprint(matset, _o, pipeline.resolve_options(_o, "", ""))
        fp_off = pipeline.fingerprint(matset, _o2, pipeline.resolve_options(_o2, "", ""))
        model_opts = pipeline.ConvertOptions(source=str(src), name="BrushWall", route="model")
        fp_model = pipeline.fingerprint(matset, model_opts,
                                        pipeline.resolve_options(model_opts, "", ""))
        check("路线/遮罩变了 → 指纹跟着变", len({fp_on, fp_off, fp_model}) == 3,
              f"{fp_on} {fp_off} {fp_model}")


# ---------------------------------------------------------------- 界面接线

def test_gui_wiring():
    print("\n== 界面接线：路线选择 ==")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-brush-gui-")
    from PySide6 import QtWidgets

    from gui.main import MainWindow

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    win = MainWindow()
    app.processEvents()
    page = win.page_convert
    check("默认走模型路线", page.current_route() == ("model", False), str(page.current_route()))
    check("遮罩勾选框在模型路线下是禁用的", not page.chk_brush_mask.isEnabled())
    page.rb_route_brush.setChecked(True)
    app.processEvents()
    check("切到笔刷 → 勾选框可用且**默认已勾**（v1 范围含遮罩）",
          page.chk_brush_mask.isEnabled() and page.chk_brush_mask.isChecked())
    check("读出来是笔刷 + 出遮罩", page.current_route() == ("brush", True), str(page.current_route()))
    check("提示语讲的是笔刷", "lightmap" in page.lbl_route_hint.text(), page.lbl_route_hint.text()[:50])
    page.chk_brush_mask.setChecked(False)
    check("取消勾选 → 读出来 False", page.current_route() == ("brush", False), str(page.current_route()))
    page.rb_route_model.setChecked(True)
    app.processEvents()
    check("切回模型 → 读出来 model/False", page.current_route() == ("model", False),
          str(page.current_route()))
    win.close()


def main() -> int:
    print("== 笔刷路线单测（施工单 _task/01-笔刷模式.md §6）==")
    test_curve()
    test_vmt()
    test_end_to_end()
    test_gui_wiring()
    print("\n—— 关键数字 ——")
    for k, v in NUMBERS.items():
        if k != "VMT 实物":
            print(f"   {k}: {v}")
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"   失败：{f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
