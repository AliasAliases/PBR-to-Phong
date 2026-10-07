# Hammer 笔刷路线（建筑 + 无缝贴图）

> **分支文档。** 上位权威 = `实施计划.md`（本项目所有决策以它为准；本文只写"笔刷线"这一支）。
> 立项：2026-09-25，用户决定**放弃"模型拆两套材质"**，建筑改走 **Hammer 笔刷 + 1024 无缝贴图**。
> 状态：**规格已核实，尚未开工**（模型路线仍在阶段 1~3 收尾）。所有 `⚠️ 待实测` 项见 §6。

---

## 0. 一句话

**同一套 PBR 素材，多开一个出口：生成笔刷能用的 `.vmt` + `.vtf`，在 Hammer 里直接选来铺墙。**

---

## 1. 为什么这条路合理（以及代价）

### 合理 —— 两条真理由

1. **明暗**：大建筑的明暗靠 **lightmap**。笔刷有 lightmap；模型（`prop_static`）只有**顶点光照** → 一大片平墙又平又块。
2. **没有"多材质"难题**：Hammer 里**每个面自由选材质**，窗户单独当一个 brush 贴玻璃即可 —— 不需要拆物体、不需要跑两次。

### 代价（硬）

⚠️ **L4D2 的笔刷着色器 `LightmappedGeneric` 不支持 Phong。** VDC 原文：

- `LightmappedGeneric.html`：`$phong` 标着 **"(in all games since [CS:GO icon]) (also in [Garry's Mod][Mapbase])"**
- `$phong.html`：**"Phong shading for LightmappedGeneric and WorldVertexTransition is only available in CS:GO engine branch, Strata Source."**（Mapbase 里另有一套不同实现）

→ 笔刷的高光/反射只能走**老派做法**：`$envmap` + 逐像素遮罩 + lightmap。
**模型路线的 Phong 数学（roughness→exponent、phong mask）在笔刷上完全用不上。**

---

## 2. 笔刷材质配方（工具要生成的）

| 用途 | 参数 | 素材来源 |
|---|---|---|
| 底色 | `$basetexture` | albedo |
| 法线 | `$bumpmap` | normal（**要翻绿**、**要无缝**） |
| 高光/反射遮罩 | **`$normalmapalphaenvmapmask 1`** ← 遮罩塞进**法线图的 alpha 通道** | roughness + metallic |
| 反射 | `$envmap env_cubemap` + `$envmaptint` / `$envmapcontrast` / `$envmapsaturation` | — |
| 材质属性 | `$surfaceprop`（脚步音、弹孔、贴花） | 用户在下拉里选 |

**为什么遮罩走法线 alpha**（VDC 原文）：

> "Rather than creating a whole new texture for a specular mask, you can embed one into the alpha channel of the `$basetexture` or `$bumpmap`. **Model materials with `$bumpmap` must do this.**"

**遮罩语义**：白 = 完全反射，黑 = 完全哑光（灰度图；带颜色则等于逐像素 `$envmaptint`）。

⚠️ **不能写 `$envmapmask`**：VDC 原文 —— "Warning: `$envmapmask` will not work with materials using `$bumpmap`… Except on … LightmappedGeneric(**only in Counter-Strike: Global Offensive**)" → **L4D2 上不能这么干**。

### 笔刷上「不要写」的清单

`$phong` / `$phongexponent` / `$phongexponenttexture` / `$phongboost` / `$phongtint` / `$phongalbedotint` / `$basemapalphaphongmask` / `$basemapluminancephongmask` / `$invertphongmask` / `$phongwarptexture`
→ 这些是 **VertexLitGeneric（模型）专用**，L4D2 笔刷上不存在。

`$envmaplightscale` → VDC 说 "since Alien Swarm"，但**我们扫过 L4D2 的 57 个 DLL，这个字符串根本不存在**（`阶段0_实测/out/exp4/param_support.md`）→ 不要写。

### 可以用（LightmappedGeneric 页面上真实存在的参数）

`$basetexture` `$bumpmap` `$ssbump` `$envmap` `$surfaceprop` `$detail` / `$detailscale` / `$detailblendmode` / `$detailblendfactor` `$translucent` `$alphatest` `$alpha` `$nocull` `$selfillum` `$lightwarptexture` `$seamless_scale` `$color` `$decalscale` `$basetexturetransform` `$nofog` `%keywords` `%tooltexture`

### 官方参考（就在工作区里）

