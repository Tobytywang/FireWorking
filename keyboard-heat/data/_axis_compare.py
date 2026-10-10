# -*- coding: utf-8 -*-
"""对照图：**同一根参考柱，切换日期后高度变不变**（本轮修掉的缺陷）。

用户报的现象：「不同日期的历史平均值应该一样的呀，为什么切换日期看起来不一样？」
根因：参考序列的值是常量，但刻度 `mx = max(当天峰值, 平均峰值)` 是**每天重算**的
      → 值没变、刻度变了 → 同一根参考柱在不同日期画出来高度不同。

渲两套图 = 每个日期一张 × 2 种刻度模式：
  改前 = 注入 `_pre_datescale.js`（把 hourAxisMax 换回逐日峰值）
  改后 = 现状（刻度 = 全周期常量）
每个日期都渲，再由**实测**挑出差异最大的两天来展示（不写死日期）。

几何全部从像素里扫（复用 `_avg_compare.py` 的 classify）：
  · 截图用 `_shot_tiles.mjs --only "#bars"`，图内坐标 = 柱图容器内相对坐标；
  · `.bars{align-items:end}` + `.bh{align-self:stretch}` ⇒ **柱底 = 图像底边**；
  · 参考柱顶 = 浅色像素的 min y；当天柱顶 = 实色像素的 min y。

判据（脚本自己断言，失败就退出）：改前两天的参考柱顶必须差得开；改后必须重合。
用 keyboard-heat/.pyenv 跑（要 PIL）。"""
import os
import re
import subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, 'heat-report-prototype.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
NODE = r'C:\Users\toby.wang\.workbuddy\binaries\node\versions\22.22.2-3\node.exe'
SHOT = os.path.join(HERE, '_shot_tiles.mjs')

BG = (246, 244, 241)
INK = (40, 34, 30)
GRAY = (110, 101, 91)
RED = (200, 60, 60)
GREEN = (32, 148, 74)
BLUE = (40, 96, 190)
LINE = (210, 205, 198)


def day_keys():
    """从产物里取日期，别写死。"""
    src = open(HTML, encoding='utf-8').read()
    m = re.search(r'const DATA = \{(.*?)\};\n', src, re.S)
    if not m:
        raise SystemExit('!! 抠不到 DATA')
    return sorted(set(re.findall(r'"(\d{4}-\d{2}-\d{2})":\[', m.group(1))))


def shoot(tag, dates, datescale):
    """datescale=True 时注入逐日刻度夹具（= 改前）。每个日期一张图。"""
    base = open(os.path.join(HERE, '_pre_datescale.js'), encoding='utf-8').read() if datescale else ''
    out = {}
    for k in dates:
        pre = os.path.join(HERE, '_tmp_axis_%s_%s.js' % (tag, k))
        # 夹具改高度前先关 transition：否则截到的是过渡中间态
        open(pre, 'w', encoding='utf-8').write(
            "document.head.insertAdjacentHTML('beforeend',"
            "'<style>.bars .bar{transition:none !important}</style>');\n"
            + base + "\nselectDay('%s');\nvoid document.body.offsetHeight;\n" % k)
        cmd = [NODE, SHOT, '--html', HTML, '--out', HERE, '--widths', '1280', '--dpr', '1',
               '--tag', 'ax_%s_%s' % (tag, k), '--only', '#bars', '--idx', '0',
               '--pre', pre, '--chrome', CHROME]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            raise SystemExit('!! 截图失败 %s %s\n%s' % (tag, k, r.stderr.decode('utf-8', 'replace')))
        p = os.path.join(HERE, 'ax_%s_%s_1280_1x.png' % (tag, k))
        if not os.path.exists(p):
            raise SystemExit('!! 截图没生成：%s\n%s' % (p, r.stdout.decode('utf-8', 'replace')))
        out[k] = p
        os.remove(pre)
    return out


def classify(px):
    """'day' = 当天柱（实色）/ 'ref' = 参考柱（同色相 28% 透明）/ None"""
    r, g, b = px
    d = r - b
    if d > 100 and r > 120 and g < 200:
        return 'day'
    if d > 25 and r > 120 and g < 235:
        return 'ref'
    return None


