# -*- coding: utf-8 -*-
"""低热度「进度条」辨识度探针 —— 圆环上的热度弧 vs 它挨着的每一层底。

用户报：低热度时进度条里的绿色容易和背景混在一起，辨识度低。

要回答四件事：
  1. 低热度的弧到底是什么颜色？（色阶 0→0.22 冷蓝、0.22→0.45 草绿）
  2. 它旁边"背景"都有谁？—— 未走段的**轨道**（track）、**底盘**（plate）、**桌面**
  3. 弧与它们的**亮度差**（Rec.601）和**色差**（RGB 欧氏）各是多少
  4. 换主题（dark/light）× 底盘不透明度 × 桌面底，结论会不会翻

做法：真实 `HeatDial` 离屏渲染（QWidget.grab，绝不抓屏），把透明帧合成到指定
桌面底色上，再按**角度**在圆环中心线上采样 —— 弧段取中点、未走段取终点再往前
14°（避开 RoundCap 的圆头）。

跑法：.pyenv\\Scripts\\python.exe _arc_contrast_probe.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import Qt                                    # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter               # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

import flame                                                   # noqa: E402
from heatcore import heat_rgb, load_config                     # noqa: E402
from overlay import HeatDial, START_DEG, SWEEP_DEG, THEMES     # noqa: E402

HEATS = (5.0, 12.0, 22.0, 35.0)
ALPHAS = (0.0, 0.45, 0.72, 1.0)
DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
THEME_NAMES = ("dark", "light")

# 当初计划的"改后"轨道色 —— 现在已经是 overlay.py THEMES 里的真值，这里只留个
# 备忘：它取自 Tk 版 overlay_tk.py 的 THEMES（#4A5261 / #C2C7D1），逐位相同，
# 好让两版圆环的观感不再分叉。Tk 版的轨道一直是不透明定色，所以它没这个毛病。
AFTER_TRACK = {"dark": (74, 82, 97), "light": (194, 199, 209)}


def scene(heat, state="typing"):
    kpm = round(heat * 3.0)
    return {"heat": heat, "kpm": kpm, "kpm_keys": kpm, "kpm_mouse": 0,
            "peak": 214.0, "state": state, "idle_seconds": 1.0, "total_keys": 100}


def lum(c):
    """Rec.601 感知亮度。判"看不看得见"看这个，别用 RGB 之和。"""
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def drgb(c1, c2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def at(img, cx, cy, radius, deg):
    """在半径 radius、角度 deg（Qt 约定：0° 在 3 点钟，逆时针为正）取 3×3 中位色。

    取中位而不是中心点：圆环边缘有抗锯齿，中心点是纯色、邻域混了底。
    """
    a = math.radians(deg)
    x = cx + radius * math.cos(a)
    y = cy - radius * math.sin(a)
    vals = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            pc = img.pixelColor(int(round(x)) + dx, int(round(y)) + dy)
            c = (pc.red(), pc.green(), pc.blue())
            vals.append((lum(c), c))
    vals.sort(key=lambda v: v[0])
    return vals[4][1]


def frame(dial, img_buf, heat, alpha, desktop):
    dial._bg_alpha = int(round(alpha * 255))
    dial._snap = scene(heat)
    dial.repaint()
    pm = dial.grab()
    # 先铺桌面底再开 painter：反过来的话 fill 会把 QPainter 的 target 冲掉。
    img_buf.fill(QColor(*desktop))
    p = QPainter(img_buf)
    p.drawPixmap(0, 0, pm)
    p.end()
    return img_buf


FONT = "C:/Windows/Fonts/msyh.ttc"


def _font(size):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(FONT, size)
    except Exception:
        return None


def compose(dial, buf, cx, cy, radius, out):
    """改前 / 改后对照：轨道「半透明白」vs「不透明定色」，各配浅底与深底。

    行 = 版本 × 桌面底，列 = 热度。每格底下打采样数字 —— 图看观感、数字给判据。
    """
    from PIL import Image, ImageDraw
    dial._theme = THEMES["dark"]
    alpha = 0.72
    heats = (5.0, 22.0, 35.0)
    desks = (("浅色底", (238, 238, 240)), ("深色底", (30, 30, 36)))
    # 「改前」硬编码成历史值（半透明白 / 半透明黑）：改完代码后这张图仍要能复现
    # "历史 vs 现在"，不能跟着 THEMES 一起变。「改后」直接从 THEMES 读 —— 顺带
    # 当一次交叉验证：探针预测的观感与真代码一致，图才和改前预期逐像素吻合。
    orig = (255, 255, 255, 74)
    new = THEMES["dark"]["track"]

    scale, pad, gap, band = 2, 20, 14, 34
    left = 172                      # 行标签宽度（放行首，格下只留 Δlum，免得挤成一团）
    cell = dial.width()
    tw = cell * scale
    combos = []
    for vshort, track in (("改前 半透明白", orig), ("改后 不透明定色", new)):
        for dname, desktop in desks:
            combos.append(("%s\n%s" % (vshort, dname), track, desktop))
    ncol = len(heats)
    W = left + pad + ncol * (tw + gap) - gap + pad
    H = 108 + pad + len(combos) * (tw + band + gap) - gap + pad
    img = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(img)
    f1, f2, f3 = _font(22), _font(16), _font(17)
    dr.text((pad, 12), "低热度「进度条」辨识度：轨道改不透明前后（dark 主题，α=72%）",
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 46), "格下 Δlum = 弧（已走段）亮度 − 轨道（未走段）亮度。"
                       "越小越糊，≤20 基本分不出（弧色固定 141~150，轨道一漂就撞）。",
            fill=(96, 102, 116), font=f2)
    for c, heat in enumerate(heats):
        dr.text((left + c * (tw + gap) + 6, 80), "热度 %.0f%%" % heat,
                fill=(26, 28, 34), font=f2)

    for r, (rname, track, desktop) in enumerate(combos):
        THEMES["dark"]["track"] = track
        y = 108 + pad + r * (tw + band + gap)
        dr.multiline_text((pad, int(y + tw / 2 - 24)), rname,
                          fill=(40, 40, 50), font=f3, spacing=4)
        for c, heat in enumerate(heats):
            x = left + c * (tw + gap)
            q = frame(dial, buf, heat, alpha, desktop)
            frac = heat / 100.0
            c_arc = at(q, cx, cy, radius, START_DEG - SWEEP_DEG * frac * 0.5)
            c_trk = at(q, cx, cy, radius, START_DEG - SWEEP_DEG * frac - 14.0)
            dl = lum(c_arc) - lum(c_trk)
            tmp = HERE / "_arc_cell.png"
            q.save(str(tmp), "PNG")
            tile = Image.open(tmp).convert("RGB").resize((tw, tw), Image.LANCZOS)
            img.paste(tile, (x, y))
            pc = q.pixelColor(5, 5)          # 窗口角落 = 桌面底有没有透上来
            dr.text((x + 6, y + tw + 7), "Δlum %+.0f　底%s"
                    % (dl, (pc.red(), pc.green(), pc.blue())),
                    fill=(40, 40, 50), font=f2)
    THEMES["dark"]["track"] = orig              # 用完还原，别污染后面的调用
    img.save(str(out), "PNG")
    try:
        (HERE / "_arc_cell.png").unlink()
    except OSError:
        pass
    print("\n对照图 %s  %s" % (out.name, img.size))


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

    dial = HeatDial(Svc())
    dial._boot_done = True
    dial._campfire = True                  # 用户当前的视觉
    dial.show()
    dial._timer.stop()                     # 冻结：快照手动换，免得被刷新覆盖
    app.processEvents()

    w, h = dial.width(), dial.height()
    d = float(min(w, h))
    cx, cy = w / 2.0, h / 2.0
    radius = flame.ring_radius(d)
    thick = flame.ring_thick(d)
    print("表盘 %dx%d  d=%.0f  环中心线 r=%.1f  笔宽 %.1f（%.1f° 弧长）"
          % (w, h, d, radius, thick, math.degrees(thick / radius)))
    print("采样：弧段取中点，未走段取「弧终点再往前 14°」\n")

    buf = QImage(w, h, QImage.Format.Format_RGB32)
    rows = []
    for tname in THEME_NAMES:
        dial._theme = THEMES[tname]
        for alpha in ALPHAS:
            for dname, desktop in DESKTOPS:
                line = []
                for heat in HEATS:
                    frac = heat / 100.0
                    img = frame(dial, buf, heat, alpha, desktop)
                    deg_used = START_DEG - SWEEP_DEG * frac * 0.5
                    deg_track = START_DEG - SWEEP_DEG * frac - 14.0
                    c_arc = at(img, cx, cy, radius, deg_used)
                    c_trk = at(img, cx, cy, radius, deg_track)
                    dl = lum(c_arc) - lum(c_trk)
                    line.append((heat, c_arc, c_trk, dl, drgb(c_arc, c_trk)))
                rows.append((tname, alpha, dname, line))

    # ---- 明细表 ----
    for heat in HEATS:
        print("── 热度 %.0f%% ──────────────────────────────────────────" % heat)
        print("  %-6s %-5s %-7s  %-15s %-15s %6s %6s"
              % ("主题", "α", "桌面", "弧（已走段）", "轨道（未走段）", "Δlum", "ΔRGB"))
        for tname, alpha, dname, line in rows:
            _h, c_arc, c_trk, dl, de = [r for r in line if r[0] == heat][0]
            flag = "  ← 糊" if (abs(dl) < 20 or de < 45) else ""
            print("  %-6s %-5.2f %-7s  %-15s %-15s %6.1f %6.1f%s"
                  % (tname, alpha, dname,
                     "rgb%s" % (c_arc,), "rgb%s" % (c_trk,), dl, de, flag))
        print()

    # ---- 汇总：哪些组合最糊 ----
    print("── 按「最糊」排序（ΔRGB 最小，取各热度里最差的那一档）──")
    flat = []
    for tname, alpha, dname, line in rows:
        worst = min(line, key=lambda r: drgb(r[1], r[2]))
        flat.append((drgb(worst[1], worst[2]), lum(worst[1]) - lum(worst[2]),
                     tname, alpha, dname, worst[0]))
    flat.sort()
    for de, dl, tname, alpha, dname, heat in flat[:10]:
        print("  %-6s α=%-5.2f %-7s 最糊在 h%2.0f%%  ΔRGB %5.1f  Δlum %+6.1f"
              % (tname, alpha, dname, heat, de, dl))

    # ---- 色阶本身：低热度段的亮度曲线 ----
    print("\n── 色阶低段（亮度和色相怎么走）──")
    print("  %-8s %-16s %6s %6s  %s" % ("frac", "rgb", "lum", "R−G", "说明"))
    for i in range(0, 46, 5):
        f = i / 100.0
        c = heat_rgb(f)
        note = ""
        if i == 0:
            note = "冷蓝（空闲）"
        elif i <= 20:
            note = "青绿段"
        elif i <= 45:
            note = "草绿段"
        print("  %-8.2f %-16s %6.1f %6d  %s"
              % (f, "rgb%s" % (c,), lum(c), c[0] - c[1], note))

    compose(dial, buf, cx, cy, radius, HERE / "_arc_contrast.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
