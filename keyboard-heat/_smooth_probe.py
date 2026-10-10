"""火焰"从小到大"到底是不是平滑连续的？—— 用户报了一个突变，但不确定是 UI 还是自己输入量突增。

分三段量，结论各管一半：

  A. **输入侧**（输入 → 热度）：用**真实的 HeatEngine** 跑仿真（把 heatcore.time 换成假时钟），
     按固定 kpm 喂击键、每 80ms 采一次样（和篝火模式的实际刷新率一致），看热度轨迹长什么样。
  B. **映射侧**（热度 → 火苗几何/颜色）：把 fire_heat → flame_height → flame_colors 这条链
     在细网格上扫一遍，找跳变。
  C. **像素侧**：直接渲染相邻热度帧，量"每 1% 热度引起多少像素变化"，用**步长减半判据**区分
     "陡"（Δ ∝ h）和"断"（Δ 不随 h 缩小）。

步长减半判据是这段的关键：连续函数在 h → 0 时 Δ → 0；真跳变则 Δ 是常数量级。
冷端还有个特例 —— 链条里有 t^0.72 和 frac^0.75 两个幂次（复合指数 0.54），
所以 Δ ∝ h^0.54，**是连续但不是 Lipschitz**（陡得有理），要看指数才分得清。

    .pyenv\\Scripts\\python.exe _smooth_probe.py
"""
from __future__ import annotations

import math
import sys
import time as _real_time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import heatcore                                      # noqa: E402
from heatcore import HeatEngine, load_config         # noqa: E402

try:
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QApplication
except ImportError as exc:
    print("SKIP 这个解释器没有 PyQt6：%s" % exc)
    raise SystemExit(2)

import flame                                          # noqa: E402
from overlay import IDLE_ARC_DEG, SWEEP_DEG           # noqa: E402
from PIL import Image, ImageDraw                      # noqa: E402

CFG = load_config()
D = float(CFG["overlay"]["*size"])
MAX_H = D * flame.FLAME_MAX_H_K
PHASE = 3.8
OUT = HERE / "_smooth_probe.png"
FONT = "C:/Windows/Fonts/msyh.ttc"
# 火焰 + 光晕所在的方框（不含圆环；圆环半径 80.6，这个框的四角最远 69.5 —— 圈外）
BOX = (60, 35, 130, 150)


# ============================================================ A. 输入侧

