# -*- coding: utf-8 -*-
"""倒计时触发的提示效果对照 —— 篝火呼吸（小火/大火） vs 数字「时间到」。

用户需求：倒计时（5/10/25 分钟）到点后，篝火模式在小火/大火间反复变更做呼吸效果，
数字模式用文字提示「时间到」。

本探针把「触发后」的几种状态离屏渲一遍，直观看效果（WA_DontShowOnScreen = 真实字体、
不弹窗）。篝火的小火/大火分别取呼吸正弦的两个端点（b=0 / b=1）。

跑法：.pyenv\\Scripts\\python.exe _countdown_probe.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import Qt                                   # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter              # noqa: E402
from PyQt6.QtWidgets import QApplication                      # noqa: E402

from heatcore import load_config                             # noqa: E402
from overlay import (HeatDial, THEMES, COUNTDOWN_BREATHE_PERIOD)  # noqa: E402

DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
# mode: True=篝火, False=数字；phase: low/high(篝火呼吸两端) / text(数字提示)
ROWS = (
    ("dark · 篝火（小火）", "dark", True, "low"),
    ("dark · 篝火（大火）", "dark", True, "high"),
    ("dark · 数字（时间到）", "dark", False, "text"),
    ("light · 篝火（小火）", "light", True, "low"),
    ("light · 篝火（大火）", "light", True, "high"),
    ("light · 数字（时间到）", "light", False, "text"),
)


def scene(heat, kpm):
    return {"heat": heat, "kpm": kpm, "kpm_keys": kpm, "kpm_mouse": 0,
            "peak": 214.0, "state": "typing", "idle_seconds": 1.0,
            "total_keys": 100}


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    class Svc:
        def __init__(self):
            self.config = load_config()
            self.db_path = HERE / "data" / "heat.db"

        def snapshot(self):
            return dict(dial._snap)

        def toggle_pause(self):
            return False

        def stop(self):
            pass

    snap = scene(heat=58.0, kpm=174)
    cell = 210
    pad = 10
    head = 26
    from PIL import Image, ImageDraw
    import PIL.ImageFont as ImageFont
    try:
        fn_head = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 15)
        fn_col = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
    except Exception:
        fn_head = fn_col = None

    grid_w = len(DESKTOPS) * (cell + pad) + pad
    grid_h = pad + sum(cell + pad + head for _ in ROWS)
    img = Image.new("RGB", (grid_w, grid_h), (18, 18, 22))
    dr = ImageDraw.Draw(img)

    tmp = HERE / "_cd_cell.png"
    y = pad
    for ri, (label, theme, camp, phase) in enumerate(ROWS):
        dr.text((pad + 2, y + 4), label, font=fn_head, fill=(235, 235, 240))
        for ci, (dname, desktop) in enumerate(DESKTOPS):
            x0 = pad + ci * (cell + pad)
            y0 = y + head
            if ri == 0:
                dr.text((x0 + 4, y - 1), dname, font=fn_col, fill=(150, 150, 160))
            dial = HeatDial(Svc())
            dial._boot_done = True
            dial._campfire = camp
            dial._bg_alpha = 0               # 100% 透明度（用户报的那档场景）
            dial._theme = THEMES[theme]
            dial._snap = dict(snap)
            dial._fired = True               # 倒计时已到点 → 触发提示
            if camp:
                # 呼吸正弦两端：b=0(小火) / b=1(大火)
                if phase == "low":
                    dial._fire_start = time.time() + COUNTDOWN_BREATHE_PERIOD / 4.0
                else:
                    dial._fire_start = time.time() - COUNTDOWN_BREATHE_PERIOD / 4.0
            dial.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            dial.show()
            dial._timer.stop()
            app.processEvents()
            pm = dial.grab()
            buf = QImage(pm.width(), pm.height(), QImage.Format.Format_RGB32)
            buf.fill(QColor(*desktop))
            pp = QPainter(buf)
            pp.drawPixmap(0, 0, pm)
            pp.end()
            sx = (buf.width() - cell) // 2
            sy = (buf.height() - cell) // 2
            buf.copy(sx, sy, cell, cell).save(str(tmp), "PNG")
            tile = Image.open(tmp).convert("RGB")
            img.paste(tile, (x0, y0))
            dial.close()
        y += cell + pad + head

    out = HERE / "_countdown_probe.png"
    img.save(str(out), "PNG")
    print("saved", out, img.size)
    try:
        tmp.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
