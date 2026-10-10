"""火焰**本体亮度**扫描 —— 用户说"亮度还是不行，要加强火的亮度"。

前四轮都在调"看得见的那团火有多亮"，但没量过两件事，这次先量：

1. **可见区间**：前景柴堆顶边（y=115）把火焰下半段挡住，空闲时主火只剩
   渐变的 0.11~1.0 段露在外面。而渐变在 0.55 处就换成**最暗的尖端色**并一路
   保持 —— 可见区有近一半吃的是最暗那档。这不是配色问题，是渐变的转折点钉死了。
2. **色阶上限**：0.52 → (189,86,0) lum 107，而 0.75 → (219,157,15) lum 159。
   "亮"在色阶上是有的，只是冷端没走到那儿。

于是四个旋钮，全部只作用在冷端、满热逐像素不变：

    _IDLE_RAMP_POS / _IDLE_RAMP_FALLOFF   空闲色阶位置抬多高（**必须单调**：nK ≤ 1）
    _COLD_SHADE_MIN_K                     纵向渐变残留多少压暗量
    _EDGE_MIX_COLD_RELIEF                 外焰冷态再轻多少压暗
    _GRAD_TIP_COLD_RELIEF                 渐变转折点冷态往上推多少
    _CORE_HUE_BUMP                        焰芯沿色阶再往上走多少（提亮不掉饱和）

像素统计用**帧差**取火焰掩码：同一帧渲染两次，第二次关掉主火层和底火层，
两帧不同的像素就是"火焰真正贡献的像素"（被前景柴堆盖住的那些在两帧里一样，
自然被排除 —— 所以统计的就是**露出来的那部分**）。

    .pyenv\\Scripts\\python.exe _flame_lum_probe.py

底下的"h100 一致性"每档都会跟基准逐像素对拍，必须为 0。
"""
from __future__ import annotations

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
from PIL import Image, ImageDraw                    # noqa: E402

PHASE = 3.8
HEATS = [(0.0, "idle"), (19.0, "h19"), (50.0, "h50")]
OUT = HERE / "_flame_lum_probe.png"
FONT = "C:/Windows/Fonts/msyh.ttc"

# (标题, ramp_pos, falloff, shade_k, relief, tip_relief, core_bump)
VARIANTS = [
    ("(1) 上一版", 0.52, 3.00, 0.26, 0.28, 0.00, 0.00),
    ("(2) 候选·温和", 0.68, 1.40, 0.16, 0.38, 0.28, 0.16),
    ("(3) 本轮·现值", 0.74, 1.28, 0.13, 0.41, 0.32, 0.18),
    ("(4) 候选·激进", 0.80, 1.20, 0.10, 0.44, 0.36, 0.20),
]

KNOBS = ("_IDLE_RAMP_POS", "_IDLE_RAMP_FALLOFF", "_COLD_SHADE_MIN_K",
         "_EDGE_MIX_COLD_RELIEF", "_GRAD_TIP_COLD_RELIEF", "_CORE_HUE_BUMP")


