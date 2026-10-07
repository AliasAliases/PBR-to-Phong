"""VMT 生成层。

规则（全部来自官方实物与实测，见实施计划 §9.5）：
  · 参数顺序按"先贴图、后状态"排列，尽量接近官方手写风格（便于用户对照/手改）
  · 顶层块要能被 HDR/dxlevel 覆盖块包裹（CS:S `ladderaluminium` 里有 `vertexlitgeneric_HDR_dx9 { ... }`）
  · 值里有空格的（如 `$phongfresnelranges "[.3 .65 30]"`）原样带引号写
  · **不做**任何"顺手帮你加个参数"的事——用户没勾的就是不写
"""

from __future__ import annotations

import re
from pathlib import Path

# 官方内容里几乎总是成组出现的参数，生成时排在一起（只是排序偏好，不改变语义）
_ORDER = [
    "$basetexture", "$compress", "$bumpmap", "$phongexponenttexture", "$envmapmask",
    "$phong", "$phongboost", "$phongexponent", "$phongfresnelranges",
    "$phongtint", "$phongalbedotint", "$basemapalphaphongmask",
    "$basemapluminancephongmask", "$invertphongmask",
    "$envmap", "$envmaptint", "$envmapcontrast", "$envmapsaturation", "$envmapfresnel",
    "$halflambert", "$alphatest", "$translucent", "$nocull", "$nodecal",
    "$surfaceprop", "$model", "$additive", "$selfillum",
]


def render(shader: str = "VertexLitGeneric", params=None, blocks=None) -> str:
    """生成 .vmt 文本。

    params: [(键, 值), ...] —— 值可以是 str/int/float/bool；bool 按 0/1 写。
    blocks: [(块名, [(键, 值), ...]), ...] —— 额外块，如 ("vertexlitgeneric_HDR_dx9", [...])
    """
    lines = [f'"{shader}"', "{"]
    for key, value in _sorted(params or []):
        lines.append(f'\t"{key}" {_fmt(value)}')
    for block_name, block_params in blocks or []:
        lines.append("")
        lines.append(f'\t"{block_name}"')
        lines.append("\t{")
        for key, value in _sorted(block_params):
            lines.append(f'\t\t"{key}" {_fmt(value)}')
        lines.append("\t}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    s = str(value)
    return f'"{s}"'          # 统一带引号：值里有空格（fresnelranges 等）也不会错


def _sorted(params) -> list:
    keys = {k.lower(): i for i, k in enumerate(_ORDER)}
    return sorted(params, key=lambda kv: (keys.get(kv[0].lower(), len(_ORDER)), kv[0].lower()))


# ---------------------------------------------------------------- EyeRefract（13-E）

# ⚠️ 照抄官方实物（`Textures/survivors/{coach,gambler,mechanic,producer}/*_eyeball_l/r.vmt`，
#    8 份**完全同构**，键集一模一样）：**裸键名、无缩进、该引号的引号、数字不引号**，
#    而且 `$Envmap` 的值**结尾带一个 `-`**（`"Engine/eye-reflection-cubemap-"`）—— 官方原样，
#    **别"顺手修掉"**（少这个减号就指向了另一个资源）。
#    ⚠️ 所以它**不能**走上面的 `render()`：那个会给键也加引号、还按 `_ORDER` 重排。
_EYE_OFFICIAL = [
    ("$Envmap", '"Engine/eye-reflection-cubemap-"'),
    ("$CorneaTexture", '"Engine/eye-cornea"'),
    ("$EyeballRadius", '"0.5"'),
    ("$AmbientOcclColor", '"[.4 .3 .27]"'),
    ("$Dilation", '".6"'),
    ("$ParallaxStrength", '"0.25"'),
    ("$CorneaBumpStrength", '".5"'),
    ("$halflambert", "1"),
    ("$nodecal", "1"),
    ("$ambientocclusion", "1"),
    ("$RaytraceSphere", "1"),
    ("$SphereTexkillCombo", "0"),
]


def render_eyerefract(iris: str, ao: str = "") -> str:
    """生成**官方同构**的 `EyeRefract` 材质（13-E）。

    `iris` 必填（我们的虹膜图名）；`ao` 为空时 `$AmbientOcclTexture` **整行不写**
    （官方 8 份都有，但选填项缺了就不该写空值）。其余键**逐字照官方**。
    """
    lines = ["EyeRefract", "{"]
    lines.append(f'$Iris "{iris}"')
    if ao:
        lines.append(f'$AmbientOcclTexture "{ao}"')
    lines += [f"{key} {value}" for key, value in _EYE_OFFICIAL]
    lines.append("}")
    return "\n".join(lines) + "\n"


def write(text: str, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------- 读（校验模型要用）

_PAIR = re.compile(r'^\s*"?(\$[A-Za-z0-9_]+)"?\s+"?([^"\r\n]*)"?\s*$', re.MULTILINE)


def parse(text: str) -> dict:
    """把 .vmt 读成 {小写键: 值}，够用来查 `$basetexture` 指向哪张图。

    宽松解析：只认 `$key value` 这种行，忽略花括号与块结构。
    ⚠️ 官方 VMT 里还有 `patch { include "..." insert {...} }` 这种结构
    （`coach_head_it.vmt` 就是），这里不展开 include，只把 include 路径记下来，
    免得"校验模型"把 patch 材质误判成"缺参数"。
    """
    params = {}
    for key, value in _PAIR.findall(text):
        params.setdefault(key.lower(), value.strip())
    return params


def includes(text: str) -> list:
    return [m.group(1) for m in re.finditer(r'include\s+"([^"]+)"', text)]


def is_patch(text: str) -> bool:
    return bool(re.match(r'\s*patch\s*\{', text, re.IGNORECASE))
