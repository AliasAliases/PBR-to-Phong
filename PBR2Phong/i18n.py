"""双语文案表 —— **必须先于任何界面代码写**（实施计划 §3 阶段 5 第一条）。

用户定的规矩（原话）："我觉得能用这个程序的基本都是看 pbr 流程的，我觉得应该用直译加解释
（中英文都得有解释）" → 所以每个参数都是 **直译标签 + 一句人话解释**，而且解释**常驻界面**
（不是悬浮提示），中英**都要有解释**。

技术术语（$phongboost、exponent、roughness）**不直接给用户看**，只在「④ 关于 → 术语表」出现。

实现上故意用**纯 Python 字典**而不是 Qt 的 .ts/.qm 工具链：文案只有几十条，
上那套工具链纯属负担（实施计划 §5 决策）。

本模块不 import Qt —— CLI 也能用它输出双语报告。
"""

from __future__ import annotations

import json
import locale
import os

LANG_SYSTEM = "system"
LANG_ZH = "zh"
LANG_EN = "en"
LANG_CHOICES = (LANG_SYSTEM, LANG_ZH, LANG_EN)

LANGUAGE_NAMES = {
    LANG_SYSTEM: {"zh": "跟随系统", "en": "Follow system"},
    LANG_ZH: {"zh": "简体中文", "en": "简体中文"},
    LANG_EN: {"zh": "English", "en": "English"},
}


def system_language() -> str:
    """跟随系统：中文系统 → zh，其余 → en。

    ⚠️ 环境变量 **`PBR2PHONG_LANG`**（`zh` / `en`）**优先于系统探测** —— 给 CI 与自动化测试用：
    GitHub 的 runner 是**英文系统**，而套件里有不少断言是按**中文界面**写的（历史原因）→
    测试跑法（`tests/run_all.py`）会把它定成 `zh`，否则 CI 上一片红。用户手动设它也有效。
    """
    forced = (os.environ.get("PBR2PHONG_LANG") or "").strip().lower()
    if forced in (LANG_ZH, LANG_EN):
        return forced
    for probe in (locale.getlocale()[0], locale.getdefaultlocale()[0] if hasattr(locale, "getdefaultlocale") else None,
                  os.environ.get("LANG")):
        if probe and str(probe).lower().startswith("zh"):
            return LANG_ZH
    return LANG_EN


def resolve_language(pref: str = LANG_SYSTEM) -> str:
    return system_language() if pref == LANG_SYSTEM else (pref if pref in (LANG_ZH, LANG_EN) else LANG_EN)


def t(key: str, lang: str = LANG_ZH, **fmt) -> str:
    """取一条文案。找不到就原样返回 key（方便开发时发现缺文案）。"""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(LANG_EN) or key
    return text.format(**fmt) if fmt else text


