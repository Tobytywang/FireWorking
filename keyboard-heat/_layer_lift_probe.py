"""第 1/2 层（外焰 / 中焰）单独提亮 —— 分层实测。

用户："亮度还是不太好, 我想让他更亮一些, 也许可以单独提升下前面的第一层和
第二层的亮度? 变得更加白,更加黄?"

这句话里有两件事是**没量过**的，先量：

A. **"第一层/第二层"到底是哪一层、各占多少像素**
   把 `flame.LAYERS` 依次截断（()→[:1]→[:2]→[:3]）渲同一帧，相邻两帧做差，
   差出来的就是第 N 层**真正露出来**的像素（被内层盖住的部分自动不算）。
   逐层量 lum 中位数和 **R−B**（饱和度判据 —— 加白会把它压低，加色温不会）。

B. **"更白更黄"有多大的余量**
   第 1/2 层各三个旋钮（_L1_HUE/_L1_LIFT/_L1_KEEP 与 _L2_*）：
       HUE  底端色沿黑体色阶再往上走  → 更黄、更白，R−B 保得住
       LIFT 底端再往 _CORE_TINT 混白 → 更白，R−B 掉
       KEEP 顶端保留比例抬高          → 尖也亮，整层读出来才亮
   三组候选一起渲（h0 / h19 / h50 / h100），跟现值逐像素对拍。

    .pyenv\\Scripts\\python.exe _layer_lift_probe.py
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
from PIL import Image, ImageDraw                   # noqa: E402

PHASE = 3.8
HEATS = [(0.0, "idle"), (19.0, "h19"), (50.0, "h50"), (100.0, "h100")]
OUT = HERE / "_layer_lift_probe.png"
OUT_MAP = HERE / "_layer_map.png"
FONT = "C:/Windows/Fonts/msyh.ttc"

# (标题, L12_HOT, L1_EDGE, L1_KEEP_UP, L2_HUE, L2_KEEP_UP)
VARIANTS = [
    ("(0) 现值", 0.60, 0.00, 0.00, 0.00, 0.00),
    ("(1) 温和", 0.60, 0.10, 0.12, 0.06, 0.04),
    ("(2) 本轮·落地", 0.60, 0.16, 0.20, 0.09, 0.08),
    ("(3) 更强", 0.60, 0.24, 0.28, 0.14, 0.12),
]

KNOBS = ("_L12_HOT", "_L1_EDGE", "_L1_KEEP_UP", "_L2_HUE", "_L2_KEEP_UP")
LAYER_NAME = ("第1层 外焰", "第2层 中焰", "第3层 焰芯", "底火层")


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


def _buf(img):
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return bytes(ptr)


def mask_stats(on, off):
    """帧差掩码 → (像素数, lum 中位, lum p90, R−B 中位, ≥200 占比)。"""
    a, b = _buf(on), _buf(off)
    lums, rbs = [], []
    for i in range(0, len(a), 4):
        bb, gg, rr, aa = a[i], a[i + 1], a[i + 2], a[i + 3]
        if (abs(rr - b[i + 2]) + abs(gg - b[i + 1]) + abs(bb - b[i])) < 10:
            continue
        if aa < 250:
            continue
        lums.append(0.299 * rr + 0.587 * gg + 0.114 * bb)
        rbs.append(rr - bb)
    if not lums:
        return (0, 0, 0, 0, 0.0)
    lums.sort()
    rbs.sort()
    n = len(lums)
    hot = sum(1 for v in lums if v >= 200) / float(n)
    return (n, int(lums[n // 2]), int(lums[int(n * 0.9)]),
            int(rbs[n // 2]), hot)


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
    FULL = flame.LAYERS
    front_top = flame.log_image_load(HERE / "assets" / "log-pile-front.png",
                                     slot="front").content_rect(cx, cy, d)[1]
    print("画布 %dx%d  d=%.0f   前景柴堆顶边 y=%.1f" % (dial.width(), dial.height(), d, front_top))
    print()

    def frame(heat, upto=3, floor_on=True, sparks=True):
        """upto: -1 关掉底火层；0 关主火层；N = 只画前 N 层。"""
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
        """逐层掩码：第 N 层 = A(N) 与 A(N-1) 的差。"""
        base = frame(heat, upto=0, floor_on=False, sparks=False)
        out = []
        prev = base
        for n in (1, 2, 3):
            cur = frame(heat, upto=n)
            out.append(mask_stats(cur, prev))
            prev = cur
        out.append(mask_stats(frame(heat, upto=3), frame(heat, upto=3, floor_on=False)))
        return out

    # ---- A. 现状逐层 ----
    print("=" * 78)
    print("A. 现状（旋钮全 0）逐层露出量 —— 数字是**帧差掩码**，被内层盖住的不算")
    print("=" * 78)
    print("  %-6s %-12s %6s %6s %6s %6s %7s" % ("热度", "层", "像素", "中位", "p90", "R−B", "≥200"))
    baseline = {}
    for heat, hname in HEATS:
        st = layers_of(heat)
        baseline[heat] = st
        for li, s in enumerate(st):
            n, med, p90, rb, hot = s
            print("  %-6s %-12s %6d %6d %6d %6d %6.0f%%"
                  % (hname, LAYER_NAME[li], n, med, p90, rb, hot * 100))
        print()

    # ---- B. 三类候选取样 ----
    print("=" * 78)
    print("B. 三类候选（每格 = L1 中位lum / L2 中位lum / L1 R−B / L2 R−B）")
    print("=" * 78)
    got = {}
    tiles = []
    for vi, v in enumerate(VARIANTS):
        patch(v)
        got[vi] = {}
        for heat, hname in HEATS:
            st = layers_of(heat)
            got[vi][heat] = st
            src = HERE / ("_ll_%d_%d.png" % (vi, int(heat)))
            frame(heat).save(str(src), "PNG")
            tiles.append((vi, heat, Image.open(src).convert("RGB")))
        base = got[0]
        line = []
        for heat, hname in HEATS:
            n1, m1, _p1, rb1, _h1 = got[vi][heat][0]
            n2, m2, _p2, rb2, _h2 = got[vi][heat][1]
            b1 = base[heat][0][1]
            b2 = base[heat][1][1]
            line.append("%s L1 %3d(%+d) RB%3d | L2 %3d(%+d) RB%3d | 层次差 %3d→%3d"
                        % (hname, m1, m1 - b1, rb1, m2, m2 - b2, rb2,
                           b2 - b1, m2 - m1))
        print("  %-10s" % v[0])
        for s in line:
            print("      " + s)
        print()

    # ---- C. 满热对拍 ----
    print("=" * 78)
    print("C. h100 对拍（守不守得住已验收的旺火形态）")
    print("=" * 78)
    ref = None
    for vi, v in enumerate(VARIANTS):
        patch(v)
        dst = HERE / ("_ll100_%d.png" % vi)
        frame(100.0).save(str(dst), "PNG")
        b = dst.read_bytes()
        if ref is None:
            ref = b
            print("  %-10s 基准" % v[0])
            continue
        diff = 0 if b == ref else sum(1 for x, y in zip(ref, b) if x != y)
        print("  %-10s 与基准不同字节 %d%s" % (v[0], diff, "" if diff else "   ✓ 逐像素不变"))
    patch(VARIANTS[0])
    print()

    def nxt():
        compose(tiles, got)
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


def compose(tiles, got):
    scale, gap, pad, hdr, top = 3, 12, 16, 96, 118
    cols, rows = len(VARIANTS), len(HEATS)
    w0, h0 = tiles[0][2].size
    crop = (int(w0 * 0.30), int(h0 * 0.20), int(w0 * 0.70), int(h0 * 0.64))
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    tw, th = cw * scale, ch * scale
    W = pad * 2 + cols * (tw + gap) - gap
    H = hdr + pad + rows * (th + gap + top) - gap + pad
    out = Image.new("RGB", (W, H), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    f1, f2, f3 = _font(20), _font(16), _font(13)
    dr.text((pad, 8), "第 1/2 层（外焰 / 中焰）单独提亮 —— 同一摇曳相位，合成在白桌面上",
            fill=(28, 28, 38), font=f1)
    dr.text((pad, 36), "每格数字：第1层 中位lum(Δ) R−B ｜ 第2层 中位lum(Δ) R−B　"
                       "Δ 是相对现值的增量；R−B 是饱和度（加白会掉，加色温不掉）",
            fill=(105, 105, 118), font=f2)
    dr.text((pad, 60), "行 = 热度档，列 = 候选档；第 3 层（焰芯）本轮不动",
            fill=(105, 105, 118), font=f2)
    by = {(vi, heat): im for vi, heat, im in tiles}
    base = got[0]
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            x = pad + c * (tw + gap)
            y = hdr + pad + r * (th + gap + top)
            out.paste(by[(c, heat)].crop(crop).resize((tw, th), Image.LANCZOS),
                      (x, y))
            dr.text((x + 2, y - 26), "%s   %s" % (VARIANTS[c][0], hname),
                    fill=(40, 40, 50), font=f2)
            for li in (0, 1):
                n, med, p90, rb, hot = got[c][heat][li]
                bm = base[heat][li][1]
                brb = base[heat][li][3]
                col = (196, 62, 40) if med > base[heat][li][1] else (70, 70, 84)
                dr.text((x + 2, y + th + 4 + li * 34),
                        "%s 中位 %3d (%+d)  R−B %3d (%+d)"
                        % (LAYER_NAME[li][:3], med, med - bm, rb, rb - brb),
                        fill=col, font=f3)
                dr.text((x + 2, y + th + 19 + li * 34),
                        "     像素 %4d   p90 %3d   ≥200 %2.0f%%" % (n, p90, hot * 100),
                        fill=(120, 120, 132), font=f3)
    out.save(OUT)
    print("对照图 %s  %s" % (OUT.name, out.size))
    hero(tiles, got)


def hero(tiles, got):
    """放大对照：h50 / h100 的现值 vs 落地值 —— 判断"够不够亮"看这张最直接。"""
    by = {(vi, heat): im for vi, heat, im in tiles}
    w0, h0 = by[(0, 100.0)].size
    crop = (int(w0 * 0.34), int(h0 * 0.22), int(w0 * 0.66), int(h0 * 0.62))
    scale = 5
    tw = (crop[2] - crop[0]) * scale
    th = (crop[3] - crop[1]) * scale
    pad, gap, band = 16, 14, 30
    rows = [50.0, 100.0]
    W = pad * 2 + tw * 2 + gap
    H = 48 + pad + len(rows) * (th + band + gap) - gap + pad
    out = Image.new("RGB", (W, H), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    f1, f2 = _font(20), _font(13)
    dr.text((pad, 8), "放大对照（5×）　左：现值　右：本轮落地",
            fill=(28, 28, 38), font=f1)
    for r, heat in enumerate(rows):
        y = 48 + pad + r * (th + band + gap)
        for c, vi in enumerate((0, 2)):
            x = pad + c * (tw + gap)
            out.paste(by[(vi, heat)].crop(crop).resize((tw, th), Image.LANCZOS),
                      (x, y))
            _n, med, _p, rb, _hot = got[vi][heat][0]
            dr.text((x + 2, y + th + 6),
                    "%s  h%d   lum %d   R−B %d"
                    % (VARIANTS[vi][0], int(heat), med, rb),
                    fill=(40, 40, 50), font=f2)
    path = HERE / "_layer_lift_zoom.png"
    out.save(path)
    print("放大图 %s  %s" % (path.name, out.size))


if __name__ == "__main__":
    raise SystemExit(main())
