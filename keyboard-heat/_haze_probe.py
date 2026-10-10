"""诊断「灰蒙蒙」到底来自哪里 —— 纯计算，只读，不渲染。

两种互斥的可能，必须用数字分开：

  A. 有全局透明遮罩（窗口 alpha / 半透明图层）—— 火焰的颜色被桌面稀释，
     表现为「亮度和饱和度同时下降，且随桌面内容变化」。
  B. 配色本身去饱和（我上一轮把空闲色阶位置抬太高 + 提白）—— 色相还在橙红，
     但饱和度掉下去，表现为「发白、发灰」，与桌面无关。

这个脚本打印三样东西：
  1. 色阶表 FIRE_RAMP 的饱和度和亮度
  2. _ramp_pos 把各档热度映射到色阶哪个位置
  3. flame_colors 三层在若干热度下的**实际渲染色**（含 _lift 提白 / _soft_shade 压暗）
     —— 每个色都给出 HSV 饱和度，冷态是否「发灰」一眼可见。
"""
from __future__ import annotations

import colorsys
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flame  # noqa: E402


def hsv(c):
    h, s, v = colorsys.rgb_to_hsv(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0)
    return h * 360.0, s, v


def tag(c):
    _h, s, v = hsv(c)
    return "rgb%-16s 饱和%5.1f%% 亮%5.1f%%" % (str(tuple(c)), s * 100.0, v * 100.0)


print("=" * 78)
print("1. 色阶表 FIRE_RAMP（黑体辐射 + T^4 辐射强度 + Reinhard 色调映射）")
print("=" * 78)
for pos, c in flame.FIRE_RAMP:
    print("   位置 %.2f  %s" % (pos, tag(c)))

print()
print("=" * 78)
print("2. _ramp_pos：热度 -> 色阶位置（_IDLE_RAMP_POS=%.2f, 指数=%.1f）"
      % (flame._IDLE_RAMP_POS, flame._IDLE_RAMP_FALLOFF))
print("=" * 78)
prev = None
for i in range(0, 21):
    t = i / 20.0
    p = flame._ramp_pos(t)
    c = flame._ramp(p)
    _h, s, v = hsv(c)
    mark = ""
    if prev is not None and v < prev - 1e-6:
        mark = "   <== 亮度回落（火比上一档更暗）"
    prev = v
    print("   热度 %.2f -> 色阶 %.3f  %s%s" % (t, p, tag(c), mark))

print()
print("=" * 78)
print("3. flame_colors + 三层实际渲染色（含提白 _lift / 压暗 _soft_shade）")
print("=" * 78)
for t in (0.0, 0.05, 0.19, 0.30, 0.50, 0.80, 1.0):
    o, m, c = flame.flame_colors(t)
    sk = flame.flame_shade_k(t)
    print("   热度 %.2f  外焰压暗量k=%.3f  尖端压暗折扣=%.3f"
          % (t, flame._edge_mix_k(t), sk))
    print("       外焰 base %s" % tag(o))
    print("       中焰 base %s" % tag(m))
    print("       焰芯 base %s   <== 焰芯饱和度最低就是「发灰」的来源" % tag(c))
    grads = (
        ("外焰", flame._lift(o, 0.06), flame._soft_shade(o, 0.48, sk)),
        ("中焰", flame._lift(c, 0.02), flame._soft_shade(m, 0.70, sk)),
        ("焰芯", flame._lift(c, 0.62 * flame.flame_core_lift_k(t)),
         flame._soft_shade(c, 0.52, sk)),
    )
    for name, bottom, top in grads:
        _h1, s1, _v1 = hsv(bottom)
        _h2, s2, _v2 = hsv(top)
        print("       %s 渐变：根 饱和%5.1f%% / 尖 饱和%5.1f%%   （%.0f%% 处起转尖色）"
              % (name, s1 * 100.0, s2 * 100.0, 55.0))
    print()

print("=" * 78)
print("4. 空闲态（heat=0）三层渐变，逐档列出 —— 判断「灰」的具体数值")
print("=" * 78)
o, m, c = flame.flame_colors(0.0)
sk = flame.flame_shade_k(0.0)
grads = (
    ("外焰", flame._lift(o, 0.06), flame._soft_shade(o, 0.48, sk)),
    ("中焰", flame._lift(c, 0.02), flame._soft_shade(m, 0.70, sk)),
    ("焰芯", flame._lift(c, 0.62 * flame.flame_core_lift_k(0.0)),
     flame._soft_shade(c, 0.52, sk)),
)
for name, bottom, top in grads:
    print("   %s  根 %s" % (name, tag(bottom)))
    print("   %s  尖 %s" % ("　" * len(name), tag(top)))
