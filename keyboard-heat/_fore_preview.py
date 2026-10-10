"""端向柴预览：用共享的「多边形清单」直接画成 SVG，验证它确实压在火焰平底边上。

不依赖 Qt（这环境没装 PyQt6），纯几何转 SVG，两版 UI 消费的就是同一份清单，
所以遮挡顺序是真实的。输出 fore_preview.svg（idle / high 两档并排）。
"""
import math
import flame

CAMP_PIT = (14, 12, 17)


def hx(c):
    return "#%02x%02x%02x" % (c[0], c[1], c[2])


def pts_str(pts):
    return " ".join("%.1f,%.1f" % (x, y) for x, y in pts)


def ring_defs(svg, cx, cy):
    pass


def panel(d, heat, ox):
    cx = cy = d / 2.0
    base_y = flame.flame_base_y(cy, d)
    h = flame.flame_height(heat, d * flame.FLAME_MAX_H_K)
    w = flame.flame_width(h, heat)
    outer, mid, core = flame.flame_colors(heat)
    t = 1.3
    out = []
    # 圆环
    rr = flame.ring_radius(d)
    rt = flame.ring_thick(d)
    out.append('<circle cx="%.0f" cy="%.0f" r="%.1f" fill="none" '
                'stroke="#3a3f4a" stroke-width="%.1f"/>' % (cx + ox, cy + ox, rr, rt))
    # 灶膛
    pr = flame.pit_radius(d)
    out.append('<circle cx="%.0f" cy="%.0f" r="%.1f" fill="%s"/>'
                % (cx + ox, cy + ox, pr, hx(CAMP_PIT)))
    # 光晕（SVG 径向渐变近似 Qt 的 Plus 光晕）
    gx, gy = cx + ox, (base_y - h * 0.28) + ox
    gr = h * 1.05 + d * 0.06
    a0 = int(58 + 96 * heat)
    out.append('<defs><radialGradient id="g%d">' % int(ox))
    out.append('<stop offset="0" stop-color="%s" stop-opacity="%.2f"/>'
               % (hx(mid), a0 / 255))
    out.append('<stop offset="0.32" stop-color="%s" stop-opacity="%.2f"/>'
               % (hx(mid), a0 * 0.42 / 255))
    out.append('<stop offset="0.62" stop-color="%s" stop-opacity="%.2f"/>'
               % (hx(mid), a0 * 0.11 / 255))
    out.append('<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient></defs>'
               % hx(mid))
    out.append('<circle cx="%.0f" cy="%.0f" r="%.1f" fill="url(#g%d)"/>'
               % (gx, gy, gr, int(ox)))
    # 后对柴 + 中对柴（都在火焰后面）
    for pair in ("back", "mid"):
        for pts, col in flame.log_draw_list(
                flame.log_pile(cx + ox, base_y + ox, d, heat, mid, "charred",
                               pair=pair)):
            out.append('<polygon points="%s" fill="%s"/>'
                       % (pts_str(pts), hx(col)))
    # 炭火床
    er_r = max(w * 0.60, d * 0.15)
    out.append('<defs><radialGradient id="e%d">' % int(ox))
    out.append('<stop offset="0" stop-color="%s" stop-opacity="%.2f"/>'
               % (hx(core), (80 + 165 * heat) / 255))
    out.append('<stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient></defs>'
               % hx(mid))
    out.append('<ellipse cx="%.0f" cy="%.0f" rx="%.1f" ry="%.1f" fill="url(#e%d)"/>'
               % (cx + ox, base_y + ox, er_r, er_r * 0.70, int(ox)))
    # 火焰三层（用层底/层顶代表色近似 Qt 渐变）
    grads = (outer, mid, core)
    for (shrink, seed), c in zip(flame.LAYERS, grads):
        p = flame.outline(cx + ox, base_y + ox, h, w, t, seed, shrink, 26)
        out.append('<polygon points="%s" fill="%s" opacity="0.96"/>'
                   % (pts_str(p), hx(c)))
    # 前对柴
    for pts, col in flame.log_draw_list(
            flame.log_pile(cx + ox, base_y + ox, d, heat, mid, "charred",
                           pair="front")):
        out.append('<polygon points="%s" fill="%s"/>' % (pts_str(pts), hx(col)))
    # 端向柴
    for pts, col in flame.fore_draw_list(
            flame.log_fore(cx + ox, base_y + ox, d, heat, mid, "charred")):
        out.append('<polygon points="%s" fill="%s"/>' % (pts_str(pts), hx(col)))
    # 火星
    for sx, sy, sr, sa in flame.SparkField().at(t, heat, cx + ox, base_y + ox, h):
        if sa <= 0.02:
            continue
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" '
                   'opacity="%.2f"/>' % (sx, sy, sr, hx(core), sa))
    return out


def main():
    d = 360
    parts = []
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" '
                 'width="%d" height="%d" viewBox="0 0 %d %d">'
                 % (d * 3, d, d * 3, d))
    parts.append('<rect width="%d" height="%d" fill="#1b1d22"/>' % (d * 3, d))
    # 左：idle（余烬），右：high（满火）
    parts += panel(d, 0.15, d * 0.5)
    parts += panel(d, 1.0, d * 2.0)
    parts.append('<text x="%d" y="%d" fill="#9aa" font-size="20" '
                 'text-anchor="middle">idle</text>' % (int(d * 1.0), d - 8))
    parts.append('<text x="%d" y="%d" fill="#9aa" font-size="20" '
                 'text-anchor="middle">high</text>' % (int(d * 2.5), d - 8))
    parts.append('</svg>')
    with open("fore_preview.svg", "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print("wrote fore_preview.svg")


if __name__ == "__main__":
    main()
