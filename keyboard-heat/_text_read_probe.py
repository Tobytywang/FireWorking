# -*- coding: utf-8 -*-
"""数字仪表盘「文字可读性」探针 —— 底盘半透明/全透明时文字还能不能看清。

用户报两件事：
  1. α=45% 时，灰色底盘上的文字（尤其灰色的 muted 行）和背景重合、辨识度差；
  2. α=0%（全透明）时，白色的文字被背景整个盖住、看不见。

根因：文字一直是用主题色**直接画**在底盘上，没有自己的底色。底盘一透明，文字就
直接贴在桌面上，对比度完全交给「桌面碰巧是什么色」。

修法（见 overlay._hud_text）：给每段文字描一圈 1px 的**反相光晕**——亮字配暗边、
暗字配亮边。底色是深是浅、盘体透明与否都不影响，边框那圈反相色总能勾出字形。

本探针做两件事：
  · 离屏渲染「有光晕(改后)」vs「无光晕(改前)」两种，叠到深/中/浅三种桌面底上，
    量文字相对**局部背景**的亮度差（contrast_low=暗边 vs 底、contrast_high=填充 vs 底）。
  · 出一张对照图：行 = 主题 × α × 桌面，列 = 改前 / 改后。

跑法：.pyenv\\Scripts\\python.exe _text_read_probe.py
"""
from __future__ import annotations

import math
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import Qt                                    # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter               # noqa: E402
from PyQt6.QtWidgets import QApplication                       # noqa: E402

import flame                                                   # noqa: E402
from heatcore import load_config                              # noqa: E402
from overlay import HeatDial, THEMES                           # noqa: E402

# （主题, α, 桌面）—— 用户点名的两档：45% 和 0%，外加一档实心做对照。
THEMES_USED = ("dark", "light")
ALPHAS = (0.0, 0.45, 1.0)
DESKTOPS = (
    ("深终端", (30, 30, 36)),
    ("中灰", (64, 64, 68)),
    ("浅色", (238, 238, 240)),
)


def lum(c):
    """Rec.601 感知亮度。判「看不看得见」看这个，别用 RGB 之和。"""
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _plain_text(p, rect, text, font, fill, align):
    """改前行为：文字直接画、不带光晕（等价旧 drawText）。"""
    if not text:
        return
    p.setFont(font)
    p.setPen(fill)
    p.drawText(rect, int(align), text)


def _noop_text(p, rect, text, font, fill, align):
    return None


def frame(dial, buf, alpha, desktop, mode):
    """mode: 'plain'=改前无光晕  'halo'=改后带光晕  'none'=不画文字(取背景基准)。"""
    dial._bg_alpha = int(round(alpha * 255))
    if mode == "plain":
        dial._hud_text = _plain_text
    elif mode == "halo":
        dial._hud_text = types.MethodType(HeatDial._hud_text, dial)
    else:
        dial._hud_text = _noop_text
    dial.repaint()
    pm = dial.grab()
    buf.fill(QColor(*desktop))
    p = QPainter(buf)
    p.drawPixmap(0, 0, pm)
    p.end()
    return buf


def scene(heat, kpm):
    return {"heat": heat, "kpm": kpm, "kpm_keys": kpm, "kpm_mouse": 0,
            "peak": 214.0, "state": "typing", "idle_seconds": 1.0,
            "total_keys": 100}


