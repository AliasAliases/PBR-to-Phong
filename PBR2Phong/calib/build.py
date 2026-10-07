"""标定实验包生成器 —— 实施计划阶段 0 的收尾，也是阶段 1「垂直切片」的雏形。

它打通了最窄的端到端链路：
    造图 → PNG → 调 VTFCmd 出 VTF → 生成 VMT → 写进 L4D2 的 materials

**它不改任何映射数学**（那要等标定结论），只负责把"看得见的东西"摆到游戏里。

用法：
    python -m calib.build                 # 只生成到 阶段0_实测/标定包/
    python -m calib.build --deploy        # 顺便写进 L4D2（会先备份原文件）

标定要回答的 5 件事（实施计划 §8 + §5.8）：
    A `$phongalbedotint` + exponent 贴图 G 通道在 L4D2 是否生效  → 决定方案 A 还是压黑派
    B exponent 贴图 R 通道 → 实际指数的映射是什么（L4D2 没有 $phongexponentfactor）
    C 4 的倍数的非 2 次幂 VTF 引擎读不读
    D 法线绿通道要不要翻
    E basecolor 的 alpha 在 L4D2 是不是"不透明=反射、透明=哑光"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import deploy, imaging, naming, vmt, vtf  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE / "阶段0_实测" / "标定包"

L4D2 = Path(r"D:\SteamLibrary\steamapps\common\Left 4 Dead 2")
MATERIALS = L4D2 / "left4dead2" / "materials"
CARRIER_MDL = L4D2 / "left4dead2" / "models" / "custom" / "basketball.mdl"

SIZE = 512
BANDS = 16
TEX_DIR_NAME = "calib"          # VTF 在 materials 下统一放这里，便于整体删除

# ---------------------------------------------------------------- 造图

_DIGITS = {  # 3x5 点阵，不依赖任何字体文件
    "0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
}


def _draw_number(dst: np.ndarray, text: str, cx: int, cy: int, scale: int, color=(255, 255, 255)):
    w = (len(text) * 4 - 1) * scale
    x0 = cx - w // 2
    y0 = cy - (5 * scale) // 2
    for ch_i, ch in enumerate(text):
        glyph = _DIGITS[ch]
        for row in range(5):
            for col in range(3):
                if glyph[row][col] == "1":
                    x = x0 + ch_i * 4 * scale + col * scale
                    y = y0 + row * scale
                    dst[y:y + scale, x:x + scale, 0] = color[0]
                    dst[y:y + scale, x:x + scale, 1] = color[1]
                    dst[y:y + scale, x:x + scale, 2] = color[2]


def band_values() -> list:
    """16 档 R 通道值（0..255 均分）。"""
    return [round(i * 255 / (BANDS - 1)) for i in range(BANDS)]


def make_base() -> np.ndarray:
    """底色：饱和红 + 每档的白字编号（数字用来在模型上认出是哪一档）。"""
    img = imaging.solid(SIZE, SIZE, (200, 60, 60), 255)
    bw = SIZE // BANDS
    for i in range(BANDS):
        cx = i * bw + bw // 2
        for cy in (int(SIZE * 0.32), int(SIZE * 0.68)):   # 上下半各写一遍（G 通道分半）
            _draw_number(img, str(i), cx, cy, 4)
    return img


def make_base_gray() -> np.ndarray:
    return imaging.solid(SIZE, SIZE, (128, 128, 128), 255)


def make_base_alpha() -> np.ndarray:
    """底色 RGB 纯红，alpha 上半 255、下半 0（测 L4D2 的 alpha→反射行为）。"""
    img = imaging.solid(SIZE, SIZE, (200, 60, 60), 255)
    img[SIZE // 2:, :, 3] = 0
    return img


def make_exp(width: int = SIZE, height: int = SIZE) -> np.ndarray:
    """exponent 贴图：R = 16 档指数，G = 上半 255 / 下半 0（albedo 染色强度），B = 0。"""
    img = np.zeros((height, width, 4), np.uint8)
    img[:, :, 3] = 255
    bw = width // BANDS
    for i, v in enumerate(band_values()):
        img[:, i * bw:(i + 1) * bw, 0] = v
    img[: height // 2, :, 1] = 255          # G：上半满染色
    return img


def make_normal(flip_g: bool) -> np.ndarray:
    """一排横躺的圆管状凸起：让"凹凸是否反了"一眼可辨。"""
    y = np.arange(SIZE)[:, None]
    h = np.sin(2 * np.pi * 6 * y / SIZE)                 # 高度场
    dhdy = np.cos(2 * np.pi * 6 * y / SIZE) * (2 * np.pi * 6 / SIZE) * 60
    nx = np.zeros_like(dhdy)
    ny = -dhdy
    nz = np.ones_like(dhdy)
    length = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    nx, ny, nz = nx / length, ny / length, nz / length
    img = np.zeros((SIZE, SIZE, 4), np.uint8)
    img[:, :, 0] = np.clip(128 + nx * 127, 0, 255).astype(np.uint8)
    g = np.clip(128 + ny * 127, 0, 255).astype(np.uint8)
    img[:, :, 1] = (255 - g) if flip_g else g
    img[:, :, 2] = np.clip(128 + nz * 127, 0, 255).astype(np.uint8)
    img[:, :, 3] = 255
    return img


def make_dome(flip_g: bool) -> np.ndarray:
    """一个**大圆包**的法线图（不是细条纹）。

    为什么要换：细条纹在球面上太难看凸凹，用户反馈"两版看着都差不多"。
    一个大包就明显得多——**凸起会有一道跟着光走的亮月牙，凹坑正好相反**。
    """
    y, x = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32)
    r2 = ((x - SIZE / 2) ** 2 + (y - SIZE / 2) ** 2) / (SIZE * 0.34) ** 2
    h = np.exp(-r2) * 60.0
    dhdx = np.gradient(h, axis=1)
    dhdy = np.gradient(h, axis=0)
    nx, ny, nz = -dhdx, -dhdy, np.ones_like(h)
    n = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    img = np.zeros((SIZE, SIZE, 4), np.uint8)
    img[:, :, 0] = np.clip(128 + nx / n * 127, 0, 255)
    g = np.clip(128 + ny / n * 127, 0, 255).astype(np.uint8)
    img[:, :, 1] = (255 - g) if flip_g else g
    img[:, :, 2] = np.clip(128 + nz / n * 127, 0, 255)
    img[:, :, 3] = 255
    return img


def make_base_tick() -> np.ndarray:
    """灰底 + **可数刻度**（第 i 档画 i+1 根竖线）。

    为什么要换：原来的数字在球面上是**镜像**的（模型 UV 导致），
    6/9/2/5 会被认错。刻度只数根数，镜像和翻转都不影响判读。
    """
    img = imaging.solid(SIZE, SIZE, (90, 90, 90), 255)
    bw = SIZE // BANDS
    for i in range(BANDS):
        count = i + 1
        cx = i * bw + bw // 2
        x0 = cx - (count * 2 - 1) // 2
        for t in range(count):
            x = x0 + t * 2
            img[SIZE // 2 - 45: SIZE // 2 + 45, x:x + 1] = (255, 255, 255, 255)
    return img


def make_base_solid(rgb) -> np.ndarray:
    """纯饱和色底（A 题专用）：染色生效时高光会"融进底色里"，不生效则是刺眼的白斑。"""
    return imaging.solid(SIZE, SIZE, rgb, 255)


def make_exp_split(r_value: int = 100) -> np.ndarray:
    """A 题专用指数图：**R 恒定**（高光大小全程一样）、G 左半 255 / 右半 0。

    这样一颗球上同时出现"染色区"和"不染色区"，直接对比，不用换材质。
    """
    img = np.zeros((SIZE, SIZE, 4), np.uint8)
    img[:, :, :] = (r_value, 0, 0, 255)
    img[:, : SIZE // 2, 1] = 255          # 左半满染色
    return img


def make_exp_r_only() -> np.ndarray:
    """B 题专用指数图：只有 R 梯度、G 恒 0（不让染色干扰看大小）。"""
    img = np.zeros((SIZE, SIZE, 4), np.uint8)
    img[:, :, 3] = 255
    bw = SIZE // BANDS
    for i, v in enumerate(band_values()):
        img[:, i * bw:(i + 1) * bw, 0] = v
    return img


# ---------------------------------------------------------------- 变体定义

PHONG_COMMON = [
    ("$phong", 1),
    ("$phongboost", 20),
    ("$phongfresnelranges", "[.1 .5 1]"),
]


def variants() -> list:
    """返回 [(编号名, 说明, 要回答哪一题, [(键, 值), ...]), ...]"""
    base = [(k, v) for k, v in [("$basetexture", f"{TEX_DIR_NAME}/calib_base")]]
    out = []

    out.append(("00-基线-无phong", "只有底色，确认我们的 VTF 能被正常读出来",
                "—", base))

    out.append(("01-标定-带albedotint",
                "核心标定：R 通道 16 档指数 + G 上下半（上=满染色/下=不染色）",
                "A + B",
                base + [("$phongexponenttexture", f"{TEX_DIR_NAME}/calib_exp"),
                        ("$basemapalphaphongmask", 1), ("$phongalbedotint", 1)] + PHONG_COMMON))

    out.append(("02-标定-不带albedotint",
                "同上但去掉 albedotint —— 若两半高光变得一样，说明 01 的差异确实来自 G 通道",
                "A（对照）",
                base + [("$phongexponenttexture", f"{TEX_DIR_NAME}/calib_exp"),
                        ("$basemapalphaphongmask", 1)] + PHONG_COMMON))

    for e in (5, 20, 60, 150):
        out.append((f"{3 + (5, 20, 60, 150).index(e):02d}-参照-E{e}",
                    f"标量 $phongexponent {e}（没有指数贴图）—— 用来比出 01 里每档对应多少指数",
                    "B", base + [("$phongexponent", e), ("$basemapalphaphongmask", 1),
                                 ("$phongalbedotint", 1)] + PHONG_COMMON))

    out.append(("07-标定-非2次幂",
                "同 01，但指数贴图是 200×100（4 的倍数、非 2 次幂）",
                "C",
                base + [("$phongexponenttexture", f"{TEX_DIR_NAME}/calib_exp_npot"),
                        ("$basemapalphaphongmask", 1), ("$phongalbedotint", 1)] + PHONG_COMMON))

    for tag, name, note in (("08", "calib_normal_a", "绿通道原样（OpenGL 算法直出）"),
                            ("09", "calib_normal_b", "绿通道取反（我们预测这个才对）")):
        out.append((f"{tag}-法线{tag[-1].upper()}-{note}",
                    f"加 $bumpmap，{note}",
                    "D",
                    [("$basetexture", f"{TEX_DIR_NAME}/calib_base_gray"),
                     ("$bumpmap", f"{TEX_DIR_NAME}/{name}")] + PHONG_COMMON))

    out.append(("10-反射-alpha分半",
                "无 phong，开 $envmap，底色 alpha 上半 255/下半 0，看哪半在反光",
                "E",
                [("$basetexture", f"{TEX_DIR_NAME}/calib_base_alpha"),
                 ("$envmap", "env_cubemap"), ("$envmaptint", "[1 1 1]"), ("$envmapcontrast", 1)]))

    out.append(("11-反射-alpha分半-反转",
                "同 10 但加 $basealphaenvmapmask 1 —— 看是不是反过来了",
                "E",
                [("$basetexture", f"{TEX_DIR_NAME}/calib_base_alpha"),
                 ("$basealphaenvmapmask", 1),
                 ("$envmap", "env_cubemap"), ("$envmaptint", "[1 1 1]"), ("$envmapcontrast", 1)]))

    # ---------------- 第二轮：重做成"一眼可判"的版本 ----------------
    # 用户第一轮反馈：数字在球面上是镜像的（模型 UV 导致，认不对档位）；
    # 而且暗红底上的红色高光看不出来 → A 题问法失效。所以下面这三个重做。
    red = [("$basetexture", f"{TEX_DIR_NAME}/calib_base_red")]

    out.append(("20-重做A-染色开",
                "饱和红底 + 【R 恒定、G 左半满/右半 0】："
                "若染色生效，一半的高光会『融进红底』，另一半是刺眼白斑",
                "A",
                red + [("$phongexponenttexture", f"{TEX_DIR_NAME}/calib_exp_split"),
                       ("$basemapalphaphongmask", 1), ("$phongalbedotint", 1),
                       ("$phong", 1), ("$phongboost", 60), ("$phongfresnelranges", "[.1 .5 1]")]))

    out.append(("21-重做A-染色关",
                "和 20 完全相同，只去掉 $phongalbedotint —— 若 20/21 有明显差别就说明染色生效",
                "A（对照）",
                red + [("$phongexponenttexture", f"{TEX_DIR_NAME}/calib_exp_split"),
                       ("$basemapalphaphongmask", 1),
                       ("$phong", 1), ("$phongboost", 60), ("$phongfresnelranges", "[.1 .5 1]")]))

    out.append(("22-重做B-可数刻度",
                "灰底 + 【可数刻度】（第 k 档画 k 根竖线，镜像也不影响认读）+ R 梯度、G 恒 0",
                "B",
                [("$basetexture", f"{TEX_DIR_NAME}/calib_base_tick"),
                 ("$phongexponenttexture", f"{TEX_DIR_NAME}/calib_exp_r"),
                 ("$basemapalphaphongmask", 1),
                 ("$phong", 1), ("$phongboost", 60), ("$phongfresnelranges", "[.1 .5 1]")]))

    for tag, name, note in (("23", "calib_dome_a", "绿通道原样"),
                            ("24", "calib_dome_b", "绿通道取反（我们预测这个才对）")):
        out.append((f"{tag}-重做D-大圆包-{note}",
                    f"灰底 + 【一个大圆包】的法线图，{note}。"
                    "手电绕着扫：凸起会有一道跟着光走的亮月牙，凹坑正好相反",
                    "D",
                    [("$basetexture", f"{TEX_DIR_NAME}/calib_base_gray"),
                     ("$bumpmap", f"{TEX_DIR_NAME}/{name}"),
                     ("$phong", 1), ("$phongboost", 20), ("$phongfresnelranges", "[.1 .5 1]")]))
    return out


# ---------------------------------------------------------------- 主流程


def build_textures() -> list:
    tex = PACKAGE / "textures"
    jobs = [
        ("calib_base", make_base(), "BGRA8888", ()),
        ("calib_base_gray", make_base_gray(), "BGRA8888", ()),
        ("calib_base_alpha", make_base_alpha(), "BGRA8888", ()),
        ("calib_exp", make_exp(), "BGRA8888", ()),
        ("calib_exp_npot", make_exp(200, 100), "BGRA8888", ()),
        ("calib_normal_a", make_normal(False), "DXT5", ("NORMAL",)),
        ("calib_normal_b", make_normal(True), "DXT5", ("NORMAL",)),
        # ---- 第二轮重做的"一眼可判"版本 ----
        ("calib_base_red", make_base_solid((230, 30, 30)), "BGRA8888", ()),
        ("calib_exp_split", make_exp_split(), "BGRA8888", ()),
        ("calib_base_tick", make_base_tick(), "BGRA8888", ()),
        ("calib_exp_r", make_exp_r_only(), "BGRA8888", ()),
        ("calib_dome_a", make_dome(False), "DXT5", ("NORMAL",)),
        ("calib_dome_b", make_dome(True), "DXT5", ("NORMAL",)),
    ]
    made = []
    for name, arr, fmt, flags in jobs:
        png = imaging.save(arr, tex / f"{name}.png")
        made.append((name, png, fmt, flags))
    return made


def build_vtfs(tex_jobs) -> list:
    out = PACKAGE / "vtf"
    made = []
    for name, png, fmt, flags in tex_jobs:
        path = vtf.convert(png, out, fmt=fmt, alpha_format=fmt, flags=flags, output_name=name)
        made.append((name, path, flags))
    return made


def build_vmts() -> list:
    out = PACKAGE / "vmt"
    made = []
    for name, desc, answers, params in variants():
        text = vmt.render("VertexLitGeneric", params)
        made.append((name, desc, answers, vmt.write(text, out / f"{name}.vmt")))
    return made


def write_switcher(carrier_rel: str, target_dir: Path) -> Path:
    """生成给用户用的"换材质"菜单脚本（只改那一个 VMT，VTF 全部已就位）。"""
    vmt_dir = (PACKAGE / "vmt").resolve()
    mats = MATERIALS.resolve()
    lines = [
        "# PBR to Phong · 标定材质切换器（按提示输入编号）",
        f'$materials = "{mats}"',
        f'$vmtDir    = "{vmt_dir}"',
        f'$target    = Join-Path $materials "{carrier_rel}"',
        "",
        "if (-not (Test-Path $target)) { Write-Host \"找不到目标 VMT：$target\" -ForegroundColor Red; exit 1 }",
        "$files = Get-ChildItem $vmtDir -Filter *.vmt | Sort-Object Name",
        "Write-Host ''",
        "Write-Host '可用变体：' -ForegroundColor Cyan",
        "for ($i = 0; $i -lt $files.Count; $i++) { Write-Host ('  [{0,2}] {1}' -f ($i + 1), $files[$i].BaseName) }",
        "Write-Host '  [ R] 还原成原来的材质'",
        "Write-Host ''",
        "$pick = Read-Host '请输入编号（回车=退出）'",
        "if ($pick -eq 'R' -or $pick -eq 'r') {",
        "    $bak = Get-ChildItem (Join-Path $materials '_pbr2phong_backup') -Recurse -Filter '*basketball.vmt' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1",
        "    if ($bak) { Copy-Item $bak.FullName $target -Force; Write-Host \"已还原：$($bak.FullName)\" -ForegroundColor Green } else { Write-Host '没找到备份' -ForegroundColor Yellow }",
        "    exit 0 }",
        "if (-not $pick) { exit 0 }",
        "$idx = [int]$pick - 1",
        "if ($idx -lt 0 -or $idx -ge $files.Count) { Write-Host '编号不对' -ForegroundColor Red; exit 1 }",
        "Copy-Item $files[$idx].FullName $target -Force",
        "Write-Host \"已切换为：$($files[$idx].BaseName)\" -ForegroundColor Green",
    ]
    p = PACKAGE / "切换材质.ps1"
    p.write_text("\n".join(lines), encoding="utf-8-sig")

    # 双击即用：绕过 PowerShell 执行策略（很多人被这条卡住）
    bat = PACKAGE / "切换材质.bat"
    bat.write_text(
        "@echo off\r\nchcp 65001 >nul\r\n"
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "{p}"\r\n'
        "pause\r\n", encoding="utf-8")
    return p


def write_instructions(carrier_rel: str, vmt_list, answers_map) -> Path:
    rows = ["| 编号 | 变体 | 看什么 | 回答哪一题 |", "|---|---|---|---|"]
    for name, desc, ans, _ in vmt_list:
        rows.append(f"| `{name}` | {desc} | | {ans} |")
    text = f"""# 标定实验包 · 操作说明与预期现象

