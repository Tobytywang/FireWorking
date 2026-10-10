"""环境自检 —— 告诉你这台机器能用哪个界面版本。

    python doctor.py

检查三件事：采集依赖（pynput，两个版本都必须有）、
PyQt6 版渲染栈、Tkinter 版渲染栈，并给出建议。
"""

from __future__ import annotations

import importlib
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent


def probe(module, attr=None):
    """返回 (是否可用, 版本或错误摘要)。"""
    try:
        mod = importlib.import_module(module)
    except Exception as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)
    if attr:
        try:
            obj = getattr(mod, attr)
            ver = getattr(obj, "__version__", None)
            return True, str(ver) if ver else "ok"
        except Exception as exc:
            return False, str(exc)
    return True, getattr(mod, "__version__", "ok")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("=" * 58)
    print("键盘热度显示器 · 环境自检")
    print("=" * 58)
    print("Python  %s" % sys.version.split()[0])
    print("解释器  %s" % sys.executable)
    print()

    rows = []

    ok_pynput, info_pynput = probe("pynput")
    rows.append(("pynput（采集，必需）", ok_pynput, info_pynput))

    ok_tk, info_tk = probe("tkinter")
    if ok_tk:
        try:
            import tkinter
            info_tk = "Tk %s" % tkinter.TkVersion
        except Exception:
            ok_tk = False
            info_tk = "Tk 初始化失败"

    ok_qt, info_qt = probe("PyQt6.QtWidgets")
    if ok_qt:
        try:
            from PyQt6.QtCore import QT_VERSION_STR
            info_qt = "Qt %s" % QT_VERSION_STR
        except Exception:
            pass

    rows.append(("PyQt6（PyQt6 版界面）", ok_qt, info_qt))
    rows.append(("tkinter（Tkinter 版界面）", ok_tk, info_tk))

    for label, ok, info in rows:
        print("  %s %-26s %s" % ("[OK]  " if ok else "[MISS]", label, info))

    print()
    print("-- 数据目录 --")
    data_dir = PROJECT_DIR / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(":memory:")      # 不落盘探测，避免留下临时文件
        conn.execute("CREATE TABLE t(x)")
        conn.commit()
        conn.close()
        if os.access(str(data_dir), os.W_OK):
            print("  [OK]   %s 可写，SQLite 正常" % data_dir)
        else:
            print("  [WARN] %s 不可写，数据无法落库" % data_dir)
    except Exception as exc:
        print("  [FAIL] data 目录异常：%s" % exc)

    cfg = PROJECT_DIR / "config.json"
    print("  %s   config.json %s" % ("[OK]  " if cfg.exists() else "[MISS]", "存在" if cfg.exists() else "缺失"))

    print()
    print("-- 结论 --")

    if not ok_pynput:
        print("  [!] 缺 pynput，采集功能无法工作。先运行：")
        print("      %s -m pip install pynput" % sys.executable)
        return 1

    if ok_qt:
        print("  [OK] 两个版本都能跑，默认会用 PyQt6 版（窗口效果更好，托盘操作）。")
        print("       想强制用 Tkinter 版：python overlay_tk.py")
    elif ok_tk:
        print("  [OK] 可用 Tkinter 版（零依赖，全局热键操作）。")
        print("       想要更好的窗口效果，装 PyQt6：")
        print("       %s -m pip install PyQt6" % sys.executable)
    else:
        print("  [X] 两个界面栈都不可用，悬浮窗跑不起来。三个选择：")
        print("      1) 装 PyQt6：%s -m pip install PyQt6" % sys.executable)
        print("      2) 换成官方 python.org 发行版（自带 tkinter）")
        print("      3) 只用报告功能：python main.py --report")
        return 1

    print()
    print("  报告功能始终可用（纯标准库）：python main.py --report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