- `Textures/props/mailboxwood01a.vmt`（**L4D2 笔刷**）：`$envmap env_cubemap` + `$basealphaenvmapmask 1` + `$envmaptint` + `$envmapcontrast` + `$envmapsaturation` —— 用**底色 alpha** 当遮罩
- `Textures/floor05.vmt`：`$bumpmap` + `$ssbump 1` + `$envmap` + **`$normalmapalphaenvmapmask 1`** + `$envmaptint` + `$envmapcontrast` —— 用**法线 alpha** 当遮罩，**正是我们要的写法**
- ⚠️ `floor05.vmt` 的**出处未标**（`Textures/` 根目录混了 L4D2 与 CS:S 的材质）→ 见 §6 #2
- 另注意：L4D2 多数世界材质**只有 `$basetexture` + `$surfaceprop`，完全没有高光**（地毯/屋顶/储物柜）→ "基础墙面地面不吃高光"再次被印证。**所以第一版可以不出遮罩，先把底色+法线跑通。**

---

## 3. 在 Blender 里做无缝素材：三条硬要求

### ① 绝对不能烘 AO / 阴影 / 大尺度明暗

笔刷的明暗 **100% 来自 lightmap**。烘进贴图的 AO 会**跟着平铺一起重复**，大老远就能看出规律 → 一眼假。
→ 无缝图里**只放局部细节**（砖缝、噪点、划痕），**一个像素的大尺度明暗都不要**。

### ② 法线图也必须无缝

底色无缝但法线有缝 → **光照上会出现一张网格状的接缝**，非常显眼。

### ③ `1024` 决定"多细"，世界尺寸由 Hammer 的 Texture Scale 决定

两者互相独立，别指望靠改分辨率调大小。官方定义（`$decalscale` 条目原文）：

> "Same as a brush face's texture scale value: **the number of units that each texel covers. Normally 0.25 or lower.**"

→ ✅ **用户在 Hammer++ 的 Face Edit Sheet 里实测确认（2026-09-25）**：**默认 0.25**；**调大 = 图案变大、重复变少**；调小 = 图案变小、重复变多 —— 与官方定义完全一致。

**换算表**（按"每个 texel 占 scale 个单位"推导；1 unit ≈ 2.54 cm，玩家高 72 units）：

| Texture Scale | 512 贴图铺 | 1024 贴图铺 | 2048 贴图铺 |
|---|---|---|---|
| 0.125 | 64 units | 128 units | 256 units |
| **0.25（默认）** | 128 units | **256 units** | 512 units |
| 0.5 | 256 units | 512 units | 1024 units |

→ 用法：先想好"一块砖在世界里应该多大"，再反推 scale。
　例：1024 贴图里横向 8 块砖、每块 20 cm（≈8 units）→ 一个 tile 覆盖 64 units → `scale = 64 ÷ 1024 = 0.0625`
→ **分辨率管"多细"，scale 管"多大"** —— 别靠改分辨率调大小。

### 怎么做出真正无缝的程序化纹理（**未核实完，先不写死**）

| 做法 | 特点 |
|---|---|
| 天然可循环的节点（Checker / Brick / Wave / Magic） | 最省事，但图案受限 |
| 镜像重复 | 一定连续，但会有可见对称 |
| **4D 噪声上环面**（把 u/v 映射成两个圆，喂给 Noise 的 4D 输入） | 真正无缝，要搭节点 |
| 后期修缝（GIMP 的 Make Seamless 之类） | 通用，但会牺牲细节 |

→ 你选定之后我再把具体节点连法写成步骤（含截图位）。

---

## 4. 在 Hammer++ 里铺上去（操作步骤）

**入口**：`D:\SteamLibrary\steamapps\common\Left 4 Dead 2\bin\hammerplusplus.exe`

1. **搭体块**：用 **Block 工具**在视图里拉方块当墙 / 屋顶（现代建筑用方块拼最省事）
2. **选材质**：打开**材质浏览器**，在 `Filter` 里输入材质名 → 选中 → 鼠标变成"贴图刷"
3. **刷上去**：在面的中心点一下 = 贴到这个面；按住左键拖过多个面 = 连刷
4. **调参数**：选中面 → 打开 **Face Edit Sheet（面编辑面板）**，里面有：
   - **Texture Scale**（世界单位 / texel，**默认 0.25**；改大 → 图案变大、重复变少，3D 视图里立刻能看到）
   - **Lightmap Scale（Luxel scale，默认 16）** —— 管**笔刷明暗的精细度**，与贴图大小无关（语义待核实，见 §6 #3b）
   - **Shift X/Y**、**Scale X/Y**、**Rotation**
   - **Justify**：Fit / Center / World / Face / Top / Bottom / Left / Right
   - **Treat as one**
   - **Alignment：World / Face** —— 无缝贴图铺墙基本都用 **World**，两面墙之间才不会错位
   - ⚠️ **除 Texture Scale 已实测外，上面其余字段都还没核实**（VDC 被反爬封着，无原文）
