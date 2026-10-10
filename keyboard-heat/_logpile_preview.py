"""柴堆 / 火焰落位验收台 —— 改素材、改 FLAME_*_K、改 LOG_SLOT_* 之后跑它。

做两件事：
  1. 打出几何数字（起火点、火根、火尖、前景柴堆顶边、灶膛余量）
  2. 出一张对照图：左 = 低热，右 = 满热；都按真实层次画
     （后景柴堆 → 底火层 → 主火三层 → 前景柴堆），并叠三条参考线：
       青 = 起火点（火焰绕它缩放）   红 = 火焰轮廓的平直底边   橙 = 前景柴堆顶边

关键不变量（脚本会逐条判定，FAIL 就得调参）：
  · 火焰的**平直底边**必须被前景柴堆的**轮廓**盖住（不是外接矩形，是逐行宽度）
  · 满热的火尖不许越过灶膛（否则火焰压到圆环上）
  · 起火点必须落在后景柴堆的炭化柴尖那一段里

    .pyenv\\Scripts\\python.exe _logpile_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import flame  # noqa: E402
from heatcore import cfg_get, load_config  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

BACK = HERE / "assets" / "log-pile.png"
FRONT = HERE / "assets" / "log-pile-front.png"
DIAL = 190.0
SCALE = 2
HEATS = ((0.0, "idle"), (1.0, "full"))
OUT = HERE / "_logpile_preview.png"


class RowSpan:
    """一张贴图的逐行轮廓宽度（内容像素坐标）。

    用 LogImage.data（抠过底、带 alpha 的那份）建图 —— 直接开原始 PNG 的话
    alpha 全是 255，量出来每行都是满宽，判据就废了（踩过这个坑）。
    逐行取 crop().getbbox()：走 PIL 的 C 实现，比在 Python 里扫 alpha 快两个量级。
    """

    def __init__(self, li):
        self.im = Image.frombytes("RGBA", (li.w, li.h), li.data)
        self.w, self.h = li.w, li.h
        self._cache = {}

    def at(self, y):
        y = max(0, min(self.h - 1, int(y)))
        if y not in self._cache:
            bb = self.im.crop((0, y, self.w, y + 1)).getbbox()
            self._cache[y] = (bb[0], bb[2] - 1) if bb else None
        return self._cache[y]


def content_rows(li):
    """内容包围盒对应的像素行范围。"""
    return li.bbox[1], li.bbox[3] - 1


def paste_li(canvas, li, box):
    """把抠好底的 LogImage 按 box 缩放贴上去。

    注意要用 li.data（抠过底、带 alpha 的那份），不能直接开原始 PNG ——
    原始文件是不透明的黑底，直接贴会把整个面板糊成黑块。
    """
    im = Image.frombytes("RGBA", (li.w, li.h), li.data)
    lx, ly, lw, lh = box
    im = im.resize((max(1, int(round(lw))), max(1, int(round(lh)))),
                   Image.LANCZOS)
    canvas.alpha_composite(im, (int(round(lx)), int(round(ly))))


def main():
    d = DIAL * SCALE
    cx = cy = d / 2.0
    pit_r = flame.pit_radius(d)
    ring_in = flame.ring_inner_radius(d)
    base_y = flame.flame_base_y(cy, d)

    back = flame.log_image_load(BACK, slot="back")
    front = flame.log_image_load(FRONT, slot="front")
    if back is None or front is None:
        print("素材加载失败（Pillow 缺失？文件不在？）")
        return 1
    fl_active = bool(cfg_get(load_config()["overlay"], "flame_floor", True))

    print("盘直径 %.0f（真机 %.0f × %d 倍）" % (d, DIAL, SCALE))
    print("火根 flame_base_y = %.1f   灶膛半径 %.1f   圆环内沿 %.1f\n"
          % (base_y, pit_r, ring_in))

    for tag, li in (("后景", back), ("前景", front)):
        x0, y0, x1, y1 = li.bbox
        l, t, r, b = li.content_rect(cx, cy, d)
        print("%s %dx%d  内容像素 x %d..%d y %d..%d  宽高比 %.2f"
              % (tag, li.w, li.h, x0, x1 - 1, y0, y1 - 1,
                 (x1 - x0) / float(y1 - y0)))
        print("     画布落位 x %.1f..%.1f  y %.1f..%.1f   宽 %.3fd 高 %.3fd"
              % (l, r, t, b, (r - l) / d, (b - t) / d))

    span_front = RowSpan(front)
    span_back = RowSpan(back)

    print("\n起火点（火焰绕它向四周缩放）")
    a = flame.flame_anchor_y(cx, cy, d, back)
    l, top, r, bottom = back.content_rect(cx, cy, d)
    print("     y = %.1f   = 内容顶边往下 %.0f%%   (火根往上一 %.1fpx)"
          % (a, (a - top) / (bottom - top) * 100, base_y - a))
    print("     炭化柴尖那一段 y %.1f..%.1f  → 基点落在里面：%s"
          % (top, top + (bottom - top) * 0.25,
             "是" if top <= a <= top + (bottom - top) * 0.25 else "否"))

    print("\n平直底边是否落在木头上（逐行量轮廓，取 4 个热度）")
    print("   —— 判据是「前景柴堆 ∪ 后景柴堆」，两者都能当它的底：")
    print("      落在前景上 = 被前面的柴压住；落在后景上 = 火在木柴前面，也是对的。")
    print("      真正的毛病只有一种：底边后面是空的（直接怼在灶膛背景上）。")
    ok = True
    fx, fy, flw, _flh = front.box(cx, cy, d)
    fs = flw / float(front.w)                 # 前景贴图的画布/像素缩放比
    bx, by, blw, _blh = back.box(cx, cy, d)
    bs = blw / float(back.w)

    def span_at(which, y):
        if which == "front":
            sp = span_front.at((y - fy) / fs)
            return (fx + sp[0] * fs, fx + sp[1] * fs) if sp else (None, None)
        sp = span_back.at((y - by) / bs)
        return (bx + sp[0] * bs, bx + sp[1] * bs) if sp else (None, None)

    def cover(y, hw, who):
        nonlocal ok
        need = (cx - hw, cx + hw)
        hits = []
        for which in ("front", "back"):
            left, right = span_at(which, y)
            if left is not None and left <= need[0] and right >= need[1]:
                hits.append(which)
        if not hits:
            ok = False
        print("   %-8s y=%6.1f  需盖住 x %6.1f..%6.1f  → %s"
              % (who, y, need[0], need[1],
                 ("落在" + "/".join({"front": "前景", "back": "后景"}[h]
                                    for h in hits) + "柴堆上")
                 if hits else "**后面是空的**"))

    for heat in (0.0, 0.25, 0.5, 1.0):
        g = flame.flame_geom(cx, cy, d, heat, back)
        worst = max(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in
                    flame.outline(cx, g.root_y, g.span, g.w, 1.3, 11, 1.0, 20))
        print("  热度 %.2f：火根 y=%.1f  火尖 y=%.1f  跨度 %.1f  最远点 %.1f/%.1f 灶膛 %s"
              % (heat, g.root_y, g.tip_y, g.span, worst, pit_r,
                 "（出界！）" if worst > pit_r else ""))
        if worst > pit_r:
            ok = False
        cover(g.root_y, g.w * flame._halfw(0.0), "主火")
        if fl_active:
            fg = flame.flame_floor_geom(cx, cy, d, back)
            cover(fg.root_y, fg.w * flame._halfw(0.0), "底火层")
    print("\n判定：%s" % ("几何全部通过" if ok else "有问题，见上面的 **后面是空的**"))

    # ---- 对照图 ----
    g0 = flame.flame_geom(cx, cy, d, 0.0, back)
    panel = int(d)
    out = Image.new("RGB", (panel * 2 + 12, panel), (245, 245, 248))
    for i, (heat, name) in enumerate(HEATS):
        img = Image.new("RGBA", (panel, panel), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        dr.ellipse((cx - pit_r, cy - pit_r, cx + pit_r, cy + pit_r),
                   fill=(42, 36, 28, 255))
        dr.ellipse((cx - ring_in, cy - ring_in, cx + ring_in, cy + ring_in),
                   outline=(96, 216, 200, 255), width=2)
        paste_li(img, back, back.box(cx, cy, d))
        _, mid, core = flame.flame_colors(heat)
        fg = flame.flame_floor_geom(cx, cy, d, back)
        fb, ftp = flame.flame_floor_colors(heat)
        dr.polygon(flame.outline(cx, fg.root_y, fg.span, fg.w, 3.8,
                                 flame.FLAME_FLOOR_SEED),
                   fill=flame._mix(fb, ftp, 0.5) + (255,))
        g = flame.flame_geom(cx, cy, d, heat, back)
        for (shrink, seed), col in zip(flame.LAYERS,
                                       flame.flame_colors(heat)):
            dr.polygon(flame.outline(cx, g.root_y, g.span, g.w, 3.8, seed,
                                     shrink), fill=col + (255,))
        paste_li(img, front, front.box(cx, cy, d))
        # 参考线：青=起火点，红=火焰平直底边，橙=前景柴堆顶边
        fc = front.content_rect(cx, cy, d)
        for y, col in ((g0.anchor_y, (80, 220, 220)),
                       (g.root_y, (230, 60, 60)),
                       (fc[1], (250, 170, 60))):
            dr.line((4, y, panel - 4, y), fill=col + (255,), width=2)
        out.paste(img.convert("RGB"), (i * (panel + 12), 0))
    out.save(OUT)
    print("对照图 %s（左 idle / 右 full；青=起火点 红=火焰底边 橙=前景柴堆顶边）"
          % OUT.name)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
