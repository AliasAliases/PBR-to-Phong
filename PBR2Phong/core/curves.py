"""换算曲线：这是 **GUI 唯一依赖的数学契约**（GUI 只把 LUT 交给 core，绝不自己算）。

集中放三件事，别散到别处：
  1. `roughness → exponent 通道值`（0..255）
  2. `roughness → Phong 遮罩`（0..1）
  3. 控制点 ↔ 256 级 LUT（将来 GUI 曲线编辑器用的通用件）

⭐ exponent 映射的依据（2026-09-25 实测，见实施计划 §0.6）：
  · L4D2 **没有 `$phongexponentfactor`**（57 个 DLL 里查无此参）→ 不能照抄 PBR-2-Source 的
    "通道 = r⁻²×(0.8/32) + VMT 里写 factor 32"。
  · exponent 贴图的 R 通道由引擎映射成 **1..150**（VDC：min→1、max→150）。
  · 离线证据支持是**线性**的：官方头部标量 `$phongexponent` 取 7/10/12，而
    `coach_head_exp.vtf` 的 R 中位 13 → 线性给 E≈8.6（吻合）；指数映射只给 E≈1.3（差太远）。
  · 硬限制：`r < 0.073` 时 0.8/r² 超过 150，全部顶格 → UI 必须说人话。
"""

from __future__ import annotations

import numpy as np

EXP_MIN = 1.0
EXP_MAX = 150.0
# 有效指数 ≈ 0.8 / roughness²（沿用 PBR-2-Source 的公式形状，去掉它那个 factor 32）
EXP_NUMERATOR = 0.8

# Phong 遮罩默认曲线：(1−r)³ × 1.1（PBR-2-Source 的做法，见实施计划 §9.2）
MASK_GAIN = 1.1


def _to01(values) -> np.ndarray:
    """统一入口：uint8（0..255）会当 0..1 用；float 一律按 0..1 处理。

    ⚠️ 这个函数是踩过坑加的：以前 `phong_mask()` 直接 clip 到 0..1，
    而调用方传的是 uint8 的 0..255 —— 于是整张遮罩都变成 0，
    **而端点断言（r=0 和 r=1）居然还是通过的**，只有采样中段才看得出来。

    ⚠️⚠️ 又踩了一次：调用方传 **0~255 的 float**（`.mean()` 的产物）时，
    它会被整片 clip 成 1.0 而**不报错**。所以现在遇到 >1 的 float 直接**报错**，
    逼调用方明确 /255 —— 这类"静默算错"比崩掉难查得多。
    """
    a = np.asarray(values)
    if a.dtype == np.uint8:
        return a.astype(np.float32) / 255.0
    f = a.astype(np.float32)
    if f.size and float(np.nanmax(f)) > 1.001:
        raise ValueError(
            "传进来的浮点值看起来是 0~255 而不是 0~1（本函数约定 uint8=0~255、float=0~1）。"
            "请先 /255，别让它在 clip 里被静默压成 1。")
    return np.clip(f, 0.0, 1.0)


def roughness_to_exponent(roughness, gain: float = 1.0):
    """粗糙度 → 有效指数（数值域 1..150）。

    `gain` 就是界面上那根「**高光锐度**」滑杆：>1 让指数变大（高光更小更锐），
    <1 让指数变小（高光更大更柔）。**默认 1.0 = 不干预**，
    所以滑杆不动时结果与之前完全一致（已经验证过的行为不受影响）。
    """
    r = np.clip(_to01(roughness), 1e-4, 1.0)
    e = EXP_NUMERATOR / (r * r) * float(gain)
    return np.clip(e, EXP_MIN, EXP_MAX)


def exponent_channel(roughness, gain: float = 1.0) -> np.ndarray:
    """粗糙度 → exponent 贴图 **R 通道**的 8 位值（0..255）。"""
    e = roughness_to_exponent(roughness, gain)
    v = (e - EXP_MIN) / (EXP_MAX - EXP_MIN) * 255.0
    return np.clip(np.rint(v), 0, 255).astype(np.uint8)