# ---- 素材体检警告：**码 + 参数**（12 单）--------------------------------------
# ⚠️ 12 单起，警告**不是句子**：`core` 只出 `{"code": ..., "args": {...}}`（`core/pack.py::warn()`），
#    人话一律在这一层渲染（core 不产出给人看的字面量）。写进 `phong_input.json` 的也是**码**。
# ⚠️ **中文文案与改造前逐字一致**（判据 4）：每条的中文就是 12 单动手前那一句，
#    由 `tests/test_warnings.py` 的锚点表逐条比对锁住 —— 改文案要先改那张表并说明。
# ⚠️ 带 `{…}` 的是参数位（`args` 里给原始值，**不许在 core 里拼句子**）。
WARNING_TEXT = {
    # —— 缺图（core/pack.py）——
    "no_roughness_map": {
        "zh": "没有粗糙度贴图 → 按「全粗糙」处理（高光会很大很糊）",
        "en": "No roughness map → treating everything as fully rough (highlights will be big and "
              "washed out)"},
    "no_metallic_map": {
        "zh": "没有金属度贴图 → 按「全非金属」处理（高光保持白色）",
        "en": "No metalness map → treating everything as non-metal (highlights stay white)"},
    "no_ao_map": {
        "zh": "没有 AO 贴图 → 跳过 AO 相关步骤",
        "en": "No AO map → skipping the AO steps"},
    "no_normal_map": {
        "zh": "没有法线贴图 → 不输出法线（引擎会用平坦法线）",
        "en": "No normal map → no normal is written (the engine will use a flat normal)"},
    # —— 贴图没信息量（13-A，现在走码）——
    "roughness_is_constant": {
        "zh": "粗糙度贴图整张都是同一个值 → 处处一样光，等于没有粗糙度细节，回去看看烘焙是不是没把粗糙度写进去",
        "en": "The roughness map is one single value everywhere — uniform highlights, no roughness "
              "detail at all; check whether the bake actually wrote roughness"},
    "roughness_has_two_values": {
        "zh": "粗糙度贴图只有两个值 → 高光只有两档（不是过渡），这类图多半是烘焙或导出时被压成了黑白",
        "en": "The roughness map has only two values — highlights come in just two steps; this kind "
              "of map is usually a bake/export that got squashed to black-and-white"},
    "metallic_all_zero": {
        "zh": "金属度贴图整张都是 0（全非金属）→ 高光保持白色；如果你本来就要做金属，回去看看烘焙是不是没把金属度写进去",
        "en": "The metalness map is 0 everywhere (fully non-metal) — highlights stay white; if you "
              "did want metal, check whether the bake wrote metalness at all"},
    "metallic_all_one": {
        "zh": "金属度贴图整张都是 255（全金属）→ 整块料都会按金属上色，非金属的地方也会带金属染色",
        "en": "The metalness map is 255 everywhere (fully metal) — the whole material gets metal "
              "tinting, including the parts that are not metal"},
    # —— 底色 / 法线 / 遮罩（core/pack.py）——
    "darken_metal_route": {
        "zh": "当前用的是「压黑派」（金属区被压暗）——这是 albedotint 不生效时的退路",
        "en": "Using the darken-metal route (metal areas are darkened) — the fallback for when "
              "albedotint does not take effect"},
    "normal_is_flat": {
        "zh": "法线贴图是平的（R/G 几乎都是 128）→ 模型上不会有任何凹凸，回去看看烘焙是不是没勾上法线",
        "en": "The normal map is flat (R/G are almost all 128) → there will be no bumps at all on "
              "the model; check whether the bake had normals enabled"},
    "cutout_needs_normal": {
        "zh": "要透明就必须有法线图：这套素材没有法线贴图 → 这次**不出高光遮罩**"
              "（真塞进底色 alpha 的话，会把底色的透明整个吃掉）",
        "en": "Cut-out transparency requires a normal map: this set has none → **no phong mask this "
              "time** (putting it into the base colour alpha would eat the transparency)"},
    "mask_carrier_normal_missing": {
        "zh": "遮罩载体选了法线图，但没有法线贴图 → 遮罩只好塞进底色 alpha",
        "en": "The mask carrier is set to the normal map but there is no normal map → the mask goes "
              "into the base colour alpha instead"},
    "basecolor_alpha_overridden": {
        "zh": "你的底色带透明，但高光遮罩会覆盖它 —— 要透明请打开「这个材质要透明」",
        "en": "Your base colour has transparency, but the phong mask will overwrite it — turn on "
              "\"This material needs cut-out transparency\" if you want it"},
    "no_alpha_but_cutout": {
        "zh": "这套素材的底色没有透明区域 —— 勾了也不会裁掉任何东西。",
        "en": "This set's base colour has no transparent area — turning it on cuts nothing away."},
    "mask_size_mismatch": {
        "zh": "遮罩与宿主图尺寸不一致 → 两边都放大到 {w}×{h}（只放大、不缩小）",
        "en": "Mask and carrier sizes differ → both are scaled up to {w}×{h} (only up, never down)"},
    # —— 笔刷路线（core/pipeline.py）——
    "brush_ao_not_baked": {
        "zh": "笔刷路线：AO 贴图**故意不烘进底色** —— 平铺贴图烘进 AO/大尺度明暗会跟着重复、"
              "大老远就看出规律；笔刷的明暗 100% 交给 lightmap（Hammer笔刷路线.md §3①）",
        "en": "Brush route: the AO map is **deliberately not baked into the base colour** — tiled "
              "textures would repeat the AO/large-scale shading; brush shading is 100% lightmap"},
    "brush_dropped_envmap_params": {
        "zh": "笔刷路线：跳过预设里的 {n} 个 $envmap* 参数（笔刷的 envmap 由「反射遮罩」开关决定）",
        "en": "Brush route: dropped {n} $envmap* parameter(s) from the preset (the brush envmap is "
              "decided by the \"reflection mask\" switch)"},
    "brush_mask_carrier_key": {
        "zh": "笔刷遮罩落在 {carrier} 的 alpha → VMT 自动写 {key} 1",
        "en": "The brush mask lands in the {carrier} alpha → the VMT gets {key} 1 automatically"},
    "brush_forbidden_keys": {
        "zh": "⚠️ 笔刷 VMT 里出现了禁令键：{keys}",
        "en": "⚠️ Forbidden keys showed up in the brush VMT: {keys}"},
    "brush_ignores_model_names": {
        "zh": "笔刷路线忽略模型里的材质名（笔刷材质名 = 贴图基名，在 Hammer 材质浏览器里直接选）",
        "en": "The brush route ignores the material names in the model (brush material name = "
              "texture base name, picked directly in Hammer's material browser)"},
    # —— 其它着色器（13-E 眼睛）——
    "eye_eyerefract_written": {
        "zh": "眼睛档（EyeRefract）：按官方那套键写，不出 Phong/底色——眼睛要的是虹膜图 + 眼睛 AO",
        "en": "Eyes preset (EyeRefract): written with the official key set, no Phong/base colour — "
              "eyes need the iris map + eye AO"},
    "other_shader_kept_base_only": {
        "zh": "这一档用的是 {shader} 着色器（不是 VertexLitGeneric）→ 只写底色与预设带的参数；"
              "眼睛那套 $Iris 贴图本版不做",
        "en": "This preset uses the {shader} shader (not VertexLitGeneric) → only the base colour "
              "and the preset's own parameters are written; the $Iris eye textures are not made here"},
    # —— 透明（09 单）——
    "cutout_replaced_translucent": {
        "zh": "要透明：已把 $translucent 换成 $alphatest（半透明混合会让树叶这类边缘发黑）",
        "en": "Cut-out requested: $translucent was replaced with $alphatest (alpha blending makes "
              "leaf edges go black)"},
    "cutout_wrote_alphatest": {
        "zh": "要透明 → 自动写 $alphatest 1（二值裁剪；树叶 / 铁网这类不要用 $translucent）",
        "en": "Cut-out requested → $alphatest 1 is written (binary cut-out; leaves/wire mesh should "
              "not use $translucent)"},
    "basemapalphaphongmask_removed": {
        "zh": "遮罩实际落在法线 alpha（不是底色）→ 已去掉预设里的 $basemapalphaphongmask"
              "（留着它引擎会去读底色 alpha，把遮罩指错地方）",
        "en": "The mask actually lands in the normal alpha (not the base colour) → "
              "$basemapalphaphongmask was removed (keeping it makes the engine read the base colour "
              "alpha and aim the mask at the wrong place)"},
    "basemapalphaphongmask_added": {
        "zh": "遮罩在底色 alpha → 自动补上 $basemapalphaphongmask 1（否则引擎不会去读它）",
        "en": "The mask is in the base colour alpha → $basemapalphaphongmask 1 is added (otherwise "
              "the engine will not read it)"},
    # —— 部署（13-C，现在走码）——
    "deploy_skipped_conflicts": {
        "zh": "materials 里有同名文件、你没让覆盖 → 这次只出了产物，没有部署",
        "en": "materials already has files with these names and you chose not to overwrite — "
              "products were written, nothing was deployed"},
}

