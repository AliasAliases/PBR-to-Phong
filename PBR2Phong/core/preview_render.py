"""预览用的**简化 Blinn-Phong 渲染**（15-E）—— 纯 numpy，**不写盘、不碰 Qt、不调 VTFCmd**。

用户 2026-10-07 的问题（②+③）：右边的"产出成品"原来是 **512×512 缩略贴图** → 糊；笔刷素材
没有模型，看不到"铺在面上"的效果。→ 改成：拿**当前参数现算的那几张贴图**，在**球 / 平板**上
做一个简化 Blinn-Phong 着色，按控件尺寸现算（不再固定 512）。

⚠️ 这里是**近似**，不是引擎的 Phong、也不跑 lightmap —— 定位仍是"看个大概"，最终以
**HLMV / 游戏为准**（这条定位文案在界面上保留）。
⚠️ 光**固定不变**（不跟任何参数走）：预览只该反映材质本身，不该因为"换了个参数"看起来亮了一截。
"""

from __future__ import annotations

import numpy as np

from . import curves

# 主光方向（从左上前方来；正视 +Z）
LIGHT = (-0.45, 0.55, 0.70)
AMBIENT = 0.18          # 环境项：球背面不至于全黑
DIFFUSE = 0.85
SPEC_SCALE = 0.9
BACKGROUND = (0x2B, 0x33, 0x40)     # 球面之外的底色（跟预览框的深色同调）


def _rgb(img) -> np.ndarray | None:
    """贴图 → float32 的 HxWx3（0..1）。单通道铺成三通道；四通道丢掉 alpha。"""
    if img is None:
        return None
    arr = np.asarray(img)
    if arr.ndim == 2:
        arr = np.dstack([arr] * 3)
    if arr.shape[2] == 1:
        arr = np.dstack([arr[:, :, 0]] * 3)
    elif arr.shape[2] == 4:
        arr = arr[:, :, :3]
    return arr.astype("float32") / 255.0


def surface(size: int, shape: str = "sphere"):
    """几何：`(法线 HxWx3, 切线 HxWx3, 副切线 HxWx3, 有效像素掩码)`。

    球：解析球面（正交直看）；平板：正对镜头的平面（铺墙感）。
    """
    lin = (np.arange(size, dtype="float32") + 0.5) / size * 2.0 - 1.0
    x, y = np.meshgrid(lin, -lin)                      # y 向上
    if shape == "plane":
        n = np.zeros((size, size, 3), "float32")
        n[:, :, 2] = 1.0
        t = np.zeros_like(n)
        t[:, :, 0] = 1.0
        b = np.zeros_like(n)
        b[:, :, 1] = 1.0
        return n, t, b, np.ones((size, size), bool)
    r2 = x * x + y * y
    mask = r2 <= 1.0
    z = np.sqrt(np.clip(1.0 - r2, 0.0, 1.0))
    n = np.dstack([x, y, z])
    # 球面的切线基：T = normalize(ẑ × N)，B = N × T（球面参数化的那一套）
    up = np.zeros_like(n)
    up[:, :, 2] = 1.0
    t = np.cross(up, n)
    t /= np.maximum(1e-6, np.linalg.norm(t, axis=2, keepdims=True))
    b = np.cross(n, t)
    return n, t, b, mask


def render(images: dict, size: int = 256, shape: str = "sphere", kind: str = "basecolor",
           normal_map: bool = True) -> np.ndarray:
    """把现算好的贴图渲染成一张 `size×size` 的 RGB（uint8）。

    :param images: `{kind: 数组}` —— 直接给 `pack.PackResult.images()`（basecolor / normal / exp）
    :param size:   渲染边长（**按控件尺寸给** —— 不再固定 512）
    :param shape:  `"sphere"`（球）或 `"plane"`（平板 / 铺墙感）
    :param kind:   拿哪张贴图当**底色**看（底色 / 指数 / 法线 —— 界面上的"右框看"）
    :param normal_map: 要不要让法线贴图参与扰动（看"法线图本身"时关掉，免得看出双重凹凸）
    """
    size = max(8, int(size))
    albedo = _rgb(images.get(kind))
    if albedo is None:                                  # 这张图没有 → 说清楚（调用方去显示占位）
        return None
    if albedo.shape[0] != size or albedo.shape[1] != size:
        albedo = _resize(albedo, size)

    n, t, b, mask = surface(size, shape)

    # ---- 法线扰动（切线空间 → 世界）----
    if normal_map and kind != "normal":
        nm = _rgb(images.get("normal"))
        if nm is not None:
            if nm.shape[0] != size or nm.shape[1] != size:
                nm = _resize(nm, size)
            v = nm * 2.0 - 1.0
            v[:, :, 1] *= -1.0                          # 贴图 v 向下 → 世界 y 向上
            pert = (v[:, :, 0:1] * t + v[:, :, 1:2] * b + v[:, :, 2:3] * n)
            n = pert / np.maximum(1e-6, np.linalg.norm(pert, axis=2, keepdims=True))

    # ---- 高光指数 + 高光染色：都取自现算的指数贴图（R=指数、G=金属染色强度）----
    exp = images.get("exp")
    if exp is None:
        exponent = np.full((size, size), 8.0, "float32")
        tint = np.zeros((size, size), "float32")
    else:
        exp = np.asarray(exp)
        if exp.shape[0] != size or exp.shape[1] != size:
            exp = _resize_gray(exp, size)
        exponent = curves.roughness_to_exponent(
            curves.exponent_to_roughness(exp[:, :, 0])).astype("float32")
        tint = (exp[:, :, 1].astype("float32") / 255.0) if exp.shape[2] >= 3 else \
            np.zeros((size, size), "float32")

    # ---- 着色 ----
    light = np.asarray(LIGHT, "float32")
    light /= np.linalg.norm(light)
    view = np.array([0.0, 0.0, 1.0], "float32")
    half = light + view
    half /= np.linalg.norm(half)

    ndl = np.clip((n * light).sum(axis=2), 0.0, 1.0)
    ndh = np.clip((n * half).sum(axis=2), 0.0, 1.0)
    spec = np.power(ndh, exponent) * SPEC_SCALE
    # 金属把高光染成底色（指数贴图的 G 通道就是这个强度）；非金属高光是白的
    spec_color = (1.0 - tint[:, :, None]) * 1.0 + tint[:, :, None] * albedo
    color = albedo * (AMBIENT + DIFFUSE * ndl)[:, :, None] + spec[:, :, None] * spec_color

    out = np.clip(color, 0.0, 1.0) * 255.0
    out[~mask] = np.asarray(BACKGROUND, "float32")      # 球面之外 = 暗背景
    return out.astype(np.uint8)


def _resize(arr: np.ndarray, size: int) -> np.ndarray:
    """最近邻缩到 size×size（预览用，够快就行；缩放质量不参与判据）。"""
    h, w = arr.shape[:2]
    yi = (np.arange(size, dtype="float32") * h / size).astype(int).clip(0, h - 1)
    xi = (np.arange(size, dtype="float32") * w / size).astype(int).clip(0, w - 1)
    return arr[yi][:, xi]


def _resize_gray(arr: np.ndarray, size: int) -> np.ndarray:
    if arr.ndim == 2:
        arr = arr[:, :, None]
    return _resize(arr, size)
