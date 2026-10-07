"""Phong 合成的逐像素数学：把 PBR 的四张图，算成 Source 要的三张图。

固定事实（全部来自实测/官方实物，见实施计划 §0.6 与 §9.5）：
  · `$phongexponenttexture` 的 **R = 指数**、**G = albedo 染色强度**（仅 `$phongalbedotint 1`）、
    **B = 空**。
  · Phong 遮罩**白 = 满高光、黑 = 没高光**（官方 `v_shotgun_a.vtf` 的 alpha 就是金属件遮罩）
    → 不需要 `$invertphongmask`。
  · 金属策略默认走 **方案 A「不压黑」**：保留 albedo，靠 G 通道让高光跟随底色。
    `darken_basecolor()` 是给"万一 albedotint 不生效"的压黑派退路，默认不启用。
"""

from __future__ import annotations

import numpy as np

from . import curves


def exponent_map(roughness: np.ndarray, metallic: np.ndarray, gain: float = 1.0) -> np.ndarray:
    """→ (H, W, 3) uint8：R=指数、G=染色强度、B=0。`gain` = 界面上的「高光锐度」。"""
    r = _as01(roughness)
    m = _as01(metallic)
    out = np.zeros(r.shape + (3,), np.uint8)
    out[:, :, 0] = curves.exponent_channel(r, gain)
    out[:, :, 1] = np.clip(np.rint(m * 255.0), 0, 255).astype(np.uint8)
    return out


def mask_map(roughness: np.ndarray, ao: np.ndarray | None = None) -> np.ndarray:
    """→ (H, W) uint8 的高光遮罩（255 = 满高光）。AO 给了就乘进去。"""
    mask = curves.phong_mask(roughness)
    if ao is not None:
        mask = mask * _as01(ao)
    return np.clip(np.rint(mask * 255.0), 0, 255).astype(np.uint8)


def composite_basecolor(albedo: np.ndarray, ao: np.ndarray | None = None,
                        ao_amount: float = 0.5) -> np.ndarray:
    """底色：可选把 AO 按比例压进去（默认 50%，见 §9.2）。方案 A 不动颜色。"""
    rgb = np.asarray(albedo, dtype=np.float32)[:, :, :3]
    if ao is not None and ao_amount > 0:
        rgb = rgb * (1.0 - ao_amount + ao_amount * _as01(ao)[:, :, None])
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def darken_basecolor(albedo: np.ndarray, roughness: np.ndarray, metallic: np.ndarray) -> np.ndarray:
    """【压黑派退路，默认不用】albedo × (1 − (1−r)×m)。

    PBR-2-Source 的做法。只有在实测证明 `$phongalbedotint` 不生效时才切到这里，
    代价是金属高光会变成灰白（Source 没有逐像素高光颜色通道）。
    """
    r = _as01(roughness)[:, :, None]
    m = _as01(metallic)[:, :, None]
    factor = 1.0 - (1.0 - r) * m
    return np.clip(np.rint(np.asarray(albedo, np.float32)[:, :, :3] * factor), 0, 255).astype(np.uint8)


def flip_normal_green(normal_rgb: np.ndarray) -> np.ndarray:
    """法线绿通道取反：Blender（OpenGL 约定）→ Source（DirectX 约定）。

    依据：VDC `Bump_map.html`/`Normal_map.html`——两套规则的绿通道相反，Source 取 DirectX；
    Blender 烘焙是 OpenGL。旁证：PBR-2-Source 源码 `if normalType == GL: g.invert()`。
    """
    out = np.array(normal_rgb, dtype=np.uint8, copy=True)
    out[:, :, 1] = 255 - out[:, :, 1]
    return out


def _as01(arr) -> np.ndarray:
    """uint8 / float 都接受，统一成 0..1 float32。

    约定：uint8 → /255；float → 必须是 0..1（>1 直接报错，避免被静默 clip 成 1）。
    """
    a = np.asarray(arr)
    if a.dtype == np.uint8:
        return a.astype(np.float32) / 255.0
    f = a.astype(np.float32)
    if f.size and float(np.nanmax(f)) > 1.001:
        raise ValueError(
            "传进来的浮点值看起来是 0~255 而不是 0~1（约定：uint8=0~255、float=0~1）。"
            "请先 /255 —— 否则会被 clip 成 1 而完全不报错。")
    return np.clip(f, 0.0, 1.0)