def patch(v):
    for name, val in zip(KNOBS, v[1:]):
        setattr(flame, name, val)


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = {}

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def monotonic_report(v):
    """t 从 0 扫到 1，看色阶位置有没有回落（回落 = "打几个字火反而变暗"）。"""
    patch(v)
    prev_p = prev_l = None
    worst = 0.0
    for i in range(0, 201):
        t = i / 200.0
        p = flame._ramp_pos(t)
        c = flame._ramp(p)
        if prev_p is not None and p < prev_p - 1e-9:
            worst = max(worst, (prev_l - lum(c)) / max(1.0, prev_l))
        prev_p, prev_l = p, lum(c)
    return worst * 100.0


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._campfire = True
    dial._boot_done = True
    dial.show()
    dial._timer.stop()

    d = float(min(dial.width(), dial.height()))
    cx, cy = dial.width() / 2.0, dial.height() / 2.0
    front_top = flame.log_image_load(HERE / "assets" / "log-pile-front.png",
                                     slot="front").content_rect(cx, cy, d)[1]
    print("画布 %dx%d  d=%.0f   前景柴堆顶边 y=%.1f" % (dial.width(), dial.height(), d, front_top))
    print()

    tiles, stats, colors = [], [], []

    def frame(heat, flame_on):
        """渲一帧。flame_on=False 时关掉主火层 + 底火层 + 火星，用来做帧差掩码。"""
        keep = (flame.LAYERS, flame.flame_floor_geom, flame.SparkField.at)
        if not flame_on:
            flame.LAYERS = ()
            flame.flame_floor_geom = lambda *a, **k: None
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
        # 合成到**浅色桌面**上：实测用户桌面右下角是白的 (255,255,255)，灶膛
        # alpha 232 会透上来 9% —— 换成深灰底会比用户实际看到的更暗，判断会偏。
        img.fill(QColor(250, 250, 250))
        pp = QPainter(img)
        pp.drawPixmap(0, 0, pm)
        pp.end()
        return img

    # ---- 满热不变量：四个旋钮在 t=1 都必须恒等，h100 逐像素不变 ----
    # 比 PNG 字节：同一套像素编码结果逐字节相同，等价于逐像素对拍（且不碰 sip 指针）
    base = None
    for vi in range(len(VARIANTS)):
        patch(VARIANTS[vi])
        dst = HERE / ("_flh100_%d.png" % vi)
        frame(100.0, True).save(str(dst), "PNG")
        b = dst.read_bytes()
        if base is None:
            base = b
        diff = 0 if b == base else sum(1 for x, y in zip(base, b) if x != y)
        print("  h100 对拍 %-10s 与基准不同字节 %d%s"
              % (VARIANTS[vi][0], diff, "" if diff else "   ✓ 逐像素不变"))
    print()

    def shoot(vi, heat):
        patch(VARIANTS[vi])
        on, off = frame(heat, True), frame(heat, False)
        colors.append((vi, heat, flame.flame_colors(heat / 100.0),
                       flame.flame_shade_k(heat / 100.0),
                       flame._edge_mix_k(heat / 100.0),
                       flame._grad_tip_stop(heat / 100.0)))
        src = HERE / ("_fl_%d_%d.png" % (vi, int(heat)))
        on.save(str(src), "PNG")
        tiles.append((vi, heat, Image.open(src).convert("RGB")))
        stats.append((vi, heat, sample(on, off)))

    seq = [(vi, h) for vi in range(len(VARIANTS)) for h, _ in HEATS]

    def nxt():
        if not seq:
            compose(tiles, stats, colors)
            dial._quit()
            return
        vi, heat = seq.pop(0)
        shoot(vi, heat)
        QTimer.singleShot(120, nxt)

    QTimer.singleShot(600, nxt)
    app.exec()
    print("DONE")
    return 0