> 生成器：`PBR2Phong/calib/build.py`（这一套就是"PNG→VTF→VMT→写进 materials"的最小链路）
> 载体模型：`basketball.mdl`（球体，最适合看高光大小）
> 材质落点：`materials/{carrier_rel}`（原文件已自动备份）

## 一、怎么用

> ⚡ **最快路径**：双击 **`标定问答.bat`**。它只带你走 4 个最关键的变体（01 / 02 / 08 / 09），
> 每步只需按一个字母，答案会自动写进 `你的回答.txt`，结束时自动还原材质。不想逐个手点就用它。

1. 打开 **HLMV++**（`Left 4 Dead 2\\bin\\hlmvplusplus.exe`），加载 `models/custom/basketball.mdl`
2. 在材质/光照面板里把**光源调到一个能看到高光**的角度（HLMV 里可以拖光源方向）
3. 在工作区根目录运行 `阶段0_实测\\标定包\\切换材质.bat`，按菜单换材质，逐个记下现象
4. 全部看完一次回报即可（不用来回问）

## 二、变体清单

{chr(10).join(rows)}

## 三、每一题"该看什么、什么算成功"

### A · `$phongalbedotint` 到底生不生效（★ 决定全项目走向）
看 **01**：高光的**颜色**在上下两半是否不同。
- **不同**（一半偏红 = 染色生效，一半发白）→ **方案 A「不压黑」成立**，按原计划走
- **一样**（两半都是白高光）→ albedotint 不生效 → 必须退回**压黑派**（高光变灰白，金属靠 envmap 带色）
- 再对照 **02**（去掉 albedotint）：如果 02 两半一样、01 两半不同，结论就坐实了

