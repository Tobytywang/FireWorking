# -*- coding: utf-8 -*-
"""逐小时分布：改前（只有当天一根柱，一天里 23 个小时是空的）/ 改后（每格两根柱，
浅色 = 全周期同时段平均）对照图。

改前 = 注入 `_pre_noavg.js` 复现（该夹具同时是探针 `--noavg` 的反向验证用例）。
改后 = 现状。

图内几何**全部从像素里扫**，不写死坐标：
  · 柱图区的 x 范围 = 「灰痕像素 ∪ 柱体像素」的 x 范围 —— 24 个小时每格都有一条 2% 的
    灰痕或柱子，所以这个并集就是 `.bars` 的左右边界（0 点与 23 点也在内），据此把 x
    均分 24 段；
  · 柱底 = 灰痕/柱体像素的最大 y；柱图区高用 CSS 的 170px 反推顶边（两版都没改过这个高度）；
  · 当天柱与参考柱靠**饱和度**区分：当天柱（含鼠标段）r−b > 100，参考柱（同色相 28% 透明）
    r−b ≈ 55。抗锯齿边缘落在中间地带，按各段计数时误差 < 1 段。
用 keyboard-heat/.pyenv 的 python 跑（要 PIL）。"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (246, 244, 241)
INK = (40, 34, 30)
GRAY = (110, 101, 91)
RED = (200, 60, 60)
GREEN = (32, 148, 74)
BAR_H = 170          # .bars 的高度（CSS 未改过，两版一致）


def load(p):
    return Image.open(os.path.join(HERE, p)).convert('RGB')


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def classify(px):
    """'day' = 当天柱（实色）/ 'ref' = 参考柱（同色相浅色）/ 'soft' = 2% 灰痕 / None"""
    r, g, b = px
    d = r - b
    if d > 100 and r > 120 and g < 200:
        return 'day'
    if d > 25 and r > 120 and g < 235:
        return 'ref'
    if 225 <= r <= 246 and abs(r - g) <= 5 and abs(g - b) <= 5:
        return 'soft'
    return None


def scan(im, geom=None):
    """扫出柱图区的几何 + 24 段里各段的柱子类型。

    `geom` 传上一帧扫出的几何时，**复用它的左右边界**：柱图区的左右边界由 CSS 决定
    （卡片宽、padding、gap 两版都没改），两帧必然相同。这不只是省事 —— 改后帧自己扫
    边界会失败（那条"柱底带"里灰痕与参考柱混在一起，扫出来只有 324px 宽，段宽虚报
    13.5px，分段全错），复用是**更可靠**的做法。

    ⚠ 四个坑（都实测撞过，别简化掉）：
      ① **卡片外边框也是中性浅灰**，且贯穿整张图 —— 直接拿全部 soft 像素的边界会把
         x 范围撑成整张卡片（0..1051）、把柱底撑到卡片底，算出 dayTopPct = 126%。
      ② **图例的三个色块也是橙色系**（第一块就是 `--accent-2` 纯色、第三块是 `--mouse`），
         会被当成柱子：实测改后图 dayN 虚报成 2、柱底跑到图例上（321 而非 279 - 0）。
         解法：柱图区最多 170px 高，而图例色块只有 13px —— 取橙色系像素 y 集合的
         **最长连续段**即可把两者分开。
      ③ 柱底只认**柱体**像素的最大 y（在①的段内）：卡片下边框是横线，排除左右边列
         也挡不住它。
      ④ 段内要有 ≥ MIN 个像素才算「这格有柱」：抗锯齿的零星像素会把段数虚报
         （实测改前图 10 个飘在当天柱边缘的 ref 像素 → refN 虚报 1）。"""
    W, H = im.size
    px = im.load()
    edge = 4
    day_pts, ref_pts, soft_pts = [], [], []
    for y in range(H):
        for x in range(edge, W - edge):
            k = classify(px[x, y])
            if k == 'day':
                day_pts.append((x, y))
            elif k == 'ref':
                ref_pts.append((x, y))
            elif k == 'soft':
                soft_pts.append((x, y))
    if not day_pts and not ref_pts:
        raise SystemExit('!! 没扫到柱体像素 —— 截图不对？')
    # 柱图区 = 橙色系像素 y 集合的**最长连续段**（见坑②）。改前没有图例，只有一段；
    # 改后多出 13px 高的图例段，最长的那段仍是柱图区（最高可达 170px）。
    rows = sorted({y for _, y in day_pts + ref_pts + soft_pts})
    seg, best = [], []
    for y in rows:
        if seg and y == seg[-1] + 1:
            seg.append(y)
        else:
            if len(seg) > len(best):
                best = seg
            seg = [y]
    if len(seg) > len(best):
        best = seg
    y0b, y1b = best[0], best[-1]
    keep = lambda pts: [(x, y) for x, y in pts if y0b <= y <= y1b]
    day_pts, ref_pts, soft_pts = keep(day_pts), keep(ref_pts), keep(soft_pts)
    if not day_pts and not ref_pts:
        raise SystemExit('!! 柱图区段里没扫到柱体像素 —— 分类阈值不对？')
    bot = max(y for _, y in day_pts + ref_pts)
    if geom:
        x0, x1 = geom['x0'], geom['x1']
    else:
        band = [x for x, y in soft_pts + day_pts + ref_pts if bot - 5 <= y <= bot]
        x0, x1 = min(band), max(band)
    seg_w = (x1 - x0 + 1) / 24.0

    def seg_of(x):
        return int((x - x0) / seg_w)

    day_cnt, ref_cnt = [0] * 24, [0] * 24
    for x, _ in day_pts:
        i = seg_of(x)
        if 0 <= i < 24:
            day_cnt[i] += 1
    for x, _ in ref_pts:
        i = seg_of(x)
        if 0 <= i < 24:
            ref_cnt[i] += 1
    # MIN 取 30：真实柱最少也有 ~35 像素（1% 高 × 一格宽），而抗锯齿的零星像素只有个位数
    # （实测改前图当天柱边缘飘出 10 个 ref 像素 → refN 虚报 1）。
    MIN = 30
    segs = [(day_cnt[h] >= MIN, ref_cnt[h] >= MIN) for h in range(24)]
    valid_day = [y for x, y in day_pts if day_cnt[seg_of(x)] >= MIN]
    day_top = min(valid_day) if valid_day else None
    return {'x0': x0, 'x1': x1, 'seg_w': seg_w, 'bot': bot,
            'top': bot - BAR_H, 'segs': segs,
            'dayN': sum(1 for a, _ in segs if a),
            'refN': sum(1 for _, b in segs if b),
            'dayPx': sum(day_cnt), 'refPx': sum(ref_cnt),
            'dayTopPct': (bot - day_top) / BAR_H * 100 if day_top else 0,
            'area': sum(day_cnt) + sum(ref_cnt),
            'dayCnt': day_cnt, 'refCnt': ref_cnt}


pre = scan(load('hr_pre_1280_1x.png'))          # 改前：只有当天柱
aft = scan(load('hr_1280_1x.png'), geom=pre)    # 改后：当天柱 + 参考柱（复用同一套左右边界）

im_pre = load('hr_pre_1280_1x.png')
im_aft = load('hr_1280_1x.png')

PAD = 20
TITLE_H = 58           # 总标题 + 帧标题两行（第一版 34 时两行叠在一起了）
SEP = 62               # 两帧之间（放分隔标签）
FOOT_H = 58
GW = 440               # 右侧标注槽宽度（正文最长约 33 个全角字符 × 12.5px ≈ 412px）
W = PAD * 2 + im_pre.width + GW
H = PAD + TITLE_H + im_pre.height + SEP + im_aft.height + FOOT_H + PAD

cv = Image.new('RGB', (W, H), BG)
d = ImageDraw.Draw(cv)
f_t = font(19)
f_l = font(14)
f_s = font(12.5)
f_b = font(13.5)


def slots(y_from, y_to, n, gap=6):
    """把 n 条标注均匀铺在 [y_from, y_to]，返回各自的 y。不重叠。"""
    if n <= 0:
        return []
    span = (y_to - y_from) - gap * (n - 1)
    step = span / n
    return [y_from + i * (step + gap) for i in range(n)]


d.text((PAD, PAD), '逐小时分布：加入「历史同时段平均」参考柱（改动前 / 改动后）', font=f_t, fill=INK)

# ---------- 帧 1：改前 ----------
y1 = PAD + TITLE_H
d.text((PAD, y1 - 24), '改前：24 个小时里只有 %d 根柱有内容，其余只剩一条 2%% 灰痕'
       % pre['dayN'], font=f_l, fill=RED)
cv.paste(im_pre, (PAD, y1))
gx = PAD + im_pre.width + 16
# 红框圈住"唯一那根柱"与"右侧整片空白"
for h in range(24):
    if pre['segs'][h][0]:
        sx0 = PAD + pre['x0'] + h * pre['seg_w']
        d.rectangle([sx0 - 4, y1 + pre['top'] - 4, sx0 + pre['seg_w'] + 4, y1 + pre['bot'] + 4],
                    outline=RED, width=2)
        d.text((gx, y1 + pre['top'] - 6), '① 全图唯一的柱', font=f_l, fill=RED)
        break
# 空白片区的红框（从最后一根柱之后到 23 点）：与柱子**等高**，一眼看出"这块本该有内容"
last_day = max([h for h in range(24) if pre['segs'][h][0]] or [0])
sx0 = PAD + pre['x0'] + last_day * pre['seg_w'] + pre['seg_w'] + 6
d.rectangle([sx0, y1 + pre['top'] + 8, PAD + pre['x1'], y1 + pre['bot'] + 4], outline=RED, width=1)
for yy, t in zip(slots(y1 + pre['top'] + 40, y1 + pre['bot'], 3),
                 ['② 其余 23 个小时只剩 2% 灰痕，视觉上等于空白',
                  '   —— 就是你说的"太空了"',
                  '③ 唯一的柱也没有参照：不知道这天算多还是算少']):
    d.text((gx, yy), t, font=f_s, fill=RED)

# ---------- 分隔标签 ----------
yml = y1 + im_pre.height + SEP // 2
d.line([(PAD, yml), (PAD + im_pre.width, yml)], fill=(210, 205, 198), width=1)
d.text((PAD, yml - 26), '↓  加入参考柱（浅色 = 全周期同时段平均，与当天柱共用同一条刻度）',
       font=f_l, fill=GREEN)

# ---------- 帧 2：改后 ----------
y2 = y1 + im_pre.height + SEP
d.text((PAD, y2 - 18), '改后：每天都是两根柱 —— 深色 = 当天，浅色 = 历史同时段平均',
       font=f_l, fill=GREEN)
cv.paste(im_aft, (PAD, y2))
for h in range(24):
    if aft['segs'][h][0]:
        sx0 = PAD + aft['x0'] + h * aft['seg_w']
        d.rectangle([sx0 - 4, y2 + aft['top'] + 20, sx0 + aft['seg_w'] + 4, y2 + aft['bot'] + 4],
                    outline=GREEN, width=2)
        break
for yy, t in zip(slots(y2 + 110, y2 + im_aft.height - 46, 4),
                 ['④ 浅色参考柱：%d / 24 个小时有值，把原来空着的地方填上' % aft['refN'],
                  '   一眼看出"这天比平时闲"，而不是只有一根孤零零的柱',
                  '⑤ 两根柱共用同一条刻度（参考柱峰值 100%%、当天柱 %.0f%%）'
                  % aft['dayTopPct'],
                  '   各用各的 max 会让两根都顶格，"参考"就白加了']):
    d.text((gx, yy), t, font=f_s, fill=GREEN)

# ---------- 脚注：量化 ----------
# ⚠ 小时数必须**去重**：09 点既是当天唯一的活跃小时、也有参考柱（两柱同格），
#   直接写「当天 1 + 参考 16 = 17」不闭合（那是格数不是小时数）。
cover_pre = sum(1 for a, b in pre['segs'] if a or b)
cover_aft = sum(1 for a, b in aft['segs'] if a or b)
fy = y2 + im_aft.height + 12
d.line([(PAD, fy - 8), (PAD + im_pre.width, fy - 8)], fill=(210, 205, 198), width=1)
d.text((PAD, fy), '横向覆盖：有柱的小时  改前 %d/24（参考柱 0）  →  改后 %d/24'
                  '　（参考柱 %d 格 + 当天柱 %d 格 = %d 格；09 点两柱同格，去重后 %d 个小时）'
       % (cover_pre, cover_aft, aft['refN'], aft['dayN'],
          aft['refN'] + aft['dayN'], cover_aft),
       font=f_b, fill=INK)
d.text((PAD, fy + 22), '柱体像素：改前 %s（全是当天柱）  →  改后 %s = 当天 %s + 参考 %s'
                       '（参考柱占 %.0f%%）'
       % (format(pre['area'], ','), format(aft['area'], ','),
          format(aft['dayPx'], ','), format(aft['refPx'], ','),
          aft['refPx'] / max(1, aft['area']) * 100),
       font=f_b, fill=INK)

out = os.path.join(HERE, '_avg_ref_ab.png')
cv.save(out)
print('saved', out, cv.size)
print('改前 dayN=%d refN=%d area=%d dayTop=%.0f%%  bot=%d 段宽%.1f'
      % (pre['dayN'], pre['refN'], pre['area'], pre['dayTopPct'], pre['bot'], pre['seg_w']))
print('     段计数 day %s' % pre['dayCnt'])
print('            ref %s' % pre['refCnt'])
print('改后 dayN=%d refN=%d area=%d dayTop=%.0f%%  bot=%d 段宽%.1f'
      % (aft['dayN'], aft['refN'], aft['area'], aft['dayTopPct'], aft['bot'], aft['seg_w']))
print('     段计数 day %s' % aft['dayCnt'])
print('            ref %s' % aft['refCnt'])
