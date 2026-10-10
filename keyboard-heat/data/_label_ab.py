# -*- coding: utf-8 -*-
"""标签裁剪 A/B 验收：判据 = 「去掉容器裁剪」与「带着裁剪」的渲染必须完全一致。

做法（不用猜位置）：
  1. 对每个 dsf 先 measure 一次，拿到**首个可见月块的标签 rect**（随 CSS 候选而变）
  2. 渲两张图：A = 候选 CSS；B = 候选 CSS + `.cal-scroll{overflow:visible}`
     （overflow 不改变布局，所以两张图的几何应完全相同 —— 唯一差别就是"裁不裁"）
  3. 在标签带的像素窗口内逐行统计墨迹，比较两者的墨迹段
     - 完全相同 → 没被裁 ✓
     - B 比 A 多出像素（上方或下方）→ A 被裁了 ✗，并报出被裁几行

用法：
  python _label_ab.py                          # 跑基线 + 若干候选
  python _label_ab.py --cands "base" ".ym-label{line-height:14px}.ym-block{gap:2px}"
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_lab_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
UNCLIP = '.cal-scroll{overflow:visible}'

JS = r"""
<script>
(function(){
  function R(el){var b=el.getBoundingClientRect();
    return {t:+b.top.toFixed(2),b:+b.bottom.toFixed(2),l:+b.left.toFixed(2),r:+b.right.toFixed(2)};}
  var out={vw:window.innerWidth,cases:[]};
  ['year-cal','cd-cal'].forEach(function(id){
    var host=document.getElementById(id); if(!host) return;
    var blk=null;
    [].slice.call(host.children).forEach(function(b){
      if(!blk && b.style.display!=='none' && b.querySelector('.ym-label')) blk=b; });
    if(!blk) return;
    var lab=blk.querySelector('.ym-label'), lcs=getComputedStyle(lab);
    var grid=blk.querySelector('.ym-grid');
    out.cases.push({id:id,label:lab.textContent,labRect:R(lab),
      gridT:grid?+grid.getBoundingClientRect().top.toFixed(2):null,
      blkRect:R(blk),
      lineHeight:lcs.lineHeight, fontSize:lcs.fontSize,
      blockT:+blk.getBoundingClientRect().top.toFixed(2)});
  });
  var pre=document.createElement('pre'); pre.id='EGEO3';
  pre.textContent=JSON.stringify(out); document.body.appendChild(pre);
})();
</script>
"""


def build(css=''):
    src = open(SRC, encoding='utf-8').read()
    if css:
        src = src.replace('</head>', '<style id="_probe_css">'+css+'</style></head>', 1)
    src = src.replace('</body>', JS+'</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)


def chrome(args, w, h, dsf):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,%d' % (w, h), '--virtual-time-budget=3000']
    cmd += args + ['file:///' + TMP.replace('\\', '/')]
    return subprocess.run(cmd, capture_output=True).stdout.decode('utf-8', 'replace')


def measure(css, w, dsf):
    build(css)
    dump = chrome(['--dump-dom'], w, 900, dsf)
    m = re.search(r'<pre id="EGEO3">(.*?)</pre>', dump, re.S)
    if not m:
        return None
    return json.loads(htmllib.unescape(m.group(1)).strip())


def shot(css, w, h, dsf, path):
    build(css)
    chrome(['--screenshot='+os.path.abspath(path)], w, h, dsf)
    return path


def ink_rows(path, dsf, x0, x1, y0, y1, bgxy):
    im = Image.open(path).convert('RGB')
    bg = im.getpixel(bgxy)
    rows = [y for y in range(y0, y1)
            if sum(1 for x in range(x0, x1)
                   if sum(abs(a-b) for a, b in zip(im.getpixel((x, y)), bg)) > 14)]
    segs = []
    for y in rows:
        if not segs or y != segs[-1][-1]+1:
            segs.append([y])
        else:
            segs[-1].append(y)
    return segs, bg


def run(cand_css, tag, widths, dsfs, height=1600):
    print('\n================ 候选：%s ================' % tag)
    for wv in widths:
        for dsf in dsfs:
            info = measure(cand_css, wv, dsf)
            if not info or not info['cases']:
                print('  w=%d dsf=%g  测量失败' % (wv, dsf)); continue
            c = info['cases'][0]
            lr = c['labRect']
            # 看得见的 x 带：第 1 个月块左起 ~0.9 个月块宽
            x0 = int((lr['l']-4)*dsf); x1 = int((lr['r']-2)*dsf)
            y0 = int((lr['t']-8)*dsf); y1 = int((lr['t']+16)*dsf)
            bgxy = (int((lr['r']+40)*dsf), int((lr['t']-5)*dsf))
            a = shot(cand_css, wv, height, dsf, '_abA_%g.png' % dsf)
            b = shot(cand_css + '\n' + UNCLIP, wv, height, dsf, '_abB_%g.png' % dsf)
            sa, _ = ink_rows(a, dsf, x0, x1, y0, y1, bgxy)
            sb, bg = ink_rows(b, dsf, x0, x1, y0, y1, bgxy)
            fa = sa[0] if sa else []
            fb = sb[0] if sb else []
            # 用"多出来的像素行"判裁没裁
            extra_top = (fb[0]-fa[0]) if (fa and fb) else 0
            extra_bot = (fb[-1]-fa[-1]) if (fa and fb) else 0
            same = (fa == fb)
            print('  w=%-5d dsf=%-5g lh=%-8s 标签盒高 %5.2f | 带裁剪墨迹 %d 行 | 去裁剪 %d 行 | %s'
                  % (wv, dsf, c['lineHeight'], lr['b']-lr['t'], len(fa), len(fb),
                     '✓ 一致（没被裁）' if same else
                     '✗ 被裁：上 %+d / 下 %+d 设备行' % (extra_top, extra_bot)))
            if not same:
                print('         A 段 %s\n         B 段 %s' % (['%d..%d'%(s[0],s[-1]) for s in sa],
                                                             ['%d..%d'%(s[0],s[-1]) for s in sb]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--widths', default='1144')
    ap.add_argument('--dsfs', default='1,1.25,1.5,2')
    ap.add_argument('--cands', nargs='*', default=[
        'base',
        '.ym-label{line-height:14px}.ym-block{gap:2px}',
        '.ym-label{line-height:15px}.ym-block{gap:1px}',
        '.ym-label{line-height:normal}',
    ])
    a = ap.parse_args()
    widths = [int(x) for x in a.widths.split(',')]
    dsfs = [float(x) for x in a.dsfs.split(',')]
    for cand in a.cands:
        css = '' if cand == 'base' else cand
        run(css, cand, widths, dsfs)


if __name__ == '__main__':
    main()
