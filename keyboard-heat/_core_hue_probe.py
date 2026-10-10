# -*- coding: utf-8 -*-
"""最前面那层火焰为什么被读成"绿" —— 逐层色相实测 + 焰芯暖白改前/改后对照。

用户："最前面那层火焰,我觉得它颜色有点'绿', 可以把它调成更加偏向黄+白的颜色吗?"

**先说清一个反直觉点：黑体色阶里没有绿。** 色阶 H 从 0° 走到 47.2°，全程
R > G > B（见 _layer_hue_probe.py 的 A 节）。所以"绿"不可能是某个像素真的
G > R，只能是**同时对比**：一块低饱和的灰米色被全饱和的橙黄包围，
就会被推成"偏冷"，而在这簇火的语境里"偏冷"正好落在黄绿侧。

A  真实渲染逐层色相（帧差掩码 + 逐通道中位）—— 哪一层最灰
   把 flame.LAYERS 依次截断渲同一帧、相邻帧做差，取每层**真正露出来**的像素。
   被内层盖住的不算、被前景柴堆挡住的不算。

B  改前 / 改后 逐层对照 + 放大图

    .pyenv\\Scripts\\python.exe _core_hue_probe.py
"""
from __future__ import annotations

import colorsys
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from heatcore import load_config                    # noqa: E402

try:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    print("SKIP 这个解释器没有 PyQt6：%s" % exc)
    raise SystemExit(2)

import flame                                       # noqa: E402
from overlay import HeatDial                       # noqa: E402
from PIL import Image, ImageDraw                   # noqa: E402

PHASE = 3.8
HEATS = [(0.0, "idle"), (19.0, "h19"), (50.0, "h50"), (100.0, "h100")]
FONT = "C:/Windows/Fonts/msyh.ttc"
OUT = HERE / "_core_hue_probe.png"
OUT_ZOOM = HERE / "_core_hue_zoom.png"

LAYER_NAME = ("第1层 外焰", "第2层 中焰", "第3层 焰芯", "底火层")

# 上一版的"中性白"（R−G 只有 5、S 只有 12% —— 混进去把色阶色的暖意冲掉 2.5 倍）
OLD_TINT = (255, 250, 224)
OLD_KEEP_UP = 0.00

