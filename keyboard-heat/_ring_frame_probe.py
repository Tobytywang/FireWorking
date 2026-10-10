# -*- coding: utf-8 -*-
"""环带轮廓探针 —— 上一轮只描了外沿，内圈和两个端头（转角）还是虚的。

用户报（第 6 轮）：「现在只有外圈有，内圈和转角的那个地方，也应该有」。

`THEMES.track_edge` 那条线原来是**一条外弧**。这轮把它补成闭合轮廓：
外弧 + 内弧 + 两个端头半圆（包住轨道的圆笔帽）。本探针量三处：

  · 内沿 —— 180°（9 点钟）方向、跨 `ring_inner_radius` 的**径向**剖面
  · 末端 —— −40°（220° 顺时针扫 260° 的终点）处跨端面的**切向**剖面
  · 起点 —— 220° 处同法（它总被热度弧的圆笔帽盖着，作对照）

量法：真实 `HeatDial` 离屏渲染（QWidget.grab，**绝不抓屏**）→ 合成到指定桌面底。
热度取 4%：热度弧只占 220°~209.6°，180° 和两个端头都是**纯轨道**。

「改前」用 `legacy(True)` 把轮廓退化回一条外弧（内弧与外弧重合、端头半圆缩成点），
所以同一个渲染路径能同时给出两版 —— 不用去翻 git 里的旧文件。

判据：剖面里要有一条**同时远离轨道和邻居**的线。分离度 = min(离轨道, 离邻居)，
低于 25 就等于没画。改前内沿的邻居是灶膛、端头的邻居是底盘，两者在
「浅色桌面 + α≈72%」下都和轨道几乎同亮度，所以分离度 ≈ 0。

跑法：
  .pyenv\\Scripts\\python.exe _ring_frame_probe.py now    # 三处剖面对照（改前/改后）
  .pyenv\\Scripts\\python.exe _ring_frame_probe.py look   # 出 _ring_frame_probe.png 放大对照图
"""
from __future__ import annotations

