"""转换流水线：**GUI 与 CLI 共用的那一份实现**（铁律：数学与流程只写一次）。

原来这套逻辑长在 `cli/convert.py` 里。GUI 要复用它，就把它提到 core：
  · `ConvertOptions` —— 一次转换的全部设置（取代 argparse 的 Namespace）
  · `resolve_options()` —— 三层参数继承（素材级 > 预设档 > 全局默认）
  · `fingerprint()` / `already_done()` —— 确定性重跑与"跳过已成功"
  · `convert_set()` —— 一套素材：3 张 PNG → VTF → VMT →（可选）写进 materials

core 不 print、不 import GUI：需要用户确认时用 `confirm` 回调（CLI 给控制台询问，GUI 给对话框）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import brush, curves, deploy, imaging, pack, phong, settings, vmt, vtf

DEFAULT_MATERIALS = Path(r"D:\SteamLibrary\steamapps\common\Left 4 Dead 2\left4dead2\materials")
RECORD_NAME = "phong_input.json"

# 输出 VTF 的格式选择（依据官方语料实测，见实施计划 §0.6 #13）：
#   底色 DXT5 且**不加额外标志**（官方底色只有 EIGHT_BIT_ALPHA）；
#   指数贴图官方清一色 DXT1 + ANISOTROPIC；法线 DXT5 + NORMAL。
VTF_FORMATS = {
    "basecolor": ("DXT5", ()),
    "normal": ("DXT5", ("NORMAL",)),
    "exp": ("DXT1", ("ANISOTROPIC",)),
    # 13-E 眼睛专用图（官方 `$Iris` / `$AmbientOcclTexture` 指向的图）：
    #   虹膜带 alpha（瞳孔/眼白遮罩会用），走 DXT5 最稳；眼睛 AO 是灰度，DXT1 够。
    "iris": ("DXT5", ()),
    "eyeao": ("DXT1", ()),
}


class MissingInput(ValueError):
    """缺了**必须由用户提供**的输入（13-E 眼睛档的虹膜图是第一个）。

    ⚠️ 只带**码**（`eye.iris` / `eye.ao`），**不在 core 里拼人话** —— 人话由 CLI / GUI 过 i18n 渲染
    （`_task/13` §2.7⑥-5：缺虹膜图要给人话，不是 KeyError / traceback）。
    """

    def __init__(self, code: str, **args):
        super().__init__(code)
        self.code = code
        self.info = args


@dataclass
class ConvertOptions:
    """一次转换的设置。字段名刻意与旧的 argparse 参数一致，便于平滑迁移。"""
    source: str = ""
    name: str = ""
    cdmaterials: str = "custom"
    preset: str = phong.DEFAULT_PRESET
    out: str = ""
    deploy: bool = False
    materials: str = str(DEFAULT_MATERIALS)
    force: bool = False
    yes: bool = False
    ao: float | None = None
    darken: bool = False
    no_flip_normal: bool = False
    sets: tuple = ()                      # 素材级覆盖：("vmt.$phongboost=30", ...)
    overrides: dict = field(default_factory=dict)   # GUI 直接给的素材级覆盖（按键/值）
    vtfcmd: str = ""                      # VTFCmd.exe 路径（空 = 自动找常见位置）
    route: str = "model"                  # "model"（VertexLitGeneric+Phong）| "brush"（LightmappedGeneric）
    # 笔刷路线要不要出 envmap 遮罩。**默认出** —— 施工单 `_task/01-笔刷模式.md` §2 写明用户拍板的
    # v1 范围含遮罩；要只出底色+法线就显式传 False（CLI `--no-brush-mask` / 界面取消勾选）。
    brush_mask: bool = True


def coerce(text: str):
    """把 `键=值` 的 值 还原成合适的类型（数字/真假/字符串）。"""
    low = text.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def overrides_from(options: ConvertOptions) -> dict:
    """界面上那些"顺手覆盖"合并成素材级覆盖字典（GUI 直接给的优先，随后是命令行式的）。"""
    overrides = dict(options.overrides or {})
    if options.ao is not None:
        overrides["basecolor.ao_amount"] = options.ao
    if options.darken:
        overrides["basecolor.darken_metal"] = True
    if options.no_flip_normal:
        overrides["normal.flip_green"] = False
    for item in options.sets:
        if "=" in item:
            k, _, val = item.partition("=")
            overrides[k.strip()] = coerce(val.strip())
    return overrides


def resolve_options(options: ConvertOptions, config_root="", presets_root="") -> settings.Resolved:
    """把三层继承解析出来（素材级 > 预设档 > 全局默认），带每项的"来源"。"""
    global_values = settings.load_global(config_root) if config_root else {}
    presets = settings.load_presets(presets_root) if presets_root else {}
    return settings.resolve(options.preset, overrides_from(options), global_values, presets)


def fingerprint(matset, options: ConvertOptions, resolved) -> str:
    """参数指纹 = 输入文件（名字/大小/时间）+ **三层继承后的全部参数**。

    用途只有一个：判断"这套素材上次是不是已经用同样的参数成功处理过"，重跑时好跳过。
    所以它必须覆盖一切会改变产物的东西（用解析后的 values，改 config.json 或预设也会变指纹）。
    """
    h = hashlib.sha256()
    h.update(json.dumps({
        "参数": resolved.values, "cdmaterials": options.cdmaterials, "name": options.name,
        # ⚠️ 路线也是"会改变产物"的选项：模型线出 3 张图 + VertexLitGeneric，笔刷线出 2 张 + LMG。
        #    不写进指纹的话，换路线重跑会被误判成"已成功"而跳过。
        "路线": getattr(options, "route", "model"),
        "笔刷遮罩": bool(getattr(options, "brush_mask", True)),
    }, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    for key, path in sorted(matset.images.items()):
        st = Path(path).stat()
        h.update(f"{key}|{Path(path).name}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8"))
    return h.hexdigest()[:16]


def load_record(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}


def already_done(out_dir: Path, fp: str) -> bool:
    """上次的记录指纹一致、且产物都还在 → 这套不用重做。"""
    rec = load_record(out_dir / RECORD_NAME)
    if rec.get("指纹") != fp:
        return False
    produced = rec.get("产物") or {}
    return bool(produced) and all((out_dir / rel).is_file() for rel in produced.values())


def files_from_record(out_dir: Path, record: dict, cdm: str) -> list:
    """从 `phong_input.json` 的产物清单里重建"要部署哪些文件"。"""
    files = []
    for key, rel in (record.get("产物") or {}).items():
        if not (key.startswith("vtf_") or key.startswith("vmt_")):
            continue
        src = out_dir / rel
        if src.is_file():
            files.append((src, f"{cdm}/{src.name}" if cdm else src.name))
    return files


def planned_outputs(out_dir: Path, tex_name: str, names, kinds,
                    has_normal: bool = True, extra=()) -> list:
    """这次会写哪几个文件 —— **写盘之前**就能算出来（13-C 拿它查同名冲突）。

    ⚠️ 必须与真正的落盘位置逐一对上：PNG 在 `out_dir/`、VTF 在 `out_dir/vtf/`、VMT 在 `out_dir/`，
    外加记录文件 `phong_input.json` 与 `log.txt`（`pack.write_outputs` / `vtf.convert` / `vmt.write`
    三处的命名规则）。法线那张可能压根不出（素材没有法线图）→ 按 `has_normal` 决定要不要算它。
    `extra`：13-E 的眼睛专用图（虹膜 / 眼睛 AO）这类**额外产物** —— 由调用方按当前档位算好传进来。
    """
    out = []
    for kind in kinds:
        if kind == "normal" and not has_normal:
            continue
        out.append(out_dir / f"{tex_name}_{kind}.png")
        out.append(out_dir / "vtf" / f"{tex_name}_{kind}.vtf")
    out += list(extra)
    out += [out_dir / f"{n}.vmt" for n in names]
    out += [out_dir / RECORD_NAME, out_dir / "log.txt"]
    return out


def names_from_model(model_path) -> tuple:
    """读编译好的 `.mdl`，返回 (cdmaterials, [材质名, ...])。

    为什么以模型为准：`$cdmaterials` 与材质名在**编译时就被烘进 MDL**，事后改文件夹必须重编译。
    所以 `.mdl` 是权威来源（比 SMD、比用户记忆都可靠）。
    一个模型可能有多个材质槽，但它们常共用同一套贴图 → 一套贴图要生成多个 VMT。
    """
    from . import naming
    mdl = naming.read_mdl(model_path)
    cdm = mdl.cdmaterials[0] if mdl.cdmaterials else ""
    names = [t for t in mdl.textures if t.lower() != "no_material"]
    return cdm, names, mdl


def convert_set(matset, options: ConvertOptions, resolved, vmt_names=None,
                cdm_override=None, confirm=None, progress=None) -> dict:
    """一套素材走完全流程。返回结果字典（含 out_dir / 产物 / 警告 / deployed）。

    vmt_names / cdm_override：由"读 .mdl"那条路提供（一个模型可能有多个材质槽，
    但它们可以共用同一套贴图 → **一套贴图 + 多个 VMT**）。
    progress：可选回调 `f(阶段名, 0..1)`，给 GUI 显示进度用。
    """
    say = progress or (lambda stage, frac: None)
    v = resolved.values
    route = (getattr(options, "route", "model") or "model").strip().lower()
    if route not in ("model", "brush"):
        raise ValueError(f"不认识的路线：{route}（只支持 model / brush）")
    is_brush = route == "brush"
    # ⚠️ PackOptions 只在 core 里造一次（`pack.options_from_values`）—— GUI 预览用的是**同一份**，
    #    免得预览与真转换两条路各写一套、慢慢漂移（漂移了预览就会骗人）。
    pack_options = pack.options_from_values(v, route=route,
                                            brush_mask=bool(options.brush_mask))
    tex_name = options.name or matset.group or "material"
    out_dir = Path(options.out) if options.out else Path(options.source).parent / f"{tex_name}_phong"
    out_dir.mkdir(parents=True, exist_ok=True)
    cdm = (cdm_override or options.cdmaterials or "").strip("/\\").replace("\\", "/")
    ask = confirm or (lambda conflicts: options.yes or False)

    fp = fingerprint(matset, options, resolved)
    if already_done(out_dir, fp) and not options.force:
        # ⚠️ 跳过 ≠ 什么都不做：`--deploy` 是**另一件事**（把已有产物搬进游戏）。
        #    第一版在这里直接 return，"重跑 + 部署"就什么都不干（踩过）。
        got = {"skipped": True, "skip_reason": "fingerprint", "out_dir": out_dir, "name": tex_name,
               "fingerprint": fp,
               "vmts": [], "vtfs": {}, "pngs": {}, "record": {}, "deployed": None}
        if options.deploy:
            rec = load_record(out_dir / RECORD_NAME)
            files = files_from_record(out_dir, rec, cdm)
            if files:
                got["deployed"] = deploy.install(Path(options.materials), files)
        return got

    # 13-C：**不静默覆盖**。这两个清单要在写盘前算好（下面用它查同名冲突）。
    #     ⚠️ 改之前 `ask` 定义了却**从没被调用** —— `confirm` 是一整条死代码：`--out` 与
    #     `--deploy` 都在偷偷覆盖，GUI 那个冲突对话框根本不会弹（i18n 却写着"不会偷偷覆盖"）。
    kinds = ("basecolor", "normal") if is_brush else ("basecolor", "normal", "exp")
    names = [tex_name] if is_brush else [n for n in (vmt_names or [tex_name]) if n]
    # 13-E：眼睛档（官方 `EyeRefract`）要看**用户给的虹膜 / 眼睛 AO** 在不在 —— 这两个值在这里先取出来，
    # 冲突闸门（要算额外产物）与后面的 VMT/VTF 支路共用同一份。
    eye_iris_src = str(v.get("eye.iris") or "").strip()
    eye_ao_src = str(v.get("eye.ao") or "").strip()
    is_eye = str(v.get("shader.name") or "") == "EyeRefract"
    eye_extra = ([out_dir / "vtf" / f"{tex_name}_iris.vtf"] if is_eye and eye_iris_src else []) + \
                ([out_dir / "vtf" / f"{tex_name}_eyeao.vtf"] if is_eye and eye_ao_src else [])

    say("通道打包", 0.1)
    result = pack.build(matset, pack_options)
    if is_brush and matset.get("misc.ao", "standard.ao") is not None:
        result.warnings.append(pack.warn("brush_ao_not_baked"))
    # ⚠️ 冲突项用 **码**（`exists` / `in_materials`）而不是人话 —— core 不产出给人看的字面量，
    #    人话由 CLI / GUI 各自过 i18n。
    conflicts = [(str(p.relative_to(out_dir)).replace("\\", "/"), "exists")
                 for p in planned_outputs(out_dir, tex_name, names, kinds,
                                          has_normal=result.normal is not None,
                                          extra=eye_extra) if p.is_file()]
    if conflicts and not (options.force or options.yes) and not ask(conflicts):
        # 用户没让覆盖 → 这一套**整块跳过**：一个字节都不写（连记录文件也不动）
        return {"skipped": True, "skip_reason": "conflict", "out_dir": out_dir, "name": tex_name,
                "fingerprint": fp, "vmts": [], "vtfs": {}, "pngs": {}, "record": {},
                "deployed": None, "conflicts": [rel for rel, _why in conflicts]}
    pngs = pack.write_outputs(result, out_dir, tex_name, kinds=kinds)

    say("PNG → VTF", 0.4)
    vtfs = {}
    for kind, png in pngs.items():
        fmt, flags = VTF_FORMATS[kind]
        vtfs[kind] = vtf.convert(png, out_dir / "vtf", fmt=fmt, alpha_format=fmt,
                                 flags=flags, output_name=f"{tex_name}_{kind}",
                                 vtfcmd=options.vtfcmd or None)

    # 13-E：眼睛专用图（用户给的虹膜 / 眼睛 AO）→ 也出 VTF，命名 `<贴图基名>_iris` / `_eyeao`
    #    （官方 `$Iris` 指向的图名跟 VMT 名不一样，官方自己也这么干 → 我们按自己的命名法，交付里写清）。
    if is_eye:
        for kind, src in (("iris", eye_iris_src), ("eyeao", eye_ao_src)):
            if not src:
                continue
            if not Path(src).is_file():
                raise MissingInput(f"eye.{kind}", path=src)
            fmt, flags = VTF_FORMATS[kind]
            vtfs[kind] = vtf.convert(Path(src), out_dir / "vtf", fmt=fmt, alpha_format=fmt,
                                     flags=flags, output_name=f"{tex_name}_{kind}",
                                     vtfcmd=options.vtfcmd or None)

    say("生成 .vmt", 0.8)
    prefix = f"{cdm}/{tex_name}" if cdm else tex_name
    if is_brush:
        # 笔刷 = LightmappedGeneric：底色 + 法线（+ 可选 envmap 遮罩塞 alpha）。
        # 模型专用的 `$phong*` 与整个 `$envmap*` 家族都被 `brush.params()` 丢掉。
        dropped_envmap = [k for k, _ in resolved.vmt_params() if k.lower().startswith("$envmap")]
        if dropped_envmap:
            result.warnings.append(pack.warn("brush_dropped_envmap_params", n=len(dropped_envmap)))
        vmt_text = vmt.render(brush.SHADER, brush.params(
            prefix, has_normal=(result.normal is not None),
            mask_carrier=result.mask_carrier_used,
            use_mask=bool(options.brush_mask),
            extra=resolved.vmt_params()))
        if options.brush_mask:
            carrier = result.mask_carrier_used or "basecolor"
            key = "$normalmapalphaenvmapmask" if carrier == "normal" else "$basealphaenvmapmask"
            result.warnings.append(pack.warn("brush_mask_carrier_key", carrier=carrier, key=key))
        forbidden = brush.forbidden_keys_in(vmt_text)
        if forbidden:
            result.warnings.append(pack.warn("brush_forbidden_keys", keys=forbidden))
    else:
        # 2026-09-27（08 单 S5）：有的档要用**别的着色器** —— 角色-眼睛官方就是 `EyeRefract`
        # （不是 VertexLitGeneric）。缺省仍是 VLG，所以老档位的产出**一个字节没变**。
        shader_name = str(v.get("shader.name") or "VertexLitGeneric")
        if shader_name == "EyeRefract":
            # 13-E：**官方对齐**的眼睛材质。官方 8 份眼睛 VMT 里**没有** `$basetexture`、也没有
            # `$surfaceprop`（见 `Textures/survivors/*/*_eyeball_*.vmt`）→ 这条支路只写官方那套键，
            # 外加我们的 `$Iris`（必填）/ `$AmbientOcclTexture`（选填）。
            if not eye_iris_src:
                # 缺虹膜图 —— 抛**带码**的异常，人话由 CLI / GUI 渲染（core 不产人话）
                raise MissingInput("eye.iris")
            vmt_text = vmt.render_eyerefract(f"{prefix}_iris",
                                            f"{prefix}_eyeao" if eye_ao_src else "")
            result.warnings.append(pack.warn("eye_eyerefract_written"))
        else:
            params = [("$basetexture", f"{prefix}_basecolor")]
            if result.normal is not None:
                params.append(("$bumpmap", f"{prefix}_normal"))
            if v.get("use_exponent_texture", True):
                params.append(("$phongexponenttexture", f"{prefix}_exp"))
            if shader_name != "VertexLitGeneric":
                # ⚠️ 换了着色器就别把 Phong 那套塞进去（`$phong*` / `$bumpmap` 对 EyeRefract 无意义，
                #    写进去只会让 VMT 变得四不像）。只留底色 + 预设自己带的那几个键。
                params = [(k, val) for k, val in params if k in ("$basetexture", "$surfaceprop")]
                result.warnings.append(pack.warn("other_shader_kept_base_only", shader=shader_name))
            params += resolved.vmt_params()
            # 09 单：材质本身要透明（树叶 / 铁网 / 栅栏）→ 写 `$alphatest 1`（**二值裁剪**）。
            # ⚠️ 禁令：`$alphatest` 与 `$translucent` **绝不同时写**（半透明混合会让树叶边缘发黑）
            #    → 既然用户说了"要透明"，就把 `$translucent` 摘掉（并说明为什么）。
            if bool(v.get("alpha.cutout")):
                dropped = [k for k, _ in params if k.lower() == "$translucent"]
                if dropped:
                    params = [(k, val) for k, val in params if k.lower() != "$translucent"]
                    result.warnings.append(pack.warn("cutout_replaced_translucent"))
                if not any(k.lower() == "$alphatest" for k, _ in params):
                    params.append(("$alphatest", 1))
                    result.warnings.append(pack.warn("cutout_wrote_alphatest"))
            # ★ 遮罩放进底色 alpha 时，必须显式让引擎去读它；否则引擎去读 `$bumpmap` 的 alpha，
            #   我们算出来的遮罩就被无视了（这个坑在真实素材上当场撞到）。
            # ⚠️ 09 单的反向情形：遮罩**实际落在法线 alpha**（或这次压根不出遮罩）时，预设里若还写着
            #   `$basemapalphaphongmask 1`，它会**指错地方** —— 引擎转去把底色的 alpha 当遮罩
            #   （而底色的 alpha 现在装的是"叶子哪里透明"）→ 必须摘掉。
            if result.mask_carrier_used != "basecolor":
                stale = [k for k, _ in params if k.lower() == "$basemapalphaphongmask"]
                if stale:
                    params = [(k, val) for k, val in params
                              if k.lower() != "$basemapalphaphongmask"]
                    result.warnings.append(pack.warn("basemapalphaphongmask_removed"))
            if shader_name == "VertexLitGeneric" and result.mask_carrier_used == "basecolor" and \
                    "$basemapalphaphongmask" not in {k.lower() for k, _ in params}:
                params.append(("$basemapalphaphongmask", 1))
                result.warnings.append(pack.warn("basemapalphaphongmask_added"))
            vmt_text = vmt.render(shader_name, params)

    if is_brush and vmt_names:
        result.warnings.append(pack.warn("brush_ignores_model_names"))
    vmt_paths = [(n, vmt.write(vmt_text, out_dir / f"{n}.vmt")) for n in names]

    rough_src = matset.get("shader.roughness")
    clip_ratio = None
    if rough_src is not None:
        rough_arr = imaging.load(rough_src)[:, :, 0].astype("float32") / 255.0
        clip_ratio = round(curves.near_specular_clip_ratio(rough_arr), 4)

    # phong_input.json —— 确定性重跑的凭据（实施计划 §9.1）
    # ⚠️ 键必须带前缀：png 与 vtf 两类都有 basecolor/normal/exp，
    #    第一版直接合并两个 dict，同名键被后写的覆盖 → PNG 全从记录里消失了。
    produced = {}
    for kind, p in pngs.items():
        produced[f"png_{kind}"] = str(Path(p).relative_to(out_dir)).replace("\\", "/")
    for kind, p in vtfs.items():
        produced[f"vtf_{kind}"] = str(Path(p).relative_to(out_dir)).replace("\\", "/")
    for n, p in vmt_paths:
        produced[f"vmt_{n}"] = str(p.relative_to(out_dir)).replace("\\", "/")
    record = {
        "格式": "pbr2phong/input", "版本": 1, "指纹": fp,
        "组名": matset.group, "识别方式": matset.source,
        "材质名": names, "贴图基名": tex_name, "$cdmaterials": cdm,
        "路线": route, "笔刷遮罩": (bool(options.brush_mask) if is_brush else None),
        "预设": resolved.preset_name, "这套是": resolved.report_line(),
        "覆盖项": {k: resolved.values[k] for k in resolved.override_keys},
        "参数来源": resolved.sources_report(), "生效参数": resolved.values,
        "输入映射": {k: Path(v2).name for k, v2 in matset.images.items()},
        "认出来但本版不用": matset.ignored,
        "输出尺寸": {k: (list(s) if s else None) for k, s in result.sizes.items()},
        "被顶格的近镜面像素占比": clip_ratio,
        "产物": produced, "警告": result.warnings,
    }
    (out_dir / RECORD_NAME).write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "log.txt").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n\n--- .vmt ---\n" + vmt_text,
        encoding="utf-8-sig")   # 带 BOM：Windows 的记事本 / PowerShell 才不会读成乱码

    deployed = None
    if options.deploy:
        say("写进 materials", 0.9)
        files = [(p, f"{cdm}/{p.name}" if cdm else p.name) for p in vtfs.values()]
        for n, p in vmt_paths:
            files.append((p, f"{cdm}/{n}.vmt" if cdm else f"{n}.vmt"))
        root = Path(options.materials)
        # 13-C：部署同样**不许静默覆盖** —— `deploy.py` 的注释一直这么写，但调用方从没问过。
        dconf = [(f"materials/{rel}", "in_materials") for _src, rel in files
                 if (root / rel).is_file()]
        if dconf and not (options.force or options.yes) and not ask(dconf):
            result.warnings.append(pack.warn("deploy_skipped_conflicts"))
        else:
            deployed = deploy.install(root, files)

    say("完成", 1.0)
    return {"skipped": False, "out_dir": out_dir, "name": tex_name, "fingerprint": fp,
            "pngs": pngs, "vtfs": vtfs, "vmts": vmt_paths, "record": record,
            "deployed": deployed}
