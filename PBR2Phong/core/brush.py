"""笔刷路线（`LightmappedGeneric`）的数学与 VMT 参数 —— 与模型路线是**两套**。

    模型（VertexLitGeneric）：roughness → exponent（指数贴图 R 通道）+ Phong mask
    笔刷（LightmappedGeneric）：**L4D2 不支持 Phong** → roughness → **envmap 遮罩**

为什么单独一个模块：`core/phong.py` 是模型路线的数学，这里是笔刷路线的数学；
两条路线的 VMT 模板、参数语义完全不同（施工单见 `_task/01-笔刷模式.md`，背景见 `Hammer笔刷路线.md` §2）。
**共享的部分**（认素材、解图、尺寸、色彩空间、PNG→VTF→部署）照旧走 `pack` / `vtf` / `deploy`。

遮罩载体（两条都在 L4D2 官方内容里见过）：
    · 有法线图 → 塞进**法线图的 alpha**，VMT 写 `$normalmapalphaenvmapmask 1`
    · 没有法线 → 塞进**底色图的 alpha**，VMT 写 `$basealphaenvmapmask 1`
⚠️ **不能**用独立的 `$envmapmask`：它和 `$bumpmap` 在 L4D2 上不能同用
   （VDC 原文：只有 CS:GO 分支的 LightmappedGeneric 才行）。

遮罩曲线 = VDC《Adapting PBR Textures to Source》里给 brush 的那条：
    specular = curve(1 - roughness, 108→0, 208→112)      ← 阈值在 sRGB 0..255 域
→ 令 x = 1-r；x ≤ 108/255 → 0；x ≥ 208/255 → 112/255；中间线性。
⚠️ 归零点 **roughness ≈ 1 − 108/255 = 0.5765**（不是那页里写的"64%"，那句我算过、不符）。

⚠️ **遮罩默认是出的**（`_task/01-笔刷模式.md` §2：用户拍板的 v1 范围含 envmap 遮罩）
—— 要"只出底色+法线"就显式关掉（`ConvertOptions.brush_mask=False`，CLI `--no-brush-mask`，界面取消勾选）。
`Hammer笔刷路线.md` §2 末那条"L4D2 多数世界材质压根没高光"是文档里的观察，**不靠改默认值来表达**。
"""

from __future__ import annotations

import numpy as np

from . import vmt as vmt_mod

# 官方 brush 曲线的三个锚点（都已归一化到 0..1）
MASK_X_LO = 108.0 / 255.0     # (1-r) 低于它 → 完全不反光
MASK_X_HI = 208.0 / 255.0     # (1-r) 高于它 → 顶到 MASK_TOP
MASK_TOP = 112.0 / 255.0      # 最光滑处也只有 ≈0.44（官方曲线的上限）
ROUGHNESS_ZERO = 1.0 - MASK_X_LO     # ≈0.5765：粗糙度高于它就不再反光

SHADER = "LightmappedGeneric"

# 笔刷上**写了就出错**的键（`_task/01-笔刷模式.md` §4）：
#   · `$phong*` 家族 —— LightmappedGeneric 的 `$phong` 徽标是 "since CS:GO"（`$phong.html` 只认 CS:GO/Strata/Mapbase）
#   · 独立遮罩图 `$envmapmask` —— 与 `$bumpmap` 在 L4D2 不能同用
#   · `$envmaplightscale` —— 扫过 L4D2 全部 57 个 DLL，这个字符串不存在
#   · `$envmap*` 家族也不许从模型预设继承（那是给 VertexLitGeneric 调的 → 墙面会无条件全反射）
MODEL_ONLY_KEYS = {
    "$phong", "$phongboost", "$phongexponent", "$phongexponenttexture", "$phongfresnelranges",
    "$phongtint", "$phongalbedotint", "$phongwarptexture", "$phongdisablehalflambert",
    "$phongmaskcontrastbrightness", "$basemapalphaphongmask", "$basemapluminancephongmask",
    "$invertphongmask", "$halflambert", "$model", "$envmapfresnel",
    "$envmapmask", "$envmaplightscale",
}

# 从 `extra`（预设/用户继承来的参数）里必须整个丢掉的前缀
DROP_PREFIXES = ("$envmap",)


