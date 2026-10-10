"""空闲火苗亮度**档位扫描** —— 一屏放三档，挑完再回填 flame.py 的常量。

用户上一轮说"还是可以再亮一些"。空闲亮度由三个旋钮共同决定，它们都只在冷端
生效（中热以上几乎不动、满热逐像素不变）：

    _IDLE_RAMP_POS        空闲时色阶位置抬到哪（底色多亮）
    _COLD_SHADE_MIN_K     纵向渐变保留多少压暗量（火团上下多均匀）
    _EDGE_MIX_COLD_RELIEF 外焰冷态比满热再轻多少压暗（边缘多亮）

三档：(1) 上轮验收版 → (2) 候选 A → (3) 候选 B。两行：idle 是主角，h05 是旁证
（空闲调亮不该把低热档顶掉）。每格底下打一行像素统计 —— 数字比眼睛准。

    .pyenv\\Scripts\\python.exe _idle_levels.py

选完把 (2) 或 (3) 那三个数写回 flame.py 的常量，再跑 _test_flame.py。
走离屏渲染（QWidget.grab），不抓屏。
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

PHASE = 3.8                                        # 固定摇曳相位，各档才可比
# idle 是主角；h05 是低热旁证；h50 是**对照** —— 用来说明"空闲提亮"没有把
# 中热档一起抬上去（那一行的两组数字应该几乎一样）。
HEATS = [(0.0, "idle"), (5.0, "h05"), (50.0, "h50")]
OUT = HERE / "_idle_levels.png"
FONT = "C:/Windows/Fonts/msyh.ttc"

# (标题, _IDLE_RAMP_POS, _IDLE_RAMP_FALLOFF, _COLD_SHADE_MIN_K, _EDGE_MIX_COLD_RELIEF)
VARIANTS = [
    ("(1) 上轮验收 0.28/指数3/0.40/无", 0.28, 3.0, 0.40, 0.00),
    ("(2) 本轮 0.52/指数3/0.26/0.28", 0.52, 3.0, 0.26, 0.28),
]

# 火焰可见区（idle 火尖 y≈95、前景柴堆顶边 y≈115）——只统计这一段，避开柴堆的橙像素
BOX = (60, 90, 132, 115)


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = {}

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def patch(ramp, falloff, shade, relief):
    """三个旋钮 + 衰减指数都是模块级常量，绘制函数每次现读 → patch 有效。"""
    flame._IDLE_RAMP_POS = ramp
    flame._IDLE_RAMP_FALLOFF = falloff
    flame._COLD_SHADE_MIN_K = shade
    flame._EDGE_MIX_COLD_RELIEF = relief


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._campfire = True
    dial._boot_done = True
    dial.show()
    dial._timer.stop()                             # 冻结时间 → 相位可控

    tiles, stats, colors = [], [], []

    def shoot(vi, heat):
        _t, ramp, falloff, shade, relief = VARIANTS[vi]
        patch(ramp, falloff, shade, relief)
        colors.append((vi, heat, flame.flame_colors(heat / 100.0),
                       flame.flame_shade_k(heat / 100.0)))
        dial._snap = {"heat": heat, "kpm": 0, "kpm_keys": 0, "kpm_mouse": 0,
                      "peak": 214.0, "state": "idle" if heat == 0 else "typing",
                      "idle_seconds": 1.0, "total_keys": 100}
        dial._phase = PHASE
        dial.update()
        pm = dial.grab()
        img = QImage(pm.size(), QImage.Format.Format_RGB32)
        img.fill(QColor(64, 64, 68))
        pp = QPainter(img)
        pp.drawPixmap(0, 0, pm)
        pp.end()
        dst = HERE / ("_il_%d_%d.png" % (vi, int(heat)))
        img.save(str(dst), "PNG")
        im = Image.open(dst).convert("RGB")
        tiles.append((vi, heat, im))
        stats.append((vi, heat, sample(im)))

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


def sample(im):
    """火焰可见区的像素统计：达标像素数 + 亮度和的中位/最高。"""
    x0, y0, x1, y1 = BOX
    s = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = im.getpixel((x, y))
            if r > 35 and r > g + 12 and r > b + 12:
                s.append(r + g + b)
    if not s:
        return 0, 0, 0
    s.sort()
    return len(s), s[len(s) // 2], s[-1]


def compose(tiles, stats, colors):
    scale, gap, pad, top = 3, 10, 14, 34
    cols, rows = len(VARIANTS), len(HEATS)
    tw = tiles[0][2].width * scale
    th = tiles[0][2].height * scale
    W = pad + cols * (tw + gap) - gap + pad
    H = pad + rows * (th + gap + top) - gap + pad
    out = Image.new("RGB", (W, H), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(FONT, 18)
        f2 = ImageFont.truetype(FONT, 15)
    except Exception:
        f = f2 = None
    by = {(vi, heat): im for vi, heat, im in tiles}
    st = {(vi, heat): v for vi, heat, v in stats}
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            x = pad + c * (tw + gap)
            y = pad + r * (th + gap + top)
            out.paste(by[(c, heat)].resize((tw, th), Image.LANCZOS), (x, y))
            dr.text((x + 2, y - 26), "%s   %s" % (VARIANTS[c][0], hname),
                    fill=(40, 40, 48), font=f)
            n, med, mx = st[(c, heat)]
            dr.text((x + 2, y + th + 4),
                    "火焰可见像素 %d   亮度和 中位 %d / 最高 %d" % (n, med, mx),
                    fill=(90, 90, 100), font=f2)
    out.save(OUT)
    print("档位图 %s  %s" % (OUT.name, out.size))
    print()
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            n, med, mx = st[(c, heat)]
            print("  %-5s %-36s 像素 %4d  中位 %3d  最高 %3d"
                  % (hname, VARIANTS[c][0], n, med, mx))
    print()
    print("  配色（外焰/中焰/焰芯）与渐变压暗折扣：")
    for vi, heat, (o, m, c), sk in colors:
        if heat != 0.0:
            continue
        print("    %-36s outer %-14s mid %-14s core %-14s shade_k %.2f"
              % (VARIANTS[vi][0], str(o), str(m), str(c), sk))


if __name__ == "__main__":
    raise SystemExit(main())
