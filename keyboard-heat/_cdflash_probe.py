# -*- coding: utf-8 -*-
"""倒计时进度环对照（第二轮修正）：倒计时＝**剩余时间**。

用户需求（本轮）：倒计时刚开始是 100%（满圈），倒计时结束是 0%（空），
然后**整圈圆环闪烁**提示时间到。本探针把「计时中」的几个剩余进度（100% / 75% /
50% / 25% / 0%）离屏渲一遍，再渲「到点」的闪烁亮帧 / 暗帧，分篝火 / 数字两种模式、
dark / light 两主题、叠在三种桌面上。圆环固定蓝（COUNTDOWN_ARC_COLOR）。

程序化校验：
  · 剩余 100%→0% 的蓝弧像素数单调不增，且 50% ≈ ½×100%（环随剩余耗尽）。
  · 闪烁亮帧蓝像素 ≈ 满圈；闪烁暗帧 ≈ 0（整圈消失） → 确实是「闪」。

跑法：.pyenv\\Scripts\\python.exe _cdflash_probe.py
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
from overlay import (HeatDial, THEMES)                        # noqa: E402

DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)

# (label, theme, campfire, state)；state 可以是 0~1 的剩余占比，或 "flash_on" /
# "flash_off"（到点闪烁的亮/暗帧）。
MODES = (
    ("篝火 · dark", "dark", True),
    ("数字 · dark", "dark", False),
    ("篝火 · light", "light", True),
    ("数字 · light", "light", False),
)
STATES = (
    ("剩余 100%（刚选）", 1.0),
    ("剩余 75%", 0.75),
    ("剩余 50%", 0.5),
    ("剩余 25%", 0.25),
    ("剩余 0%（到点前）", 0.0),
    ("到点·闪亮帧", "flash_on"),
    ("到点·闪暗帧", "flash_off"),
)


def scene():
    return {"heat": 58.0, "kpm": 174, "kpm_keys": 174, "kpm_mouse": 0,
            "peak": 214.0, "state": "typing", "idle_seconds": 1.0,
            "total_keys": 100}


def blue_count(img):
    """统计离屏渲染里蓝弧（COUNTDOWN_ARC_COLOR ≈ (59,130,246)）的像素数。

    火是橙红、文字是主题色、轨道/边线是灰，都不会落到这个蓝色域里，所以蓝像素
    ≈ 进度环的可见弧长，用来量「环随剩余耗尽」和「闪烁亮/暗」。
    """
    px = img.load()
    W, H = img.size
    tr, tg, tb = 59, 130, 246
    n = 0
    for y in range(0, H, 2):              # 隔行采样，够判趋势又不慢
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            if abs(r - tr) < 45 and abs(g - tg) < 45 and abs(b - tb) < 45 \
                    and b >= 150 and r <= 120:
                n += 1
    return n


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

    snap = scene()
    cell = 170
    pad = 8
    head = 22
    from PIL import Image, ImageDraw
    import PIL.ImageFont as ImageFont
    try:
        fn_head = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
        fn_col = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 11)
    except Exception:
        fn_head = fn_col = None

    grid_w = len(DESKTOPS) * (cell + pad) + pad
    grid_h = pad + sum(cell + pad + head for _ in MODES)
    img = Image.new("RGB", (grid_w, grid_h), (18, 18, 22))
    dr = ImageDraw.Draw(img)

    tmp = HERE / "_cdflash_cell.png"
    results = []          # (mode_label, state_label, blue_counts per desktop)

    y = pad
    for (mlabel, theme, camp) in MODES:
        # 模式标题
        dr.text((pad + 2, y + 3), mlabel, font=fn_head, fill=(235, 235, 240))
        y += head
        row_counts = []
        for (slabel, st) in STATES:
            dr.text((pad + 2, y + 3), slabel, font=fn_col, fill=(150, 150, 165))
            desk_counts = []
            for (dname, desktop) in DESKTOPS:
                x0 = pad + DESKTOPS.index((dname, desktop)) * (cell + pad)
                y0 = y + head
                dial = HeatDial(Svc())
                dial._boot_done = True
                dial._campfire = camp
                dial._bg_alpha = 0            # 100% 透明度场景
                dial._theme = THEMES[theme]
                dial._snap = dict(snap)
                dial._countdown_min = 10       # 选定 10 分钟档
                if st == "flash_on":
                    dial._fired = True
                    dial._countdown_deadline = time.time()
                    dial._countdown_flash_on = lambda: True
                elif st == "flash_off":
                    dial._fired = True
                    dial._countdown_deadline = time.time()
                    dial._countdown_flash_on = lambda: False
                else:
                    dial._fired = False
                    dial._countdown_deadline = time.time() + 10 * 60 * float(st)
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
                desk_counts.append(blue_count(tile))
                dial.close()
            row_counts.append((slabel, desk_counts))
            y += cell + pad + head
        results.append((mlabel, row_counts))

    out = HERE / "_cdflash_probe.png"
    img.save(str(out), "PNG")
    try:
        tmp.unlink()
    except OSError:
        pass

    # ---- 程序化校验 ----
    print("saved", out, img.size)
    print("\n蓝弧像素数（隔行采样，三桌面取均值）：")
    all_ok = True
    for (mlabel, row_counts) in results:
        print("  [%s]" % mlabel)
        prev = None
        for (slabel, dc) in row_counts:
            mean = sum(dc) / len(dc)
            print("    %-16s 蓝像素≈ %5.0f" % (slabel, mean))
        # 取第一个桌面（深终端）做趋势校验
        seq = [rc[1][0] for rc in row_counts]      # 100,75,50,25,0,flash_on,flash_off
        n100, n75, n50, n25, n0, f_on, f_off = seq
        # 单调不增
        mono = (n100 >= n75 >= n50 >= n25 >= n0)
        half = abs(n50 - n100 * 0.5) / max(1, n100) < 0.15
        flash = (f_on > n100 * 0.8) and (f_off < n100 * 0.1)
        ok = mono and half and flash
        all_ok = all_ok and ok
        print("    单调递减:%s  50%%≈½×100%%:%s  闪亮≈满圈&闪暗≈0:%s  -> %s"
              % (mono, half, flash, "OK" if ok else "FAIL"))
    print("\n校验结论：%s" % ("全部通过" if all_ok else "存在失败项"))


if __name__ == "__main__":
    main()
