"""改前 / 改后对照图 —— 只动"空闲火苗亮不亮"，素材和槽位一律不动。

用户的原话是"初始状态的火苗……完全是一团漆黑"。这一轮只改了三个数：
色阶起点 `_IDLE_RAMP_POS`、渐变压暗折扣 `flame_shade_k`、空闲高度 `FLAME_IDLE_K`。
所以对照图只做一个变量轴：

  (1) 改前   _IDLE_RAMP_POS = 0（色阶恒等）、shade 折扣恒 1、FLAME_IDLE_K = 0.16
  (2) 改后   _IDLE_RAMP_POS = 0.28、冷态 shade 折扣 0.40、FLAME_IDLE_K = 0.19

两行：空闲（idle）是主角；5% 热度（h05）是旁证 —— 空闲调亮不该把低热档顶掉。
下面还会打一行像素统计（火焰可见区的中位/最高亮度和），数字比眼睛准。

    .pyenv\\Scripts\\python.exe _idle_bright.py

走离屏渲染（QWidget.grab），不抓屏 —— 探针窗口和真机实例都在右下角同一位置。
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

PHASE = 3.8                                        # 固定摇曳相位，两次渲染才可比
HEATS = [(0.0, "idle"), (5.0, "h05")]
OUT = HERE / "_idle_bright.png"
FONT = "C:/Windows/Fonts/msyh.ttc"

# (标题, FLAME_IDLE_K, _IDLE_RAMP_POS(None=恒等), 冷态 shade 折扣下限(None=不压暗))
VARIANTS = [
    ("(1) 改前：色阶恒等 + 空闲 0.16", 0.16, None, None),
    ("(2) 改后：色阶抬到 0.28 + 空闲 0.19", 0.19, 0.28, 0.40),
]

# 火焰可见区（idle 时火尖 y≈95、前景柴堆顶边 y≈115）——只统计这一段，避开柴堆
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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._campfire = True
    dial._boot_done = True
    dial.show()
    dial._timer.stop()                             # 冻结时间 → 相位可控

    tiles, stats = [], []

    def patch(idle_k, ramp, shade):
        flame.FLAME_IDLE_K = idle_k              # flame_height 每次调用现读全局
        if ramp is None:
            flame._ramp_pos = lambda t: max(0.0, min(1.0, float(t)))
        else:
            flame._ramp_pos = (lambda t, h=ramp:
                               max(0.0, min(1.0, float(t)))
                               + h * (1.0 - max(0.0, min(1.0, float(t)))) ** 3)
        if shade is None:
            flame.flame_shade_k = lambda heat: 1.0
        else:
            flame.flame_shade_k = (lambda heat, m=shade:
                                   1.0 - (1.0 - m)
                                   * (1.0 - max(0.0, min(1.0, float(heat)))) ** 3)

    def shoot(vi, heat):
        title, idle_k, ramp, shade = VARIANTS[vi]
        patch(idle_k, ramp, shade)
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
        dst = HERE / ("_ib_%d_%d.png" % (vi, int(heat)))
        img.save(str(dst), "PNG")
        im = Image.open(dst).convert("RGB")
        tiles.append((vi, heat, im))
        stats.append((vi, heat, sample(im)))

    seq = [(vi, h) for vi in range(len(VARIANTS)) for h, _ in HEATS]

    def nxt():
        if not seq:
            compose(tiles, stats)
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


def compose(tiles, stats):
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
    print("对照图 %s  %s" % (OUT.name, out.size))
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            n, med, mx = st[(c, heat)]
            print("  %-8s %-30s 像素 %4d  中位 %3d  最高 %3d"
                  % (hname, VARIANTS[c][0], n, med, mx))


if __name__ == "__main__":
    raise SystemExit(main())