def scan_bars(path):
    """扫出「最高的参考柱」与「最高的当天柱」的顶边 y。

    ⚠ 不能直接取 `min(y of ref pixels)` —— **当天柱顶部的圆角抗锯齿**会被判成参考柱
      （实测：09-22 当天柱顶到 100%，它的 5px 圆角弧混白后 r−b 掉进参考柱区间，
      于是改前/改后的 refTop 都被误报成 0，抹掉了真正的 61px 差异）。
      解法：按列求 ref 像素的**最长连续竖段**，只认可「段长 ≥ MINRUN」的列 ——
      圆角弧只有 ~5px 长，参考柱柱身有几十到上百 px。
      柱底 = 图像底边（`.bars{align-items:end}` + `.bh{align-self:stretch}`）。"""
    im = Image.open(path).convert('RGB')
    w, h = im.size
    px = im.load()
    M = [[classify(px[x, y]) for x in range(w)] for y in range(h)]

    def tops(kind, minrun):
        best = None
        for x in range(w):
            start, cur = -1, None
            for y in range(h + 1):
                hit = y < h and M[y][x] == kind
                if hit and start < 0:
                    start = y
                elif not hit and start >= 0:
                    if cur is None or (y - start) > cur[1]:
                        cur = (start, y - start)
                    start = -1
            if cur and cur[1] >= minrun and (best is None or cur[0] < best):
                best = cur[0]
        return best

    MINRUN = 12
    refTop = tops('ref', MINRUN)
    dayTop = tops('day', MINRUN)
    if refTop is None:
        raise SystemExit('!! %s 没扫到参考柱（竖段 ≥%dpx）—— 分类阈值或截图不对' % (path, MINRUN))
    if dayTop is None:
        raise SystemExit('!! %s 没扫到当天柱（竖段 ≥%dpx）—— 数据里当天柱太矮？' % (path, MINRUN))
    return {'refTop': refTop, 'dayTop': dayTop, 'bot': h - 1,
            'refH': h - refTop, 'dayH': h - dayTop,
            'refPx': sum(r.count('ref') for r in M),
            'dayPx': sum(r.count('day') for r in M), 'w': w, 'h': h}