# 「高光锐度」的四档快捷值（傻瓜模式：一根滑杆 + 4 个档位）
SHARPNESS_STEPS = {
    "柔和": 0.6, "标准": 1.0, "锐利": 1.5, "极锐": 2.2,
}
SHARPNESS_MIN, SHARPNESS_MAX = 0.4, 2.5


def sharpness_from_slider(value: float) -> float:
    """滑杆 0..100 → gain（对数手感：中间=1.0，两端 0.4 / 2.5）。"""
    t = float(np.clip(value, 0, 100)) / 100.0
    return float(round(SHARPNESS_MIN * (SHARPNESS_MAX / SHARPNESS_MIN) ** t, 3))


def slider_from_sharpness(gain: float) -> int:
    g = float(np.clip(gain, SHARPNESS_MIN, SHARPNESS_MAX))
    t = np.log(g / SHARPNESS_MIN) / np.log(SHARPNESS_MAX / SHARPNESS_MIN)
    return int(round(t * 100))


def exponent_to_roughness(channel):
    """反函数（GUI 显示"这一档相当于多粗糙"、以及报告里用）。"""
    c = np.clip(np.asarray(channel, dtype=np.float32), 0, 255) / 255.0
    e = EXP_MIN + c * (EXP_MAX - EXP_MIN)
    return np.sqrt(EXP_NUMERATOR / np.maximum(e, 1e-6))


def phong_mask(roughness) -> np.ndarray:
    """粗糙度 → Phong 遮罩（0..1，越大越亮/越高光）。"""
    r = _to01(roughness)
    return np.clip((1.0 - r) ** 3 * MASK_GAIN, 0.0, 1.0)


def near_specular_clip_ratio(roughness) -> float:
    """有多少比例的像素因为 0.8/r²>150 而被顶格（给报告/警告用）。"""
    r = _to01(roughness)
    if r.size == 0:
        return 0.0
    return float((EXP_NUMERATOR / np.maximum(r, 1e-4) ** 2 > EXP_MAX).mean())


# ---------------------------------------------------------------- 通用 LUT

def lut_from_points(points, size: int = 256) -> np.ndarray:
    """控制点 [(x, y), ...]（x/y 都在 0..1）→ 长度 size 的 LUT（float32）。

    线性插值 + 两头夹紧；x 不必预先排序（这里会排）。给将来 GUI 的曲线编辑器用。
    """
    pts = sorted((float(x), float(y)) for x, y in points)
    if not pts:
        return np.zeros(size, np.float32)
    if len(pts) == 1:
        return np.full(size, np.clip(pts[0][1], 0.0, 1.0), np.float32)
    xs = np.array([p[0] for p in pts], np.float32)
    ys = np.array([p[1] for p in pts], np.float32)
    grid = np.linspace(0.0, 1.0, size, dtype=np.float32)
    return np.clip(np.interp(grid, xs, ys), 0.0, 1.0).astype(np.float32)


