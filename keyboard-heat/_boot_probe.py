"""启动耗时探针：分拆各阶段，找出"首次启动卡"的瓶颈。

用法（必须在 .pyenv 下、offscreen 跑，避免弹出真窗口）：
    QT_QPA_PLATFORM=offscreen .pyenv/Scripts/python.exe _boot_probe.py
"""
from __future__ import annotations

import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

T = {}
t0 = time.perf_counter()


def mark(name):
    global t0
    T[name] = time.perf_counter() - t0
    t0 = time.perf_counter()


mark("进程冷启动到脚本第一行")  # 之前的是解释器+import本脚本，无法在这里量

import PyQt6.QtWidgets  # noqa: F401
mark("import PyQt6.QtWidgets")

import heatcore  # noqa: F401
mark("import heatcore")

import flame  # noqa: F401
mark("import flame")

import overlay  # noqa: F401
mark("import overlay")

from heatcore import HeatService
mark("import HeatService")

# run.bat 里三种"嗅探"用的 import（pynput / PIL / PyQt6.QtWidgets）。
# 这里只测 import 本身，模拟 run.bat 为每个嗅探另起一个进程的成本（进程冷启动另算）。
try:
    import pynput  # noqa: F401
    T["(deps) import pynput"] = T.get("(deps) import pynput", 0)
    mark("(deps) import pynput")
except Exception as e:  # pragma: no cover
    mark("(deps) import pynput FAIL: %r" % e)

try:
    import PIL  # noqa: F401
    mark("(deps) import PIL")
except Exception as e:  # pragma: no cover
    mark("(deps) import PIL FAIL: %r" % e)

s = HeatService().start()
mark("HeatService().start()")

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)
mark("QApplication()  <- 含字体数据库扫描")

dial = overlay.HeatDial(s)
mark("HeatDial() 构造")

dial.show()
app.processEvents()
mark("show + processEvents（首帧布局）")

dial.update()
app.processEvents()
mark("首次 paint（含 log_image_load 解码 PNG）")

from PyQt6.QtGui import QFontDatabase
_fams = QFontDatabase.families()
mark("QFontDatabase.families()  <- 若上面已扫过则极快")

print("\n===== 启动阶段耗时（offscreen 近似，真实 GUI 字体/插件扫描会更真实）=====")
for k, v in T.items():
    print("  %-32s %8.1f ms" % (k, v * 1000.0))
print("  ----")
print("  %-32s %8.1f ms" % ("累计（脚本内）", sum(T.values()) * 1000.0))
