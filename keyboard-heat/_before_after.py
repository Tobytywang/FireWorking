"""改前 / 改后对照图 —— 把"篝火变小"和"空闲火苗变大"两件事拆开看。

三块面板，同一台表盘、同一帧相位、同一热度，只动一个变量：

  ① 旧素材 + 旧参数   篝火2 / 低矮篝火，槽位 0.62 / 0.48，FLAME_IDLE_K = 0.09
  ② 新素材 + 旧参数   篝火3 / 篝火3_低矮，槽位与空闲比例照旧
  ③ 新素材 + 新参数   篝火3 / 篝火3_低矮，槽位 0.53 / 0.41，FLAME_IDLE_K = 0.16

② 是中间态：素材换了但参数没换 —— 用来确认③的变化确实来自参数，而不是"新素材本来
就不一样"。两行分别是空闲（idle）和 5% 热度（h05），后者用来确认"空闲变大"没有把
低热档挤掉。

    .pyenv\\Scripts\\python.exe _before_after.py

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

PHASE = 3.8                                        # 固定摇曳相位，三次渲染才可比
HEATS = [(0.0, "idle"), (5.0, "h05")]
OUT = HERE / "_before_after.png"
FONT = "C:/Windows/Fonts/msyh.ttc"

# (标题, 后景图, 前景图, 后景槽位, 前景槽位, 空闲比例)
VARIANTS = [
    ("(1) 旧素材 + 旧参数", "log-pile", "log-pile-front",
     (0.62, 0.030), (0.48, 0.045), 0.09),
    ("(2) 新素材 + 旧参数", "log-pile", "log-pile-front",
     (0.62, 0.030), (0.48, 0.045), 0.09),
    ("(3) 新素材 + 新参数", "log-pile", "log-pile-front",
     (0.53, 0.030), (0.41, 0.045), 0.16),
]
# (1) 用备份的旧素材；后两行用当前 assets/
ASSETS = [("_bak_log-pile.png", "_bak_log-pile-front.png"),
          ("assets/log-pile.png", "assets/log-pile-front.png"),
          ("assets/log-pile.png", "assets/log-pile-front.png")]


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = {}

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def load_li(path, slot):
    li = flame.log_image_load(str(HERE / path), slot="back")
    if li is None:
        return None
    li.slot = flame.ImageSlot(slot[0], slot[1], 0.0, 0.0)
    return li


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._campfire = True
    dial._boot_done = True
    dial.show()
    dial._timer.stop()                             # 冻结时间 → 相位可控

    tiles = []
    jobs = [(vi, h) for vi in range(len(VARIANTS)) for h, _ in HEATS]

    def shoot(vi, heat):
        title, _b, _f, bs, fs, idle_k = VARIANTS[vi]
        back_src, front_src = ASSETS[vi]
        dial._log_image_obj = load_li(back_src, bs)
        dial._log_image_front_obj = load_li(front_src, fs)
        flame.FLAME_IDLE_K = idle_k             # flame_height 每次调用现读全局
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
        img.save(str(HERE / ("_ba_%d_%d.png" % (vi, int(heat)))), "PNG")
        tiles.append((vi, heat, Image.open(
            HERE / ("_ba_%d_%d.png" % (vi, int(heat)))).convert("RGB")))

    seq = list(jobs)

    def nxt():
        if not seq:
            compose(tiles)
            dial._quit()
            return
        vi, heat = seq.pop(0)
        shoot(vi, heat)
        QTimer.singleShot(120, nxt)

    QTimer.singleShot(600, nxt)
    app.exec()
    print("DONE")
    return 0


def compose(tiles):
    scale, gap, pad, top = 2, 10, 14, 34
    cols = len(VARIANTS)
    rows = len(HEATS)
    tw = tiles[0][2].width * scale
    th = tiles[0][2].height * scale
    W = pad + cols * (tw + gap) - gap + pad
    H = pad + rows * (th + gap + top) - gap + pad
    out = Image.new("RGB", (W, H), (245, 245, 248))
    dr = ImageDraw.Draw(out)
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(FONT, 18)
    except Exception:
        f = None
    by_heat = {}
    for vi, heat, im in tiles:
        by_heat[(vi, heat)] = im
    for r, (heat, hname) in enumerate(HEATS):
        for c in range(cols):
            x = pad + c * (tw + gap)
            y = pad + r * (th + gap + top)
            im = by_heat[(c, heat)].resize((tw, th), Image.LANCZOS)
            out.paste(im, (x, y))
            label = "%s   %s" % (VARIANTS[c][0], hname)
            dr.text((x + 2, y - 26), label, fill=(40, 40, 48), font=f)
    out.save(OUT)
    print("对照图 %s  %s" % (OUT.name, out.size))


if __name__ == "__main__":
    raise SystemExit(main())
