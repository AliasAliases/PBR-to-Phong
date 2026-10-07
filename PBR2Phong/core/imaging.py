"""图像搬运层：PNG 读写、numpy 互转、通道工具。

约束：纯 Python（numpy + Pillow），**不 import 任何 GUI、不 print**。
色彩空间的解释由调用者负责（core 只搬运数值，不猜语义）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load(path: str | Path) -> np.ndarray:
    """读 PNG/GIF/BMP/TGA 等，返回 (H, W, C) 的 uint8，C ∈ {1, 3, 4}。

    16 位输入会被降到 8 位（Source 的 VTF 是 8 位；降位规则写在这里，别散在别处）。
    """
    im = Image.open(path)
    arr = np.array(im)
    if arr.dtype == np.uint16:                      # 16bit → 8bit
        arr = (arr.astype(np.uint32) * 255 // 65535).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    return arr


def save(arr: np.ndarray, path: str | Path) -> Path:
    """写 PNG（无损；游戏侧要的 8 位 PNG 就是它）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    a = arr
    if a.ndim == 2:
        a = a[:, :, None]
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[a.shape[2]]
    src = a[:, :, 0] if a.shape[2] == 1 else a      # "L" 模式必须传 (H, W)
    Image.fromarray(src, mode).save(p)
    return p


def ensure_rgba(arr: np.ndarray) -> np.ndarray:
    """统一成 (H, W, 4)。灰度/彩色都能吃，缺 alpha 补 255（不透明）。"""
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        arr = arr[:, :, None]
    c = arr.shape[2]
    if c == 4:
        return arr
    if c == 3:
        return np.dstack([arr, np.full((h, w), 255, np.uint8)])
    if c == 1:
        return np.dstack([np.repeat(arr, 3, axis=2), np.full((h, w), 255, np.uint8)])
    raise ValueError(f"通道数不支持：{c}")


def ensure_rgb(arr: np.ndarray) -> np.ndarray:
    """统一成 (H, W, 3)，丢掉 alpha。"""
    if arr.ndim == 2:
        return np.repeat(arr[:, :, None], 3, axis=2)
    if arr.shape[2] == 3:
        return arr
    if arr.shape[2] == 4:
        return arr[:, :, :3]
    if arr.shape[2] == 1:
        return np.repeat(arr, 3, axis=2)
    raise ValueError(f"通道数不支持：{arr.shape[2]}")


def resample(arr: np.ndarray, width: int, height: int) -> np.ndarray:
    """双线性重采样到指定尺寸（灰度/彩色/带 alpha 都吃）。

    ⚠️ 调用方负责遵守"只放大、不缩小"的规矩——这个函数本身不做判断。
    """
    a = arr if arr.ndim == 3 else arr[:, :, None]
    mode = {1: "L", 3: "RGB", 4: "RGBA"}[a.shape[2]]
    src = a[:, :, 0] if a.shape[2] == 1 else a
    out = np.array(Image.fromarray(src, mode).resize((width, height), Image.BILINEAR))
    return out if arr.ndim == 3 else out


def solid(width: int, height: int, rgb, alpha=255) -> np.ndarray:
    """造一张纯色图（RGBA）。"""
    out = np.zeros((height, width, 4), np.uint8)
    out[:, :, 0], out[:, :, 1], out[:, :, 2] = rgb
    out[:, :, 3] = alpha
    return out


def paste(dst: np.ndarray, src: np.ndarray, x: int, y: int) -> None:
    """把 src 贴到 dst 的 (x, y)（就地修改，超出边界自动裁剪）。"""
    h, w = src.shape[:2]
    dh, dw = dst.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(dw, x + w), min(dh, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    dst[y0:y1, x0:x1, : src.shape[2]] = src[y0 - y:y1 - y, x0 - x:x1 - x]