5. ⚠️ **Hammer 只认 `materials/` 下的 VMT + VTF，不认裸 PNG** —— 你的无缝图必须先经过工具转成材质

### 预期现象（做完应该看到什么）

- 贴图铺满整面墙，**边缘看不到接缝**（若看到一条明显直线 → 贴图本身不无缝，或法线不无缝）
- 调大 scale → 图案**变大**、重复变少；调小 → 变密
- 编译进游戏后，墙面明暗**随光照变化**（来自 lightmap），**不会**有跟着视角走的高光

> ✅ **已实测确认（2026-09-25）**：默认 **0.25**；**改大 → 图案变大、重复变少**，**改小 → 图案变小、重复变多**。
> **怎么打开这个面板**：3D 视图里用 Select 工具**选中一个面** → 按 `Shift+A`（贴图应用工具），或走菜单 `Tools → Face Edit Sheet`。
> 判据 = 面板顶部出现**那张贴图的缩略图**；空白 / 灰的 / 写着"多种材质"说明没选到面（这时 scale 框也填不进去）。

---

## 5. 和本工具的关系

| 段 | 模型路线 | 笔刷路线 |
|---|---|---|
| 认素材（MB 清单 / 前缀分组 / 通道打包图） | ✅ 共用 | ✅ 共用 |
| 图像处理（解图 / 尺寸 / 色彩空间） | ✅ 共用 | ✅ 共用 |
| **数学** | Phong（roughness→exponent、phong mask） | **另一套**（roughness/metallic → envmap 遮罩） |
| **VMT 模板** | `VertexLitGeneric` | **`LightmappedGeneric`** |
| PNG → VTF → 写进 `materials` | ✅ 共用 | ✅ 共用 |
| 部署 / 冲突 / 备份 / 撤销 | ✅ 共用 | ✅ 共用 |

> 命名也更简单：笔刷材质**不需要 `.mdl`**，就是 `materials/` 下的一个目录 + 材质名，你在 Hammer 的材质浏览器里直接选。

**阶段归属：待定。** 建议排在**与官方对照（阶段 4）之后** —— 两者共用前四阶段的基础设施，笔刷模式基本只是"换模板 + 换数学"，很薄。若想早点看到那栋楼立起来，插在阶段 3 之后也合理。

---

## 6. 笔刷线待实测清单

| # | 待验证 | 证据现状 | 怎么验 |
|---|---|---|---|
| 1 | `$normalmapalphaenvmapmask` 在 L4D2 **笔刷**上是否真生效 | VDC 原文认可这个替代法，但**没给 LightmappedGeneric 徽标**；L4D2 的 `materialsystem.dll` / `stdshader_dx9.dll` 里**有这个字符串** | 一张测试材质刷到一个小方块上，截图对比"有遮罩 / 无遮罩" |
| 2 | `floor05.vmt` 的出处（L4D2 还是 CS:S） | `Textures/` 根目录混源，未标 | 用 GCFScape 在 L4D2 的 VPK 里搜 `tile/floor05` |
| 3 | ~~Hammer Texture Scale 的默认值与方向~~ | ✅ **已结案 2026-09-25**（用户在 Hammer++ 面板实测：默认 0.25、改大变大、重复变少） | — |
| 3b | **Lightmap / Luxel Scale** 的语义与推荐值（笔刷明暗精细度） | 用户实测**默认 16**；它与世界单位 / 贴图尺寸的关系**未核实**（VDC 被封，无原文） | 改一档（如 16 → 8）编译后看阴影锐度与 BSP 体积变化 |
| 4 | 要不要 `$ssbump`（官方笔刷大量用 ssbump 而非普通法线） | 官方 `floor05` / `blue06` / `building_roof_01` 都用 `$ssbump 1` + `-ssbump` 贴图 | 待查：ssbump 贴图怎么产出、我们能不能生成 |
| 5 | 笔刷上到底需不需要遮罩 | **L4D2 多数世界材质压根没有高光**（只有 `$basetexture` + `$surfaceprop`） | 先出"底色 + 法线"最小版本，看效果再决定 |

---

## 7. 交付要求（沿用全局规矩）

任何带交互的交付物（工具 / 预览器 / 测试包）都必须附 **"操作说明 + 预期现象"** —— 界面上哪块是什么、该拖哪里、看到什么说明什么。
