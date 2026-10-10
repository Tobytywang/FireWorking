# -*- coding: utf-8 -*-
"""进度条「轨道外沿描边」探针 —— 轨道（未走段）和底盘糊在一起时，加条线能不能分开。

用户报：透明度 72 的时候，进度条的底色（轨道）和圆盘背景底色（底盘）区分度太低；
建议"把之前那圈白色边沿的设计套到进度条的边框上"（那圈边沿就是上一轮从底盘上
去掉的 `THEMES.rim` 描边）。

**注意**：用户第 6 轮又报了"现在只有外圈有，内圈和转角的那个地方也应该有"，于是
轮廓从「一条外弧」补成了**整圈闭合**（外弧 + 内弧 + 两个端头半圆）。本探针只量
**外沿**这一段（`sweep` / `look` / `full` 都是围绕它的）；内沿和端头在
`_ring_frame_probe.py`。两份一起看才是完整的四边。

量法：真实 `HeatDial` 离屏渲染（QWidget.grab，**绝不抓屏**）→ 合成到指定桌面底。
在**同一半径**上取两根射线：
  · 180°（9 点钟）—— 落在弧的**已覆盖段**里（弧从 220° 顺时针扫 260°，
    经 180/90/0 到 320°），且强度 4% 的热度弧只占 220°~209.6°，所以 180° 只有轨道
  · 270°（正下方）—— 弧的缺口，同一半径上什么都没有，是纯底盘
两者相减就是"轨道 vs 圆盘底色"的对比度，不用凑两组采样、也不受抗锯齿干扰。

跑法：
  .pyenv\\Scripts\\python.exe _ring_edge_probe.py now      # 当前状态剖面
  .pyenv\\Scripts\\python.exe _ring_edge_probe.py sweep    # 候选描边色 × 宽度扫参
  .pyenv\\Scripts\\python.exe _ring_edge_probe.py look     # 出 _ring_edge_look.png 对照图
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
from overlay import HeatDial, THEMES, START_DEG, SWEEP_DEG        # noqa: E402

FONT = "C:/Windows/Fonts/msyh.ttc"
ALPHAS = (0.0, 0.45, 0.72, 1.0)
DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
THEME_NAMES = ("dark", "light")
HEAT = 4.0                      # 低热度：热度弧只占 220°~209.6°，180° 是纯轨道
ANG_TRACK = 180.0               # 9 点钟：有轨道的方向
ANG_GAP = 270.0                 # 正下方：弧的缺口，纯底盘
MIN_D = 25.0                    # |Δlum| 下限：低于这个基本分不出来

# 候选描边色（暗盘配亮线、亮盘配暗线 —— 和原来 rim 的思路一致，但这次是**定色不透明**）
CAND = {
    "dark": (
        ("纯白", (255, 255, 255)),
        ("亮雾", (224, 229, 238)),
        ("中亮", (196, 203, 216)),
        ("蓝灰", (150, 159, 176)),
        ("muted", (169, 176, 192)),
    ),
    "light": (
        ("纯黑", (0, 0, 0)),
        ("深灰", (64, 71, 84)),
        ("muted", (95, 102, 116)),
        ("中灰", (130, 137, 150)),
    ),
}


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


def at(img, cx, cy, radius, deg):
    """半径 radius、角度 deg 上取 3×3 里亮度居中的像素（躲开抗锯齿）。"""
    a = math.radians(deg)
    x = int(round(cx + radius * math.cos(a)))
    y = int(round(cy - radius * math.sin(a)))
    vals = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            pc = img.pixelColor(x + dx, y + dy)
            c = (pc.red(), pc.green(), pc.blue())
            vals.append((lum(c), c))
    vals.sort(key=lambda v: v[0])
    return vals[4][1]


def geom(d):
    thick = flame.ring_thick(d)
    radius = flame.ring_radius(d)
    return {
        "thick": thick,
        "radius": radius,
        "band_out": radius + thick / 2.0,              # 环外沿
        "band_in": radius - thick / 2.0,               # 环内沿
        "plate_r": d / 2.0 - max(2.0, d * 0.012),
        "edge_w": flame.ring_edge_w(d) if hasattr(flame, "ring_edge_w") else 0.0,
    }


def probe_frame(app, dial, theme, alpha, desk, cand=None, edge_w=None, heat=HEAT):
    """渲一帧并读四个位置：轨道（180°）、底盘（270°）、描边（180° 外沿窗口取极值）。"""
    g = geom(float(min(dial.width(), dial.height())))
    saved_cand = THEMES[theme].get("track_edge")
    saved_fn = getattr(flame, "ring_edge_w", None)
    if cand is not None:
        THEMES[theme]["track_edge"] = tuple(cand)
    if edge_w is not None:
        flame.ring_edge_w = lambda _d, _w=float(edge_w): _w   # noqa: E731
    try:
        img = composite(shot(app, dial, theme, alpha, heat), desk)
    finally:
        if saved_cand is None:
            THEMES[theme].pop("track_edge", None)
        else:
            THEMES[theme]["track_edge"] = saved_cand
        if saved_fn is None:
            flame.__dict__.pop("ring_edge_w", None)
        else:
            flame.ring_edge_w = saved_fn

    c = dial.width() / 2.0
    g = geom(float(min(dial.width(), dial.height())))          # 还原后的诚实几何
    g["edge_w"] = float(edge_w or 0.0)
    out = {"img": img, "g": g}
    out["track"] = at(img, c, c, g["radius"], ANG_TRACK)
    out["plate"] = at(img, c, c, g["radius"], ANG_GAP)
    out["plate_outer"] = at(img, c, c, (g["band_out"] + g["plate_r"]) / 2.0, ANG_TRACK)
    if g["edge_w"] > 1.0:
        out["peak"] = edge_peak(img, c, c, g, out["track"], out["plate"])
    return out


def edge_peak(img, cx, cy, g, track, plate):
    """在"环外沿往外 edge_w"那一小段里，找**同时最能离开轨道和底盘**的像素。

    细线在半径方向只有 ~1px 是实心、两侧各 1px 是抗锯齿（实测 2.09px 的线：
    r87 是 121、r88 是 202（纯色）、r89 是 147）。所以这里**必须取单像素**，
    不能用 3×3 中位 —— 中位会把 1px 的线抹成半价（实测纯白只有 147），
    数字假性小一半还会看错相对强弱。大面积的轨道/底盘才用中位。

    返回 (分离度, 半径, rgb)。分离度 = min(|lum−轨道|, |lum−底盘|)：
    要"两边都分得开"才算数。
    """
    tl, pl = lum(track), lum(plate)
    y0 = int(round(cy))
    best = None
    for x in range(int(math.floor(cx - g["band_out"] - g["edge_w"] - 1.2)),
                   int(math.ceil(cx - g["band_out"] + 1.2)) + 1):
        for y in (y0 - 1, y0, y0 + 1):
            pc = img.pixelColor(x, y)
            c = (pc.red(), pc.green(), pc.blue())
            sep = min(abs(lum(c) - tl), abs(lum(c) - pl))
            if best is None or sep > best[0]:
                best = (sep, cx - x, c)
    return best


def section_now(app, dial):
    print("1. 当前状态：轨道（180°）vs 底盘（270°，同一半径）")
    print("   %-6s %-5s %-7s %-16s %-16s %7s %7s %s"
          % ("主题", "α", "桌面", "轨道", "底盘", "Δlum", "ΔRGB", ""))
    worst = []
    for theme in THEME_NAMES:
        for apct in ALPHAS:
            for dname, desk in DESKTOPS:
                r = probe_frame(app, dial, theme, apct, desk)
                dl = lum(r["track"]) - lum(r["plate"])
                de = math.sqrt(sum((a - b) ** 2 for a, b in zip(r["track"], r["plate"])))
                flag = "  ← 糊（分不出来）" if (abs(dl) < MIN_D or de < 40) else ""
                if theme == "dark":
                    worst.append((de, apct, dname))
                print("   %-6s %-5s %-7s %-16s %-16s %+7.1f %7.1f%s"
                      % (theme, "%d%%" % round(apct * 100), dname,
                         "rgb%s" % (r["track"],), "rgb%s" % (r["plate"],), dl, de, flag))
            print()
    worst.sort()
    print("   dark 主题最糊（ΔRGB 最小）的四个组合：")
    for de, apct, dname in worst[:4]:
        print("     α=%3d%%  %-6s  ΔRGB %5.1f" % (round(apct * 100), dname, de))


def section_sweep(app, dial):
    print("\n2. 候选描边色 × 宽度：线要同时远离**轨道**和**底盘**才算有区分度")
    g = geom(float(min(dial.width(), dial.height())))
    print("   盘 d=%.0f  环中心线 r=%.1f  笔宽 %.1f（带 %.1f~%.1f）  盘半径 %.1f  外沿余量 %.1fpx"
          % (float(min(dial.width(), dial.height())), g["radius"], g["thick"],
             g["band_in"], g["band_out"], g["plate_r"], g["plate_r"] - g["band_out"]))
    print("   分离度 = min(|Δlum 对轨道|, |Δlum 对底盘|)，在描边窗口里取最大（细线只有 1px 实心）")
    for theme in THEME_NAMES:
        for wname, w in (("1.5px", 1.5), ("2.1px", 2.09), ("2.6px", 2.6), ("3.2px", 3.2)):
            print("\n   ── %s 主题　描边宽 %s" % (theme, wname))
            print("      %-8s %-24s %-24s" % ("候选", "轨道/底盘撞车时（最差）", "全部组合（最差）"))
            for cname, cand in CAND[theme]:
                hit, allsep = 99.0, 99.0
                w1 = w2 = ""
                for apct in ALPHAS:
                    for dname, desk in DESKTOPS:
                        r = probe_frame(app, dial, theme, apct, desk,
                                        cand=cand, edge_w=w)
                        if "peak" not in r:
                            continue
                        sep, rr, cc = r["peak"]
                        tag = "%s α%d%%(r%.0f)" % (dname, round(apct * 100), rr)
                        if sep < allsep:
                            allsep, w2 = sep, tag
                        # 只有"轨道和底盘本来就撞在一起"的组合才需要这条线
                        if abs(lum(r["track"]) - lum(r["plate"])) < MIN_D and sep < hit:
                            hit, w1 = sep, tag
                mark = "  OK" if hit >= MIN_D else "  ← 撞车时不够"
                print("      %-8s %-24s %-24s%s"
                      % (cname, "%5.1f  %s" % (hit, w1 or "—"),
                         "%5.1f  %s" % (allsep, w2), mark))
            print("      （左列若显示 —，说明该宽度/主题下没有组合撞车；右列是全部 12 个组合里最差的）")


def radial_strip(img, cx, cy, r_lo, r_hi, zoom, row_h=30):
    """把 180° 方向、r_lo~r_hi 那一段的像素抽成一条横向色带。

    **横向 = 径向**（左 = 半径小的一侧 = 环内，右 = 盘外）。取 y=cy−1/cy/cy+1 三行的
    逐通道中位色，避免某一行的抗锯齿把结论带偏。
    """
    from PIL import Image
    n = int(math.ceil(r_hi - r_lo))
    bar = Image.new("RGB", (n, 1))
    ys = [int(round(cy)) - 1, int(round(cy)), int(round(cy)) + 1]
    for i in range(n):
        x = int(round(cx - (r_lo + i + 0.5)))
        cols = []
        for y in ys:
            pc = img.pixelColor(x, y)
            cols.append((pc.red(), pc.green(), pc.blue()))
        cols.sort(key=lum)
        bar.putpixel((i, 0), cols[1])
    return bar.resize((n * zoom, row_h), Image.NEAREST)


def section_look(app, dial):
    """出对照图：行 = 候选（含"无描边"），列 = 桌面底；每条是环外沿的径向剖面。"""
    from PIL import Image, ImageDraw
    cands = [("无描边", (0, 0, 0, 0))] + list(CAND["dark"])
    alpha = 0.72
    zoom, row_h = 9, 30
    g = geom(float(min(dial.width(), dial.height())))
    cx, cy = dial.width() / 2.0, dial.height() / 2.0
    r_lo, r_hi = g["band_out"] - 7.0, g["plate_r"] + 2.0
    sw = int(math.ceil(r_hi - r_lo)) * zoom
    pad, gap, band, left = 18, 22, 52, 128
    W = pad * 2 + left + len(DESKTOPS) * (sw + gap) - gap
    H = 118 + pad + len(cands) * (row_h + band + gap) - gap
    canvas = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(canvas)
    f1, f2, f3 = _font(21), _font(15), _font(14)
    dr.text((pad, 10), "进度条外沿描边候选（dark 主题，α=72%%，径向剖面 ×%d）" % zoom,
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 40), "每条色带 = 环外沿那 %.0f~%.0f px 的像素（180° 方向）。"
                       "**左 = 环内（轨道）　右 = 盘外（底盘/桌面）**，中间那条亮/暗线就是描边。"
            % (r_lo, r_hi), fill=(96, 102, 116), font=f2)
    dr.text((pad, 62), "判据：描边要同时和轨道、底盘拉开 —— |Δlum| 两边都 ≥ %.0f 才算有区分度。"
                       "「线分离度」= min(对轨道, 对底盘)，越大越分得开。" % MIN_D,
            fill=(96, 102, 116), font=f2)
    for c, (dname, _d) in enumerate(DESKTOPS):
        dr.text((pad + left + c * (sw + gap) + 4, 92), dname, fill=(26, 28, 34), font=f2)

    # 色带上的刻度：环外沿 / 盘外沿 各画一道竖直参考线
    for c, (dname, desk) in enumerate(DESKTOPS):
        for rx in (g["band_out"], g["plate_r"]):
            xx = pad + left + c * (sw + gap) + int((rx - r_lo) * zoom)
            dr.line([(xx, 100), (xx, 113)], fill=(150, 155, 165), width=1)
    dr.text((pad + left, 100), "刻度：环外沿 / 盘外沿", fill=(150, 155, 165), font=f3)

    for r, (cname, cand) in enumerate(cands):
        y = 118 + r * (row_h + band + gap)
        dr.text((pad, int(y + row_h / 2 - 10)), cname, fill=(40, 40, 50), font=f3)
        for c, (dname, desk) in enumerate(DESKTOPS):
            x = pad + left + c * (sw + gap)
            res = probe_frame(app, dial, "dark", alpha, desk, cand=cand, edge_w=2.09)
            canvas.paste(radial_strip(res["img"], cx, cy, r_lo, r_hi, zoom, row_h), (x, y))
            dt = lum(res["track"]) - lum(res["plate"])
            line = "轨↔盘 %+.0f" % dt
            if "peak" in res:
                sep, rr, cc = res["peak"]
                line += "　线分离度 %.0f" % sep
                print("     %-8s %-6s 线峰值 r%.1f rgb%-16s 轨道%-16s 底盘%-16s 分离度 %.1f"
                      % (cname, dname, rr, cc, res["track"], res["plate"], sep))
            color = (200, 40, 40) if (abs(dt) < MIN_D and
                                      res.get("peak", (99,))[0] < MIN_D) else (40, 40, 50)
            dr.text((x + 2, y + row_h + 6), line, fill=color, font=f3)
    out = HERE / "_ring_edge_look.png"
    canvas.save(str(out), "PNG")
    print("\n对照图 %s  %s" % (out.name, canvas.size))


def section_full(app, dial):
    """最终交付图：改前 / 改后两行 × 四个实际场景。"""
    from PIL import Image, ImageDraw
    rows = (("改前　环上没线", (0, 0, 0, 0)), ("改后　环外沿描边", None))
    cols = (
        ("深终端 α=72%（不撞）", 0.72, (30, 30, 36), 4.0),
        ("浅色 α=72%　← 用户报的那档", 0.72, (238, 238, 240), 4.0),
        ("浅色 α=45%", 0.45, (238, 238, 240), 4.0),
        ("浅色 α=72% 高热度", 0.72, (238, 238, 240), 62.0),
    )
    scale, pad, gap, band, left = 2, 18, 16, 64, 150
    cell = dial.width() * scale
    W = pad * 2 + left + len(cols) * (cell + gap) - gap
    H = 128 + pad + len(rows) * (cell + band + gap) - gap
    canvas = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(canvas)
    f1, f2, f3 = _font(23), _font(15), _font(14)
    dr.text((pad, 10), "进度条和圆盘底色糊在一起：环外沿加一条线（dark 主题，篝火模式）",
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 44), "透明度 72% 时，底盘是半透明的、会跟着桌面漂 —— 撞上浅色桌面时底盘到 "
                       "lum 84.8，和轨道（81.4）几乎重合，", fill=(96, 102, 116), font=f2)
    dr.text((pad, 64), "第 2 列就是用户报的那档：改前进度条（环上那条带子）和盘面连成一片；"
                       "改后在环的外沿描了一条 2px 的线，边界重新立起来。",
            fill=(96, 102, 116), font=f2)
    dr.text((pad, 86), "「轨↔盘」= 轨道亮度 − 底盘亮度（同一半径、180°/270° 两根射线）。"
                       "|Δ| < 25 就是分不出来。", fill=(96, 102, 116), font=f2)

    tmp = HERE / "_ring_edge_cell_full.png"
    for c, (cname, _a, _d, _h) in enumerate(cols):
        dr.text((pad + left + c * (cell + gap) + 2, 104), cname, fill=(26, 28, 34), font=f2)
    for r, (rname, cand) in enumerate(rows):
        y = 128 + r * (cell + band + gap)
        dr.text((pad, int(y + cell / 2 - 10)), rname, fill=(40, 40, 50), font=f3)
        for c, (cname, apct, desk, heat) in enumerate(cols):
            x = pad + left + c * (cell + gap)
            res = probe_frame(app, dial, "dark", apct, desk, cand=cand,
                              edge_w=2.09, heat=heat)
            res["img"].save(str(tmp), "PNG")
            tile = Image.open(tmp).convert("RGB").resize((cell, cell), Image.LANCZOS)
            canvas.paste(tile, (x, y))
            dt = lum(res["track"]) - lum(res["plate"])
            txt = "轨↔盘 %+.0f" % dt
            sep = res["peak"][0] if "peak" in res else 0.0
            if sep:
                txt += "　线分离度 %.0f" % sep
                txt += "　线↔轨 %+.0f　线↔盘 %+.0f" % (
                    lum(res["peak"][2]) - lum(res["track"]),
                    lum(res["peak"][2]) - lum(res["plate"]))
            color = (200, 40, 40) if abs(dt) < MIN_D and sep < MIN_D else (40, 40, 50)
            dr.text((x + 2, y + cell + 7), txt, fill=color, font=f3)
            print("   %-14s %-24s %s" % (rname, cname, txt))
    canvas.save(str(HERE / "_ring_edge_probe.png"), "PNG")
    try:
        tmp.unlink()
    except OSError:
        pass
    print("\n对照图 _ring_edge_probe.png  %s" % (canvas.size,))


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
    if tag in ("sweep", "all"):
        section_sweep(app, dial)
    if tag in ("look", "all"):
        section_look(app, dial)
    if tag in ("full", "all"):
        section_full(app, dial)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
