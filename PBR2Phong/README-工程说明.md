# PBR2Phong 工程

把 PBR（金属度/粗糙度）贴图转换成 **Left 4 Dead 2（起源1）** 用的 Phong 贴图 + `.vmt` + `.vtf`。

- **唯一权威文档**：工作区根目录 `../实施计划.md`（先读 §0 开工指引 + §0.6 实测结论）
- **开发日志**：`../PBR to Phong.md`
- **阶段 0 实测**：`../阶段0_实测/`（含标定包生成器产出的实验包）

## 目录

```
core/     纯 Python 基础设施：不 import 任何 GUI、不 print（可 CLI 单测）
  imaging.py   PNG 读写 / numpy 互转 / 重采样（只放大由调用方负责）
  source_io.py 认 Material Bakery 的素材（manifest 优先，否则文件名反解）
  curves.py    ★ 换算曲线：指数 R 通道、Phong 遮罩、控制点↔LUT（GUI 唯一的数学依赖）
  phong.py     通道合成（exp 的 R/G、遮罩、法线翻绿、压黑派退路）+ **五套**官方预设
  pack.py      三张输出图 + 尺寸规则（各自取尺寸、只放大不缩小）
  settings.py  ★ 三层参数继承（素材级 > 预设档 > 全局默认）+ 每项的"来源"标签
  pipeline.py  ★ 转换流程（**GUI 与 CLI 共用同一份实现**，绝不复制）
  vtf.py       调 VTFCmd 转 VTF（校验产物、默认版本 7.4）
  naming.py    读 .mdl 拿 $cdmaterials + 材质名（引擎权威路径）
  vmt.py       生成 .vmt 文本 + 解析（认得 patch/include）
  validate.py  校验模型：拿 .mdl 当权威查产物位置 / 贴图存在 / 大小写 / no_material
  deploy.py    写进 materials（同名冲突停下来问；⚠️ **不备份、不写清单、不可撤销** —— 用户 2026-09-25 拍板）
cli/convert.py  端到端命令行：素材夹 → 3 张 PNG → VTF → .vmt →（可选）部署
                多套串行、单个失败不影响其它、写 phong_input.json、重跑默认跳过已成功（--force 重跑）
cli/validate.py 校验模型（`--all` 扫 models\custom 下全部）
gui/main.py     PySide6 界面（**5 页**：① 转换 ② 预览 + 调参 ③ 参数表 / 材质属性 / 自由键值
                ④ 导出 ⑤ 关于 + 状态栏进度·取消 + 后台线程 + i18n 接线；版式 = `GUI測試/假GUI/`）
i18n.py         双语文案表（约 155 条；每个参数 = 直译标签 + 常驻人话解释）
run_gui.py      打包入口（源码运行等价 `python -m gui.main`）
build_exe.py    打 onedir 包（PyInstaller；产物 `../dist/PBR2Phong/`）
calib/build.py  标定实验包生成器（阶段 0 用，实验已结束）
tests/          **十三个套件共 557 项**：test_pipeline 110 / test_gui_flow 97 / test_first_run 29 /
                test_brush 39 / test_hlmv 24 / test_layout 52（零滚动 + 5 页版式 + 漏键/串语言/来源列/解释截断/片号/Markdown + 眼睛档零滚动）/
                test_vtf_encoding 13 / test_neutral_params 39（默认值逐位一致锁）/ test_preview 28 /
                test_sliders 29 / test_presets 51（21 档预设 / 材质属性必填 / 术语表 / 附带两项 / 13-E 眼睛官方对齐）/
                **test_transparency 26（透明裁剪：底色 alpha 保住 / VMT 只写 `$alphatest` / 没法线不许静默吞 / 没 alpha 要出声）**/
                **test_warnings 20（12 单：警告 = 码 + 参数；27 条中文锚点逐字比对 / 全码英文渲染无中日韩字 / 逐码覆盖 / 旧 json 兼容 + 14-A 的 log 可读化）**
                另有 shot_gui.py（离屏截图与控件文字清单）、check_exe.py（真启动打包好的 exe 并抓图）

**跑测试的前提**（逐套件；缺前提的检查会**打印一行说明并跳过**，不会把整片报红 —— 公开仓库 / CI 上这很重要）：

> 🆕 **14-E：全量跑法** = `python PBR2Phong/tests/run_all.py` —— **默认只打一行汇总**（例：`13 套件 · 557 项 · 失败 0`），
> 失败才列失败套件与那几条 ✗；`--verbose` 出明细、`--only test_pipeline,test_warnings` 只跑指定套件、`--list` 列名字。
> **日常只跑受影响的 1~3 个套件**（改哪儿跑哪儿的地图写在 `_task/README.md`「测试与 token 经济性」），
> **全量留给片收口 / CI**（`.github/workflows/tests.yml`：push 与 PR 都在 windows-latest 上跑一遍）。

| 套件 | 前提 |
|---|---|
| 全部 | Python 3.11 + `PySide6` / `numpy` / `Pillow`；跑 GUI 类的建议 `QT_QPA_PLATFORM=offscreen` |
| 要出 VTF 的（`test_pipeline` 的端到端那条 / `test_gui_flow` 的转换段 / `test_presets` 的 VMT 段 / `test_brush` 的产物自检 / **`test_transparency` 整片**） | 本机有 **VTFCmd.exe**（Source SDK / VTFLib；`core/vtf.py` 会自动找常见位置，也可 `--vtfcmd` 指定）；**没有 → 说明并跳过**（`test_transparency` 会整片跳过，其余只跳那几段） |
| **需要 L4D2 安装**的几条（`test_pipeline` 的命名层与 `--list-materials`、`test_gui_flow` 的 13-B 三条） | `…\Left 4 Dead 2\left4dead2\models\custom\school_gate.mdl` 在（脚本里是硬编码路径，本机实测用）→ **没有就跳过**（合计约 16 条） |
| `test_presets` 的 13-E 段 / `test_brush` 的产物自检 | 要工作区里的 `Textures/survivors/**`（官方语料）与 `阶段0_实测/vtfio.py` —— **都不随公开仓库分发** → 缺了就说明并跳过 |
| `test_gui_flow` / `test_presets` | 仓库里带 `测试素材/合成素材/**`（26 KB，可 `tests/make_synthetic_set.py` 重生成） |
| `test_layout` / `test_preview` / `test_sliders` | 要有 `C:\Windows\Fonts`（`QT_QPA_FONTDIR`）才能量版式 |
```

## 现状（2026-09-27）

- **阶段 0 ~ 6 全部完成**，验收通过（用户实跑两轮："跑通了，游戏里正常" / GUI"一切正常，也有 log，没碰到错误"）
- **三层验收全落地**：core 单测 + `../阶段0_实测/exp8_交付自检.py`、`exp7_验收对照.py`（与官方统计对照）、用户游戏内确认
- 真实 Material Bakery 素材（ShuiMa 水马）已端到端跑通并部署到 `materials/custom/ShuiMa/`
- 此后又交付并验收：**笔刷模式 v1**（`LightmappedGeneric`）、**γ 一键 HLMV 按钮**、
  **GUI 改版 S1/S2/S2.5**、**06 版式落地**（5 页 + 零滚动）、**07 S3+S4**（预览接真图 + 4 大拉条 + 中性参数 + 曲线编辑器）
- **08 S5+S6（本片）**：预设 **5 档 → 21 档**（模型 11 / 笔刷 9 / 贴花 1，数值照抄官方普查）；
  **角色-眼睛走 `EyeRefract` 支路**；**材质属性改必填**（全局默认 `vmt.$surfaceprop=default`，界面上看得见）；
  **关于页术语表 8 → 12 条**（材质定义 / 每种开关 / Phong / 粗糙度→指数 / VTF·VMT，中英成对）；
  附带：第 2 页常驻说明「哪几根只改 vmt、预览不会变」+ 预览跟着第 1 页表格的选中项走
- **09 透明材质支持（本片）**：新参数 `alpha.cutout`（默认 `False`，素材级可覆盖、进指纹）；
  打开后**高光遮罩强制走法线 alpha**（底色 alpha 留给你自己的透明）+ VMT 自动写 `$alphatest 1`
  并摘掉 `$translucent`；**没有法线图时宁可不放遮罩**也不静默吃掉透明；底色带透明但没开这个开关 → 体检警告；
  「植被」档默认不出遮罩 + 默认要透明；开关在第 3 页「材质属性」组常驻，跟着档走
- **10 残留小修（本片，08/09 验收时挂出来的四条）**：① **「材质属性」整组跟着预设档走**
  （表面类型 + 5 个常用开关 + 要透明；观感旋钮滑杆/曲线**不跟档**）；② `alpha.cutout` **进第 3 页参数表**（12 → 13 行，
  勾了就显示「你改过」）；③ **「来源」列走 i18n**（core 只出层标识，英文界面不再蹦「全局默认 / 预设：X / 你改过」）；
  ④ 勾了「要透明」但素材**没有可裁的地方** → 出体检警告（不再静默）
- **13-E 角色眼睛（本片）**：按官方 8 份 `EyeRefract` 实物**整套对齐**（`$Iris` 必填 / `$AmbientOcclTexture` 选填，
  `$Envmap "Engine/eye-reflection-cubemap-"` 结尾那个 `-` 原样保留）；第 3 页新增「眼睛专用图」两行，**跟着档走**。
  ⚠️ 两点使用说明：① **眼睛档仍会一并输出底色 / 法线 / 指数图**（那是既有产物链路，`EyeRefract` 用不到它们 ——
  **可以忽略、不用管**）；② 命令行指定虹膜图：`python -m cli.convert <素材> --preset 角色-眼睛 --set eye.iris=<图片路径>`
  （可选 `--set eye.ao=<图片路径>`）。缺虹膜图会当场给人话提示，不会静默兜底。
- **自动化检查 557 项全绿（13 套件）**（见上；缺 VTFCmd / L4D2 的少数几条会跳过并说明）
- **已重新打出 onedir 包**：`python build_exe.py` → `../dist/PBR2Phong/PBR2Phong.exe`（发布文档 `../README.md`、`../LICENSE`、`../THIRD_PARTY_LICENSES.md`）
  —— **14-B 起，这三份会由 `build_exe.py` 自动拷进 `dist/PBR2Phong/`**（包里带 Qt LGPLv3，许可文本必须随包）；
  ⚠️ 它们是**拷贝**：改了 `LICENSE`/`README.md`/`THIRD_PARTY_LICENSES.md` 就要**重打一次**。
- **下一步**：用户在打包版上照 `GUI自测清单.md` 的 7d / 7e / 7f 走一遍（叶子透明 + 切档重放）；`实施计划.md` §9.9 / §9.8 两处改写（一类）

## 铁律

1. **数学只在 core 里做一次**：GUI 与 CLI 都只搬运数据，绝不各自实现映射。
2. **core 不 print**：要报告就返回结构化的东西，由 CLI/GUI 决定怎么显示。
3. **不凭记忆断言引擎行为**：参数支不支持用 `bin\*.dll` 查字符串，贴图格式看实物。
4. **单测别只断言端点**：踩过坑——端点碰巧正确、中段全错（见 `curves._to01` 的注释）。

