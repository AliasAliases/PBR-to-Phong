"""落地层：把产物写进 L4D2 的 materials 目录。

**不备份、不撤销**（用户 2026-09-25 拍板 A，原话："我觉得备份功能大可不必，覆盖就覆盖呗，
大不了再调材质的事"）：
  · 覆盖就是覆盖 —— ⚠️ 覆盖掉**不是本工具写的**文件就再也回不来（用户已知并接受这个代价）
  · 安全底线只剩一条：**不静默覆盖** —— 目标已有同名文件时停下来，用 `confirm` 回调问用户
  · 历史：曾把被覆盖的文件备份到 `<materials>\\_pbr2phong_backup\\<时间戳>\\`、每次写入留
    `_pbr2phong_manifest_<时间戳>.json`，`restore()` 可一键撤销 —— 这一整套已按用户要求删除。

core 不 print、不弹窗——需要用户确认时用 `confirm` 回调（由 CLI/GUI 提供）。
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DeployedFile:
    dest: str          # 相对 materials 根
    action: str        # "新增" / "覆盖"


def install(materials_root: str | Path, files) -> list:
    """files: [(源文件, 相对 materials 的目标路径), ...]

    ⚠️ 冲突策略由调用方先定（`pipeline` 会先问「覆盖 / 跳过」再调这里），
    所以本函数只认"已经决定要写"的清单：目标有同名文件就直接覆盖。
    返回 [DeployedFile, ...]（哪些是新增、哪些是覆盖）。
    """
    root = Path(materials_root)
    if not root.is_dir():
        raise NotADirectoryError(f"找不到 L4D2 的 materials 目录：{root}")

    done: list = []
    for src, rel in files:
        src, dest = Path(src), root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        done.append(DeployedFile(rel.replace("\\", "/"), "覆盖" if dest.exists() else "新增"))
        shutil.copy2(src, dest)
    return done