def contrast_pair(dial, buf, alpha, desktop, use_halo):
    """返回 (bg_lum, text_min_lum, text_max_lum)。min/max 取「有字」帧里文字像素的
    亮度极值：min 是反相光晕（暗边）贡献、max 是填充色贡献。两者都相对局部背景算
    差值，任一个够大就说明文字看得清（暗边勾形 or 填充本身够跳）。"""
    with_img = frame(dial, buf, alpha, desktop, "halo" if use_halo else "plain").copy()
    no_img = frame(dial, buf, alpha, desktop, "none")
    W, H = with_img.width(), with_img.height()
    bgs, lums = [], []
    for y in range(H):
        for x in range(W):
            pc = with_img.pixelColor(x, y)
            nc = no_img.pixelColor(x, y)
            wc = (pc.red(), pc.green(), pc.blue())
            ncl = lum((nc.red(), nc.green(), nc.blue()))
            # 文字/光晕像素 = 有字帧和空白帧差得明显的地方
            if (abs(pc.red() - nc.red()) + abs(pc.green() - nc.green())
                    + abs(pc.blue() - nc.blue())) > 14:
                bgs.append(ncl)                 # 该像素处的局部背景（没字时）
                lums.append(lum(wc))
    if not bgs:
        return None
    bgs.sort(); lums.sort()
    return (bgs[len(bgs) // 2], lums[0], lums[-1])


def readable(bg, lo, hi):
    """可读的判据：暗边或填充任一相对背景的 |Δlum| ≥ 30。"""
    return max(abs(lo - bg), abs(hi - bg)) >= 30


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    class Svc:
        def __init__(self):
            self.config = load_config()
            self.db_path = HERE / "data" / "heat.db"

        def snapshot(self):
            return dict(dial._snap)

        def toggle_pause(self):
            return False

        def stop(self):
            pass

    dial = HeatDial(Svc())
    dial._boot_done = True
    dial._campfire = False                 # 数字仪表盘，文字都在这里
    dial._snap = scene(heat=58.0, kpm=174)  # 让大数字走 heat_color（橙色），测最花哨的一档
    dial.show()
    dial._timer.stop()
    app.processEvents()

    w, h = dial.width(), dial.height()
    buf = QImage(w, h, QImage.Format.Format_RGB32)

    print("=" * 76)
    print("数字仪表盘文字可读性：改前(无光晕) vs 改后(反相光晕)")
    print("=" * 76)
    print("  %-6s %-5s %-7s | %-9s %-9s | %-9s %-9s | %s"
          % ("主题", "α", "桌面", "改前Δlow", "改前Δhigh", "改后Δlow", "改后Δhigh", "改后可读"))
    rows = []
    for tname in THEMES_USED:
        dial._theme = THEMES[tname]
        for alpha in ALPHAS:
            for dname, desktop in DESKTOPS:
                before = contrast_pair(dial, buf, alpha, desktop, use_halo=False)
                after = contrast_pair(dial, buf, alpha, desktop, use_halo=True)
                if before is None or after is None:
                    continue
                b_bg, b_lo, b_hi = before
                a_bg, a_lo, a_hi = after
                b_low, b_high = abs(b_lo - b_bg), abs(b_hi - b_bg)
                a_low, a_high = abs(a_lo - a_bg), abs(a_hi - a_bg)
                ok = "是" if readable(a_bg, a_lo, a_hi) else "否"
                print("  %-6s %-5.2f %-7s | %-9.1f %-9.1f | %-9.1f %-9.1f | %s"
                      % (tname, alpha, dname, b_low, b_high, a_low, a_high, ok))
                rows.append((tname, alpha, dname, desktop, before, after))

    # 对照图：行 = 每组合，列 = 改前 / 改后
    from PIL import Image, ImageDraw
    try:
        from PIL import ImageFont
        FONT = "C:/Windows/Fonts/msyh.ttc"
        f1 = ImageFont.truetype(FONT, 20)
        f2 = ImageFont.truetype(FONT, 14)
    except Exception:
        f1 = f2 = None

    scale = 2
    pad = 18
    gap = 14
    band = 40
    tile = max(w, h) * scale
    ncol = 2
    W = pad * 2 + ncol * (tile + gap) - gap
    H = pad * 2 + len(rows) * (tile + band + gap) - gap
    img = Image.new("RGB", (W, H), (248, 248, 250))
    dr = ImageDraw.Draw(img)
    dr.text((pad, 12), "数字仪表盘文字可读性：左=改前(无光晕) 右=改后(反相光晕)",
            fill=(26, 28, 34), font=f1)
    dr.text((pad, 42), "行=主题×α×桌面。改后给文字描一圈反相光晕，45% 与 0% 两档在浅色桌面下也能看清。",
            fill=(96, 102, 116), font=f2)

    for r, (tname, alpha, dname, desktop, before, after) in enumerate(rows):
        y = pad * 2 + r * (tile + band + gap)
        # 改前
        dial._theme = THEMES[tname]
        before_img = frame(dial, buf, alpha, desktop, "plain")
        before_img.save(str(HERE / "_tr_cell_b.png"), "PNG")
        tb = Image.open(HERE / "_tr_cell_b.png").convert("RGB").resize((tile, tile), Image.LANCZOS)
        img.paste(tb, (pad, y))
        # 改后
        after_img = frame(dial, buf, alpha, desktop, "halo")
        after_img.save(str(HERE / "_tr_cell_a.png"), "PNG")
        ta = Image.open(HERE / "_tr_cell_a.png").convert("RGB").resize((tile, tile), Image.LANCZOS)
        img.paste(ta, (pad + tile + gap, y))
        a_bg, a_lo, a_hi = after
        label = "%s α=%.0f %% %s  改后Δ≥%.0f" % (tname, alpha * 100, dname,
                                                   max(abs(a_lo - a_bg), abs(a_hi - a_bg)))
        dr.text((pad, y + tile + 8), label, fill=(40, 40, 50), font=f2)

    for tmp in ("_tr_cell_b.png", "_tr_cell_a.png"):
        try:
            (HERE / tmp).unlink()
        except OSError:
            pass
    out = HERE / "_text_read_probe.png"
    img.save(str(out), "PNG")
    print("\n对照图 %s  %s" % (out.name, img.size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
