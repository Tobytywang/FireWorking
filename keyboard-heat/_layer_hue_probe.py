# -*- coding: utf-8 -*-
"""量"最前面那层火焰"到底偏在哪。

用户报「有点绿」。火焰色阶是从黑体色温算出来的，理论上不会 G>R，所以
"绿"多半不是真的绿，而是某个通道关系在**深色背景 + 暖橙邻居**的衬托下
被读成了偏冷。这个探针把三层火焰的实际 RGB / 色相 / 通道关系全部打出来。

三段：
  A  FIRE_RAMP 色阶表 —— 看色阶本身有没有"黄绿带"
  B  flame_colors(heat) 三层 —— 看每层落在色阶哪一段、混了多少白
  C  Tk 版三层（_mixc 口径）—— 双 UI 必须同源

只读，不改任何东西。
"""
import colorsys
import sys

sys.path.insert(0, ".")
import flame

HEATS = [0.0, 2, 5, 10, 19, 30, 50, 70, 85, 100]


def hsv(rgb):
    r, g, b = [c / 255.0 for c in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s * 100.0, v * 100.0


def show(tag, rgb):
    h, s, v = hsv(rgb)
    r, g, b = rgb
    gr = (g / r * 100.0) if r else 0.0
    print("  %-22s rgb(%3d,%3d,%3d)  H %6.1f  S %5.1f  V %5.1f  R-B %4d  G/R %5.1f%%"
          % (tag, r, g, b, h, s, v, r - b, gr))


def sec_a():
    print("=" * 78)
    print("A  黑体色阶 FIRE_RAMP（%d 个 stop，%.0fK → %.0fK）"
          % (flame.FIRE_STOPS, flame.FIRE_T_MIN, flame.FIRE_T_MAX))
    print("=" * 78)
    for pos, rgb in flame.FIRE_RAMP:
        h, s, v = hsv(rgb)
        flag = ""
        if s > 5 and h > 55:
            flag = "   <== 偏黄绿"
        print("  pos %.3f   rgb(%3d,%3d,%3d)  H %6.1f  S %5.1f  V %5.1f  R-B %4d%s"
              % (pos, rgb[0], rgb[1], rgb[2], h, s, v, rgb[0] - rgb[2], flag))
    print()


def sec_b():
    print("=" * 78)
    print("B  flame_colors(heat) 三层（Qt 版口径）")
    print("=" * 78)
    for heat in HEATS:
        t = heat / 100.0
        outer, mid, core = flame.flame_colors(t)
        pos = flame._ramp_pos(t)
        print("  heat %5.1f   _ramp_pos %.3f   _edge_mix_k %.3f   core_lift_k %.3f"
              % (heat, pos, flame._edge_mix_k(t), flame.flame_core_lift_k(t)))
        show("  outer 外焰(第1层)", outer)
        show("  mid   中焰(第2层)", mid)
        show("  core  焰芯(第3层)", core)
        print()


def sec_c():
    print("=" * 78)
    print("C  Tk 版三层（往 CAMP_PIT_RGB 混的比例口径）")
    print("=" * 78)
    import overlay_tk as tko
    pit = tko.CAMP_PIT_RGB
    print("  CAMP_PIT_RGB = %s    _mixc(a,b,k) = a*(1-k)+b*k" % (pit,))
    show("灶膛底", pit)
    print()
    for heat in HEATS:
        t = heat / 100.0
        outer, mid, core = flame.flame_colors(t)
        lw = flame._l12_weight(t)
        # 三个 Tk 旋钮都住在 flame.py 里（两边共用的常量区），不在 overlay_tk
        k1 = min(1.0, flame._L1_TK_KEEP + flame._L1_TK_KEEP_UP * lw)
        f0 = tko._mixc(pit, outer, k1)
        f1 = tko._mixc(mid, core, flame._L2_TK_MIX_UP * lw)
        # Tk 焰芯：往 flame._CORE_TINT 混白（0.30 × 热度折扣），见 overlay_tk
        f2 = tko._mixc(core, flame._CORE_TINT,
                       0.30 * flame.flame_core_lift_k(t))
        print("  heat %5.1f   _l12_weight %.3f   L1 保留比例 %.3f" % (heat, lw, k1))
        show("  l0 外焰", f0)
        show("  l1 中焰", f1)
        show("  l2 焰芯", f2)
        print()


def main():
    sec_a()
    sec_b()
    sec_c()
    return 0


if __name__ == "__main__":
    sys.exit(main())
