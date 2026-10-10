# -*- coding: utf-8 -*-
"""圆环「进度条」可读性回归 —— 低热度的弧不许和轨道糊在一起。

用户报：低热度时进度条里的绿色容易和背景混在一起，辨识度低。

根因：轨道（未走段）原先是**半透明白 / 半透明黑**，最终亮度会跟着桌面漂 ——
浅色桌面 + α=72% 时能漂到 134。而热度色阶的低段（冷蓝 → 青绿 → 草绿）亮度
**恒定在 141~150**（"等亮度变色相"是刻意的），两个一撞就分不出来了。

修法：轨道改成 **alpha=255 的定色**，取值与 Tk 版 THEMES 逐位相同。这样
"弧 − 轨道"的亮度差在任何不透明度、任何桌面下都恒定（dark +60、light −57）。

本文件盯十件事：

  1. 轨道在**真实渲染结果**里必须是完全不透明的（alpha=255）—— 半透明必漂
  2. 轨道的实际颜色必须等于 THEMES 里写的值（防被别处的 QPen 悄悄覆盖）
  3. 低热度弧与轨道的亮度差 ≥ 40（实测 dark 60 / light 57）
  4. 两版 UI 的轨道同色（防双 UI 配色分叉）
  5. **底盘最外圈不许有描边线**（用户报的"圈圈最外面有一个白色的圆形线条"）
  6. **环带轮廓四条边都要有线**（外弧 + 内弧 + 两个端头，用户第 6 轮报"现在只有
     外圈有，内圈和转角的那个地方也应该有"）：内外两条弧各要一个纯色像素，
     颜色 = THEMES 的 track_edge
  7. 轨道的底色**撞上**底盘底色时（用户报的"透明度 72 时区分度太低"），
     边界必须分得开
  8. **弧的端头**也要有线：沿切向跨过弧末端要能找到一条同时离开轨道和底盘的线，
     而且它必须落在弧**外**（t>0）—— 直线封口会落在 t=0，只有绕圆笔帽的半圆
     才落到 t>0
  9. 源码守卫：底盘不许有描边、轮廓必须画在轨道之前、闭合路径的六段一行不许少、
     Tk 侧四个轮廓元素都先于 i_track、线的 alpha 必须走 `flame.track_edge_alpha`
 10. **线的透明度与底盘反相**（用户第 7 轮）：`flame.track_edge_alpha` = `1 − bg_alpha`。
     逐条查：公式本身（端点 0↔1、单调）、α=0 时线画满（纯色像素）、α=100% 时线
     消失（窗口里没有任何像素靠近 track_edge）、α=72% 时线的像素 = 线色混向
     "底盘 × 桌面"合成色。最后四档全扫"边界可辨"。
     第 6 条改成在 **α=0** 上量就是因为这条规则：α=72% 时线只有 28% 不透明，
     **按定义**挤不出纯色像素（以前恒为不透明才可以）。

第 5 条的判据很干净，不用合成桌面：底盘边缘的抗锯齿只是"plate 色 × 透明度"的
混合，**不会改变非预乘的 RGB**。所以离屏帧上边界像素（alpha>0）的颜色必须仍等于
plate 色。原来那圈 `setPen(QPen(theme["rim"], 2.0))` 会往边界混进白/黑 —— 实测
dark 深底上边界像素变成 rgb(133,138,144)（plate 是 (24,27,35)）、Δlum +104；去掉
后同一位置的像素 rgb(27,28,36)、Δlum +1。见 `_rim_off_probe.py`。

第 6~8 条对应**另一条线**（用户点名要的）：它不在底盘上，而在**环带自己**身上，
是"进度条自己的边框"。两者容易搞混，所以第 5 条禁的是"盘子轮廓上那条"，
第 6~8 条要的是"环带轮廓那条" —— 判据半径差 ~6px，互不重叠。

第 7/8 条**必须合成到桌面底上**才算数：底盘是半透明的，轨道撞的是
"底色 × 桌面"混合后的最终亮度（dark α=72% 撞浅色桌面时底盘 lum 84.8、
轨道 81.4，两者几乎重合）。离屏帧上看不见"桌面"，也就看不见这个撞车。
判据也因此从"线自己够不够亮"改成 **max(盘面自己 vs 轨道, 线的分离度)**：
线淡下去（第 10 条）和盘面站起来是同一枚硬币的两面，两者取大才算边界可辨。
线在 28% 不透明时**按构造**只能拉开 ~1/4 的距离，所以门槛比定色线低（20）。

第 6 条还**间接盯着灶膛的画序**：灶膛半径和轮廓内弧只差 1.5px，它要是画在轮廓
之后，内弧就被切掉一截、挤不出纯色像素（实测可见宽度 2.1px → 1.5px）。

跑法：.pyenv\\Scripts\\python.exe _test_ring.py
"""
from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PyQt6.QtGui import QColor, QImage, QPainter                # noqa: E402
from PyQt6.QtWidgets import QApplication                        # noqa: E402