# ⚠️ **过渡期兼容**：12 单之前写下的 `phong_input.json` 里存的是**中文整句** →
#    读旧记录时仍然按这张表换成英文（新记录不会再产生这些句子）。
WARNINGS_EN = {
    "这套素材的底色没有透明区域 —— 勾了也不会裁掉任何东西。":
        "This set's base colour has no transparent area — turning it on cuts nothing away.",
    "materials 里有同名文件、你没让覆盖 → 这次只出了产物，没有部署":
        "materials already has files with these names and you chose not to overwrite — "
        "products were written, nothing was deployed",
    "粗糙度贴图整张都是同一个值 → 处处一样光，等于没有粗糙度细节，回去看看烘焙是不是没把粗糙度写进去":
        "The roughness map is one single value everywhere — uniform highlights, no roughness "
        "detail at all; check whether the bake actually wrote roughness",
    "粗糙度贴图只有两个值 → 高光只有两档（不是过渡），这类图多半是烘焙或导出时被压成了黑白":
        "The roughness map has only two values — highlights come in just two steps; this kind of "
        "map is usually a bake/export that got squashed to black-and-white",
    "金属度贴图整张都是 0（全非金属）→ 高光保持白色；如果你本来就要做金属，回去看看烘焙是不是没把金属度写进去":
        "The metalness map is 0 everywhere (fully non-metal) — highlights stay white; if you did "
        "want metal, check whether the bake wrote metalness at all",
    "金属度贴图整张都是 255（全金属）→ 整块料都会按金属上色，非金属的地方也会带金属染色":
        "The metalness map is 255 everywhere (fully metal) — the whole material gets metal tinting, "
        "including the parts that are not metal",
}


def warning(w, lang: str = LANG_ZH) -> str:
    """一条体检警告 → 当前语言的说法。

    · **新格式**（12 单起）：`{"code": ..., "args": {...}}` → 查 `WARNING_TEXT` 按语言渲染；
      码认不出来就原样给码（**不假装翻译过**）。
    · **旧格式**（历史 `phong_input.json` 里的中文整句）：中文原样、英文查 `WARNINGS_EN`。
    """
    if isinstance(w, dict):
        code = str(w.get("code") or "")
        args = w.get("args") or {}
        entry = WARNING_TEXT.get(code)
        if not entry:
            return code
        text = entry.get(lang) or entry.get(LANG_ZH) or code
        try:
            return text.format(**args)
        except (KeyError, IndexError):
            return text
    text = str(w)
    return WARNINGS_EN.get(text, text) if lang == LANG_EN else text


def render_warnings(warnings, lang: str = LANG_ZH) -> list:
    """一串警告 → 当前语言的句子（给界面 / 日志用）。"""
    return [warning(w, lang) for w in (warnings or [])]


def readable_log_text(record: dict, lang: str = LANG_ZH, vmt_text: str = "") -> str:
    """把 core 写的记录变成**用户可读**的日志（14-A）。

    ⚠️ 守铁律：**core 只写码**（`log.txt` / `phong_input.json` 里的警告是 `{"code":…}`）——
    "可读化"这一步放在 **UI 层**：这里把记录里的 `警告` 换成当前语言的句子，再拼上 .vmt
    （与 core 写的 `log.txt` 同构，只是那一段不再是一串裸 `"code":`）。
    """
    rec = dict(record or {})
    rec["警告"] = render_warnings(record.get("警告"), lang)
    return json.dumps(rec, ensure_ascii=False, indent=2) + "\n\n--- .vmt ---\n" + vmt_text


# 13-F：内置 21 档预设的**英文显示名**。
#   ⚠️ 只翻**内置**这 21 档；**用户自存的档名一律原样显示**（那是他的数据，不能替他翻译）。
#   ⚠️ 预设名同时是**持久化数据**（`phong_input.json` 的「预设」字段、`presets/*.json` 的「名称」、
#      `phong.PRESETS` 的字典键）→ 所以**键永远是中文原名**，这里只管"显示成什么"。
PRESET_NAMES_EN = {
    "角色-身体": "Character · Body", "角色-头": "Character · Head",
    "角色-眼睛": "Character · Eyes",
    "武器-第一人称": "Weapon · First-person", "武器-世界掉落": "Weapon · World model",
    "感染者": "Infected", "道具": "Prop", "载具": "Vehicle", "植被": "Foliage",
    "招牌·发光": "Sign · Emissive", "投掷物·玻璃": "Throwable · Glass",
    "混凝土·沥青": "Concrete · Asphalt", "金属": "Metal", "木": "Wood", "砖": "Brick",
    "石膏墙": "Plaster wall", "瓷砖": "Tile", "玻璃·窗户": "Glass · Window",
    "自然土地": "Natural ground", "建筑·装饰条": "Trim · Moulding", "贴花": "Decal",
}


def preset_display(name: str, lang: str = LANG_ZH) -> str:
    """预设名的**显示形态**：内置档在英文下给英文名；自存/自定义档名**原样返回**。"""
    if lang != LANG_EN:
        return name
    return PRESET_NAMES_EN.get(name, name)


def preset_is_builtin(name: str) -> bool:
    """内置 21 档之一？（用来在「来源」列区分"内置档 / 自存档"）"""
    return name in PRESET_NAMES_EN


# ---------------------------------------------------------------- 界面骨架

