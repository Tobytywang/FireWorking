# -*- coding: utf-8 -*-
"""倒计时进度环对照 —— 选了时长后，圆环改表示「剩余时间占比」（满圈＝刚选，
随计时耗尽到空），不再表示热度。

用户需求（本轮修正）：倒计时刚开始是 100%（满圈），倒计时结束是 0%（空）。
本探针把「计时中」的几个剩余进度（100% / 50% / 0% 到点前）离屏渲一遍，分篝火 / 数字
两种模式、dark / light 两主题、叠在三种桌面上。圆环用固定蓝（COUNTDOWN_ARC_COLOR）。
「到点后整圈闪烁」由 _cdflash_probe.py 单独覆盖。

跑法：.pyenv\\Scripts\\python.exe _cdarc_probe.py
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
# (label, theme, campfire, frac)；frac 是**剩余占比**：1.0=刚选满圈，0.0=到点前空
ROWS = (
    ("篝火 · 剩余 100%（刚选）", "dark", True, 1.0),
    ("篝火 · 剩余 50%", "dark", True, 0.5),
    ("篝火 · 剩余 0%（到点前）", "dark", True, 0.0),
    ("数字 · 剩余 100%（刚选）", "dark", False, 1.0),
    ("数字 · 剩余 50%", "dark", False, 0.5),
    ("数字 · 剩余 0%（到点前）", "dark", False, 0.0),
    ("篝火 · 剩余 50%（light）", "light", True, 0.5),
    ("数字 · 剩余 50%（light）", "light", False, 0.5),
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

    snap = scene(heat=58.0, kpm=174)     # 真实热度其实挺高，但计时中环不画它
    cell = 200
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

    tmp = HERE / "_cdarc_cell.png"
    y = pad
    for ri, (label, theme, camp, frac) in enumerate(ROWS):
        dr.text((pad + 2, y + 4), label, font=fn_head, fill=(235, 235, 240))
        for ci, (dname, desktop) in enumerate(DESKTOPS):
            x0 = pad + ci * (cell + pad)
            y0 = y + head
            if ri == 0:
                dr.text((x0 + 4, y - 1), dname, font=fn_col, fill=(150, 150, 160))
            dial = HeatDial(Svc())
            dial._boot_done = True
            dial._campfire = camp
            dial._bg_alpha = 0               # 100% 透明度场景
            dial._theme = THEMES[theme]
            dial._snap = dict(snap)
            dial._countdown_min = 10         # 选定 10 分钟档
            dial._fired = False
            # 让 _countdown_progress 返回 frac（剩余占比）：remaining = frac * total
            dial._countdown_deadline = time.time() + 10 * 60 * frac
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

    out = HERE / "_cdarc_probe.png"
    img.save(str(out), "PNG")
    print("saved", out, img.size)
    try:
        tmp.unlink()
    except OSError:
        pass


if __name__ == "__main__":
    main()
