"""探针：证明开屏(loading)阶段底盘透明度已跟随持久化配置，而非写死不透明。

做法：把配置 bg_alpha 设为 0（对应托盘「底盘透明度=100%」），离屏构造 HeatDial、
强制处于开屏态、触发一帧绘制、抓屏后**统计「盘面色 + 高 alpha」的像素数**。
- 修复前：开屏时 plate 被硬编码 255 → 出现大量不透明盘面色像素（整块圆盘）。
- 修复后：开屏时也用 self._bg_alpha(=0) → 盘面色像素数为 0（与配置一致，无突变）。
  这个差异是压倒性的（数千 vs 0），不会被火焰/圆环干扰判读。

用法：
    QT_QPA_PLATFORM=offscreen .pyenv/Scripts/python.exe _boot_alpha_probe.py
"""
from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import heatcore
import overlay
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication


def count_plate_pixels(dial):
    """统计抓屏里「盘面色 + alpha>=250」的像素数（盘面色按主题取，容差 8）。"""
    dial.show()
    dial.repaint()
    pm = dial.grab()
    img = pm.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    pr, pg, pb = dial._theme["plate"]
    tol = 8
    w, h = img.width(), img.height()
    n = 0
    step = 2  # 隔点采样足够
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = img.pixelColor(x, y)
            if c.alpha() >= 250 and abs(c.red() - pr) <= tol \
                    and abs(c.green() - pg) <= tol and abs(c.blue() - pb) <= tol:
                n += 1
    return n


def main():
    svc = heatcore.HeatService().start()
    svc.config.setdefault("overlay", {})["bg_alpha"] = 0.0

    app = QApplication(sys.argv)
    dial = overlay.HeatDial(svc)
    print("构造后 self._bg_alpha = %d（应为 0，即托盘「100%%透明」）" % dial._bg_alpha)

    # 强制处于开屏态（booting=True），走修复前那条「硬编码 255」分支
    dial._boot_done = False
    import time
    dial._boot_start = time.time()  # 刚启动，boot_t<1 → 仍在开屏

    n = count_plate_pixels(dial)
    print("开屏态「盘面色+高alpha」像素数 = %d" % n)
    print("判定：=0 → 已跟随配置（无突变）；>数百 → 仍写死不透明（未修复）")
    ok = n < 50
    print("\n结果: %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