STRINGS = {
    "app.title": {"zh": "PBR → Phong", "en": "PBR → Phong"},
    "app.subtitle": {
        "zh": "把 PBR（粗糙度 / 金属度）贴图转成 L4D2 能用的 Phong 贴图 + VMT + VTF",
        "en": "Turn PBR (roughness / metallic) textures into L4D2-ready Phong textures + VMT + VTF"},
    "app.window_title": {"zh": "PBR → Phong", "en": "PBR → Phong"},

    "tab.convert": {"zh": "① 转换", "en": "① Convert"},
    "tab.about": {"zh": "⑤ 关于", "en": "⑤ About"},

    # 状态栏（常驻所有标签页）
    "status.ready": {"zh": "就绪", "en": "Ready"},
    "status.done": {"zh": "完成：成功 {ok} / 跳过 {skip} / 失败 {fail}",
                    "en": "Done: {ok} ok / {skip} skipped / {fail} failed"},
    "btn.start": {"zh": "开始转换", "en": "Start"},
    "btn.cancel": {"zh": "取消", "en": "Cancel"},

    # ① 转换页
    "import.title": {"zh": "导入素材", "en": "Import textures"},
    "drop.hint": {"zh": "把烘焙好的素材文件夹拖到这里",
                  "en": "Drop a baked texture folder here"},
    "btn.choose_folder": {"zh": "选择文件夹…", "en": "Choose folder…"},
    "label.recognized": {"zh": "已识别 {n} 套素材", "en": "{n} texture set(s) recognised"},
    "label.recognized_empty": {"zh": "还没有选择素材", "en": "No folder selected yet"},
    "label.output_choose": {"zh": "输出到：<点击选择>", "en": "Output to: <click to choose>"},
    "table.material": {"zh": "素材", "en": "Material"},
    "table.status": {"zh": "状态", "en": "Status"},
    "table.progress": {"zh": "进度", "en": "Progress"},
    "table.note": {"zh": "说明", "en": "Note"},

    # ② 结果对比页（v1 占位）

    # ③ 参数设置页
    "settings.preset": {"zh": "预设", "en": "Preset"},
    "settings.preset_desc": {
        # ⚠️ 这一句是**灰字解释**，长度必须量过（11 片起由 `tests/test_layout.py` ④b 自动锁：
        #    中英 × 两路线 × 两页，判据 = 换行后需要多高 ≤ 实得高度）。旧脚本
        #    `阶段0_实测/diag_desc_width.py` 已删（它量的是没激活的页 = 过期几何，会误报"截断"）。
        "zh": "按素材类别给的默认可调参数；换档会重放材质属性（滑杆曲线不动）。",
        "en": "Per-type defaults; switching preset replays its material attributes; sliders stay put."},
    "settings.mode": {"zh": "其他参数", "en": "Other parameters"},
    "settings.vtfcmd": {"zh": "VTFCmd.exe", "en": "VTFCmd.exe"},
    "settings.vtfcmd_found": {"zh": "已自动找到：{path}", "en": "Auto-detected: {path}"},
    "settings.vtfcmd_missing": {"zh": "没找到 —— 请点「浏览」指定 VTFCmd.exe",
                                "en": "Not found — click Browse and point at VTFCmd.exe"},
    "settings.language_desc": {"zh": "界面语言，默认跟随系统。", "en": "UI language; follows the system by default."},
    "settings.source": {"zh": "来源", "en": "From"},
    # 「来源」列的三个取值（10 片：原来它们硬编码在 `core/settings.py` 里 → 英文界面蹦中文）
    "src.global": {"zh": "全局默认", "en": "Global default"},
    "src.preset": {"zh": "预设：{name}", "en": "From preset: {name}"},
    # 13-F：用户**自存档**的档名 —— 只换标签、名字原样（不能替用户翻译他自己的命名）
    "src.preset_custom": {"zh": "自存档：{name}", "en": "From your preset: {name}"},
    "src.override": {"zh": "你改过", "en": "You changed"},
    "btn.restore_inherit": {"zh": "恢复继承", "en": "Reset to inherited"},
    "btn.save_preset": {"zh": "保存为预设", "en": "Save as preset"},
    "preset.name_prompt": {"zh": "给这套参数起个名字（以后能在预设下拉里选到）",
                           "en": "Name this preset (it will show up in the preset list)"},
    "preset.saved": {"zh": "已保存预设「{name}」", "en": "Saved preset \"{name}\""},
    "settings.saved_preset_desc": {"zh": "你自己存的预设", "en": "Your own preset"},
    "about.no_log": {"zh": "还没有日志 —— 先转换一次吧", "en": "No log yet — run a conversion first"},
    "about.config_dir": {"zh": "配置目录（全局默认 / 预设 / 界面记忆）",
                         "en": "Config folder (defaults / presets / UI memory)"},
    "btn.open_config": {"zh": "打开配置目录", "en": "Open config folder"},
    "settings.param_table": {"zh": "参数", "en": "Parameter"},
    "settings.value_table": {"zh": "当前值", "en": "Value"},
    "settings.steps": {"zh": "快速档位", "en": "Quick steps"},
    "step.柔和": {"zh": "柔和", "en": "Soft"},
    "step.标准": {"zh": "标准", "en": "Standard"},
    "step.锐利": {"zh": "锐利", "en": "Sharp"},
    "step.极锐": {"zh": "极锐", "en": "Very sharp"},

    # 材质属性（v1 的"属性面板"）
    "attr.title": {"zh": "材质属性（必填）", "en": "Material attributes (required)"},
    "attr.hint": {
        "zh": "这些不是调效果，是告诉游戏「这是什么材质」。这一项现在算必填（用户 2026-09-27 拍板），"
              "所以它默认就有一个看得见的值（下面那个下拉里显示的那个），不会静默兜底。",
        "en": "These don't change the look — they tell the game what the material is. "
              "This is required now, so it always shows a visible value (the one in the dropdown "
              "below) instead of silently falling back."},
    "attr.surfaceprop": {"zh": "表面类型 Surface", "en": "Surface type"},
    "attr.surfaceprop_default": {"zh": "(默认)", "en": "(default)"},
    "attr.surfaceprop_desc": {
        "zh": "决定脚步声、子弹命中音效、弹孔和物理手感（写进 VMT 的 $surfaceprop）；不改外观。"
              "世界材质（笔刷）几乎都写它，模型材质官方只有 17% 写 —— 所以要你选。",
        "en": "Drives footstep sounds, bullet impact sounds, decals and physics feel "
              "(written as $surfaceprop); it does not change the look. Nearly all world/brush "
              "materials set it, only 17% of official model materials do — hence the choice."},
    "attr.toggles": {"zh": "常用开关", "en": "Common switches"},
    "attr.cutout": {"zh": "这个材质要透明（树叶 / 铁网 / 栅栏）",
                    "en": "This material needs cut-out transparency (leaves / fences / grates)"},
    "attr.cutout_desc": {
        "zh": "打开后：高光遮罩改走法线 alpha（不再吃掉底色的透明），并自动写 $alphatest 1（二值裁剪，"
              "树叶这类别用 $translucent，边缘会发黑）。⚠️ 这类材质必须有法线图；没有的话宁可不放遮罩，"
              "也不会把透明吃掉。",
        "en": "When on: the highlight mask moves to the normal map's alpha (so it stops eating the "
              "base colour's transparency) and $alphatest 1 is written (binary cut-out — avoid "
              "$translucent here, it makes leaf edges go black). ⚠️ These materials need a normal "
              "map; without one we skip the mask rather than eat your transparency."},
    "settings.vmt_only_hint": {
        "zh": "⚠️ 上面这几根条里，有的只改 .vmt、不改贴图 —— 所以预览不会变，进游戏才看得见"
              "（高光强度、反射染色；其它几根会改变贴图，预览会跟着变）。",
        "en": "⚠️ Some of the sliders above only change the .vmt, not the textures — so the "
              "preview won't move; you'll see it in game (specular strength, reflection tint). "
              "The others do change the textures, and the preview follows them."},
    "attr.custom": {"zh": "自由键值（进阶，写给懂 VMT 的人）",
                    "en": "Custom key-values (advanced, for VMT users)"},
    "attr.key": {"zh": "键", "en": "Key"},
    "attr.value": {"zh": "值", "en": "Value"},
    "btn.add": {"zh": "添加", "en": "Add"},
    "btn.remove": {"zh": "删除选中", "en": "Remove selected"},
    "attr.kv_empty": {"zh": "（还没加任何键值）", "en": "(No key-values added yet)"},
    "curve.reset": {"zh": "重置曲线", "en": "Reset curve"},
    "curve.hint": {"zh": ("在上面那块里上下拖动控制点改映射；双击恢复成直线。"
                          "曲线只在松手时生效。"),
                   "en": ("Drag the control points up/down to reshape the mapping; "
                          "double-click to reset. Applies when you release the mouse.")},
    "attr.kv_need_select": {
        "zh": "先在上面选一行，再点「删除选中」。",
        "en": "Select a row above first, then press Remove selected."},
    "attr.toggle_desc": {
        "zh": "$translucent 半透明 · $alphatest 透明裁切 · $nocull 双面 · $nodecal 不接贴花 · $halflambert 半兰伯特",
        "en": "$translucent (translucent) · $alphatest (alpha cut-out) · $nocull (two-sided) · "
              "$nodecal (no decals) · $halflambert (half lambert)"},


    # 校验模型
    "validate.done": {"zh": "校验完成", "en": "Check finished"},
    "validate.ok": {"zh": "✓ 没发现问题", "en": "✓ No problems found"},
    "validate.problems": {"zh": "发现 {n} 处问题：", "en": "{n} problem(s) found:"},

    # ④ 关于页
    "about.version": {"zh": "版本 {v}", "en": "Version {v}"},
    "about.license": {"zh": "许可证：MIT（打包版内含 Qt / PySide6，遵循 LGPLv3，已附其许可证文本）",
                      "en": "License: MIT (bundled Qt / PySide6 is LGPLv3; its licence text is included)"},
    "about.log": {"zh": "日志文件", "en": "Log file"},
    "btn.open_log": {"zh": "打开日志", "en": "Open log"},
    "about.glossary": {"zh": "术语解释（给想搞懂的进阶用户，普通用户可忽略）",
                       "en": "Glossary (for the curious; safe to ignore)"},
    "about.col_term": {"zh": "术语", "en": "Term"},
    "about.col_explain": {"zh": "人话解释", "en": "Explanation"},

    # 命名（实施计划 §3 阶段 2）
    "naming.title": {"zh": "命名（决定材质路径）", "en": "Naming (decides the material path)"},
    "naming.mode_model": {"zh": "我有编译好的模型（.mdl）", "en": "I have a compiled model (.mdl)"},
    "naming.mode_manual": {"zh": "还没有模型，我自己填", "en": "No model yet — I'll fill it in"},
    "naming.model_path": {"zh": "模型文件", "en": "Model file"},
    "naming.browse": {"zh": "浏览…", "en": "Browse…"},
    "naming.auto_hint": {
        "zh": "拖入或选择 .mdl：工具会读出它编译时写死的目录与材质名，你就不用管了。",
        "en": "Pick a .mdl: the tool reads the folder and material names baked in at compile time."},
    "naming.read_ok": {"zh": "已读出：目录 {cdm} ｜ 材质 {names}",
                       "en": "Read: folder {cdm} | materials {names}"},
    "naming.read_fail": {"zh": "读不出来：{why}", "en": "Could not read it: {why}"},
    # 13-B 返工（一类 2026-10-01 实测更正）：**一次转换就给每个材质名各写一份 VMT**、都指向本次
    # 这套贴图；只有"不同材质槽要配不同贴图"才需要分开跑。⚠️ 界面文案不许带 Markdown 星号/反引号
    # （`test_layout` 有一道锁）；也**不能**再出现"分几次跑"这个短语（`_task/13` §2.5 判据 3）。
    "naming.multi_materials": {
        "zh": "⚠ 这个模型有 {n} 个材质名 —— 本次会给每个名字各写一份 VMT，都指向你这次的贴图；"
              "只有要给不同材质配不同贴图时，才需要分开跑（每次一套素材）。名字可以直接选中复制。",
        "en": "⚠ This model has {n} material names — this run writes one VMT per name, all pointing "
              "at this run's textures. You only need separate runs when different materials use "
              "different textures (one texture set per run). The names can be selected and copied."},
    "naming.cdmaterials": {"zh": "materials 下的目录", "en": "Folder under materials"},
    "naming.material_name": {"zh": "材质名", "en": "Material name"},

    # ---- 13-E 眼睛专用图（只对「角色-眼睛」档出现；跟档走、不做折叠）----
    "eye.title": {"zh": "眼睛专用图（只对「角色-眼睛」档）",
                  "en": "Eye textures (Character · Eyes preset only)"},
    "eye.hint": {
        "zh": "眼睛档要的是虹膜那张图（美术资产）：PBR 那几张烘不出虹膜构图。虹膜图必填，"
              "眼睛 AO 选填（没有就不写 $AmbientOcclTexture）—— 换到别的档这组会自己消失。",
        "en": "The Eyes preset needs the iris image (an art asset — the PBR bakes cannot produce "
              "an iris). Iris is required, eye AO is optional (no AO ⇒ no $AmbientOcclTexture "
              "line). Switching to another preset hides this group."},
    "eye.iris": {"zh": "虹膜图（必填）", "en": "Iris map (required)"},
    "eye.ao": {"zh": "眼睛 AO（选填）", "en": "Eye AO (optional)"},
    "eye.pick": {"zh": "选一张眼睛专用图", "en": "Pick an eye texture"},
    "eye.filter": {"zh": "图片 (*.png *.jpg *.jpeg *.tga *.bmp)",
                   "en": "Images (*.png *.jpg *.jpeg *.tga *.bmp)"},
    "eye.need_iris": {
        "zh": "眼睛档需要一张虹膜图（必填）：在「参数表 / 材质属性」页的「眼睛专用图」那行点"
              "「浏览…」选一张，或者换一个预设档。",
        "en": "The Eyes preset needs an iris map (required): pick one under \"Eye textures\" on the "
              "Parameter table page, or switch to another preset."},
    "eye.need_ao": {"zh": "眼睛 AO 那张图找不到（路径不对或文件没了）—— 清掉那一行或重新选一张。",
                    "en": "The eye AO image cannot be found (bad path or deleted) — clear that row "
                          "or pick it again."},
    "naming.final_path": {"zh": "将会写到：materials/{path}", "en": "Will be written to: materials/{path}"},
    "naming.manual_hint": {
        "zh": "两栏必须与模型里编译时写的一致（工具不会替你改大小写）。",
        "en": "Both fields must match what was compiled into the model (case is preserved)."},

    # 输出
    "output.deploy": {"zh": "直接写进游戏（推荐）", "en": "Write into the game (recommended)"},
    "output.deploy_desc": {
        "zh": "转换完直接放进 L4D2 的 materials 目录。碰到同名文件会先问你，不会偷偷覆盖。",
        "en": "Puts results straight into L4D2's materials folder. If a file already exists, it asks you first."},

    # 做什么材质（模型 Phong / 笔刷 LightmappedGeneric）
    "route.title": {"zh": "选择模式", "en": "Choose mode"},
    "route.model": {"zh": "模型材质（Phong，给 .mdl 用）", "en": "Model material (Phong, for .mdl)"},
    "route.brush": {"zh": "笔刷材质（Hammer 铺墙用）", "en": "Brush material (for Hammer)"},
    "route.mask": {"zh": "给笔刷出反射遮罩（默认出）", "en": "Reflection mask for brushes (on by default)"},
    "route.hint_model": {
        "zh": "模型：高光走 exponent 贴图（VertexLitGeneric），适合武器 / 角色 / 道具。",
        "en": "Model: specular via an exponent texture (VertexLitGeneric) — weapons, characters, props."},
    "route.hint_brush": {
        "zh": "笔刷：L4D2 的笔刷没有 Phong，只出底色 + 法线（+ 可选反射遮罩）；明暗靠 lightmap，"
              "材质在 Hammer 的材质浏览器里直接选（不需要 .mdl）。",
        "en": "Brush: L4D2 brushes have no Phong — base color + normal (+ optional reflection mask). "
              "Lighting comes from the lightmap; pick the material in Hammer's browser (no .mdl)."},

    # 03 GUI 改版：三页结构 + 工具路径上第 1 页
    "tab.tuning": {"zh": "② 预览 + 调参", "en": "② Preview & tuning"},
    "tab.config": {"zh": "③ 参数表 / 材质属性 / 自由键值",
                   "en": "③ Parameter table / attributes / key-values"},
    "tab.export": {"zh": "④ 导出", "en": "④ Export"},

    # ② 预览 + 调参页：左右两个预览框
    "preview.src": {"zh": "源素材", "en": "Source"},
    "preview.out": {"zh": "产出成品", "en": "Result"},
    "preview.zoom": {"zh": "⤢ 放大预览", "en": "⤢ Zoom preview"},
    "preview.kind": {"zh": "右框看：", "en": "Right box:"},
    "preview.kind_exp": {"zh": "指数贴图", "en": "Exponent map"},
    "preview.kind_basecolor": {"zh": "底色", "en": "Base color"},
    "preview.kind_normal": {"zh": "法线", "en": "Normal"},
    "preview.need_import": {"zh": "先在第 ① 页导入素材\n这里就会出现图",
                            "en": "Import textures on page ① first —\nthe images show up here"},
    "preview.none": {"zh": "（这套素材没有这张图）", "en": "(This texture set has no such map)"},
    "preview.zoom_title": {"zh": "放大预览", "en": "Zoom preview"},
    "preview.hint": {"zh": "预览＝当前参数在内存里现算的结果（不写盘、不调 VTFCmd）。"
                           "拖动拉条时这里不动，松手才重算。",
                     "en": "This preview is recomputed in memory from the current settings "
                           "(no files written, VTFCmd not called). Dragging a slider doesn't "
                           "refresh it — releasing does."},

    "paths.title": {"zh": "工具路径", "en": "Tool paths"},
    "export.conflict_hint": {
        "zh": "碰到同名文件会停下来问你「覆盖 / 跳过」；⚠️ 选了覆盖就撤不回来（不做备份）。",
        "en": "If a file with the same name exists it stops and asks you (overwrite / skip). "
              "⚠️ Overwriting cannot be undone (no backups are kept)."},
    "export.output_title": {"zh": "输出位置", "en": "Output location"},
    "export.only_title": {"zh": "导出方式", "en": "Export mode"},
    "export.out_dir": {"zh": "输出目录", "en": "Output folder"},
    "export.deploy_dir": {"zh": "部署目录（游戏 materials）", "en": "Deploy folder (game materials)"},
    "export.result_title": {"zh": "这次的结果", "en": "This run"},
    "export.start_hint": {
        "zh": "（未导入素材时置灰）",
        "en": "(Greyed out until textures are imported)"},

    # 模型浏览器（HLMV）—— 施工单 02/03：一键起来看材质
    "hlmv.label": {"zh": "HLMV 路径", "en": "HLMV path"},
    "hlmv.run": {"zh": "用 HLMV 看看", "en": "Open in HLMV"},
    "hlmv.run_desc": {
        "zh": "用 L4D2 自带的 HLMV 打开上面那个模型。⚠️ 材质要先转换并部署进 materials（HLMV 只认游戏目录里的 VMT/VTF）；"
              "⚠️ HLMV 没有 lightmap：看材质够用，看整体明暗要进游戏。",
        "en": "Opens the model above in L4D2's HLMV. ⚠️ Convert and deploy into materials first (HLMV only reads VMT/VTF under the game folder). "
              "⚠️ HLMV has no lightmap: fine for checking a material, not for judging overall lighting."},
    "hlmv.hint_configured": {"zh": "用你指定的：{path}", "en": "Using yours: {path}"},
    "hlmv.hint_default": {"zh": "自动找到的（默认位置）：{path}", "en": "Auto-detected (default): {path}"},
    "hlmv.hint_fallback_default": {
        "zh": "你指定的那个文件不在 → 改用默认位置：{path}",
        "en": "Your path doesn't exist → falling back to the default: {path}"},
    "hlmv.hint_missing": {
        "zh": "没找到 HLMV。它一般在这个位置：{path}\n请点「浏览…」指定 hlmv.exe。",
        "en": "HLMV not found. It usually lives here: {path}\nPlease use “Browse…” to point at hlmv.exe."},
    "hlmv.no_model": {
        "zh": "先在上面选一个 .mdl —— HLMV 得有模型才开得起来。",
        "en": "Pick a .mdl first — HLMV needs a model to open."},
    "hlmv.started": {"zh": "已启动 HLMV：{name}", "en": "HLMV launched: {name}"},
    "hlmv.failed": {"zh": "启动 HLMV 失败：{why}", "en": "Could not launch HLMV: {why}"},

    # 运行状态
    "status.working": {"zh": "{name}：{stage}", "en": "{name}: {stage}"},
    "status.done_one": {"zh": "完成", "en": "Done"},
    "status.failed": {"zh": "失败", "en": "Failed"},
    "status.skipped": {"zh": "跳过", "en": "Skipped"},
    "status.cancelled": {"zh": "已取消", "en": "Cancelled"},
    "err.no_folder": {"zh": "先选一个素材文件夹", "en": "Pick a texture folder first"},
    "err.need_name": {"zh": "先填材质名（或用 .mdl 自动读）", "en": "Enter a material name (or use a .mdl)"},
    # 拖进来的文件夹里认不出贴图 —— 这是**用户第一个动作就可能撞到**的地方，必须说人话。
    # （之前这里只是静默显示"还没有选择素材"，看起来像拖拽坏了）
    "err.empty_folder": {
        "zh": "这个文件夹里没找到能认的贴图：\n{path}\n\n"
              "请选里面直接放着 PNG 的那个文件夹（Material Bakery 烘出来的那个），而不是它的上一级。\n"
              "文件名里带 BaseColor / Roughness / Normal / Metallic 就能认出来。",
        "en": "No recognisable textures in this folder:\n{path}\n\n"
              "Pick the folder that directly contains the PNGs (the one Material Bakery wrote),\n"
              "not its parent. Files named BaseColor / Roughness / Normal / Metallic are recognised."},
    "scan.done": {"zh": "识别到 {n} 套素材，可以点「开始转换」了",
                  "en": "{n} set(s) recognised — hit “Start” when ready"},
    "scan.none": {"zh": "这个文件夹里没认到贴图 —— 换个文件夹试试（见弹框里的说明）",
                  "en": "No textures recognised in this folder — see the dialog for what to pick"},
    "scan.dropped_model": {"zh": "已读入模型：{name}", "en": "Model loaded: {name}"},

    # 结束汇总（实施计划 §9.1：按钮 = 打开输出目录 / 打开日志 / 复制失败原因）
    "btn.open_out": {"zh": "打开输出目录", "en": "Open output folder"},
    "btn.copy_fail": {"zh": "复制失败原因", "en": "Copy failure reasons"},
    "result.copied": {"zh": "已复制到剪贴板", "en": "Copied to clipboard"},
    "result.no_fail": {"zh": "没有失败项", "en": "No failures"},
    "status.cancelling": {"zh": "正在取消…", "en": "Cancelling…"},

    # 校验模型
    "btn.validate": {"zh": "校验模型", "en": "Check model"},
    "validate.need_model": {"zh": "先选一个编译好的 .mdl 模型", "en": "Pick a compiled .mdl first"},

    # 同名冲突（用户拍板：不静默覆盖，停下来问；⚠️ 用户同时拍板"不备份"→ 覆盖是不可撤销的）
    "conflict.title": {"zh": "目标位置已有同名文件", "en": "Files with the same name already exist"},
    "conflict.body": {"zh": "下面这些位置已经有文件了。\n⚠️ 选择「覆盖」会直接替换、不留备份，也撤不回来。\n\n{list}",
                      "en": "These already exist.\n⚠️ \"Overwrite\" replaces them directly — no backup, and it cannot be undone.\n\n{list}"},
    "conflict.overwrite": {"zh": "覆盖", "en": "Overwrite"},
    "conflict.skip": {"zh": "跳过", "en": "Skip"},
    # 13-C：冲突的"为什么"用**码**传（core 只出 `exists` / `in_materials`），人话在这里渲染
    "conflict.why_exists": {"zh": "已有同名文件", "en": "a file with this name is already there"},
    "conflict.why_in_materials": {"zh": "materials 里已有同名文件",
                                  "en": "already exists in materials"},
    # 13-C：跳过的**原因**（"指纹一致"不说，那是老行为；撞上同名产物必须说出来）
    "skip.conflict": {"zh": "目标目录已有同名产物，你没让覆盖",
                      "en": "products with these names already exist — you chose not to overwrite"},
}

