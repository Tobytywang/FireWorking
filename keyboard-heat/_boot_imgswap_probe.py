from __future__ import annotations

import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import heatcore
import overlay
from PyQt6.QtWidgets import QApplication


def main():
    svc = heatcore.HeatService().start()
    app = QApplication(sys.argv)

    # 当前配置确实启用了位图柴堆（log_image / log_image_front 指向 PNG）
    cfg = svc.config.get("overlay", {})
    print("config log_image        = %r" % cfg.get("log_image"))
    print("config log_image_front  = %r" % cfg.get("log_image_front"))

    t0 = time.perf_counter()
    dial = overlay.HeatDial(svc)          # __init__ 内同步解码
    dt = (time.perf_counter() - t0) * 1000
    print("HeatDial.__init__ 耗时 = %.1f ms（含同步解码两张 PNG）" % dt)

    # 关键断言：构造完成（show 之前）位图缓存已就绪 → 首帧 paintEvent 走位图分支，
    # 不会先画代码柴堆再切换。
    back_ok = dial._log_image_obj is not None
    front_ok = dial._log_image_front_obj is not None
    print("构造后 _log_image_obj 已就绪      = %s" % back_ok)
    print("构造后 _log_image_front_obj 已就绪 = %s" % front_ok)

    ok = back_ok and front_ok
    print("\n结果: %s  (PASS = 开屏第一帧即位图，无『代码柴堆→位图』切换)"
          % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
