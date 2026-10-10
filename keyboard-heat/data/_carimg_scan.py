# -*- coding: utf-8 -*-
"""从用户截图里量「日历网格底 → 图例墨迹」空白带，并换算成 CSS px。

做法：
 1) 用网格方块的**纵向节距**（= 13px 格 + 3px 间隙 = 16 CSS px）反推缩放比，不猜 DPR。
 2) 定位网格最后一行方块的墨迹下沿（= 内容的视觉底边）。
 3) 只在网格下方找图例墨迹、卡片下边框。
 4) 用用户画的纯红框（237,28,36）bbox 当交叉校验 —— 注意标题的橙色竖条
    (#e8590c) 与"红"很接近，必须用 g 通道把它排除。
"""
import sys
from collections import Counter
from PIL import Image

P = sys.argv[1]
im = Image.open(P).convert('RGB')
W, H = im.size
px = im.load()
bg = Counter(im.getdata()).most_common(1)[0][0]


def d(c, r=bg):
    return abs(c[0] - r[0]) + abs(c[1] - r[1]) + abs(c[2] - r[2])


# 用户框的纯红 (237,28,36)；标题橙条 (232,89,12) 的 g=89 会被这条排除
def ISBOX(c):
    return c[0] > 200 and c[1] < 60 and c[2] < 70


xs = [x for x in range(W) if any(ISBOX(px[x, y]) for y in range(0, H, 2))]
ys = [y for y in range(H) if any(ISBOX(px[x, y]) for x in range(0, W, 2))]
print('用户红框 bbox: x %d..%d (宽 %d)   y %d..%d (高 %d)'
      % (min(xs), max(xs), max(xs) - min(xs) + 1, min(ys), max(ys), max(ys) - min(ys) + 1))

# --- 横带剖面（用整幅宽度，避免只看半幅漏掉右半的图例） ---
prof = [sum(1 for x in range(0, W, 2) if d(px[x, y]) > 10) for y in range(H)]
thr = (W // 2) * 0.25
runs, cur = [], None
for y in range(H):
    if prof[y] >= thr and cur is None:
        cur = y
    elif prof[y] < thr and cur is not None:
        runs.append((cur, y - 1)); cur = None
if cur is not None:
    runs.append((cur, H - 1))

# 网格行 = 连续、节距恒定（16 CSS px × scale）的若干条
cand = [r for r in runs if 10 <= r[1] - r[0] <= 40]
pitch = Counter(cand[i + 1][0] - cand[i][0] for i in range(len(cand) - 1))
grid_pitch = pitch.most_common(1)[0][0]
scale = grid_pitch / 16.0
gr = [r for r in cand if r[0] < H]
print('横带: %s' % runs[:16])
print('网格行段: %s' % gr[:10])
print('节距 %d px  →  缩放比 %.3f（16 CSS px = 13 格 + 3 隙）' % (grid_pitch, scale))

grid_bot = max(r[1] for r in gr[:8])
print('网格墨迹下沿 y = %d' % grid_bot)

# --- 网格下方：图例墨迹（整体右端）与卡片下边框 ---
leg = [y for y in range(grid_bot + 1, H)
       if sum(1 for x in range(0, W, 2) if d(px[x, y]) > 12) > 3]
legT, legB = min(leg), max(leg)

# 卡片下边框：网格下方一条接近全宽的浅灰线（--line）
bar = None
for y in range(H - 1, grid_bot, -1):
    n = sum(1 for x in range(0, W, 2) if d(px[x, y]) > 6)
    if n > (W // 2) * 0.85:
        bar = y; break

print('图例墨迹 y = %d..%d (高 %d)' % (legT, legB, legB - legT + 1))
print('卡片下边框 y = %s' % bar)
print('-' * 62)
print('网格墨迹底 → 图例墨迹顶          = %4d px = %5.1f CSS px'
      % (legT - grid_bot, (legT - grid_bot) / scale))
print('图例墨迹顶 → 图例墨迹底（行高）  = %4d px = %5.1f CSS px'
      % (legB - legT + 1, (legB - legT + 1) / scale))
if bar:
    print('图例墨迹底 → 卡片下边框          = %4d px = %5.1f CSS px'
          % (bar - legB, (bar - legB) / scale))
print('红框高 = %.1f CSS px（用户圈定的"空白"）' % ((max(ys) - min(ys) + 1) / scale))
