# PBR to Phong — 开发日志（给 AI 自己看）

> **给其他窗口的读法**：先读「0. 快速上下文」和「1. 当前状态」，然后**直接跳到最后一个未完成的段落**。
> 已完成的段落（标 ✅ 且带"结论"）不要重做，不要重读参考文件全文。

---

## 0. 快速上下文

| 项 | 内容 |
|---|---|
| 目标 | 开发工具，把 PBR 流程贴图转换成 **Left 4 Dead 2（起源1 / Source 1）** 用的 Phong 贴图 |
| 输入 | Material Bakery（`D:\Codex Projects\Blender Addons\Auto Bake v1.5`）烘焙落盘的 PBR 贴图集 + `_mbakery.json` 清单 |
| 输出 | 通道打包 PNG → 调 VTFCmd 出 **VTF** → 生成 **`.vmt`** →（可选）部署进 `materials/`（旧文"第一版不出 VTF/VMT"已废，见 §1） |
| 形态 | **独立 GUI 程序**（PySide6，**5 页零滚动**）+ CLI；core 纯 Python、不依赖 bpy |
| 工作区 | `D:\Codex Projects\Softwares\PBR to Phong`（2026-09-28 搬家；旧路径 `...\Blender Addons\PBR to Phong` 已废 —— 残留的空 `.dsh-meow` 也已由用户删除） |
| 参考资料 | `Valve Developer Community\`（VDC 网页）、`Textures\`（从 L4D2 抽出的官方材质 + VTF） |
| 验证环境 | L4D2 装在 `D:\SteamLibrary\steamapps\common\Left 4 Dead 2` |

**工作规矩（用户定的，必须遵守）**：① 用户明确说"开始"后才开工；② 用 Git 管理，须经用户允许才能建仓库/提交（用户会提供 GitHub PAT）；③ 默认处于"验证"阶段，用户指令可能宽泛，**多提问敲定细节**；④ 有问题不要犹豫直接问；⑤ 收到反馈**先问清楚问题**，不要立刻改；⑥ 保持工作目录整洁易读；⑦ 单次工作超 30 分钟做一次阶段汇报；⑧ 不把反馈写进用户看的 `readme.md`，除非用户要求。

---

## 1. 当前状态

**阶段：阶段 0 ~ 6 + 笔刷 v1 + γ HLMV + GUI 改版（S1~S6、06~10）全部完成并验收（2026-09-28）。** 三层验收全落地 —— core 单测 + `exp8` 交付自检、
`exp7` 与官方统计对照、**用户实跑确认**（"跑通了，游戏里正常" / GUI"一切正常，也有 log，没碰到错误" / 透明材质"棕榈树弄好了，没黑边了"）。
GUI 现为 **5 页零滚动**版式（① 转换 / ② 预览 + 调参 / ③ 参数表·材质属性·自由键值 / ④ 导出 / ⑤ 关于）、**21 档预设（按路线过滤）**、
预览接真图 + 4 大拉条 + 曲线编辑器、透明材质（`alpha.cutout`）；
`dist/PBR2Phong/` onedir 包已重打（见 §4 第十五/十六轮）；**全量 453 项全绿（12 套件）**。

> ⭐ 接手请先读：`实施计划.md`（**唯一权威**：§0.5 进度快照 + §0.6 实测结论 34 条）、`阶段0_实测/阶段0-实测报告.md`；跨会话的指令与成果走 `_task/`（一类发单）与 `_submission/`（二类交活），变更历史看 `git log`。
> **下一步**：`_task/11-文案与一致性收尾.md`（待开工 —— ① 三处灰字解释别被无声截断 ② 切路线也不动观感旋钮 ③ 其余体检警告英文化=低优先）。
> ✅ `实施计划.md` §9.9 / §9.8 两处改写**已完成**（2026-09-28，一类：按 γ 拍板与否决内嵌、以及用户"没洁癖、大大方方用、标记来源"的许可立场）。
> ⚠️ 本日志 §1 是**摘要式、最易腐烂**：页数与测试项数**以 `PBR2Phong/README-工程说明.md` 为准**。

已定：
- 目标引擎 = L4D2
- 输入 = Material Bakery 的烘焙产物
- 输出范围（已演进，本条只是历史）：最初定"第一版只出贴图，不碰 VTF/VMT"，**现已扩为：PNG + 自动调 VTFCmd 转 VTF + 生成 `.vmt` 文件**（详见下面"VTF 路线"与"VMT"两条）
- 金属策略 = **方案 A「不压黑」**：保留 albedo 颜色，用 `$phongalbedotint 1` + `$phongexponenttexture` 的 **G 通道**控制高光染色强度；**放弃 (1−metallic) 压黑**。理由：Source 没有逐像素高光颜色通道，压黑会让高光染色一起变黑（金属高光变灰白）；而官方 L4D2 武器正是 `$phongalbedotint 1` + 不压黑
- 世界笔刷（`LightmappedGeneric`）：**架构上预留，第一版不实现** —— ⚠️ **已过时（2026-09-26 起）**：笔刷模式 v1 **已实现并验收**（`_task/01-笔刷模式.md` ✅ 收），规格权威见 `Hammer笔刷路线.md`
- 形态 = 独立程序方向（GUI 技术栈交给另一个窗口调研，见 `GUI 选型调研.md`）
- **VTF 路线**：第一版只出 PNG；VTF 转换先"调起 VTFEdit / 其命令行 VTFCmd"（用户在程序里指定路径），**预览、批处理、参数记忆由我们自己做**（这些正是 VTFEdit 难用的地方）；**自研 VTF 写出排第二版**
- **高光遮罩载体 = 按类别预设**：武器/硬表面 → basecolor 的 alpha（`$basemapalphaphongmask 1`，一套 alpha 兼任 phong mask + envmap mask）；角色/软表面 → 法线图的 alpha（默认行为）
- **输入层不绑死 MB**：扫描目录下的图像文件；有 `_mbakery.json` 则精确识别（最高优先级）；否则按"用户选中的第一张图的前缀"分组匹配（下拉只显示同前缀文件）；**提取不出前缀就罢工**，要求逐个指定；支持通道打包图（ORM/RMA 的 R/G/B 手工映射）；确认结果固化为 `phong_input.json`
- **尺寸规则（用户 2026-09-24 推翻我的提议，最终版）**：**用户给什么尺寸就输出什么尺寸，工具不做任何尺寸管制、不拒绝、不重采样**。用户原话："其实游戏也没说不能读取这种意外的尺寸，不如用户他给啥咱就输出啥吧？"——我们只出 PNG，PNG 对尺寸无要求；2 次幂的限制属于转 VTF 那一步（需要时用 VTFCmd 的 `-resize`/`-rclampwidth`）。仅在报告里附一行提示（宽高非 4 倍数会影响 DXT 块压缩）
- **VMT**：第一版就**生成 `.vmt` 文件**（不是只给片段）
- **VMT 路径**：GUI 给一个**目录输入框**（默认填 `custom`，不做弹窗询问）→ VMT 里的路径 = `<输入内容>/<名字>`；留空则直接放 `materials/` 根下；不做自动推断
- **产物落地**：用户拍板**直接写进 L4D2 的 materials 目录**（`D:\SteamLibrary\steamapps\common\Left 4 Dead 2\left4dead2\materials`）。配套安全设计：**不静默覆盖**（同名冲突停下来问）、本地输出目录永远留档。⚠️ **2026-09-25 用户拍板"备份全砍"**（原话"覆盖就覆盖呗，大不了再调材质的事"）→ **写入前备份 / 写入清单 / 一键撤销 三样已从 `core.deploy` 删除**，覆盖不可撤销（用户已知情接受）
- **属性面板**：一级常用（`$surfaceprop` 下拉、`$model`/`$nocull`/`$translucent`/`$alphatest`/`$nodecal`/`$halflambert`/`$phongdisablehalflambert` 开关）+ 二级自由键值（可存预案/预设）
- `$envmap env_cubemap` **默认关**，GUI 手动勾
- **预设系统**：内置 武器 / 角色 / 道具 / 玻璃 四套（数值抄自官方实测）；用户可改可存自己的预设
- **第一版范围（2026-09-24 用户勾选确认）**：**纳入** = 调 VTFCmd 自动出 VTF、生成 `.vmt`、命名两栏 + 读 `.mdl`、"校验模型"按钮、属性面板、通道打包 PNG + 日志；**不做（放第二版）** = 实时/静态 Phong 预览（用按素材类别的官方真实预设兜底）、结果对比页（第一版该页显示"第二版，敬请期待"）。**输出位置：以"直接写进 materials"为主，另留一个"只导出不部署"开关"。⚠️ **本条"不做"那两项已于 2026-09-28 作废**：第 ② 页预览接真图、结果对比页这个页签已不存在（3D 走 γ 一键 HLMV）—— 见 `实施计划.md` §9.9
- **GUI 侧并行结论（已采纳，2026-09-28 同步现状）**：PySide6 / **5 页**（① 转换 / ② 预览 + 调参 / ③ 参数表 / ④ 导出 / ⑤ 关于；旧的"4 标签页（转换·结果对比·参数设置·关于）"与"状态栏常驻开始转换"**均已废**）/ 中英双语、默认跟随系统、语言切换在标签栏右上角 / 文案 = 直译 + 解释常驻界面 / 跟随系统主题 / 日志 `log.txt` / 配置记忆 + 可存预设 / MIT + 双语 README + `--onedir` 打包（排除未用 Qt 模块）。⚠️ **零滚动是硬约束**（不许 `QScrollArea`）；参数页**不许折叠**

- **同名冲突策略（用户拍板）**：**停下来问用户** —— **覆盖 / 跳过**（实现里只有这两个，**没有"改名"**）；⚠️ **覆盖不可撤销**（备份已按用户要求全砍）
- **命名模式（已定，用户拍板）**：两条来源，**产物完全相同**，后续一条代码路径 —— ① **有已编译的 `.mdl`** → 拖入（或工具在 L4D2 `models\` 下按名字自动搜索）→ 读出 `$cdmaterials` + 材质名 → 目标路径零人工确定（"这样最稳妥"）；② **没有 `.mdl`（首次制作）** → **两栏手填**：`$cdmaterials` 目录 + 材质名，两栏下方**实时显示拼出的最终路径**（防重复前缀、防写错），结果固化成 `phong_input.json`。**工具不自动改写大小写**，按用户输入原样落地，只在检测到大小写与 MDL 不一致时给 Linux 警告
- **校验模型按钮（已定）**：读 `.mdl` 与我们的产物比对 —— ① VMT/VTF 是否落在 MDL 期望的位置；② VMT 里的 `$basetexture` 是否指向真实存在的 VTF；③ 大小写是否与 MDL 一致（Linux srcds 会挂）；④ MDL 里是否有多出来的材质、或未赋材质的 `no_material` 面（在用户自己的 `sportsground.mdl` 里就实拍到了 `no_material`）

未定 / 待验证：见第 3 节。

✅ **需求冲突已决策**：官方确认 **L4D2 的 `LightmappedGeneric` / `WorldVertexTransition` 不支持 Phong**（仅 CS:GO 分支与 Strata Source 有）。用户决定：**架构上预留"笔刷模式"接口，第一版不实现**。用户只做第三方模型与材质，基础墙面地面本来就不依赖 Phong（靠 lightmap + `$envmap` + `$ssbump`），影响约等于零；将来要支持时，走 VDC 的 brush 方案（albedo + 法线图 alpha 里的 envmap mask + cubemap）。

---

## 2. 用户需求（按时间顺序，保留原话）

**第 1 轮**（用户定规矩）：
> "我要开发一个blender插件，把PBR流程的贴图烘焙成起源1引擎用的Phong贴图"
> 规矩原文：① 明确说"开始"之后才开工；② 用 Git 管理，我给 PAT，经允许才建项目/提交；③ 每次开发都默认在"验证"阶段，指示可能宽泛，**多问我问题以敲定后续细节**；④ 有问题不要犹豫；⑤ 收到反馈后不要立刻修改，问清楚我碰到的问题；⑥ 保持工作目录整洁，写给自己用的 md 大纲 = 用户需求/修改过程(修bug/测试/交付/验证/结论)/给此次对话的总结；⑦ 该 md 会被其他对话读取，要能忽略已完成工作；⑧ 不把反馈写进用户看的 readme.md，除非用户要求；⑨ 单次工作超 30 分钟做阶段汇报。

**第 2 轮**（目标与形态）：
> 目标引擎："Left 4 dead 2"
> 输入设想："我的设想是直接烘焙PBR贴图后做后处理，我此前已经开发了一个批量烘焙插件，你在分析之后觉得怎么做最合适？"
> 输出："第一版只出贴图，VTF/VMT 以后再说"
> 目标 shader：VertexLitGeneric（模型/道具/武器）+ LightmappedGeneric（地图世界笔刷/建筑）

**第 3 轮**（金属 / 素材 / 形态）：
> 金属策略选：**物理派** —— 金属区 basecolor 乘 (1−metallic) 压暗，`$phongtint` 染高光色，并输出 envmap mask
> 形态疑问："你觉得是做Blender内插件好还是做成独立的程序好？我明白了其实 Phong 贴图只是数学转换再打包而已"
> 要求："咱先讨论可行性和实现方式…不急着开工"
> "我把 vdc 里面的网页下了，html 格式，还有什么你访问不到的我帮你找"

**第 4 轮**（素材 + GUI 分工）：
> "我把VDC的html和vtf和vmt都放在工作目录下了，一个文件夹叫：Valve Developer Community，另一个Textures"
> GUI 选型："看哪个最好用，你别在这个对话做，单独在工作目录写个简单的markdown指令我在另一个窗口做"

**第 5 轮**（VTF / 输入层 / 尺寸）：
> VTF："我想让用户装一个vtfedit，直接在我们的程序里指定路径然后预览和编辑就直接开vtfedit转换，你觉得如何？可是我真觉得它很难用，不如自己再做一个好用点的……"
> 输入层："你提的设计真不错！只在目录下找图像文件！我再加点：如果当前文件夹有多个物体的贴图，直接根据第一张选上的图像前缀，如（Couch_basecolor.dds）就直接把'Couch'抓出来，给剩下的'匹配'上去（即在下拉文件里只显示前缀里有Couch的图像文件），怎么样？如果是连在一起就直接罢工让用户自己一个个连。只有用MB的才是人上人！"
> 尺寸（先说"小于256*256 直接拒绝"，随后自己推翻）："不对啊，其实游戏也没说不能读取这种意外的尺寸，不如用户他给啥咱就输出啥吧？"

**第 6 轮**（落地 / 属性 / 命名）：
> 路径："直接询问用户要不要创建一个materials下的自定义文件夹放进去，有就有，没有直接扔materials里面，这个自定义文件夹命名为custom" → 随后改为"目录输入框，默认 custom，不做弹窗询问"
> 属性："要。还有我总觉得资产属性这些应该也做进来吧，总不可能让用户用完转换功能了还得开vtfedit调吧？"
> 落地：选择**直接写进 L4D2 的 materials**
> 命名（SourceOps 工作流原话）："我在blender用sourceops工作，譬如说我创建了一个叫'school_gate'的模型，我得在模型面板创建一个'custom/school_gate'的槽，还得在材质面板下添加一个'custom/school_gate'的路径，而且我的模型材质名称也得是school_gate才能正常读取，我现在在想有没有一些例外能跳出这个情况"
> 对"读 SMD 自动取名字"的反馈："你的方向三很不错，可是用户每次还得找一遍自己的smd来确定路径……我总觉得应该有更好的实现方法，一会细说"

---

## 3. 技术结论

### 3.1 ✅ 已验证（有实物证据）

**Material Bakery 的输出契约**（决定了我们怎么认图）：
- 一个集合 = 一套贴图，命名 `<组名>-<贴图类型>-<分辨率>.png`
- 每套贴图带 `_mbakery.json` 清单，用**语义 ID** 标识：`shader.base_color` / `shader.roughness` / `shader.metallic` / `shader.ior` / `shader.specular_ior_level` / `shader.emission_color` / `misc.ao` / `standard.normal` 等
- **不要靠猜文件名认图，读清单的 `type`**
- 它本身已有 `misc.channel_packing` 烘焙类型（"多图合并进通道"这套机制在 MB 里已存在）

**L4D2 官方 Phong 真实用法**（从 `Textures\` 里的官方 VMT 读出）：

| 素材类别 | 真实参数写法 |
|---|---|
| 角色（survivors） | `$phong 1` / `$phongboost 1.4~1.5` / `$phongexponent 5` **或** `$phongexponenttexture ..._exp` / `$phongtint "[.85 .85 1]"` / `$phongfresnelranges "[.3 .65 30]"` / `$ambientocclusion 1` / `$diffuseexp 1.5` / `$lightwarptexture ..._wrp` |
| 第一人称武器（v_ 模型） | `$phongboost 45~100`（远高于角色！）/ `$phongexponenttexture ..._exp` / **`$basemapalphaphongmask 1`** / `$phongalbedotint 1` / `$envmap env_cubemap` / `$envmapfresnel 1` / `$envmapFresnelMinMaxExp "[.4 1 .4]"` |
| 玻璃/瓶罐 | `$envmap env_cubemap` + `$envmapsaturation` / `$envmaptint`；可乐瓶同时用 `$normalmapalphaenvmapmask 1` + `$phong 1` + `$phongexponent 200` |
| 散装样例 | `models\infected\wwz\Zombie_Gasbag\head_01_0mat.vmt`：`$phongexponent 7` / `$phongtint "[.85 .85 1]"` / `$phongfresnelranges "[.2 .5 5]"` |

**关键事实**：
- `$phongexponent` 是**标量整数**（官方值域实测 5 / 7 / 50 / 200），`$phongexponenttexture` 是可选替代（官方用 `_exp` 后缀命名贴图）
- `$phongboost` 是**浮点**（.02 ~ 100 都有），且**强弱随素材类别变化一个数量级** → 工具需要"按类别预设"而不是一个全局默认值
- **`$phongalbedotint 1` 让高光染色跟随 albedo** —— 这正是金属工作流想要的（金属的 F0 = albedo），武器上官方就在用
- 遮罩有两种来源：`$basemapalphaphongmask 1`（用 basecolor 的 alpha）和 `$normalmapalphaenvmapmask 1`（用法线图的 alpha）
- L4D2 的 `glbaseshaders.cfg` 含大量 `phong_vs20` / `phong_ps20b` 静态组合 → Phong 是一等公民
- **`LightmappedGeneric` / `WorldVertexTransition` 的 Phong 只在 CS:GO 分支与 Strata Source 才有（官方 `$phong.html` 原文）→ L4D2 的世界笔刷材质不支持 Phong**；这两个 shader 同时也不支持 `$phongexponenttexture`（只能用标量 `$phongexponent`）
- **`$phongexponenttexture` 各通道语义（官方原文）**：R = exponent 遮罩（0 = 大而糊，255 = 小而锐）、G = albedo 染色遮罩（仅 `$phongalbedotint`）、B = 无、A = `$rimlight` 遮罩（仅 `$rimmask`）
- **高光强度遮罩默认来自 `$bumpmap` 的 alpha 通道**，`$basemapalphaphongmask` / `$basemapluminancephongmask` 可覆盖 → **法线图必须带 alpha 保存**
- `$phongexponentfactor` 把 exponent 贴图的值**乘**一个系数（默认 0.0 = 无高光，官方建议 149.0）→ 有效 exponent 可以远超 8 位范围

**SourceOps 工作流（读源码确认，2026-09-24）**：SourceOps 装在 `C:\Users\Admin\AppData\Roaming\Blender Foundation\Blender\4.5\scripts\addons\SourceOps`（同目录还有 `io_scene_valvesource` = Blender Source Tools）。这个工作流决定"我们生成的 VMT/VTF 该叫什么、放哪"。

- `addon/types/model_export/smd.py:321-337`：写进 SMD 的材质名 = **Blender 材质名原样照抄**（`smd_mat = getattr(mesh.materials[poly.material_index], 'name', 'no_material')`），不做任何加工
- `addon/types/model_export/model.py:173-181`：QC 里的 `$cdmaterials` **完全来自模型面板的 `material_folder_items` 列表**（默认 `models/example`）；**该列表为空时写 `$cdmaterials "/"`**
- 导出格式只有 **SMD / FBX**（没有 DMX）→ 若要从模型文件读材质名，只需支持 SMD
- 结论：所谓"三处必须一致"其实只有**两个旋钮** —— ① Blender 材质名 → 决定 SMD 里引用什么名字；② 模型面板的 `$cdmaterials` 列表 → 决定 studiomdl 去哪个目录找 VMT。**第三处（VMT 的文件名与路径）是这两个的推导结果**

**材质路径真相（⭐⭐ 实证，用用户自己的 school_gate 模型验证，2026-09-24）**：
- `left4dead2\models\custom\school_gate.mdl` 内部字符串：`cdmaterials = "custom\school_gate\"`、材质名 = `school_gate`（另有 `School_Gate` = SMD 名）
- 实际 VMT 位于 `materials/custom/school_gate/school_gate.vmt`，其中 `$basetexture "custom/school_gate/school_gate"`
- **规则：引擎查找路径 = `$cdmaterials` + 材质名（字符串拼接）**，两者在 MDL 里是**两个独立字段**，编译时由 studiomdl 写入
- 推论：① **文件夹名可以任意**，但必须与编译时写进 MDL 的 `$cdmaterials` 一致；② "目录名 = 材质名 = 模型名"只是**约定不是要求**（目录与材质名是两个字段，可任意组合）；③ **自由度在编译之前**——编译后该信息被冻结进 MDL，事后改文件夹名必须重编译；④ VMT 里 `$basetexture` 是**相对 `materials/` 的路径**，与 VMT 自己放哪无关（贴图可以放在完全不同的目录）；⑤ 模型 `.mdl` 自己放哪不影响材质查找
- ⚠️ 大小写陷阱：MDL 里是 `School_Gate`、实际文件是 `school_gate.vmt` → Windows 不敏感所以能跑，**Linux srcds 会挂**。"能跑"不等于"规则允许"
- 🎯 **能力发现（对本工具极重要）**：MDL 里就烘着"引擎会去哪儿找材质"，所以**工具可直接读编译好的 `.mdl` 拿到权威材质路径**，不必让用户去找 SMD（.mdl 比 SMD 更权威——SMD 改了但没重编译时以 .mdl 为准；模型文件也比 SMD 好找）。这回答用户"应该有更好的实现方法"。
- 实现注意：L4D2 是 MDL v49，`mstudiotexture_t` 是**定长结构数组**（不是偏移表），我第一版解析把这里写错了（字符串扫描法正确）；正式实现需按结构布局解析