### B · exponent 贴图 R 通道 → 实际指数
看 **01**：高光大小从第 0 档到第 15 档是否**单调**变化（0 档最大最糊、15 档最小最锐）。
再看 **03~06**（标量 `$phongexponent` 5 / 20 / 60 / 150）各是什么大小，
**说出 01 里哪一号数字的高光跟哪个标量最像**（例如"第 8 档 ≈ E20"）。
> 这一条决定曲线怎么写：VDC 说 R 通道映射成 1..150，我们怀疑不是线性，得实测。

### C · 非 2 次幂尺寸
看 **07**（指数贴图是 200×100）。能正常显示 = 引擎不吃"2 的幂"这套限制；
花屏/材质变粉红/纯黑 = 引擎读不了，那 VTF 阶段就必须帮用户缩到 2 的幂。

### D · 法线绿通道
看 **08** 和 **09**：贴图画的是一排**横躺的圆管状凸起**。
- 看着像**凸起的圆管** = 这一版绿通道是对的
- 看着像**凹进去的槽**（光一挪就明显不对）= 绿通道反了
> 我的预测是 **09**（绿通道取反）才对——VDC 说 Source 用 DirectX 约定、Blender 是 OpenGL。

### E · basecolor 的 alpha 在 L4D2 怎么用
看 **10**：底色 alpha 上半 255（不透明）、下半 0（透明）。开 `$envmap` 后：
- 只有**一半**在反光 → 说明 L4D2 确实"不透明=反射 / 透明=哑光"
- 两半都反光或不反光 → 行为跟文档不一样，要按实测写
再看 **11**（加了 `$basealphaenvmapmask 1`）：**应该正好反过来**。

