# -*- coding: utf-8 -*-
"""「总览」信息密度：候选方向的改前/改后对照图。

三个方向：
  0 现状       —— 双行卡，卡片按容器均分宽度（内容只占 27%）
  A 单行紧凑   —— 标签左、值右两端对齐 + 三组统一 4 列（列宽对齐）
  B 组内一行   —— 每组压成一条：组名在行首，指标横排、竖线分隔（密度最高）

每个方向真渲一张图（注入 CSS/JS 后无头 Chrome 截图），自动裁白后纵向拼接。
必须用带 PIL 的解释器跑：`../.pyenv/Scripts/python.exe _density_ab.py`
"""
import argparse
import os
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_probe_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
FONT = r'C:\Windows\Fonts\msyh.ttc'

ONLY_JS = """
(function(){var keep=document.getElementById('stats').closest('section');
 [].slice.call(document.querySelectorAll('header,.wrap > section,.wrap > .note'))
   .forEach(function(e){if(e!==keep)e.style.display='none';});
 document.querySelectorAll('#stats .stat').forEach(function(el){
   el.style.transition='none';});})();
"""

SL = ('.stat{display:flex;align-items:baseline;justify-content:space-between;'
      'gap:12px;padding:10px 14px;transition:none}'
      '.stat:hover{transform:none;box-shadow:none}'
      '.stat .k{margin-bottom:0}.stat .v{font-size:18px}')

VARIANTS = [
    ('0 现状：双行卡 · 卡宽随容器均分', '', ''),
    ('A 单行紧凑：标签左/值右 + 三组统一 4 列',
     SL + '.cluster-grid{grid-template-columns:repeat(4,minmax(0,1fr))}', ''),
    ('B 组内一行：组名在行首，指标横排',
     SL + """
.cluster{display:flex;align-items:center;margin-bottom:0;padding:8px 0;
  border-top:1px solid var(--line)}
.cluster:last-child{border-bottom:1px solid var(--line)}
.cluster-h{margin:0;flex:0 0 78px;width:78px;font-size:12px}
.cluster-grid{display:flex;flex:1;gap:0;min-width:0;grid-template-columns:none}
.stat{background:none;border:none;border-radius:0;box-shadow:none;
  flex:1 1 0;min-width:0;padding:0 12px}
.stat+.stat{border-left:1px solid var(--line-soft)}
.stat .k{font-size:11.5px}
.stat .v{font-size:16px}
""", ''),
]


def build(css):
    src = open(SRC, encoding='utf-8').read()
    if css:
        src = src.replace('</head>', '<style id="_ab_css">' + css + '</style></head>', 1)
    src = src.replace('</body>', '<script>' + ONLY_JS + '</script></body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)


def shot(out, width, dsf=2):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,900' % width, '--virtual-time-budget=3000',
           '--screenshot=' + out, 'file:///' + TMP.replace('\\', '/')]
    subprocess.run(cmd, capture_output=True)
    return out


def trim(im, pad=14):
    """裁掉背景留白：底色取整图众数色，再找非底色的包围盒。"""
    im = im.convert('RGB')
    cols = im.getcolors(maxcolors=1 << 24) or []
    bg = max(cols)[1] if cols else (255, 255, 255)
    px = im.load()
    w, h = im.size
    box = None
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if abs(p[0] - bg[0]) + abs(p[1] - bg[1]) + abs(p[2] - bg[2]) > 12:
                box = (x, y, x + 1, y + 1) if box is None else (
                    min(box[0], x), min(box[1], y), max(box[2], x + 1), max(box[3], y + 1))
    if not box:
        return im, bg
    l, t, r, b = box
    l = max(0, l - pad); t = max(0, t - pad)
    r = min(w, r + pad); b = min(h, b + pad)
    return im.crop((l, t, r, b)), bg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--out', default=os.path.join(HERE, '_density_ab.png'))
    a = ap.parse_args()
    tiles = []
    for name, css, _ in VARIANTS:
        build(css)
        raw = os.path.join(HERE, '_ab_tmp.png')
        shot(raw, a.width)
        im, bg = trim(Image.open(raw))
        tiles.append((name, im, bg))
        print('  %-40s %dx%d' % (name, im.size[0], im.size[1]))
    os.remove(os.path.join(HERE, '_ab_tmp.png'))

    try:
        font = ImageFont.truetype(FONT, 15)
    except Exception:
        font = ImageFont.load_default()
    gap, barh = 26, 30
    W = max(t[1].size[0] for t in tiles)
    H = sum(t[1].size[1] + barh for t in tiles) + gap * len(tiles)
    out = Image.new('RGB', (W, H), tiles[0][2])
    dr = ImageDraw.Draw(out)
    y = 0
    for name, im, bg in tiles:
        dr.rectangle([0, y, W, y + barh], fill=(40, 40, 40))
        dr.text((10, y + 6), name, font=font, fill=(255, 255, 255))
        y += barh
        out.paste(im, (0, y)); y += im.size[1] + gap
    out.save(a.out)
    print('→ ' + a.out)


if __name__ == '__main__':
    main()
