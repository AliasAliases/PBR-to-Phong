# -*- coding: utf-8 -*-
"""**真启动一次打包好的 exe**，抓住它的窗口存图，并检查"窗口里确实画了东西"。

为什么不能只看"打包成功"：
  · `--windowed` 的 exe 崩在启动期是**没有任何提示**的（没控制台）→ 必须真跑一次；
  · 光看"进程还在"也不够：Qt 可能起来了但窗口是空白/报错框；
  · 所以判据 = **窗口标题对 + 抓到的图不是纯色**（用像素标准差当"有没有内容"的尺子）。

做法：`subprocess.Popen` 起 exe → `EnumWindows` 找它**可见的、够大的**主窗口 →
`PrintWindow(hwnd, dc, 2)` 抓图（PW_RENDERFULLCONTENT）→ 存 PNG → 关掉进程。

用法：
    python tests/check_exe.py                     # 用 ../../dist/PBR2Phong/PBR2Phong.exe
    python tests/check_exe.py <exe 路径> [输出目录]
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                  # 工作区根
DEFAULT_EXE = ROOT / "dist" / "PBR2Phong" / "PBR2Phong.exe"

PASS: list = []
FAIL: list = []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def make_dpi_aware() -> str:
    """让本进程 **DPI 感知** —— 这一步不做，高 DPI 屏上抓到的是"窗口的一角"。

    ⚠️ 2026-09-27 实测踩到：本机 DPR = 1.5（144 DPI）。进程**不** DPI 感知时，
    `GetWindowRect` 给的是**逻辑**尺寸（1295×797），而 Qt 是按**物理**像素画的
    （1280×760 逻辑 → 1920×1140 物理）→ `PrintWindow` 只填充了左上角那一块，
    存出来的图看着像"界面被横着裁掉了"。**那是抓图工具的锅，不是界面的锅**
    （同一版式用 Qt 自己量的最小需求 673px ≤ 实得 1274px，根本没溢出）。

    返回用了哪种模式，供断言"确实设上了"。
    """
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # PER_MONITOR_AWARE_V2
            return "per-monitor-v2"
    except Exception:  # noqa: BLE001
        pass
    try:
        if user32.SetProcessDPIAware():                                 # 老系统兜底
            return "system"
    except Exception:  # noqa: BLE001
        pass
    return "none"


def find_main_window(pid: int, min_size: int = 300):
    """返回该进程的可见主窗口 hwnd（够大的那个），找不到返回 0。"""
    hits: list = []

    def cb(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if rect.right - rect.left >= min_size and rect.bottom - rect.top >= min_size:
            hits.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return hits[0] if hits else 0


def grab(hwnd: int) -> Image.Image:
    """PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT) → PNG。"""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top

    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(memdc, bmp)
    user32.PrintWindow(hwnd, memdc, 2)                  # 2 = PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    header = BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.biWidth, header.biHeight = w, -h             # 负高度 = 自上而下
    header.biPlanes, header.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(memdc, bmp, 0, h, buf, ctypes.byref(header), 0)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXE
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "阶段0_实测" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("== 打包好的 exe：真启动一次 ==")
    # ⚠️ 必须在**创建任何窗口/DC 之前**设好，否则高 DPI 屏上抓图只覆盖窗口的一部分
    aware = make_dpi_aware()
    check("抓图进程已设 DPI 感知（否则高 DPI 屏只抓到窗口一角）", aware != "none", aware)
    check("exe 存在", exe.is_file(), str(exe))
    if not exe.is_file():
        return 1
    check("包里有 Qt（onedir 的 dll 在旁边）",
          (exe.parent / "_internal" / "PySide6" / "Qt6Core.dll").is_file(),
          str(exe.parent / "_internal" / "PySide6"))

    # ⚠️ 把配置目录指到临时目录：**别碰用户真实的 %APPDATA%\PBR2Phong**
    env = dict(os.environ)
    env["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-exe-")
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    print(f"  已启动 pid={proc.pid}（配置目录 {env['PBR2PHONG_HOME']}）")

    hwnd = 0
    deadline = time.time() + 45
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        hwnd = find_main_window(proc.pid)
        if hwnd:
            break
        time.sleep(0.5)
    time.sleep(1.5)                                     # 等它把界面画完

    title = ""
    img = None
    if hwnd:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        img = grab(hwnd)
        img.save(out_dir / "exe_window.png")

    check("进程活着（没启动就退出）", proc.poll() is None,
          f"exit={proc.poll()}")
    check("找到主窗口", bool(hwnd), f"hwnd={hwnd}")
    check("窗口标题是 PBR → Phong", "PBR" in title and "Phong" in title, title)
    if img is not None:
        arr = np.asarray(img.convert("RGB"), dtype=np.float32)
        try:
            dpi = user32.GetDpiForWindow(hwnd)
        except Exception:  # noqa: BLE001
            dpi = 0
        scale = (dpi / 96.0) if dpi else 0
        print(f"  窗口 DPI={dpi}（缩放 {scale:.2f}×）→ 抓图 {img.size[0]}×{img.size[1]} 物理像素")
        check("窗口里确实画了东西（不是纯色空白）", float(arr.std()) > 5.0,
              f"像素标准差 {float(arr.std()):.2f}，尺寸 {img.size}")
        # 若 DPI 感知没设上，抓到的宽度会只有"逻辑宽度"那么宽（本机 1295），一眼能看出来
        if scale > 1.01:
            expect_w = int(1280 * scale)
            check("抓到的图覆盖整个窗口（没被高 DPI 裁掉）",
                  img.size[0] >= expect_w - 40,
                  f"抓到 {img.size[0]}px，期望 ≥ {expect_w - 40}px（1280 逻辑 × {scale:.2f}）")
        check("截图已存", (out_dir / "exe_window.png").is_file(),
              str(out_dir / "exe_window.png"))

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"  已关闭（配置目录留在 {env['PBR2PHONG_HOME']}）")

    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"   失败：{f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