## 四、看完之后

把现象发我，我会：
1. 把结论写回 `实施计划.md` §0.6 与 `阶段0_实测/阶段0-实测报告.md`
2. 按结论定下 `core/curves.py`（exponent 映射）与"方案 A / 压黑派"
3. 进入阶段 1 的正式垂直切片

## 五、撤掉这一套

- 还原材质：跑 `切换材质.ps1` 输入 `R`（或用 `core.deploy.restore()` 按清单还原）
- 清掉标定贴图：删 `materials/{TEX_DIR_NAME}/` 整个目录
- 备份与写入清单在 `materials\\_pbr2phong_backup\\` 与 `materials\\_pbr2phong_manifest_*.json`
"""
    p = PACKAGE / "操作说明与预期现象.md"
    p.write_text(text, encoding="utf-8")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 PBR2Phong 标定实验包")
    ap.add_argument("--deploy", action="store_true", help="顺便写进 L4D2 的 materials")
    ap.add_argument("--yes", action="store_true", help="遇到同名文件直接覆盖（不交互提问）")
    ap.add_argument("--materials", default=str(MATERIALS), help="L4D2 materials 目录")
    ap.add_argument("--carrier", default=str(CARRIER_MDL), help="载体模型 .mdl")
    args = ap.parse_args()

    materials = Path(args.materials)
    carrier = Path(args.carrier)
    print(f"工作区：{WORKSPACE}")
    print(f"标定包：{PACKAGE}")

    # 1) 载体模型的材质落点 —— 用引擎权威路径，并按磁盘真实大小写落地
    mdl = naming.read_mdl(carrier)
    rel_expected = mdl.expected_vmt_paths()[0]
    case_note = naming.check_path_case(materials, rel_expected)
    carrier_rel = rel_expected
    if case_note and case_note != "missing":
        print(f"⚠️ 大小写提示：{case_note}")
        carrier_rel = case_note.split("实际是 ", 1)[-1]     # 用磁盘上真实的拼写
    print(f"载体模型 {carrier.name} → $cdmaterials={mdl.cdmaterials} 材质名={mdl.textures}")
    print(f"材质落点：materials/{carrier_rel}")

    # 2) 造图 → VTF → VMT
    tex_jobs = build_textures()
    print(f"✓ 造了 {len(tex_jobs)} 张标定贴图 → {PACKAGE / 'textures'}")
    vtfs = build_vtfs(tex_jobs)
    for name, path, flags in vtfs:
        print(f"   VTF {name}: {vtf.read_info(path)}")
    vmt_list = build_vmts()
    print(f"✓ 生成 {len(vmt_list)} 个 VMT 变体 → {PACKAGE / 'vmt'}")

    # 3) 给用户的操作脚本与说明
    write_switcher(carrier_rel, PACKAGE)
    write_instructions(carrier_rel, vmt_list, None)
    print(f"✓ 切换器与说明 → {PACKAGE}")

    # 4) 可选：直接写进游戏
    if args.deploy:
        files = [(path, f"{TEX_DIR_NAME}/{name}.vtf") for name, path, _ in vtfs]
        files.append((PACKAGE / "vmt" / f"{vmt_list[1][0]}.vmt", carrier_rel))
        # ⚠️ 2026-09-25 起 `deploy.install` 不再备份、不再写清单（用户拍板 A），
        #    所以这里也没有"清单文件"可打印了。
        done = deploy.install(materials, files,
                              confirm=lambda c: True if args.yes else _ask(c))
        print(f"✓ 已写入 materials（{len(done)} 个文件）")
        for d in done:
            print(f"   {d.action} {d.dest}")
    else:
        print("\n（未部署。加 --deploy 就会写进 L4D2）")
    return 0


def _ask(conflicts) -> bool:
    print("目标位置已有同名文件：")
    for rel, why in conflicts:
        print(f"   {rel}  （{why}）")
    return input("覆盖它们？(y/N) ").strip().lower() == "y"


if __name__ == "__main__":
    raise SystemExit(main())