# ---------------------------------------------------------------- 21 档预设（全部来自官方 VMT 实据）
#
# 2026-09-27（施工单 `_task/08-S5+S6-预设与术语表.md` §2.1）从 5 档扩到 **21 档**
# = **模型 11 + 笔刷 9 + 贴花 1**。数值是**一类扫 L4D2 自己 5 个 VPK（8465 个 .vmt）统计出来的
# 最常见取值**，照抄，别凭记忆改。明确不做：skybox / particle / vgui（用户拍板不要）。
#
# 每个档的字段：
#   route      = "model"（VertexLitGeneric+Phong）| "brush"（LightmappedGeneric）
#   kind       = "model" | "brush" | "decal"（只用于分类与核对"21 档"的构成）
#   shader     = 可选：这个档要用别的着色器（缺省 = 按 route 走 VLG / LMG）
#   brush_mask = 可选：切到这一档时，界面上的「给笔刷出反射遮罩」该不该勾
PRESETS = {
    # ============================ 模型路线（11 档）============================
    "角色-身体": {
        "route": "model", "kind": "model",
        "desc": "幸存者身体：高光很弱很宽（boost 1.4 / 指数 5），遮罩走法线 alpha",
        "mask_carrier": "normal",
        "use_exponent_texture": False,
        "vmt": {"$phong": 1, "$phongboost": 1.4, "$phongexponent": 5,
                "$phongtint": "[.85 .85 1]", "$phongfresnelranges": "[.3 .65 30]",
                "$halflambert": 0},
    },
    "角色-头": {
        "route": "model", "kind": "model",
        "desc": "幸存者头部：官方用 _exp 贴图 + 很宽的 fresnel（指数 5~12）",
        "mask_carrier": "normal",
        "use_exponent_texture": True,
        "vmt": {"$phong": 1, "$phongboost": 1.4, "$phongtint": "[.85 .85 1]",
                "$phongfresnelranges": "[.2 .5 5]", "$halflambert": 0},
    },
    "角色-眼睛": {
        "route": "model", "kind": "model",
        # ⚠️ 官方 8 个眼睛材质用的是 **EyeRefract 着色器**，不是 VLG → 单独一条支路，
        #    绝不能塞进 Phong 模板（那会把 Phong 参数写进一个不认识的着色器里）。
        #    13-E 起这条支路**按官方键集整套写**（`core/vmt.py::render_eyerefract`）：
        #    要一张虹膜图（`$Iris`，必填）+ 可选眼睛 AO（`$AmbientOcclTexture`）。
        "shader": "EyeRefract",
        "desc": "角色眼睛：官方 EyeRefract；要一张虹膜图（必填），可选眼睛 AO（贴图要自己给）",
        "mask_carrier": "basecolor",
        "use_exponent_texture": False,
        # ⚠️ 官方 8 份眼睛 VMT 里**没有** `$surfaceprop`（也没有 `$basetexture`）→ 这一档不写它，
        #    免得"表面类型必填"把 `$surfaceprop` 带进一个官方没有它的材质里（判据：键集与官方一致）。
        "vmt": {},
    },
    "武器-第一人称": {
        "route": "model", "kind": "model",
        "desc": "第一人称武器：绝大多数数据（v_models 40 里 phong 37），全套用 $phongalbedotint",
        "mask_carrier": "basecolor",
        "use_exponent_texture": True,
        "vmt": {"$phong": 1, "$phongboost": 1, "$phongfresnelranges": "[5 5 15]",
                "$phongalbedotint": 1, "$basemapalphaphongmask": 1,
                "$envmap": "env_cubemap", "$envmapfresnel": 1,
                "$envmapFresnelMinMaxExp": "[.4 1 .4]", "$halflambert": 0},
    },
    "武器-世界掉落": {
        "route": "model", "kind": "model",
        "desc": "地上捡的武器：指数贴到 1（几乎全哑）、fresnel 很窄",
        "mask_carrier": "basecolor",
        "use_exponent_texture": True,
        "vmt": {"$phong": 1, "$phongboost": 1, "$phongfresnelranges": "[.1 .4 2]",
                "$basemapalphaphongmask": 1},
    },
    "感染者": {
        "route": "model", "kind": "model",
        # ⚠️ L4D2 最大一类（579 个），但**只有 28 个真开了 $phong** → 这一档要"高光很弱"才像官方。
        "desc": "感染者（L4D2 最大一类）：官方绝大多数没开 $phong，所以高光故意做得很弱",
        "mask_carrier": "normal",
        "use_exponent_texture": True,
        "vmt": {"$phong": 1, "$phongboost": 2, "$phongfresnelranges": "[1 1 1]"},
    },
    "道具": {
        "route": "model", "kind": "model",
        "desc": "静态道具：官方 boost 1~2 / 指数 10，且约半数带 envmap（所以这档留 $envmap）",
        "mask_carrier": "basecolor",
        "use_exponent_texture": True,
        # ⚠️ 别照抄别人的特例参数：曾把 CS:S 冷却塔的 `$basemapluminancephongmask` + `$phongboost 0.1`
        #    当"道具档"抄进来 → 引擎改用底色**亮度**当遮罩，把我们算好的 alpha 遮罩整个作废。
        "vmt": {"$phong": 1, "$phongboost": 1.5, "$phongfresnelranges": "[.3 .6 4]",
                "$basemapalphaphongmask": 1, "$phongalbedotint": 1,
                "$envmap": "env_cubemap"},
    },
    "载具": {
        "route": "model", "kind": "model",
        # 官方 props_vehicles 用**标量** $phongexponent 500 —— 超过我们指数贴图能表达的 1..150，
        # 所以这一档**必须走标量**（use_exponent_texture=False），别硬塞进贴图。
        "desc": "载具：官方用标量指数 500（超出指数贴图量程，所以这档走标量）",
        "mask_carrier": "basecolor",
        "use_exponent_texture": False,
        "vmt": {"$phong": 1, "$phongboost": 1, "$phongexponent": 500,
                "$phongfresnelranges": "[.3 .6 4]"},
    },
    "植被": {
        "route": "model", "kind": "model",
        # 官方 48 个植被材质里 **0 个**开 $phong → 叶子不该反光，这一档干脆不出高光。
        # ⚠️ 09 单：叶子这类材质**靠 alpha 抠形状** → 这一档默认"要透明"，
        #    而且**不出遮罩**（没遮罩可覆盖 alpha，天然不会把叶子抠出来的形状吃掉）。
        "use_mask": False,
        "alpha_cutout": True,
        "desc": "植被：官方 48 个里 0 个开 $phong —— 叶子不该反光，所以这一档不出高光；默认按透明裁剪处理",
        "mask_carrier": "basecolor",
        "use_exponent_texture": False,
        "vmt": {},
    },
    "招牌·发光": {
        "route": "model", "kind": "model",
        # 官方 props_signs：boost 2 / 指数 10（或 64），需要自发光档。
        "desc": "招牌 / 发光牌：官方 boost 2、指数 10，需要 $selfillum 自发光档",
        "mask_carrier": "basecolor",
        "use_exponent_texture": True,
        "vmt": {"$phong": 1, "$phongboost": 2, "$phongfresnelranges": "[.5 1 2]",
                "$selfillum": 1},
    },
    "投掷物·玻璃": {
        "route": "model", "kind": "model",
        "desc": "瓶罐玻璃：靠 envmap 反光，指数极大（官方武器 VMT 那套 $envmap + $envmaptint）",
        "mask_carrier": "basecolor",
        "use_exponent_texture": False,
        "vmt": {"$phong": 1, "$phongboost": 5, "$phongexponent": 200,
                "$phongfresnelranges": "[1 .5 8]", "$envmap": "env_cubemap",
                "$envmaptint": "[.1 .1 .1]", "$basemapalphaphongmask": 1},
    },

    # ============================ 笔刷路线（9 档）============================
    # 笔刷 = LightmappedGeneric，**没有 Phong**（L4D2 不支持）→ 只出底色 + 法线 + 可选反射遮罩，
    # 明暗交给 lightmap。所以这 9 档唯一要定的是 **$surfaceprop**（世界材质几乎 100% 都写它）。
    "混凝土·沥青": {
        "route": "brush", "kind": "brush",
        "desc": "混凝土 / 沥青（官方 98 个里 96 个写了 surfaceprop，concrete×89）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "concrete"},
    },
    "金属": {
        "route": "brush", "kind": "brush",
        "desc": "金属（官方 89 个里 88 个写了，metal×38 / 通风管 metalvent×43）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "metal"},
    },
    "木": {
        "route": "brush", "kind": "brush",
        "desc": "木（官方 94 个里 91 个写了，wood×78 / 板材 wood_plank×7）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "wood"},
    },
    "砖": {
        "route": "brush", "kind": "brush",
        "desc": "砖（官方 31 个**全部**写了 $surfaceprop）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "brick"},
    },
    "石膏墙": {
        "route": "brush", "kind": "brush",
        "desc": "石膏墙 / 干墙（官方 81 个里 79 个写了，sheetrock×37 / plaster×33）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "plaster"},
    },
    "瓷砖": {
        "route": "brush", "kind": "brush",
        "desc": "瓷砖（官方 30 个里 28 个写了，且 15 个带 envmap）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "tile"},
    },
    "玻璃·窗户": {
        "route": "brush", "kind": "brush",
        "desc": "玻璃 / 窗户：官方 16 个里 14 个写 surfaceprop、**15 个开 envmap** → 默认勾反射遮罩",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "brush_mask": True,
        "vmt": {"$surfaceprop": "glass"},
    },
    "自然土地": {
        "route": "brush", "kind": "brush",
        "desc": "自然土地（官方 62 个里 52 个写了，dirt×33 / grass×5 / mud×1）",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "dirt"},
    },
    "建筑·装饰条": {
        "route": "brush", "kind": "brush",
        # 官方**没有**专属值（45 个里 36 个写了，混着 carpet/plaster/rubber/brick）→ 默认 plaster，让用户改。
        "desc": "建筑装饰条：官方没有专属 surfaceprop（混着 carpet/plaster/rubber/brick）→ 默认 plaster，按需改",
        "mask_carrier": "normal", "use_exponent_texture": False,
        "vmt": {"$surfaceprop": "plaster"},
    },

    # ============================ 贴花（1 档）============================
    "贴花": {
        "route": "brush", "kind": "decal",
        # ⚠️ 官方 decals 的主力**不是** DecalModulate（41/328），而是
        #    **LightmappedGeneric + $decal 1**（157/328）→ 所以它走笔刷路线。
        #    无高光、无 envmap（0/328）；$surfaceprop 基本不写（12/328）。
        #    ⚠️ 贴花要透明：底色**必须保留 alpha**（配 $translucent 1）—— 别在这一档把 alpha 砍掉。
        "desc": "贴花：LightmappedGeneric + $decal 1（官方 157/328 是这个写法，不是 DecalModulate）",
        "mask_carrier": "basecolor", "use_exponent_texture": False,
        "brush_mask": False,          # 贴花不反光
        "vmt": {"$decal": 1, "$translucent": 1, "$decalscale": "0.250000",
                "$vertexcolor": 1, "$vertexalpha": 1},
    },
}

DEFAULT_PRESET = "角色-身体"


def presets_for_route(route: str) -> list:
    """这个路线能用哪些预设（模型 11 / 笔刷 9 + 贴花 1）。

    ⚠️ 预设必须**按路线过滤**：笔刷档的参数是 LMG 的（没有 $phong），
    模型档的参数是 VLG 的（没有 $surfaceprop 之外的 LMG 项）—— 混在一起会产出四不像的 VMT。
    """
    r = "brush" if str(route).strip().lower() == "brush" else "model"
    return [name for name, p in PRESETS.items() if p.get("route", "model") == r]


def preset_kinds() -> dict:
    """按 kind 数一遍（给"21 档"这个承诺当守门人用：模型 11 / 笔刷 9 / 贴花 1）。"""
    out = {"model": 0, "brush": 0, "decal": 0}
    for p in PRESETS.values():
        out[p.get("kind", "model")] = out.get(p.get("kind", "model"), 0) + 1
    return out
