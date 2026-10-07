"""命名层：从编译好的 `.mdl` 读出「引擎会去哪儿找材质」。

为什么读 .mdl 而不是问用户：`$cdmaterials` 与材质名在**编译时就被 studiomdl 烘进 MDL**，
编译之后信息是冻结的（改文件夹必须重编译）。所以 .mdl 是权威来源，比 SMD/用户记忆都可靠。

⚠️ 实测关键点（9 个真实模型 9/9 验证通过）：
  · `mstudiotexture_t.sznameindex` 是**相对本结构自身**的偏移（SDK 里就是 `((char*)this)+sznameindex`），
    写成绝对偏移会读出乱码。
  · `$cdmaterials` 的字符串是**绝对**偏移。
  · **纹理表本身就是模型的材质清单**，不需要再走 网格 反查（未赋材质的面会写成 `no_material`）。
  · 大小写原样保留、绝不改写（必须与 MDL 里烘的字符串一致）。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

IDST = 0x54534449  # "IDST"

OFF_NAME = 12
OFF_NUMTEXTURES = 204
OFF_TEXTUREINDEX = 208
OFF_NUMCDTEXTURES = 212
OFF_CDTEXTUREINDEX = 216

SIZEOF_TEXTURE = 64          # mstudiotexture_t（定长结构数组，不是偏移表）
MISSING_MATERIAL = "no_material"


class MdlError(RuntimeError):
    """MDL 读取失败（消息给人看）。"""


@dataclass
class StudioModel:
    path: Path
    version: int
    name: str
    cdmaterials: list = field(default_factory=list)
    textures: list = field(default_factory=list)

    @property
    def missing_materials(self) -> list:
        return [t for t in self.textures if t.lower() == MISSING_MATERIAL]

    def expected_vmt_paths(self) -> list:
        """引擎实际会去找的 materials 相对路径（`$cdmaterials` + 材质名 直接拼接）。"""
        out = []
        for cd in (self.cdmaterials or [""]):
            d = cd.replace("\\", "/").strip("/")
            for t in self.textures:
                out.append(f"{d}/{t}.vmt" if d else f"{t}.vmt")
        return out

    def target_dir(self, index: int = 0) -> str:
        """第 index 个材质该被放到 materials 下的哪个目录（正斜杠、无首尾斜杠）。"""
        cd = self.cdmaterials[index] if index < len(self.cdmaterials) else ""
        return cd.replace("\\", "/").strip("/")


def _cstr(buf: bytes, off: int) -> str:
    end = buf.index(b"\x00", off)
    return buf[off:end].decode("utf-8", errors="replace")


def read_mdl(path: str | Path) -> StudioModel:
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise MdlError(f"读不了这个模型文件：{p.name}（{e.strerror}）") from e
    if len(data) < 260:
        raise MdlError(f"{p.name} 太小了，不像是一个编译好的 .mdl")
    id_, version = struct.unpack_from("<ii", data, 0)
    if id_ != IDST:
        raise MdlError(f"{p.name} 不是 Source 模型文件（可能你选的是 .smd 或 .vvd）")

    name = _cstr(data, OFF_NAME)
    num_textures, tex_index = struct.unpack_from("<ii", data, OFF_NUMTEXTURES)
    num_cd, cd_index = struct.unpack_from("<ii", data, OFF_NUMCDTEXTURES)
    if not (0 <= num_textures <= 4096) or not (0 <= tex_index < len(data)):
        raise MdlError(f"{p.name} 的头部读不出来（材质表位置异常），可能是版本不支持")

    mdl = StudioModel(path=p, version=version, name=name)
    for i in range(num_textures):
        base = tex_index + i * SIZEOF_TEXTURE
        (sznameindex,) = struct.unpack_from("<i", data, base)
        stroff = base + sznameindex                      # ★ 相对自身
        if 0 <= stroff < len(data):
            mdl.textures.append(_cstr(data, stroff))

    for i in range(max(0, min(num_cd, 1024))):
        (stroff,) = struct.unpack_from("<i", data, cd_index + i * 4)
        if 0 <= stroff < len(data):
            mdl.cdmaterials.append(_cstr(data, stroff))
    return mdl


def find_models_with_name(root: str | Path, name: str) -> list:
    """在 L4D2 `models\\` 下按名字找模型（用户写 school_gate 就找 school_gate.mdl）。"""
    root = Path(root)
    if not root.is_dir():
        return []
    key = name.strip().lower()
    if key.endswith(".mdl"):
        key = key[:-4]
    return sorted(p for p in root.rglob("*.mdl") if p.stem.lower() == key)


def check_path_case(materials_root: str | Path, rel: str) -> str:
    """按**大小写敏感**逐级查盘上真实文件。

    返回：""=完全一致 / "missing"=不存在 / 其他=大小写不符的说明。
    Windows 不敏感所以能跑，Linux srcds 会挂——这一条是给 Linux 服务器用的警告。
    """
    cur = Path(materials_root)
    parts = rel.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if not cur.is_dir():
            return "missing"
        entries = {p.name: p for p in cur.iterdir()}
        if part not in entries:
            ci = [n for n in entries if n.lower() == part.lower()]
            if ci:
                return f"磁盘上实际是 {'/'.join(parts[:i] + [ci[0]])}"
            return "missing"
        cur = entries[part]
    return ""