import flame                                                    # noqa: E402
from heatcore import load_config                                # noqa: E402
from overlay import HeatDial, START_DEG, SWEEP_DEG, THEMES      # noqa: E402

OK = 0
BAD = 0
HEATS = (5.0, 22.0, 35.0)          # "绿色"落在 22%~45%，22 与 35 是主战场
ALPHAS = (0, 114, 184, 255)
MIN_DLUM = 40.0                    # 弧与轨道的亮度差下限
MIN_EDGE = 25.0                    # 定色线"同时离开轨道和底盘"的分离度下限
MIN_EDGE_FADED = 20.0              # 线半透明时（第 10 条）：按构造只能拉开 ~1/4 距离
DESKS = ((30, 30, 36), (64, 64, 68), (238, 238, 240))


def ok(name, cond, detail=""):
    global OK, BAD
    if cond:
        OK += 1
        print("  [PASS] %-46s %s" % (name, detail))
    else:
        BAD += 1
        print("  [FAIL] %-46s %s" % (name, detail))


def eq(name, got, want):
    ok(name, got == want, "got=%r want=%r" % (got, want))


def lum(c):
    """Rec.601 感知亮度。判"看不看得见"看这个，别用 RGB 之和。"""
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def blend(fg, bg, k):
    """k = fg 的保留比例（= 不透明度）。半透明线画在某个底上就是这个混合。"""
    return tuple(int(round(fg[i] * k + bg[i] * (1.0 - k))) for i in range(3))


def scene(heat):
    kpm = round(heat * 3.0)
    return {"heat": heat, "kpm": kpm, "kpm_keys": kpm, "kpm_mouse": 0,
            "peak": 214.0, "state": "typing", "idle_seconds": 1.0, "total_keys": 100}


def sample(img, cx, cy, radius, deg):
    """在半径 radius、角度 deg 上取 3×3 里亮度居中的像素（抗锯齿边不算）。

    返回 (r, g, b, a) —— **alpha 是关键**：半透明的轨道在离屏图里就带 alpha < 255，
    到屏幕上会被桌面颜色冲淡，亮度就漂了。
    """
    a = math.radians(deg)
    x = cx + radius * math.cos(a)
    y = cy - radius * math.sin(a)
    vals = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            pc = img.pixelColor(int(round(x)) + dx, int(round(y)) + dy)
            c = (pc.red(), pc.green(), pc.blue(), pc.alpha())
            vals.append((lum(c), c))
    vals.sort(key=lambda v: v[0])
    return vals[4][1]


