# -*- coding: utf-8 -*-
"""改前/改后对照图：倒计时节「4 卡 → 按类型分布卡片」的接缝。

改前 = _cdgap_now_1280.png   （旧产物，探针实测 gap = 0.0px）
改后 = _cdgap_after_1280.png （本次修复后，探针实测 gap = 14.0px）

三件事：
 ① 全图差异 bbox —— 硬证据：差异只从接缝那几行开始（4 卡以上逐像素一致 ⇒ 数据没被牵连）
 ② 像素扫描**自动定位**接缝：页面背景 #f6f4f1 / 卡片白 #ffffff 不同，
    取 x∈[200,600]（卡片中段，避开文字）逐行判"是否整行近白"，
    行序列里「白 → 非白 → 白」的那一段非白，就是间隙（改前应无此段）。
    ⚠ 自动定位出的两端行号会打印出来供核对，不靠肉眼。
 ③ 在放大帧上把间隙带涂色 + 标注实测值（数值来自探针，非手填）。
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(HERE, '_cdgap_now_1280.png')
AFTER = os.path.join(HERE, '_cdgap_after_1280.png')
OUT = os.path.join(HERE, '_cdgap_ab.png')

GAP_BEFORE = 0.0          # 探针实测（_cdgap_probe.py）
GAP_AFTER = 14.0          # 探针实测（_cdgap_probe.py）

BOX = (0, 116, 520, 180)  # x0,y0,x1,y1（原图坐标）
ZOOM = 4
# ⚠ 扫描列必须落在**单张卡内部**：4 卡之间有 12px 横向 gap（页面背景色），
#   一旦列的区间跨过 gap，"整行近白"就永远不成立（实测整段被误判成"非白"、接缝定位失真）。
#   取 x∈[130,340]（第一张卡 106..360 的内部）即可。
XSCAN = (130, 340)

b = Image.open(BEFORE).convert('RGB')
a = Image.open(AFTER).convert('RGB')
print('before %sx%s   after %sx%s' % (b.size + a.size))

# ---- ① 全图差异 ----
d = ImageChops.difference(b, a).convert('L')
print('全图差异 bbox = %s  （只应从接缝起；4 卡以上一致 = 数据没被牵连）' % (d.getbbox(),))

# ---- ② 自动定位接缝 ----
def card_rows(im, y0, y1):
    """返回 [(y, is_white, mean_lum)]。
    近白(≥250) = 卡片内部；否则 = 边框 / 间隙 / 页面背景 —— 三者亮度不同：
      卡片白 255 / 页面背景 #f6f4f1 ≈ 244 / 边框 rgba(40,33,26,.12) 叠白 ≈ 228
    所以顺带输出平均亮度，就能把"边框行"与"间隙行"分开，不用猜。"""
    px = im.load()
    out = []
    for y in range(y0, y1):
        n = 0
        tot = 0
        lum = 0.0
        for x in range(XSCAN[0], XSCAN[1], 2):
            r, g, bl = px[x, y]
            tot += 1
            lum += 0.299 * r + 0.587 * g + 0.114 * bl
            if r >= 250 and g >= 250 and bl >= 250:
                n += 1
        out.append((y, n / tot > 0.98, lum / tot))
    return out


def runs(rows):
    """压成 [(y_start, y_end, is_white, lum_min, lum_max)]。"""
    res = []
    for y, isw, lm in rows:
        if res and res[-1][2] == isw:
            res[-1][1] = y
            res[-1][3] = min(res[-1][3], lm)
            res[-1][4] = max(res[-1][4], lm)
        else:
            res.append([y, y, isw, lm, lm])
    return [tuple(r) for r in res]


def show_runs(tag, im, y0, y1):
    rr = runs(card_rows(im, y0, y1))
    print('%s 行结构（x∈%d..%d）:' % (tag, XSCAN[0], XSCAN[1]))
    for a0, a1, isw, l0, l1 in rr:
        kind = '卡片白' if isw else ('边框/暗' if l0 < 238 else '间隙/背景')
        print('   y %3d..%-3d  %-8s lum %.0f..%.0f  (%d 行)'
              % (a0, a1, kind, l0, l1, a1 - a0 + 1))
    return rr


runs_b = show_runs('BEFORE', b, 116, 180)
runs_a = show_runs('AFTER', a, 116, 180)

# ---- ③ 拼接 + 标注 ----
def seam_of(rr):
    """从行结构里读出 (4 卡底边框区, 面板内部起点)。
    第一段"非白"= 4 卡底边框（改后它后面还会跟一段"间隙/背景"）；
    之后第一段"卡片白"= 面板内部。"""
    border = None
    panel = None
    for a0, a1, isw, l0, l1 in rr:
        if not isw and border is None:
            border = (a0, a1)
        elif isw and border is not None:
            panel = a0
            break
    return border, panel


def frame(im, color, border, panel):
    c = im.crop(BOX).resize(((BOX[2] - BOX[0]) * ZOOM, (BOX[3] - BOX[1]) * ZOOM), Image.NEAREST)
    dr = ImageDraw.Draw(c)
    if border and panel:
        # 4 卡底边框的**底沿** → 面板内部首行，就是要标注的那条缝
        yA = (border[1] + 1 - BOX[1]) * ZOOM
        yB = (panel - BOX[1]) * ZOOM
        if yB - yA >= 2:                      # 有间隙：涂色带 + 上下双线
            dr.rectangle([0, yA, c.width - 1, yB - 1], fill=(255, 232, 232))
            dr.line([0, yA, c.width, yA], fill=color, width=3)
            dr.line([0, yB, c.width, yB], fill=color, width=3)
        else:                                 # 没间隙：一条重合线
            yy = (border[1] - BOX[1]) * ZOOM
            dr.line([0, yy, c.width, yy], fill=color, width=3)
    return c


fb, pb_ = seam_of(runs_b)
fa, pa_ = seam_of(runs_a)
print('BEFORE 4卡底边框 y=%s，面板内部起于 y=%s' % (fb, pb_))
print('AFTER  4卡底边框 y=%s，面板内部起于 y=%s' % (fa, pa_))

cb = frame(b, (200, 30, 30), fb, pb_)
ca = frame(a, (200, 30, 30), fa, pa_)


def band(text, w, h=28, bg=(28, 24, 20)):
    im = Image.new('RGB', (w, h), bg)
    f = None
    for p in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, 16)
                break
            except Exception:
                pass
    ImageDraw.Draw(im).text((10, 5), text, fill=(255, 255, 255),
                            font=f or ImageFont.load_default())
    return im


W = max(cb.width, ca.width)
parts = [band('BEFORE（旧产物）  实测 gap = %.1fpx —— 4 卡与下方面板贴死、边框重合' % GAP_BEFORE, W), cb,
         band('AFTER（本次修复）  实测 gap = %.1fpx —— 与全页卡片间距一致' % GAP_AFTER, W), ca]
H = sum(p.height for p in parts)
out = Image.new('RGB', (W, H), (255, 255, 255))
y = 0
for p in parts:
    out.paste(p, (0, y))
    y += p.height
out.save(OUT)
print('对照图 -> %s (%dx%d)' % (os.path.basename(OUT), out.width, out.height))
