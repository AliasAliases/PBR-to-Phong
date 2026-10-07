"""VTF 层：调 VTFCmd 把 PNG 转成 VTF，并**验证产物真的生成了**。

⚠️ 两条来自实测的硬规矩（`阶段0_实测/`，2026-09-25）：
  1. **不能信 VTFCmd 的退出码**——尺寸不是 4 的倍数时它静默失败（不产文件、不报错、rc=0）。
     所以每次转换后都必须自己检查产物存在 + 头部尺寸对不对。
  2. **`-flag NORMAL` 只写标志位，不做任何通道重排**——法线绿通道要我们自己翻。
"""

from __future__ import annotations

import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

# 常见安装位置（找不到时由用户手动指定；GUI 会记住）
VTFCMD_CANDIDATES = (
    Path(r"C:\Users\Admin\Desktop\blender files\L4D2 mod making stuff\VTFEdit_Reloaded_v2.1.10\VTFCmd.exe"),
)

VTF_SIGNATURE = b"VTF\x00"

# VTFCmd.exe 的输出是 **GBK**。所以解码必须显式带 errors="replace"：
# 否则在 PYTHONUTF8=1（UTF-8 模式）下，subprocess 的读线程会当场抛 UnicodeDecodeError
# 死掉，`proc.stdout` 直接变成 None —— 恰好在最需要"原因"的时候把原因吞了。
# GBK 向下兼容 ASCII，所以它的英文输出照样一个字节不差。
VTFCMD_ENCODING = "gbk"

# 输出用哪个 VTF 版本：官方 7620 个 VTF 的实测分布 = 7.4 占 6778，另有 7.0/7.1/7.2/7.3，
# **没有 7.5** → 7.0~7.4 都在安全区，取最新的 7.4（不要用 VTFCmd 的默认 7.3 也行，但统一到 7.4）。
DEFAULT_VERSION = "7.4"

FLAG_BITS = {
    "POINTSAMPLE": 0x0001, "TRILINEAR": 0x0002, "CLAMPS": 0x0004, "CLAMPT": 0x0008,
    "ANISOTROPIC": 0x0010, "HINT_DXT5": 0x0020, "SRGB": 0x0040, "NORMAL": 0x0080,
    "NOMIP": 0x0100, "NOLOD": 0x0200, "MINMIP": 0x0400, "PROCEDURAL": 0x0800,
    "ONEBITALPHA": 0x1000, "EIGHT_BIT_ALPHA": 0x2000, "EMBM": 0x4000, "ENVMAP": 0x8000,
}

FORMAT_NAMES = {
    0: "RGBA8888", 1: "ABGR8888", 2: "RGB888", 3: "BGR888", 4: "RGB565", 5: "I8",
    6: "IA88", 7: "P8", 8: "A8", 12: "BGRA8888", 13: "DXT1", 14: "DXT3", 15: "DXT5",
    16: "BGRX8888", 20: "DXT1_ONEBITALPHA",
}


class VtfError(RuntimeError):
    """VTF 转换失败。message 是给**人**看的说明，不是堆栈。"""


@dataclass
class VtfInfo:
    version: tuple
    width: int
    height: int
    image_format: int
    mip_count: int
    flags: int

    @property
    def format_name(self) -> str:
        return FORMAT_NAMES.get(self.image_format, f"?{self.image_format}")

    @property
    def flag_names(self) -> list:
        return [n for n, b in FLAG_BITS.items() if self.flags & b]

    def __str__(self) -> str:
        return (f"VTF {self.version[0]}.{self.version[1]} {self.width}x{self.height} "
                f"{self.format_name} mips={self.mip_count} flags={'|'.join(self.flag_names) or '无'}")


def find_vtfcmd(explicit: str | Path | None = None) -> Path | None:
    """找 VTFCmd：先看用户指定的，再看常见位置。找不到返回 None（由上层给引导）。"""
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for c in VTFCMD_CANDIDATES:
        if c.is_file():
            return c
    return None