def apply_lut(values01: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """把 0..1 的值过一遍 LUT（会做最近邻采样；LUT 长度决定量化级数）。"""
    idx = np.clip(np.rint(np.asarray(values01) * (len(lut) - 1)), 0, len(lut) - 1).astype(np.int32)
    return lut[idx]


# ---------------------------------------------------------------------------
# 2026-09-27 新增（施工单 `_task/07-S3+S4-预览与拉条.md` S4）—— **只增不改**：
# 下面这些函数**不改上面任何一个公式与常数**，只提供"在既有曲线之前"作用的中性旋钮。
# 每个旋钮的默认值都保证**原样返回**（连数组都不复制）→ 默认值下产物逐位一致。
# ---------------------------------------------------------------------------

# 「粗糙度整体偏移」滑杆的两端（左 = 更亮更反光 / 右 = 更哑）
ROUGHNESS_OFFSET_MIN, ROUGHNESS_OFFSET_MAX = -0.35, 0.35
# 「金属染色强度」（exp 的 G 通道整体缩放）；1.0 = 不干预
METAL_TINT_MIN, METAL_TINT_MAX = 0.0, 2.0
# 笔刷「反射强度」（envmap 遮罩整体增益）；1.0 = 不干预。
# ⚠️ 量程必须**在对数上对称于 1.0**（0.25 × 4.0 = 1）→ 滑杆正好在中点 50 时 = 1.0 不干预。
# 早先写成 0.25..3.0，中点就成了 0.866（"不动滑杆却已经在改产物"，自测当场抓到）。
ENVMAP_GAIN_MIN, ENVMAP_GAIN_MAX = 0.25, 4.0


def apply_roughness_offset(roughness, offset: float = 0.0):
    """「粗糙度整体偏移」：`r' = clamp(r + offset)`。

    ⚠️ **offset = 0（默认）时原样返回**（同一个对象，不复制）—— 这是"默认值下逐位一致"的
    第一道保证。作用点 = **粗糙度灰度图 → 既有曲线之间**。
    """
    if not offset:
        return roughness
    return np.clip(_to01(roughness) + float(offset), 0.0, 1.0)


def apply_roughness_points(roughness, points):
    """曲线编辑器：控制点 `[(x, y), ...]` → LUT → 作用在粗糙度上（`r' = LUT(r)`）。

    ⚠️ **没有控制点（默认 `[]`）时原样返回**。LUT 的通用件（`lut_from_points` / `apply_lut`）
    本来就是为这件事写的，这里只是把它接到粗糙度上。
    """
    if not points:
        return roughness
    return apply_lut(_to01(roughness), lut_from_points(points))


def scale_metal_tint(metallic, tint: float = 1.0):
    """「金属染色强度」：把金属度（= exp 贴图的 **G 通道** = 高光染色强度）整体缩放。

    ⚠️ **tint = 1.0（默认）时原样返回**（同一个对象）。
    """
    if float(tint) == 1.0:
        return metallic
    a = np.asarray(metallic)
    f = (a.astype(np.float32) / 255.0 if a.dtype == np.uint8 else a.astype(np.float32))
    return np.clip(np.rint(np.clip(f, 0.0, 1.0) * float(tint) * 255.0), 0, 255).astype(np.uint8)


def offset_from_slider(value: float) -> float:
    """「粗糙度整体偏移」滑杆 0..100 → 偏移量（**50 = 0.0 不干预**，两端 ∓）。"""
    t = (float(np.clip(value, 0, 100)) - 50.0) / 50.0
    span = ROUGHNESS_OFFSET_MAX if t >= 0 else -ROUGHNESS_OFFSET_MIN
    return float(round(t * span, 3))


def slider_from_offset(offset: float) -> int:
    o = float(np.clip(offset, ROUGHNESS_OFFSET_MIN, ROUGHNESS_OFFSET_MAX))
    span = ROUGHNESS_OFFSET_MAX if o >= 0 else -ROUGHNESS_OFFSET_MIN
    return int(round(50 + o / span * 50))


def tint_from_slider(value: float) -> float:
    """「金属染色强度」滑杆 0..100 → 0.0..2.0（**50 = 1.0 不干预**）。"""
    t = float(np.clip(value, 0, 100)) / 100.0
    return float(round(METAL_TINT_MIN + t * (METAL_TINT_MAX - METAL_TINT_MIN), 3))


def slider_from_tint(tint: float) -> int:
    t = float(np.clip(tint, METAL_TINT_MIN, METAL_TINT_MAX))
    return int(round((t - METAL_TINT_MIN) / (METAL_TINT_MAX - METAL_TINT_MIN) * 100))


def gain_from_slider(value: float) -> float:
    """笔刷「反射强度」滑杆 0..100 → 0.25..3.0（**50 = 1.0 不干预**，对数手感）。"""
    t = float(np.clip(value, 0, 100)) / 100.0
    return float(round(ENVMAP_GAIN_MIN * (ENVMAP_GAIN_MAX / ENVMAP_GAIN_MIN) ** t, 3))


def slider_from_gain(gain: float) -> int:
    g = float(np.clip(gain, ENVMAP_GAIN_MIN, ENVMAP_GAIN_MAX))
    t = np.log(g / ENVMAP_GAIN_MIN) / np.log(ENVMAP_GAIN_MAX / ENVMAP_GAIN_MIN)
    return int(round(t * 100))
