"""参数模型：三层继承 + 每项参数的"来源"追踪（实施计划 §5.7）。

用户拍板的三层（原话见实施计划）：
    ① 全局默认（整机一份）      ← A 类「换算规则」：roughness→exponent 曲线、AO 混合比例、
                                  遮罩公式、色彩空间策略
    ② 预设档（按类别，可存多套） ← B 类「观感与身份」：$phongboost、$phongfresnelranges、
                                  $envmap 开关、遮罩载体、属性面板默认值
    ③ 素材级覆盖（每套可为空）   ← 任何参数都能单独覆盖；**但曲线不能**（曲线只到预设档这一层）

**生效顺序：就近优先（素材级 > 预设档 > 全局默认）。**

为什么要连"来源"一起返回：用户是"没用过类似工具的普通人"，如果不告诉他
"这个值是你自己改的 / 还是预设给的"，他会陷进"我到底改没改过这个"的迷雾里
——这比参数本身更容易劝退。所以 `resolve()` 的返回值里每一项都带来源标签。

文件落点（与实施计划一致）：
    config.json       全局默认（整机一份）
    presets/<名>.json 预设档（可存多套）
    phong_input.json  每套素材：输入映射 + 用了哪个预设 + 覆盖项 + 每项来源
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import phong

CONFIG_NAME = "config.json"
PRESET_DIR_NAME = "presets"
GUI_PREFS_NAME = "gui.json"
# 参数来源的**层**（10 片：原来这三个是中文**字面量**，界面直接显示它们 —— 于是英文界面的
# 「来源」列蹦出中文（09 验收挂出来的问题）。现在 core 内部只保留**层标识**（language-neutral），
# 界面按它走 i18n（`src.global` / `src.preset` / `src.override`），中文措辞**只在一个地方生成** → `source_label()`。
SOURCE_KIND_GLOBAL = "global"
SOURCE_KIND_PRESET = "preset"
SOURCE_KIND_OVERRIDE = "override"


def source_label(kind: str, preset_name: str = "") -> str:
    """层标识 → **中文报告口径**（`phong_input.json` / 日志 / CLI 用词；界面不用它，见上）。"""
    if kind == SOURCE_KIND_PRESET:
        return f"预设：{preset_name}" if preset_name else "预设"
    if kind == SOURCE_KIND_OVERRIDE:
        return "你改过"
    return "全局默认"


def default_config_root() -> Path:
    """全局默认与预设放哪儿 —— **整机一份**，所以放用户配置目录而不是程序目录
    （打包成 exe 后程序目录通常是只读的）。

        Windows : %APPDATA%\\PBR2Phong
        其他     : ~/.config/PBR2Phong

    环境变量 `PBR2PHONG_HOME` 可覆盖（开发/测试用）。
    """
    env = os.environ.get("PBR2PHONG_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "PBR2Phong"
    return Path.home() / ".config" / "PBR2Phong"


def ensure_config_root(root: str | Path | None = None) -> Path:
    """拿到配置目录；**第一次运行时把内置默认与五套预设导出过去**（用户能直接改）。

    ⚠️ **配置记忆是"锦上添花"，建不出来也绝不能影响主功能**：只读的 %APPDATA%、
    漫游配置、被安全软件锁住…… 这些情况下要安静地退回"没有记忆"，
    而不是让程序一启动就崩（这个坑是本地沙箱不允许写 %APPDATA% 时当场撞出来的）。
    """
    root = Path(root) if root else default_config_root()
    try:
        if not (root / CONFIG_NAME).is_file() or not (root / PRESET_DIR_NAME).is_dir():
            write_default_config(root)
    except OSError:
        pass
    return root


def load_gui_prefs(root: str | Path) -> dict:
    """读界面偏好（语言 / 上次文件夹 / 勾选状态 / 窗口大小）。没有就返回 {}。"""
    p = Path(root) / GUI_PREFS_NAME
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_gui_prefs(root: str | Path, prefs: dict) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / GUI_PREFS_NAME
    p.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

# ---------------------------------------------------------------- 外部程序：HLMV（模型浏览器）

HLMV_EXE_NAME = "hlmv.exe"


def default_hlmv_path(l4d2_root: str | Path) -> str:
    """L4D2 自带的 HLMV 默认在 `<L4D2>\\bin\\hlmv.exe`（施工单 `_task/02-HLMV按钮.md` §3）。"""
    return str(Path(l4d2_root) / "bin" / HLMV_EXE_NAME)


def resolve_hlmv_path(configured: str, l4d2_root: str | Path) -> tuple:
    """决定"这次用哪个 HLMV"：返回 `(exe 路径 or ""，来源种类)`。

    四种来源（界面按种类给对应的人话，别写 `FileNotFoundError`）：
      · `"configured"`        —— 用户配了、文件也在 → 用他指定的
      · `"fallback_default"`  —— 用户配了但文件不在 → 退回默认位置（默认在）
      · `"default"`           —— 没配 → 用默认位置（默认在）
      · `"missing"`           —— 默认也不在 → 路径返回空串，界面给"它一般在 …，请指定"的人话
    """
    default = default_hlmv_path(l4d2_root)
    configured = (configured or "").strip()
    if configured:
        if Path(configured).is_file():
            return configured, "configured"
        if Path(default).is_file():
            return default, "fallback_default"
        return "", "missing"
    if Path(default).is_file():
        return default, "default"
    return "", "missing"


# 曲线类参数：**只能在全局默认与预设档里改，素材级覆盖不许动**
CURVE_KEYS = ("curve.roughness_to_exponent", "curve.mask_formula")

# A 类：换算规则（全局默认这一层）
GLOBAL_DEFAULTS = {
    "curve.roughness_to_exponent": "linear_1_150",   # 依据 §0.6 #12 的离线证据
    "curve.mask_formula": "one_minus_r_cubed_x1.1",
    "curve.curve_points": [],                        # 预设档可以自带一条曲线（控制点）
    "curve.sharpness_gain": 1.0,                     # 界面上那根「高光锐度」滑杆（1.0 = 不干预）
    # ---- 2026-09-27 新增（07 单 S4）：**默认值 = 不干预**，三层继承与指纹自动带它们 ----
    "curve.roughness_offset": 0.0,                   # 「粗糙度整体偏移」r' = clamp(r + off)
    "curve.metal_tint": 1.0,                         # 「金属染色强度」（exp 的 G 通道整体缩放）
    "curve.envmap_gain": 1.0,                        # 笔刷「反射强度」（envmap 遮罩整体增益）
    "basecolor.ao_amount": 0.5,
    "basecolor.darken_metal": False,                 # False = 方案 A 不压黑
    "normal.flip_green": True,                       # Blender(GL) → Source(DX)
    "colorspace.exponent": "linear",                 # 指数贴图是线性数据
    "colorspace.basecolor": "srgb",
    "vtf.version": "7.4",
    # ---- 2026-09-27 新增（08 单 S5）：材质属性改「必填」----
    # 用户 2026-09-27 原话："材质属性应该是必填"。做法**不是**静默兜底，而是：
    # ① 给一个**看得见的**默认值（界面上那个下拉会显示 `default`）；
    # ② 预设档还可以覆盖它（笔刷 9 档各自带着自己的 $surfaceprop，见 `phong.PRESETS`）。
    # → 效果 = 产出的 `.vmt` 里**永远有** $surfaceprop，而且用户看得见当前用的是哪个。
    "vmt.$surfaceprop": "default",
    # ---- 2026-09-27 新增（09 单）：材质本身要透明（alpha 裁剪）----
    # 树叶 / 铁网 / 栅栏 / 贴纸这类靠 alpha 抠形状的材质。打开后：
    # 遮罩强制走法线 alpha（不许覆盖底色 alpha）+ VMT 自动写 `$alphatest 1`。
    # 默认 False = 老路径逐位不变（`test_neutral_params.py` 的哈希锁盯着）。
    "alpha.cutout": False,
}


def _flatten_preset(name: str) -> dict:
    """把 `phong.PRESETS` 里的一个预设展平成同一种键风格（vmt 项加 `vmt.` 前缀）。"""
    p = phong.PRESETS[name]
    out = {"mask_carrier": p["mask_carrier"], "use_exponent_texture": bool(p["use_exponent_texture"])}
    for k, v in p["vmt"].items():
        out[f"vmt.{k}"] = v
    # 2026-09-27（08 单）：有的档要用别的**着色器**（角色-眼睛 = EyeRefract，不是 VLG）。
    # ⚠️ 它不是一个 VMT 参数，是"用哪个着色器块"——所以单独一个键，别塞进 vmt.* 里。
    if p.get("shader"):
        out["shader.name"] = p["shader"]
    # 2026-09-27（09 单）：这两项也是"预设能定的策略"，不是 VMT 参数
    if "use_mask" in p:
        out["use_mask"] = bool(p["use_mask"])
    if "alpha_cutout" in p:
        out["alpha.cutout"] = bool(p["alpha_cutout"])
    return out


def builtin_presets() -> dict:
    return {name: _flatten_preset(name) for name in phong.PRESETS}


@dataclass
class Resolved:
    values: dict = field(default_factory=dict)
    # ⚠️ `sources` 存的是**层标识**（global / preset / override），**不是**给人看的字面量 ——
    #    要中文措辞用 `source_of()`，要整份字典写进 `phong_input.json` 用 `sources_report()`。
    sources: dict = field(default_factory=dict)
    preset_name: str = ""
    override_keys: list = field(default_factory=list)

    def source_kind(self, key: str) -> str:
        return self.sources.get(key, SOURCE_KIND_GLOBAL)

    def source_of(self, key: str) -> str:
        """中文报告口径（既有断言与 CLI 都按这个来，10 片语义不变）。"""
        return source_label(self.source_kind(key), self.preset_name)

    def sources_report(self) -> dict:
        """key → 中文来源标签（写 `phong_input.json` 的那一份）。"""
        return {k: source_label(v, self.preset_name) for k, v in self.sources.items()}

    def report_line(self) -> str:
        """给报告用的一句话：『这套 = 武器预设 + 覆盖了 N 个参数』"""
        base = f"{self.preset_name}预设" if self.preset_name else "全局默认"
        n = len(self.override_keys)
        return f"这套 = {base}" + (f" + 覆盖了 {n} 个参数" if n else "")

    def vmt_params(self) -> list:
        """挑出要写进 .vmt 的键值（按 `vmt.` 前缀）。"""
        return [(k[len("vmt."):], v) for k, v in self.values.items() if k.startswith("vmt.")]


def resolve(preset_name: str = "", overrides: dict | None = None,
            global_values: dict | None = None, presets: dict | None = None) -> Resolved:
    """三层继承：素材级 > 预设档 > 全局默认。返回带来源标签的结果。"""
    glob = dict(GLOBAL_DEFAULTS)
    glob.update(global_values or {})
    table = builtin_presets()
    table.update(presets or {})

    res = Resolved(preset_name=preset_name)
    for k, v in glob.items():
        res.values[k] = v
        res.sources[k] = SOURCE_KIND_GLOBAL

    if preset_name:
        if preset_name not in table:
            raise KeyError(f"没有这个预设：{preset_name}（现有：{'、'.join(sorted(table))}）")
        for k, v in table[preset_name].items():
            res.values[k] = v
            res.sources[k] = SOURCE_KIND_PRESET

    for k, v in (overrides or {}).items():
        if k in CURVE_KEYS:
            raise ValueError(f"曲线参数 `{k}` 不允许在素材级覆盖（曲线只到预设档这一层）")
        res.values[k] = v
        res.sources[k] = SOURCE_KIND_OVERRIDE
        res.override_keys.append(k)
    return res


# ---------------------------------------------------------------- 文件落点

def load_global(root: str | Path) -> dict:
    """读 `config.json`（没有或坏了就返回 {}，不抛）。"""
    p = Path(root) / CONFIG_NAME
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data.get("参数", {}) if isinstance(data, dict) else {}


def save_global(root: str | Path, values: dict, note: str = "") -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / CONFIG_NAME
    p.write_text(json.dumps({"说明": note or "PBR2Phong 全局默认参数",
                             "参数": values}, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_presets(root: str | Path) -> dict:
    """读 `presets/*.json`。每个文件形如 {"名称": …, "说明": …, "参数": {...}}。"""
    d = Path(root) / PRESET_DIR_NAME
    out = {}
    if not d.is_dir():
        return out
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("参数"), dict):
            out[data.get("名称") or f.stem] = data["参数"]
    return out


def preset_filename(name: str) -> str:
    """预设名 → 安全的文件名。

    ⚠️ 预设名里可能有 `/`（如「玻璃/投掷物」），直接当文件名会当成子目录 → 写盘报错。
    真正的名字仍然完整存在文件里的 `名称` 字段，文件名只是它的"代号"。
    """
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", str(name).strip()) or "preset"
    return safe + ".json"


def save_preset(root: str | Path, name: str, values: dict, desc: str = "") -> Path:
    d = Path(root) / PRESET_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    p = d / preset_filename(name)
    p.write_text(json.dumps({"名称": name, "说明": desc, "参数": values},
                            ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def write_default_config(root: str | Path) -> Path:
    """把内置预设与全局默认导出一份到磁盘，方便用户/后续 GUI 直接改。

    ⚠️ 写不进去时**只跳过这一份文件**，不往上抛（见 `ensure_config_root` 的说明）。
    """
    root = Path(root)
    path = None
    for name, vals in [("", None)] + [(n, v) for n, v in builtin_presets().items()]:
        try:
            if name == "":
                path = save_global(root, GLOBAL_DEFAULTS,
                                   note="PBR2Phong 全局默认（A 类换算规则）。改这里会影响所有素材。")
            else:
                save_preset(root, name, vals, phong.PRESETS[name]["desc"])
        except OSError:
            continue
    return path or (root / CONFIG_NAME)