def params(prefix: str, *, has_normal: bool = True, mask_carrier: str = "",
           use_mask: bool = True, extra=()) -> list:
    """组装笔刷 VMT 的参数表。

    prefix          VMT 里的贴图前缀（`<cdmaterials>/<名字>`）
    has_normal      有没有法线图（没有就不写 `$bumpmap`）
    mask_carrier    遮罩实际落在哪张图的 alpha：`"normal"` / `"basecolor"`（空 = 没遮罩）
    use_mask        要不要出遮罩（**默认出**；调用方可显式关掉）
    extra           从预设/用户那里继承来的参数 —— 禁令键与整个 `$envmap*` 家族都会被丢掉
    """
    out = [("$basetexture", f"{prefix}_basecolor")]
    if has_normal:
        out.append(("$bumpmap", f"{prefix}_normal"))
    if use_mask:
        out.append(("$envmap", "env_cubemap"))          # 只在出遮罩时才写
        # 规格（施工单 §3）：载体默认是**法线 alpha**；只有"没法线"或显式要求底色时才退到底色 alpha
        if not has_normal or (mask_carrier or "").lower() == "basecolor":
            out.append(("$basealphaenvmapmask", 1))
        else:
            out.append(("$normalmapalphaenvmapmask", 1))
    for key, value in (extra or ()):
        low = key.lower()
        if low in MODEL_ONLY_KEYS or any(low.startswith(p) for p in DROP_PREFIXES):
            continue
        out.append((key, value))
    return out


def render(prefix: str, **kw) -> str:
    """直接出笔刷 VMT 文本（模板固定 `LightmappedGeneric`）。"""
    return vmt_mod.render(SHADER, params(prefix, **kw))


def forbidden_keys_in(text: str) -> list:
    """扫一段 VMT 文本，返回里面出现的**禁令键**（空列表 = 干净）。

    给测试与交付自检用：别让 `$phong*` / `$envmapmask` 之类偷偷溜进笔刷材质。
    注意 `$envmap`（我们主动写的那个）与 `$normalmapalphaenvmapmask` /
    `$basealphaenvmapmask` 不算违规，其它 `$envmap*` 都算。
    """
    allowed = {"$envmap", "$normalmapalphaenvmapmask", "$basealphaenvmapmask"}
    keys = vmt_mod.parse(text)
    return sorted(k for k in keys
                  if k in MODEL_ONLY_KEYS or (k.startswith("$envmap") and k not in allowed))


# ------------------------------------------------------------------ 曲线 / 遮罩

def vdc_brush_curve(rough01: np.ndarray) -> np.ndarray:
    """VDC 那条 brush specular 曲线：roughness(0..1) → 遮罩(0..MASK_TOP)。"""
    x = 1.0 - np.clip(np.asarray(rough01, dtype=np.float32), 0.0, 1.0)
    t = (x - MASK_X_LO) / (MASK_X_HI - MASK_X_LO)
    return np.clip(t, 0.0, 1.0) * MASK_TOP


def envmap_mask(rough: np.ndarray, metal: np.ndarray | None = None, *,
                metal_floor: float = 1.0, gain: float = 1.0) -> np.ndarray:
    """roughness（+ 可选 metallic）→ envmap 遮罩 **uint8**（0..255）。

    输入按项目约定收 **uint8 0..255**（`pack._gray()` 的出品）；传 float 直接报错，
    绝不让它在后面的 clip 里悄悄消失（项目铁律：uint8 = 0..255、float = 0..1）。
    语义：**白 = 完全反光，黑 = 完全哑光**。
    金属单独兜底：`mask = max(曲线, metallic × metal_floor)`，默认 floor = 1.0（金属永远反光）
    —— 那条 brush 曲线是给**非金属**调的。
    """
    r = np.asarray(rough)
    if r.dtype != np.uint8:
        raise ValueError(f"笔刷遮罩只收 uint8(0..255) 的粗糙度，收到 {r.dtype}")
    m = vdc_brush_curve(r.astype(np.float32) / 255.0)
    if metal is not None:
        mm = np.asarray(metal)
        if mm.dtype != np.uint8:
            raise ValueError(f"笔刷遮罩只收 uint8(0..255) 的金属度，收到 {mm.dtype}")
        m = np.maximum(m, np.clip(mm.astype(np.float32) / 255.0, 0.0, 1.0) * float(metal_floor))
    m = np.clip(m * float(gain), 0.0, 1.0)
    return np.rint(m * 255.0).astype(np.uint8)
