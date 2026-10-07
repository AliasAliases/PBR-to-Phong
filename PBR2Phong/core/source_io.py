"""输入层：把 Material Bakery 烘出来的贴图文件夹，认成"一套套素材 + 每张图是什么"。

输入契约（读 Auto Bake v1.5 的 `core/imported.py` 得到，是**格式事实**不是代码借用）：
  · 一个集合一个目录，图名 `<前缀>-<类型>-<尺寸>.png`（历史写法五花八门：
    有 `Common Parts 1BaseColor-2048` 这种前缀与类型粘在一起的，也有 `-2048px` 的）
  · 目录里可能有 `_mbakery.json`，结构：
        {"format": "material_bakery/textures", "version": 1, "group": "...",
         "uv_layer": "", "textures": {"<type_key>": {"file": "x.png",
                                                     "size_x": 2048, "size_y": 2048}}}
    ⚠️ `textures` 是**按 type_key 索引**的，不是按文件名 —— 要先建 文件名→条目 的反查表。

⚠️ 许可边界：Auto Bake 是 **GPL v2+**，本项目是 MIT。所以这里**只借鉴格式事实、
不抄它的代码**——逻辑是自己写的。（同名函数/同名字段是互操作所必需。）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MANIFEST_NAME = "_mbakery.json"
MANIFEST_FORMAT = "material_bakery/textures"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".exr", ".tga", ".bmp", ".webp")

# 我们要用的语义类型（右侧是文件里可能出现的写法，已归一化成"只留小写字母数字"）
TYPE_ALIASES = {
    "shader.base_color": ("basecolor", "albedo", "color", "diffuse"),
    "shader.roughness": ("roughness", "rough"),
    "shader.metallic": ("metallic", "metalness"),
    "standard.normal": ("normal", "normalmap"),
    "shader.normal": ("normal", "normalmap"),
    "misc.ao": ("ambientocclusion", "ao"),
    "standard.ao": ("ambientocclusion",),
    "shader.emission_color": ("emissioncolor", "emissive", "emission"),
    "shader.emission_strength": ("emissionstrength",),
    "shader.alpha": ("alpha", "opacity"),
    "misc.channel_packing": ("channelpacking", "packed"),
}

# v1 真正会用到的四种；其余认出来但"这一版不用"，要如实报告给用户
USED_TYPES = ("shader.base_color", "shader.roughness", "shader.metallic",
              "standard.normal", "shader.normal", "misc.ao")
NORMAL_KEYS = ("standard.normal", "shader.normal", "misc.normal")

# 文件名里的类型 token → type_key，长的优先（"AmbientOcclusion" 不能被 "Normal" 抢先）
_TOKENS = {}
for _key, _aliases in TYPE_ALIASES.items():
    for _a in _aliases:
        _TOKENS.setdefault(_a, _key)
_TOKENS = dict(sorted(_TOKENS.items(), key=lambda kv: -len(kv[0])))

_SEPARATORS = re.compile(r"[-_\s.]+")
_SIZE_TOKEN = re.compile(r"^(\d+)([kK])?(px)?$")
_SIZE_PAIR = re.compile(r"^(\d+)([kK])?[x×](\d+)([kK])?(px)?$")

# ---- Material Bakery 新写法：**没有 alpha 的底色 = 正名 + `_NoAlpha`**（15-B）----------------
# 规则（照抄 MB 的 `naming.NO_ALPHA_SUFFIX = "_NoAlpha"`，UDIM 瓦片号插在标记**后面**）：
#   · 带 alpha 的底色   = 正名            `Body-BaseColor-2k.png`
#   · 没有 alpha 的底色 = 正名 + `_NoAlpha` `Body-BaseColor-2k_NoAlpha.png`
#   · UDIM 瓦片         = 标记之后再插瓦片号 `Body-BaseColor-2k_NoAlpha.1001.png`
# ⚠️ **必须在解析之前剥掉**：不剥的话尾段会被"粘着写法"回退当成"以 alpha 结尾" → 认成 `shader.alpha`，
#    底色就被**静默**丢进 `ignored`。MB 的 `_strip_no_alpha_marker()` 注释里踩的是同一个坑。
# 口径与 MB 一致：**前面必须是分隔符或行首、后面必须是结尾或 `.瓦片号`** ——
# 用户自己起的 `NoAlphaFoo-BaseColor-2k` 不许误伤（后面跟的是 `F`，不匹配）。
_NO_ALPHA_MARKER = re.compile(r"(?:^|[ _\-.])no[ _\-]?alpha(?=$|\.\d)", re.IGNORECASE)
_UDIM_SUFFIX = re.compile(r"\.(\d{4})$")           # `….1001` = 瓦片号，不是尺寸
_UDIM_RANGE = (1001, 1100)                          # UDIM 的合法瓦片号区间（1001+u+10v）


def strip_no_alpha_marker(stem: str) -> tuple:
    """剥掉 `_NoAlpha` 标记 → (剥完的名字, 是否带标记)。"""
    text = str(stem)
    m = _NO_ALPHA_MARKER.search(text)
    if not m:
        return text, False
    return text[:m.start()] + text[m.end():], True


def _is_udim_tile(token: str) -> bool:
    return token.isdigit() and _UDIM_RANGE[0] <= int(token) <= _UDIM_RANGE[1]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


def parse_size(token: str) -> tuple:
    """`2k`→(2048,2048) `2048`→(2048,2048) `1024x512`→(1024,512) `2kx1k` 都认。认不出→(0,0)"""
    t = str(token or "").strip()
    m = _SIZE_PAIR.match(t)
    if m:
        to_px = lambda n, s: int(n) * 1024 if s else int(n)
        return to_px(m.group(1), m.group(2)), to_px(m.group(3), m.group(4))
    m = _SIZE_TOKEN.match(t)
    if not m:
        return 0, 0
    v = int(m.group(1)) * (1024 if m.group(2) else 1)
    return v, v


def _trailing_alnum(text: str, count: int) -> int:
    seen = 0
    for i in range(len(text) - 1, -1, -1):
        if text[i].isalnum():
            seen += 1
            if seen == count:
                return len(text) - i
    return len(text)


def parse_filename(filename: str) -> tuple:
    """文件名 → (type_key|None, 宽, 高, 前缀)。认不出 type_key 返回 None（不猜）。"""
    stem = Path(str(filename)).stem
    stem, _declared = strip_no_alpha_marker(stem)   # 15-B：先剥标记，别让它冒充 alpha 图
    stem = _UDIM_SUFFIX.sub("", stem)               # 15-B：瓦片号不参与类型/尺寸解析
    parts = [p for p in _SEPARATORS.split(stem) if p]
    if not parts:
        return None, 0, 0, ""

    size_x = size_y = 0
    while len(parts) > 1:
        if _is_udim_tile(parts[-1]):                # 15-B：尺寸后面可能还挂着瓦片号
            parts.pop()
            continue
        if not parse_size(parts[-1])[0]:
            break                                   # 尺寸**不一定是末段**，但也不是任意段
        size_x, size_y = parse_size(parts.pop())

    for width in (3, 2, 1):                     # 从右往左拼 1~3 段找类型
        if len(parts) < width:
            continue
        if _norm("".join(parts[-width:])) in _TOKENS:
            key = _TOKENS[_norm("".join(parts[-width:]))]
            prefix = " ".join(parts[:len(parts) - width])
            return key, size_x, size_y, prefix.strip()

    glued = _norm(parts[-1])                    # 老写法：前缀和类型粘在一段里
    for token, key in _TOKENS.items():
        if len(token) < len(glued) and glued.endswith(token):
            cut = len(parts[-1]) - _trailing_alnum(parts[-1], len(token))
            prefix = " ".join(parts[:-1] + [parts[-1][:cut].strip(" -_.")])
            return key, size_x, size_y, prefix.strip()
    return None, size_x, size_y, " ".join(parts)


@dataclass
class MaterialSet:
    """一套素材 = 一个组名 + 若干张已识别的图。"""
    group: str
    images: dict = field(default_factory=dict)     # {type_key: 路径}
    sizes: dict = field(default_factory=dict)      # {type_key: (w, h)}
    source: str = "filename"                       # filename / manifest
    ignored: list = field(default_factory=list)    # 认出来但 v1 不用的类型
    unknown: list = field(default_factory=list)    # 15-C 缺陷 D：文件名认不出类型的图（**必须被看见**）
    declared_no_alpha: bool = False                # 15-B：文件名标了 `_NoAlpha` = 这张底色没有 alpha

    def get(self, *keys):
        for k in keys:
            if k in self.images:
                return self.images[k]
        return None

    @property
    def normal(self):
        return self.get(*NORMAL_KEYS)

    def images_text(self) -> str:
        """15-G：第 ① 页表格「认到的图」那一格的内容（**不含组名** —— 组名自己占一列）。

        ⚠️ 那里只回答"你导入了什么、认出了什么"：**一条状态都不许出现**（进度/完成与否属于
        第 ④ 页与底部状态栏）。
        """
        names = {"shader.base_color": "底色", "shader.roughness": "粗糙度",
                 "shader.metallic": "金属度", "standard.normal": "法线",
                 "shader.normal": "法线", "misc.ao": "AO"}
        text = "、".join(sorted(names.get(k, k) for k in self.images))
        if self.declared_no_alpha:      # 15-B：文件名写明的事，表格里带一句短的
            text += "（底色无 alpha）"
        return text

    def unrecognized_text(self) -> str:
        """15-C 缺陷 D：第 ① 页「没认出的」那一格 —— 认不出类型的文件名 + 认出来但本版不用的类型。"""
        parts = [f"{Path(p).name}（认不出是什么）" for p in self.unknown]
        parts += list(self.ignored)
        return "、".join(parts)

    def assign(self, path, type_key: str) -> bool:
        """手工把一张"认不出"的图**指定**成某个类型（指完就当正常素材用）。

        15-C 缺陷 D：`…-BaseColor-awdjw-1k.png` 这种名字解析不出类型 → 它先进 `unknown`，
        用户点它、选个类型，这一下就把它搬进 `images`。
        """
        target = Path(path)
        if target not in [Path(p) for p in self.unknown]:
            return False
        self.images[type_key] = target
        if not (self.sizes.get(type_key) or (0, 0))[0]:
            try:
                from . import imaging                     # 局部导入：别让模块级依赖绕圈
                arr = imaging.load(target)
                self.sizes[type_key] = (arr.shape[1], arr.shape[0])
            except Exception:  # noqa: BLE001 —— 读不了就交给转换那一步去报错
                self.sizes[type_key] = (0, 0)
        self.unknown = [p for p in self.unknown if Path(p) != target]
        return True

    def summary(self) -> str:
        names = {"shader.base_color": "底色", "shader.roughness": "粗糙度",
                 "shader.metallic": "金属度", "standard.normal": "法线",
                 "shader.normal": "法线", "misc.ao": "AO"}
        got = [names.get(k, k) for k in self.images]
        text = f"{self.group}（{self.source}）：" + "、".join(sorted(got))
        if self.declared_no_alpha:                  # 15-B：文件名已经写明的事，报告里也照说
            text += "；底色文件名标了 _NoAlpha —— 这张底色没有 alpha"
        return text


def read_manifest(folder: str | Path):
    p = Path(folder) / MANIFEST_NAME
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("textures"), dict):
        return None
    return data


def scan_folder(root: str | Path) -> list:
    """扫一个目录（可含多个子目录 = 多套素材），返回 [MaterialSet, ...]。

    优先 manifest（精确）；没有就按文件名反解（启发式，认不出就如实说不认）。
    """
    root = Path(root)
    if not root.is_dir():
        return []
    sets = []
    for current in sorted(p for p in root.rglob("*") if p.is_dir()) + [root]:
        images = sorted(f for f in current.iterdir()
                        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS)
        if not images:
            continue

        manifest = read_manifest(current)
        by_file, manifest_group = {}, ""
        if manifest:
            manifest_group = str(manifest.get("group") or "")
            for key, value in manifest["textures"].items():
                if isinstance(value, dict) and value.get("file"):
                    by_file[value["file"]] = (key, value)

        group = current.relative_to(root).as_posix() if current != root else ""
        item = MaterialSet(group=group or manifest_group or current.name,
                           source="manifest" if by_file else "filename")

        for img in images:
            _, declared_no_alpha = strip_no_alpha_marker(Path(img.name).stem)
            hit = by_file.get(img.name)
            if hit and isinstance(hit[1], dict):
                key = hit[0]
                legacy = int(hit[1].get("size", 0) or 0)
                item.sizes[key] = (int(hit[1].get("size_x", legacy) or legacy),
                                   int(hit[1].get("size_y", legacy) or legacy))
            else:
                key, sx, sy, prefix = parse_filename(img.name)
                if key is None:
                    # 15-C 缺陷 D：**不许静默丢掉** —— 记下来，界面要列出来、还要能手工指定类型
                    # （用户原话：改名成 `…-BaseColor-awdjw-1k.png` 后"导入素材表里直接少一张，
                    #   界面什么都不说"）
                    item.unknown.append(img)
                    continue
                item.sizes.setdefault(key, (sx, sy))
                if not item.group and prefix:
                    item.group = prefix
            if declared_no_alpha and key == "shader.base_color":
                item.declared_no_alpha = True
            if key in USED_TYPES:
                item.images.setdefault(key, img)
            else:
                item.ignored.append(f"{img.name}（{key}）")

        # ⚠️ 一张都没认出来、但**有认不出的图** → 也要收进来：那一套得让人看见、让人指认
        if item.images or item.unknown:
            sets.append(item)
    return sets