import math
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
ALPHAS = (0.0, 0.45, 0.72, 1.0)
DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
THEME_NAMES = ("dark", "light")
HEAT = 4.0                      # 低热度：热度弧只占 220°~209.6°
ANG_IN = 180.0                  # 9 点钟：有轨道，用来量内沿
ANG_END = -40.0                 # 弧末端（220° 顺时针扫 260°）
ANG_START = 220.0               # 弧起点
ANG_GAP = 270.0                 # 正下方：弧的缺口，那里是纯底盘
MIN_D = 25.0                    # |Δlum| 下限：低于这个基本分不出来


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def drgb(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


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


_SAVED = {}


def legacy(on):
    """把轮廓退化成「只有外弧」= 改前的样子。

    `overlay.paintEvent` 是**实时**调 flame 的几何函数，所以在探针里替换这几个
    函数就等于换了绘制结果 —— 不必改生产代码，也不必去翻 git 里的旧版本。
    """
    if on:
        if not _SAVED:
            _SAVED["inner"] = flame.ring_edge_inner_radius
            _SAVED["cap"] = flame.ring_edge_cap_radius
        flame.ring_edge_inner_radius = flame.ring_edge_radius
        flame.ring_edge_cap_radius = lambda _d: 0.01
    elif _SAVED:
        flame.ring_edge_inner_radius = _SAVED.pop("inner")
        flame.ring_edge_cap_radius = _SAVED.pop("cap")


def geom(d):
    thick = flame.ring_thick(d)
    radius = flame.ring_radius(d)
    return {
        "d": d,
        "thick": thick,
        "radius": radius,
        "band_in": radius - thick / 2.0,
        "band_out": radius + thick / 2.0,
        "pit_r": flame.pit_radius(d),
        "plate_r": d / 2.0 - max(2.0, d * 0.012),
        "e_out": flame.ring_edge_radius(d),
        "e_in": flame.ring_edge_inner_radius(d),
        "e_cap": flame.ring_edge_cap_radius(d),
    }


def composite(img, desktop):
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    out.fill(QColor(*desktop))
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.drawImage(0, 0, img)
    p.end()
    return out


def probe_frame(app, dial, theme, alpha, desk, heat=HEAT, leg=False):
    """渲一帧（离屏 → 合成桌面），返回 RGB32 的 QImage。"""
    dial._theme = THEMES[theme]
    dial._bg_alpha = int(round(alpha * 255))
    dial._snap = scene(heat)
    legacy(leg)
    try:
        dial.repaint()
        app.processEvents()
        img = dial.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    finally:
        legacy(False)
    return composite(img, desk)


def px(img, x, y):
    pc = img.pixelColor(int(round(x)), int(round(y)))
    return (pc.red(), pc.green(), pc.blue())


def at(img, cx, cy, radius, deg, leg=False):
    a = math.radians(deg)
    return px(img, cx + radius * math.cos(a), cy - radius * math.sin(a))


def radial_profile(img, cx, cy, r_lo, r_hi, deg, step=0.5):
    """沿径向的亮度剖面 [(r, lum, rgb)]。"""
    prof = []
    r = r_lo
    while r <= r_hi + 1e-9:
        c = at(img, cx, cy, r, deg)
        prof.append((r, lum(c), c))
        r += step
    return prof


def tang_profile(img, cx, cy, radius, deg, lo=-17.0, hi=17.0, step=1.0):
    """在 r=radius 处沿**切向**跨过角度 deg 的剖面 [(t, lum, rgb)]。

    正方向 = 角度**递减**方向 = 弧的扫掠方向（屏幕坐标下的单位向量是
    (sin a, cos a)）。所以：
      · 末端 −40°：t<0 在弧上、t>0 进了缺口
      · 起点 220°：t>0 在弧上、t<0 进了缺口
    """
    a = math.radians(deg)
    bx = cx + radius * math.cos(a)
    by = cy - radius * math.sin(a)
    tx, ty = math.sin(a), math.cos(a)
    prof = []
    t = lo
    while t <= hi + 1e-9:
        c = px(img, bx + t * tx, by + t * ty)
        prof.append((t, lum(c), c))
        t += step
    return prof


def seam(prof, ref_a, ref_b):
    """剖面里「同时最远离两个参考色」的像素 → (分离度, 位置, rgb)。

    改前只有轨道和邻居两种色（中间是抗锯齿过渡），每个像素必然接近其中之一，
    分离度 ≈ 0；改后中间多一条线，分离度 = min(离轨道, 离邻居) 会跳到 100 上下。
    """
    la, lb = lum(ref_a), lum(ref_b)
    best = None
    for pos, l, c in prof:
        sep = min(abs(l - la), abs(l - lb))
        if best is None or sep > best[0]:
            best = (sep, pos, c)
    return best


def refs(img, cx, cy, g):
    """三根参考色：轨道（环带正中）、灶膛（内沿的邻居）、底盘（端头的邻居）。"""
    track = at(img, cx, cy, g["radius"], ANG_IN)
    pit = at(img, cx, cy, g["pit_r"] - max(3.0, g["thick"] * 0.45), ANG_IN)
    plate = at(img, cx, cy, g["plate_r"] - 3.0, ANG_GAP)
    return track, pit, plate


def fmt_prof(prof, step_label=True):
    return "  ".join("%s%+.0f:%3.0f" % ("" if step_label else "", pos, l)
                     for pos, l, _c in prof)


def section_now(app, dial):
    d = float(min(dial.width(), dial.height()))
    g = geom(d)
    cx = cy = dial.width() / 2.0
    print("盘 d=%.0f   环带 %.1f~%.1f（宽 %.1f）   灶膛 r=%.1f   盘沿 r=%.1f   环中心线 r=%.1f"
          % (d, g["band_in"], g["band_out"], g["thick"], g["pit_r"],
             g["plate_r"], g["radius"]))
    print("  轮廓几何：外弧 r=%.1f  内弧 r=%.1f  端头半圆 r=%.1f"
          % (g["e_out"], g["e_in"], g["e_cap"]))
    print("  末端角度 %.0f°（%.0f° 顺时针扫 %.0f°）　起点 %.0f°"
          % (ANG_END, ANG_START, ANG_START - ANG_END, ANG_START))

    r_lo = g["band_in"] - 7.0
    r_hi = g["band_in"] + 3.0
    for theme in THEME_NAMES:
        print("\n══ %s 主题　α=72%%　浅色桌面（用户报的那档）" % theme)
        for name, leg in (("改前", True), ("改后", False)):
            img = probe_frame(app, dial, theme, 0.72, (238, 238, 240), leg=leg)
            track, pit, plate = refs(img, cx, cy, g)
            pin = radial_profile(img, cx, cy, r_lo, r_hi, ANG_IN)
            sin_ = seam(pin, track, pit)
            send = tang_profile(img, cx, cy, g["radius"], ANG_END)
            s_end = seam(send, track, plate)
            print("  【%s】轨道 rgb%s lum%.0f　灶膛 lum%.0f　底盘 lum%.0f"
                  % (name, track, lum(track), lum(pit), lum(plate)))
            print("     内沿 r%.1f→%.1f 100°侧: %s" % (r_lo, r_hi, fmt_prof(pin)))
            print("       → 最佳像素 r%.1f rgb%s，离轨道 %+.0f / 离灶膛 %+.0f ⇒ 分离度 %.0f%s"
                  % (sin_[1], sin_[2], lum(sin_[2]) - lum(track),
                     lum(sin_[2]) - lum(pit), sin_[0],
                     "  ← 够" if sin_[0] >= MIN_D else "  ← 不够（这条边等于没画）"))
            print("     末端 t-17..+17（t<0 弧上 / t>0 缺口）: %s" % fmt_prof(send))
            print("       → 最佳像素 t%+.0f rgb%s，离轨道 %+.0f / 离底盘 %+.0f ⇒ 分离度 %.0f%s"
                  % (s_end[1], s_end[2], lum(s_end[2]) - lum(track),
                     lum(s_end[2]) - lum(plate), s_end[0],
                     "  ← 够" if s_end[0] >= MIN_D else "  ← 不够（这条边等于没画）"))

    print("\n══ 12 个组合（改后）：三处轮廓线的分离度，都要 ≥ %.0f" % MIN_D)
    print("   %-6s %-5s %-7s %10s %10s %10s" % ("主题", "α", "桌面", "内沿", "末端", "起点"))
    worst = 99.0
    for theme in THEME_NAMES:
        for apct in ALPHAS:
            for dname, desk in DESKTOPS:
                img = probe_frame(app, dial, theme, apct, desk)
                track, pit, plate = refs(img, cx, cy, g)
                a = seam(radial_profile(img, cx, cy, r_lo, r_hi, ANG_IN), track, pit)[0]
                b = seam(tang_profile(img, cx, cy, g["radius"], ANG_END), track, plate)[0]
                c = seam(tang_profile(img, cx, cy, g["radius"], ANG_START), track, plate)[0]
                worst = min(worst, a, b, c)
                mark = "" if min(a, b, c) >= MIN_D else "  ← 糊"
                print("   %-6s %-5s %-7s %10.0f %10.0f %10.0f%s"
                      % (theme, "%d%%" % round(apct * 100), dname, a, b, c, mark))
        print()
    print("   最差 %.0f（%s）" % (worst, "OK" if worst >= MIN_D else "不够"))


def zoom_tile(img, cx, cy, x, y, half, zoom):
    """以 (x, y) 为中心裁 half 半径的小块并放大。"""
    from PIL import Image
    im = QImage(img) if not isinstance(img, QImage) else img
    # QImage → PIL
    buf = im.constBits()
    buf.setsize(im.sizeInBytes())
    pil = Image.frombytes("RGB", (im.width(), im.height()), bytes(buf),
                          "raw", "BGRX")
    crop = pil.crop((int(x - half), int(y - half), int(x + half), int(y + half)))
    return crop.resize((int(half * 2 * zoom), int(half * 2 * zoom)), Image.NEAREST)


def spot(img, cx, cy, g, which):
    """三处的放大窗口中心 + 半宽。"""
    if which == "inner":                        # 内沿：180° 方向
        return cx - g["e_in"], cy, 26
    if which == "end":                          # 末端半圆
        a = math.radians(ANG_END)
        return cx + g["radius"] * math.cos(a), cy - g["radius"] * math.sin(a), 26
    a = math.radians(ANG_START)                 # 起点半圆
    return cx + g["radius"] * math.cos(a), cy - g["radius"] * math.sin(a), 26


def section_look(app, dial):
    """对照图：行 = 改前/改后，列 = 整盘 + 三处放大。"""
    from PIL import Image, ImageDraw
    d = float(min(dial.width(), dial.height()))
    g = geom(d)
    cx = cy = dial.width() / 2.0
    theme, alpha, desk = "dark", 0.72, (238, 238, 240)
    spots = (("整盘", None, 0), ("内沿 180°（贴灶膛）", "inner", 5.0),
             ("末端 −40°（转角）", "end", 5.0), ("起点 220°（被弧盖着）", "start", 5.0))
    rows = (("改前　只有外沿", True), ("改后　闭合轮廓", False))
    cell, pad, gap, band, left = 260, 20, 16, 96, 186
    W = pad * 2 + left + len(spots) * (cell + gap) - gap
    H = 140 + pad + len(rows) * (cell + band + gap) - gap
    canvas = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(canvas)
    f1, f2, f3 = _font(23), _font(16), _font(14)
    dr.text((pad, 12), "进度条边框：外圈 → 整圈闭合（dark 主题，α=72%，浅色桌面）",
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 48), "改前只有一条外弧：环带的内侧和两个端头是虚的，看过去像半条边。",
            fill=(96, 102, 116), font=f2)
    dr.text((pad, 70), "改后补上内弧 + 两个端头半圆（包住轨道的圆笔帽），轮廓闭合。"
                       "放大 5 倍，红框里是这条线。", fill=(96, 102, 116), font=f2)
    dr.text((pad, 92), "轨道 rgb(74,82,97) lum 81　灶膛 lum 21　浅底 α=72% 的底盘 lum 85 —— "
                       "三者挨在一起，没有这条线就分不开。", fill=(96, 102, 116), font=f2)

    for c, (cname, _w, _z) in enumerate(spots):
        dr.text((pad + left + c * (cell + gap) + 2, 116), cname, fill=(26, 28, 34), font=f2)

    for r, (rname, leg) in enumerate(rows):
        y = 140 + r * (cell + band + gap)
        dr.text((pad, int(y + cell / 2 - 10)), rname, fill=(40, 40, 50), font=f3)
        img_qt = probe_frame(app, dial, theme, alpha, desk, leg=leg)
        track, pit, plate = refs(img_qt, cx, cy, g)
        big = zoom_tile(img_qt, cx, cy, cx, cy, dial.width() / 2.0, 1.0)
        canvas.paste(big.resize((cell, cell), Image.LANCZOS), (pad + left, y))
        for c, (cname, which, zoom) in enumerate(spots):
            if which is None:
                continue
            x, yy, half = spot(img_qt, cx, cy, g, which)
            canvas.paste(zoom_tile(img_qt, cx, cy, x, yy, half, zoom),
                         (pad + left + c * (cell + gap), y))
            dr.rectangle([(pad + left + c * (cell + gap), y),
                          (pad + left + c * (cell + gap) + cell, y + cell)],
                         outline=(210, 90, 90))
        a = seam(radial_profile(img_qt, cx, cy, g["band_in"] - 7.0,
                                g["band_in"] + 3.0, ANG_IN), track, pit)[0]
        b = seam(tang_profile(img_qt, cx, cy, g["radius"], ANG_END), track, plate)[0]
        cc = seam(tang_profile(img_qt, cx, cy, g["radius"], ANG_START), track, plate)[0]
        txt = "内沿 %.0f　末端 %.0f　起点 %.0f　（分离度，≥%.0f 算画上了）" % (a, b, cc, MIN_D)
        dr.text((pad + left, y + cell + 8), txt, fill=(40, 40, 50), font=f3)
        print("   %-16s %s" % (rname.replace("　", " "), txt))

    out = HERE / "_ring_frame_probe.png"
    canvas.save(str(out), "PNG")
    print("\n对照图 %s  %s" % (out.name, canvas.size))


def main():
    tag = (sys.argv[1] if len(sys.argv) > 1 else "now").lower()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(Svc())
    dial._boot_done = True
    dial._campfire = True              # 走用户的实际视觉（篝火模式）
    dial.show()
    dial._timer.stop()
    app.processEvents()
    print("窗口 %dx%d" % (dial.width(), dial.height()))

    if tag in ("now", "all"):
        section_now(app, dial)
    if tag in ("look", "all"):
        section_look(app, dial)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
