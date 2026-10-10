"""量出「起火点」（柴堆交叉处 / 炭化区）的真实位置 —— 火焰基点的取值依据。

不碰生产代码，只输出数据：
  · 两张素材的尺寸、内容包围盒、内容宽高比
  · 后景柴堆的**炭化区**纵向分布（低亮度 + 低暖度 = 黑灰的炭，木头的暗面不会误判）
  · 按当前 LOG_SLOT_* 落位后，内容包围盒换算到表盘坐标的实际位置
  · 起火点 / 它的相对高度 / 满热火根 —— 验证"满热火根落在 base_y 上"这条不变量

    .pyenv\\Scripts\\python.exe _anchor_probe.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flame  # noqa: E402
from PIL import Image  # noqa: E402

BACK = HERE / "assets" / "log-pile.png"
FRONT = HERE / "assets" / "log-pile-front.png"
D = 190.0


def load(name, path, slot):
    t0 = time.perf_counter()
    li = flame.log_image_load(path, slot=slot)
    dt = time.perf_counter() - t0
    if li is None:
        print("%-6s LOAD FAILED %s" % (name, path))
        return None
    x0, y0, x1, y1 = li.bbox
    print("%-6s %-22s %4dx%-5d  %.2fMB  load %.3fs  槽位 w_k=%.2f sink_k=%.3f"
          % (name, path.name, li.w, li.h, path.stat().st_size / 1e6, dt,
             li.slot.w_k, li.slot.sink_k))
    print("       内容包围盒 x %d..%d  y %d..%d   (内容 %.0fx%.0f, 宽高比 %.3f)"
          % (x0, x1 - 1, y0, y1 - 1, x1 - x0, y1 - y0,
             (x1 - x0) / float(y1 - y0)))
    return li


def char_zone(path, li):
    """低亮度 + 低暖度 = 炭化。按内容高度分 20 档统计占比。"""
    im = Image.open(path).convert("RGB")
    x0, y0, x1, y1 = li.bbox
    im = im.crop((x0, y0, x1, y1))
    im = im.resize((max(1, im.width // 4), max(1, im.height // 4)))
    px = im.load()
    w, h = im.size
    bins = [0] * 20
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if max(r, g, b) < 90 and (r - b) < 34:
                bins[y * 20 // h] += 1
    tot = float(max(1, sum(bins)))
    print("       炭化区纵向分布（内容高度 0%=顶, 100%=底）")
    for i, n in enumerate(bins):
        if n:
            print("        %2d-%2d%%  %5.1f%%  %s"
                  % (i * 5, i * 5 + 5, n / tot * 100, "#" * int(n / tot * 100)))
    # 判据只能看**顶端集中度**，不能看"密集段到哪为止"：柴堆底部的木头暗面
    # （低亮度、低暖度）也会被算成"炭"，所以分布尾部必然还有一坨。
    top5 = sum(bins[:5]) / tot * 100.0
    print("       顶端 0~25%%（柴尖那一段）占全部炭化像素的 %.0f%%；"
          "均匀分布应为 25%% → 集中度 %.1fx"
          % (top5, top5 / 25.0))
    print("       FLAME_ANCHOR_K = %.2f → 起火点取在内容顶边往下 %.0f%%；"
          "炭化集中在顶端 0~25%% 那一段，所以取值 %s"
          % (flame.FLAME_ANCHOR_K, flame.FLAME_ANCHOR_K * 100,
             "合适" if flame.FLAME_ANCHOR_K <= 0.25 else "偏低了，要调小"))


def placement(name, li, cx, cy, d):
    l, t, r, b = li.content_rect(cx, cy, d)
    base_y = flame.flame_base_y(cy, d)
    print("%-6s 内容 x %.1f..%.1f  宽 %.3fd | y %.1f..%.1f  高 %.3fd | 底边 %+.1fpx 相对火根"
          % (name, l, r, (r - l) / d, t, b, (b - t) / d, b - base_y))
    a = flame.flame_anchor_y(cx, cy, d, li)
    ch = b - t
    print("       起火点 y=%.1f（内容顶边往下 %.0f%%）  它在形状里的相对高度 %.3f"
          % (a, (a - t) / ch * 100, flame.flame_anchor_pos(cx, cy, d, li)))
    g1 = flame.flame_geom(cx, cy, d, 1.0, li)
    print("       满热：火根 y=%.1f（火根线 %.1f，差 %+.2fpx）  火尖 y=%.1f  跨度 %.1f"
          % (g1.root_y, base_y, g1.root_y - base_y, g1.tip_y, g1.span))
    g0 = flame.flame_geom(cx, cy, d, 0.0, li)
    print("       空闲：火根 y=%.1f  火尖 y=%.1f  跨度 %.1f（= 柴堆内容高的 %.0f%%）"
          % (g0.root_y, g0.tip_y, g0.span, g0.span / ch * 100))
    fl = flame.flame_floor_geom(cx, cy, d, li)
    print("       底火层：跨度 %.1f（顶沿探出内容顶边 %.1fpx）"
          % (fl.span, t - fl.tip_y))


def main():
    cx = cy = D / 2.0
    print("表盘 d=%.0f，圆心 (%.0f, %.0f)，火根 base_y=%.1f，灶膛半径 %.1f，圆环内沿 %.1f"
          % (D, cx, cy, flame.flame_base_y(cy, D), flame.pit_radius(D),
             flame.ring_inner_radius(D)))
    print("满热跨度上限 = FLAME_MAX_H_K × d = %.1f，空闲比例 FLAME_IDLE_K = %.2f\n"
          % (flame.FLAME_MAX_H_K * D, flame.FLAME_IDLE_K))

    back = load("篝火3", BACK, "back") if BACK.exists() else None
    front = load("低矮", FRONT, "front") if FRONT.exists() else None

    if back is not None:
        placement("后景", back, cx, cy, D)
        char_zone(BACK, back)
    if front is not None:
        print()
        placement("前景", front, cx, cy, D)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
