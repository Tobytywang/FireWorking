"""灶膛（pit）不透明度对照 —— 在**真实桌面**上合成，看火到底要多少暗底才不灰。

起因：用户反馈「还是不太亮，灰蒙蒙的，是不是加遮罩了」。逐像素对拍（_screen_probe.py）
证明屏幕像素 == 绘制像素（98.8% 一致、平均差 0.27），合成层没有任何遮罩。
真正的机制是**反过来的**：

    bg_alpha = 0.0  → 底盘 plate 全透明
    CAMP_PIT_MIN_ALPHA = 96  → 灶膛只剩 38% 不透明
    白色桌面 0.62 × 255 = 158 透上来 → 灶膛 rgb(14,12,17) 被冲成 rgb(164,163,165) 的中灰

火焰 rgb(189,86,0) 压在这块灰底上，对比度不足 → 「发闷、不亮」。
而光晕是**加法混合**，叠在亮底上只会更白，等于白画。

这个脚本把窗口离屏渲染后合成到**抓下来的真实桌面**上，扫描灶膛不透明度，
输出横向对照图 + 每档的火焰区像素统计。只读，不改项目代码。
"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

try:
    from PIL import Image, ImageDraw, ImageFont, ImageGrab
except ImportError as exc:                                   # pragma: no cover
    print("SKIP 需要 PIL：%s" % exc)
    raise SystemExit(2)

from PyQt6.QtGui import QImage                               # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

import overlay                                               # noqa: E402
from heatcore import load_config                             # noqa: E402
from overlay import HeatDial                                 # noqa: E402

SCENE = {"heat": 0.0, "kpm": 0, "kpm_keys": 0, "kpm_mouse": 0,
         "peak": 214.0, "state": "idle", "idle_seconds": 1.0, "total_keys": 100}

# 灶膛不透明度扫描。96 = 当前值；往上加 = 给火一块更黑的底。
PIT_ALPHAS = (96, 150, 200, 232, 255)
BG_ALPHA_K = 0.0            # 底盘保持用户当前的设定（全透明），只动灶膛

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"


class FakeService:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = dict(SCENE)

    def snapshot(self):
        return dict(self.snap)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


def sat(c):
    mx, mn = max(c[:3]), min(c[:3])
    return 0.0 if mx == 0 else (mx - mn) / float(mx) * 100.0


def med(img, box):
    px = list(img.crop(box).convert("RGB").getdata())
    if not px:
        return (0, 0, 0)
    px.sort(key=lambda p: p[0] + p[1] + p[2])
    return px[len(px) // 2]


def grab_offscreen(dial, path):
    pm = dial.grab()
    qimg = pm.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    qimg.save(str(path), "PNG")
    return Image.open(path).convert("RGBA")


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    dial = HeatDial(FakeService())
    dial._boot_done = True
    dial._snap = dict(SCENE)
    dial._timer.stop()
    dial._phase = 0.0
    dial.show()
    dial.update()
    for _ in range(8):
        app.processEvents()
        time.sleep(0.04)
    x, y, w, h = dial.x(), dial.y(), dial.width(), dial.height()
    dial.hide()
    for _ in range(12):                 # 等窗口真的从屏幕上消失
        app.processEvents()
        time.sleep(0.05)

    bg = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    bg_path = HERE / "_probe_desktop.png"
    bg.save(bg_path)
    print("桌面背景已抓：%s  尺寸 %s  四角颜色 L%s R%s T%s B%s"
          % (bg_path.name, bg.size, bg.getpixel((2, h - 3)), bg.getpixel((w - 3, h - 3)),
             bg.getpixel((2, 2)), bg.getpixel((w - 3, 2))))

    # 两个采样区：灶膛上部（无火，纯底）、火焰主体
    box_pit = (55, 62, 135, 88)
    box_fire = (84, 94, 106, 118)

    tiles = []
    for pit_a in PIT_ALPHAS:
        overlay.CAMP_PIT_MIN_ALPHA = pit_a
        dial._bg_alpha = int(BG_ALPHA_K * 255)
        dial.show()
        dial.update()
        for _ in range(10):
            app.processEvents()
            time.sleep(0.04)
        off = grab_offscreen(dial, HERE / ("_probe_pit%d.png" % pit_a))
        dial.hide()
        for _ in range(6):
            app.processEvents()
            time.sleep(0.03)

        comp = bg.copy()
        comp.paste(off, (0, 0), off)

        c_pit = med(comp, box_pit)
        c_fire = med(comp, box_fire)
        # 火焰相对灶膛的对比度：亮度差（"跳不跳得出来"）
        contrast = (sum(c_fire) - sum(c_pit)) / 3.0
        print("  灶膛 alpha %3d (%.0f%%) | 灶膛底 rgb%-16s 饱和%5.1f%% | "
              "火焰区 rgb%-16s 饱和%5.1f%% | 火-底亮度差 %+6.1f"
              % (pit_a, pit_a / 2.55, str(c_pit), sat(c_pit), str(c_fire),
                 sat(c_fire), contrast))
        tiles.append((pit_a, comp, c_pit, c_fire, contrast))

    # ---- 拼一张对照图：每格 = 真实桌面 + 该档灶膛 ----
    pad, cap_h = 14, 34
    cols = len(tiles)
    sheet = Image.new("RGB", (pad + cols * (w + pad), cap_h + h + pad * 2), (32, 32, 36))
    dr = ImageDraw.Draw(sheet)
    f_title = font(19)
    f_cap = font(15)
    dr.text((pad, 9), "灶膛不透明度对照（底 = 真实抓屏桌面；底盘 plate 保持全透明）",
            font=f_title, fill=(238, 238, 242))
    for i, (pit_a, comp, c_pit, c_fire, contrast) in enumerate(tiles):
        px = pad + i * (w + pad)
        sheet.paste(comp, (px, cap_h))
        label = "灶膛 alpha %d (%.0f%%)" % (pit_a, pit_a / 2.55)
        dr.text((px, cap_h + h + 5), label, font=f_cap, fill=(240, 240, 244))
        if pit_a == 96:
            dr.rectangle([px - 2, cap_h - 2, px + w + 1, cap_h + h + 1],
                         outline=(232, 92, 92), width=2)
            dr.text((px, cap_h + h + 22), "  ← 改前：白底冲成中灰",
                    font=f_cap, fill=(232, 120, 120))
        elif pit_a == 232:
            dr.rectangle([px - 2, cap_h - 2, px + w + 1, cap_h + h + 1],
                         outline=(96, 214, 128), width=2)
            dr.text((px, cap_h + h + 22), "  ← 改后（新值）", font=f_cap,
                    fill=(120, 220, 150))
    out = HERE / "_backdrop_levels.png"
    sheet.save(out)
    print()
    print("对照图 -> %s" % out)
    dial._quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
