# -*- coding: utf-8 -*-
"""底盘「最外圈细线」的径向剖面 —— 去掉前后对照。

用户报：圈圈最外面有一个白色的圆形线条，去掉它。

那条线不是弧、也不是轨道，而是**底盘椭圆的描边（pen）**：
    overlay.py:  p.setPen(QPen(QColor(*theme["rim"]), 2.0)); p.drawEllipse(...)
dark 主题是半透明白 (255,255,255,120)，light 是半透明黑 (0,0,0,110)。它画在底盘
半径上（pen 以路径居中），于是最外圈多出一小环，亮度比盘面高得多 —— 深色底下
盘面 lum ≈ 28，那一环能到 120+，非常跳。Tk 版同样有一份（create_oval 的
outline=th["rim"], width=2）。

量法：真实 HeatDial 离屏渲染（QWidget.grab，绝不抓屏）→ 合成到指定桌面底 →
沿**正下方**（270°）逐像素扫径向剖面。选正下方是因为弧的缺口就在那儿（弧从
220° 顺时针扫 260°，缺口 320°→220°），所以那条射线上既没有弧、也没有轨道，
扫到的只有底盘本身和它的描边。

跑法：
  .pyenv\\Scripts\\python.exe _rim_off_probe.py before   # 出 _rim_off_before.png
  .pyenv\\Scripts\\python.exe _rim_off_probe.py after    # 出 _rim_off_after.png
  .pyenv\\Scripts\\python.exe _rim_off_probe.py merge    # 合成 _rim_off_probe.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 必须在 import QtWidgets 之前设：offscreen 平台插件，绝不弹窗、绝不抓屏
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage, QPainter                  # noqa: E402
from PyQt6.QtWidgets import QApplication                          # noqa: E402

import flame                                                      # noqa: E402
from heatcore import load_config                                  # noqa: E402
from overlay import HeatDial, THEMES                              # noqa: E402

FONT = "C:/Windows/Fonts/msyh.ttc"
ALPHA_PCT = 0.72                       # 用户的档（config.json 里 bg_alpha）
ALPHAS = (0.0, 0.45, 0.72, 1.0)
DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
THEME_NAMES = ("dark", "light")
HEAT = 4.0                             # 低热度：只留一小段弧，射线仍落在缺口里
ZOOM = 6                               # 边界放大倍数
PEAK_LO, PEAK_HI = -5, 6               # 找描边尖峰的半径区间（相对 plate_r）


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _font(size):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(FONT, size)
    except Exception:
        return None


def scene(heat):
    kpm = round(heat * 3.0)
    return {"heat": heat, "kpm": kpm, "kpm_keys": kpm, "kpm_mouse": 0,
            "peak": 214.0, "state": "typing" if heat > 0 else "idle",
            "idle_seconds": 1.0, "total_keys": 100}


class Svc:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"

    def snapshot(self):
        return scene(HEAT)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def shot(app, dial, theme, alpha, heat=HEAT):
    """离屏渲一帧。返回 ARGB32（**非预乘**）的 QImage。"""
    dial._theme = THEMES[theme]
    dial._bg_alpha = int(round(alpha * 255))
    dial._snap = scene(heat)
    dial.repaint()
    app.processEvents()
    return dial.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)


def composite(img, desktop):
    """把带透明度的离屏帧叠到纯色桌面底上（= 屏幕上看到的样子）。"""
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    out.fill(QColor(*desktop))
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.drawImage(0, 0, img)
    p.end()
    return out


def profile(img, cx, cy, plate_r, lo, hi):
    """沿正下方（x=cx，y=cy+r）逐像素扫，返回 [(r, rgb, alpha, lum)]。

    区间会裁到窗口内 —— 圆盘边界离窗口下沿只剩 ~2px（plate_r = d/2 − 2.28，
    d = 窗高），再往外就没有像素了。
    """
    rows = []
    r0 = max(int(plate_r) + lo, 1)
    r1 = min(int(plate_r) + hi, int(img.height() - cy) - 2)   # 别越出窗口下沿
    for r in range(r0, r1 + 1):
        pc = img.pixelColor(int(round(cx)), int(round(cy)) + r)
        c = (pc.red(), pc.green(), pc.blue())
        rows.append((r - plate_r, c, pc.alpha(), lum(c)))
    return rows


def edge_stats(rows, desk_lum):
    """返回 (盘面 lum, 最偏离的采样点, Δ相对盘面, **超出 [盘面, 桌面] 的量**)。

    判据用最后那个"超界量"：边界上合法的过渡只是"盘面 × 桌面"的线性混合，所以过渡
    像素的亮度必然落在两个端点之间。**超出端点**就说明边界上还叠了第三个东西 ——
    原来那圈 2px 的 rim 描边。

    只盯着"相对盘面的 Δ"会误伤：浅色桌面 + 半透明盘时，边界那个抗锯齿像素本来就会
    偏离盘面 40 左右（它有一小部分被桌面透上来），但它落在 [盘面, 桌面] 里，是正常
    过渡。盘面取 r ≤ −2 的深处值（AA 只影响最外 1px，不碰这里）。
    """
    inner = [r for r in rows if r[0] <= -2.0]
    base = inner[-1][3]
    lo, hi = min(base, desk_lum), max(base, desk_lum)
    worst = max(rows, key=lambda r: max(lo - r[3], r[3] - hi, 0.0))
    return base, worst, worst[3] - base, max(lo - worst[3], worst[3] - hi, 0.0)


def main():
    tag = (sys.argv[1] if len(sys.argv) > 1 else "after").lower()
    if tag == "merge":
        return merge()
    if tag not in ("before", "after"):
        print("用法：_rim_off_probe.py before|after|merge")
        return 2

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(Svc())
    dial._boot_done = True
    dial._campfire = True              # 走用户的实际视觉（篝火模式）
    dial.show()
    dial._timer.stop()
    app.processEvents()

    w, h = dial.width(), dial.height()
    d = float(min(w, h))
    cx, cy = w / 2.0, h / 2.0
    plate_r = d / 2.0 - max(2.0, d * 0.012)
    print("圆盘 d=%.0f  plate_r=%.2f  弧半径=%.2f  弧宽=%.2f（270° 方向无弧无轨道）"
          % (d, plate_r, flame.ring_radius(d), flame.ring_thick(d)))

    print("\n1. 边界超界量：过渡像素的亮度必须落在 [盘面, 桌面] 之间（超出 = 叠了描边）")
    print("   %-6s %-6s %-6s %8s %8s %8s %6s %8s" % ("主题", "α", "桌面", "盘面lum",
                                                    "偏点lum", "Δlum", "峰α", "超界"))
    worst = []
    for theme in THEME_NAMES:
        for apct in ALPHAS:
            for dname, desk in DESKTOPS:
                img = composite(shot(app, dial, theme, apct), desk)
                rows = profile(img, cx, cy, plate_r, PEAK_LO, PEAK_HI)
                base_l, pk, dl, over = edge_stats(rows, lum(desk))
                flag = "" if over <= 3.0 else "  ←"
                if theme == "dark":
                    worst.append(over)
                print("   %-6s %-6s %-6s %8.1f %8.1f %+8.1f %6d %8.1f%s"
                      % (theme, "%d%%" % round(apct * 100), dname,
                         base_l, pk[3], dl, pk[2], over, flag))
            print()
    print("   最坏超界量：%.1f（dark 主题 12 个组合里最大的）" % max(worst))

    print("2. dark 主题整条剖面（α=72%）—— 看那条线有没有、在哪几行")
    for dname, desk in (DESKTOPS[0], DESKTOPS[2]):
        print("   ── %s（底 %s）" % (dname, desk))
        img = composite(shot(app, dial, "dark", ALPHA_PCT), desk)
        for r, c, a, l in profile(img, cx, cy, plate_r, -6, 2):
            bar = "#" * max(0, int(round((l - 20) / 4.0)))
            print("     r%+5.2f  rgb%-16s α%3d  lum%7.1f  %s" % (r, c, a, l, bar))

    print("\n3. 边界放大图 %s" % _zoom(app, dial, cx, cy, d, plate_r, tag))
    print("DONE")
    return 0


def _zoom(app, dial, cx, cy, d, plate_r, tag):
    """1 行 3 列：三种桌面底下的底盘下缘（270°），放大 ZOOM 倍。"""
    from PIL import Image, ImageDraw
    rows = []
    for dname, desk in DESKTOPS:
        img = composite(shot(app, dial, "dark", ALPHA_PCT), desk)
        rows.append((dname, desk, img))

    half_w = 17                         # 切向半宽
    r_lo, r_hi = -30, 2                 # 径向范围（相对 plate_r）
    half_h = (r_hi - r_lo) // 2
    cy_crop = cy + plate_r + (r_lo + r_hi) / 2.0
    tw, th = half_w * 2 * ZOOM, half_h * 2 * ZOOM
    gap, pad, band = 16, 18, 76
    W = pad * 2 + len(rows) * (tw + gap) - gap
    H = 84 + pad + th + band + pad
    canvas = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(canvas)
    f1, f2 = _font(21), _font(15)
    f3 = _font(14)
    dr.text((pad, 10), "底盘下缘（正下方 270°）放大 %d 倍　dark 主题　α=72%%　【%s】"
            % (ZOOM, "改前" if tag == "before" else "改后"),
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 40), "裁切：径向 %+d ~ %+d px（相对底盘半径；盘外只剩 ~2px）、切向 ±%d px。"
            % (r_lo, r_hi, half_w), fill=(96, 102, 116), font=f2)
    dr.text((pad, 60), "「超界」= 过渡像素的亮度超出 [盘面, 桌面] 的量 —— 合法过渡只是两者的"
                       "混合，永远不会超。", fill=(96, 102, 116), font=f2)

    tmp = HERE / "_rim_cell.png"
    for i, (dname, desk, img) in enumerate(rows):
        x = pad + i * (tw + gap)
        img.save(str(tmp), "PNG")
        full = Image.open(tmp).convert("RGB")
        px, py = int(round(cx)), int(round(cy_crop))
        crop = full.crop((px - half_w, py - half_h, px + half_w, py + half_h))
        canvas.paste(crop.resize((tw, th), Image.NEAREST), (x, 84 + pad))
        rows_p = profile(img, cx, cy, plate_r, PEAK_LO, PEAK_HI)
        base_l, pk, dl, over = edge_stats(rows_p, lum(desk))
        ty = 84 + pad + th + 8
        dr.text((x + 2, ty), "%s　底%s" % (dname, desk), fill=(40, 40, 50), font=f2)
        dr.text((x + 2, ty + 20),
                "盘面 %.0f → %.0f　Δ%+.0f　超界 %.1f"
                % (base_l, pk[3], dl, over), fill=(40, 40, 50), font=f3)
    try:
        tmp.unlink()
    except OSError:
        pass
    out = HERE / ("_rim_off_%s.png" % tag)
    canvas.save(str(out), "PNG")
    return "%s  %s" % (out.name, canvas.size)


def merge():
    """把 before / after 两张同尺寸图横拼成最终对照。"""
    from PIL import Image, ImageDraw
    a = HERE / "_rim_off_before.png"
    b = HERE / "_rim_off_after.png"
    if not a.exists() or not b.exists():
        print("缺图：先分别跑 before / after")
        return 2
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    gap, pad, head = 20, 18, 52
    W = ia.width + ib.width + gap + pad * 2
    H = max(ia.height, ib.height) + pad * 2 + head
    canvas = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(canvas)
    dr.text((pad, 12), "底盘最外圈细线：去掉前 / 去掉后（同一帧、同一桌面、同一采样射线）",
            fill=(26, 28, 34), font=_font(23))
    canvas.paste(ia, (pad, head + pad))
    canvas.paste(ib, (pad + ia.width + gap, head + pad))
    out = HERE / "_rim_off_probe.png"
    canvas.save(str(out), "PNG")
    print("对照图 %s  %s" % (out.name, canvas.size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