def run_vtfcmd(args, timeout: int = 600) -> subprocess.CompletedProcess:
    """跑一次 VTFCmd 并接住它的输出（stdout/stderr 已解码成 str）。

    解码上的硬规矩：**绝不能让非 UTF-8 字节把读线程搞死**。固定用
    errors="replace"，再怪的字节也能落成替代字符，`proc.stdout` 不会是 None
    —— 报错时那段"原因"才拿得到。
    """
    return subprocess.run(args, capture_output=True,
                          encoding=VTFCMD_ENCODING, errors="replace", timeout=timeout)


def read_info(path: str | Path) -> VtfInfo:
    """只读头部（够用：校验尺寸/格式/标志；像素解码在需要时再补）。"""
    raw = Path(path).read_bytes()
    if raw[:4] != VTF_SIGNATURE:
        raise VtfError(f"{Path(path).name} 不是 VTF 文件")
    major, minor, _hdr, width, height, flags, _frames, _first = struct.unpack_from("<IIIHHIHH", raw, 4)
    (image_format,) = struct.unpack_from("<I", raw, 52)
    (mip_count,) = struct.unpack_from("<B", raw, 56)
    return VtfInfo((major, minor), width, height, image_format, mip_count, flags)


def convert(
    png: str | Path,
    out_dir: str | Path,
    *,
    fmt: str = "DXT5",
    alpha_format: str | None = None,
    flags: tuple = (),
    version: str | None = DEFAULT_VERSION,
    output_name: str | None = None,
    mipmaps: bool = True,
    vtfcmd: str | Path | None = None,
    expect_size: tuple | None = None,
) -> Path:
    """PNG → VTF。返回产物路径。

    参数直接映射到 VTFCmd 的命令行；`expect_size` 给了就顺便校验产物尺寸（默认拿 PNG 的尺寸）。
    失败一律抛 `VtfError`，且消息是**人话**。
    """
    src = Path(png)
    if not src.is_file():
        raise VtfError(f"找不到输入图片：{src}")

    exe = find_vtfcmd(vtfcmd)
    if exe is None:
        raise VtfError("没找到 VTFCmd.exe。请安装 VTFEdit Reloaded，或在设置里指定它的位置。")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ((output_name or src.stem) + ".vtf")
    if target.exists():
        target.unlink()                       # 免得拿旧文件当成功

    args = [str(exe), "-file", str(src), "-output", str(out_dir),
            "-format", fmt, "-alphaformat", alpha_format or fmt,
            "-nothumbnail", "-noreflectivity"]
    if not mipmaps:
        args.append("-nomipmaps")
    if flags:
        args += ["-flag", ",".join(flags)]
    if version:
        args += ["-version", version]

    proc = run_vtfcmd(args, timeout=600)

    # ★ 关键：不信退出码，只认产物
    produced = out_dir / (src.stem + ".vtf")
    if not produced.is_file():
        w, h = expect_size or _png_size(src)
        hint = "" if (w % 4 == 0 and h % 4 == 0) else \
            f"（这张图是 {w}×{h}，VTFCmd 要求宽高都能被 4 整除）"
        raise VtfError(
            f"VTFCmd 没有生成 .vtf{hint}。它退出码是 {proc.returncode}，"
            f"所以别信退出码——要看清上面的原因。\n{(proc.stdout or '').strip()[-300:]}"
        )
    if produced != target:
        produced.replace(target)

    if expect_size is None:
        expect_size = _png_size(src)
    info = read_info(target)
    if (info.width, info.height) != tuple(expect_size):
        raise VtfError(
            f"产物尺寸不对：期望 {expect_size[0]}×{expect_size[1]}，"
            f"实际 {info.width}×{info.height}。VTFCmd 可能偷偷缩放了，请检查参数。"
        )
    return target


def _png_size(path: Path) -> tuple:
    from PIL import Image
    with Image.open(path) as im:
        return im.size