def font(sz):
    for p in ('C:/Windows/Fonts/msyhbd.ttc', 'C:/Windows/Fonts/msyh.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def main():
    days = day_keys()
    print('日期：%s' % ', '.join(days))
    old_png = shoot('old', days, datescale=True)
    new_png = shoot('now', days, datescale=False)
    png = {'old': old_png, 'new': new_png}
    old = {k: scan_bars(v) for k, v in old_png.items()}
    new = {k: scan_bars(v) for k, v in new_png.items()}
    for k in days:
        print('  %s | 改前 参考柱 顶%3d 高%3d 当天柱 顶%3d 高%3d | 改后 参考柱 顶%3d 高%3d 当天柱 顶%3d 高%3d'
              % (k, old[k]['refTop'], old[k]['refH'], old[k]['dayTop'], old[k]['dayH'],
                 new[k]['refTop'], new[k]['refH'], new[k]['dayTop'], new[k]['dayH']))

    srt = sorted(days, key=lambda k: old[k]['refH'])
    d_hi, d_lo = srt[-1], srt[0]          # 参考柱最高 / 最低
    spread_old = old[d_hi]['refH'] - old[d_lo]['refH']
    spread_new = abs(new[d_hi]['refH'] - new[d_lo]['refH'])
    print('展示：%s（改前参考柱最高 %dpx） / %s（最低 %dpx）' % (d_hi, old[d_hi]['refH'], d_lo, old[d_lo]['refH']))

    # ── 断言：判据本身必须真的能抓住缺陷 ──
    if spread_old < 8:
        raise SystemExit('!! 改前两天的参考柱高度几乎没差（%dpx）—— 夹具没复现出缺陷' % spread_old)
    if spread_new > 1:
        raise SystemExit('!! 改后两天的参考柱高度仍不一致（%dpx）—— 刻度还是逐日的' % spread_new)
    if new[d_lo]['dayH'] == new[d_hi]['dayH']:
        raise SystemExit('!! 改后两天的当天柱高完全相同 —— 图里看不出"当天在变"')

    # ────────────────────── 拼图（2 列 × 2 行）──────────────────────
    im = {(st, k): Image.open(png[st][k]).convert('RGB') for st in ('old', 'new') for k in (d_hi, d_lo)}
    IW, IH = im[('old', d_hi)].size

    PAD, TITLE_H, ROWLBL, COLGAP, ROWGAP, FOOT_H = 20, 78, 108, 34, 56, 92
    W = PAD * 2 + ROWLBL + IW * 2 + COLGAP
    H = PAD + TITLE_H + IH + ROWGAP + IH + FOOT_H + PAD
    cv = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(cv)
    f_t, f_l, f_s, f_b = font(19), font(14), font(12.5), font(13.5)
    f_h = font(17)

    x_old = PAD + ROWLBL
    x_new = x_old + IW + COLGAP
    d.text((PAD, PAD), '同一根参考柱，切换日期后高度会不会变？（改前 / 改后）', font=f_t, fill=INK)
    d.text((x_old, PAD + 34), '改前：刻度 = max(当天峰值, 平均峰值)，每天重算 → 基线自己在动',
           font=f_l, fill=RED)
    d.text((x_new, PAD + 34), '改后：刻度 = 全周期常量 → 参考柱逐日等高', font=f_l, fill=GREEN)

    y = {d_hi: PAD + TITLE_H, d_lo: PAD + TITLE_H + IH + ROWGAP}
    for k in (d_hi, d_lo):
        for st, x in (('old', x_old), ('new', x_new)):
            cv.paste(im[(st, k)], (x, y[k]))
            d.rectangle([x - 1, y[k] - 1, x + IW, y[k] + IH], outline=LINE, width=1)
        d.text((PAD, y[k] + IH // 2 - 26), k, font=f_h, fill=INK)
        d.text((PAD, y[k] + IH // 2 + 2), '参考柱高', font=f_s, fill=GRAY)
        d.text((PAD, y[k] + IH // 2 + 18), '%dpx' % old[k]['refH'], font=f_s, fill=RED)
        d.text((PAD, y[k] + IH // 2 + 34), '%dpx' % new[k]['refH'], font=f_s, fill=GREEN)

    def hline(x_img, y_img, ypx, color, width, dash=0):
        """在帧内画一条横线；dash>0 时画成虚线（用于"把上一行的线延伸过来"）。"""
        yy = y_img + ypx
        if dash:
            for xx in range(x_img, x_img + IW, dash * 2):
                d.line([(xx, yy), (min(xx + dash - 1, x_img + IW - 1), yy)], fill=color, width=width)
        else:
            d.line([(x_img + 1, yy), (x_img + IW - 1, yy)], fill=color, width=width)

    # 每一帧：参考柱顶一条横线 + 标注（线太靠顶时把标注压到线下，免得撞标题）
    for k in (d_hi, d_lo):
        for st, x, col in (('old', x_old, RED), ('new', x_new, GREEN)):
            v = (old if st == 'old' else new)[k]
            hline(x, y[k], v['refTop'], col, 2)
            ly = y[k] + v['refTop'] + (4 if v['refTop'] < 20 else -18)
            d.text((x + 8, ly), '参考柱顶 y=%d（高 %dpx）' % (v['refTop'], v['refH']), font=f_s, fill=col)
            # 当天柱顶：蓝色短标
            hline(x, y[k], v['dayTop'], BLUE, 3)
            ty = y[k] + v['dayTop'] + (4 if v['dayTop'] < 20 else -18)
            d.text((x + IW - 190, ty), '当天柱顶 y=%d' % v['dayTop'], font=f_s, fill=BLUE)

    # 把**上一行**的参考柱顶虚线延伸到下一行 —— 一眼看出第二行有没有落在同一条线上
    for st, x, col in (('old', x_old, RED), ('new', x_new, GREEN)):
        ref = (old if st == 'old' else new)[d_hi]['refTop']
        hline(x, y[d_lo], ref, col, 1, dash=6)
    dd_old = old[d_lo]['refTop'] - old[d_hi]['refTop']
    dd_new = new[d_lo]['refTop'] - new[d_hi]['refTop']
    d.text((x_old + 8, y[d_lo] + IH - 40),
           '虚线 = 上一行参考柱顶；本行实际柱顶低了 %dpx ← 基线在动' % dd_old, font=f_s, fill=RED)
    d.text((x_new + 8, y[d_lo] + IH - 40),
           '虚线 = 上一行参考柱顶；本行与它重合（差 %dpx）✓' % dd_new, font=f_s, fill=GREEN)

    # ────────────────────── 脚注 ──────────────────────
    fy = y[d_lo] + IH + 16
    d.line([(PAD, fy - 12), (W - PAD, fy - 12)], fill=LINE, width=1)
    same = len({new[k]['refH'] for k in days}) == 1
    d.text((PAD, fy),
           '参考柱高度：改前 %s=%dpx / %s=%dpx（差 %dpx，%.2f 倍）　→　'
           '改后 %s=%dpx / %s=%dpx（差 %dpx）'
           % (d_hi, old[d_hi]['refH'], d_lo, old[d_lo]['refH'], spread_old,
              old[d_hi]['refH'] / max(1, old[d_lo]['refH']),
              d_hi, new[d_hi]['refH'], d_lo, new[d_lo]['refH'], spread_new), font=f_b, fill=INK)
    d.text((PAD, fy + 22),
           '参考柱的数值两天完全相同（全周期同时段平均，数值极差 0）—— 变的只有刻度。'
           '当天柱高：改前 %d/%dpx、改后 %d/%dpx，逐日不同（正确）。'
           % (old[d_hi]['dayH'], old[d_lo]['dayH'], new[d_hi]['dayH'], new[d_lo]['dayH']),
           font=f_b, fill=INK)
    d.text((PAD, fy + 44),
           '全量 %d 天：改后参考柱高度%s'
           % (len(days), ' %s 天全部 %dpx，完全一致 ✓' % (len(days), new[days[0]]['refH'])
              if same else '仍不一致 %s ✗' % [new[k]['refH'] for k in days]), font=f_b, fill=INK)

    out = os.path.join(HERE, '_axis_ab.png')
    cv.save(out)
    print('saved', out, cv.size)
    print('参考柱顶跨日位移：改前 %dpx  →  改后 %dpx' % (dd_old, dd_new))


if __name__ == '__main__':
    main()
