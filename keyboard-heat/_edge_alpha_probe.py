# -*- coding: utf-8 -*-
"""环带轮廓线「透明度反相」探针 —— 底盘越实心，线越淡；底盘全透明，线画满。

用户第 7 轮原话：「这个白色的边框，也为他设计透明度，但是它的透明度和整体的透明度
是反着来的：如果整体的透明度是 100%，那么它的透明度是 0%；如果整体的透明度是 0%，
那么它的透明度是 100%」。

换算成代码里的量（菜单叫「底盘不透明度」，值就是 `bg_alpha`）：
    底盘不透明 100%（盘面实心）→ 线不透明 0%（看不见）
    底盘不透明   0%（盘面全透）→ 线不透明 100%（画满）
也就是 `flame.track_edge_alpha(bg_alpha) = 1 − bg_alpha`。

本探针逐档量两件事：
  · **线自己**的分离度 = min(|Δlum 对轨道|, |Δlum 对它的邻居（底盘/桌面）|)
  · **盘面自己**的分离度 = |lum 轨道 − lum 底盘|
线存在的理由就是第二项不够（浅色桌面 + α≈72% 时轨道 81.4 撞底盘 84.8），
所以判据是 **max(这两项) ≥ MIN_D**：边界只要有一种东西交代得清就算可辨。
反相曲线让"线淡下去"和"盘面站起来"发生在同一档，这个 max 才是恒定够用的。

量的方法：真实 `HeatDial` 离屏渲染（QWidget.grab，绝不抓屏）→ 合成到桌面底。
「改前」= 把 `flame.track_edge_alpha` 换成恒为 1 的 lambda（渲染路径实时读它，
不用改生产代码、也不用翻 git）。

跑法：
  .pyenv\\Scripts\\python.exe _edge_alpha_probe.py now    # 两个曲线 × 4 档 × 2 主题 × 3 桌面
  .pyenv\\Scripts\\python.exe _edge_alpha_probe.py look   # 出 _edge_alpha_probe.png
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
ALPHAS = (0.0, 0.45, 0.72, 1.0)          # 菜单里的四档
DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)
THEME_NAMES = ("dark", "light")
HEAT = 4.0                      # 低热度：热度弧只占 220°~209.6°，180° 处是纯轨道
ANG_TRACK = 180.0               # 9 点钟：有轨道，量"线 vs 轨道"
ANG_GAP = 270.0                 # 正下方：弧的缺口，量"底盘"（同半径上没有环带）
MIN_D = 25.0                    # |Δlum| 下限：低于这个基本分不出来


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


# ── 两个曲线 ─────────────────────────────────────────────────────────────
CURVES = (
    ("改前　线恒为不透明", lambda _a: 1.0),
    ("改后　线不透明 = 1 − 底盘不透明", flame.track_edge_alpha),
)
_SAVED_FN = {}


def use_curve(fn):
    """渲染路径实时读 `flame.track_edge_alpha`，换掉它就等于换了一版绘制。"""
    if "fn" not in _SAVED_FN:
        _SAVED_FN["fn"] = flame.track_edge_alpha
    flame.track_edge_alpha = fn


def restore_curve():
    if _SAVED_FN:
        flame.track_edge_alpha = _SAVED_FN.pop("fn")


def geom(d):
    thick = flame.ring_thick(d)
    radius = flame.ring_radius(d)
    return {
        "d": d,
        "thick": thick,
        "radius": radius,
        "band_in": radius - thick / 2.0,
        "band_out": radius + thick / 2.0,
        "edge_w": flame.ring_edge_w(d),
        "pit_r": flame.pit_radius(d),
        "plate_r": d / 2.0 - max(2.0, d * 0.012),
    }


def composite(img, desktop):
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    out.fill(QColor(*desktop))
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    p.drawImage(0, 0, img)
    p.end()
    return out


def probe_frame(app, dial, theme, alpha, desk, heat=HEAT):
    """渲一帧（离屏 → 合成桌面），返回 RGB32 的 QImage。曲线由 `use_curve` 决定。"""
    dial._theme = THEMES[theme]
    dial._bg_alpha = int(round(alpha * 255))
    dial._snap = scene(heat)
    dial.repaint()
    app.processEvents()
    img = dial.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)
    return composite(img, desk)


def px(img, x, y):
    pc = img.pixelColor(int(round(x)), int(round(y)))
    return (pc.red(), pc.green(), pc.blue())


def at(img, cx, cy, radius, deg):
    a = math.radians(deg)
    return px(img, cx + radius * math.cos(a), cy - radius * math.sin(a))


def edge_peak(img, cx, cy, g, track, neighbor):
    """环外沿那一小段里**同时最能离开轨道和邻居**的像素。

    细线在半径方向只有 ~1px 是实心、两侧各 1px 抗锯齿（实测 2.09px 的线：
    r88 实心 lum 202，r87 是 121、r89 是 147），固定取"线中心"会取到 AA 像素、
    数字假性小一半。所以扫一段窗口取极值 —— 人眼看到的也确实是整段。
    （同理**必须取单像素**：3×3 中位会把 1px 的线抹成半价。）

    返回 (分离度, 半径, rgb)；分离度 = min(|lum−轨道|, |lum−邻居|)。
    """
    tl, nl = lum(track), lum(neighbor)
    best = None
    r = g["band_out"] - 1.2
    hi = g["band_out"] + g["edge_w"] + 1.2
    while r <= hi:
        c = at(img, cx, cy, r, ANG_TRACK)
        sep = min(abs(lum(c) - tl), abs(lum(c) - nl))
        if best is None or sep > best[0]:
            best = (sep, r, c)
        r += 0.5
    return best


def measure(app, dial, theme, alpha, desk, g):
    """一个组合的全套数字。"""
    img = probe_frame(app, dial, theme, alpha, desk)
    track = at(img, dial.width() / 2.0, dial.height() / 2.0, g["radius"], ANG_TRACK)
    plate = at(img, dial.width() / 2.0, dial.height() / 2.0,
               g["plate_r"] - 3.0, ANG_GAP)
    peak = edge_peak(img, dial.width() / 2.0, dial.height() / 2.0, g, track, plate)
    return {
        "img": img,
        "track": track,
        "plate": plate,
        "plate_sep": abs(lum(track) - lum(plate)),
        "edge_sep": peak[0],
        "edge_rgb": peak[2],
        "edge_r": peak[1],
        "keep": flame.track_edge_alpha(alpha),
        "ok": max(abs(lum(track) - lum(plate)), peak[0]) >= MIN_D,
    }


def section_now(app, dial):
    d = float(min(dial.width(), dial.height()))
    g = geom(d)
    print("盘 d=%.0f  轨道带 %.1f~%.1f（宽 %.1f）  轮廓线宽 %.2f  盘半径 %.1f"
          % (d, g["band_in"], g["band_out"], g["thick"], g["edge_w"], g["plate_r"]))
    print("判据：max(盘面自己 vs 轨道的差, 线的分离度) ≥ %.0f —— 边界有一种东西交代清就行"
          % MIN_D)
    worst = {}
    for cname, fn in CURVES:
        use_curve(fn)
        try:
            print("\n══ %s" % cname)
            print("   %-6s %-6s %-7s %8s %8s %8s   %-22s %s"
                  % ("主题", "底盘α", "桌面", "轨道", "底盘", "线", "结论", "线色"))
            for theme in THEME_NAMES:
                for alpha in ALPHAS:
                    for dname, desk in DESKTOPS:
                        r = measure(app, dial, theme, alpha, desk, g)
                        mark = "可辨" if r["ok"] else "★糊了★"
                        if not r["ok"]:
                            worst[cname] = (theme, alpha, dname)
                        print("   %-6s %-6s %-7s %8.0f %8.0f %8.0f   %-22s %s"
                              % (theme, "%d%%" % round(alpha * 100), dname,
                                 lum(r["track"]), lum(r["plate"]), r["edge_sep"],
                                 "max %.0f" % max(r["plate_sep"], r["edge_sep"]), mark))
        finally:
            restore_curve()
    print()
    for cname, _fn in CURVES:
        bad = worst.get(cname)
        print("   %-28s %s" % (cname, "全部可辨" if not bad else "最差档 %s" % (bad,)))


def section_now_table(app, dial):
    """更紧凑的一张表：每档只看"最糊的那个桌面"（三桌面取最差）。"""
    d = float(min(dial.width(), dial.height()))
    g = geom(d)
    print("\n══ 逐档对照（每个 α 取三个桌面里最差的那个）")
    print("   %-24s %-6s %-6s %10s %10s %10s   %s"
          % ("曲线", "主题", "底盘α", "线不透明", "盘面分离", "线分离", "判定"))
    for cname, fn in CURVES:
        use_curve(fn)
        try:
            for theme in THEME_NAMES:
                for alpha in ALPHAS:
                    rows = [measure(app, dial, theme, alpha, desk, g)
                            for _n, desk in DESKTOPS]
                    worst = min(rows, key=lambda r: max(r["plate_sep"], r["edge_sep"]))
                    verdict = max(worst["plate_sep"], worst["edge_sep"])
                    print("   %-24s %-6s %-6s %10.2f %10.0f %10.0f   %s（%.0f %s%.0f）"
                          % (cname, theme, "%d%%" % round(alpha * 100),
                             flame.track_edge_alpha(alpha) if cname.startswith("改后")
                             else 1.0,
                             worst["plate_sep"], worst["edge_sep"],
                             "可辨" if worst["ok"] else "★糊★",
                             verdict, ">=" if worst["ok"] else "<", MIN_D))
        finally:
            restore_curve()


def curve_panel(width, height):
    """把两条曲线画出来：横轴 = 底盘不透明度，纵轴 = 线的等效不透明度。"""
    from PIL import Image, ImageDraw
    panel = Image.new("RGB", (width, height), (255, 255, 255))
    dr = ImageDraw.Draw(panel)
    f = _font(15)
    f2 = _font(13)
    pad_l, pad_r, pad_t, pad_b = 78, 30, 52, 56
    x0, y0 = pad_l, height - pad_b          # 原点
    x1, y1 = width - pad_r, pad_t
    dr.text((14, 10), "线的不透明度 vs 底盘不透明度", fill=(26, 28, 34), font=f)
    dr.text((14, 30), "（纵轴：线）", fill=(96, 102, 116), font=f2)
    # 网格
    for i in range(5):
        gx = x0 + (x1 - x0) * i / 4.0
        gy = y0 - (y0 - y1) * i / 4.0
        dr.line([(gx, y1), (gx, y0)], fill=(226, 228, 232))
        dr.line([(x0, gy), (x1, gy)], fill=(226, 228, 232))
        dr.text((gx - 10, y0 + 6), "%d%%" % (i * 25), fill=(96, 102, 116), font=f2)
        dr.text((34, gy - 8), "%.1f" % (i * 0.25), fill=(96, 102, 116), font=f2)
    dr.line([(x0, y0), (x1, y0)], fill=(120, 126, 138))
    dr.line([(x0, y0), (x0, y1)], fill=(120, 126, 138))
    dr.text((x0 + 130, y0 + 30), "底盘不透明度", fill=(96, 102, 116), font=f2)

    def pt(a, k):
        return (x0 + (x1 - x0) * a, y0 - (y0 - y1) * k)

    styles = (((214, 92, 92), "改前：线恒为不透明（1.0）",
               (x1 - 224, y1 + 8)),
              ((46, 138, 96), "改后：线不透明 = 1 − 底盘不透明",
               (x1 - 232, y0 - 60)))
    for (col, label, pos), fn in zip(styles, (CURVES[0][1], CURVES[1][1])):
        dr.line([pt(a / 100.0, fn(a / 100.0)) for a in range(0, 101, 2)],
                fill=col, width=3)
        for a in ALPHAS:
            x, y = pt(a, fn(a))
            dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=col)
        dr.text(pos, label, fill=col, font=f2)
    return panel


def zoom_radial(img, cx, cy, g, zoom=10, zoom_t=4, half_t=9.0):
    """裁「径向 × 切向」的一小段：180° 的径向就是水平方向。

    窗口横跨「轨道尾段 → 轮廓线 → 底盘」，放大后横着看就是一条剖面条。
    半径范围**不能对称取** —— 盘只有 190px，环外沿离窗口左边只剩 ~8px，
    `cx ± half` 会取到画布外（越界像素是 `(0,0,0,255)`，那是假数据）。
    所以按"环内沿往里 4px → 盘半径往里 3px"来定。
    """
    from PIL import Image
    buf = img.constBits()
    buf.setsize(img.sizeInBytes())
    pil = Image.frombytes("RGB", (img.width(), img.height()), bytes(buf), "raw", "BGRX")
    r_lo, r_hi = g["band_in"] - 4.0, g["plate_r"] - 3.0
    box = (int(round(cx - r_hi)), int(round(cy - half_t)),
           int(round(cx - r_lo)), int(round(cy + half_t)))
    crop = pil.crop(box)
    return crop.resize((crop.width * zoom, crop.height * zoom_t), Image.NEAREST)


def section_gamma(app, dial):
    """要不要把中段抬亮：γ < 1 时端点**一动不动**（0^γ=0、1^γ=1），只抬中间。"""
    d = float(min(dial.width(), dial.height()))
    g = geom(d)
    print("\n══ 曲线指数 γ（`flame.TRACK_EDGE_ALPHA_GAMMA`）：线不透明 = (1 − α)^γ")
    print("   %-6s %s %10s   %s"
          % ("γ", "".join("%12s" % ("底盘α=%d%%" % round(a * 100)) for a in ALPHAS),
             "最差 max", "说明"))
    for gm in (1.0, 0.75, 0.5):
        use_curve(lambda a, _gm=gm: max(0.0, (1.0 - a) ** _gm))
        try:
            worst = 99.0
            for theme in THEME_NAMES:
                for a in ALPHAS:
                    for _n, desk in DESKTOPS:
                        r = measure(app, dial, theme, a, desk, g)
                        worst = min(worst, max(r["plate_sep"], r["edge_sep"]))
            ks = [(1.0 - a) ** gm for a in ALPHAS]
            tip = ("严格线性＝用户话的字面意思" if gm == 1.0
                   else "中段抬亮 %.0f%%" % ((ks[2] / 0.28 - 1.0) * 100))
            print("   %-6.2f %s %10.0f   %s"
                  % (gm, "".join("%11.0f%%" % (k * 100) for k in ks), worst, tip))
        finally:
            restore_curve()


def zoom_tile(img, cx, cy, x, y, half, zoom, out_w):
    """以 (x, y) 为心裁 half 半径的方块、放大后缩到 out_w 宽（整盘用）。"""
    from PIL import Image
    buf = img.constBits()
    buf.setsize(img.sizeInBytes())
    pil = Image.frombytes("RGB", (img.width(), img.height()), bytes(buf), "raw", "BGRX")
    crop = pil.crop((int(x - half), int(y - half), int(x + half), int(y + half)))
    side = int(round(out_w / float(zoom)))
    return crop.resize((side * zoom, side * zoom), Image.NEAREST).resize(
        (out_w, out_w), Image.LANCZOS)


def section_look(app, dial):
    """对照图：行 = 曲线（改前/改后），列 = 菜单的四档底盘不透明度。"""
    from PIL import Image, ImageDraw
    d = float(min(dial.width(), dial.height()))
    g = geom(d)
    cx = cy = dial.width() / 2.0
    theme, desk, dname = "dark", (238, 238, 240), "浅色桌面"
    # 与 zoom_radial 的默认参数一致：径向 (plate_r−3) − (band_in−4) ≈ 19px ×10
    tile_w = int(round((g["plate_r"] - 3.0) - (g["band_in"] - 4.0))) * 10
    tile_h = int(2 * 9.0 * 4)
    pad, gap, band, left = 20, 16, 76, 214
    panel_h = 230
    W = pad * 2 + left + len(ALPHAS) * (tile_w + gap) - gap
    H = (150 + pad + len(CURVES) * (tile_h + band + gap)
         + (tile_w + 52) + panel_h)
    canvas = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(canvas)
    f1, f2, f3 = _font(23), _font(16), _font(14)
    dr.text((pad, 12), "进度条边框的透明度：从「恒为不透明」改成「与底盘反相」",
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 48), "dark 主题、%s、低热度。每格是环外沿的一小段（横向 = 径向，"
                       "放大 10×4）：左边是轨道，右边是底盘，中间那条线就是边框。"
            % dname, fill=(96, 102, 116), font=f2)
    dr.text((pad, 70), "判据：max(盘面自己 vs 轨道的亮度差, 线的分离度) ≥ %.0f —— "
                       "线淡下去的那几档，盘面自己就够分了；线画满的那档，盘面已经不参与。"
            % MIN_D, fill=(96, 102, 116), font=f2)
    dr.text((pad, 92), "注意 α=100% 那列：改前还有一条线（其实多余 —— 盘面 27 vs 轨道 81），"
                       "改后线消失，边界由盘面自己交代。", fill=(96, 102, 116), font=f2)

    for c, alpha in enumerate(ALPHAS):
        x = pad + left + c * (tile_w + gap)
        dr.text((x + 4, 120), "底盘不透明 %d%%" % round(alpha * 100),
                fill=(26, 28, 34), font=f2)

    for r, (cname, fn) in enumerate(CURVES):
        y = 150 + r * (tile_h + band + gap)
        use_curve(fn)
        try:
            dr.text((pad, int(y + tile_h / 2 - 10)), cname, fill=(40, 40, 50), font=f3)
            for c, alpha in enumerate(ALPHAS):
                x = pad + left + c * (tile_w + gap)
                res = measure(app, dial, theme, alpha, desk, g)
                canvas.paste(zoom_radial(res["img"], cx, cy, g), (x, y))
                dr.rectangle([(x, y), (x + tile_w, y + tile_h)], outline=(206, 210, 216))
                dr.text((x + 2, y + tile_h + 6),
                        "线不透明 %.0f%%" % (res["keep"] * 100), fill=(40, 40, 50),
                        font=f3)
                dr.text((x + 2, y + tile_h + 24),
                        "线 %.0f ／ 盘面 %.0f" % (res["edge_sep"], res["plate_sep"]),
                        fill=(40, 40, 50), font=f3)
            row = [measure(app, dial, theme, a, desk, g) for a in ALPHAS]
            dr.text((pad + left, y + tile_h + 46),
                    "max = %s   %s" % (" / ".join("%.0f" % max(x["plate_sep"], x["edge_sep"])
                                                 for x in row),
                                       "全部 ≥ %.0f，可辨" % MIN_D
                                       if all(x["ok"] for x in row) else "★有档糊★"),
                    fill=(40, 40, 50), font=f3)
        finally:
            restore_curve()

    # 整盘一行（只出改后）：端点长什么样，得看全盘 —— 环外沿那一小段看不出"线还在不在"
    y = 150 + len(CURVES) * (tile_h + band + gap)
    use_curve(CURVES[1][1])
    try:
        dr.text((pad, int(y + 95 - 10)), "改后　整盘观感", fill=(40, 40, 50), font=f3)
        for c, alpha in enumerate(ALPHAS):
            x = pad + left + c * (tile_w + gap)
            img = probe_frame(app, dial, theme, alpha, desk)
            canvas.paste(zoom_tile(img, cx, cy, cx, cy, dial.width() / 2.0, 1.0, tile_w),
                         (x, y))
            dr.text((x + 2, y + tile_w + 6),
                    "底盘不透明 %d%%" % round(alpha * 100), fill=(40, 40, 50), font=f3)
    finally:
        restore_curve()

    panel_y = H - panel_h - 4
    panel = curve_panel(W - pad * 2, panel_h)
    canvas.paste(panel, (pad, panel_y))

    out = HERE / "_edge_alpha_probe.png"
    canvas.save(str(out), "PNG")
    print("\n对照图 %s  %s" % (out.name, canvas.size))


def main():
    tag = (sys.argv[1] if len(sys.argv) > 1 else "now").lower()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(Svc())
    dial._boot_done = True
    dial.show()
    dial._timer.stop()
    app.processEvents()
    print("窗口 %dx%d   篝火模式 %s" % (dial.width(), dial.height(), dial._campfire))

    if tag in ("now", "all"):
        section_now(app, dial)
        section_now_table(app, dial)
        section_gamma(app, dial)
    if tag in ("look", "all"):
        section_look(app, dial)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
