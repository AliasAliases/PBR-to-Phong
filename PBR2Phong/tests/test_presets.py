"""S5 + S6 的验收测试（离屏跑）：21 档预设 / 材质属性必填 / 术语表 / 两个附带项。

对应 `_task/08-S5+S6-预设与术语表.md` §6 的判据 2~8。
「跑真转换、看产出的 .vmt」那几条会**真调 VTFCmd**（本机有；没有就自动跳过并说明）。

跑法：python tests/test_presets.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["PBR2PHONG_HOME"] = tempfile.mkdtemp(prefix="pbr2phong-presets-")

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402

import i18n  # noqa: E402
from core import imaging, phong, pipeline, settings, source_io, vmt, vtf  # noqa: E402
from gui.main import MainWindow  # noqa: E402

PASS, FAIL = [], []


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


def run_preset(folder: Path, out: Path, preset: str, route: str, name: str, sets=()) -> str:
    """真跑一遍转换（不部署），返回产出的 .vmt 文本。

    `sets`：素材级覆盖（13-E 眼睛档要用 `eye.iris=<图片>` 这种）。
    """
    opts = pipeline.ConvertOptions(
        source=str(folder), name=name, out=str(out / name), cdmaterials="custom",
        preset=preset, deploy=False, route=route, sets=tuple(sets),
        vtfcmd=str(vtf.find_vtfcmd() or ""))
    resolved = pipeline.resolve_options(opts, "", "")
    ms = source_io.scan_folder(folder)[0]
    got = pipeline.convert_set(ms, opts, resolved)
    vmt_path = Path(got["out_dir"]) / f"{name}.vmt"
    return vmt_path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    print("== S5+S6（21 档预设 / 必填 / 术语表 / 附带两项）==")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    folder = WS / "测试素材" / "合成素材"
    has_vtfcmd = bool(vtf.find_vtfcmd())
    if not folder.is_dir():
        check("合成素材存在", False, str(folder))
        return 1

    # ---------- 判据 2：21 档列全 ----------
    print("== 判据 2：21 档预设 ==")
    kinds = phong.preset_kinds()
    check("一共 21 档", len(phong.PRESETS) == 21, str(len(phong.PRESETS)))
    check("构成 = 模型 11 / 笔刷 9 / 贴花 1",
          kinds == {"model": 11, "brush": 9, "decal": 1}, str(kinds))
    check("模型路线 11 档", len(phong.presets_for_route("model")) == 11,
          str(phong.presets_for_route("model")))
    check("笔刷路线 9 档 + 贴花 1 = 10 档",
          len(phong.presets_for_route("brush")) == 10,
          str(phong.presets_for_route("brush")))
    check("每档都有 desc / mask_carrier / use_exponent_texture",
          all(p.get("desc") and "mask_carrier" in p and "use_exponent_texture" in p
              for p in phong.PRESETS.values()))
    check("明确不做的三类没有被加进来",
          not ({"skybox", "particle", "vgui"} & set(phong.PRESETS)))

    # ---------- 下拉按路线过滤（GUI 层）----------
    win = MainWindow()
    win.resize(1280, 760)
    win.show()
    win.page_convert.load_folder(folder)
    app.processEvents()
    combo = win.page_tuning.panel.cmb_preset
    names_model = [combo.itemText(i) for i in range(combo.count())]
    check("模型路线的下拉 = 11 档", len(names_model) == 11, str(names_model))
    win.page_convert.rb_route_brush.setChecked(True)
    app.processEvents()
    names_brush = [combo.itemText(i) for i in range(combo.count())]
    check("切笔刷后下拉换成 10 档（9 档笔刷 + 贴花）",
          len(names_brush) == 10 and "贴花" in names_brush and "玻璃·窗户" in names_brush,
          str(names_brush))
    check("笔刷下拉里没有模型档（不会产出四不像的 VMT）",
          "角色-身体" not in names_brush and "武器-第一人称" not in names_brush)
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()

    # ---------- 判据 5：材质属性必填 ----------
    print("== 判据 5：材质属性必填 ==")
    check("标题里没有「可选」",
          "可选" not in win.t("attr.title") and "必填" in win.t("attr.title"), win.t("attr.title"))
    sp_box = win.page_config.cmb_sp
    check("表面类型下拉常驻可见（第 3 页）",
          sp_box.isVisibleTo(win.page_config) and sp_box.count() == 18,
          f"{sp_box.count()} 项（17 + (默认)）")
    check("下拉当前就有一个看得见的值（不是空的）",
          bool(sp_box.currentData()) or sp_box.currentIndex() == 0, str(sp_box.currentData()))
    check("全局默认里就有 vmt.$surfaceprop（这才是「必填」的底气，而不是静默兜底）",
          settings.GLOBAL_DEFAULTS.get("vmt.$surfaceprop") == "default",
          str(settings.GLOBAL_DEFAULTS.get("vmt.$surfaceprop")))

    # ---------- 判据 3 / 4：真跑 3+1 档，看产出的 .vmt ----------
    print("== 判据 3 / 4：真跑几档，看产出的 .vmt ==")
    if not has_vtfcmd:
        check("本机有 VTFCmd（没有就跳过这几条）", False, "没找到 VTFCmd.exe → 跳过")
    else:
        with tempfile.TemporaryDirectory(prefix="pbr2phong-vmt-") as td:
            out = Path(td)
            v_body = run_preset(folder, out, "角色-身体", "model", "Body")
            v_inf = run_preset(folder, out, "感染者", "model", "Inf")
            v_brush = run_preset(folder, out, "玻璃·窗户", "brush", "Glass")

            print("     角色-身体.vmt：" + v_body.replace("\n", " ")[:110])
            print("     感染者.vmt：" + v_inf.replace("\n", " ")[:110])
            print("     玻璃·窗户.vmt：" + v_brush.replace("\n", " ")[:110])

            check("角色-身体：boost 1.4 + 标量指数 5",
                  '"$phongboost" 1.4' in v_body and '"$phongexponent" 5' in v_body
                  and "$phongexponenttexture" not in v_body,
                  v_body.replace("\n", " ")[:90])
            check("感染者：boost 2 + 走指数贴图 + fresnel [1 1 1]",
                  '"$phongboost" 2' in v_inf
                  and "$phongexponenttexture" in v_inf and "[1 1 1]" in v_inf)
            check("玻璃·窗户（笔刷）：LightmappedGeneric + $surfaceprop glass",
                  v_brush.splitlines()[0].strip() == '"LightmappedGeneric"'
                  and '"$surfaceprop" "glass"' in v_brush,
                  v_brush.splitlines()[0].strip())
            check("玻璃·窗户里**一个 $phong 都没有**（笔刷不支持）",
                  "$phong" not in v_brush.lower())
            check("角色-身体里也有 $surfaceprop（必填的证据：默认值也写进去）",
                  "$surfaceprop" in v_body, "Body VMT has $surfaceprop")

            # ---------- 13-E：眼睛档 = **官方对齐的 EyeRefract**（原来"只出骨架"的行为已废） ----------
            print("== 13-E：角色眼睛（官方对齐 EyeRefract） ==")
            iris_png = out / "iris.png"
            imaging.save(np.dstack([np.full((16, 16), 120, np.uint8)] * 3), iris_png)
            ao_png = out / "eyeao.png"
            imaging.save(np.dstack([np.full((16, 16), 200, np.uint8)] * 3), ao_png)

            # 官方实物（**判据 2 的基准**）：8 份完全同构，取其一即可。
            # ⚠️ 14-D：公开仓库里**没有** `Textures/`（官方语料不传）→ 缺了就**说明并跳过**，不许报红。
            off_path = WS / "Textures" / "survivors" / "coach" / "coach_eyeball_l.vmt"
            if not off_path.is_file():
                print("   ⏭ 跳过 13-E 与官方语料的逐键对比：没找到官方眼睛 VMT 语料（**公开仓库里属正常**）")
                print(f"      期望位置：{off_path}")
                # 下面两条**不依赖语料**，照跑（保住"缺虹膜图必须出声"这条命脉）
                try:
                    run_preset(folder, out, "角色-眼睛", "model", "EyeNoIris")
                    check("13-E（无语料也成立）：缺虹膜图要出声", False, "居然跑成功了")
                except pipeline.MissingInput as e:
                    check("13-E（无语料也成立）：缺虹膜图 → 抛带码的异常 eye.iris",
                          e.code == "eye.iris", str(e.code))
                check("13-E（无语料也成立）：那句人话由 i18n 给（中英都有）",
                      "虹膜" in i18n.t("eye.need_iris", "zh")
                      and "iris" in i18n.t("eye.need_iris", "en").lower())
            else:
                off = vmt.parse(off_path.read_text(encoding="utf-8", errors="replace"))
                v_eye = run_preset(folder, out, "角色-眼睛", "model", "Eye",
                                   sets=(f"eye.iris={iris_png}",))
                got = vmt.parse(v_eye)
                print("     角色-眼睛.vmt：" + v_eye.replace("\n", " | ")[:200])
                check("13-E 判据 2：眼睛 VMT 的**键集与官方完全一致**（没给 AO 时按规格只少那一行）",
                      set(got) in (set(off), set(off) - {"$ambientoccltexture"}),
                      f"{sorted(set(got) ^ set(off))}")
                diff = {k: (got.get(k), off.get(k)) for k in off
                        if k not in ("$iris", "$ambientoccltexture") and got.get(k) != off[k]}
                check("13-E 判据 2：除 $Iris/$AmbientOcclTexture 外，**其余键的值逐字相同**",
                      not diff, str(diff))
                check("13-E 判据 3：负面锁 —— 没有 $basetexture / $phong / $bumpmap",
                      not any(k in got for k in ("$basetexture", "$bumpmap"))
                      and not any(k.startswith("$phong") for k in got), str(sorted(got)))
                check("13-E：$Envmap 结尾那个 `-` 原样保住",
                      got.get("$envmap") == "Engine/eye-reflection-cubemap-", got.get("$envmap"))
                check("13-E：$Iris 指向我们产出的虹膜图",
                      got.get("$iris", "").endswith("_iris"), got.get("$iris"))
                check("13-E：没给眼睛 AO → $AmbientOcclTexture **整行不写**",
                      "$ambientoccltexture" not in got, str(got.get("$ambientoccltexture")))
                check("13-E：虹膜图真的出了 VTF",
                      (out / "Eye" / "vtf" / "Eye_iris.vtf").is_file())

                v_eye2 = run_preset(folder, out, "角色-眼睛", "model", "Eye2",
                                    sets=(f"eye.iris={iris_png}", f"eye.ao={ao_png}"))
                got2 = vmt.parse(v_eye2)
                check("13-E：给了眼睛 AO → $AmbientOcclTexture 指我们的 _eyeao，且键集仍与官方一致",
                      got2.get("$ambientoccltexture", "").endswith("_eyeao")
                      and set(got2) == set(off), got2.get("$ambientoccltexture"))
                check("13-E：眼睛 AO 也出了 VTF",
                      (out / "Eye2" / "vtf" / "Eye2_eyeao.vtf").is_file())

                # 缺虹膜图 → **带码**的异常（人话由 CLI/GUI 过 i18n）
                try:
                    run_preset(folder, out, "角色-眼睛", "model", "EyeNoIris")
                    check("13-E 判据 5：缺虹膜图要出声（不是静默兜底）", False, "居然跑成功了")
                except pipeline.MissingInput as e:
                    check("13-E 判据 5：缺虹膜图 → 抛带码的异常 eye.iris", e.code == "eye.iris",
                          str(e.code))
                check("13-E 判据 5：那句人话由 i18n 给（中英都有，不是 traceback）",
                      "虹膜" in i18n.t("eye.need_iris", "zh")
                      and "iris" in i18n.t("eye.need_iris", "en").lower(),
                      i18n.t("eye.need_iris", "en")[:80])

                # ⭐ 必败样例自检：少写一个键，键集比对**必须**抓到（否则这锁就是空转的）
                real_render = vmt.render_eyerefract
                vmt.render_eyerefract = lambda iris, ao="": real_render(iris, ao).replace(
                    "$nodecal 1\n", "")
                try:
                    v_bad = run_preset(folder, out, "角色-眼睛", "model", "EyeBad",
                                       sets=(f"eye.iris={iris_png}",))
                finally:
                    vmt.render_eyerefract = real_render
                check("13-E 自检：**人为少写一个键必须报红**（不是空转的锁）",
                      set(vmt.parse(v_bad)) != set(off),
                      f"少了 nodecal 还是等同官方？{sorted(set(vmt.parse(v_bad)) ^ set(off))}")

    # ---------- 判据 6：术语表 ----------
    print("== 判据 6：术语表 ==")
    terms = " ".join(t for t, _zh, _en in i18n.GLOSSARY)
    need = ["surfaceprop", "Phong", "Exponent", "halflambert", "nocull", "translucent",
            "alphatest", "nodecal", "VTF", "VMT"]
    check(f"六类术语都有（{len(i18n.GLOSSARY)} 条）",
          all(k in terms for k in need), str([k for k in need if k not in terms]))
    check("每条都有中英两份",
          all(zh.strip() and en.strip() for _t, zh, en in i18n.GLOSSARY))
    bad = [t for t, zh, en in i18n.GLOSSARY
           if "**" in zh + en or "`" in zh + en or any("\u4e00" <= c <= "\u9fff" for c in en)]
    check("术语表里没有 Markdown 标记、英文版也没夹中文", not bad, str(bad))
    about_rows = win.page_about.table.rowCount()
    check("关于页真的把术语列出来了", about_rows == len(i18n.GLOSSARY), str(about_rows))
    cells = [win.page_about.table.item(0, c).text() for c in range(2)]
    check("关于页第一行有中英两份文字", all(cells), str(cells))

    # ---------- 判据 7：预设名 sanitize ----------
    print("== 判据 7：预设名带 / 时写盘不炸 ==")
    with tempfile.TemporaryDirectory(prefix="pbr2phong-preset-name-") as td:
        p = settings.save_preset(td, "玻璃/投掷物", {"vmt.$phongboost": 3}, desc="测试")
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
        check("落盘文件名已经 sanitize（斜杠变下划线）",
              p.name == "玻璃_投掷物.json", p.name)
        check("JSON 里保留完整真名", data["名称"] == "玻璃/投掷物", str(data.get("名称")))

    # ---------- 判据 8：两个附带项 ----------
    print("== 判据 8：附带两项 ==")
    panel = win.page_tuning.panel
    hint = panel.lbl_vmt_only.text()
    check("附带①：界面上有那句「只改 vmt、预览不会变」的常驻说明",
          "预览" in hint and "vmt" in hint.lower(), hint[:60])
    check("附带①：英文版也有",
          bool(i18n.t("settings.vmt_only_hint", i18n.LANG_EN).strip())
          and "\u4e00" not in i18n.t("settings.vmt_only_hint", i18n.LANG_EN))

    prev = win.page_tuning.preview
    table = win.page_convert.table
    check("表格里有两套素材（Barrel / Couch）", table.rowCount() >= 2, str(table.rowCount()))
    table.selectRow(0)
    app.processEvents()
    cap0 = prev.left.caption
    img0 = None if prev.left.image_array is None else np.array(prev.left.image_array)
    table.selectRow(1)
    app.processEvents()
    cap1 = prev.left.caption
    img1 = None if prev.left.image_array is None else np.array(prev.left.image_array)
    check("附带②：换选中行 → 左框（源素材）换成那一套",
          cap0 != cap1 and "Couch" in cap1, f"{cap0} → {cap1}")
    check("附带②：换选中行 → 右框（产出）也跟着重算",
          img0 is not None and img1 is not None
          and (img0.shape != img1.shape or bool((img0[:, :, :3] != img1[:, :, :3]).any())),
          f"{None if img0 is None else img0.shape} → {None if img1 is None else img1.shape}")

    # ---------- 13-F：预设名的中英（只翻内置 21 档；自存档原样） ----------
    print("== 13-F：预设名中英（内置翻、自存档不翻、来源列分得清） ==")
    cfg = win.page_config
    panel = win.page_tuning.panel
    win.page_convert.rb_route_model.setChecked(True)
    app.processEvents()
    idx = panel.cmb_preset.findData("武器-第一人称")
    panel.cmb_preset.setCurrentIndex(max(0, idx))
    win.set_language("en")
    app.processEvents()

    def cjk(s):
        return any("\u4e00" <= ch <= "\u9fff" for ch in s)

    texts_en = [panel.cmb_preset.itemText(i) for i in range(panel.cmb_preset.count())]
    data_en = [panel.cmb_preset.itemData(i) for i in range(panel.cmb_preset.count())]
    check("英文下下拉显示英文名（一个中日韩字都没有）",
          bool(texts_en) and not any(cjk(t) for t in texts_en), str(texts_en)[:180])
    check("英文下 itemData 仍是**中文原名**（持久化数据不许被翻译）",
          all(d in phong.PRESETS for d in data_en), str(data_en)[:180])
    check("英文下 current_preset() 拿到的仍是**键**（中文原名）",
          cfg.current_preset() in phong.PRESETS, cfg.current_preset())
    cfg.refresh_sources()
    src_en = [cfg.src_table.item(r, 2).text() for r in range(cfg.src_table.rowCount())]
    leaked = [x for x in src_en if cjk(x)]
    check("**必败样例**：英文下「来源」列一个中文预设名都不许出现（旧代码这里是 `From preset: 武器`）",
          not leaked, str(leaked)[:200])
    check("英文下「来源」列真的是内置档的说法", any("From preset:" in x for x in src_en), str(src_en)[:200])

    # 自存档：**名字原样**，标签区分
    settings.save_preset(cfg.config_root, "我的测试档",
                         settings.resolve("角色-身体", {}, {}, {}).values)
    cfg.reload_presets(keep="我的测试档")
    app.processEvents()
    win.set_language("en")
    app.processEvents()
    texts2 = [panel.cmb_preset.itemText(i) for i in range(panel.cmb_preset.count())]
    check("自存档档名**原样显示**（不能替用户翻译他自己的命名）", "我的测试档" in texts2,
          str(texts2[-3:]))
    cfg.refresh_sources()
    src2 = [cfg.src_table.item(r, 2).text() for r in range(cfg.src_table.rowCount())]
    check("英文下来源列**分得清**内置档 / 自存档",
          any(x.startswith("From your preset: 我的测试档") for x in src2), str(src2)[:220])

    win.set_language("zh")
    app.processEvents()
    texts_zh = [panel.cmb_preset.itemText(i) for i in range(panel.cmb_preset.count())]
    check("中文下显示名不变（还是中文原名）", "武器-第一人称" in texts_zh, str(texts_zh)[:180])
    cfg.reload_presets(keep=phong.DEFAULT_PRESET)
    cfg.refresh_sources()
    src_zh = [cfg.src_table.item(r, 2).text() for r in range(cfg.src_table.rowCount())]
    check("中文下「来源」列仍是原来的口径（预设：…）",
          any(x.startswith("预设：") for x in src_zh), str(src_zh)[:200])

    win.close()
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败：" + "；".join(FAIL))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
