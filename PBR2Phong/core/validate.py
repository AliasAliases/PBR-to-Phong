"""校验模型（v1 功能）：拿编译好的 `.mdl` 当权威，检查我们的产物是否真的对得上。

查四件事（实施计划 §2 的「校验模型」按钮）：
  ① VMT/VTF 是否落在 MDL 期望的位置
  ② VMT 里 `$basetexture` / `$bumpmap` / `$phongexponenttexture` 指向的 VTF 是否存在
  ③ 大小写是否与 MDL 里烘的字符串一致（Windows 能跑、**Linux srcds 会挂**）
  ④ 模型里有没有未赋材质的面（`no_material`）

为什么要这么做：`$cdmaterials` 与材质名在**编译时就被烘进 MDL**，事后改文件夹必须重编译，
所以"引擎到底去哪儿找、找什么名字"只有 MDL 说了算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import naming, vmt

# 会指向贴图的参数（值是不带扩展名、相对 materials/ 的路径）
TEXTURE_PARAMS = ("$basetexture", "$bumpmap", "$phongexponenttexture", "$envmapmask",
                  "$detail", "$lightwarptexture", "$compress", "$normalmap",
                  "$basealphaenvmapmask")


@dataclass
class Finding:
    level: str          # "拒绝" / "警告" / "提示"
    message: str
    detail: str = ""

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}" + (f"（{self.detail}）" if self.detail else "")


@dataclass
class ModelReport:
    model: str
    cdmaterials: list = field(default_factory=list)
    textures: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    vmt_checked: int = 0
    vtf_checked: int = 0

    @property
    def ok(self) -> bool:
        return not any(f.level == "拒绝" for f in self.findings)


def _case_lookup(materials_root: Path, rel: str):
    """大小写敏感地找一个 materials 下的相对路径。

    返回 ("ok"|"case"|"missing", 说明)。Windows 不敏感，所以必须逐级列目录比对。
    """
    state = naming.check_path_case(materials_root, rel)
    if state == "":
        return "ok", ""
    if state == "missing":
        return "missing", ""
    return "case", state


def validate_model(model_path: str | Path, materials_root: str | Path) -> ModelReport:
    model_path = Path(model_path)
    materials_root = Path(materials_root)
    mdl = naming.read_mdl(model_path)
    rep = ModelReport(model=str(model_path), cdmaterials=mdl.cdmaterials, textures=mdl.textures)

    if mdl.version != 49:
        rep.findings.append(Finding("提示", f"这个模型是 MDL v{mdl.version}，本项目按 L4D2 的 v49 验的"))
    if len(mdl.cdmaterials) > 1:
        rep.findings.append(Finding("警告", f"模型里有 {len(mdl.cdmaterials)} 条 $cdmaterials；"
                                            "引擎只用第一条来拼路径，其余要确认是不是多余的"))
    if not mdl.cdmaterials:
        rep.findings.append(Finding("拒绝", "MDL 里没有 $cdmaterials —— 引擎不知道去哪儿找材质"))

    for tex in mdl.textures:
        if tex.lower() == "no_material":
            rep.findings.append(Finding("警告", "模型里有未赋材质的面（no_material）",
                                        "这些面在游戏里会是紫色/黑白格子，回 Blender 补材质再重编译"))

    cdm = mdl.cdmaterials[0] if mdl.cdmaterials else ""
    rel_dir = cdm.replace("\\", "/").strip("/")

    for tex in mdl.textures:
        if tex.lower() == "no_material":
            continue
        rel_vmt = f"{rel_dir}/{tex}.vmt" if rel_dir else f"{tex}.vmt"
        state, note = _case_lookup(materials_root, rel_vmt)
        if state == "missing":
            rep.findings.append(Finding("拒绝", f"引擎会找的 VMT 不存在：materials/{rel_vmt}",
                                        "这就是「游戏里材质丢失」最常见的原因"))
            continue
        if state == "case":
            rep.findings.append(Finding("警告",
                                        f"大小写与 MDL 不一致：materials/{rel_vmt}",
                                        f"{note} —— Windows 能跑，Linux 服务器会挂"))
        rep.vmt_checked += 1
        _check_vmt_textures(materials_root, materials_root / rel_vmt, rep)
    return rep


def _check_vmt_textures(materials_root: Path, vmt_path: Path, rep: ModelReport) -> None:
    try:
        text = vmt_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        rep.findings.append(Finding("警告", f"读不了 {vmt_path.name}", e.strerror or ""))
        return

    if vmt.is_patch(text):
        inc = vmt.includes(text)
        rep.findings.append(Finding("提示", f"{vmt_path.name} 是 patch 材质（include {inc}）",
                                    "本工具不展开 include，参数检查可能不完整"))
    params = vmt.parse(text)
    if not params:
        rep.findings.append(Finding("警告", f"{vmt_path.name} 里没读到任何参数", "文件可能是空的或格式不对"))
        return

    for key in TEXTURE_PARAMS:
        value = params.get(key)
        if not value:
            continue
        if value.startswith("$") or value.startswith("env_") or value.startswith("effects/"):
            continue                                    # env_cubemap / 引擎内置图，不查
        rel = value.replace("\\", "/").strip("/")
        # 值可能是 `<路径>/<名字>`，也可能是不带目录的裸名（裸名同样相对 materials/ 根）
        for ext in (".vtf",):
            state, note = _case_lookup(materials_root, rel + ext)
            if state == "missing":
                rep.findings.append(Finding("拒绝", f"{vmt_path.name} 的 {key} 指向的贴图不存在："
                                                    f"materials/{rel}{ext}", "VMT 在、贴图不在，引擎会画成粉黑格子"))
            elif state == "case":
                rep.findings.append(Finding("警告", f"{vmt_path.name} 的 {key} 大小写不符："
                                                    f"materials/{rel}{ext}", note))
            else:
                rep.vtf_checked += 1

    if "$phong" in params and not any(k in params for k in
                                      ("$phongexponenttexture", "$phongexponent", "$phongexponentfactor")):
        rep.findings.append(Finding("提示", f"{vmt_path.name} 开了 $phong 但没有指数来源",
                                    "会退回默认指数 5"))
    if "$phongalbedotint" in params and "$phongexponenttexture" not in params:
        rep.findings.append(Finding("警告", f"{vmt_path.name} 写了 $phongalbedotint 但没有 "
                                            "$phongexponenttexture", "官方文档：必须有成对的指数贴图才生效"))
    if "$basemapalphaphongmask" in params and "$bumpmap" in params and "$envmap" in params:
        rep.findings.append(Finding("提示", f"{vmt_path.name}：底色 alpha 同时当 phong 遮罩与反射遮罩",
                                    "这是官方武器路线，确认 alpha 画的是高光遮罩"))
