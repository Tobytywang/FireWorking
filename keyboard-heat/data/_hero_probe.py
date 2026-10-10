#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""头部三卡替换的验证探针：
   (1) 用 Python 按报告同款口径，从真实数据独立重算三项新指标，证明不是写死；
   (2) 把 _hero_before.png / _hero_after.png 拼成并排对照图。
   用法：python _hero_probe.py
"""
import re, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, 'heat-report.html')

html = open(HTML, encoding='utf-8').read()
def grab(name):
    start = html.index('const %s = ' % name) + len('const %s = ' % name)
    end = html.index('};\n', start) + 1   # JSON 顶层以 } 收尾，内层不会是 "};\n"
    return json.loads(html[start:end])

DATA = grab('DATA'); META = grab('META'); COUNTDOWN = grab('COUNTDOWN')
W_MOVE, W_CLICK, W_SCROLL = 0.01, 4, 2
def mouseEquiv(r): return r[4]*W_MOVE + r[5]*W_CLICK + r[6]*W_SCROLL

def dayTotals(k):
    keys = act = meq = 0
    for r in DATA.get(k, []):
        keys += r[1]; act += r[3]; meq += mouseEquiv(r)
    return keys, act, meq

DAYS = sorted(DATA.keys())
ALL_KEYS = ALL_ACT = 0
totalWorkSpanSec = 0
for k in DAYS:
    keys, act, meq = dayTotals(k)
    ALL_KEYS += keys; ALL_ACT += act
    fM = lM = -1
    for r in DATA[k]:
        if r[1] > 0 or r[4] > 0 or r[5] > 0 or r[6] > 0:
            if fM < 0: fM = r[0]
            lM = r[0]
    if fM >= 0:
        totalWorkSpanSec += (lM - fM) * 60

daysN = len(DAYS) or 1
avgActiveHours = (ALL_ACT / 3600) / daysN
avgKeys = ALL_KEYS / daysN
activeRatio = (ALL_ACT / totalWorkSpanSec * 100) if totalWorkSpanSec > 0 else 0

print('=== 头部三卡（Python 独立重算，与报告 JS 同口径）===')
print('  数据天数 DAY_KEYS.length = %d' % daysN)
print('  ① 日均活跃时长 = %.2f 小时  （全周期活跃 %.2f 小时 ÷ %d 天）'
      % (avgActiveHours, ALL_ACT/3600, daysN))
print('  ② 日均击键数 = %d 次/天    （全周期 %s 次 ÷ %d 天）'
      % (round(avgKeys), format(ALL_KEYS, ','), daysN))
print('  ③ 活跃时长占比 = %.1f%%    （活跃秒 %s ÷ 工作总秒 %s）'
      % (activeRatio, format(ALL_ACT, ','), format(totalWorkSpanSec, ',')))
print('      其中 工作总时长 = %.2f 小时（每天 首次活动分钟~末次活动分钟 之差，跨天累加）'
      % (totalWorkSpanSec/3600))

# ---------- 拼对照图 ----------
try:
    from PIL import Image, ImageDraw, ImageFont
    before = os.path.join(HERE, '_hero_before.png')
    after = os.path.join(HERE, '_hero_after.png')
    if os.path.exists(before) and os.path.exists(after):
        b = Image.open(before).convert('RGB')
        a = Image.open(after).convert('RGB')
        cropH = 430
        b = b.crop((0, 0, b.width, cropH))
        a = a.crop((0, 0, a.width, cropH))
        gap = 16; labelH = 30
        W = b.width + a.width + gap
        H = cropH + labelH
        out = Image.new('RGB', (W, H), (246, 244, 241))
        d = ImageDraw.Draw(out)
        # CJK 字体兜底
        font = None
        for fp in [r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyhbd.ttc']:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, 18); break
                except Exception: pass
        if font is None:
            font = ImageFont.load_default()
        d.text((8, 5), '改前（旧头部：总击键数 / 活跃时长 / 鼠标占比）', fill=(111,101,91), font=font)
        d.text((b.width + gap + 8, 5), '改后（新头部：日均活跃时长 / 日均击键数 / 活跃时长占比）', fill=(232,89,12), font=font)
        out.paste(b, (0, labelH))
        out.paste(a, (b.width + gap, labelH))
        out_path = os.path.join(HERE, '_hero_ab.png')
        out.save(out_path)
        print('\n对照图已生成 ->', out_path)
    else:
        print('\n（缺少 before/after 截图，跳过拼图）')
except Exception as e:
    print('\n（拼图失败：%s）' % e)