class Svc:
    def __init__(self):
        self.config = load_config()
        self.db_path = HERE / "data" / "heat.db"
        self.snap = scene(5.0)

    def snapshot(self):
        return dict(self.snap)

    def toggle_pause(self):
        return False

    def stop(self):
        pass


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    svc = Svc()
    dial = HeatDial(svc)
    dial._boot_done = True
    dial._campfire = True              # 弧与篝火无关，但走用户的实际视觉
    dial.show()
    dial._timer.stop()
    app.processEvents()

    w, h = dial.width(), dial.height()
    d = float(min(w, h))
    cx, cy = w / 2.0, h / 2.0
    radius = flame.ring_radius(d)

    def shot(theme, alpha, heat):
        dial._theme = THEMES[theme]
        dial._bg_alpha = alpha
        dial._snap = scene(heat)
        dial.repaint()
        app.processEvents()
        # 转成非预乘的 ARGB32：预乘格式下半透明像素的颜色是被乘过的，
        # 直接读会得到"看起来正常、其实已经变了"的数字。
        return dial.grab().toImage().convertToFormat(QImage.Format.Format_ARGB32)

    print("\n1. 轨道必须是完全不透明的定色（半透明必随背景漂）")
    for theme in ("dark", "light"):
        want = THEMES[theme]["track"]
        eq("%s 主题 track 只写 3 个分量（无 alpha）" % theme, len(want), 3)
        for alpha in ALPHAS:
            img = shot(theme, alpha, 22.0)
            frac = 0.22
            deg = START_DEG - SWEEP_DEG * frac - 14.0
            c = sample(img, cx, cy, radius, deg)
            eq("%s α=%3d 轨道像素 alpha" % (theme, alpha), c[3], 255)
            eq("%s α=%3d 轨道像素 rgb" % (theme, alpha), c[:3], tuple(want))

    print("\n2. 低热度弧 vs 轨道：亮度差 ≥ %.0f（越小越糊）" % MIN_DLUM)
    for theme in ("dark", "light"):
        for heat in HEATS:
            img = shot(theme, 184, heat)          # 184/255 = 73%，用户的档
            frac = heat / 100.0
            arc = sample(img, cx, cy, radius, START_DEG - SWEEP_DEG * frac * 0.5)
            trk = sample(img, cx, cy, radius, START_DEG - SWEEP_DEG * frac - 14.0)
            dl = lum(arc) - lum(trk)
            ok("%s h%.0f%%  Δlum %+6.1f" % (theme, heat, dl), abs(dl) >= MIN_DLUM)

    print("\n3. 弧本身也不透明（半透明的弧同样会被冲淡）")
    for theme in ("dark", "light"):
        img = shot(theme, 0, 22.0)                # α=0：底盘全透，最考验弧
        frac = 0.22
        c = sample(img, cx, cy, radius, START_DEG - SWEEP_DEG * frac * 0.5)
        eq("%s α=0 弧像素 alpha" % theme, c[3], 255)

    print("\n4. 双 UI 同色：Qt 的 track 必须等于 Tk 版的 track")
    tk_src = (HERE / "overlay_tk.py").read_text(encoding="utf-8")
    for theme in ("dark", "light"):
        m = re.search(r'"%s":\s*\{(.*?)\}' % theme, tk_src, re.S)
        mm = re.search(r'"track":\s*"#([0-9A-Fa-f]{6})"', m.group(1)) if m else None
        if not mm:
            ok("%s 从 overlay_tk.py 抠到 track 色" % theme, False, "没抠到")
            continue
        hexv = mm.group(1)
        tk_rgb = tuple(int(hexv[i:i + 2], 16) for i in (0, 2, 4))
        eq("%s 两版 track 逐位相同" % theme, tuple(THEMES[theme]["track"]), tk_rgb)

    print("\n5. 底盘最外圈不许有描边线（边缘像素必须仍是 plate 色）")
    # 不预设盘面半径：沿正下方（弧的缺口，无弧无轨道）往下扫，取**最后一个明显不透明**
    # 的像素当"底盘边缘"。边缘的抗锯齿只是 plate 色 × 透明度，不改变非预乘 RGB，所以
    # 这三行像素的颜色必须仍等于 plate。原来那圈 setPen(QPen(rim, 2.0)) 会往这里混进
    # 白/黑 —— 实测 dark 深底上边缘像素变成 rgb(133,138,144)（plate 是 (24,27,35)），
    # 换成合成到桌面看是 Δlum +104。
    ix = int(round(cx))
    iy = int(round(cy))
    for theme in ("dark", "light"):
        plate = tuple(THEMES[theme]["plate"])
        for alpha in (114, 184, 255):          # 跳过 α=0：盘面全透，"边缘"无从谈起
            img = shot(theme, alpha, 22.0)
            # 上界避开窗口最后两行：offscreen + 多次 grab() 后那里会留下 α=1 的残留
            # （实测 (255,255,0,1)），肉眼不可见但会污染判据。越界像素会返回
            # (0,0,0,255)，更不能算进来。
            y_end = min(iy + int(round(d / 2.0)), h - 3)
            ys = [y for y in range(iy + 40, y_end + 1)
                  if img.pixelColor(ix, y).alpha() >= 100]
            bad = []
            if not ys:
                bad.append("没扫到底盘边缘")
            else:
                last = max(ys)
                for y in (last - 2, last - 1, last):
                    pc = img.pixelColor(ix, y)
                    c = (pc.red(), pc.green(), pc.blue(), pc.alpha())
                    dev = max(abs(c[i] - plate[i]) for i in range(3))
                    # 容差 10：半透明像素在"预乘 → 非预乘"往返里有舍入（α=114 时
                    # plate(24,27,35) 读回来是 (29,29,35)）。描边混进来是 100+ 的量级，
                    # 差得很开，10 不会漏判。
                    if dev > 10:
                        bad.append((y, c, dev))
            ok("%s α=%3d 底盘边缘 3 行仍 = plate%s" % (theme, alpha, plate),
               not bad, "越界 %s" % (bad,))

    print("\n6. 环带轮廓：外沿和内沿**都要**找得到那条线，颜色必须对")
    for theme in ("dark", "light"):
        want = THEMES[theme]["track_edge"]
        eq("%s 主题 track_edge 只写 3 个分量（无 alpha）" % theme, len(want), 3)
        # 取 α=0（底盘全透明）—— 按第 10 条的反相规则，这一档线**画满**，
        # 才挤得出逐位等于 track_edge 的纯色像素。α=72% 时线只有 28% 不透明，
        # "没有纯色像素"是**设计如此**，不是 bug。
        img = shot(theme, 0, 4.0)
        # 热度必须取 4%：那时热度弧只占 209.6°~220°，180° 处是**纯轨道**。
        # 换成 22% 的话 180° 落在热度弧里，弧的内边缘和轮廓内弧只差 0.07px，
        # 抗锯齿会把内弧线像素渗成 rgb(197,204,216)（差 1 个单位），
        # "逐位相等"就抓不到了 —— 那是采样问题，不是线的问题。
        # 细线在半径方向只有 ~1px 实心、两侧是抗锯齿，所以扫一小段窗口找**纯色像素**：
        # 断言"存在一个像素逐位等于 track_edge"，比取某个固定半径稳（AA 位置随尺寸变）。
        for label, rr in (("外沿", flame.ring_edge_radius(d)),
                          ("内沿", flame.ring_edge_inner_radius(d))):
            hit = None
            for x in range(int(cx - rr) - 2, int(cx - rr) + 3):
                for y in (int(cy) - 1, int(cy), int(cy) + 1):
                    pc = img.pixelColor(x, y)
                    c = (pc.red(), pc.green(), pc.blue(), pc.alpha())
                    if c[:3] == tuple(want):
                        hit = (x, y, c)
            ok("%s 环%s找得到纯色描边像素 %s" % (theme, label, tuple(want)),
               hit is not None,
               "在 x%+d 附近扫" % int(cx - rr) if hit is None else "x=%d y=%d" % hit[:2])
            if hit:
                eq("%s %s描边像素 alpha=255（α=0 这档线是定色的）" % (theme, label),
                   hit[2][3], 255)
        # 几何：外弧 > 环外沿 > 环内沿 > 内弧。内弧一旦跑到环带里，就会糊在轨道上。
        bo = flame.ring_inner_radius(d) + flame.ring_thick(d)
        bi = flame.ring_inner_radius(d)
        er, eir = flame.ring_edge_radius(d), flame.ring_edge_inner_radius(d)
        ok("%s 外弧 %.1f > 环外沿 %.1f > 环内沿 %.1f > 内弧 %.1f"
           % (theme, er, bo, bi, eir), er > bo > bi > eir)
        eq("%s 端头半圆半径 = (外弧 − 内弧) / 2（半圆才接得上两条弧）" % theme,
           round(flame.ring_edge_cap_radius(d), 6), round((er - eir) / 2.0, 6))

    print("\n7. 轨道底色撞底盘底色时，描边必须把两者分开")
    # 用户报的那一档：dark + α=72% + 浅色桌面（实测轨道 rgba(74,82,97) vs 底盘
    # rgb(83,85,92)，Δlum −3.9 / ΔRGB 10.7 —— 离屏帧上看不出问题，合成桌面才现形）。
    # light 主题撞的是深/中灰桌面。两边都要过。
    COLLIDE = {"dark": (((30, 30, 36), False), ((238, 238, 240), True)),
               "light": (((30, 30, 36), True), ((64, 64, 68), True))}

    def comp(img, desk):
        out = QImage(img.size(), QImage.Format.Format_RGB32)
        out.fill(QColor(*desk))
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.drawImage(0, 0, img)
        p.end()
        return out

    def px(canvas, x, y):
        pc = canvas.pixelColor(x, y)
        return (pc.red(), pc.green(), pc.blue())

    for theme in ("dark", "light"):
        img = shot(theme, 184, 4.0)                  # α=184/255=72%
        g = {"band_out": flame.ring_inner_radius(d) + flame.ring_thick(d),
             "edge_w": flame.ring_edge_w(d)}
        for desk, collide in COLLIDE[theme]:
            canvas = comp(img, desk)
            # 轨道：180° 环中心线；底盘：270° 同一半径（弧的缺口，同一半径上没有环带）
            ct = px(canvas, int(round(cx - radius)), int(round(cy)))
            cp = px(canvas, int(round(cx)), int(round(cy + radius)))
            d_tp = lum(ct) - lum(cp)
            # 描边窗口里取单像素最大分离度（细线只有 1px 实心，用 3×3 中位会抹淡一半）
            best = 0.0
            for x in range(int(cx - g["band_out"] - g["edge_w"] - 1.5),
                           int(cx - g["band_out"]) + 2):
                for dy in (-1, 0, 1):
                    c = px(canvas, x, int(round(cy)) + dy)
                    best = max(best, min(abs(lum(c) - lum(ct)), abs(lum(c) - lum(cp))))
            tag = "%s α=72%% 底%s" % (theme, desk)
            if collide:
                print("       （%s：轨道 %s vs 底盘 %s，Δlum %+.1f —— 撞车档，"
                      "这条线正是为它加的）" % (tag, ct, cp, d_tp))
            # 判据是 **max(盘面, 线)**：线在 28% 不透明时只能拉开 ~1/4 的距离，
            # 而盘面自己在"底盘够实"的档上就分得开 —— 两者此消彼长（见第 10 条）。
            ok("%s 边界可辨 max(盘面 %.1f, 线 %.1f) ≥ %.0f"
               % (tag, abs(d_tp), best, MIN_EDGE_FADED),
               max(abs(d_tp), best) >= MIN_EDGE_FADED)
            # 对照值：这一档到底撞没撞。判错了说明桌面底或半透明合成有变，
            # 上面的"边界可辨"就失去意义了。
            eq("%s 撞车与否符合预期" % tag, abs(d_tp) < MIN_EDGE, collide)

    print("\n8. 端头（转角）：弧的两个端面也要有线 —— 用户第 6 轮报的正是这两条边")
    # 量法同 `_ring_frame_probe.py`：在 r=环中心线处沿**切向**跨过端面取剖面，找
    # 同时最远离轨道和邻居的像素。末端 −40°（220° 顺时针扫 260°），切向正方向
    # = 角度递减方向（弧的扫掠方向），所以 t>0 落在缺口里。
    # 起点 220° 不列判据：它总被热度弧的圆笔帽盖着，实际看不见（φ=0 时也是
    # 一小段 IDLE 弧），量出来的是热度弧的边缘，不是轮廓线。
    for theme in ("dark", "light"):
        img = shot(theme, 184, 4.0)
        for desk in ((30, 30, 36), (238, 238, 240)):
            canvas = comp(img, desk)
            ct = px(canvas, int(round(cx - radius)), int(round(cy)))       # 180°：轨道
            cp = px(canvas, int(round(cx)),
                    int(round(cy + d / 2.0 - max(2.0, d * 0.012) - 3.0)))  # 270° 缺口：底盘
            ang = math.radians(-40.0)
            bx = cx + flame.ring_radius(d) * math.cos(ang)
            by = cy - flame.ring_radius(d) * math.sin(ang)
            txx, tyy = math.sin(ang), math.cos(ang)
            best, where = 0.0, 0
            for t in range(-17, 18):
                c = px(canvas, int(round(bx + t * txx)), int(round(by + t * tyy)))
                sep = min(abs(lum(c) - lum(ct)), abs(lum(c) - lum(cp)))
                if sep > best:
                    best, where = sep, t
            tag = "%s α=72%% 底%s" % (theme, desk)
            ok("%s 端头边界可辨 max(盘面 %.1f, 线 %.1f) ≥ %.0f"
               % (tag, abs(lum(ct) - lum(cp)), best, MIN_EDGE_FADED),
               max(abs(lum(ct) - lum(cp)), best) >= MIN_EDGE_FADED,
               "最佳在 t%+d" % where)
            ok("%s 端头那条线落在弧外（t>0，缺口一侧）" % tag, where > 0,
               "t%+d" % where)

    print("\n9. 源码守卫：不许再给底盘加描边；整圈轮廓必须画在轨道之前")
    src = (HERE / "overlay.py").read_text(encoding="utf-8")
    tk_src = (HERE / "overlay_tk.py").read_text(encoding="utf-8")
    key = "drawEllipse(QPointF(cx, cy), plate_r, plate_r)"
    ok("overlay.py 里有底盘 drawEllipse（守卫的锚点还在）", key in src)
    seg = src[max(0, src.index(key) - 240):src.index(key)] if key in src else ""
    ok("底盘 drawEllipse 之前设的是 NoPen", "Qt.PenStyle.NoPen" in seg, seg.strip()[-60:])
    ok("那段里没有 QPen（旧描边不会再溜回来）", "QPen(" not in seg)
    ok("overlay_tk.py 的 i_plate 不画 outline",
       'fill=th["plate"], outline="", width=0' in tk_src)
    ok('两版 THEMES 都不再有 rim 键（找的是 `"rim":`，注释里的引用不算）',
       '"rim":' not in src and '"rim":' not in tk_src)
    # 线的透明度必须走共享公式：Qt 用 setAlphaF(flame.track_edge_alpha(...))，
    # Tk 用 _edge_colors() 里的同一条公式（Tk 的 canvas item 没有逐元素 alpha，
    # 只能把线色混向身下的颜色）。任何一边自己写死 alpha 都算分叉。
    ok("overlay.py 的轮廓 pen alpha 来自 flame.track_edge_alpha",
       "edge_col.setAlphaF(flame.track_edge_alpha(" in src)
    ok("overlay_tk.py 的 _edge_colors 用同一个公式",
       "flame.track_edge_alpha(self.cfg_alpha)" in tk_src)
    ok("overlay_tk.py 有 _sync_edge_colors（篝火⇄数字切换时跟着换底色）",
       "_sync_edge_colors" in tk_src and "self._sync_edge_colors()" in tk_src)
    # 层序：Qt 先画整圈轮廓再画轨道（后画的压在上面）；Tk 无 z-index，只能靠
    # "创建顺序" —— 四个轮廓元素（i_edge / i_edge_in / i_edge_caps）都要先于 i_track。
    i_path = src.index("p.drawPath(path)") if "p.drawPath(path)" in src else -1
    i_track_arc = src.index("drawArc(arc_rect") if "drawArc(arc_rect" in src else -1
    ok("overlay.py 真的调了轮廓的 drawPath（光有变量不算）", "p.drawPath(path)" in src)
    ok("overlay.py 的轮廓 drawPath 在轨道 drawArc 之前",
       i_path > 0 and i_track_arc > 0 and i_path < i_track_arc,
       "path@%d track@%d" % (i_path, i_track_arc))
    # 轮廓必须是**闭合**的：外弧 → 末端半圆 → 内弧 → 起点半圆 → closeSubpath。
    # 少任何一段（尤其两条半圆）就退回成"只有外圈"，用户第 6 轮报的 bug 复现。
    for frag in ("path.arcMoveTo(rect_o, START_DEG)",
                 "path.arcTo(rect_o, START_DEG, -SWEEP_DEG)",
                 "path.arcTo(rect_e, end_deg, -180.0)",
                 "path.arcTo(rect_i, end_deg, SWEEP_DEG)",
                 "path.arcTo(rect_s, START_DEG + 180.0, -180.0)",
                 "path.closeSubpath()"):
        ok("轮廓里有 %s" % frag, frag in src)
    ok("overlay_tk.py 的内弧建在 i_track 之前",
       0 < tk_src.index("self.i_edge_in") < tk_src.index("self.i_track"),
       "in@%d track@%d" % (tk_src.index("self.i_edge_in"), tk_src.index("self.i_track")))
    ok("overlay_tk.py 的两个端头半圆建在 i_track 之前",
       0 < tk_src.index("self.i_edge_caps") < tk_src.index("self.i_track"),
       "caps@%d track@%d" % (tk_src.index("self.i_edge_caps"),
                             tk_src.index("self.i_track")))
    ok("overlay_tk.py 的端头半圆是 180° 弧（少了就退回直线）",
       "extent=-180.0" in tk_src)
    ok("overlay_tk.py 的 i_edge 建在 i_track 之前",
       0 < tk_src.index("self.i_edge") < tk_src.index("self.i_track"),
       "edge@%d track@%d" % (tk_src.index("self.i_edge"), tk_src.index("self.i_track")))
    for theme in ("dark", "light"):
        m = re.search(r'"%s":\s*\{(.*?)\}' % theme, tk_src, re.S)
        mm = re.search(r'"track_edge":\s*"#([0-9A-Fa-f]{6})"', m.group(1)) if m else None
        if not mm:
            ok("%s 从 overlay_tk.py 抠到 track_edge 色" % theme, False, "没抠到")
            continue
        hexv = mm.group(1)
        tk_rgb = tuple(int(hexv[i:i + 2], 16) for i in (0, 2, 4))
        eq("%s 两版 track_edge 逐位相同" % theme, tuple(THEMES[theme]["track_edge"]), tk_rgb)

    print("\n10. 线的透明度与底盘反相（用户第 7 轮）：端点 0↔1、单调、渲染对得上")
    # 10a 公式本身
    for a in (0.0, 0.45, 0.72, 1.0):
        eq("track_edge_alpha(%.2f) = 1 − %.2f" % (a, a),
           round(flame.track_edge_alpha(a), 6), round(1.0 - a, 6))
    eq("端点：底盘全不透明 → 线完全不透明 = 0", flame.track_edge_alpha(1.0), 0.0)
    eq("端点：底盘全透明 → 线全不透明 = 1", flame.track_edge_alpha(0.0), 1.0)
    ok("单调：底盘越实心，线越淡",
       flame.track_edge_alpha(0.0) > flame.track_edge_alpha(0.45)
       > flame.track_edge_alpha(0.72) > flame.track_edge_alpha(1.0))

    # 10b 渲染：α=0 线画满（有纯色像素）、α=255 线消失（窗口里没有任何像素靠近它）
    def edge_window():
        bo = flame.ring_inner_radius(d) + flame.ring_thick(d)
        ew = flame.ring_edge_w(d)
        xs = list(range(int(cx - bo - ew - 1.5), int(cx - bo) + 2))
        return [(x, int(round(cy)) + dy) for x in xs for dy in (-1, 0, 1)]

    for theme in ("dark", "light"):
        want = tuple(THEMES[theme]["track_edge"])
        lw = lum(want)
        for desk in DESKS:
            canvas = comp(shot(theme, 0, 4.0), desk)
            hit = [c for c in (px(canvas, x, y) for x, y in edge_window()) if c == want]
            ok("%s α=0 底%s 线画满（存在逐位 = track_edge 的像素）" % (theme, desk),
               bool(hit), "%d 个" % len(hit))
            canvas = comp(shot(theme, 255, 4.0), desk)
            near = min(abs(lum(px(canvas, x, y)) - lw) for x, y in edge_window())
            # α=100% 那档线完全消失：窗口里只剩轨道和底盘，亮度离线色 ≥ 30
            ok("%s α=100%% 底%s 线消失（窗口最近像素离线色 %.0f ≥ 30）"
               % (theme, desk, near), near >= 30)

    # 10c α=72%：线的像素必须等于"线色 × 28% + (底盘 × 72% 桌面) × 72%"
    k72 = flame.track_edge_alpha(184 / 255.0)
    for theme in ("dark", "light"):
        want = tuple(THEMES[theme]["track_edge"])
        plate = tuple(THEMES[theme]["plate"])
        for desk in DESKS:
            canvas = comp(shot(theme, 184, 4.0), desk)
            under = blend(plate, desk, 184 / 255.0)          # 线底下的"底盘 × 桌面"
            want_px = blend(want, under, k72)
            best = min(((max(abs(px(canvas, x, y)[i] - want_px[i]) for i in range(3)),
                         px(canvas, x, y)) for x, y in edge_window()),
                       key=lambda t: t[0])
            ok("%s α=72%% 底%s 线像素 = 线色×%.0f%% + 底盘合成色"
               % (theme, desk, k72 * 100), best[0] <= 5,
               "最近 %s / 期望 %s（差 %d）" % (best[1], want_px, best[0]))

    # 10d 四档全扫：max(盘面自己, 线) ≥ MIN_EDGE_FADED —— 线淡下去时盘面自己接上
    for theme in ("dark", "light"):
        worst = 99.0
        for alpha in ALPHAS:
            for desk in DESKS:
                canvas = comp(shot(theme, alpha, 4.0), desk)
                ct = px(canvas, int(round(cx - radius)), int(round(cy)))
                cp = px(canvas, int(round(cx)),
                        int(round(cy + d / 2.0 - max(2.0, d * 0.012) - 3.0)))
                # 线自己的分离度要按"同时离开两端"算，取窗口里的极值
                edge = 0.0
                for x, y in edge_window():
                    c = px(canvas, x, y)
                    edge = max(edge, min(abs(lum(c) - lum(ct)), abs(lum(c) - lum(cp))))
                worst = min(worst, max(abs(lum(ct) - lum(cp)), edge))
        ok("%s 四档 × 三桌面 最差 max(盘面, 线) %.1f ≥ %.0f"
           % (theme, worst, MIN_EDGE_FADED), worst >= MIN_EDGE_FADED)

    print("\n结果：%d 通过 / %d 失败" % (OK, BAD))
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
