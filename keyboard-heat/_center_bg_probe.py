# -*- coding: utf-8 -*-
"""盘中央「有没有一块底」的对照 —— 篝火模式 vs 数字模式。

用户报（100% 透明度）：**篝火部分有一个深色的背景色，文字部分却没有，有点割裂**。
即：篝火模式的灶膛在中央铺了一块深色圆盘，数字模式却把文字直接悬在桌面上。

本探针把两模式 × 两主题 × 三种桌面都渲一遍，直观看「中央那块底」现在是否一致。
（`WA_DontShowOnScreen` = 用真实字体库离屏渲染，不会弹窗。）

跑法：.pyenv\\Scripts\\python.exe _center_bg_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import Qt                                   # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter              # noqa: E402
from PyQt6.QtWidgets import QApplication                      # noqa: E402

from heatcore import load_config                             # noqa: E402
from overlay import HeatDial, THEMES                          # noqa: E402

DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
ROWS = (
    ("dark · 篝火模式（灶膛）", "dark", True),
    ("dark · 数字模式（盘芯）", "dark", False),
    ("light · 篝火模式（灶膛）", "light", True),
    ("light · 数字模式（盘芯）", "light", False),
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

    tmp = HERE / "_cb_cell.png"
    y = pad
    for ri, (label, theme, camp) in enumerate(ROWS):
        dr.text((pad + 2, y + 4), label, font=fn_head, fill=(235, 235, 240))
        for ci, (dname, desktop) in enumerate(DESKTOPS):
            x0 = pad + ci * (cell + pad)
            y0 = y + head
            if ri == 0:
                dr.text((x0 + 4, y - 1), dname, font=fn_col, fill=(150, 150, 160))
            dial = HeatDial(Svc())
            dial._boot_done = True
            dial._campfire = camp
            dial._bg_alpha = 0               # 100% 透明度（用户报的那档）
            dial._theme = THEMES[theme]
            dial._snap = dict(snap)
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

    out = HERE / "_center_bg_probe.png"
    img.save(str(out), "PNG")
    print("saved", out, img.size)
    try:
        tmp.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
