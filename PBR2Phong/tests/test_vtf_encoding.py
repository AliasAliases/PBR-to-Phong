# -*- coding: utf-8 -*-
"""VTFCmd 输出解码回归：**非 UTF-8（GBK）输出不许把原因吞掉**。

对应真 bug（`core/vtf.py`）：
    原来 `subprocess.run(args, capture_output=True, text=True, timeout=600)`
    按**当前 locale** 解码，而 VTFCmd.exe 的输出是 GBK。在 PYTHONUTF8=1 下
    subprocess 的读线程当场抛 UnicodeDecodeError 死掉，`proc.stdout` 变成 None
    → “没生成 .vtf”那条报错里的**原因那一段永远是空的**（用户准则：报错说人话）。

本测试锁死这个契约，**不需要本机装 VTFCmd.exe**（用 `sys.executable -c` 当假 VTFCmd）。

跑法：`python tests/test_vtf_encoding.py`
中文控制台先设：`set PYTHONUTF8=1` + `set PYTHONIOENCODING=utf-8`
（本测试正是要在 PYTHONUTF8=1 下通过。）
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))                      # PBR2Phong/

from core import vtf  # noqa: E402

PASS: list = []
FAIL: list = []
NUMBERS: dict = {}


def check(title, ok, detail=""):
    (PASS if ok else FAIL).append(title)
    print(f"  {'✓' if ok else '✗'} {title}" + (f"   {detail}" if detail else ""))


GBK_BYTES = bytes([0xB2, 0xE2, 0xCA, 0xD4])               # GBK 的「测试」
GBK_TEXT = GBK_BYTES.decode("gbk")

# 假 VTFCmd：往 stdout 写**原始 GBK 字节**（不走自动编码，否则又不算非 UTF-8 了）、
# 退出码 0、绝不产出任何文件 —— 正是"静默失败"那个形态。
FAKE_VTFCMD = (
    "import sys;"
    "sys.stdout.buffer.write(bytes([0xb2,0xe2,0xca,0xd4]));"
    "sys.stdout.buffer.flush()"
)


# ------------------------------------------------------- ① stdout 不许变 None

def test_stdout_survives_gbk():
    print("\n== ① 非 UTF-8 输出：读线程不许被打死，stdout 不许是 None ==")
    proc = vtf.run_vtfcmd([sys.executable, "-c", FAKE_VTFCMD])
    NUMBERS["helper 拿到的 stdout"] = repr(proc.stdout)
    check("proc.stdout 不是 None（读线程没被 UnicodeDecodeError 打死）",
          proc.stdout is not None, repr(proc.stdout))
    text = proc.stdout or ""
    check("stdout 里有内容（不是空串）", text.strip() != "", repr(text))
    check("GBK 的「测试」被解出来了（或至少落成替代字符 \\ufffd）",
          GBK_TEXT in text or "\ufffd" in text, repr(text))
    check("退出码照旧看得见（rc=0）", proc.returncode == 0, str(proc.returncode))
    check("helper 返回的是 str 不是 bytes", isinstance(proc.stdout, str),
          type(proc.stdout).__name__)


# --------------------------------------------------- ② 失败分支的「原因」非空

def test_failure_reason_not_empty():
    print("\n== ② 不产出 .vtf 的失败分支：报错里的「原因」不再是空的 ==")
    real_run = vtf.subprocess.run
    real_find = vtf.find_vtfcmd

    def fake_find(explicit=None):
        return Path(sys.executable)                       # 假装这就是 VTFCmd

    def fake_run(args, **kw):
        # 丢掉真参数，换成假 VTFCmd；**参数原样透传给真 subprocess.run**，
        # 所以调用点漏了 errors="replace" 这里就会现原形。
        return real_run([sys.executable, "-c", FAKE_VTFCMD], **kw)

    vtf.subprocess.run = fake_run
    vtf.find_vtfcmd = fake_find
    msg = ""
    raised = False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src = tmp / "FakeWall-BaseColor-16.png"
            src.write_bytes(b"")                          # 内容不重要：expect_size 给死
            try:
                vtf.convert(src, tmp / "out", expect_size=(8, 8))
            except vtf.VtfError as e:
                raised = True
                msg = str(e)
    finally:
        vtf.subprocess.run = real_run
        vtf.find_vtfcmd = real_find

    NUMBERS["失败分支报错"] = msg.replace("\n", " ⏎ ")
    check("假 VTFCmd 不产 .vtf → 抛 VtfError（走了产物校验那条分支）", raised,
          "居然没抛" if not raised else "")
    check("报错里带退出码（说明确实是「别信退出码」那条分支）", "退出码是 0" in msg,
          msg.replace("\n", " ⏎ ")[:110])
    reason = msg.splitlines()[-1].strip() if msg else ""
    check("原因那一段**非空**（这就是原来被吞掉的东西）", reason != "", repr(reason))
    check("原因里能看见内容（GBK 中文或替代字符）",
          GBK_TEXT in reason or "\ufffd" in reason, repr(reason))


# ----------------------------------------------- ③ 调用契约：必须容错解码

def test_call_contract():
    print("\n== ③ 契约：helper 必须显式容错解码，不随 locale/PYTHONUTF8 漂 ==")
    seen: dict = {}
    real_run = vtf.subprocess.run

    def spy(args, **kw):
        seen.update(kw)
        return real_run([sys.executable, "-c", "pass"], **kw)

    vtf.subprocess.run = spy
    try:
        vtf.run_vtfcmd([sys.executable, "-c", "pass"])
    finally:
        vtf.subprocess.run = real_run

    check("errors='replace'（怪字节只能落成替代字符，不许抛）",
          seen.get("errors") == "replace", str(seen.get("errors")))
    check("显式给了编码（不靠 locale 猜）", bool(seen.get("encoding")),
          str(seen.get("encoding")))
    check("capture_output=True（要拿得到原因）", seen.get("capture_output") is True,
          str(seen.get("capture_output")))
    check("timeout 仍然是 600 秒（行为不变）", seen.get("timeout") == 600,
          str(seen.get("timeout")))


# ------------------------------------------------- 修复前/后对照（只打印，不断言）

def show_before_after():
    print("\n== 修复前 / 修复后对照（同一条假 VTFCmd，PYTHONUTF8 现状如下）==")
    print(f"   PYTHONUTF8={os.environ.get('PYTHONUTF8')!r} "
          f"PYTHONIOENCODING={os.environ.get('PYTHONIOENCODING')!r} "
          f"locale_getpreferredencoding={__import__('locale').getpreferredencoding(False)!r}")

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):                 # 读线程的 traceback 是预期噪音
        old = subprocess.run([sys.executable, "-c", FAKE_VTFCMD],
                             capture_output=True, text=True)
    after = vtf.run_vtfcmd([sys.executable, "-c", FAKE_VTFCMD])
    print(f"   修复前 text=True          → repr(proc.stdout) = {old.stdout!r}")
    print(f"   修复后 run_vtfcmd(...)    → repr(proc.stdout) = {after.stdout!r}")
    crash = "UnicodeDecodeError" in buf.getvalue()
    print("   修复前读线程 → "
          + ("抛了 UnicodeDecodeError（正是本 bug）" if crash
             else "没抛（本机 locale 恰好能解，但契约仍不可靠）"))
    NUMBERS["修复前 repr"] = repr(old.stdout)
    NUMBERS["修复后 repr"] = repr(after.stdout)


def main() -> int:
    print("== VTFCmd 输出解码回归（GBK 输出不许吞掉原因）==")
    test_stdout_survives_gbk()
    test_failure_reason_not_empty()
    test_call_contract()
    show_before_after()
    print("\n—— 关键数字 ——")
    for k, v in NUMBERS.items():
        print(f"   {k}: {v}")
    print(f"\n通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    for f in FAIL:
        print(f"   失败：{f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
