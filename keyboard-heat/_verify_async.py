"""验证：柴堆 PNG 解码已异步化，首帧 paintEvent（主线程）不再同步阻塞。

按调用线程区分来源：主线程（paint/__init__ 路径）的同步调用必须为 0；
后台 'log-image-preload' 线程负责真正的解码（预期 2 次）。

用法：
    QT_QPA_PLATFORM=offscreen .pyenv/Scripts/python.exe _verify_async.py
"""
from __future__ import annotations

import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from unittest import mock

import heatcore
import flame
import overlay
from PyQt6.QtWidgets import QApplication

threads = {"main": 0, "worker": 0}
orig = flame.log_image_load


def spy(*a, **k):
    tname = threading.current_thread().name
    if tname == "log-image-preload":
        threads["worker"] += 1
    else:
        threads["main"] += 1
    return orig(*a, **k)


with mock.patch.object(flame, "log_image_load", spy):
    svc = heatcore.HeatService().start()
    app = QApplication(sys.argv)
    dial = overlay.HeatDial(svc)          # __init__ 里只启动后台线程，不在主线程解码
    # 构造刚结束、后台线程还没跑完（解码需 ~200ms+），缓存必须还是 None
    immediate_none = (dial._log_image_obj is None and dial._log_image_front_obj is None)
    main_after_init = threads["main"]     # __init__ 路径不应在主线程解码
    dial.show()
    app.processEvents()                   # 首帧 paint 此刻发生（主线程）
    main_after_paint = threads["main"]    # 首帧 paint 期间主线程不应有任何解码

    time.sleep(0.8)                       # 等后台线程把两张 PNG 解完
    app.processEvents()
    loaded = (dial._log_image_obj is not None
              and dial._log_image_front_obj is not None)

    print("构造后缓存立即可用（应为 False，证明没同步解码）: %s" % immediate_none)
    print("__init__ 主线程解码次数（应为 0）: %d" % main_after_init)
    print("首帧 paint 主线程解码次数（应为 0）: %d" % main_after_paint)
    print("后台线程加载完成后缓存已填充（应为 True）: %s" % loaded)
    print("后台线程共解码次数（应为 2）: %d" % threads["worker"])

    ok = (immediate_none and main_after_init == 0 and main_after_paint == 0
          and loaded and threads["worker"] == 2)
    print("\n结果: %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)