class Clock:
    """替掉 heatcore.time 的假时钟 —— 不然量 120 秒的轨迹要真等 120 秒。"""

    def __init__(self, t0=1e6):
        self.t = float(t0)

    def monotonic(self):
        return self.t

    def time(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def simulate(kpm, seconds=120.0, dt=0.08, floor=True):
    """按固定 kpm 打字，每 dt 秒采一次样，返回 [(t, heat, kpm_measured, span), ...]。

    dt=0.08 = 篝火模式的实际刷新间隔（overlay._refresh_interval → min(base, 80)ms），
    而 sample() 只在 UI 刷新时被调用，所以 EMA 每步的增量就是 weight=1-(1-0.2)^0.08。
    floor=True 时复现当前代码的 `if heat < 0.5: heat = 0`。
    """
    clock = Clock()
    real = heatcore.time
    heatcore.time = clock
    try:
        eng = HeatEngine(CFG["heat"])
        traj = []
        acc = 0.0
        steps = int(seconds / dt) + 1
        for i in range(steps):
            acc += kpm / 60.0 * dt
            n = int(acc)
            acc -= n
            for _ in range(n):
                eng.record()
            snap = eng.sample()
            h = snap["heat"]
            if not floor:
                # 反事实：只在"空闲衰减"那支才抹零（拟议改动）
                h = snap["heat"]
            traj.append((i * dt, h, snap["kpm"], span_of(h)))
            clock.advance(dt)
        return traj
    finally:
        heatcore.time = real


def span_of(raw_heat):
    """原始热度 0~100 → 火苗总跨度 px（走真实链路：fire_heat → flame_height）。"""
    t = flame.fire_heat(max(0.0, raw_heat) / 100.0, "typing", False, 0.0)
    return flame.flame_height(t, MAX_H)


def simulate_old(kpm, seconds=120.0, dt=0.08):
    """**改前**代码的轨迹（复刻旧 HeatEngine.sample 的热度那几行）。

    旧代码每帧算完都 `if heat < 0.5: heat = 0`（不分升降），快照只给 1 位小数。
    照抄下来做对照：低于 ~85 kpm 全程卡 0、高一点的也要几十秒才起跳、起跳一步 +5.4px。
    """
    window, alpha, full_kpm, idle_after, decay = 60.0, 0.2, 300.0, 30.0, 0.9
    buckets = []
    heat = 0.0
    last_active = None
    traj = []
    acc = 0.0
    t = 0.0
    for i in range(int(seconds / dt) + 1):
        acc += kpm / 60.0 * dt
        n = int(acc)
        acc -= n
        sec = int(t)
        if n:
            if buckets and buckets[-1][0] == sec:
                buckets[-1][1] += n
            else:
                buckets.append([sec, n])
            last_active = t
        while buckets and buckets[0][0] < t - window:
            buckets.pop(0)
        kpm_now = sum(b[1] for b in buckets) * 60.0 / window
        idle = (t - last_active) if last_active is not None else 1e9
        if last_active is not None and idle > idle_after:
            heat *= decay ** dt
        else:
            target = min(kpm_now / full_kpm, 1.0) * 100.0
            weight = 1.0 - (1.0 - alpha) ** dt
            heat += (target - heat) * weight
        if heat < 0.5:                      # ← 旧代码：不分升降，一律抹零
            heat = 0.0
        heat = min(max(heat, 0.0), 100.0)
        heat_out = round(heat, 1)           # ← 旧代码：快照 1 位小数
        traj.append((t, heat_out, int(round(kpm_now)), span_of(heat_out)))
        t += dt
    return traj


# ============================================================ B. 映射侧

def mapping_sweep():
    """细扫映射链，返回 [(raw_heat, span, tip_y, w, ramp_pos, arc_deg, n_spark), ...]。"""
    rows = []
    grid = [i * 0.02 for i in range(0, 251)]                    # 0 ~ 5.00，步长 0.02
    grid += [5.0 + i * 0.25 for i in range(1, 381)]             # 5 ~ 100，步长 0.25
    for h in grid:
        frac = h / 100.0
        t = flame.fire_heat(frac, "typing", False, 0.0)
        span = flame.flame_height(t, MAX_H)
        w = flame.flame_width(span, t)
        arc = IDLE_ARC_DEG if frac <= 0.002 else SWEEP_DEG * frac
        n_spark = int(round(2 + 7 * max(0.0, min(1.0, t))))
        rows.append((h, span, span, w, flame._ramp_pos(t), arc, n_spark))
    return rows


def holder_test(x0, h0, hmin):
    """在 x0 处把步长从 h0 一路减半，看 Δspan 怎么缩 —— 连续则 Δ→0，跳变则 Δ 不变。"""
    out = []
    h = h0
    while h >= hmin:
        out.append((h, span_of(x0 + h) - span_of(x0)))
        h /= 2.0
    return out


# ============================================================ C. 像素侧

def render(heat_raw, li_back, li_front, state="typing", spark=None):
    """离屏渲一帧（只画火 + 贴图柴堆，不画圆环/底盘 —— BOX 里本来也看不到圆环）。

    底填成"灶膛在白桌面上的实际合成色" (36,34,38)：相邻帧做差时它自动抵掉，
    但排进对照图时观感贴近真机。
    spark=None → 新建默认 SparkField（照常放火星）；False → 这帧不放（暂停态）。
    """
    t = flame.fire_heat(heat_raw / 100.0, state, False, 0.0)
    field = flame.SparkField() if spark is None else spark
    img = QImage(int(D), int(D), QImage.Format.Format_ARGB32)
    img.fill(QColor(36, 34, 38))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    flame.draw_campfire_qt(p, D / 2.0, D / 2.0, D, t, PHASE, field,
                           log_image=li_back, log_image_front=li_front, floor=True)
    p.end()
    return img


def img_delta(a, b):
    """两帧在 BOX 内的平均绝对像素差（0~255）。"""
    ia = a.copy(BOX[0], BOX[1], BOX[2] - BOX[0], BOX[3] - BOX[1])
    ib = b.copy(BOX[0], BOX[1], BOX[2] - BOX[0], BOX[3] - BOX[1])
    ba = bytes(ia.constBits().asstring(ia.sizeInBytes()))
    bb = bytes(ib.constBits().asstring(ib.sizeInBytes()))
    return sum(abs(x - y) for x, y in zip(ba, bb)) / float(len(ba))


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    print("配置：full_kpm=%s  ema_alpha=%s  window=%ss  idle_after=%ss"
          % (CFG["heat"]["*full_kpm"], CFG["heat"]["*ema_alpha"],
             CFG["heat"]["window_seconds"], CFG["heat"]["idle_after_seconds"]))
    print("篝火模式刷新间隔 = 80ms（overlay._refresh_interval）  → EMA 每步 weight = %.5f"
          % (1.0 - (1.0 - 0.2) ** 0.08))
    print()

    # ---------------- A ----------------
    print("=" * 78)
    print("A. 输入侧：按固定速度打字，热度轨迹（120 秒，每 80ms 采样）")
    print("=" * 78)
    RATES = (40, 60, 80, 84, 90, 120, 200, 300)

    def table(title, fn, rates):
        out = {}
        print("  %s" % title)
        print("  %-8s %-9s %-11s %-13s %-13s %s"
              % ("kpm", "上限热度", "起步时刻", "120s 后跨度", "单帧最大跳", "视觉"))
        for kpm in rates:
            traj = fn(kpm)
            out[kpm] = traj
            spans = [s for _, _, _, s in traj]
            nz = next((tt for tt, h, _, _ in traj if h > 0.0), None)
            jumps = [spans[i + 1] - spans[i] for i in range(len(spans) - 1)]
            cap = min(kpm / float(CFG["heat"]["*full_kpm"]), 1.0) * 100.0
            note = "全程卡在 0（火毫无反应）" if nz is None else "起跳"
            print("  %-8d %-9.0f %-11s %-13.1f %-13s %s"
                  % (kpm, cap, "-" if nz is None else "%.1fs" % nz,
                     spans[-1], "%.2fpx" % (max(jumps) if jumps else 0.0), note))
        print()
        return out

    traj_by_rate = table("【本轮修复后】下限只在衰减支（heatcore._HEAT_FLOOR）",
                         simulate, RATES)
    old_by_rate = table("【改前】每帧不分升降都 `if heat < 0.5: heat = 0`",
                        simulate_old, RATES)
    print("  阈值 = full_kpm × (0.5/每步权重) ≈ %.0f kpm：旧代码里每步增量 target×权重"
          % (0.5 / (1.0 - 0.8 ** 0.08) * 300 / 100))
    print("  必须一次 ≥ 0.5，而每步都从 0 重来 —— 达不到就永远卡住，达到了又一步跳 5.4px。")
    print()

    # ---------------- B ----------------
    print("=" * 78)
    print("B. 映射侧：热度 → 火苗几何（细扫，含步长减半判据）")
    print("=" * 78)
    rows = mapping_sweep()
    print("  低热段 0~5（每格 0.02 热度）")
    print("  %-7s %-11s %-11s %-9s %-11s" % ("热度", "跨度 px", "Δ跨度", "Δ/热度", "火星数"))
    prev = None
    for h, span, _t, _w, _rp, _arc, ns in rows:
        if h > 5.01:
            break
        if prev is None or abs(h - round(h)) < 1e-9 or h in (0.5,):
            print("  %-7.2f %-11.2f %-11s %-9s %-11d"
                  % (h, span, "-" if prev is None else "%+.2f" % (span - prev),
                     "-" if prev is None else "%.1f" % ((span - prev) / 0.02
                                                        if h > 0 else float("nan")),
                     ns))
        prev = span
    print()
    print("  步长减半判据（跨度随热度的响应）：")
    for x0, label in ((0.0, "热度 0（冷端起点）"), (5.0, "热度 5"), (50.0, "热度 50")):
        series = holder_test(x0, 0.5 if x0 == 0.0 else 2.0, 0.0078125)
        print("    %s" % label)
        for i, (h, dv) in enumerate(series):
            exp = ""
            if i:
                hh, dprev = series[i - 1]
                if dv > 1e-9 and dprev > 1e-9:
                    exp = "  比上一档 ×%.3f（h 减半 → 线性应 0.500）" % (dv / dprev)
            print("      h=%-10.6f Δ=%.4f px%s" % (h, dv, exp))
    print()

    # 色阶位置 / 环绕弧 / 火星数
    print("  其它随热度变化的量：")
    rp0, rp5, rp20 = (flame._ramp_pos(flame.fire_heat(x / 100.0, "typing", False, 0.0))
                      for x in (0.0, 5.0, 20.0))
    print("    色阶位置  _ramp_pos(fire_heat)：0 热度 %.3f，5 热度 %.3f，20 热度 %.3f"
          % (rp0, rp5, rp20))
    print("    火星颗数  n = int(round(2 + 7*fire_heat)) —— **整数阶梯**，跳变点（原始热度）：")
    pts, prevn = [], None
    for h in [i * 0.01 for i in range(10001)]:
        t = flame.fire_heat(h / 100.0, "typing", False, 0.0)
        n = int(round(2 + 7 * t))
        if prevn is not None and n != prevn:
            pts.append((h, prevn, n))
        prevn = n
    print("      " + "  ".join("%.2f(%d→%d)" % p for p in pts))
    print("    环绕热弧  frac>0.002 时取 frac，否则取 IDLE_ARC_DEG/SWEEP_DEG=%.4f："
          % (IDLE_ARC_DEG / SWEEP_DEG))
    print("      0 热度 → %.2f°    0.5 热度 → %.2f°    1.0 热度 → %.2f°    → **先缩后长**"
          % (IDLE_ARC_DEG, SWEEP_DEG * 0.005, SWEEP_DEG * 0.01))
    print()

    # ---------------- C ----------------
    print("=" * 78)
    print("C. 像素侧：相邻热度帧的实际差别（BOX=%s）" % (BOX,))
    print("=" * 78)
    li_back = flame.log_image_load(HERE / "assets" / "log-pile.png", slot="back")
    li_front = flame.log_image_load(HERE / "assets" / "log-pile-front.png", slot="front")
    grid = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 13.0, 16.0,
            20.0, 25.0, 30.0, 40.0, 50.0, 65.0, 80.0, 100.0]
    frames = {h: render(h, li_back, li_front) for h in grid}
    frames["paused"] = render(flame.EMBER_HEAT * 100.0, li_back, li_front,
                              state="paused")
    print("  %-9s %-9s %-12s %s" % ("热度区间", "Δ热度", "平均像素差", "每 1% 热度"))
    per = []
    for a, b in zip(grid, grid[1:]):
        dv = img_delta(frames[a], frames[b])
        rate = dv / (b - a)
        per.append((a, b, dv, rate))
        print("  %-9s %-9.1f %-12.2f %.3f" % ("%.1f→%.1f" % (a, b), b - a, dv, rate))
    print()
    print("  从 0 起跳的「第一步」到底多大（这是真实会发生的动作 —— 热度下限 0.5）：")
    f0 = frames[0.0]
    for step in (0.5, 1.0, 2.0, 5.0, 10.0):
        print("    热度 0 → %-5.1f  平均像素差 %.2f   跨度 %.1f → %.1f px（+%.1f）"
              % (step, img_delta(f0, render(step, li_back, li_front)),
                 span_of(0.0), span_of(step), span_of(step) - span_of(0.0)))
    print()
    print("  满热/中热的对照尺度：热度 40→50 的平均像素差 %.2f（同样 10 个热度）"
          % img_delta(frames[40.0], frames[50.0]))
    print()

    # ---------------- D ----------------
    print("=" * 78)
    print("D. 另外三处跳变 —— 都已修，这里量的是修复后的状态")
    print("=" * 78)
    emb = flame.EMBER_HEAT
    _sp_idle = span_of(0.0)
    _sp_pause = flame.flame_height(flame.fire_heat(0.0, "paused", False, 0.0), MAX_H)
    print("  ① 手动暂停（托盘「暂停记录」）：")
    print("     空闲跨度 %.1f px   暂停跨度 %.1f px   差 %+.1f px（改前是 +18.9px）"
          % (_sp_idle, _sp_pause, _sp_pause - _sp_idle))
    print("     EMBER_HEAT = %.2f，暂停态与空闲同一个火形 —— 信号改由琥珀色圆环承担"
          % emb)
    print()
    print("  ② 暂停不放火星：`spark_field=False` 现在被 draw_campfire_qt 认（改前传的是")
    print("     None，会被当成「没传，新建默认的」，火星照放 18 个像素）。")
    with_sp = render(20.0, li_back, li_front, spark=flame.SparkField())
    no_sp = render(20.0, li_back, li_front, spark=False)
    print("     同一帧 [给 field] vs [spark_field=False] 的差异像素：%d 个"
          % count_diff(with_sp, no_sp))
    print("     （>0 = False 真的把它关掉了；改前这一行会直接 AttributeError）")
    print()
    print("  ③ 环绕热弧改成「不短于空闲段」之后（阈值 IDLE_ARC_DEG/SWEEP_DEG = %.4f）："
          % (IDLE_ARC_DEG / SWEEP_DEG))
    for h in (0.0, 0.5, 0.96, 1.0, 5.0, 20.0):
        frac = h / 100.0
        arc = IDLE_ARC_DEG if frac <= IDLE_ARC_DEG / SWEEP_DEG else SWEEP_DEG * frac
        print("       热度 %-6.2f → 弧长 %5.2f°%s"
              % (h, arc, "   ← 改前这里会缩到 1.30°" if h == 0.5 else ""))
    print("     单调不降 ✓（改前 0→2.50°、0.5→1.30°、1.0→2.60°：先缩后长）")
    print()
    print("  ④ 剩下唯一的**离散**量：火星颗数 n = int(round(2+7t))，7 个跳变点")
    print("     热度 2.97 / 12.83 / 25.34 / 39.69 / 55.49 / 72.51 / 90.60，")
    print("     新火星在满不透明度上出现（alpha=(1-k)^1.7×(0.30+0.70t)，k=0 取最大）。")
    print("     这是设计（火星本来就一闪一闪），量级也只有几个像素。")
    print()

    compose(rows, traj_by_rate, old_by_rate, per, frames)
    return 0


