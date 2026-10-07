"""打包层：一套素材 → 三张输出图（尺寸规则也在这一层落实）。

输出配方（实施计划 §5.2）：
    <名>_basecolor.png  RGBA8 sRGB   底色（方案 A 不压黑）+ alpha = 高光遮罩（武器路线）
    <名>_normal.png     RGBA8 linear 法线（绿通道已按 Source 约定翻转）+ alpha = 遮罩（角色路线）
    <名>_exp.png        RGB8  linear R = 指数、G = 染色强度(=金属度)、B = 空

尺寸规则（用户拍板，§5.3）：**每张输出图各自取自己的尺寸**；
只有当"小图必须合并进宿主图"时才插值——而且**只放大、绝不缩小**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import brush, curves, imaging, phong, source_io


@dataclass
class PackOptions:
    mask_carrier: str = "basecolor"     # basecolor（武器/硬表面）| normal（角色/软表面/笔刷）
    darken_metal: bool = False          # 压黑派退路；默认 False = 方案 A
    ao_amount: float = 0.5              # AO 压进底色的比例
    ao_in_mask: bool = True             # AO 是否也压进高光遮罩
    flip_normal_green: bool = True      # Blender(GL) → Source(DX)
    sharpness_gain: float = 1.0         # 「高光锐度」滑杆：指数整体缩放，1.0 = 不干预
    mask_kind: str = "phong"            # 遮罩公式：phong（模型路线）| brush（笔刷的 envmap 遮罩）
    use_mask: bool = True               # 要不要出遮罩（笔刷路线由调用方按「出不出反射遮罩」传）
    # ---- 2026-09-27 新增（施工单 `_task/07-S3+S4` 的 S4）----
    # ⚠️ 四个新字段的默认值都表示"**不干预**"，实现上也是"原样走老路"→ **默认值下产物逐位一致**
    #    （`tests/test_neutral_params.py` 拿改动前录下的产物哈希当锁）。
    roughness_offset: float = 0.0       # 「粗糙度整体偏移」：r' = clamp(r + off)
    roughness_points: tuple = ()        # 曲线编辑器的控制点（空 = 用原曲线）
    metal_tint: float = 1.0             # 「金属染色强度」：exp 的 G 通道整体缩放
    envmap_gain: float = 1.0            # 笔刷「反射强度」：envmap 遮罩整体增益
    # ---- 2026-09-27（09 单）：材质本身要透明（alpha 裁剪）----
    # 打开后：遮罩**强制走法线 alpha** + 没法线时**不许静默回退**（回退会把叶子抠出来的透明吃掉）。
    # 默认 False → 老路径一个字节不变。
    alpha_cutout: bool = False


@dataclass
class PackResult:
    basecolor: np.ndarray = None
    normal: np.ndarray = None
    exp: np.ndarray = None
    sizes: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    mask_carrier_used: str = ""     # **实际**把遮罩塞进了哪张图的 alpha（可能是回退后的结果）

    def images(self) -> dict:
        return {"basecolor": self.basecolor, "normal": self.normal, "exp": self.exp}


def _gray(path: Path, target: tuple | None = None) -> np.ndarray:
    """读一张灰度图（多通道就取平均），需要时**只放大**到 target 尺寸。**返回 uint8**。

    ⚠️ 这里踩过一个严重 bug：`.mean(axis=2)` 返回的是 **0~255 的 float**，
    而下游的约定是「uint8 = 0~255、float = 0~1」——于是整张粗糙度被 clip 成 1.0，
    指数贴图全算错（该是 7 的地方全变成 0）。**Blender/MB 烘出来的灰度图是 RGB 三通道，
    正好会走这条路**；当时合成测试素材用的是单通道 PNG，恰好绕开了它。
    → 取完平均必须**回到 uint8**。
    """
    arr = imaging.load(path)
    if arr.shape[2] >= 3:
        arr = np.rint(arr[:, :, :3].mean(axis=2)).astype(np.uint8)
    else:
        arr = arr[:, :, 0]
    if target and (arr.shape[1], arr.shape[0]) != tuple(target):
        arr = imaging.resample(arr, target[0], target[1])
    return arr


def _merge_size(a: tuple, b: tuple) -> tuple:
    """两张图要合并时的公共尺寸 = 各边取大（保证只放大、不缩小）。"""
    return max(a[0], b[0]), max(a[1], b[1])


def _num(value, default: float) -> float:
    """把可能缺失 / 为 None / 为空串的参数值取成 float。

    ⚠️ **别写成 `value or default`**：`0.0 or 1.0` 会变成 1.0 —— "把金属染色关掉"会被**静默**
    改成"不干预"（2026-09-27 自测当场抓到：染色拉到底，产物一点都不变）。
    """
    if value is None or value == "":
        return float(default)
    return float(value)


def _adjust_rough(rough, opt: "PackOptions"):
    """把 S4 的两个"粗糙度旋钮"（整体偏移 + 自定义曲线）作用在粗糙度灰度图上。

    ⚠️ 两者的默认值都是"**原样返回**"，所以不设它们时与改动前**逐位一致**。
    顺序 = 先整体偏移、再走自定义曲线（偏移是"整体亮一点/哑一点"，曲线是"映射形状"）。
    """
    return curves.apply_roughness_points(
        curves.apply_roughness_offset(rough, opt.roughness_offset), opt.roughness_points)


def options_from_values(values: dict, *, route: str = "model",
                        brush_mask: bool = True) -> "PackOptions":
    """从三层继承解析出来的 `values` 造一份 `PackOptions` —— **GUI 预览与真转换共用这一份**。

    2026-09-27 加：以前这段是内联写在 `pipeline.convert_set()` 里的，GUI 想"预览一下"就得**复制一份**；
    两条路一旦漂移，**预览就会骗人**（而且违反"转换逻辑只在 core 里实现一次"的项目铁律）。
    现在这里 = 唯一出处。
    """
    is_brush = (route or "model").strip().lower() == "brush"
    v = values or {}
    return PackOptions(
        # 笔刷：遮罩走**法线 alpha**（`$normalmapalphaenvmapmask`），没有法线时 pack 会回退到底色 alpha
        mask_carrier=("normal" if is_brush else v.get("mask_carrier", "basecolor")),
        darken_metal=(False if is_brush else bool(v.get("basecolor.darken_metal", False))),
        # ⚠️ 笔刷路线 **AO 不烘进底色**：笔刷贴图是**平铺**的，烘进 AO/大尺度明暗会跟着重复、
        #    大老远就看出规律（`Hammer笔刷路线.md` §3①）。笔刷的明暗 100% 来自 lightmap。
        ao_amount=(0.0 if is_brush else float(v.get("basecolor.ao_amount", 0.5))),
        flip_normal_green=bool(v.get("normal.flip_green", True)),
        sharpness_gain=float(v.get("curve.sharpness_gain", 1.0)),
        mask_kind=("brush" if is_brush else "phong"),
        # 模型路线：预设可以规定"这一档不出遮罩"（例：植被 —— 叶子不该反光，也没遮罩可盖 alpha）
        use_mask=(bool(brush_mask) if is_brush else bool(v.get("use_mask", True))),
        roughness_offset=_num(v.get("curve.roughness_offset"), 0.0),
        roughness_points=tuple(v.get("curve.curve_points") or ()),
        metal_tint=_num(v.get("curve.metal_tint"), 1.0),
        envmap_gain=_num(v.get("curve.envmap_gain"), 1.0),
        alpha_cutout=bool(v.get("alpha.cutout", False)),
    )


def warn(code: str, **args) -> dict:
    """构造一条体检警告 = **码 + 参数**（12 单）。

    ⚠️ **core 不产出给人看的字面量**：这里只给 `{"code": ..., "args": {...}}`，
    人话由 `i18n.warning()` 按当前语言渲染（中文文案在 `i18n.WARNING_TEXT` 里，逐字与改造前一致）。
    `args` 只放**原始值**（数字 / 名字 / 尺寸），不许拼句子。
    """
    return {"code": code, "args": args}


def build(matset: source_io.MaterialSet, options: PackOptions | None = None) -> PackResult:
    opt = options or PackOptions()
    res = PackResult()

    base_path = matset.get("shader.base_color")
    if base_path is None:
        raise ValueError(f"{matset.group}：没有底色贴图（Base Color），没法转换。")
    base = imaging.load(base_path)
    base_rgb = base[:, :, :3]
    base_size = (base.shape[1], base.shape[0])
    # 源底色自带透明吗？—— 09 单：它带透明、而遮罩又要塞进底色 alpha 时，透明会被吃掉（要提醒）
    src_alpha = base[:, :, 3] if base.shape[2] == 4 else None

    rough_path = matset.get("shader.roughness")
    metal_path = matset.get("shader.metallic")
    ao_path = matset.get("misc.ao", "standard.ao")
    normal_path = matset.normal

    if rough_path is None:
        res.warnings.append(warn("no_roughness_map"))
    if metal_path is None:
        res.warnings.append(warn("no_metallic_map"))
    if ao_path is None:
        res.warnings.append(warn("no_ao_map"))
    if normal_path is None:
        res.warnings.append(warn("no_normal_map"))

    # ---- 指数贴图：各自取原尺寸，取 roughness / metallic 里大的那个 ----
    exp_size = base_size
    for p, key in ((rough_path, "shader.roughness"), (metal_path, "shader.metallic")):
        if p is not None:
            size = matset.sizes.get(key) or _png_size(p)
            exp_size = (max(exp_size[0], size[0]), max(exp_size[1], size[1]))
    # ⚠️ 13-A：源图先各自留一份（体检要用**没叠加用户旋钮**的版本），再走既有链路
    rough_src = _gray(rough_path, exp_size) if rough_path else None
    metal_src = _gray(metal_path, exp_size) if metal_path else None
    rough = _adjust_rough(rough_src, opt) if rough_src is not None \
        else np.full(exp_size[::-1], 255, np.uint8)
    metal = metal_src if metal_src is not None else np.zeros(exp_size[::-1], np.uint8)
    # ---- 13-A：体检两条「这张贴图其实没有信息量」（用户真给过这类素材） ----
    #     ⚠️ 判据一律看**源图**（`*_src`），不看叠加了用户旋钮之后的数组 —— 否则用户自己拖一下
    #     「粗糙度整体偏移」就会凭空多出一条警告。也**不动**既有那几条"没贴图"的判定。
    if rough_src is not None:
        uniq = np.unique(rough_src)
        if uniq.size == 1:
            res.warnings.append(warn("roughness_is_constant"))
        elif uniq.size == 2:
            res.warnings.append(warn("roughness_has_two_values"))
    if metal_src is not None:
        uniq = np.unique(metal_src)
        if uniq.size == 1 and int(uniq[0]) == 0:
            res.warnings.append(warn("metallic_all_zero"))
        elif uniq.size == 1 and int(uniq[0]) == 255:
            res.warnings.append(warn("metallic_all_one"))
    # 「金属染色强度」= exp 贴图 **G 通道**（高光染色强度）整体缩放；1.0 时原样返回
    metal = curves.scale_metal_tint(metal, opt.metal_tint)
    res.exp = phong.exponent_map(rough, metal, opt.sharpness_gain)

    # ---- 遮罩：在底色尺寸上算（粗糙度需要放大就放大） ----
    rough_for_mask = _adjust_rough(_gray(rough_path, base_size), opt) if rough_path \
        else np.full(base_size[::-1], 255, np.uint8)
    ao_for_base = _gray(ao_path, base_size) if ao_path else None
    mask = None
    if opt.use_mask:
        if opt.mask_kind == "brush":
            # 笔刷路线：envmap 遮罩（VDC 那条 brush 曲线 + 金属兜底），不吃 AO
            metal_for_mask = _gray(metal_path, base_size) if metal_path else None
            mask = brush.envmap_mask(rough_for_mask, metal_for_mask, gain=opt.envmap_gain)
        else:
            mask = phong.mask_map(rough_for_mask, ao_for_base if opt.ao_in_mask else None)

    # ---- 底色 ----
    albedo = phong.composite_basecolor(base_rgb, ao_for_base, opt.ao_amount)
    if opt.darken_metal:
        rough_small = _adjust_rough(_gray(rough_path, base_size), opt) if rough_path \
            else np.full(base_size[::-1], 255, np.uint8)
        metal_small = curves.scale_metal_tint(
            _gray(metal_path, base_size) if metal_path else np.zeros(base_size[::-1], np.uint8),
            opt.metal_tint)
        albedo = phong.darken_basecolor(albedo, rough_small, metal_small)
        res.warnings.append(warn("darken_metal_route"))

    base_out = np.dstack([albedo, base[:, :, 3] if base.shape[2] == 4 else np.full(base_size[::-1], 255, np.uint8)])

    # ---- 法线 ----
    normal_out = None
    if normal_path is not None:
        nrm = imaging.load(normal_path)[:, :, :3]
        # ⚠️ 真实素材上撞到过：法线图整张 R=G=128（“平的”），用户以为有凹凸其实一点没有。
        #    这种图翻不翻 G、挂不挂 $bumpmap 都一样，得明说，否则他会以为是我们压平了。
        dev = int(np.abs(nrm[:, :, :2].astype(np.int16) - 128).max())
        if dev < 3:
            res.warnings.append(warn("normal_is_flat"))
        if opt.flip_normal_green:
            nrm = phong.flip_normal_green(nrm)
        normal_out = np.dstack([nrm, np.full(nrm.shape[:2], 255, np.uint8)])

    # ---- 遮罩塞进哪张图的 alpha ----
    # 09 单：**要透明的材质强制走法线 alpha** —— 底色 alpha 得留给"哪块是叶子"
    carrier = "normal" if opt.alpha_cutout else opt.mask_carrier
    if mask is None:
        res.mask_carrier_used = ""            # 这次不出遮罩（调用方显式关掉了）
    elif carrier == "basecolor":
        base_out = _put_alpha(base_out, mask, res)
        res.mask_carrier_used = "basecolor"
    else:
        if normal_out is None:
            if opt.alpha_cutout:
                # ⚠️ **绝不静默回退**：回退 = 把底色 alpha 换成遮罩 → 叶子抠出来的透明整个丢掉
                res.warnings.append(warn("cutout_needs_normal"))
                res.mask_carrier_used = ""
            else:
                res.warnings.append(warn("mask_carrier_normal_missing"))
                base_out = _put_alpha(base_out, mask, res)
                res.mask_carrier_used = "basecolor"
        else:
            normal_out = _put_alpha(normal_out, mask, res)
            res.mask_carrier_used = "normal"

    # ---- 体检（不静默）：底色带透明，遮罩却要盖到底色 alpha 上 ----
    if src_alpha is not None and res.mask_carrier_used == "basecolor" \
            and int((src_alpha != 255).sum()) > 0:
        res.warnings.append(warn("basecolor_alpha_overridden"))

    # ---- 体检（不静默）：勾了"要透明"，但这套素材压根没有可裁的地方 ----
    # 10 片 §2.4：静默 = 用户以为开了就有效，回头会当成工具坏了。
    if opt.alpha_cutout and (src_alpha is None or not bool((src_alpha < 255).any())):
        res.warnings.append(warn("no_alpha_but_cutout"))

    res.basecolor, res.normal = base_out, normal_out
    res.sizes = {
        "basecolor": (base_out.shape[1], base_out.shape[0]),
        "normal": (normal_out.shape[1], normal_out.shape[0]) if normal_out is not None else None,
        "exp": (res.exp.shape[1], res.exp.shape[0]),
    }
    return res


def _put_alpha(img: np.ndarray, mask: np.ndarray, res: PackResult) -> np.ndarray:
    """把遮罩写进 alpha；尺寸不一致时按「只放大、不缩小」对齐。"""
    if mask.shape != img.shape[:2]:
        w, h = _merge_size((mask.shape[1], mask.shape[0]), (img.shape[1], img.shape[0]))
        if (img.shape[1], img.shape[0]) != (w, h):
            img = imaging.resample(img, w, h)
        if (mask.shape[1], mask.shape[0]) != (w, h):
            mask = imaging.resample(mask, w, h)
        res.warnings.append(warn("mask_size_mismatch", w=w, h=h))
    out = np.array(img, dtype=np.uint8, copy=True)
    out[:, :, 3] = mask
    return out


def write_outputs(res: PackResult, out_dir: str | Path, name: str,
                  kinds=("basecolor", "normal", "exp")) -> dict:
    """把选中的几张输出图写盘。`kinds` 默认三张全写（模型路线）；
    笔刷路线只要 `("basecolor", "normal")` —— 笔刷用不上指数贴图。"""
    out_dir = Path(out_dir)
    written = {}
    if "basecolor" in kinds:
        written["basecolor"] = imaging.save(res.basecolor, out_dir / f"{name}_basecolor.png")
    if "normal" in kinds and res.normal is not None:
        written["normal"] = imaging.save(res.normal, out_dir / f"{name}_normal.png")
    if "exp" in kinds:
        written["exp"] = imaging.save(res.exp, out_dir / f"{name}_exp.png")
    return written


def _png_size(path) -> tuple:
    from PIL import Image
    with Image.open(path) as im:
        return im.size