# 对照的两档：(标题, _CORE_TINT, _L3_KEEP_UP)。改后那一档直接读**当前代码值**，
# 所以探针永远对照"上一版 vs 现在的代码"，不会因为落地值变了而失真。
CASES = [
    ("改前（中性白）", OLD_TINT, OLD_KEEP_UP),
    ("改后（落地）", flame._CORE_TINT, flame._L3_KEEP_UP),
]


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = {}

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def _buf(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return bytes(ptr)


def mask_color(on, off):
    """帧差掩码 → (像素数, 中位 (r,g,b), H, S, V, R−B)。"""
    a, b = _buf(on), _buf(off)
    rs, gs, bs = [], [], []
    for i in range(0, len(a), 4):
        bb, gg, rr, aa = a[i], a[i + 1], a[i + 2], a[i + 3]
        if (abs(rr - b[i + 2]) + abs(gg - b[i + 1]) + abs(bb - b[i])) < 10:
            continue
        if aa < 250:
            continue
        rs.append(rr)
        gs.append(gg)
        bs.append(bb)
    n = len(rs)
    if not n:
        return (0, (0, 0, 0), 0.0, 0.0, 0.0, 0)
    rs.sort()
    gs.sort()
    bs.sort()
    med = (rs[n // 2], gs[n // 2], bs[n // 2])
    h, s, v = colorsys.rgb_to_hsv(med[0] / 255.0, med[1] / 255.0, med[2] / 255.0)
    return (n, med, h * 360.0, s * 100.0, v * 100.0, med[0] - med[2])


def hue_of(rgb):
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return h * 360.0, s * 100.0, v * 100.0


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._campfire = True
    dial._boot_done = True
    dial.show()
    dial._timer.stop()

    d = float(min(dial.width(), dial.height()))
    FULL = flame.LAYERS
    print("画布 %dx%d  d=%.0f" % (dial.width(), dial.height(), d))
    print("_CORE_MIX_MAX_K = %.2f（焰芯混白上限，_core_gain(1)=1 → 满热混这么多）"
          % flame._CORE_MIX_MAX_K)
    print()

    def frame(heat, upto=3, floor_on=True, sparks=True):
        """upto: 0 关主火层；N = 只画前 N 层。"""
        keep = (flame.LAYERS, flame.flame_floor_geom, flame.SparkField.at)
        flame.LAYERS = () if upto <= 0 else FULL[:upto]
        if not floor_on:
            flame.flame_floor_geom = lambda *a, **k: None
        if not sparks:
            flame.SparkField.at = lambda self, *a, **k: []
        try:
            dial._snap = {"heat": heat, "kpm": 0, "kpm_keys": 0, "kpm_mouse": 0,
                          "peak": 214.0, "state": "idle" if heat == 0 else "typing",
                          "idle_seconds": 1.0, "total_keys": 100}
            dial._phase = PHASE
            dial.update()
            pm = dial.grab()
        finally:
            flame.LAYERS, flame.flame_floor_geom, flame.SparkField.at = keep
        img = QImage(pm.size(), QImage.Format.Format_RGB32)
        img.fill(QColor(250, 250, 250))
        pp = QPainter(img)
        pp.drawPixmap(0, 0, pm)
        pp.end()
        return img

    def layers_of(heat):
        base = frame(heat, upto=0, floor_on=False, sparks=False)
        out = []
        prev = base
        for n in (1, 2, 3):
            cur = frame(heat, upto=n)
            out.append(mask_color(cur, prev))
            prev = cur
        out.append(mask_color(frame(heat, upto=3),
                              frame(heat, upto=3, floor_on=False)))
        return out

    def set_case(ci):
        _t, tint, ku = CASES[ci]
        flame._CORE_TINT = tint
        flame._L3_KEEP_UP = ku

    # ---- 0. 两档的"白"本身 ----
    print("=" * 86)
    print("0. 焰芯混白用的那个「白」本身")
    print("=" * 86)
    for tag, tint, ku in CASES:
        h, s, v = hue_of(tint)
        print("  %-14s tint rgb%-16s H %5.1f  S %5.1f  R−G %3d (%4.1f%% of R)"
              "   _L3_KEEP_UP %+.2f"
              % (tag, tint, h, s, tint[0] - tint[1],
                 (tint[0] - tint[1]) / tint[0] * 100.0, ku))
    print()

    # ---- A. 逐层色相：改前 vs 改后 ----
    print("=" * 86)
    print("A. 逐层色相（帧差掩码 + 逐通道中位）—— 被内层盖住/被柴堆挡住的都不算")
    print("=" * 86)
    print("  %-6s %-12s | %-28s | %-28s" % ("热度", "层", "改前", "改后"))
    print("  %-6s %-12s | %-28s | %-28s"
          % ("", "", "中位RGB      H    S    V  R−G", "中位RGB      H    S    V  R−G"))
    data = {}
    for ci, (tag, _t, _k) in enumerate(CASES):
        set_case(ci)
        for heat, hname in HEATS:
            data[(ci, heat)] = layers_of(heat)
    for heat, hname in HEATS:
        for li in range(4):
            if li == 3 and data[(0, heat)][3][0] == 0:
                continue
            cells = []
            for ci in (0, 1):
                _n, med, h, sat, v, rb = data[(ci, heat)][li]
                cells.append("rgb(%3d,%3d,%3d) %5.1f %5.1f %5.1f %4d"
                             % (med[0], med[1], med[2], h, sat, v, med[0] - med[1]))
            print("  %-6s %-12s | %s | %s" % (hname, LAYER_NAME[li],
                                              cells[0], cells[1]))
        print()

    print("=" * 86)
    print("A2. 焰芯的位置：R−G（暖意，抗「灰/绿」）与 V（亮度，撑「白」）")
    print("=" * 86)
    print("  %-6s  %-24s  %-24s" % ("热度", "改前 焰芯R−G / V", "改后 焰芯R−G / V"))
    for heat, hname in HEATS:
        seg = []
        for ci in (0, 1):
            _n, med, _h, _s, v, _rb = data[(ci, heat)][2]
            seg.append("%3d / %5.1f" % (med[0] - med[1], v))
        print("  %-6s  %-24s  %-24s" % (hname, seg[0], seg[1]))
    print()

    print("=" * 86)
    print("A3. 改后：焰芯在改前/改后 都还是三层里最亮的那层吗")
    print("=" * 86)
    for heat, hname in HEATS:
        seg = []
        for ci in (0, 1):
            st = data[(ci, heat)]
            who = LAYER_NAME[max(range(3), key=lambda i: st[i][4])]
            seg.append(who)
        same = "一致" if seg[0] == seg[1] else "**变了**"
        print("  %-6s  改前最亮 = %-12s  改后最亮 = %-12s  %s"
              % (hname, seg[0], seg[1], same))
    print()

    # ---- B. 渲图 ----
    tiles = {}
    for ci, (tag, _t, _k) in enumerate(CASES):
        set_case(ci)
        for heat, _h in HEATS:
            src = HERE / ("_ch_%d_%d.png" % (ci, int(heat)))
            frame(heat).save(str(src), "PNG")
            tiles[(ci, heat)] = Image.open(src).convert("RGB")
    flame._CORE_TINT = CASES[1][1]
    flame._L3_KEEP_UP = CASES[1][2]

    def nxt():
        compose(tiles, data)
        dial._quit()

    QTimer.singleShot(200, nxt)
    app.exec()
    print("DONE")
    return 0


def _font(size):
    try:
        from PIL import ImageFont
        return ImageFont.truetype(FONT, size)
    except Exception:
        return None


def compose(tiles, data):
    w0, h0 = tiles[(0, 100.0)].size
    crop = (int(w0 * 0.34), int(h0 * 0.20), int(w0 * 0.66), int(h0 * 0.62))
    scale, gap, pad, band = 5, 14, 16, 74
    tw = (crop[2] - crop[0]) * scale
    th = (crop[3] - crop[1]) * scale
    rows = [19.0, 50.0, 100.0]
    W = pad * 2 + 2 * (tw + gap) - gap
    H = 126 + pad + len(rows) * (th + band + gap) - gap + pad
    out = Image.new("RGB", (W, H), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    f1, f2, f3 = _font(21), _font(14), _font(13)
    dr.text((pad, 8), "焰芯（最前面那层）的「白」调暖 —— 左：改前　右：改后",
            fill=(28, 28, 38), font=f1)
    dr.text((pad, 38), "黑体色阶全程 H ≤ 47.2°、R > G > B，没有绿；"
                       "「绿」是一块低饱和灰米色被全饱和橙黄包围的同时对比。",
            fill=(105, 105, 118), font=f2)
    dr.text((pad, 60), "改前 = 中性白 (255,250,224)、顶端不提亮　→　"
                       "改后 = 暖白 (255,238,186) + _L3_KEEP_UP +0.24",
            fill=(105, 105, 118), font=f2)
    dr.text((pad, 84), "每格：焰芯中位 rgb / H / S / V / R−G。"
                       "R−G 越大越暖（抗「绿」），V 越高越亮（撑「白」）。",
            fill=(105, 105, 118), font=f2)
    for r, heat in enumerate(rows):
        for c in range(2):
            x = pad + c * (tw + gap)
            y = 126 + pad + r * (th + band + gap)
            out.paste(tiles[(c, heat)].crop(crop).resize((tw, th), Image.LANCZOS),
                      (x, y))
            dr.text((x + 2, y - 36), "%s   h%d" % (CASES[c][0], int(heat)),
                    fill=(40, 40, 50), font=f2)
            _n, med, h, sat, v, _rb = data[(c, heat)][2]
            dr.text((x + 2, y + th + 4),
                    "焰芯 rgb(%3d,%3d,%3d)  H %.1f  S %.1f  V %.1f"
                    % (med[0], med[1], med[2], h, sat, v),
                    fill=(40, 40, 50), font=f3)
            dr.text((x + 2, y + th + 20),
                    "R−G %3d（暖意）   R−B %3d   V %.1f（亮度）"
                    % (med[0] - med[1], med[0] - med[2], v),
                    fill=(170, 70, 40) if c else (120, 120, 132), font=f3)
    out.save(OUT)
    print("对照图 %s  %s" % (OUT.name, out.size))

    # 放大：h100 中心区
    zscale = 6
    cw2, ch2 = int(w0 * 0.40), int(h0 * 0.34)
    crop2 = (int(w0 * 0.5 - cw2 / 2), int(h0 * 0.30),
             int(w0 * 0.5 + cw2 / 2), int(h0 * 0.30 + ch2))
    tw2 = (crop2[2] - crop2[0]) * zscale
    th2 = (crop2[3] - crop2[1]) * zscale
    W2 = pad * 2 + tw2 * 2 + gap
    H2 = 56 + pad + th2 + 40 + pad
    out2 = Image.new("RGB", (W2, H2), (245, 245, 248))
    dr2 = ImageDraw.Draw(out2)
    dr2.text((pad, 8), "放大对照（6×）h100 焰芯", fill=(28, 28, 38), font=f1)
    dr2.text((pad, 34), "看中央那块曾经发灰的颜色 —— 改后应该读成「淡金」，"
                        "不再是「灰米」", fill=(105, 105, 118), font=f2)
    for c in range(2):
        x = pad + c * (tw2 + gap)
        y = 56 + pad
        out2.paste(tiles[(c, 100.0)].crop(crop2).resize((tw2, th2), Image.LANCZOS),
                   (x, y))
        _n, med, h, sat, v, _rb = data[(c, 100.0)][2]
        dr2.text((x + 2, y + th2 + 6),
                 "%s  焰芯 rgb(%d,%d,%d)  H %.1f  S %.1f  V %.1f  R−G %d"
                 % (CASES[c][0], med[0], med[1], med[2], h, sat, v,
                    med[0] - med[1]),
                 fill=(40, 40, 50), font=f3)
    out2.save(OUT_ZOOM)
    print("放大图 %s  %s" % (OUT_ZOOM.name, out2.size))


if __name__ == "__main__":
    raise SystemExit(main())