# ---------------------------------------------------------------- 参数（直译 + 常驻解释）

# (键, 中文标签, English 标签, 中文解释, English 解释)
PARAMS = [
    ("sharpness", "高光锐度", "Specular Sharpness",
     "数值越大，高光越集中越小；越大越像抛光金属。",
     "Higher = tighter and smaller highlight, like polished metal."),
    ("boost", "高光强度", "Specular Strength",
     "高光有多亮。角色通常较弱，武器通常很强。",
     "How bright the highlight is. Usually weak on characters, strong on weapons."),
    ("ao", "环境光遮蔽", "Ambient Occlusion",
     "把烘焙好的阴影压进底色，缝隙看起来更深。",
     "Bakes shadows into the base color so crevices look darker."),
    ("curve", "粗糙度映射", "Roughness Curve",
     "决定“多粗糙的材质对应多锐的高光”。拖动控制点可以改这条映射。",
     "Maps how rough a surface is to how sharp its highlight is. Drag the points to reshape it."),
    # ---- 2026-09-27 新增（07 单 S4 的 4 大拉条）----
    ("offset", "粗糙度整体偏移", "Roughness Offset",
     "整张图往左更亮更反光、往右更哑。中间 = 不改。",
     "Shifts the whole map: left = shinier, right = more matte. Centre = unchanged."),
    ("tint", "金属染色强度", "Metal Tint Strength",
     "金属区高光染上底色的强度（写在指数图的绿通道里）。中间 = 不改。",
     "How strongly metal highlights take the base colour tint (stored in the exponent map's "
     "green channel). Centre = unchanged."),
    ("refl", "反射强度", "Reflection Strength",
     "笔刷材质反射的强弱（envmap 遮罩整体增益）。中间 = 不改。",
     "Reflection strength for brush materials (overall envmap mask gain). Centre = unchanged."),
    ("envtint", "反射染色", "Reflection Tint",
     "反射偏冷还是偏暖亮（写进 $envmaptint）。中间 = 不改。",
     "Whether reflections lean cool or warm/bright (written into $envmaptint). Centre = unchanged."),
]