def sample(on, off):
    """帧差取火焰掩码 → 露出来的那部分火焰的亮度统计。"""
    w, h = on.width(), on.height()
    lums, bright150, bright190 = [], 0, 0
    for y in range(h):
        for x in range(w):
            a = on.pixelColor(x, y)
            b = off.pixelColor(x, y)
            if (abs(a.red() - b.red()) + abs(a.green() - b.green())
                    + abs(a.blue() - b.blue())) < 10:
                continue
            if a.alpha() < 250:
                continue
            L = lum((a.red(), a.green(), a.blue()))
            lums.append(L)
            if L >= 150:
                bright150 += 1
            if L >= 190:
                bright190 += 1
    if not lums:
        return 0, 0, 0, 0, 0, 0
    lums.sort()
    return (len(lums), lums[len(lums) // 2], lums[int(len(lums) * 0.9)],
            lums[-1], bright150, bright190)


def compose(tiles, stats, colors):
    scale, gap, pad, top, hdr = 3, 10, 14, 84, 72
    cols, rows = len(VARIANTS), len(HEATS)
    w0, h0 = tiles[0][2].size
    crop = (int(w0 * 0.32), int(h0 * 0.20), int(w0 * 0.68), int(h0 * 0.62))
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    tw, th = cw * scale, ch * scale
    W = pad + cols * (tw + gap) - gap + pad
    H = hdr + pad + rows * (th + gap + top) - gap + pad
    out = Image.new("RGB", (W, H), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(FONT, 17)
        f2 = ImageFont.truetype(FONT, 15)
        f3 = ImageFont.truetype(FONT, 19)
    except Exception:
        f = f2 = f3 = None
    dr.text((pad, 6), "火焰亮度对照 —— 同一摇曳相位，合成在你那块白桌面上",
            fill=(30, 30, 40), font=f3)
    dr.text((pad, 31), "数字 = 露出来的火焰像素（帧差取的掩码，被柴堆盖住的不算）",
            fill=(110, 110, 122), font=f2)
    by = {(vi, heat): im for vi, heat, im in tiles}
    st = {(vi, heat): v for vi, heat, v in stats}
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            x = pad + c * (tw + gap)
            y = hdr + pad + r * (th + gap + top)
            im = by[(c, heat)].crop(crop).resize((tw, th), Image.LANCZOS)
            out.paste(im, (x, y))
            dr.text((x + 2, y - 27), "%s   %s" % (VARIANTS[c][0], hname),
                    fill=(40, 40, 48), font=f)
            n, med, p90, mx, b150, b190 = st[(c, heat)]
            dr.text((x + 2, y + th + 4), "像素 %d   中位 %d" % (n, med),
                    fill=(80, 80, 92), font=f2)
            dr.text((x + 2, y + th + 23), "p90 %d   最高 %d" % (p90, mx),
                    fill=(80, 80, 92), font=f2)
            dr.text((x + 2, y + th + 42), "≥150 %d   ≥190 %d" % (b150, b190),
                    fill=(80, 80, 92), font=f2)
    out.save(OUT)
    hero(tiles)
    print("对照图 %s  %s" % (OUT.name, out.size))
    print()
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            n, med, p90, mx, b150, b190 = st[(c, heat)]
            print("  %-5s %-10s 像素 %4d  中位 %3d  p90 %3d  最高 %3d  ≥150 %3d  ≥190 %3d"
                  % (hname, VARIANTS[c][0], n, med, p90, mx, b150, b190))
        print()
    print("  单调性（t=0→1 扫描，色阶位置回落导致的最大亮度跌幅；0 = 完全单调）")
    for vi, v in enumerate(VARIANTS):
        print("    %-10s 跌幅 %5.1f%%" % (v[0], monotonic_report(v)))
    print()
    print("  idle 各层渐变根/尖（真正露出来的那段）")
    for vi, heat, (o, m, c), sk, ek, ts in colors:
        if heat != 0.0:
            continue
        print("    %-10s 转折点 %.2f  外焰压暗 %.2f" % (VARIANTS[vi][0], ts, ek))
        for name, bot, top in (("外焰", flame._lift(o, 0.06), flame._soft_shade(o, 0.48, sk)),
                               ("中焰", flame._lift(c, 0.02), flame._soft_shade(m, 0.70, sk)),
                               ("焰芯", flame._lift(c, 0.62 * flame.flame_core_lift_k(0.0)),
                                flame._soft_shade(c, 0.52, sk))):
            print("        %s 根 %-16s lum %5.1f | 尖 %-16s lum %5.1f"
                  % (name, str(bot), lum(bot), str(top), lum(top)))


def hero(tiles):
    """只放大 idle，上一版 vs 现值并排 —— 判断"够不够亮"看这张最直接。"""
    pair = [(0, "(1) 上一版（色阶 0.52）"), (2, "(3) 本轮现值（色阶 0.74）")]
    by = {(vi, heat): im for vi, heat, im in tiles}
    w0, h0 = by[(0, 0.0)].size
    crop = (int(w0 * 0.36), int(h0 * 0.34), int(w0 * 0.66), int(h0 * 0.66))
    scale = 6
    tw = (crop[2] - crop[0]) * scale
    th = (crop[3] - crop[1]) * scale
    pad, gap = 16, 16
    out = Image.new("RGB", (pad * 2 + tw * 2 + gap, pad * 2 + th + 52),
                    (245, 245, 248))
    dr = ImageDraw.Draw(out)
    try:
        from PIL import ImageFont
        f3 = ImageFont.truetype(FONT, 19)
        f2 = ImageFont.truetype(FONT, 15)
    except Exception:
        f3 = f2 = None
    dr.text((pad, 8), "空闲态（idle）火焰 · 6 倍放大 —— 同一相位、同一桌面底",
            fill=(30, 30, 40), font=f3)
    for i, (vi, label) in enumerate(pair):
        x = pad + i * (tw + gap)
        out.paste(by[(vi, 0.0)].crop(crop).resize((tw, th), Image.LANCZOS),
                  (x, 40))
        dr.text((x, 40 + th + 4), label, fill=(40, 40, 48), font=f2)
    path = HERE / "_flame_lum_zoom.png"
    out.save(path)
    print()
    print("英雄图 %s  %s" % (path.name, out.size))


if __name__ == "__main__":
    raise SystemExit(main())