def count_diff(a, b):
    """两帧在 BOX 内明显不同的像素个数。"""
    ia = a.copy(BOX[0], BOX[1], BOX[2] - BOX[0], BOX[3] - BOX[1])
    ib = b.copy(BOX[0], BOX[1], BOX[2] - BOX[0], BOX[3] - BOX[1])
    ba = bytes(ia.constBits().asstring(ia.sizeInBytes()))
    bb = bytes(ib.constBits().asstring(ib.sizeInBytes()))
    n = 0
    for i in range(0, len(ba), 4):
        if (abs(ba[i] - bb[i]) + abs(ba[i + 1] - bb[i + 1])
                + abs(ba[i + 2] - bb[i + 2])) > 12:
            n += 1
    return n


def compose(rows, traj_by_rate, old_by_rate, per, frames):
    """四格：跨度曲线（冷端放大） / 引擎轨迹（改前改后） / 每 1% 热度的像素变化 / 原始帧。"""
    W, H = 1100, 1000
    out = Image.new("RGB", (W, H), (247, 247, 250))
    dr = ImageDraw.Draw(out)
    try:
        from PIL import ImageFont
        f_t = ImageFont.truetype(FONT, 21)
        f = ImageFont.truetype(FONT, 15)
        f2 = ImageFont.truetype(FONT, 13)
    except Exception:
        f_t = f = f2 = None
    dr.text((24, 12), "火焰「从小到大」的连续性实测 —— 突变在输入侧，映射侧是连续的",
            fill=(30, 30, 40), font=f_t)

    def panel(x0, y0, w1, h1, title, right=56, bottom=76):
        dr.rectangle([x0, y0, x0 + w1, y0 + h1], fill=(255, 255, 255),
                     outline=(210, 212, 220))
        dr.text((x0 + 12, y0 + 8), title, fill=(50, 50, 62), font=f)
        return x0 + 46, y0 + h1 - bottom, w1 - 46 - right, h1 - bottom - 24

    # ---- 面板 1：跨度 vs 热度（0~20 段放大） ----
    ox, oy, pw, ph = panel(24, 46, 516, 330, "① 火苗总跨度 vs 热度（px，低热段放大）")
    pts = [(ox + pw * h / 20.0, oy - ph * span / 70.0)
           for h, span, *_r in rows if h <= 20.0 + 1e-9]
    dr.line(pts, fill=(214, 122, 44), width=3)
    for h in (0, 5, 10, 15, 20):
        x = ox + pw * h / 20.0
        dr.line([x, oy, x, oy + 4], fill=(150, 150, 160))
        dr.text((x - 6, oy + 7), "%d" % h, fill=(120, 120, 132), font=f2)
    for s in (0, 20, 40, 60):
        y = oy - ph * s / 70.0
        dr.line([ox - 4, y, ox, y], fill=(150, 150, 160))
        dr.text((ox - 32, y - 8), "%d" % s, fill=(120, 120, 132), font=f2)
    x5 = ox + pw * 0.5 / 20.0
    dr.line([x5, oy - ph, x5, oy], fill=(220, 80, 80), width=1)
    dr.text((x5 + 8, oy - ph + 2), "旧下限 0.5 → 第一步 +5.4px\n新下限 0.01 → 第一步 +1.5px",
            fill=(200, 70, 70), font=f2)
    dr.text((ox, oy + 28), "映射本身连续、单调、无断点 —— 但冷端比中段陡 ~7 倍（复合幂次 0.54）",
            fill=(110, 110, 124), font=f2)
    dr.text((ox, oy + 46), "跨度 0→0.5 就 +5.4px、0.5→5 再 +19px；中段每 1% 只 +0.5px。",
            fill=(110, 110, 124), font=f2)

    # ---- 面板 2：引擎轨迹（改前 vs 改后）----
    ox2, oy2, pw2, ph2 = panel(
        552, 46, 524, 330, "② 引擎轨迹：固定 kpm 打字 120 秒（真实 HeatEngine）", right=82)

    def dashed(pts, color, width=1, dash=6):
        for i in range(0, max(0, len(pts) - 1), dash * 2):
            seg = pts[i:i + dash + 1]
            if len(seg) > 1:
                dr.line(seg, fill=color, width=width)

    RATEC = ((40, (120, 155, 205)), (60, (120, 155, 205)), (80, (120, 155, 205)),
             (84, (120, 155, 205)), (90, (230, 160, 50)), (120, (200, 110, 200)),
             (200, (220, 80, 80)), (300, (175, 60, 60)))
    for kpm, col in RATEC:                      # 改前：灰虚线
        dashed([(ox2 + pw2 * tt / 120.0, oy2 - ph2 * h / 100.0)
                for tt, h, _, _ in old_by_rate[kpm]], (208, 208, 214), 1, 8)
    for kpm, col in RATEC:                      # 本轮：实线
        dr.line([(ox2 + pw2 * tt / 120.0, oy2 - ph2 * h / 100.0)
                 for tt, h, _, _ in traj_by_rate[kpm]], fill=col, width=2)
    for kpm, col in ((90, (230, 160, 50)), (120, (200, 110, 200)), (200, (220, 80, 80))):
        pts = [(ox2 + pw2 * tt / 120.0, oy2 - ph2 * h / 100.0)
               for tt, h, _, _ in traj_by_rate[kpm]]
        dr.text((ox2 + pw2 + 6, pts[-1][1] - 8), "%d kpm" % kpm, fill=col, font=f2)
    dr.line([ox2, oy2, ox2 + pw2, oy2], fill=(150, 150, 160))
    dr.text((ox2 - 40, oy2 + 6), "0", fill=(120, 120, 132), font=f2)
    dr.text((ox2 - 40, oy2 - ph2 + 6), "100", fill=(120, 120, 132), font=f2)
    dr.text((ox2, oy2 + 8), "0s", fill=(120, 120, 132), font=f2)
    dr.text((ox2 + pw2 - 26, oy2 + 8), "120s", fill=(120, 120, 132), font=f2)
    dr.text((ox2, oy2 + 28), "灰虚线 = 改前：40~84 kpm 全程贴 0（火毫无反应），90 kpm 要等 56.6s",
            fill=(110, 110, 124), font=f2)
    dr.text((ox2, oy2 + 46), "实线 = 本轮：每个速率都在 1~2 秒内起跳，单帧最大跳 5.46px → 0.66px",
            fill=(110, 110, 124), font=f2)

    # ---- 面板 3：每 1% 热度的像素变化 ----
    ox3, oy3, pw3, ph3 = panel(
        24, 392, 1052, 296, "③ 每 1% 热度引起多少像素变化（火焰区平均绝对差）", right=34, bottom=64)
    rmax = max(r for *_x, r in per) or 1.0
    bw = pw3 / len(per)
    for i, (a, b, dv, rate) in enumerate(per):
        hgt = ph3 * min(1.0, rate / rmax)
        x = ox3 + i * bw
        dr.rectangle([x + 1, oy3 - hgt, x + bw - 2, oy3],
                     fill=(214, 92, 92) if a < 1.0 else (238, 176, 96))
        dr.text((x - 1, oy3 + 6), "%.0f" % a, fill=(120, 120, 132), font=f2)
    dr.text((ox3 - 40, oy3 - ph3 + 4), "%.2f" % rmax, fill=(120, 120, 132), font=f2)
    dr.text((ox3 - 40, oy3 + 6), "0", fill=(120, 120, 132), font=f2)
    dr.line([ox3, oy3, ox3 + pw3, oy3], fill=(150, 150, 160))
    for i, (a, b, dv, rate) in enumerate(per[:3]):
        dr.text((ox3 + i * bw - 4, oy3 - ph3 * (rate / rmax) - 18),
                "%.2f" % rate, fill=(200, 70, 70), font=f2)
    dr.text((ox3, oy3 + 26), "冷端（热度 0→1）每 1% 的像素变化是中段（40→50）的 ~7 倍 —— "
            "起步那一下的动静天生最大。", fill=(110, 110, 124), font=f2)
    dr.text((ox3, oy3 + 44), "修复前下限 0.5 → 起步一帧就吃掉 0.5 个热度（≈1.7 像素差）；"
            "现在下限 0.01，同一帧只有 ≈0.03。", fill=(110, 110, 124), font=f2)

    # ---- 面板 4：原始帧 ----
    y = 736
    dr.text((24, 710), "④ 原始帧（同一摇曳相位）—— 热度的每个台阶都对应这里的一帧；"
            "最右一格是「手动暂停」", fill=(50, 50, 62), font=f)
    thumbs = [(0.0, "热度 0（空闲）"), (1.0, "热度 1.0"), (5.0, "热度 5"),
              (20.0, "热度 20"), ("paused", "手动暂停（现在与空闲同形）")]
    for i, (key, label) in enumerate(thumbs):
        q = frames.get(key)
        if q is None:
            continue
        im = Image.open(_dump(q, HERE, key if isinstance(key, str) else key))
        im = im.convert("RGB").crop(BOX)
        im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        x = 24 + i * (im.width + 14)
        out.paste(im, (int(x), y))
        dr.text((int(x), y + im.height + 4), label,
                fill=(200, 70, 70) if key == "paused" else (90, 90, 102), font=f2)
    out.save(OUT)
    print("对照图 %s  %s" % (OUT.name, out.size))


def img_delta_median(per):
    vals = sorted(r for *_x, r in per[1:])
    return vals[len(vals) // 2]


def _dump(qimg, here, tag):
    if not isinstance(tag, str):
        tag = "%.1f" % tag
    path = here / ("_smooth_%s.png" % tag.replace(".", "_"))
    qimg.save(str(path), "PNG")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