**VDC 资料**（`Valve Developer Community\`）：
- `Adapting_PBR_Textures_to_Source.html` = 社区版的 PBR→Source 转换方法论，**但它明确只做 brush 材质、跳过 Phong**
  - 高光贴图通常塞在**法线图的 alpha 通道**里
  - roughness→高光曲线**在 sRGB 空间做**：`specular = curve(1−roughness, 108→0, 208→112)`；按此公式**高光归零点实际是 roughness ≈ 0.577**（即 1 − 108/255），VDC 原文说的"64% sRGB"算术对不上（另一窗口已核实并记为 lesson，实现时以 0.577 为准）
  - AO 在 brush 上不支持 → 按 25~50% 不透明度乘进 albedo；displacement 按 12.5% 乘进 albedo
  - 法线绿通道：Source 与 3DS Max 一致，Maya 需翻转
- `Creating_PBR_materials.html` 是 Source 2 / Strata 的 PBR，**与本项目无关，别再读**
- 仍有用的：`$phong.html` / `$envmap.html` / `$normalmapalphaenvmapmask.html` / `$ssbump.html` / `VertexLitGeneric.html` / `LightmappedGeneric.html` / `Normal_map.html` / `SurfaceGGX.html` / `VMT.html` / `VTF_(Valve_Texture_Format).html`

**VDC `$phong.html` 官方参数语义（⭐⭐ 已核实，逐字来自官方页）**：

| 参数 | 语义 |
|---|---|
| `$phongexponenttexture` 的 **R** | **Exponent mask** = 高光大小，0–255；**0 = 大而糊的高光，255 = 小而锐的高光** |
| `$phongexponenttexture` 的 **G** | **Albedo tint mask** = 仅在 `$phongalbedotint 1` 时生效；0 = 不染色，255 = 完全染色 |
| `$phongexponenttexture` 的 **B** | 什么都不存（Nothing） |
| `$phongexponenttexture` 的 **A** | `$rimlight` 遮罩（仅当 `$rimmask 1`） |
| `$phongexponent` | 全局 exponent 值，**会覆盖** exponent 贴图 |
| `$phongexponentfactor` | 把 `$phongexponenttexture` 的 exponent **乘**这个数；默认 0.0（等于没高光），官方建议值 **149.0** |
| Phong 遮罩的默认来源 | **`$bumpmap` 的 alpha 通道**；`$basemapalphaphongmask` / `$basemapluminancephongmask` 可覆盖它 |
| `$normalmapalphaenvmapmask` | 让 bumpmap 的 alpha 同时用于 Phong 遮罩 **与** `$envmap` 遮罩 |
| `$invertphongmask` | 反转 phong 遮罩 |
| `$phongalbedotint` | 用 `$basetexture` 的颜色给高光染色，染色强度由 exponent 贴图的 **G 通道**决定；**必须有 `$phongexponenttexture` 才有效**；**与 `$phongtint` 互斥**（后者会禁用它）；它把 basetexture 乘在反射上，不压暗 albedo，但反射会变暗 → 要在 phong mask 或 `$phongboost` 上补偿 |
| `$phongtint` | RGB 高光染色；与 `$phongalbedotint` 二选一 |

**结论**：模型路线（VertexLitGeneric）的"高光强度"其实有**两条并存**的通道——`$bumpmap` 的 alpha（默认遮罩，8 位）+ exponent 贴图的 R/G。**这直接确定打包布局**：法线图必须带 alpha，exponent 贴图是 RGB(A) 四通道打包图。

**官方 VTF 实测规格（⭐ 直接解析 L4D2 官方 VTF 头部得到，样本在 `Textures\`）**：

| 贴图 | 格式 | 尺寸 | 标志 |
|---|---|---|---|
| `v_shotgun_a.vtf`（basecolor） | **DXT5** | 1024² | EIGHT_BIT_ALPHA → **basecolor 带 8bit alpha** |
| `v_shotgun_a_exp.vtf` / `coach_head_exp.vtf` | **DXT1** | 1024² / 2048² | **无 sRGB 标志、无 alpha** |
| `v_4pistols_exp.vtf` | DXT1 | **512×1024（非正方形）** | ANISO |
| `coach_head_normal.vtf` | **DXT5** | 2048² | **NORMAL(0x80)** + EIGHT_BIT_ALPHA → **法线图带 alpha** |
| `coach_head_wrp.vtf`（lightwarp） | BGR888 | 256×16 | CLAMPS/CLAMPT |

由此推出的输出规格：
- **exponent 贴图官方就用 DXT1**（无 alpha、无 sRGB 标志）→ 我们只需输出 RGB，且曲线应**在线性空间**做（不是 VDC 那种给 brush 灰度图用的 sRGB 空间）
- **法线图官方带 8bit alpha**：角色路线里 normal alpha 就是 phong mask 的默认来源
- **basecolor 官方也带 8bit alpha**：武器路线用 `$basemapalphaphongmask 1`，让**同一个 alpha 同时充当 phong mask 与 envmap mask**
- 尺寸必须 2 的幂，但**可以非正方形**
- 官方 VTF 是 7.4；`SRGB` 标志 = 0x40（7.5 起废弃），而官方贴图**一个都没设** → sRGB 由 shader 采样方式决定，别指望从标志位判断
- ⚠️ 官方 exponent 用 DXT1（4:1 有损），G 通道（染色强度）精度很差 → 若金属染色出现渗色，改建议 DXT5 / BGRA8888

### 3.2 ⚠️ 待验证（重要，别当结论用）

1. **法线图绿通道方向**：Blender 的约定可能等同于 Maya（需翻转）而不是 3DS Max。猜错会让整套法线反向。→ 需实测（同一法线贴图正/反两版各做一次，在游戏里看凹凸受光方向）。
2. **粗糙度→指数曲线**：没有官方公式，是美术曲线，必须留一轮"在 HLMV/游戏里目测调参"的验收。
3. **`$phongexponentfactor` 在 L4D2 的可用性与实际表现**（官方页有 CS:GO 图标标记的段落可能不适用于 L4D2）—— 决定"低粗糙度端精度"这条分支怎么走。
4. **`$phongexponenttexture` 的 8 位 R 通道 + 标量 factor 的组合**：单像素精度只有 8 位，意味着同一材质内**高光锐度的动态范围有限**，极光/极糙材质可能需要拆成多套材质或改走标量。
5. **`$phongexponentfactor` 的文档与实物矛盾**：官方文档说它默认 `0.0`（等于没有高光）、建议 `149.0`，但**官方 L4D2 武器 VMT 全都没写它、高光却正常** → 文档那个默认值要么是错的、要么只适用 CS:GO。实现策略：**不写它**（跟官方实物走），但需实测确认它对 exponent 强度的实际影响。
6. ~~studiomdl 材质名解析规则~~ → **已实证解决**，见 3.1「材质路径真相」。

### 3.3 已知的硬限制（不是我们的锅，要写进预期）

- PBR 的 roughness 是连续 0–1，Source 的 exponent 贴图**单像素只有 8 位**；按 `n ≈ 2/α² − 2`（α = roughness²）估算，roughness=0.1 需要 n≈20000。**范围可以靠 `$phongexponentfactor`（官方建议 149）扩展，但单像素只有 8 位精度** → 同一张材质里"极镜面"和"中粗糙"无法共存，只能靠曲线压缩或拆分材质解决。
- Source 的 Phong 不能量守恒，金属没有物理正确的表示，只能"看起来像"。

---

## 4. 修改过程（修 bug / 测试 / 交付 / 验证）

### 2026-09-25 · 第十六轮：阶段 6 —— 打出第一个「能发给别人」的 onedir 包

**① 打包**：新增 `PBR2Phong/build_exe.py`（PyInstaller `--onedir --windowed`，剔掉 41 个没用到的 Qt 模块）
+ 入口 `PBR2Phong/run_gui.py`。产物 `dist/PBR2Phong/PBR2Phong.exe`（5.2 MB），**整包 148.5 MB / 217 文件**。
为什么 `--onedir` 不 `--onefile`：包里带 PySide6/Qt（LGPLv3），**动态链接 + 能让用户替换 Qt** 才是合规姿势；
`--onefile` 每次启动解压到临时目录，既慢又没法换 Qt。为什么 `--windowed`：面向普通用户不弹黑框（代价：启动期崩溃看不到 traceback → 真出问题要临时 `--console` 重打）。

**② ⭐ 不只看"打包成功"，真启动一次并抓图**：新增 `PBR2Phong/tests/check_exe.py` ——
`Popen` 起 exe → `EnumWindows` 找它**可见且够大**的主窗口 → `PrintWindow(hwnd, dc, 2)` 抓图 →
断言「进程活着 + 窗口标题 `PBR → Phong` + **抓到的图不是纯色**（像素标准差 40.45 > 5）」。**7 项全过**，
截图 `阶段0_实测/out/exe_window.png`（界面与源码版一致）。⚠️ 测试把 `PBR2PHONG_HOME` 指到临时目录，
**不碰用户真实的 `%APPDATA%\PBR2Phong`**。

**③ 文档三件套**：`README.md`（**双语**、含 SmartScreen「仍要运行」说明与"**不备份**、覆盖不可撤销"警示）、
`LICENSE`（MIT）、`THIRD_PARTY_LICENSES.md`（PySide6/Qt = **LGPLv3、动态链接、可替换**，附许可与源码链接；numpy/Pillow；
明确写出**不分发 VTFCmd**）。

**④ 顺手**：`对账.md` §6 里那条"本机 HLMV 跑不起来"的旧避坑条目改成正确版本（HLMV 能起，是当初调用方式的问题）。

**验证**：`test_pipeline` **71** + `test_gui_flow` **46** + `test_first_run` **28** = **145 项全绿**；
打包 exe 真启动 7 项全过。⚠️ **剩下只有一件我做不到**：把 `dist/PBR2Phong/` 拷到**另一台机器**上双击跑一遍。

### 2026-09-25 · 第十五轮：阶段 5 验收通过 + 跨会话对账 + 备份策略被用户否掉

**① ✅ 阶段 5 验收达成（这一轮的"用户需求"就是一句回话）**：用户原话：**"我的测试结果是一切正常，
也有 log，暂时没碰到什么错误"** —— 阶段 5 的验收标准就是"用户能自己从头跑完一遍"，到此达成。
（此前 139 项自动化检查全绿，现在加上用户实跑，两层都绿。）goal 已标 **complete**。

**② 跨会话对账（用户要求）**：用户说"我睡完觉起来忘了这开发进度，你跟隔壁对话对个账，就在
`对账.md`，你加个分界线，写下面，它写上面"。做法：**只追加**，不动上面那半 —— 上面那半是隔壁窗口
写的、内容相当于模型线 **10 小时前**的状态，**四处已过时**（D/B 题卡点、真实素材未跑、"阶段 5 未开工"、
"会写 `materials/calib/` + `basketball.vmt`"），在本窗口那半里**逐条更正**并写明当前事实。
追加用了"临时文件 + `Add-Content -Encoding utf8`"（避免整篇重写覆盖对方、也避免给文件插 BOM）。

**③ ⚠️ 用户否掉了备份功能**：「我觉得备份功能大可不必，覆盖就覆盖呗，大不了再调材质的事」。
现状是每次写好都备份到 `materials\_pbr2phong_backup\<时间戳>\` + 留写入清单。**诚实评估**：正常循环里
被覆盖的几乎都是**我们自己上一次的产物** → 备份是垃圾；备份唯一真有价值的场景 = 覆盖**不是我们写的**
文件（当初确实靠它救回过用户原始的 `basketball.vmt`）。给出两档（A 完全不备份 / B 只对"不在我们写入
清单里"的文件备一次）。

**④ ✅ 两件事拍板 + 阶段 6 开工（用户 2026-09-25）**：
- **「高光锐度」= A（保留现状：允许素材级覆盖）** —— 用户原话「A，记得md里也要加一句我确定用A的事」。
  已写进 `实施计划.md` §5.7 作为**明写的例外**：`curve.sharpness_gain` 只是**乘数**（不改公式形状），
  而傻瓜滑杆本来就该作用于"当前这套素材"；仍被拒绝的只有公式本体两项。
- **备份/撤销 = A（完全不备份）** —— 用户此前原话已明说"备份大可不必"；含义：**阶段 6 的"撤销"项一并取消**
  （没有备份就没有可撤销的东西），代价已知并接受：**覆盖了不是本工具写的文件就再也回不来**。
  「同名冲突停下来问」与「只导出不部署」开关**保留不变**（他没要求改这两个）。
- **阶段 6 开工**（用户原话"可以开始阶段6"）：`--onedir` 打包 + 双语 README + MIT/Qt 许可 + SmartScreen 提示。

### 2026-09-25 · 第十四轮：补"第一次运行"这条线（用空配置目录当新机器，当场查出三处）

**做法**：新增 `tests/test_first_run.py`（**28 项**）——把 `PBR2PHONG_HOME` 指到一个**还不存在的
临时目录**，等于"这台机器第一次双击启动"，然后把**用户最开始那几下**全点一遍：什么都没选就点
「开始转换」/「校验模型」、拖错文件夹、认到素材但没填材质名、切语言、关窗口。
判据是"界面到底说了什么人话"，所以把 `QMessageBox` 换成记录器（既不死等用户点，又能断言弹框原文）。

**① ⚠️ 拖错文件夹时界面像坏了（真问题）**：`load_folder` 扫到 0 套时只是把标签变回
"还没有选择素材" —— 用户拖了上一级目录，看到的就是"什么都没发生"，会以为**拖拽功能是坏的**。
现在弹框说人话（"这个文件夹里没找到能认的贴图：<路径>；请选里面直接放着 PNG 的那个文件夹，
而不是它的上一级"）+ 状态栏同步。**这是用户第一个动作就可能撞到的地方，比任何参数都致命。**

**② 状态栏漏了一句英文调试文本**：`scan {folder} → {n} set(s)` 直接显示在用户面前
（违反自己定的"状态栏别露调试信息"，是上一轮留下的漏网）。

**③ 切换语言时状态栏不跟着翻译**：页面都换了，底部还挂着上一句中文 —— 双语是这阶段的硬要求，
不能半截。`log()` 现在可以带 i18n 的 key（`log_key()`），切语言时重新渲染；自由文本（错误原因）原样保留。

**④ 顺手做「`.mdl` 也能拖进来」**：用户的动作是"拖素材夹 + 挑模型"，那就别让他为模型多点三步
（能拖就别点的延伸）。

**验证**：`test_first_run.py` **28 项**、`test_gui_flow.py` **46 项**、`test_pipeline.py` **65 项**全绿；
截图重出（拖拽提示改成两行也没挤坏布局）。

### 2026-09-25 · 第十三轮：阶段 5 补完 §9.1 最后两件事 + 报出"平法线图"

**① 结束汇总那一行（实施计划 §9.1 明写、之前漏了）**：跑完在表格下面出现
「完成：成功 x / 跳过 y / 失败 z」+ 三个按钮 —— **`打开输出目录` / `打开日志` / `复制失败原因`**。
按钮按结果自动灰掉：**没跑过就整行不显示**（不留空控件），没失败就禁用"复制失败原因"，
失败原因格式是 `材质组：原因` 一行一条，直接进剪贴板 —— 用户不用再去输出目录里翻 `log.txt`。

**② 取消原来"点不动"**：worker 只在"两套素材之间"检查 `_cancel`，而一套 2048² 素材要跑十几秒
（三次 VTFCmd）。现在在进度回调里插**取消检查点**（`Cancelled` 异常），慢阶段之间就能打断，
该套标成 `跳过 / 已取消`。**中断留下的半套产物不会被写进 `phong_input.json`**，所以重跑必然重做 ——
不会出现"半成品冒充成品"。状态栏也从"已取消"改成"正在取消…"（点了不等于已经停了，别撒谎）。

**③ ⭐ 顺手报出"平法线图"**：用户的真实素材 `ShuiMa` 那张法线图**整张 R=G=128、B=255**（平的），
他却以为有凹凸效果。这种图**翻不翻 G、挂不挂 `$bumpmap` 都一样**，我们必须明说，
否则他会以为是我们压平的。`pack.build` 现在算法线图 R/G 与 128 的最大偏差，<3 就警告：
"法线贴图是平的（R/G 几乎都是 128）→ 模型上不会有任何凹凸，回去看看烘焙是不是没勾上法线"。
（判据：**用户素材的缺陷要如实报，不要默默替他兜住** —— 他自评"我在 blender 做的材质确实不太行"。）

**验证**：`test_gui_flow.py` **46 项全绿**（新增 5 项：汇总行出现/与状态栏一致/两个打开按钮可用/
没失败时禁用复制/取消检查点抛不抛）、`test_pipeline.py` **65 项全绿**（新增 2 项回归：平法线要报、
真有起伏不报）、CLI 在真实素材 `ShuiMa` 上跑通并**当场打印出平法线警告**（VTF 版本/格式照旧全对）。

### 2026-09-25 · 第十二轮：阶段 5 收尾（双击就能跑 + 自测清单 + 终于看到真实渲染）

**① 让用户"双击就能跑"**：新增工作区根目录的 `启动PBR2Phong.bat`，以及
`PBR2Phong/GUI自测清单.md`（11 步走完清单，每步都写"**应该看到什么**"）——
按实施计划 §9.9 的规矩：交付带交互的东西必须附「操作说明 + 预期现象」（早先有个 POC 被评过"没用明白"）。

**② 补上工具路径设置**：之前报错信息里承诺"在设置里指定 VTFCmd 路径"，可那个设置**根本不存在** →
现在有了（自动检测优先 + 可手动指定 + 记进 `gui.json`）。

**③ 删掉一个死控件**：「记住输出位置，以后不再问」—— 输出位置已由实施计划定为
"直接写进 materials + 本地留档"，那个勾选框勾不勾都没用。**面向大众的工具不该有摆设。**

**④ ⚠️ 启动器一开始是坏的（真跑才发现，两条我踩了个遍）**：
- cmd.exe 用 **OEM 代码页**读 `.bat` → 我写的中文提示被读成乱码，**然后当成命令去执行**
  （`'闈?..' 不是内部或外部命令`）
- **只有 LF 没有 CR** → cmd 错拆 `rem` / `if (...)` 块，`cd /d "%~dp0PBR2Phong"` 被从 `\P` 处劈开
→ 已改成 **CRLF + 纯 ASCII**（中文提示写进程序与自测清单）。**判据：交付任何"给用户双击的脚本"之前，一定真跑一次。**

**⑤ ⭐ 意外收获：能看到真实渲染了。** 之前 HLMV 在本机开不出来，所以一直只能用离屏截图
（那版中英混排有"糊字"假象，是离屏字体库的问题）。这次发现 **Qt 走真平台插件时窗口能正常开出来**
（stderr 干净），进程活着时用 `PrintWindow(hwnd, dc, 2)` 抓窗口即可 ——
**系统字体、中英混排完全正常**，比离屏截图可信得多。

**验证**：`test_gui_flow.py` **37 项全绿**、core 单测 63 项、CLI 两条路、启动器真跑通过。
**阶段 5 只剩**：用户自己双击跑一遍（这是它的验收标准），以及 v2 的「结果对比」页。

### 2026-09-25 · 第十一轮：目标收尾 + 清理残留 + 阶段 4（与官方深化对照）

**① 目标收尾**：用户在水马模型上确认 **"跑通了，游戏里正常"** → 阶段 0 + 阶段 1
（含最后那条"能在 HLMV/游戏中看到一次正确效果"）**全部完成**。

**② 清理实验残留**（用户选"清掉"）：还原了他原来的 `basketball.vmt`（从 `_pbr2phong_backup\20260925-024359\`，
自动挑出**不含 `calib/` 的那份**才动手）、删掉 `materials\calib\`（13 文件 / 12.1 MB）与
`materials\custom\pbr_test\`（4 文件 / 0.8 MB）；`ShuiMa` 产物、备份与写入清单保留。

**③ 阶段 4：与官方素材深化对照**（`阶段0_实测/exp9_官方对照深化.py` → `out/exp9/对照报告.md`）。
做法上想了半天"不同贴图怎么逐像素比"，最后找到一把**共同的尺子**：
**法线图每个像素 (R,G,B) 解出来必须是单位向量** —— 这条对官方素材同样成立，于是能逐像素验。
结果：

| | \|n\| 均值 | 偏差>10% 占比 | B≥128 占比 |
|---|---|---|---|
| ★ 我们 ShuiMa_normal | **1.000** | 0.00% | 100% |
| 官方 coach_head_normal | **1.000** | 0.06% | 100% |

→ **通道布局（R=x, G=y, B=z）理解正确，绿通道方向与 Source 一致**（两侧都满足同一条物理约束）。
另外实证：官方**角色**把 Phong 遮罩放**法线 alpha**（均值 46.7、全黑 13%）、
**武器**放**底色 alpha**（全黑 59.9%）→ 与我们"角色档 mask_carrier=normal / 武器档 =basecolor"一致。

**④ 顺手体检出用户素材的一点情况**：ShuiMa 的**源法线完全是平的**
（B 恒 255、R/G 标准差 ≈0.003），所以这个模型拿不到表面细节；对照官方 `coach_head_normal`
的 B 均值是 252.5。已写进报告提示 —— 可能是道具本来就平，也可能烘焙时没把高模细节烘进去。
→ 顺带记下待办：**工具应当在"法线是平的"时给人话警告**。

### 2026-09-25 · 第十轮：交付自检（不看画面也能证明数据是对的）

HLMV 在本机跑不起来、游戏又只能由用户开，所以"看到一次正确效果"这条我无法自己完成。
退而求其次做了 **`阶段0_实测/exp8_交付自检.py`**：把**实际躺在 `materials/custom/ShuiMa/` 里**的
三个 VTF 解回来，跟源素材与我们的计算逐项核对 —— **12 项全过**：

| 检查 | 结果 |
|---|---|
| 产物规格 | 三个都是 **VTF 7.4 / 2048²**，底色 DXT5+8bit alpha、法线 DXT5+`NORMAL`、指数 DXT1+`ANISOTROPIC` |
| 底色 RGB vs 源 | 平均差 **1.04**（DXT5 的正常误差） |
| 底色 **alpha == 算出的高光遮罩** | 平均差 **0.05** |
| 法线 R/B 未被动过 | 平均差 **0.00** |
| 法线 **绿通道 == 源取反** | 对取反差 **0.00** vs 对原样差 **1.00** → 翻转确实生效 |
| 指数 **R == 粗糙度算出值** | 平均差 **0.75** |
| 指数 G == 金属度 / B 恒 0 | 0.01 / 0 |
| 两个 VMT 引用的 3 张贴图 | 按**大小写敏感**全部命中 |

→ 结论：**交给用户的这套文件，数据是对的**；剩下只有"人眼在游戏里看一眼"。

### 2026-09-25 · 第九轮：D 题用规格结案 + 真素材暴露的一个严重 bug

**① D 题（法线绿通道）不用人眼也结案了**：VDC 的 `Normal_map.html` 与 `Bump_map.html` 都写着
*"A bump map should be rendered in Tangent space and use vector directions **X+ Y− Z+**"*，
并把绿通道定义为 *"0 = up、128 = forward、255 = **down**"* —— **Source 是 Y−**，而 Blender/OpenGL 是 Y+，
→ **必须翻绿**，代码默认正确。另 grep 了 Auto Bake v1.5：它**不做**任何法线约定转换（照搬 GL 输出），
所以读它的产物一律要翻。标定变体 23/24 降级成"可选目视确认"。

**② 🐞 真素材抓出一个严重 bug（合成素材永远碰不到）**：
`pack._gray()` 读灰度图时用了 `arr[:, :, :3].mean(axis=2)`，`.mean()` 返回的是 **0~255 的 float**；
而下游约定是"uint8 = 0~255、float = 0~1"，于是**整张粗糙度被 clip 成 1.0，
指数贴图整片算错（该是 7 的地方全变成 0），一声不响**。
合成测试素材用的是**单通道** PNG（走 `arr[:, :, 0]` 那条分支），恰好把这个 bug 完美藏住了。
—— 这是"真素材不可替代"最好的例证，比任何解释都有说服力。

修法与防线：
- `_gray()` 取完平均**回到 uint8**（语义不再含糊）
- 在 `curves._to01` / `phong._as01` 加**守门人**：遇到 >1 的 float **直接抛错**，
  而不是 clip 成 1 —— 这类"静默算错"比崩掉难查得多
- 加回归测试（用 **RGB 三通道**的灰度图构造，正是踩雷那条路）
- **单测 59 → 62 项全绿**

**③ 验收第 2 层（与官方统计对照）做出来了**：`阶段0_实测/exp7_验收对照.py`。
修复后我们的 exp R 均值 **83.4** / 中位 **7**（E≈5），落在官方 9 张 `_exp` 的区间内
（官方均值 9.5~173、中位 10~189）；遮罩均值 121（官方武器 33.5），同量级。
→ 实施计划 §9.4 的第 2 层验收有了可复跑脚本。

**④ 修完后重新转换并重新部署了 ShuiMa**（`materials/custom/ShuiMa/`，清单
`_pbr2phong_manifest_20260925-072713.json`）——**之前部署的那一版指数贴图是错的**，
现在才是对的。

### 2026-09-25 · 第八轮：A 题结案（方案 A 成立）+ 真实素材端到端跑通

**① 🎯 全项目最大分叉关闭**：用户跑了 `标定问答.bat`：
- `[A1]` 变体 01（带 albedotint）→ **两半颜色不同**（一半偏红/暖、一半白）
- `[A2]` 变体 02（不带）→ **两半一样**（都是白的）

只切换这一个参数就决定了两半是否分色，对照组完美 → **`$phongalbedotint` + exponent 贴图 G 通道
在 L4D2 确实生效** → **方案 A「不压黑」正式成立**，不必退回压黑派。
（`[D1]/[D2]` 用户都答"看不出立体感"→ 细条纹设计不合格，已重做为大圆包 23/24 等他看。
`[B1]` 答"最像 0 号位置"，与 E5 的大光斑方向一致，但只有一个目测点，仍以官方交叉验证的"线性 1..150"为准。）

**② 真实素材端到端跑通**：用户给了水马素材（`JNU Map\props\shui_ma\textures\ShuiMa`，带真
`_mbakery.json`）与两个模型（`3mshui_ma.mdl` / `shui_ma.mdl`）。
为此补上了计划里 v1 的「**读 `.mdl` 自动取路径**」：新增 `--model`，从 MDL 读出权威的
`$cdmaterials=custom\ShuiMa\` 与材质名 **`Red_Plastic` / `White Tape`**（后者名字带空格），
并支持"**一套贴图 → 多个 VMT**"（多材质槽共用一张图集的常见情况）。
产出 3 PNG → 3 VTF(2048², 7.4) → 2 VMT，写进 `materials/custom/ShuiMa/`；
`cli/validate` 复查两个模型 **0 问题**。
真素材也确认了清单结构：type key 用的是 **`shader.normal`**（不是我预设里优先的 `standard.normal`）。

**③ 在真素材上当场撞到三个真 bug（这才是真素材的价值）**：
1. **"跳过已成功"把 `--deploy` 一起跳掉**了（跳过判定在部署之前 return）→ 已修：跳过时仍然执行部署。
2. **道具预设照抄了 CS:S 冷却塔的 `$basemapluminancephongmask 1`** —— 它让引擎改用底色的**亮度**
   当高光遮罩，**把我们辛苦算好的 alpha 遮罩整个作废**。已从预设里删掉，并把 fresnel 从
   那个特殊值 `[5 5 60]` 换回正常值。
3. **遮罩放进底色 alpha 时，必须显式写 `$basemapalphaphongmask 1`**，否则引擎会去读 `$bumpmap`
   的 alpha。已做成代码里的不变量（自动补 + 在报告里说明）。

**单测仍 59 项全绿**；另发现 ShuiMa 是**非金属**（金属度均值 0.01）→ 高光会是白的，
属正常（要看方案 A 的染色效果得拿金属材质）。

### 2026-09-25 · 第七轮：阶段 2 的三层参数模型（用户还没回话，继续往下推）

按实施计划 §5.7 把**三层继承**落成代码 `core/settings.py`：

- **① 全局默认**（A 类换算规则）：曲线标识、遮罩公式、AO 混合比例、色彩空间、暗化开关、翻法线开关
- **② 预设档**（B 类观感与身份）：从 `phong.PRESETS` 展平，含 `mask_carrier` / `use_exponent_texture` / 全部 `vmt.*` 参数
- **③ 素材级覆盖**：任何键都能覆盖，**但 `curve.*` 会被明确拒绝**（用户拍板"曲线只到预设档这一层"）

**每一项都带来源标签**（`全局默认` / `预设：武器` / `你改过`）——这是为了 GUI 那句"当前值 + 来源"，
避免用户陷进"我到底改没改过这个"的迷雾。`report_line()` 直接产出
「这套 = 武器预设 + 覆盖了 2 个参数」，写进 `phong_input.json`。

**文件落点**：`配置/config.json`（全局默认）+ `配置/presets/<名>.json`（可存多套），
已导出五套内置预设（含 `玻璃_投掷物.json`）。CLI 新增 `--config` / `--presets-dir` / `--set 键=值`（可重复）。
指纹改成用**解析后的参数**算，所以改 `config.json` 或预设也会让指纹变（重跑不会误跳过）。

**踩到的 bug（自己的）**：
1. **预设名 `玻璃/投掷物` 带斜杠，直接当文件名会写成子目录 → 写盘报错**。已加
   `preset_filename()` 做 sanitize（真名仍完整存在文件里的 `名称` 字段）。
2. 改了 `fingerprint()` 签名后忘了改测试调用 → 测试当场报 TypeError（这就是测试的价值）。
3. 又踩了一次 PowerShell `@"…"@` 把 `$phongboost` 插值吃掉的坑（已记过 lesson，这次是使用内联命令时又犯）。

**测试**：新增 13 项断言（继承优先级、来源标签、曲线锁定、未知预设报错、配置读写往返、
预设名带斜杠安全落盘），**core 单测共 59 项全绿**。

### 2026-09-25 · 第六轮：阶段 3 的批量与确定性（不依赖用户，先做）

标准的那条验收还卡在用户（HLMV 起不来、问答脚本还没跑），所以按计划往下推**不依赖用户的**阶段 3：
`cli/convert.py` 现在具备 —— 多套**串行**处理、**单个失败不影响其它**（失败原因进汇总）、
每套写 `phong_input.json`（输入映射 / 预设 / 覆盖项 / **指纹** / 产物清单 / 警告）、
**重跑默认跳过已成功的**、`--force` 全部重跑、结束打印「成功 N / 跳过 K / 失败 M」。
指纹 = 输入文件（名字+大小+修改时间）+ 所有影响结果的选项 的 sha256 前 16 位。

**又抓到自己一个 bug（这次的类型值得记）**：写 `phong_input.json` 的"产物清单"时，我把
PNG 与 VTF 两个 dict 直接合并（`list(pngs.items()) + list(vtfs.items())`），而两边的键都叫
`basecolor`/`normal`/`exp` → **后写的把先写的覆盖掉，PNG 从记录里整个消失了**，而且不报错。
是打印记录、肉眼核对时发现的。已给键加前缀（`png_*` / `vtf_*`）。
→ 教训：**合并两组同构数据时不加前缀 = 静默丢数据**。

**测试**：新增 6 项断言（指纹稳定性、换参数/换输入会导致指纹变化、指纹一致且产物齐全才跳过、
产物缺失不跳过），**core 单测共 46 项全绿**。

### 2026-09-25 · 第五轮：补完最后一段链路 + 把「用户回报」这件事的工具做出来

**① 阶段 1 的最后一段链路补验**：`cli/convert.py --deploy` 之前从没跑过（标定包那次走的是
`calib/build.py` 的部署）。这次用合成素材真跑了一遍：
`materials/custom/pbr_test/` 落地了 3 个 VTF + 1 个 VMT，并生成清单
`_pbr2phong_manifest_20260925-031022.json`。→ **阶段 1 的全链路（素材夹 → 3 张 PNG → VTF → VMT →
写进 L4D2 materials）已由产品代码走通**，只剩"进 HLMV 看到正确效果"这一条（要用户）。

**② 针对"用户回报"这个瓶颈做了工具**：观察到用户已经在用切换器（材质被切过好几个变体），
但他要逐个手点 12 个变体、还要把现象写成话 —— 摩擦太大。于是做了
`阶段0_实测/标定包/标定问答.bat`（+ `.ps1`）：只带他走 **4 个最关键的变体**
（01 / 02 判 A 题；08 / 09 判 D 题），每步只需按一个字母，**答案自动写成 `你的回答.txt`**，
结束时自动还原材质。选项设计成"a/b/c"单选而不是自由描述，就是为了让他少打字、我也好判读。
（做法上：`.ps1` 必须存成**带 BOM** 的 UTF-8，否则 Windows PowerShell 5.1 会把中文读成乱码；
已用 `Parser::ParseFile` 做语法检查、并确认四个变体都能被通配匹配到。）

### 2026-09-25 · 第四轮：验 PNG→VTF 的往返（朝向 + 量化误差）

之前只验到"文件生成了、尺寸对了"，没验"里面的像素还是不是我们写的那张"。补了
`阶段0_实测/exp6_vtf_roundtrip.py`，结果三条：

1. **VTF 行序与 PNG 一致，不需要翻转**（上红/中绿/下蓝的测试图往返一致）→ 早先对官方图的分析
   （如 `v_shotgun_a` 的 alpha 遮罩）没有上下颠倒。
2. **往返误差**：底色 DXT5 平均 0.4~0.6、**alpha 无损**；法线 DXT5 平均 1.2~1.7、最大 10（≈4.5°）；
   指数 DXT1 的 R 平均 0.49、最大 4。
3. **指数贴图保持 DXT1**：折算到指数域，绝对误差平均 0.29、最大 2.34，**只占满量程 1~150 的 1.6%**
   → 与官方 9 张 `_exp` 全用 DXT1 一致。

⚠️ **我自己一个指标写错了**：一开始打印"指数域**相对**误差"，最大值 70%，看着很吓人——但那是
**粗糙端**（E 本来只有 1~3）的比值，绝对差极小。已改成同时打印绝对误差并标注"别用相对误差下判断"。
（教训同类：**指标选错会把结论带偏**，比代码 bug 更隐蔽。）

🔎 **顺手发现的工具坑**：`Copy-Item` 会**保留源文件的 LastWriteTime** —— 所以"看 `basketball.vmt`
的修改时间"根本判断不出用户什么时候切换过材质（时间戳永远是变体文件自己的生成时间）。
这次误判过一回。判断用户有没有动作，得看内容而不是时间戳。

### 2026-09-25 · 第三轮：v1 的「校验模型」做完 + 确认 HLMV 在本机跑不起来

**尝试自己进 HLMV 看效果（失败，但值得记）**：发现 `hlmv.exe` / `hlmvplusplus.exe` 都有
`-screenshot` 命令行开关（还有 `-game`/`-width`/`-height`），本想自己渲染一张标定图、
不必麻烦用户。结果：**不管给不给参数、命令行还是 GUI，进程都是立刻 `exit=1`**，没有任何输出、
也不产文件（Steam 在跑，排除了这个原因）。→ **游戏侧验证只能靠用户**，这条路别再试了。

**顺手发现用户正在用标定包**：`materials/custom/Basketball/basketball.vmt` 现在装的是
**`06-参照-E150`**，不是部署时的 `01-标定-带albedotint` —— 说明切换器已经在用了。
（这也让下面的校验器当场抓到一个真问题：06 是标量指数、没有 `$phongexponenttexture`，
而它带着 `$phongalbedotint 1`，那个参数在没有指数贴图时是不生效的。）

**新增 v1 功能：校验模型**（`core/validate.py` + `cli/validate.py`）
拿编译好的 `.mdl` 当权威，查四件事：① VMT/VTF 是否在引擎期望的位置 ② VMT 里的
`$basetexture`/`$bumpmap`/`$phongexponenttexture` 指向的 VTF 是否存在 ③ 大小写是否与 MDL
一致 ④ 有没有 `no_material`。顺带加了解析 VMT 的能力（`core/vmt.parse`，认得官方那种
`patch { include ... }` 结构）。**对用户 9 个真实模型跑通**，抓到 3 处真问题：
`basketball.mdl` 的大小写不符（`Basketball` vs `basketball.vmt`）、`sportsground.mdl` 的
`no_material`、以及上面那条 `$phongalbedotint` 缺指数贴图。

**测试**：新增 7 项断言（VMT 解析、patch/include、贴图缺失判拒绝、大小写与不存在能区分），
**core 单测共 40 项全绿**。

### 2026-09-25 · 第二轮：把映射数学写了，端到端跑通（用合成素材）

**没等用户**，先把不依赖游戏判断的部分做完了。新增：

- **输入层 `core/source_io.py`**：认 Material Bakery 的产物。schema 是从 Auto Bake v1.5 的
  `core/imported.py` 读出来的**格式事实**：`_mbakery.json` 是
  `{"format":"material_bakery/textures","version":1,"group":…,"textures":{"<type_key>":{"file":…,"size_x":…}}}`
  ——⚠️ `textures` 是**按 type_key 索引**的，要先建"文件名→条目"反查表。
  另外把它那套文件名反解规则（`Common Parts 1-BaseColor-2k.png`、`BodyRoughness-2048.png`、
  `-1024px`、`1024x512` 都要认）自己也实现了。
  ⚠️ **许可边界**：Auto Bake 是 **GPL v2+**，本项目 MIT → **只借鉴格式事实，不抄代码**。
- **`core/curves.py`**：指数映射（线性 1..150，按 §0.6 #12 的离线证据）+ 遮罩 `(1−r)³×1.1` + 通用 LUT。
- **`core/phong.py`**：通道合成 + **四套预设**（角色身体/角色头/武器/道具/玻璃，数值全来自官方 VMT）。
- **`core/pack.py`**：三张输出图 + 尺寸规则（只放大不缩小）。
- **`cli/convert.py`**：素材夹 → 3 张 PNG → VTF(**7.4**，格式按官方语料：底色 DXT5 无额外标志、
  指数 DXT1+ANISOTROPIC、法线 DXT5+NORMAL) → `.vmt` →（可选）写进 materials + log.txt。
- **测试**：`tests/make_synthetic_set.py` 造合成素材，`tests/test_pipeline.py` **33 项断言全绿**
  （曲线端点与单调、通道不串位、尺寸规则、文件名解析、对真实 `school_gate.mdl` 的命名断言）。

**踩到并修掉的 bug（这次的教训很有价值）**：
- `curves.phong_mask()` 把 uint8 的 0..255 当成 0..1 直接 clip → **整张高光遮罩全变 0**。
  ⚠️ 而我的单测**居然通过了**——因为只断言了 r=0/r=1 两个端点，clip 之后端点碰巧还对。
  是"把产物 PNG 的 alpha 逐点采样打印出来"才发现的（中段采样 = 0）。
  → 已修（加 `_to01()` 统一入口），并**在测试里补了中段值断言**。
- `imaging.save()` 传 (H,W,1) 给 Pillow 的 `"L"` 模式会报 TypeError（要先 squeeze 成 (H,W)）。
- `core/vtf.py` 把标志位 0x0020 标成了 `HINT_DUDV`，实际是 `HINT_DXT5`；而且我给底色多加了这个
  官方根本不用的标志（官方底色只有 `EIGHT_BIT_ALPHA`）→ 已按官方语料对齐。
- `log.txt` 用 UTF-8 无 BOM 写，Windows 记事本/PowerShell 读成乱码 → 改 `utf-8-sig`
  （但 `.vmt` 保持无 BOM，免得引擎的 VMT 解析器被 BOM 噎住）。

**验证方式（这轮刻意做的）**：不只看"跑没跑通"，而是把产物 PNG **逐点采样打印**：
`exp.R = [255,255,91,21,4,1,0]`（0.073 以下顶格、之后掉得很快，符合 0.8/r²）、
`exp.G = [0,0,255]`（金属度）、`exp.B` 恒 0、`base.alpha` 中段 60（遮罩被 AO 调制）、法线 G 被翻转。

**仍未做**：拿**真实** MB 素材跑一遍；进 HLMV 看一次效果。两者都要等用户。

### 2026-09-25 · 阶段 0 收尾：标定包 + 最小链路（用户拍板"标定包 + 最小链路一起做"）

用户三个决定：① 标定包与最小链路**一起做**（不写一次性脚本）；② 载体用 `basketball.mdl`，
"你缺游戏目录权限就直接申请"；③ 工程目录名 **`PBR2Phong/`**。

**起了工程骨架** `PBR2Phong/`（全部是"数学无关"的基础设施，标定结论不会推翻它们）：
- `core/imaging.py` PNG 读写 / numpy 互转 / 通道工具
- `core/vtf.py` 调 VTFCmd + **校验产物真的生成了**（不信退出码，这是实测教训）+ 读 VTF 头部
- `core/naming.py` 读 `.mdl` 拿 `$cdmaterials` + 材质名（含大小写敏感查盘）
- `core/vmt.py` 生成 `.vmt` 文本（支持 HDR/dxlevel 覆盖块）
- `core/deploy.py` 写进 materials：备份 + 清单 + 一键还原
- `calib/build.py` 标定包生成器 ＝ **阶段 1 垂直切片的雏形**（造图→PNG→VTF→VMT→写入）

**映射数学（curves/phong/pack）故意没写** —— 等标定结论，避免实施计划 §0.2 警告的返工。

**标定包已生成并已部署**（写进 L4D2 未被沙箱拦）：
- 7 张标定贴图 → 7 个 VTF（`materials/calib/`）；12 个 VMT 变体（`阶段0_实测/标定包/vmt/`）
- `materials/custom/Basketball/basketball.vmt` 已替换为 `01-标定-带albedotint`，原文件备份在
  `materials\_pbr2phong_backup\20260925-024359\`，写入清单 `_pbr2phong_manifest_20260925-024359.json`
- 切换器 `标定包/切换材质.bat`（双击，带还原选项 `R`）；说明 `标定包/操作说明与预期现象.md`
- 设计要点：16 档 R 通道竖带 + **白字编号直接画在底色上**（这样即使在球面上也能认出是哪一档）；
  G 通道上下半分（满染色/不染色）；数字分上下两处画，避开 G 分界线
- 拿 `basketball.mdl` 试手时立刻验证了 naming+大小写检查：MDL 里是 `Basketball`、磁盘是
  `basketball.vmt`，工具自动按磁盘真实拼写落地

⏳ **等用户回报 5 项现象**（A albedotint 是否生效 / B exponent 映射 / C 非 2 次幂 / D 法线绿通道 /
E alpha→反射），回报后定 core 的数学并进阶段 1。

### 2026-09-25 · 开工：阶段 0 离线实测（在"标定包"那一段之前做的）

用户原话：**"目录下有一份实施计划.md，照着这个，你可以开始"** → 视为规矩 ① 的"开始"。

按实施计划 §0.2「第一件事：不要直接写 core，先做实测」执行，**一行 core 代码都没写**，
先把能离线做掉的实测做完了。完整报告：`阶段0_实测/阶段0-实测报告.md`；脚本与产物在 `阶段0_实测/`。

**实测结论（10 条，详见实施计划 §0.6）**：
1. VTFCmd **不做**法线通道重排（`-flag NORMAL` 只写标志位，四象限色卡逐字节相同）→ 绿通道得我们自己翻
2. VDC 双页证实：**Source = DirectX 约定、Source 2 = OpenGL 约定**，Blender 是 OpenGL → 要翻绿
3. **`$phongexponentfactor` 在 L4D2 完全不存在**（57 个 DLL 里都没这个字符串；VDC 标注 only in Source 2013 MP/TF2）→ 公式要重写
4. **`$phongdisablehalflambert` 在 L4D2 不存在** → 已从实施计划属性面板删除
5. 尺寸不是 4 的倍数时 **VTFCmd 静默失败且退出码仍为 0** → 必须检查产物是否存在
6. 4 的倍数的非 2 次幂尺寸照收；非 2 次幂也能生成 mip；默认输出 VTF 7.3（可选 7.2/7.4/7.5）
7. `-srgb` 不写 SRGB 标志位
8. MDL v49 读通：`mstudiotexture_t.sznameindex` 是**相对本结构自身**的偏移（第一版就在这踩坑）
9. **纹理表本身就是模型材质清单** → `sportsground.mdl` 直接读出 `no_material`
10. **实拍到一个真的大小写陷阱**：`basketball.mdl` 写 `Basketball`、磁盘是 `basketball.vmt`（Linux srcds 会挂）

⭐ **顺手造出的通用手段**：VMT 参数名是编译进引擎 DLL 的字符串字面量 →
**在 `Left 4 Dead 2\bin\*.dll` 里查字符串就能判"这参数在 L4D2 支不支持"**，比读 VDC 的 since 图标更硬。
用它查出 6 个 L4D2 不认识的参数（见报告 §1.1）。

⭐ **引擎自己招供**：`stdshader_dx9.dll` 里带着报错串
`material %s has a normal map and an envmapmask.  Must use $normalmapalphaenvmapmask.`
→ 证实实施计划 §5.2「法线图与独立 `$envmapmask` 互斥」的判断。

**踩到并修掉的坑**（都是我自己的 bug，不是环境的）：
- `vtfio.py` 读未压缩 VTF 时返回了 (N,4) 扁平数组没整形 → 四象限取样全错；修好后未压缩/压缩结果才对得上（**这是"先造色卡再对照"这个做法救回来的**）
- `exp3_mdl_check.py` 把"找不到"当成"存在"（判断写反了）→ 断言立即可见
- `exp4_param_support.py` 里中文引号写成了 ASCII 引号 → SyntaxError

**验证强度**：`vtfio` 对着 L4D2 materials 下 31 个真实 VTF 做"头部+各 mip 尺寸之和 == 文件大小"，单帧全部吻合；
`mdl_reader` 对着用户 9 个真实模型，解析出的材质路径 9/9 命中磁盘上真实存在的 VMT。

**未做（需要进游戏/HLMV++，等用户）**：`$phongalbedotint` 是否生效（决定方案 A vs 压黑派）、
exponent 通道真实映射、非 2 次幂 VTF 引擎能否读、法线绿通道游戏内确认、basecolor alpha 反转归属。
→ 下一步是产出"标定实验包"（16 档粗糙度渐变 + 对照 VMT），一次测完。

*（其余历史段落见下）*

---

## 5. 本次对话总结

- 用户的判断是对的：**Phong 贴图本质上只是"数学转换 + 通道打包"**，所以转换器不需要 Blender 渲染管线，甚至不需要 Blender；形态因此从"Blender 插件"改成**独立程序**。
- 转换器最大的价值不在"批量"，而在**带实时 Phong 预览的调参台**（曲线可拖、参数即时看效果）——否则它只是个脚本。
- **讨论已基本收敛**。定下的是：目标（L4D2）、形态（独立程序 + 纯 Python 核心 + CLI）、输入层（不绑死 MB 的适配器 + 前缀分组 + 固化 `phong_input.json`）、输出配方（basecolor/normal/exp 三张 + alpha 归属按类别预设）、金属方案（A 不压黑）、VMT（第一版就生成，含属性面板与预设）、落地（直接写 materials，冲突时询问）、VTF 工具链（VTFCmd 自动化，用户全程不用打开 VTFEdit）。
- 全程**没有写任何项目代码**，只做了资料调研、源码核对与归档；等用户说"开始"。
- **下一步**：① 产出"标定实验包"（16 档粗糙度渐变 + 金属/非金属 + 对照 VMT/VTF），在 HLMV++/游戏里
  一次测掉 `$phongalbedotint` 是否生效、exponent 真实映射、非 2 次幂 VTF、法线绿通道、alpha 反转；
  ② 标定结论回填后，才动 `core`（曲线 + exponent 映射 + 遮罩）。
- 阶段 0 离线实测的完整结论见 `实施计划.md` §0.6 与 `阶段0_实测/阶段0-实测报告.md`。