PARAM_INDEX = {p[0]: p for p in PARAMS}


def param(key: str, lang: str) -> dict:
    """取一个参数的四段文案（标签 + 常驻解释）。"""
    p = PARAM_INDEX.get(key)
    if not p:
        return {"label": key, "desc": ""}
    return {"label": p[1] if lang == LANG_ZH else p[2],
            "desc": p[3] if lang == LANG_ZH else p[4]}


# ---------------------------------------------------------------- 术语表（④ 关于页）

GLOSSARY = [
    # 2026-09-27（08 单 S6）扩充：至少覆盖"材质定义 / 常用开关逐条 / Phong / 粗糙度→指数 / VTF·VMT"。
    # ⚠️ 全部用人话、中英成对；**不许出现内部片号、Markdown 星号或反引号**（已有回归在扫）。
    ("材质定义 / 表面类型（$surfaceprop）",
     "告诉游戏「这是什么材质」：决定脚步声、子弹命中音效、弹孔和物理手感，不改外观。多数模型都该给一个。",
     "Tells the game what this surface is: it drives footsteps, bullet impact sounds, decals and "
     "physics feel — it does not change the look. Most models want one."),
    ("Phong / 高光",
     "跟着视角走的那片亮斑。L4D2 的模型材质有高光；笔刷材质没有（引擎不支持），笔刷的反射靠环境贴图。",
     "The highlight that moves with your view. Model materials have it in L4D2; brush materials "
     "don't (engine limitation) — brushes reflect via the environment map instead."),
    ("高光锐度 / 指数（Phong Exponent）",
     "高光有多大：指数越大，高光越小越锐（越像抛光金属）。本工具把它写进指数贴图。",
     "How big the highlight is: a larger exponent means a smaller, sharper highlight (like "
     "polished metal). This tool bakes it into the exponent map."),
    ("粗糙度 → 指数 / 金属度 → 染色",
     "越粗糙，高光越大越糊。金属度进指数贴图的绿通道，用来给高光染上底色。",
     "The rougher the surface, the bigger and softer the highlight. Metallic goes into the "
     "exponent map's green channel and tints the highlight with the base colour."),
    ("VTF / VMT",
     "VTF 是贴图（引擎读的图片格式）；VMT 是说明书，告诉引擎怎么用这些贴图。本工具两个都生成。",
     "VTF is the texture (the image format the engine reads); VMT is the instruction sheet "
     "telling the engine how to use it. This tool writes both."),
    ("$halflambert 半兰伯特",
     "让背光面不那么死黑。官方 112 个材质里有 41 个在用，是最常用的开关之一。",
     "Keeps back-lit surfaces from going pitch black. 41 of Valve's 112 sampled materials use "
     "it — one of the most common switches."),
    ("$nocull 双面",
     "两面都渲染：单面片（树叶、铁丝网、窗帘）也要看得见。",
     "Renders both sides, so single-sided sheets (leaves, chain-link, curtains) stay visible."),
    ("$translucent 半透明",
     "让贴图的 alpha 真的透明（玻璃、贴花用）。",
     "Makes the texture's alpha actually see-through (glass, decals)."),
    ("$alphatest 透明裁切",
     "按 alpha 阈值直接抠洞（树叶、铁丝网），比半透明省性能。",
     "Cuts holes by an alpha threshold (leaves, chain-link); cheaper than translucency."),
    ("$nodecal 不接贴花",
     "禁止在这个表面上留下弹孔 / 血迹贴花（镜面、玻璃常用）。",
     "Stops bullet holes and blood decals from appearing on this surface (common on glass and "
     "mirrors)."),
    ("通道打包 Channel Packing",
     "把几张灰度图分别塞进一张图的 R/G/B/A 通道，省显存。",
     "Packing several grayscale maps into one image's RGBA channels to save memory."),
    ("PBR",
     "基于物理的渲染：用粗糙度 / 金属度描述材质的现代做法（Blender 那一套）。",
     "Physically Based Rendering: describing materials with roughness/metallic, as Blender does."),
]
