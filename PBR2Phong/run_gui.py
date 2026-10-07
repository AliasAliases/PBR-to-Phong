# -*- coding: utf-8 -*-
"""打包入口（源码运行等价于 `python -m gui.main`）。

存在意义：PyInstaller 需要一个**脚本**当入口，而 `gui/main.py` 是包内模块。
打包时它会被分析成 `gui.main` + `core.*` + `i18n` 一整套；源码运行时则自己把
工程目录塞进 `sys.path`，两种跑法行为一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):          # 源码运行：把工程目录加进搜索路径
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from gui.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
