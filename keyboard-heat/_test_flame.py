"""篝火几何回归测试 —— 纯函数，不需要 PyQt6、不需要屏幕。

四条最有价值的断言，都是"改一行代码就会悄悄坏掉"的那种：

1. **柴堆不跟火苗缩放**。柴堆是零热度时的视觉锚点，一旦有人把它改回
   `span = w * 1.3`（火苗宽度），空闲时它就缩成看不见的一点 —— 界面看着像没启动。
   断言：热度 0 和热度 1 下柴堆端点必须逐像素相同。

2. **柴堆是"围拢"，不是"交叉"**。两根柴必须在中轴两边各据一侧、中间留出火口，
   而且左右镜像对称。这条一破就退回成用户否掉的 X 形交叉。
   断言：左柴最右点 < 中轴 < 右柴最左点，且两根柴的点集互为镜像。

3. **柴堆不出灶膛**。柴端的圆头和断面年轮是全堆最靠外的部分，画到灶膛外面
   就会压在圆环的内沿上；但也不能缩回去 —— 所以要同时验"不压"和"贴到边"。
   断言：把 UI 里那套半径公式抄过来，量每个端点到盘心的距离。

4. **火星不落到柴堆下面**。`SparkField` 是纯函数，位置全靠算的，
   把 base_y 的符号写反了照样能跑，只是火星往下飘。
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flame  # noqa: E402

OK = 0
BAD = 0


def eq(name, got, want):
    global OK, BAD
    if got == want:
        OK += 1
        print("  [PASS] %-46s %s" % (name, got))
    else:
        BAD += 1
        print("  [FAIL] %-46s got=%r want=%r" % (name, got, want))


def ok(name, cond, detail=""):
    """条件断言。detail 只在失败时打出来，免得日志被数字淹没。"""
    global OK, BAD
    if cond:
        OK += 1
        print("  [PASS] %-46s %s" % (name, detail))
    else:
        BAD += 1
        print("  [FAIL] %-46s %s" % (name, detail))


def lum(c):
    """感知亮度（Rec.601）。判"火够不够亮"要看这个，不是看 RGB 之和 ——
    纯橙 (255,160,0) 和暗红 (170,0,0) 的和差不多，亮度差了 3 倍。"""
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def pit_radius(d, thick_k=0.062):
    """UI 里算灶膛半径的那套公式 —— 现在只有 flame 一份，两版 UI 都调它。

    这里保留一个本地副本，是为了让"UI 真按这个公式画"这件事仍然被测试盯着：
    flame 改了公式而 UI 没跟着改，这条断言会失败。thick_k 默认取两版里更大的
    那个（Qt 0.062 > Tk 0.060），因为灶膛越小越容易露馅 —— 按最坏情况验。
    """
    thick = max(8.0, d * thick_k)
    radius = d / 2.0 - max(6.0, d * 0.045) - thick / 2.0
    return radius - thick / 2.0 - max(1.0, d * 0.008)


def _all_pts(lg):
    """一根柴的全部采样点（暗底 / 色带 / 受光面 / 沟纹 / 断面）。"""
    polys = [lg["shadow_pts"], lg["lit_pts"]]
    polys += [p for p, _ in lg["bands"]]
    polys += [p for p, _ in lg["streaks"]]
    for end in lg["ends"]:
        polys += [p for p, _ in end]
    return [pt for poly in polys for pt in poly]


def log_width(d, heat=0.0, style=None):
    """柴堆的横向实际宽度（含断面），用全部采样点的极值算。"""
    cx = d / 2.0
    pile = flame.log_pile(cx, flame.flame_base_y(cx, d), d, heat, (128, 64, 32),
                          style)
    xs = [p[0] for lg in pile for p in _all_pts(lg)]
    return max(xs) - min(xs)


def main():
    print("== 1. 柴堆是锚点，不跟火苗缩放 ==")
    d = 190.0
    base_y = flame.flame_base_y(d / 2.0, d)
    low = flame.log_pile(d / 2.0, base_y, d, 0.0, flame.flame_colors(0.0)[1])
    high = flame.log_pile(d / 2.0, base_y, d, 1.0, flame.flame_colors(1.0)[1])
    eq("柴堆数量", len(low), 2)
    same = all(a["shadow_pts"] == b["shadow_pts"] for a, b in zip(low, high))
    ok("热度 0 与 1 的柴堆几何完全一致", same)
    # 布局必须是"围拢"而不是"交叉"：左柴的全部点在中轴左边、右柴在右边，
    # 中间留出一道火口。这条一破就退回成 X 形交叉了 —— 那是用户明确否掉的方案。
    cx = d / 2.0

    def mouth(pile):
        left = [p[0] for p in _all_pts(pile[0])]
        right = [p[0] for p in _all_pts(pile[1])]
        return cx - max(left), min(right) - cx

    ml, mr = mouth(low)
    ok("两根柴不交叉（塔尖留缝）", ml > 0 and mr > 0,
       "左隙 %.1fpx / 右隙 %.1fpx" % (ml, mr))
    # 左右镜像对称：两根柴是同一根柴照出来的
    mir_l = sorted((round(cx - x, 4), round(y, 4)) for x, y in _all_pts(low[0]))
    mir_r = sorted((round(x - cx, 4), round(y, 4)) for x, y in _all_pts(low[1]))
    ok("左右两根柴镜像对称", mir_l == mir_r)
    # 柴尖朝上朝内 —— 围拢的方向感：左柴最靠内的点必须比最靠外的点高
    pts_l = _all_pts(low[0])
    outer = min(pts_l, key=lambda p: p[0])
    inner = max(pts_l, key=lambda p: p[0])
    ok("柴尖朝上朝内（是围拢不是平摊）", outer[1] - inner[1] > d * 0.04,
       "内侧高 %.1fpx" % (outer[1] - inner[1]))
    w190 = log_width(d)
    ok("柴堆宽度不随热度变",
       abs(log_width(d, 1.0) - w190) < 1e-9,
       "%.1fpx (%d%% 盘宽)" % (w190, round(w190 / d * 100)))

    print("== 2. 柴堆贴着圆环内沿，但不压上去 ==")
    for size in (120.0, 176.0, 190.0, 240.0):
        eq("flame.pit_radius 与 UI 公式一致 d=%d" % size,
           round(flame.pit_radius(size), 6), round(pit_radius(size), 6))
    eq("圆环笔宽常量与 UI 公式一致", flame.RING_THICK_K, 0.062)
    # 跨度是 log_endpoints() 从灶膛半径推出来的（"贴着圆环内沿"），所以这条
    # 既验"没压到圆环"，也验"真的够到边了" —— 只验前者的话，把柴堆改小也能过。
    # 注意现在量的是**全部采样点**（含断面年轮和圆头笔尖），圆头和断面沿轴向
    # 还会再伸出一段，是整个柴堆最靠外的部分。
    for size in (120.0, 150.0, 176.0, 190.0, 240.0, 280.0):
        cx = cy = size / 2.0
        by = flame.flame_base_y(cy, size)
        ring_in = flame.ring_inner_radius(size)
        for pair in flame.LOG_PAIRS:
            for style in flame.LOG_STYLES:
                worst = 0.0
                for heat in (0.0, 0.5, 1.0):
                    for lg in flame.log_pile(cx, by, size, heat, (128, 64, 32),
                                             style, pair=pair):
                        for x, y in _all_pts(lg):
                            worst = max(worst, math.hypot(x - cx, y - cy))
                ok("d=%d %s/%s 不压圆环" % (size, pair, style), worst <= ring_in,
                   "最远 %.1fpx / 环内沿 %.1fpx (%.0f%%)"
                   % (worst, ring_in, worst / ring_in * 100))
                ok("d=%d %s/%s 柴尾贴到边（≥ 88%% 环内沿）" % (size, pair, style),
                   worst >= ring_in * 0.88, "%.0f%%" % (worst / ring_in * 100))
    ratio = log_width(176.0) / 176.0
    ok("后对柴堆宽度占盘宽 48%~62%（要够大，但不能横穿整个盘）",
       0.48 <= ratio <= 0.62, "%d%%" % round(ratio * 100))
    # 柴堆和火苗要"配得上"：满热火苗多宽，柴堆至少要有它的八成
    h = flame.flame_height(1.0, 190.0 * flame.FLAME_MAX_H_K)
    flame_w = flame.flame_width(h, 1.0)
    ok("柴堆宽度 ≥ 满热火苗宽度的 80%（不然像火柴架着篝火）",
       log_width(190.0) >= flame_w * 0.80,
       "柴 %.0fpx / 火 %.0fpx" % (log_width(190.0), flame_w))
    # Tk 的画素是按 LOG_ITEMS_MAX 预建的（前后各一套），任何样式都不许超
    for pair in flame.LOG_PAIRS:
        for style in flame.LOG_STYLES:
            pile = flame.log_pile(95.0, flame.flame_base_y(95.0, 190.0), 190.0,
                                  0.5, (128, 64, 32), style, pair=pair)
            ok("%s/%s 绘制块数 ≤ LOG_ITEMS_MAX" % (pair, style),
               len(flame.log_draw_list(pile)) <= flame.LOG_ITEMS_MAX,
               "%d / %d" % (len(flame.log_draw_list(pile)), flame.LOG_ITEMS_MAX))

    print("== 2b. 前对柴：画在火焰图层之上、柴尖交错的那一对 ==")
    d = 190.0
    cx = cy = d / 2.0
    by = flame.flame_base_y(cy, d)
    back = flame.log_pile(cx, by, d, 0.5, (128, 64, 32), "charred")
    front = flame.log_pile(cx, by, d, 0.5, (128, 64, 32), "charred", pair="front")
    eq("前对也是两根", len(front), 2)
    f0 = flame.log_pile(cx, by, d, 0.0, (128, 64, 32), "charred", pair="front")
    f1 = flame.log_pile(cx, by, d, 1.0, (255, 128, 64), "charred", pair="front")
    ok("前对几何也不随热度变",
       all(a["shadow_pts"] == b["shadow_pts"] for a, b in zip(f0, f1)))
    (b0, t0) = flame.log_endpoints(d, "back")[0]
    (b1, t1) = flame.log_endpoints(d, "front")[0]
    ab = math.degrees(math.atan2(t0[1] - b0[1], t0[0] - b0[0]))
    af = math.degrees(math.atan2(t1[1] - b1[1], t1[0] - b1[0]))
    ok("前后两对姿态不同（角度差 ≥ 12°）", abs(ab - af) >= 12.0,
       "后对 %.1f° / 前对 %.1f°" % (ab, af))
    ok("前对比后对更平（横卧感）", abs(af) < abs(ab))
    ok("前对柴尖比后对低（一高一低才有前后）", t1[1] > t0[1],
       "前尖 y=%.1f / 后尖 y=%.1f（相对灶膛圆心）" % (t1[1], t0[1]))
    mir_l = sorted((round(cx - x, 4), round(y, 4)) for x, y in _all_pts(back[0]))
    mir_r = sorted((round(x - cx, 4), round(y, 4)) for x, y in _all_pts(back[1]))
    ok("后对左右镜像对称", mir_l == mir_r)
    # 前对柴尖要**交错**：左柴尖越过中轴搭到右边、右柴尖搭到左边，且高度错开 ——
    # 参考照片里就是这种随手搭的十字，完美对称的 X 一眼假
    ok("前对柴尖交错（越过中轴）",
       flame.log_endpoints(d, "front")[0][1][0] > 0
       and flame.log_endpoints(d, "front")[1][1][0] < 0,
       "左尖 x=%+.1f / 右尖 x=%+.1f"
       % (flame.log_endpoints(d, "front")[0][1][0],
          flame.log_endpoints(d, "front")[1][1][0]))
    tl = flame.log_endpoints(d, "front")[0][1][1]
    tr = flame.log_endpoints(d, "front")[1][1][1]
    ok("前对柴尖高度错开（不是对称 X）", abs(tl - tr) > d * 0.01,
       "高差 %.1fpx" % abs(tl - tr))

    def seg_intersects(p0, p1, q0, q1):
        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        d1, d2 = cross(q0, q1, p0), cross(q0, q1, p1)
        d3, d4 = cross(p0, p1, q0), cross(p0, p1, q1)
        return d1 * d2 < 0 and d3 * d4 < 0

    ok("前对两根柴真的相交（不是并排）",
       seg_intersects(flame.log_endpoints(d, "front")[0][0],
                      flame.log_endpoints(d, "front")[0][1],
                      flame.log_endpoints(d, "front")[1][0],
                      flame.log_endpoints(d, "front")[1][1]))
    # 背光：同一根柴、同一热度，前对的木身必须比后对暗 —— 不暗就"贴"在火上了
    cb = back[0]["bands"][0][1]
    cf = front[0]["bands"][0][1]
    ok("前对木身比后对暗（背光）", sum(cf) < sum(cb), "%s vs %s" % (cf, cb))
    fl = flame.log_pile(cx, by, d, 0.5, (128, 64, 32), "charred",
                        pair="front")[0]["lit_color"]
    bl = back[0]["lit_color"]
    ok("前对受光面偏暖（火烤出来的边，不是天光）", fl[0] > fl[2], "%s vs %s" % (fl, bl))

    print("== 2c. 端向柴：最前面一根，遮住火焰平底边 ==")
    # 火焰轮廓的底边（outline 在 base_y 的直线）会从柴塔缝隙漏出来。这根端向柴
    # 画在最前面，要把那段直线的中段盖住，且自身不能压到圆环、几何不随热度变。

    def fore_pts(fore):
        polys = [fore["shadow_pts"], fore["tube_pts"], fore["far_pts"],
                 fore["face_pts"]]
        polys += [p for p, _ in fore["rings"]]
        return [pt for poly in polys for pt in poly]

    f0 = flame.log_fore(cx, by, d, 0.0, (128, 64, 32), "charred")
    f1 = flame.log_fore(cx, by, d, 1.0, (255, 128, 64), "charred")
    ok("端向柴几何不随热度变",
       all(a == b for a, b in zip(fore_pts(f0), fore_pts(f1))))
    eq("端向柴绘制块数固定为 6", len(flame.fore_draw_list(f0)), 6)
    ok("端向柴块数 ≤ FORE_ITEMS_MAX",
       len(flame.fore_draw_list(f0)) <= flame.FORE_ITEMS_MAX)
    # 不压圆环（它在灶膛下侧中央，正常也不会超，但这是守住"别往外扩"的底线）
    for size in (120.0, 176.0, 190.0, 240.0, 280.0):
        s_cx = s_cy = size / 2.0
        s_by = flame.flame_base_y(s_cy, size)
        ring_in = flame.ring_inner_radius(size)
        worst = 0.0
        for heat in (0.0, 0.5, 1.0):
            for x, y in fore_pts(flame.log_fore(s_cx, s_by, size, heat,
                                                (128, 64, 32), "charred")):
                worst = max(worst, math.hypot(x - s_cx, y - s_cy))
        ok("d=%d 端向柴不压圆环" % size, worst <= ring_in,
           "最远 %.1fpx / 环内沿 %.1fpx (%.0f%%)"
           % (worst, ring_in, worst / ring_in * 100))
    # 关键：端向柴要真的盖住火焰平底边（base_y 直线）的中段
    for heat in (0.0, 0.5, 1.0):
        h = flame.flame_height(heat, d * flame.FLAME_MAX_H_K)
        w = flame.flame_width(h, heat)
        fore = flame.log_fore(cx, by, d, heat, (128, 64, 32), "charred")
        pts = fore_pts(fore)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        # 横向要罩住火焰底边中段（至少 ±0.6 半宽）
        ok("热度 %.1f 端向柴横向罩住火焰底边中段" % heat,
           (cx - min(xs)) >= w * 0.6 and (max(xs) - cx) >= w * 0.6,
           "端向 ±%.0fpx / 火半宽 %.0fpx" % (min(max(xs) - cx, cx - min(xs)), w))
        # 纵向：最上沿要伸到 base_y 之上（探入火），最下沿落到 base_y 之下
        ok("热度 %.1f 端向柴上端探入火焰底" % heat,
           min(ys) < by, "最上沿 y=%.1f / 火根 y=%.1f" % (min(ys), by))
        ok("热度 %.1f 端向柴下端沉到火根之下" % heat,
           max(ys) > by, "最下沿 y=%.1f / 火根 y=%.1f" % (max(ys), by))

    print("== 2d. 中对柴：填后对与前垛之间的空档 ==")
    # 低火时火焰缩成一小簇，后对（高架的 Λ）和前面那垛柴之间会露出一块空档，
    # 塔看着像悬着的。中对的柴尾角介于前后对之间、柴尖在中轴附近收拢。
    mid = flame.log_pile(cx, by, d, 0.5, (128, 64, 32), "charred", pair="mid")
    eq("中对也是两根", len(mid), 2)
    m0 = flame.log_pile(cx, by, d, 0.0, (128, 64, 32), "charred", pair="mid")
    m1 = flame.log_pile(cx, by, d, 1.0, (255, 128, 64), "charred", pair="mid")
    ok("中对几何不随热度变",
       all(a["shadow_pts"] == b["shadow_pts"] for a, b in zip(m0, m1)))
    ty_b = flame.log_endpoints(d, "back")[0][1][1]
    ty_m = flame.log_endpoints(d, "mid")[0][1][1]
    ty_f = flame.log_endpoints(d, "front")[0][1][1]
    ok("中对柴尖高度落在后对与前对之间（正好填空档）",
       ty_b < ty_m < ty_f,
       "后 %.1f < 中 %.1f < 前 %.1f（相对灶膛圆心）" % (ty_b, ty_m, ty_f))
    ok("中对柴尖收拢但不交叉（留细缝）",
       flame.log_endpoints(d, "mid")[0][1][0] < 0
       and flame.log_endpoints(d, "mid")[1][1][0] > 0)
    deg_m = flame.LOG_MID_DEG
    ok("中对柴尾角介于前后对之间", flame.LOG_FRONT_DEG < deg_m < flame.LOG_BUTT_DEG,
       "%.0f° (前 %.0f° / 后 %.0f°)" % (deg_m, flame.LOG_FRONT_DEG,
                                        flame.LOG_BUTT_DEG))

    def _pip(x, y, poly):
        inside = False
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y):
                xin = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if x < xin:
                    inside = not inside
        return inside

    def pile_void(d):
        """低火时柴堆（全对+端向柴）在塔身区域的最大纵向空洞（相对盘径）。"""
        s_cx = s_cy = d / 2.0
        s_by = flame.flame_base_y(s_cy, d)
        oy = s_by - d * flame.FLAME_BASE_Y_K
        polys = []
        for pair in flame.LOG_PAIRS:
            for lg in flame.log_pile(s_cx, s_by, d, 0.0, (128, 64, 32),
                                     "charred", pair=pair):
                polys.append(lg["shadow_pts"])
                polys += [p for p, _ in lg["bands"]]
        fore = flame.log_fore(s_cx, s_by, d, 0.0, (128, 64, 32), "charred")
        polys += [fore["shadow_pts"], fore["tube_pts"], fore["far_pts"],
                  fore["face_pts"]]
        worst = 0.0
        for fx in (-0.08, -0.04, 0.0, 0.04, 0.08):
            x = s_cx + fx * d
            ys = sorted(y for y in (oy + 0.03 * d
                                    + (0.27 - 0.03) * d * i / 300
                                    for i in range(301))
                        if any(_pip(x, y, p) for p in polys))
            for a, b in zip(ys, ys[1:]):
                worst = max(worst, b - a)
        return worst / d

    ok("低火时柴塔无大空洞（中对把空档填上）", pile_void(190.0) < 0.015,
       "最大纵向空洞 %.1f%% 盘径" % (pile_void(190.0) * 100))
    ok("小盘上同样成立", pile_void(120.0) < 0.015,
       "最大纵向空洞 %.1f%% 盘径" % (pile_void(120.0) * 100))

    print("== 3. 热度 → 火苗 ==")
    mx = 100.0
    h0 = flame.flame_height(0.0, mx)
    h1 = flame.flame_height(1.0, mx)
    eq("满热时火苗顶到上限", round(h1, 3), mx)
    eq("零热度的高度就是 FLAME_IDLE_K", round(h0, 6),
       round(flame.FLAME_IDLE_K * mx, 6))
    # 空闲态的火是唯一的火 —— 太小就压不住柴堆（用户原话："木头太大、火焰太小"）。
    # 下限 0.12 是"还能看出是一团火"，上限 0.22 是"别把低热档挤掉"。
    ok("零热度的余烬火够大（撑得住柴堆）", 0.12 * mx <= h0 <= 0.22 * mx,
       "%.1fpx = 上限的 %.0f%%" % (h0, h0 / mx * 100))
    ladder = [flame.flame_height(i / 10.0, mx) for i in range(11)]
    ok("火苗高度随热度单调不减", all(b >= a for a, b in zip(ladder, ladder[1:])))
    ok("中低段增幅比高段明显",
       (ladder[5] - ladder[1]) > (ladder[10] - ladder[6]),
       "%.1f vs %.1f" % (ladder[5] - ladder[1], ladder[10] - ladder[6]))
    ok("满热火苗的宽高比 ≥ 0.5（不是一根蜡烛）",
       flame.flame_width(h1, 1.0) / h1 >= 0.5,
       "%.2f" % (flame.flame_width(h1, 1.0) / h1))
    ok("低热火苗相对更宽（不是被拉长的同一形状）",
       flame.flame_width(flame.flame_height(0.2, mx), 0.2)
       / flame.flame_height(0.2, mx) > flame.flame_width(h1, 1.0) / h1)

    print("== 3b. 火苗不出灶膛 / 日常热度下够大 ==")
    for size in (120.0, 176.0, 190.0, 240.0):
        pr = flame.pit_radius(size)
        cy = size / 2.0
        worst = 0.0
        for heat in (0.0, 0.3, 0.6, 1.0):
            h = flame.flame_height(heat, size * flame.FLAME_MAX_H_K)
            w = flame.flame_width(h, heat)
            by = flame.flame_base_y(cy, size)
            # 轮廓上最外侧的点：半宽和摇曳都在 outline 里算好了，直接取样
            for x, y in flame.outline(cy, by, h, w, 1.3, 11, 1.0, samples=20):
                worst = max(worst, math.hypot(x - cy, y - cy))
        ok("d=%d 火苗（含摇曳）留在灶膛内" % size, worst <= pr,
           "最远 %.1fpx / 灶膛 %.1fpx (%.0f%%)" % (worst, pr, worst / pr * 100))
    # "日常热度"按 40% 算 —— 它是办公时最常见的读数，不能只有一小撮
    h40 = flame.flame_height(flame.fire_heat(0.40), 190.0 * flame.FLAME_MAX_H_K)
    ok("40% 热度时火苗不低于盘高的 1/3", h40 >= 190.0 / 3.0, "%.1fpx" % h40)

    print("== 4. 热度 → 颜色（由暗红走到亮黄）==")
    lo = flame.flame_colors(0.0)
    hi = flame.flame_colors(1.0)
    ok("低热的芯也不白", sum(lo[2]) < sum(hi[2]), "%s vs %s" % (lo[2], hi[2]))
    ok("外焰比焰芯暗", sum(hi[0]) < sum(hi[2]), "%s < %s" % (hi[0], hi[2]))
    ok("低温火偏红（R 远大于 B）", lo[1][0] > lo[1][2] * 2, str(lo[1]))
    # 原来是 `min(hi[2]) > 170`（"接近白"）。_CORE_TINT 调暖之后 B 通道落到 160 ——
    # 但"白"本来就不该由某个通道的绝对值定义，而要看**相对另两层**：最亮 + 最淡。
    # 见 _CORE_TINT 的注释（黑体色阶里没有绿，"绿"是低饱和被全饱和橙黄包围的对比）。
    ok("高温焰芯是三层里最亮的（白）",
       lum(hi[2]) > lum(hi[1]) and lum(hi[2]) > lum(hi[0]),
       "焰芯 %.0f > 中焰 %.0f / 外焰 %.0f"
       % (lum(hi[2]), lum(hi[1]), lum(hi[0])))
    ok("高温焰芯是三层里最淡的（最接近白，不是饱和黄）",
       (hi[2][0] - hi[2][2]) / float(hi[2][0])
       < (hi[1][0] - hi[1][2]) / float(hi[1][0]),
       "焰芯 R−B/R %.2f < 中焰 %.2f"
       % ((hi[2][0] - hi[2][2]) / float(hi[2][0]),
          (hi[1][0] - hi[1][2]) / float(hi[1][0])))
    # 三段要拉开体积感 —— 但在有火可看的档位上要求，冷态焰芯本来就该"没有芯"
    for heat in (0.3, 0.6, 1.0):
        c = flame.flame_colors(heat)
        ok("热度 %.0f%% 三段颜色互不相同" % (heat * 100),
           len({c[0], c[1], c[2]}) == 3, str(c))
    # 曾经是 `冷态焰芯 == lo[1]`（"余烬没有明亮的芯"）。加了 _CORE_HUE_BUMP 之后
    # 空闲的芯**确实比中焰亮**，但那是有意的 —— 用户要"火更亮"。要拦的性质换成
    # 了"这份亮是从哪儿来的"：必须是**色温抬上去的**（沿色阶往上走，暖色的饱和度
    # 还在），不能是**往白里混**混出来的 —— 后者正是早先那块"灰水滴" (111,75,67)
    # 的成因，它的 R-B 只有 44。
    ok("冷态焰芯比中焰亮（灼热的芯）", sum(lo[2]) > sum(lo[1]),
       "core %s 和 %d > mid %s 和 %d" % (lo[2], sum(lo[2]), lo[1], sum(lo[1])))
    ok("冷态焰芯的亮来自色温（R-B ≥ 120，不是混白发灰）",
       lo[2][0] - lo[2][2] >= 120,
       "R-B %d，芯 %s" % (lo[2][0] - lo[2][2], str(lo[2])))
    ok("满热的中焰仍是验收过的那一档", hi[1] == (235, 206, 99), str(hi[1]))
    # 满热**焰芯**本轮被刻意调暖（用户："最前面那层有点绿，要更偏黄+白"，
    # 见 _CORE_TINT / _L3_KEEP_UP）。旧的钉死值 (249,237,186) 不适用了，
    # 但换掉它要拦的**性质**得留着：暖意（R−G）必须真抬上去 —— "绿"就是 R−G
    # 太小、一块低饱和灰米色被全饱和橙黄包围读成中性灰。
    # 亮度侧（"白"不许丢）由上面"焰芯是三层里最亮的"那条守着。
    ok("满热焰芯被调暖（R−G 抬高，抗「灰/绿」）",
       hi[2][0] - hi[2][1] >= 18,
       "R−G %d（旧值 %d）" % (hi[2][0] - hi[2][1], 249 - 237))
    # 满热**外焰**本轮被刻意提亮（用户："亮度还是不太好…第一层更白更黄"，
    # 见 _L1_EDGE / _L1_KEEP_UP）。旧的钉死值 (175,145,69) 已经不适用，
    # 但换掉它拦的**性质**要留着：提亮之后外焰仍必须比中焰暗，否则"外圈先暗、
    # 芯子最亮"的体积线索就没了 —— 那是三层结构存在的理由。
    ok("满热外焰被提亮（比旧值亮）", lum(hi[0]) > lum((175, 145, 69)),
       "%s lum %.0f > 旧值 lum %.0f" % (hi[0], lum(hi[0]), lum((175, 145, 69))))
    ok("满热外焰虽被提亮、仍比中焰暗（体积线索还在）", lum(hi[0]) < lum(hi[1]),
       "%.0f < %.0f" % (lum(hi[0]), lum(hi[1])))
    ok("满热外焰提亮后饱和度不降（R−B 不许变小）",
       hi[0][0] - hi[0][2] >= 105,
       "R−B %d（旧值 %d）" % (hi[0][0] - hi[0][2], 175 - 69))

    print("== 4b. 焰芯提白随热度收放（冷态不许发灰）==")
    ok("满热的提白折扣 = 1（旺火零改动）", flame.flame_core_lift_k(1.0) == 1.0)
    ok("冷态的提白折扣收到下限",
       abs(flame.flame_core_lift_k(0.0) - flame._CORE_LIFT_MIN) < 1e-9,
       "%.3f" % flame.flame_core_lift_k(0.0))
    ok("折扣随热度单调不降",
       all(flame.flame_core_lift_k(i / 20.0) <= flame.flame_core_lift_k((i + 1) / 20.0)
           for i in range(20)))
    # 焰芯图层根部色 = _lift(core, 0.62 * k)。冷态那一个曾经是 (200,187,184) 的
    # 灰白（R-B 只有 16）—— 柴堆交叉点上冒出一块"灰水滴"，锚点抬上来之后完全暴露。
    # 判据用 R 通道的压倒性（r-b）而不是亮度：25% 热度已经是真在烧的火焰，亮没问题，
    # 但不能"发灰"。
    for heat in (0.0, 0.05, 0.10, 0.25, 0.5):
        _o, _m, core = flame.flame_colors(heat)
        rgb = flame._lift(core, 0.62 * flame.flame_core_lift_k(heat))
        ok("热度 %.0f%% 焰芯根部仍偏红（不发灰）" % (heat * 100),
           rgb[0] - rgb[2] >= 30 and rgb[0] > rgb[1] >= rgb[2],
           "根部色 %s  R-B %d" % (rgb, rgb[0] - rgb[2]))
    # 这条以前判的是"绝对亮度 < 220" —— 那是在"冷态越暗越好"的年代写的。
    # 用户要求空闲再亮一些之后，冷态焰芯根部是 (194,99,19)：**亮，但不灰**
    # （R-B = 175）。真正要拦的从来是"灰"——旧值 (200,187,184) 的毛病是三个
    # 通道挤在一起（R-B 只有 16），看着像柴堆上的一块"灰水滴"。所以判据改看
    # 饱和度，不再看亮度。
    _cc = flame._lift(flame.flame_colors(0.0)[2],
                      0.62 * flame.flame_core_lift_k(0.0))
    ok("冷态焰芯根部不是灰（旧值 (200,187,184)，R-B 仅 16）",
       _cc[0] - _cc[2] >= 100, "根部色 %s  R-B %d" % (_cc, _cc[0] - _cc[2]))

    print("== 4c. 空闲亮度：色阶抬升 + 渐变压暗折扣（冷态不许漆黑）==")
    # 用户抱怨"初始状态完全是一团漆黑"。归因是两件事叠在一起：
    #   ① 色阶起点 _ramp(0) = (49,0,0)（900K 余烬，物理没错但读不出在烧）
    #   ② 纵向渐变的"尖端冷却"是照满热高度定的，空闲火焰只有 ~22px 高，
    #      露在柴堆上面的那半团正好是压到最黑的一段
    # 下面把两个折扣的两端都钉死，防止以后被顺手改回去。
    ok("色阶位置 t=0 抬到 _IDLE_RAMP_POS",
       abs(flame._ramp_pos(0.0) - flame._IDLE_RAMP_POS) < 1e-9,
       "%.3f" % flame._ramp_pos(0.0))
    ok("色阶位置 t=1 仍恒等（满热不动）", flame._ramp_pos(1.0) == 1.0)
    # 它**不是**全局单调的：抬升幅度 K 加到 0.52 之后，t=0 处的导数 1-nK 变负，
    # 曲线在 19% 附近出现一个浅谷（(189,86,0) → (179,70,0)，落差 10%）。这是
    # "只抬冷端、不抬中热"的数学必然 —— 要消灭它就得把中低热一起抬上去。
    # 所以分两段判：中高段必须单调不降（火不会越烧越暗），空闲段只限回落幅度。
    _vs = [flame._ramp_pos(h / 100.0) for h in range(0, 101, 5)]
    ok("色阶位置在 25% 热度以上单调不降",
       all(b >= a for a, b in zip(_vs[5:], _vs[6:])),
       "25%% → %.3f，100%% → %.3f" % (_vs[5], _vs[-1]))
    _dip = min(_vs[1:5]) / _vs[0]
    ok("空闲段（5~20%）的回落不超过 15%", _dip >= 0.85,
       "低谷仅剩 %.1f%%（%.3f vs %.3f）" % (_dip * 100, min(_vs[1:5]), _vs[0]))
    # 曾经是"中热（50%）的色阶位置几乎不动"（阈值 0.08）。K 从 0.52 抬到 0.74
    # 之后这条**在数学上没法再成立**：单调曲线在 t=0 高、在 t=1 回到 1，中间压不
    # 回原样（见 _IDLE_RAMP_POS 的推导）。要拦的性质换成两条更硬的：
    #   1. **整段单调不降** —— "越打字火越暗"绝对不许出现（上面那条只覆盖 5~20%）
    #   2. **旺火仍明显更亮** —— 中热不能顶到接近满热的颜色，否则"火旺"就只剩
    #      尺寸一个表达了
    _allv = [flame._ramp_pos(i / 200.0) for i in range(201)]
    ok("色阶位置整段单调不降（0~100% 全扫）",
       all(b >= a - 1e-9 for a, b in zip(_allv, _allv[1:])),
       "最小步进 %+.6f（> 0 即全程不回落）"
       % min(b - a for a, b in zip(_allv, _allv[1:])))
    ok("旺火仍比中热明显更亮（色阶留白 ≥ 0.15）",
       flame._ramp_pos(1.0) - flame._ramp_pos(0.5) >= 0.15,
       "100%% %.3f − 50%% %.3f = %.3f"
       % (flame._ramp_pos(1.0), flame._ramp_pos(0.5),
          flame._ramp_pos(1.0) - flame._ramp_pos(0.5)))
    ok("空闲底色不再是漆黑（旧值 (49,0,0)）",
       lo[1][0] >= 100 and lo[1][1] >= 15, str(lo[1]))
    # 用户第二次要求"再亮一些"之后钉的新下限。旧值 (133,23,0) 是第一次提亮的
    # 结果，用户看了还是觉得不够。
    ok("空闲底色足够亮（第二次提亮后 ≥ (180,75,0)）",
       lo[1][0] >= 180 and lo[1][1] >= 75, str(lo[1]))
    ok("满热的底色逐位没变", hi[1] == (235, 206, 99), str(hi[1]))

    # ---- 第三次提亮（用户："亮度还是不太行"）新开的两个冷端旋钮 ----
    #
    # 这一轮先量后调，量到两件事：空闲时**可见的**只有渐变的 0.11~1.0 段（下半
    # 段被前景柴堆挡住），而渐变在 0.55 处就换成最暗的尖端色；而色阶上 0.75 那儿
    # 明明有 lum 159 的亮橙，冷端一直没走到。
    # 所以把转折点和焰芯都往亮处推 —— 两个都**只在冷端生效**，满热必须恒等。
    ok("渐变转折点：满热 = 常量（逐像素不变）",
       flame._grad_tip_stop(1.0) == flame._GRAD_TIP_STOP,
       "%.3f" % flame._grad_tip_stop(1.0))
    ok("渐变转折点：冷态 = 常量 + 豁免（可见段基本回到根部色）",
       abs(flame._grad_tip_stop(0.0)
           - (flame._GRAD_TIP_STOP + flame._GRAD_TIP_COLD_RELIEF)) < 1e-9,
       "%.3f" % flame._grad_tip_stop(0.0))
    ok("渐变转折点随热度单调不升（越热越早转尖色，且永不过 0.95）",
       all(flame._grad_tip_stop(i / 20.0) >= flame._grad_tip_stop((i + 1) / 20.0)
           for i in range(20)) and flame._grad_tip_stop(0.0) <= 0.95,
       "冷 %.2f → 热 %.2f" % (flame._grad_tip_stop(0.0),
                              flame._grad_tip_stop(1.0)))
    ok("焰芯加温：满热 = 0（逐像素不变）", flame._core_hue_bump(1.0) == 0.0)
    ok("焰芯加温：冷态 = 常量，且随热度单调不增",
       abs(flame._core_hue_bump(0.0) - flame._CORE_HUE_BUMP) < 1e-9
       and all(flame._core_hue_bump(i / 20.0) >= flame._core_hue_bump((i + 1) / 20.0)
               for i in range(20)),
       "冷 %.3f" % flame._core_hue_bump(0.0))
    # 端到端的一条：空闲时**露出来的**三层火，最暗的一层也得够亮（外焰尖端），
    # 最亮的一处要达到 lum 150 以上。这两个数就是"火看着亮不亮"的判据本身。
    _sk0 = flame.flame_shade_k(0.0)
    _o0, _m0, _c0 = flame.flame_colors(0.0)
    _visible = (flame._lift(_o0, 0.06), flame._soft_shade(_o0, 0.48, _sk0),
                flame._lift(_c0, 0.02), flame._soft_shade(_m0, 0.70, _sk0),
                flame._lift(_c0, 0.62 * flame.flame_core_lift_k(0.0)),
                flame._soft_shade(_c0, 0.52, _sk0))
    ok("空闲最亮处 ≥ lum 150（火真的亮起来了）",
       max(lum(c) for c in _visible) >= 150,
       "最亮 %s lum %.0f" % (max(_visible, key=lum), max(lum(c) for c in _visible)))
    ok("空闲最暗的可见层 ≥ lum 110（外焰尖端不发闷）",
       min(lum(c) for c in _visible) >= 110,
       "最暗 %s lum %.0f" % (min(_visible, key=lum), min(lum(c) for c in _visible)))

    # 外焰的压暗量：
    #   满热 = 旧公式 − _L1_EDGE（本轮**刻意**减轻 —— 少混暗红是"更黄"最值钱的
    #          一招，亮度和饱和度同向走，见 _L1_EDGE）
    #   冷态 = 0.50 − _EDGE_MIX_COLD_RELIEF，**不受 _L1_EDGE 影响**：权重
    #          _l12_weight(0) = 0，已验收的空闲观感一个像素不动。
    # 它非单调（冷态 0.09 → 中热 ~0.36 → 满热 0.16），所以只钉两端、不钉单调。
    ok("外焰压暗量：满热 = 旧公式 − _L1_EDGE",
       abs(flame._edge_mix_k(1.0) - (0.50 - 0.18 - flame._L1_EDGE)) < 1e-9,
       "%.3f（_L1_EDGE %.2f）" % (flame._edge_mix_k(1.0), flame._L1_EDGE))
    ok("外焰压暗量：冷态 = 0.50 − _EDGE_MIX_COLD_RELIEF（第 1/2 层旋钮豁免冷端）",
       abs(flame._edge_mix_k(0.0) - (0.50 - flame._EDGE_MIX_COLD_RELIEF)) < 1e-9,
       "%.3f（豁免 %.2f）" % (flame._edge_mix_k(0.0),
                            flame._EDGE_MIX_COLD_RELIEF))

    ok("渐变压暗折扣 t=1 = 1（旺火零改动）", flame.flame_shade_k(1.0) == 1.0)
    ok("渐变压暗折扣 t=0 = 下限",
       abs(flame.flame_shade_k(0.0) - flame._COLD_SHADE_MIN_K) < 1e-9,
       "%.3f" % flame.flame_shade_k(0.0))
    ok("渐变压暗折扣随热度单调不降",
       all(flame.flame_shade_k(i / 20.0) <= flame.flame_shade_k((i + 1) / 20.0)
           for i in range(20)))
    # 满热时 _soft_shade 必须退化成 _shade —— "满热逐像素不变"的落点就在这。
    ok("_soft_shade 在 k=1 退化成 _shade",
       all(flame._soft_shade(c, base, 1.0) == flame._shade(c, base)
           for c, base in ((lo[0], 0.48), (lo[1], 0.70), (lo[2], 0.52),
                           (hi[0], 0.48), (hi[1], 0.70), (hi[2], 0.52))))
    # 可见层渐变**顶端**的亮度。中焰层面积最大，它曾经在空闲时压到 (37,6,0)。
    sk0 = flame.flame_shade_k(0.0)
    for name, base, col in (("外焰", 0.48, lo[0]), ("中焰", 0.70, lo[1])):
        top = flame._soft_shade(col, base, sk0)
        ok("空闲 %s 层顶端不是全黑（R ≥ 60）" % name, top[0] >= 60,
           "顶端色 %s" % (top,))

    print("== 5. fire_heat：gamma / 点燃 / 暂停 ==")
    eq("暂停 → 用 EMBER_HEAT 那一档", flame.fire_heat(0.9, "paused"), flame.EMBER_HEAT)
    # 判据盯**性质**（"暂停不该让火跳一下"），不盯那个数值：
    # EMBER_HEAT 曾经是 0.05，跨度 41.3px，而空闲是 22.4px —— 按下暂停火反而
    # 变大 18.9px，跟"火塌成余烬"正好相反。所以真正要拦的是"暂停态不许比空闲大"。
    _d = 190.0
    _sp_idle = flame.flame_height(flame.fire_heat(0.0), _d * flame.FLAME_MAX_H_K)
    _sp_pause = flame.flame_height(flame.fire_heat(0.0, "paused"),
                                   _d * flame.FLAME_MAX_H_K)
    ok("暂停态的火不比空闲大（按下暂停不许跳）", _sp_pause <= _sp_idle + 1e-9,
       "空闲 %.1fpx / 暂停 %.1fpx" % (_sp_idle, _sp_pause))
    ok("暂停态的火也不塌到没有", _sp_pause >= _sp_idle * 0.5,
       "%.1fpx" % _sp_pause)
    ok("gamma 抬中段", flame.fire_heat(0.30) > 0.30,
       "0.30 → %.3f" % flame.fire_heat(0.30))
    eq("满热仍是满热", round(flame.fire_heat(1.0), 6), 1.0)
    ok("开屏中途窜起来", flame.fire_heat(0.0, "typing", True, 0.37) > 0.3,
       "%.3f" % flame.fire_heat(0.0, "typing", True, 0.37))
    eq("点火结束落回真实热度", round(flame.fire_heat(0.5, "typing", True, 1.0), 6),
       round(flame.fire_heat(0.5), 6))

    print("== 6. 火星：纯函数、往上飘、数量跟热度 ==")
    field = flame.SparkField()
    cx, by, h = 95.0, 133.0, 60.0
    a = field.at(3.3, 0.6, cx, by, h)
    b = field.at(3.3, 0.6, cx, by, h)
    eq("同一时刻两次调用结果一致", a, b)
    ok("时间推进后位置改变", field.at(3.9, 0.6, cx, by, h) != a)
    ok("火星全部在柴堆之上", all(y < by for _, y, _, _ in a))
    ok("淡出系数都在 0~1", all(0.0 <= sa <= 1.0 for *_, sa in a))
    eq("低热火星少", len(field.at(0.0, 0.0, cx, by, h)), 2)
    eq("满热火星最多", len(field.at(0.0, 1.0, cx, by, h)), 9)

    print("== 7. 轮廓：闭合、贴着柴堆 ==")
    pts = flame.outline(95.0, 133.0, 60.0, 20.0, 1.7, 11, 1.0, samples=20)
    eq("点数 = 两半边", len(pts), 2 * 21)
    ok("含根部的两个端点", pts[0][1] == 133.0 and pts[-1][1] == 133.0)
    ok("顶部收成尖（比根窄得多）",
       abs(pts[20][0] - pts[21][0]) < abs(pts[0][0] - pts[-1][0]) * 0.5,
       "尖 %.1fpx / 根 %.1fpx" % (abs(pts[20][0] - pts[21][0]),
                                  abs(pts[0][0] - pts[-1][0])))
    hi_pts = flame.outline(95.0, 133.0, 60.0, 20.0, 4.9, 11, 1.0, samples=20)
    ok("换一个相位轮廓就变（摇曳生效）", hi_pts != pts)

    print("== 8. 底火层：低热时也盖住柴尖 ==")
    # 主火随热度缩小时会露出柴堆的炭化黑尖（位图素材炭化很重，低热档尤其明显），
    # 底火层专门补这一段。三条性质缺一不可：低热时比主火高（否则白加）、满热时
    # 比主火矮且窄（否则会从主火里露出来）、顶端真的够到柴尖密集段。
    d = 190.0
    fcx = fcy = d / 2.0
    fby = flame.flame_base_y(fcy, d)
    li = None
    try:
        li = flame.log_image_load(
            str(Path(__file__).resolve().parent / "assets" / "log-pile.png"))
    except Exception:
        li = None

    flg = flame.flame_floor_geom(fcx, fcy, d, li)
    hf = flg.span
    h0 = flame.flame_height(0.0, d * flame.FLAME_MAX_H_K)
    h1 = flame.flame_height(1.0, d * flame.FLAME_MAX_H_K)
    ok("底火层跨度为正", hf > 0.0, "%.1fpx" % hf)
    ok("零热度：底火层比主火高（那正是它的用武之地）", hf > h0,
       "floor %.1f / main %.1f" % (hf, h0))
    ok("满热：底火层比主火矮（被主火包住）", hf < h1,
       "floor %.1f / main %.1f" % (hf, h1))
    ok("满热：底火层比主火窄",
       hf * flame.FLAME_FLOOR_ASPECT < flame.flame_width(h1, 1.0),
       "floor %.1f / main %.1f" % (hf * flame.FLAME_FLOOR_ASPECT,
                                   flame.flame_width(h1, 1.0)))
    eq("无贴图时退回兜底下限", flame.flame_floor_h(fcx, fcy, d, None),
       d * flame.FLAME_FLOOR_MIN_K)
    # 底火层与主火共用同一套锚定：形状也锚在起火点上（见第 9 节）
    eq("底火层的锚点 = 起火点",
       round(flg.anchor_y, 6),
       round(flame.flame_anchor_y(fcx, fcy, d, li), 6))

    if li is not None:
        _l, top, _r, bottom = li.content_rect(fcx, fcy, d)
        ch = bottom - top
        ok("有贴图时底火层顶端够到柴尖密集段中部",
           flg.tip_y <= top + ch * 0.30,
           "顶端 y %.1f / 柴尖区 %.1f..%.1f" % (flg.tip_y, top, bottom))
        # 它只该从柴堆顶沿探出一小截 —— 探太多就成了"一坨暗火把整垛柴包住"。
        # 上界按**内容高**给（不是绝对值）：底火层高度是 FLAME_FLOOR_MIN_K·d 这个
        # 绝对量，柴堆一小（0.62 → 0.53d，内容高 0.30 → 0.26d），同样探出 8px
        # 占的比例就变大，所以阈值放到 20%。真正要拦的是"探出半个柴堆"那种。
        ok("有贴图时底火层只从柴堆顶沿探出一小截",
           flg.tip_y >= top - ch * 0.20,
           "顶端 y %.1f / 内容顶边 %.1f（探出 %.1fpx = %.0f%% 内容高）"
           % (flg.tip_y, top, top - flg.tip_y, (top - flg.tip_y) / ch * 100))

    worst = 0.0
    for _heat in (0.0, 0.5, 1.0):
        for x, y in flame.outline(fcx, flg.root_y, flg.span, flg.w, 1.3,
                                  flame.FLAME_FLOOR_SEED, 1.0, samples=20):
            worst = max(worst, math.hypot(x - fcx, y - fcy))
    fpr = flame.pit_radius(d)
    ok("底火层留在灶膛内", worst <= fpr,
       "最远 %.1fpx / 灶膛 %.1fpx (%.0f%%)" % (worst, fpr, worst / fpr * 100))

    # 配色：主火的冷态 core 是 B 通道为 0 的纯暗红，直接拿来当底火层就是灶膛上
    # 一块死红。必须往 core_warm 混出一档色相，低热档才读得出是"薄薄一层在烧"。
    fb0, ft0 = flame.flame_floor_colors(0.0)
    fb1, _ft1 = flame.flame_floor_colors(1.0)
    ok("底火层保留色相（G/B 不为 0）", fb0[1] >= 20 and fb0[2] >= 20,
       "bottom=%s" % (fb0,))
    ok("底火层顶端比根部暗（有纵向层次）", sum(ft0) < sum(fb0),
       "top=%s bottom=%s" % (ft0, fb0))
    ok("底火层随热度变亮", sum(fb1) > sum(fb0),
       "h1=%s vs h0=%s" % (fb1, fb0))
    # 两端的值都钉死：冷态是"空闲时看得见"的验收值，它随 _IDLE_RAMP_POS 抬色阶
    # 一路变亮 —— (75,32,28)/(43,12,11)（用户抱怨"完全是一团漆黑"的那一版）
    # → (124,45,28)/(87,24,11)（第一次提亮）→ (156,81,28)/(116,57,11)（"再亮一些"）
    # → 现在这一组（"亮度还是不太行"）。满热是旺火形态，那才是不许动的那个。
    #
    # 但这次换成**盯性质**：底火层是"压在炭上的薄焰"，它必须比主火的中焰暗
    # （否则就是第二簇火苗，抢主火的视线），同时不能黑成一块（G/B 不为 0 那条
    # 已经在上面）。数值随色阶一起漂是必然的，钉死反而每轮都要改。
    _m0_floor = flame.flame_colors(0.0)[1]
    ok("冷态底火层比主火中焰暗（它有薄焰的本分）",
       sum(fb0) < sum(_m0_floor), "底火 %s 和 %d < 中焰 %s 和 %d"
       % (fb0, sum(fb0), _m0_floor, sum(_m0_floor)))
    ok("冷态底火层不是块死黑（亮度和 ≥ 200）", sum(fb0) >= 200,
       "%s 和 %d" % (fb0, sum(fb0)))
    fb1t, ft1t = flame.flame_floor_colors(1.0)
    # 本轮 _CORE_TINT 调暖之后这一组跟着漂了 —— 它是 flame_colors 的**下游**
    # （core_warm 满热时就是 core）。又是一条"每轮都要改"的钉死值，换成性质：
    # 底火层是"压在炭上的薄焰"，火旺了也不许抢主火的戏 —— 两端都得比焰芯暗。
    _core_hi = flame.flame_colors(1.0)[2]
    ok("满热底火层比主火焰芯暗（火了也不抢戏）",
       lum(fb1t) < lum(_core_hi) and lum(ft1t) < lum(_core_hi),
       "底火 %s lum %.0f / %s lum %.0f < 焰芯 %s lum %.0f"
       % (fb1t, lum(fb1t), ft1t, lum(ft1t), _core_hi, lum(_core_hi)))

    print("== 9. 起火点：火焰绕柴堆的炭化交叉点向四周长大 ==")
    # 旧版把形状锚在**底边**，热度只往上长 —— 低热时那团火落在柴堆中下部，
    # 离炭化点差一截，看着像"没烧着"。现在形状锚在起火点上：低热就是炭化点上
    # 的一小团，旺起来向上下同时铺开（上下跨度都随热度变大）。
    acx = acy = d / 2.0
    abase = flame.flame_base_y(acy, d)
    a = flame.flame_anchor_y(acx, acy, d, li)
    if li is not None:
        _l, top, _r, bottom = li.content_rect(acx, acy, d)
        ch = bottom - top
        ok("起火点落在柴堆的炭化柴尖那一段里", top <= a <= top + ch * 0.25,
           "起火点 y %.1f / 柴尖段 %.1f..%.1f" % (a, top, top + ch * 0.25))
    ok("起火点明显高于旧火根（基点抬上来了）", abase - a >= d * 0.15,
       "抬高 %.1fpx = %.3fd" % (abase - a, (abase - a) / d))

    g0 = flame.flame_geom(acx, acy, d, 0.0, li)
    g5 = flame.flame_geom(acx, acy, d, 0.5, li)
    g1 = flame.flame_geom(acx, acy, d, 1.0, li)
    eq("起火点不随热度漂（形状锚点是常量）",
       (round(g0.anchor_y, 6), round(g5.anchor_y, 6)),
       (round(g1.anchor_y, 6), round(g1.anchor_y, 6)))
    ok("每一档热度，火焰都跨在起火点两侧（不是全在它上面）",
       all(g.tip_y < g.anchor_y < g.root_y for g in (g0, g5, g1)),
       "g0 %.1f<%.1f<%.1f" % (g0.tip_y, g0.anchor_y, g0.root_y))
    ok("热度升高：火尖往上、火根往下（向四周扩展，而不是只往上长）",
       g1.tip_y < g5.tip_y < g0.tip_y and g1.root_y > g5.root_y > g0.root_y,
       "尖 %.1f→%.1f→%.1f  根 %.1f→%.1f→%.1f"
       % (g0.tip_y, g5.tip_y, g1.tip_y, g0.root_y, g5.root_y, g1.root_y))
    ok("低热时火焰就在起火点上（旧版这时候还在柴堆中下部）",
       abs((g0.tip_y + g0.root_y) * 0.5 - g0.anchor_y) <= g0.span * 0.25,
       "中心 %+.1fpx（跨度的 %.0f%%）"
       % ((g0.tip_y + g0.root_y) * 0.5 - g0.anchor_y,
          abs((g0.tip_y + g0.root_y) * 0.5 - g0.anchor_y) / g0.span * 100))
    ok("满热总跨度仍是 0.62d（满热形态是用户验收过的，不能因为改基点缩水）",
       abs(g1.span - d * 0.62) < 0.01, "%.1fpx" % g1.span)
    # 起火点的**相对高度**是反推的：不管柴堆多大，满热火根都得落在 base_y 上。
    # 早先写成常数 0.36 —— 柴堆一缩小（0.62 → 0.53d），起火点跟着下移，满热火根
    # 就戳到柴堆底边以下，底边后面空了（_logpile_preview.py 逐行轮廓判定抓到）。
    if li is not None:
        eq("有贴图时满热火根也落在 base_y 上",
           round(g1.root_y, 6), round(abase, 6))
        eq("有贴图时满热火尖 = 旧火尖",
           round(g1.tip_y, 6), round(abase - d * flame.FLAME_MAX_H_K, 6))
        pos = flame.flame_anchor_pos(acx, acy, d, li)
        eq("相对高度 = (base_y − 起火点) / 满热跨度",
           round(pos, 6), round((abase - a) / (d * flame.FLAME_MAX_H_K), 6))
    eq("无贴图时的相对高度退回常量",
       round(flame.flame_anchor_pos(acx, acy, d, None), 6),
       round(flame.FLAME_ANCHOR_POS_FALLBACK, 6))
    # 缩放不变性：起盘大小不同，满热火根都得落在各自的 base_y 上
    for size in (120.0, 190.0, 240.0):
        gs = flame.flame_geom(size / 2.0, size / 2.0, size, 1.0, li)
        eq("d=%d 满热火根 = base_y" % size, round(gs.root_y, 6),
           round(flame.flame_base_y(size / 2.0, size), 6))

    # 没贴图（代码柴堆）时必须逐像素回到旧版落位 —— 那条老路径有自己的柴尖几何，
    # 不该被贴图素材的调参顺手改掉。
    gf = flame.flame_geom(acx, acy, d, 1.0, None)
    eq("没贴图时满热火根 = 旧火根",
       round(gf.root_y, 6), round(flame.flame_base_y(acy, d), 6))
    eq("没贴图时满热火尖 = 旧火尖",
       round(gf.tip_y, 6), round(flame.flame_base_y(acy, d) - d * flame.FLAME_MAX_H_K, 6))

    print("== 9b. 前景柴堆槽位：压住火焰下半段 ==")
    fre = None
    try:
        fre = flame.log_image_load(
            str(Path(__file__).resolve().parent / "assets" / "log-pile-front.png"),
            slot="front")
    except Exception:
        fre = None
    if fre is not None and li is not None:
        ftop = fre.content_rect(acx, acy, d)[1]
        ok("前景柴堆顶边低于起火点（低热的火不会被埋住）", ftop > a,
           "前景顶边 %.1f / 起火点 %.1f" % (ftop, a))
        ok("前景比后景窄（后景两侧和柴尖还露得出来）",
           fre.slot.w_k < li.slot.w_k,
           "front %.2fd / back %.2fd" % (fre.slot.w_k, li.slot.w_k))
        eq("两个槽位是不同的落位参数",
           (fre.slot.w_k, fre.slot.sink_k) != (li.slot.w_k, li.slot.sink_k),
           True)

    # ---- 9c. 灶膛暗度：火是靠对比度被看见的 ----
    #
    # 这条性质是从一个真实缺陷里长出来的。灶膛（overlay.CAMP_PIT）是一层半透明
    # 的深色底，`CAMP_PIT_MIN_ALPHA` 早先取 96（38% 不透明）—— 只在深色桌面上
    # 验过，那时它就是个正常的坑。但用户那块桌面是**纯白** (255,255,255)：白色有
    # 62% 透上来，把灶膛冲成 rgb(164,164,165) 的**中灰**，比空闲焰芯 (189,86,0)
    # 还亮 —— 整簇火读出来是"发闷、不亮、灰蒙蒙"（用户原话），而光晕是加法混合
    # 的，叠在亮底上只会更白，等于白画。用户当时的直觉是"是不是加遮罩了"。
    #
    # 所以这里**不钉具体的 alpha 值**（那是渲染调参，会随观感变），只钉住性质：
    # 把灶膛合成到纯白桌面上之后，它必须仍然够暗、且比空闲火焰暗。
    print("== 9c. 灶膛暗度（浅色桌面上火要有对比度）==")
    _src = (Path(__file__).resolve().parent / "overlay.py").read_text(encoding="utf-8")
    _m_a = re.search(r"^CAMP_PIT_MIN_ALPHA\s*=\s*(\d+)", _src, re.M)
    _m_c = re.search(r"^CAMP_PIT\s*=\s*\((\d+),\s*(\d+),\s*(\d+)\)", _src, re.M)
    if _m_a and _m_c:
        _pa = int(_m_a.group(1))
        _pit = tuple(int(_m_c.group(i)) for i in (1, 2, 3))
        _k = _pa / 255.0
        _bg = tuple(round(v * _k + 255.0 * (1.0 - _k)) for v in _pit)   # 合成到纯白桌面
        _lum = lambda c: sum(c) / 3.0                                   # noqa: E731
        _core = flame.flame_colors(0.0)[2]         # 空闲焰芯：画面里最亮的一层
        ok("白底合成后的灶膛够暗（亮度 <= 60）", _lum(_bg) <= 60,
           "灶膛底 rgb%s 亮度 %.0f" % (_bg, _lum(_bg)))
        ok("空闲火焰比灶膛底亮（火能被看见）", _lum(_core) > _lum(_bg),
           "焰芯亮度 %.0f vs 灶膛 %.0f" % (_lum(_core), _lum(_bg)))
        ok("灶膛底线在白底上仍偏中性（没被染成彩色）",
           max(_bg) - min(_bg) <= 12, "RGB 极差 %d" % (max(_bg) - min(_bg)))
    else:
        ok("能读到 overlay.py 的 CAMP_PIT / CAMP_PIT_MIN_ALPHA", False,
           "正则没匹配到，常量可能改名了")

    print("== 9d. 「从小到大的过程」不许有跳变 ==")
    # 这些性质只有渲染出来才看得见，而本文件刻意不依赖 Qt，所以判据写成对
    # **决策**的守卫（正则/子串读源码）。三处都真的踩过：
    #   · 暂停时传 None 会被 draw_campfire_qt 当成"没传 field，新建默认的"，
    #     "暂停不放火星"形同虚设（实测暂停帧仍有 18 个火星像素）
    #   · 热弧阈值写 0.002 时，热度从 0 往上会让弧先从 2.5° 缩到 1.3° 再长
    #   · 暂停态的 EMBER_HEAT 曾经 0.05 → 火比空闲**大**（第 5 节另有行为断言）
    _fl_src = (Path(__file__).resolve().parent / "flame.py").read_text(encoding="utf-8")
    _tk_src = (Path(__file__).resolve().parent / "overlay_tk.py").read_text(encoding="utf-8")
    ok("暂停时 overlay 传 False（传 None 等于放弃这个开关）",
       'False if state == "paused" else self._sparks' in _src)
    ok("draw_campfire_qt 认得 spark_field=False（= 这帧不放火星）",
       "spark_field is False" in _fl_src)
    for _nm, _s in (("overlay.py", _src), ("overlay_tk.py", _tk_src)):
        ok("%s 热弧阈值取下限弧长（0 热度往上时弧不许先变短）" % _nm,
           "IDLE_ARC_DEG / SWEEP_DEG" in _s and "> 0.002" not in _s)

    print("== 9e. 第 1/2 层的提亮：冷端零改动、几何不被旋钮污染 ==")
    # 本轮给外焰 / 中焰加了独立提亮旋钮，全部按热度加权（_l12_weight）。
    ok("_l12_weight(0) = 0（空闲档一个像素都不许动）",
       flame._l12_weight(0.0) == 0.0, "%.3f" % flame._l12_weight(0.0))
    ok("_l12_weight(1) = 1（满热吃满提亮量）",
       flame._l12_weight(1.0) == 1.0, "%.3f" % flame._l12_weight(1.0))
    _ws = [flame._l12_weight(i / 100.0) for i in range(101)]
    ok("_l12_weight 单调不降（不许出现「越热越暗」）",
       all(_ws[i] <= _ws[i + 1] + 1e-12 for i in range(100)),
       "最大回落 %.4f" % max([_ws[i] - _ws[i + 1] for i in range(100)] + [0.0]))
    # 空闲时两个保留比例必须逐位等于基准值 —— 这是"空闲观感不动"的实现口径。
    ok("空闲的第 1 层保留比例 = _L1_KEEP（旋钮零加成）",
       flame._L1_KEEP + flame._L1_KEEP_UP * flame._l12_weight(0.0) == flame._L1_KEEP)
    ok("空闲的第 2 层保留比例 = _L2_KEEP（旋钮零加成）",
       flame._L2_KEEP + flame._L2_KEEP_UP * flame._l12_weight(0.0) == flame._L2_KEEP)
    # 几何守卫。踩过：提亮权重顺手写成 `w`，覆盖了 draw_campfire_qt 里
    # `root_y, h, w = g.root_y, g.span, g.w` 的**火焰半宽** —— 三层全都拿一个
    # 0~1 的小数当宽度去调 outline()，火焰塌成一条线，而纯函数测试全绿
    # （几何断言走 flame_geom，绕过了渲染路径）。所以守卫只能写在源码上。
    _dw = re.search(r"def draw_campfire_qt\(.*?(?=\ndef |\Z)", _fl_src, re.S)
    _body = _dw.group(0) if _dw else ""
    ok("draw_campfire_qt 的 w（火焰半宽）不被后续赋值覆盖",
       _body != "" and len(re.findall(r"^\s*w\s*=", _body, re.M)) == 0,
       "命中 %s" % re.findall(r"^\s*w\s*=", _body, re.M))
    ok("draw_campfire_qt 的提亮权重用 lw（不与 w 撞名）",
       "lw = _l12_weight(heat)" in _body)
    ok("第 1/2 层的提亮量只乘 _l12_weight，不出现别的权重",
       _body.count("_l12_weight") == 1 and _body.count("lw") >= 3)

    print()
    print("结果：%s（%d 通过 / %d 失败）"
          % ("全部通过" if BAD == 0 else "有失败", OK, BAD))
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
