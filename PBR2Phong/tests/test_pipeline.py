"""core 的单测（实施计划 §9.4 第 1 层：core 单元测试）。

覆盖：曲线端点与单调性 / 通道搬运不串位 / 尺寸规则 / 输入层文件名解析 /
      命名层（对真实 school_gate.mdl 断言）。

跑法：python tests/test_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import curves, naming, pack, phong, source_io  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail and not ok else ""))


def test_curves():
    print("\n== 曲线 ==")
    check("r=1 → 指数通道 0", curves.exponent_channel(1.0) == 0, str(curves.exponent_channel(1.0)))
    check("r→0 → 指数通道 255（顶格）", curves.exponent_channel(1e-6) == 255)

    rs = np.linspace(0.01, 1.0, 200, dtype=np.float32)
    ch = curves.exponent_channel(rs).astype(np.int32)
    check("指数通道随粗糙度单调不增", bool(np.all(np.diff(ch) <= 0)))
    check("遮罩随粗糙度单调不增",
          bool(np.all(np.diff(curves.phong_mask(rs)) <= 0)))

    # 顶格阈值：0.8/r² > 150 ⇔ r < sqrt(0.8/150) = 0.0730
    check("顶格阈值 ≈ 0.073", abs(float(np.sqrt(0.8 / 150)) - 0.0730) < 0.001,
          str(float(np.sqrt(0.8 / 150))))
    check("r=0.05 判为顶格", curves.near_specular_clip_ratio(np.array([0.05], np.float32)) == 1.0)
    check("r=0.5 不顶格", curves.near_specular_clip_ratio(np.array([0.5], np.float32)) == 0.0)

    # 官方交叉验证：coach_head_exp 的 R 中位 13 ↔ 官方头部标量 $phongexponent 7~12
    r_at_13 = float(curves.exponent_to_roughness(13))
    e_at_13 = float(curves.roughness_to_exponent(r_at_13))
    check("R=13 → 指数落在官方头部区间 7~12", 7.0 <= e_at_13 <= 12.0, f"E={e_at_13:.2f}")

    lut = curves.lut_from_points([(0, 0), (0.5, 1), (1, 0)])
    check("LUT 长度与端点正确", len(lut) == 256 and lut[0] == 0 and abs(lut[-1]) < 1e-6)
    check("LUT 中点最大", lut[128] > 0.99)


def test_channels():
    print("\n== 通道搬运（不串位）==")
    h, w = 4, 8
    rough = np.tile(np.linspace(0, 255, w, dtype=np.uint8)[None, :], (h, 1))
    metal = np.zeros((h, w), np.uint8)
    metal[:, w // 2:] = 255
    exp = phong.exponent_map(rough, metal)
    check("exp 形状 = (H,W,3)", exp.shape == (h, w, 3), str(exp.shape))
    check("exp B 通道恒为 0", int(exp[:, :, 2].max()) == 0)
    check("exp R 左高右低（粗糙度左低右高）", int(exp[0, 0, 0]) == 255 and int(exp[0, -1, 0]) == 0,
          f"{exp[0,0,0]} / {exp[0,-1,0]}")
    check("exp G = 金属度", int(exp[0, 0, 1]) == 0 and int(exp[0, -1, 1]) == 255)

    mask = phong.mask_map(rough)
    check("遮罩左（不粗糙）亮、右（粗糙）暗", int(mask[0, 0]) == 255 and int(mask[0, -1]) == 0)
    # ★ 中段采样：端点断言会漏掉"整张图都算错"的 bug（踩过一次），必须查中间值
    mid = phong.mask_map(np.array([[128]], np.uint8))          # r≈0.502 → (1-r)³×1.1
    expect = round((1 - 128 / 255) ** 3 * 1.1 * 255)
    check("遮罩中段值 = (1−r)³×1.1", abs(int(mid[0, 0]) - expect) <= 1,
          f"得 {int(mid[0,0])}，应为 {expect}")
    mid_exp = curves.exponent_channel(np.array([128], np.uint8))
    check("uint8 输入按 0..255 解释（不是被 clip 成 1）",
          int(mid_exp[0]) < 60, f"得 {int(mid_exp[0])}（r=0.5 时指数应≈3.2 → 通道≈4）")

    base = np.dstack([np.full((h, w), 200, np.uint8)] * 3)
    comp = phong.composite_basecolor(base, np.full((h, w), 0, np.uint8), 0.5)
    check("AO=0 按 50% 压暗底色", int(comp[0, 0, 0]) == 100, str(comp[0, 0, 0]))

    nrm = np.dstack([np.full((h, w), 10, np.uint8),
                     np.full((h, w), 10, np.uint8),
                     np.full((h, w), 10, np.uint8)])
    flipped = phong.flip_normal_green(nrm)
    check("法线只翻 G、不动 R/B",
          int(flipped[0, 0, 0]) == 10 and int(flipped[0, 0, 1]) == 245 and int(flipped[0, 0, 2]) == 10)

    dark = phong.darken_basecolor(base, np.zeros((h, w), np.uint8), np.full((h, w), 255, np.uint8))
    check("压黑派：r=0 且全金属 → 压到 0", int(dark[0, 0, 0]) == 0, str(dark[0, 0, 0]))


def test_sizes():
    print("\n== 尺寸规则 ==")
    check("合并尺寸取各边较大（保证只放大）", pack._merge_size((256, 256), (512, 128)) == (512, 256))
    small = np.zeros((4, 4), np.uint8)
    up = __import__("core.imaging", fromlist=["x"]).resample(small, 16, 8)
    check("resample 到目标尺寸", up.shape == (8, 16), str(up.shape))


def test_source_io():
    print("\n== 输入层：文件名解析（含官方历史写法）==")
    cases = [
        ("Common Parts 1-BaseColor-2k.png", "shader.base_color", (2048, 2048), "Common Parts 1"),
        ("BodyRoughness-2048.png", "shader.roughness", (2048, 2048), "Body"),
        ("Couch-Metallic-1024px.png", "shader.metallic", (1024, 1024), "Couch"),
        ("Couch-Normal-1024x512.png", "standard.normal", (1024, 512), "Couch"),
        ("x-AmbientOcclusion-512.png", "misc.ao", (512, 512), "x"),
        ("随便一个名字.png", None, (0, 0), "随便一个名字"),
    ]
    for name, key, size, prefix in cases:
        got_key, sx, sy, got_prefix = source_io.parse_filename(name)
        check(f"{name} → {key}", got_key == key and (sx, sy) == size and got_prefix == prefix,
              f"实得 {got_key} {(sx, sy)} {got_prefix!r}")


def test_no_alpha_marker():
    """15-B：MB 新写法 `_NoAlpha`（没有 alpha 的底色）不许被认成 alpha 灰度图。

    历史症状（一类 2026-10-07 定位）：`Concrete_Grey-BaseColor-2k_NoAlpha.png` →
    ① 尺寸解析只看末段 → `NoAlpha` 不是尺寸 → **尺寸整个丢掉**；
    ② "粘着写法"回退里 `noalpha` 以 `alpha` 结尾 → 命中 `shader.alpha` → **底色静默进 `ignored`**。
    """
    print("\n== 输入层：MB 的 `_NoAlpha` 标记（15-B）==")
    import tempfile

    cases = [
        # 带 alpha 的底色 = 正名
        ("Concrete_Grey-BaseColor-2k.png", "shader.base_color", (2048, 2048), "Concrete Grey"),
        # 没有 alpha 的底色 = 正名 + `_NoAlpha`
        ("Concrete_Grey-BaseColor-2k_NoAlpha.png", "shader.base_color", (2048, 2048), "Concrete Grey"),
        # UDIM：标记插在瓦片号**之前**
        ("Body-BaseColor-2k_NoAlpha.1001.png", "shader.base_color", (2048, 2048), "Body"),
        # 用户自己起的 `NoAlphaFoo` 不许被误伤
        ("NoAlphaFoo-BaseColor-2k.png", "shader.base_color", (2048, 2048), "NoAlphaFoo"),
        # 瓦片号本身不是尺寸：没写尺寸时不许拿它凑数
        ("Body-BaseColor.1001.png", "shader.base_color", (0, 0), "Body"),
    ]
    for name, key, size, prefix in cases:
        got_key, sx, sy, got_prefix = source_io.parse_filename(name)
        check(f"{name} → {key}", got_key == key and (sx, sy) == size and got_prefix == prefix,
              f"实得 {got_key} {(sx, sy)} {got_prefix!r}")

    # 扫目录这一层才是"底色到底进没进 ignored"的现场（parse_filename 单独看不算数）
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for name in ("Concrete_Grey-BaseColor-2k_NoAlpha.png",
                     "Concrete_Grey-Roughness-2k.png",
                     "Concrete_Grey-Normal-2k.png"):
            (d / name).write_bytes(b"x")            # scan_folder 只看后缀，不读内容
        items = source_io.scan_folder(d)
        ms = items[0] if items else None
        check("扫目录只扫出一套", len(items) == 1, str(len(items)))
        check("`_NoAlpha` 的底色照样认成底色（没被丢进 ignored）",
              bool(ms) and "shader.base_color" in ms.images and not ms.ignored,
              (ms.summary() if ms else "没扫到"))
        # ⚠️ 用 getattr 取：反向实验要把这个文件拷到"改动前"的 commit 上跑，那时还没有这个字段 ——
        #    要的是**报红**（None ≠ True），不是崩掉。
        check("`_NoAlpha` 会被记下来（declared_no_alpha）",
              getattr(ms, "declared_no_alpha", None) is True, str(ms))
        check("报告里说明「这张底色没有 alpha」",
              bool(ms) and "没有 alpha" in ms.summary(), (ms.summary() if ms else "没扫到"))


def need_l4d2_model() -> tuple:
    """公开仓库前提（14-D）：真实模型来自 **L4D2 安装**，别人机器上多半没有。

    ⚠️ 缺了就**打印一行说明并跳过**（返回 `None`），**不许报红** —— 公开仓库里"缺依赖导致一片红"
    会把真正的回归淹掉。哪些套件需要什么前提写在 `README-工程说明.md`。
    """
    mdl = Path(r"D:\SteamLibrary\steamapps\common\Left 4 Dead 2"
               r"\left4dead2\models\custom\school_gate.mdl")
    if mdl.is_file():
        return mdl
    print("   ⏭ 跳过这几条：没找到 L4D2 的真实模型 school_gate.mdl（**公开仓库里属正常**）")
    print(f"      期望位置：{mdl}")
    return None


def test_naming():
    print("\n== 命名层：对真实 school_gate.mdl 断言 ==")
    mdl = need_l4d2_model()
    if mdl is None:
        return
    m = naming.read_mdl(mdl)
    # ⚠️ 这个模型用户改过好几次：2026-09-25 重导成**双材质**（`school_gate` + `school_gate_windows`），
    #    2026-10-07 又重导成**三个**（`School_Gate00/01/02`）→ 断言**别再硬编码具体材质名**，
    #    改成"从模型里读出来什么就断言什么"（跟着实物走，用户下次再重导也不会红）。
    check("$cdmaterials 解析正确",
          bool(m.cdmaterials) and m.cdmaterials[0] == "custom\\school_gate\\", str(m.cdmaterials))
    check("材质名解析正确（相对自身偏移）",
          len(m.textures) >= 2 and all("school_gate" in t.lower() for t in m.textures),
          str(m.textures))
    check("拼出的 VMT 路径正确",
          all(f"custom/school_gate/{t}.vmt" in m.expected_vmt_paths() for t in m.textures),
          str(m.expected_vmt_paths()))

    sg = naming.read_mdl(mdl.parent / "sportsground.mdl")
    check("能读出未赋材质的 no_material", "no_material" in sg.textures, str(sg.textures))

    mats = mdl.parents[2] / "materials"
    check("大小写敏感查盘能抓到不符",
          "实际是" in naming.check_path_case(mats, "custom/Basketball/Basketball.vmt"))


def test_vmt_and_validate():
    print("\n== VMT 解析 + 校验模型 ==")
    from core import validate, vmt

    sample = '"VertexLitGeneric"\n{\n\t"$basetexture" "custom/X/x"\n\t$phong 1\n}\n'
    params = vmt.parse(sample)
    check("能读到带引号与不带引号的键", params.get("$basetexture") == "custom/X/x"
          and params.get("$phong") == "1", str(params))

    patch = ('patch\n{\n\tinclude "materials/models/survivors/shared.vmt"\n\tinsert\n\t{\n'
             '\t\t$basetexture "a/b"\n\t}\n}\n')
    check("认得 patch 材质", vmt.is_patch(patch))
    check("能取出 include 路径",
          vmt.includes(patch) == ["materials/models/survivors/shared.vmt"], str(vmt.includes(patch)))

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mats = Path(tmp) / "materials"
        d = mats / "custom" / "Test"
        d.mkdir(parents=True)
        (d / "test.vmt").write_text('"VertexLitGeneric"\n{\n\t"$basetexture" "custom/Test/test"\n'
                                    '\t"$phong" 1\n}\n', encoding="utf-8")
        (d / "test.vtf").write_bytes(b"VTF\x00")
        rep = validate.ModelReport(model="t")
        validate._check_vmt_textures(mats, d / "test.vmt", rep)
        check("VMT 与 VTF 都在 → 不报拒绝", rep.ok and rep.vtf_checked == 1,
              str([str(f) for f in rep.findings]))

        (d / "miss.vmt").write_text('"VertexLitGeneric"\n{\n\t"$basetexture" "custom/Test/nope"\n}\n',
                                    encoding="utf-8")
        rep2 = validate.ModelReport(model="t")
        validate._check_vmt_textures(mats, d / "miss.vmt", rep2)
        check("贴图缺失 → 报拒绝", not rep2.ok, str([str(f) for f in rep2.findings]))

        check("大小写不符能被抓到",
              validate._case_lookup(mats, "custom/test/test.vmt")[0] == "case")
        check("不存在能区分出来",
              validate._case_lookup(mats, "custom/Test/none.vmt")[0] == "missing")


def test_batch_skip():
    print("\n== 批量：指纹与跳过 ==")
    import json
    import tempfile
    import types
    from core import pipeline, settings

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "Couch-BaseColor-64.png"
        src.write_bytes(b"x")
        matset = types.SimpleNamespace(images={"shader.base_color": src})
        options = pipeline.ConvertOptions(preset="武器-第一人称", ao=0.5, cdmaterials="custom", name="Couch")
        resolved = settings.resolve("武器-第一人称")
        resolved2 = settings.resolve("武器-第一人称", {"vmt.$phongboost": 30})

        fp1 = pipeline.fingerprint(matset, options, resolved)
        check("指纹稳定（同输入同参数两次一致）",
              fp1 == pipeline.fingerprint(matset, options, resolved))
        check("换了参数指纹就变", fp1 != pipeline.fingerprint(matset, options, resolved2))
        src.write_bytes(b"xy")
        check("输入文件变了指纹就变", fp1 != pipeline.fingerprint(matset, options, resolved))

        out = tmp / "out"
        out.mkdir()
        (out / "a.png").write_text("x")
        (out / pipeline.RECORD_NAME).write_text(json.dumps(
            {"指纹": fp1, "产物": {"png_basecolor": "a.png"}}), encoding="utf-8")
        check("指纹一致且产物都在 → 判定已完成", pipeline.already_done(out, fp1))
        check("指纹不一致 → 不跳过", not pipeline.already_done(out, "别的指纹"))
        (out / "a.png").unlink()
        check("产物缺了 → 不跳过", not pipeline.already_done(out, fp1))

        check("--set 的键=值 会被解析成正确类型",
              pipeline.overrides_from(pipeline.ConvertOptions(
                  sets=("vmt.$phongboost=30", "basecolor.darken_metal=true"))) ==
              {"basecolor.darken_metal": True, "vmt.$phongboost": 30})


def test_settings():
    print("\n== 三层参数继承 ==")
    import tempfile
    from core import settings

    r = settings.resolve("武器-第一人称")
    check("预设覆盖了全局默认", r.source_of("vmt.$phongboost").startswith("预设"), r.source_of("vmt.$phongboost"))
    check("预设没提的项走全局默认", r.source_of("colorspace.exponent") == "全局默认")
    check("能取到预设里的 VMT 参数", ("$phongalbedotint", 1) in r.vmt_params(), str(r.vmt_params()))
    check("报告句子 = 预设 + 覆盖数",
          r.report_line() == "这套 = 武器-第一人称预设", r.report_line())

    r2 = settings.resolve("武器-第一人称", {"vmt.$phongboost": 30, "basecolor.ao_amount": 0.25})
    check("素材级覆盖优先于预设", r2.values["vmt.$phongboost"] == 30)
    check("覆盖项来源标成『你改过』", r2.source_of("vmt.$phongboost") == "你改过")
    check("报告写出覆盖了几个", "覆盖了 2 个参数" in r2.report_line(), r2.report_line())

    try:
        settings.resolve("武器-第一人称", {"curve.mask_formula": "别的"})
        check("曲线不许在素材级覆盖", False, "居然没报错")
    except ValueError:
        check("曲线不许在素材级覆盖", True)

    try:
        settings.resolve("不存在的预设")
        check("用了不存在的预设会报错", False, "居然没报错")
    except KeyError:
        check("用了不存在的预设会报错", True)

    with tempfile.TemporaryDirectory() as tmp:
        settings.write_default_config(tmp)
        check("导出的 config.json 能被读回",
              settings.load_global(tmp)["curve.roughness_to_exponent"] == "linear_1_150")
        got = settings.load_presets(tmp)
        check("导出的预设能被读回，且和内置表一一对应（现在是 21 档）",
              set(got) == set(phong.PRESETS) and len(got) == 21, str(len(got)))
        r3 = settings.resolve("武器-第一人称", {}, {}, got)
        check("用磁盘上的预设解析结果一致", r3.values["vmt.$phongboost"] == r.values["vmt.$phongboost"])
        # 预设名是**用户可见名**，可能带 `/`（用户自己存的也可能）→ 落盘必须 sanitize
        check("预设名带斜杠也能安全落盘（玻璃/投掷物）",
              "投掷物·玻璃" in got and settings.preset_filename("玻璃/投掷物") == "玻璃_投掷物.json",
              settings.preset_filename("玻璃/投掷物"))


def test_rgb_gray_regression():
    """回归：**RGB 三通道**的灰度图（Blender/MB 就是这么写的）不能走坏。

    踩过的 bug：`_gray()` 用 `.mean(axis=2)` 得到 0~255 的 float，被下游当成 0~1
    整片 clip 成 1 → 指数贴图全算错。合成素材当年用的是单通道 PNG，恰好绕开了这条路。
    """
    print("\n== 回归：RGB 灰度图不会算错 ==")
    import tempfile
    from core import curves, imaging, pack, phong, source_io

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        h = w = 8
        rough_u8 = np.full((h, w), 102, np.uint8)          # r = 0.4 → 期望 E=5 → R=7
        rough_u8[0, 0] = 0                                  # 极光滑 → 顶格 255
        rgb = np.dstack([rough_u8] * 3)                     # ★ 关键：存成 RGB 三通道
        imaging.save(rgb, tmp / "T-Roughness-8.png")
        imaging.save(np.dstack([np.full((h, w), 0, np.uint8)] * 3), tmp / "T-Metallic-8.png")
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), tmp / "T-BaseColor-8.png")

        ms = source_io.scan_folder(tmp)[0]
        res = pack.build(ms, pack.PackOptions(mask_carrier="basecolor"))
        want = int(curves.exponent_channel(np.uint8(102)))
        got = int(res.exp[1, 1, 0])
        check("RGB 灰度粗糙度 → 指数通道正确", got == want, f"得 {got}，应为 {want}")
        check("极光滑处顶格到 255", int(res.exp[0, 0, 0]) == 255, str(int(res.exp[0, 0, 0])))

        # 静默算错的守门人：0~255 的 float 必须直接报错，而不是被 clip 成 1
        try:
            phong.exponent_map(np.full((2, 2), 128.0, np.float32), np.zeros((2, 2), np.float32))
            check("0~255 的 float 会被拦下（不再静默 clip）", False, "居然没报错")
        except ValueError:
            check("0~255 的 float 会被拦下（不再静默 clip）", True)


def test_flat_normal_warning():
    """回归：真实素材（ShuiMa）的法线图是**平的**，用户却以为有凹凸 —— 必须报出来。"""
    print("\n== 回归：平法线图会被告知 ==")
    import tempfile
    from core import imaging, pack, source_io

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        h = w = 8
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), tmp / "F-BaseColor-8.png")
        imaging.save(np.dstack([np.full((h, w), 102, np.uint8)] * 3), tmp / "F-Roughness-8.png")

        flat = np.dstack([np.full((h, w), 128, np.uint8)] * 2 + [np.full((h, w), 255, np.uint8)])
        imaging.save(flat, tmp / "Flat-Normal-8.png")
        res_flat = pack.build(source_io.scan_folder(tmp)[0], pack.PackOptions())
        check("平法线图会出警告",
              any(isinstance(w_, dict) and w_.get("code") == "normal_is_flat"
                  for w_ in res_flat.warnings), str(res_flat.warnings))

        bumpy = flat.copy()
        bumpy[0, 0, 0] = 200                                # 一点真起伏 → 不该报
        imaging.save(bumpy, tmp / "Bumpy-Normal-8.png")
        tmp2 = tmp / "sub"
        tmp2.mkdir()
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), tmp2 / "B-BaseColor-8.png")
        imaging.save(bumpy, tmp2 / "Bumpy-Normal-8.png")
        res_ok = pack.build(source_io.scan_folder(tmp2)[0], pack.PackOptions())
        check("真有起伏的法线图不报",
              not any(isinstance(w_, dict) and w_.get("code") == "normal_is_flat"
                      for w_ in res_ok.warnings),
              str(res_ok.warnings))


def test_deploy_no_backup():
    """回归：用户 2026-09-25 拍板 A —— 写进 materials **不留备份、不留清单**（覆盖就是覆盖）。"""
    print("\n== 回归：部署不留备份/清单 ==")
    import tempfile
    from core import deploy

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        root = tmp / "materials"
        (root / "custom" / "X").mkdir(parents=True)
        src = tmp / "a.vtf"
        src.write_bytes(b"NEW")
        dest = root / "custom" / "X" / "a.vtf"
        dest.write_bytes(b"OLD")

        done = deploy.install(root, [(src, "custom/X/a.vtf")])
        check("覆盖记成「覆盖」", done[0].action == "覆盖" and done[0].dest == "custom/X/a.vtf", str(done))
        check("文件真被覆盖了", dest.read_bytes() == b"NEW")
        check("没有产生备份目录", not (root / "_pbr2phong_backup").exists())
        check("没有产生写入清单", not list(root.glob("_pbr2phong_manifest_*.json")))

        src2 = tmp / "b.vtf"
        src2.write_bytes(b"B")
        done2 = deploy.install(root, [(src2, "custom/X/b.vtf")])
        check("新文件记成「新增」", done2[0].action == "新增", str(done2))

        try:
            deploy.install(tmp / "nope", [(src, "x.vtf")])
            check("materials 目录不存在时报错", False, "居然没报错")
        except NotADirectoryError:
            check("materials 目录不存在时报错", True)


def test_conflict_ask():
    """13-C：**不静默覆盖** —— 目标目录 / materials 已有同名产物时，必须先问（`confirm`）。

    必败样例自检（13 单 §6-2 要求）：同一场景下 `force` 会真覆盖、而"拒绝"时旧文件**逐字节没动**
    —— 两条一起断言，证明这锁分辨得出"问了 / 没问"（改之前 core 里 `ask` 是死代码，
    `confirm` 一次也不会被调用 → 本测试第一条就会红）。
    """
    print("\n== 13-C：同名产物必须停下来问（不静默覆盖） ==")
    import tempfile
    from core import imaging, pipeline, vtf

    real_convert = vtf.convert

    def fake_convert(png, out_dir, **kw):
        """假装 VTFCmd：只落一个空 .vtf（本测试验的是"冲突闸门"，不是 VTF 编码）。"""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / ((kw.get("output_name") or Path(png).stem) + ".vtf")
        target.write_bytes(b"fake-vtf")
        return target

    def opts_for(out, **kw):
        return pipeline.ConvertOptions(source=str(src), name="T", cdmaterials="custom",
                                       out=str(out), **kw)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "src"
        src.mkdir()
        h = w = 8
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), src / "F-BaseColor-8.png")
        imaging.save(np.dstack([np.full((h, w), 100, np.uint8)] * 3), src / "F-Roughness-8.png")
        imaging.save(np.dstack([np.full((h, w), 128, np.uint8)] * 2 + [np.full((h, w), 255, np.uint8)]),
                     src / "F-Normal-8.png")
        matset = source_io.scan_folder(src)[0]
        out = tmp / "out"
        vtf.convert = fake_convert
        try:
            asked = []

            def rec(answer):
                def _f(conflicts):
                    asked.append(list(conflicts))
                    return answer
                return _f

            o1 = opts_for(out)
            got1 = pipeline.convert_set(matset, o1, pipeline.resolve_options(o1, "", ""),
                                        confirm=rec(True))
            vmt = Path(got1["out_dir"]) / "T.vmt"
            check("首次转换（目录是空的）→ 不问", not asked and vmt.is_file() and not got1["skipped"],
                  f"asked={asked} vmt={vmt.is_file()}")
            before = vmt.read_bytes()

            # 换一个参数 → 指纹变了 → 不是"指纹一致跳过"，而是**撞上已存在的同名产物**
            o2 = opts_for(out, sets=("vmt.$phongboost=30",))
            asked.clear()
            got2 = pipeline.convert_set(matset, o2, pipeline.resolve_options(o2, "", ""),
                                        confirm=rec(False))
            check("第二次撞上同名产物 → **真的问了**（`confirm` 被调用）", bool(asked),
                  str(asked)[:200])
            first = asked[0] if asked else []      # ⚠️ 护栏：没问的时候也要能干净地报红，别 IndexError
            check("问的清单里真的是同名文件（码，不是人话）",
                  bool(first) and all(why == "exists"
                                      and rel.endswith((".vmt", ".png", ".vtf", ".json", ".txt"))
                                      for rel, why in first),
                  str(first)[:200])
            check("拒绝覆盖 → 这一套记为跳过、原因是 conflict",
                  got2.get("skipped") is True and got2.get("skip_reason") == "conflict",
                  f"skipped={got2.get('skipped')} reason={got2.get('skip_reason')}")
            check("拒绝覆盖 → 旧产物**逐字节没被动**", vmt.read_bytes() == before)
            check("拒绝覆盖 → 连记录文件都没重写（一个字节都不写）",
                  (Path(got2["out_dir"]) / pipeline.RECORD_NAME).read_bytes()
                  == (Path(got1["out_dir"]) / pipeline.RECORD_NAME).read_bytes())

            # ⭐ 自检（必败样例）：同一刀加 force → 不问、且**真的覆盖出新内容**
            o3 = opts_for(out, sets=("vmt.$phongboost=30",), force=True)
            asked.clear()
            pipeline.convert_set(matset, o3, pipeline.resolve_options(o3, "", ""),
                                 confirm=rec(False))
            check("自检：force=True 时不再问（显式覆盖 = 不用问）", not asked, str(asked)[:120])
            check("自检：force=True **真的覆盖了**（内容与拒绝那次不同）", vmt.read_bytes() != before)

            # ---- 部署到 materials：同样不许静默覆盖 ----
            mroot = tmp / "materials"
            (mroot / "custom").mkdir(parents=True)
            old = mroot / "custom" / "T.vmt"
            old.write_bytes(b"OLD-IN-GAME")
            out2 = tmp / "out2"
            o4 = opts_for(out2, deploy=True, materials=str(mroot))
            r4 = pipeline.resolve_options(o4, "", "")
            asked.clear()
            got4 = pipeline.convert_set(matset, o4, r4, confirm=rec(False))
            check("部署撞上 materials 同名 → 问了（码 = in_materials）",
                  bool(asked) and all(why == "in_materials" for _rel, why in asked[0]),
                  str(asked)[:200])
            check("拒绝部署 → materials 里的文件没被动", old.read_bytes() == b"OLD-IN-GAME")
            check("拒绝部署 → 会说出一句人话（警告）",
                  any(isinstance(w, dict) and w.get("code") == "deploy_skipped_conflicts"
                      for w in got4["record"].get("警告", [])),
                  str(got4["record"].get("警告"))[:200])
            check("拒绝部署 → 产物照样出了（跳过的是部署，不是这一套）",
                  not got4["skipped"] and (out2 / "T.vmt").is_file())

            asked.clear()
            got5 = pipeline.convert_set(matset, o4, r4, confirm=rec(False))
            # 同参数的第二次：指纹一致 → 走"已完成就跳过"，**不该**当成冲突来问
            check("同样参数再跑：指纹一致 → 跳过且不问（两种跳过原因分得清）",
                  not asked and got5.get("skipped") and got5.get("skip_reason") == "fingerprint",
                  f"asked={asked} reason={got5.get('skip_reason')}")

            out3 = tmp / "out3"
            o6 = opts_for(out3, deploy=True, materials=str(mroot), yes=True)
            asked.clear()
            pipeline.convert_set(matset, o6, pipeline.resolve_options(o6, "", ""),
                                 confirm=rec(False))
            check("--yes（显式覆盖）→ 部署不再问、且真覆盖了",
                  not asked and old.read_bytes() != b"OLD-IN-GAME",
                  f"asked={asked} now={old.read_bytes()[:12]}")
        finally:
            vtf.convert = real_convert


def test_cli_conflict_ask():
    """13-C：CLI 的 `_ask` —— core 给的是**码**，人话在 CLI 这层渲染；没终端时 fail-closed。"""
    print("\n== 13-C：CLI 撞名时说什么 ==")
    import builtins
    import contextlib
    import io

    from cli import convert as cli

    buf = io.StringIO()
    real_input = builtins.input
    builtins.input = lambda _prompt="": (_ for _ in ()).throw(EOFError())
    try:
        with contextlib.redirect_stdout(buf):
            ok = cli._ask([("T.vmt", "exists"), ("materials/custom/T.vmt", "in_materials")])
    finally:
        builtins.input = real_input
    out = buf.getvalue()
    check("CLI：冲突项按码渲染成人话（不许把 exists 这种码漏到用户眼前）",
          "已有同名文件" in out and "materials 里已有同名文件" in out and "exists" not in out,
          out.replace("\n", " / ")[:200])
    check("CLI：没有可问答的终端 → 按「不覆盖」处理（fail-closed，绝不静默写）",
          ok is False and "--force" in out, f"ok={ok} out={out.replace(chr(10), ' / ')[:160]}")


def test_flat_maps_warning():
    """13-A：粗糙度是**常量 / 只有两个值**、金属度**全 0 / 全 1** → 必须出声。

    ⚠️ 必败样例自检（13 单 §6-2）：**反向样例一起断言** —— 有过渡的粗糙度、只取 0/255 两档的
    金属度（合法的金属遮罩）**都不许报**。检测器要是"见谁都报"，这几条立刻红。
    ⚠️ 判据只看**源图**：用户拖「粗糙度整体偏移」不许影响判定（旋钮把斜坡推平了也不该改口）。
    """
    print("\n== 13-A：贴图没信息量要出声 ==")
    import tempfile
    from core import imaging, pack, source_io

    counter = [0]

    def build_case(tmp, gray, metal=None, **opt_kw):
        counter[0] += 1
        d = Path(tmp) / f"c{counter[0]}"
        d.mkdir()
        h = w = 8
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3), d / "F-BaseColor-8.png")
        imaging.save(np.dstack([gray] * 3), d / "F-Roughness-8.png")
        if metal is not None:
            imaging.save(np.dstack([metal] * 3), d / "F-Metallic-8.png")
        return pack.build(source_io.scan_folder(d)[0], pack.PackOptions(**opt_kw))

    def hit(res, code):
        # 12 单：警告是**码 + 参数**（不再是中文句子）→ 断言认码
        return [w for w in res.warnings if isinstance(w, dict) and w.get("code") == code]

    def any_code(res, codes):
        return any(isinstance(w, dict) and w.get("code") in codes for w in res.warnings)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        h = w = 8
        const = np.full((h, w), 128, np.uint8)
        ramp = np.tile(np.linspace(20, 230, w, dtype=np.uint8)[None, :], (h, 1))
        two = np.zeros((h, w), np.uint8)
        two[:, w // 2:] = 255
        zeros = np.zeros((h, w), np.uint8)
        ones = np.full((h, w), 255, np.uint8)

        check("粗糙度整张一个值 → 出声", bool(hit(build_case(tmp, const), "roughness_is_constant")),
              str(build_case(tmp, const).warnings)[:200])
        check("粗糙度只有两个值 → 出声", bool(hit(build_case(tmp, two), "roughness_has_two_values")))
        check("粗糙度有过渡（**反向样例**）→ 不许报",
              not any_code(build_case(tmp, ramp), ("roughness_is_constant", "roughness_has_two_values")),
              str(build_case(tmp, ramp).warnings)[:200])
        check("金属度全 0 → 出声", bool(hit(build_case(tmp, ramp, zeros), "metallic_all_zero")))
        check("金属度全 255 → 出声", bool(hit(build_case(tmp, ramp, ones), "metallic_all_one")))
        check("金属度只有 0/255 两档（合法金属遮罩，**反向样例**）→ 不许报",
              not any_code(build_case(tmp, ramp, two), ("metallic_all_zero", "metallic_all_one")))
        check("金属度有灰阶（反向样例）→ 不许报",
              not any_code(build_case(tmp, ramp, np.full((h, w), 100, np.uint8)),
                           ("metallic_all_zero", "metallic_all_one")))
        # 判据只看源图：拖「粗糙度整体偏移」把斜坡推平/推到极端，都不许改变判定
        check("拖了「粗糙度整体偏移」的有过渡图 → 仍然不许报（判定看源图）",
              not any_code(build_case(tmp, ramp, roughness_offset=0.4),
                           ("roughness_is_constant", "roughness_has_two_values")))
        check("拖了「粗糙度整体偏移」的常量图 → 仍然出声（旋钮不能把事实盖掉）",
              bool(hit(build_case(tmp, const, roughness_offset=0.4), "roughness_is_constant")))


def test_list_materials():
    """13-B：`--mdl … --list-materials` —— 只把模型里的材质名列出来，**不转换、不写任何文件**。

    ⚠️ 必败样例：模型不存在 / 只给 `--list-materials` 没给模型 → 都必须**退出码 2 + 说人话**。
    """
    print("\n== 13-B：列模型的材质名（--list-materials） ==")
    import contextlib
    import io
    import sys as _sys
    import tempfile

    from cli import convert as cli

    mdl = need_l4d2_model()
    if mdl is None:
        return
    from core import pipeline as _pl
    expect = list(_pl.names_from_model(mdl)[1])

    def run_cli(argv):
        buf = io.StringIO()
        old = _sys.argv
        _sys.argv = ["cli.convert", *argv]
        try:
            with contextlib.redirect_stdout(buf):
                code = cli.main()
        except SystemExit as e:      # ⚠️ 护栏：argparse 遇到**不认识的参数**会直接 SystemExit(2)
            code = int(e.code or 2)  #    —— 别让它把整个脚本崩掉（那会盖住后面的断言）
        finally:
            _sys.argv = old
        return code, buf.getvalue()

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        code, text = run_cli(["--mdl", str(mdl), "--list-materials", "--out", str(out)])
        check("退出码 0", code == 0, f"code={code} {text[:160]}")
        check(f"列出了全部材质名（真实双材质模型：{expect}）",
              len(expect) >= 2 and all(n in text for n in expect), text[:220])
        check("只列不转：**没有**写任何文件", not out.exists(), f"out={out.exists()}")
        check("说清了这是「只列材质名」", "只列材质名" in text, text[:160])
        # ⚠️ 13-B 返工（一类 2026-10-01 实测；`_task/13` §2.5 判据 3）：CLI 输出里**不许再出现**
        #    "分几次跑" —— 正确口径是"本次就给每个名字各写一份 VMT、都指向这次的贴图"。
        check("13-B 返工：CLI 说清「每个名字各写一份 VMT、都指向这次的贴图」，且那句错的短语没了",
              "各写一份 VMT" in text and "不同贴图" in text and "分几次跑" not in text,
              text.replace("\n", " / ")[:240])

        code2, text2 = run_cli(["--mdl", str(Path(tmp) / "nope.mdl"), "--list-materials"])
        check("必败样例：模型不存在 → 退出码 2 且说人话",
              code2 == 2 and "找不到模型" in text2, f"code={code2} {text2[:160]}")

        code3, text3 = run_cli(["--list-materials"])
        check("必败样例：只给 --list-materials 没给模型 → 退出码 2 且给用法",
              code3 == 2 and "--mdl" in text3, f"code={code3} {text3[:160]}")

        code4, text4 = run_cli([])
        check("必败样例：什么都没给 → 退出码 2 且给用法（没素材夹不再静默崩）",
              code4 == 2 and "--list-materials" in text4, f"code={code4} {text4[:160]}")


def test_cli_readable_log():
    """14-A：CLI 真跑一次转换 → `log.txt` 是**人话**（不含裸 `"code":`），`phong_input.json` 仍是**码**。

    ⚠️ 这条必须用**真会冒警告**的素材（这里用"法线是平的 + 缺粗糙度/金属度/AO"那套），
    否则"log 里没有 code"是空话 —— 本套件里那条 GUI 侧的锁就是在无警告素材上过的。
    """
    print("\n== 14-A：log.txt 对用户可读（真跑一次 CLI） ==")
    import contextlib
    import io
    import json
    import sys as _sys
    import tempfile

    from core import imaging, vtf
    from cli import convert as cli

    if not vtf.find_vtfcmd():
        # 14-E：缺 VTFCmd 是公开仓库 / CI 的常态 → 说明并跳过（不报红）
        print("   本机没有 VTFCmd.exe → 跳过这条端到端（公开仓库 / CI 上属正常）")
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "src"
        src.mkdir()
        h = w = 8
        imaging.save(np.dstack([np.full((h, w), 200, np.uint8)] * 3),
                     src / "F-BaseColor-8_NoAlpha.png")   # 15-B：MB 的"无 alpha 底色"写法
        imaging.save(np.dstack([np.full((h, w), 128, np.uint8)] * 2
                               + [np.full((h, w), 255, np.uint8)]), src / "F-Normal-8.png")
        out = tmp / "out"
        buf = io.StringIO()
        old = _sys.argv
        _sys.argv = ["cli.convert", str(src), "--name", "LogT", "--out", str(out)]
        try:
            with contextlib.redirect_stdout(buf):
                code = cli.main()
        finally:
            _sys.argv = old
        text = buf.getvalue()
        log = (out / "log.txt").read_text(encoding="utf-8-sig", errors="replace")
        rec = json.loads((out / "phong_input.json").read_text(encoding="utf-8-sig"))
        check("CLI 真跑成功（退出码 0）", code == 0, f"code={code} {text[-160:]}")
        check("这套确实冒了警告（不然下面两条是空话）", bool(rec.get("警告")),
              str(rec.get("警告"))[:160])
        check("14-A：`log.txt` 里**没有裸的 code**", '"code":' not in log,
              str([ln.strip() for ln in log.splitlines() if '"code"' in ln][:2]))
        check("14-A：`log.txt` 里是渲染后的人话",
              any("法线贴图是平的" in ln for ln in log.splitlines()), log[:0] or "")
        check("14-A：机器凭据 `phong_input.json` 里**仍是码**",
              all(isinstance(x, dict) and "code" in x for x in rec["警告"]),
              str(rec["警告"])[:160])
        check("CLI 控制台也打了人话（不是 dict）", "⚠" in text and "{'code'" not in text,
              text[-200:].replace("\n", " / "))
        # 15-B：文件名标了 `_NoAlpha` → 报告里要照说"这张底色没有 alpha"（机器记录 + 可读日志都有）
        check("15-B：记录里说明这张底色没有 alpha",
              "没有 alpha" in str(rec.get("底色 alpha", "")), str(rec.get("底色 alpha")))
        check("15-B：可读日志里也有这句",
              any("没有 alpha" in ln for ln in log.splitlines()), log[:0] or "")


def test_slot_mapping():
    """15-C：**逐槽各配一套素材** —— 两个槽各出一份 VMT、`$basetexture` 各指各自贴图，
    产物按槽名命名互不覆盖，映射写进 `phong_input.json` 的 `逐槽映射`。
    """
    print("\n== 15-C：逐槽各配一套素材（两个槽） ==")
    import json
    import tempfile
    from dataclasses import replace

    from core import imaging, pipeline, settings, vmt, vtf

    if not vtf.find_vtfcmd():
        # 14-E：缺 VTFCmd 是公开仓库 / CI 的常态 → 说明并跳过（不报红）
        print("   本机没有 VTFCmd.exe → 跳过这条端到端（公开仓库 / CI 上属正常）")
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dirs = []
        for name, value in (("AlphaCouch", 60), ("BetaWall", 200)):
            d = tmp / name
            d.mkdir()
            imaging.save(np.dstack([np.full((8, 8), value, np.uint8)] * 3),
                         d / f"{name}-BaseColor-8.png")
            dirs.append(d)
        set_a = source_io.scan_folder(dirs[0])[0]
        set_b = source_io.scan_folder(dirs[1])[0]

        out = tmp / "out"
        options = pipeline.ConvertOptions(source=str(dirs[0]), name="slotX",
                                          out=str(out), cdmaterials="custom")
        # 15-H：**逐槽参数**各归各 —— 只给第一个槽一条覆盖项，第二个槽不动
        per_slot = {"school_gate": {"vmt.$surfaceprop": "metal"},
                    "school_gate_windows": {}}
        pairs = [("school_gate", set_a), ("school_gate_windows", set_b)]
        for slot, ms in pairs:
            opts = replace(options, name=slot, overrides=dict(per_slot[slot]))
            res = pipeline.resolve_options(opts)         # 每个槽**各解析一次**
            got = pipeline.convert_set(ms, opts, res, [slot], "custom", slot=slot)
            check(f"槽 {slot} 跑成功（没被跳过）", not got["skipped"], str(got.get("skip_reason")))

        check("两个槽各写一份 VMT",
              (out / "school_gate.vmt").is_file() and (out / "school_gate_windows.vmt").is_file())
        text_a = (out / "school_gate.vmt").read_text(encoding="utf-8", errors="replace")
        text_b = (out / "school_gate_windows.vmt").read_text(encoding="utf-8", errors="replace")
        base_a = vmt.parse(text_a).get("$basetexture", "")
        base_b = vmt.parse(text_b).get("$basetexture", "")
        check("$basetexture 各指各自贴图（且互不相同）",
              base_a.endswith("school_gate_basecolor")
              and base_b.endswith("school_gate_windows_basecolor")
              and base_a != base_b, f"{base_a!r} / {base_b!r}")
        check("产物按槽名命名、互不覆盖",
              (out / "school_gate_basecolor.png").is_file()
              and (out / "school_gate_windows_basecolor.png").is_file(),
              str(sorted(p.name for p in out.glob("*.png"))))
        # 15-H：逐槽参数 —— A 槽的 $surfaceprop 只落在 A 槽的 VMT 上，B 槽一点没沾
        check("15-H：只给 A 槽改的表面类型落到 A 槽的 VMT",
              '$surfaceprop' in text_a and 'metal' in text_a, text_a[-160:].replace("\n", " "))
        check("15-H：B 槽没被 A 槽的参数污染",
              '$surfaceprop' not in text_b or 'metal' not in text_b,
              text_b[-160:].replace("\n", " "))
        rec = json.loads((out / pipeline.RECORD_NAME).read_text(encoding="utf-8-sig"))
        mapping = rec.get("逐槽映射") or {}
        check("逐槽映射写进了 phong_input.json",
              set(mapping) == {"school_gate", "school_gate_windows"}
              and mapping["school_gate"]["素材"] == "AlphaCouch"
              and mapping["school_gate_windows"]["素材"] == "BetaWall",
              str(mapping)[:200])
        check("15-H：逐槽参数按 `slot:<槽名>.<键>` 各归各",
              mapping["school_gate"].get("覆盖项") == {"slot:school_gate.vmt.$surfaceprop": "metal"}
              and mapping["school_gate_windows"].get("覆盖项") == {},
              str({k: v.get("覆盖项") for k, v in mapping.items()}))

        # 15-C 返工 / 缺陷 D 的**端到端**一条：底色名字认不出来 → 手工指认 → 真能转出 VMT
        #   用户原话："我只需要一个 School_Gate01-BaseColor-awdjw-1k.png 就能直接让它少识别一张
        #   基础色贴图" —— 指认之后必须跟正常素材一样跑通。
        rw_dir = tmp / "Weird"
        rw_dir.mkdir()
        weird = rw_dir / "School_Gate01-BaseColor-awdjw-1k.png"
        imaging.save(np.dstack([np.full((8, 8), 120, np.uint8)] * 3), weird)
        imaging.save(np.dstack([np.full((8, 8), 90, np.uint8)] * 3),
                     rw_dir / "School_Gate01-Roughness-8.png")
        weird_set = source_io.scan_folder(tmp / "Weird")[0]
        check("前提：这张底色认不出来（进了 unknown）",
              [p.name for p in weird_set.unknown] == [weird.name] and weird_set.get("shader.base_color") is None,
              str([p.name for p in weird_set.unknown]))
        check("手工指成底色 → 这一步成功", weird_set.assign(weird, "shader.base_color"))
        rw_out = tmp / "out-weird"
        rw_opts = replace(options, name="School_Gate01", out=str(rw_out), force=True)
        rw_res = pipeline.resolve_options(rw_opts)
        got_w = pipeline.convert_set(weird_set, rw_opts, rw_res, ["School_Gate01"], "custom",
                                     slot="School_Gate01")
        check("15-C：指认之后**真的转换成功**（没被跳过、出了 VMT）",
              not got_w["skipped"] and (rw_out / "School_Gate01.vmt").is_file(),
              f"{got_w.get('skip_reason')} / {sorted(p.name for p in rw_out.glob('*'))}")


def test_unknown_files():
    """15-C 缺陷 D：文件名认不出类型的图**不许静默丢掉** —— 要列出来、还要能手工指定类型。"""
    print("\n== 15-C 缺陷 D：认不出的图要被看见 ==")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        d = tmp / "Gate"
        d.mkdir()
        (d / "Gate-Roughness-8.png").write_bytes(b"x")
        weird = d / "Gate-BaseColor-awdjw-1k.png"      # 解析不出类型（老写法里被 continue 丢掉）
        weird.write_bytes(b"x")
        check("前提：这个名字确实认不出来", source_io.parse_filename(weird.name)[0] is None,
              str(source_io.parse_filename(weird.name)))
        ms = source_io.scan_folder(tmp)[0]
        check("它被记进 unknown（不再静默丢）",
              [p.name for p in ms.unknown] == [weird.name], str([p.name for p in ms.unknown]))
        check("表格那一格会写清「认不出是什么」",
              weird.name in ms.unrecognized_text() and "认不出" in ms.unrecognized_text(),
              ms.unrecognized_text())
        check("手工指定类型 → 当正常素材用",
              ms.assign(weird, "shader.base_color") and ms.get("shader.base_color") == weird,
              str(ms.images))
        check("指定完 unknown 里就没有它了", not ms.unknown, str(ms.unknown))
        check("没在 unknown 里的文件指不动（不乱指）",
              ms.assign(tmp / "nope.png", "shader.metallic") is False)
        # 「一张都没认出来、但有认不出的图」的那一套也要收进来（否则界面又"什么都不说"）
        d2 = tmp / "OnlyWeird"
        d2.mkdir()
        (d2 / "whatever-1k.png").write_bytes(b"x")
        items = source_io.scan_folder(tmp)
        check("只有认不出的图 → 那一套也要出现在结果里",
              any(it.group == "OnlyWeird" and len(it.unknown) == 1 for it in items),
              str([(it.group, len(it.unknown)) for it in items]))


def main() -> int:
    print("== core 单测 ==")
    test_curves()
    test_channels()
    test_sizes()
    test_source_io()
    test_no_alpha_marker()
    test_unknown_files()
    test_naming()
    test_vmt_and_validate()
    test_batch_skip()
    test_settings()
    test_rgb_gray_regression()
    test_flat_normal_warning()
    test_deploy_no_backup()
    test_conflict_ask()
    test_cli_conflict_ask()
    test_flat_maps_warning()
    test_list_materials()
    test_cli_readable_log()
    test_slot_mapping()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败清单：")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print("✓ 全绿")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
