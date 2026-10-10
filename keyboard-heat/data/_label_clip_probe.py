# -*- coding: utf-8 -*-
"""月份标签（.ym-label）上下被裁的专用探针。

疑点假设（待实测证伪）：
  `.cal-scroll{overflow-x:auto}` 是经典陷阱 —— **一个轴设成非 visible，
  另一轴的 computed 值会从 visible 变成 auto**，于是它同时成了纵向滚动容器，
  把溢出的字形裁掉。而 `.ym-label{line-height:1}` 让行盒只有 1em（11px），
  字体真实 ascent+descent 通常 > 1em，字形上下都会"冒"出行盒。

量四件事：
  1. 容器 computed overflowX/overflowY（证明它是不是纵向滚动容器）
  2. 容器 clientHeight / scrollHeight / offsetHeight（有没有内容被裁）
  3. 标签行盒 rect 与容器 rect 的关系
  4. canvas TextMetrics 拿**同字体同字号的真实墨迹边界**
     （actualBoundingBoxAscent/Descent）与行盒对比 —— 这才是"被裁多少"的真值

用法：
  python _label_clip_probe.py
  python _label_clip_probe.py --css ".ym-label{line-height:1.6}"
  python _label_clip_probe.py --shot _lab.png --zoom 5
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_lab_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

JS = r"""
<script>
(function(){
  function R(el){var b=el.getBoundingClientRect();
    return {t:+b.top.toFixed(2),b:+b.bottom.toFixed(2),h:+b.height.toFixed(2),
            l:+b.left.toFixed(2),r:+b.right.toFixed(2),w:+b.width.toFixed(2)};}
  var out={vw:window.innerWidth,cases:[]};
  var cv=document.createElement('canvas'), ctx=cv.getContext('2d');
  ['year-cal','cd-cal'].forEach(function(id){
    var host=document.getElementById(id); if(!host) return;
    var scroll=host.parentElement, scs=getComputedStyle(scroll);
    var blk=null;
    [].slice.call(host.children).forEach(function(b){
      if(!blk && b.style.display!=='none' && b.querySelector('.ym-label')) blk=b; });
    if(!blk) return;
    var lab=blk.querySelector('.ym-label'), lcs=getComputedStyle(lab);
    var grid=blk.querySelector('.ym-grid');
    var lr=R(lab), sr=R(scroll), br=R(blk), gr=grid?R(grid):null;
    var lhPx = lcs.lineHeight==='normal' ? null : parseFloat(lcs.lineHeight);
    /* 行盒内基线的位置：顶 + 半行距 + fontAscent，其中 fontAscent/Descent 来自字体 box */
    ctx.font=[lcs.fontStyle,lcs.fontWeight,lcs.fontSize,lcs.fontFamily].join(' ');
    var m=ctx.measureText(lab.textContent);
    var fA=m.fontBoundingBoxAscent, fD=m.fontBoundingBoxDescent;
    var iA=m.actualBoundingBoxAscent, iD=m.actualBoundingBoxDescent;
    var half=(lhPx!=null)?(lhPx-(fA+fD))/2:0;       /* 负值 = 字形半行距被压缩 */
    var baseY = lr.t + half + fA;                    /* 推断的基线 y */
    var inkTop = baseY - iA, inkBot = baseY + iD;    /* 墨迹真实上下沿 */
    out.cases.push({
      id:id, label:lab.textContent,
      overflowX:scs.overflowX, overflowY:scs.overflowY,
      scrollRect:sr, clientH:scroll.clientHeight, scrollH:scroll.scrollHeight,
      offsetH:scroll.offsetHeight, padT:scs.paddingTop, padB:scs.paddingBottom,
      blkRect:br, gridRect:gr, labRect:lr,
      fontSize:parseFloat(lcs.fontSize), lineHeight:lcs.lineHeight, lineHeightPx:lhPx,
      fontFamily:lcs.fontFamily,
      fontAscent:+fA.toFixed(2), fontDescent:+fD.toFixed(2),
      inkAscent:+iA.toFixed(2), inkDescent:+iD.toFixed(2),
      halfLeading:+half.toFixed(2), baseY:+baseY.toFixed(2),
      inkTop:+inkTop.toFixed(2), inkBot:+inkBot.toFixed(2),
      /* 关键三量 */
      overflowAbove:+(sr.t-inkTop).toFixed(2),   /* >0 → 墨迹冒到容器上沿之外（被裁） */
      overflowBelow:+(inkBot-sr.b).toFixed(2),   /* >0 → 冒到下沿之外 */
      lineBoxOverflowAbove:+((lr.t-inkTop)).toFixed(2),   /* >0 → 墨迹冒出行盒上方 */
      lineBoxOverflowBelow:+((inkBot-lr.b)).toFixed(2),
      gapToGrid:gr?+(gr.t-lr.b).toFixed(2):null
    });
  });
  var pre=document.createElement('pre'); pre.id='EGEO2';
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


def chrome(args, w, h, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
           '--hide-scrollbars', '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,%d' % (w, h), '--virtual-time-budget=3000']
    cmd += args + ['file:///' + TMP.replace('\\', '/')]
    return subprocess.run(cmd, capture_output=True).stdout.decode('utf-8', 'replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--css', default='')
    ap.add_argument('--width', type=int, default=1144)
    ap.add_argument('--height', type=int, default=900,
                    help='截图窗口高（放大时记得调高，否则日历在折叠线以下拍不到）')
    ap.add_argument('--shot', default='')
    ap.add_argument('--zoom', type=int, default=1)
    ap.add_argument('--dsf', type=float, default=1.0,
                    help='device scale factor（1.5 = Windows 150%% 缩放，分数 DPR 会暴露裁剪取整问题）')
    a = ap.parse_args()
    build(a.css)
    if a.shot:
        target = os.path.abspath(a.shot)
        args = ['--screenshot='+target]
        chrome(args, a.width, a.height, a.dsf)
        print('shot -> %s  (图像 = %g x %g 倍窗口)' % (target, a.width*a.dsf, a.height*a.dsf))
        return
    dump = chrome(['--dump-dom'], a.width, a.height, a.dsf)
    m = re.search(r'<pre id="EGEO2">(.*?)</pre>', dump, re.S)
    if not m:
        print('!! 没拿到测量块，len=%d' % len(dump)); print(dump[:500]); return
    r = json.loads(htmllib.unescape(m.group(1)).strip())
    print('viewport %d' % r['vw'])
    for c in r['cases']:
        print('\n[%s] 首个可见月块标签 = %r' % (c['id'], c['label']))
        print('  容器 overflowX/Y = %s / %s   (⚠ 任一轴非 visible → 另一轴 computed 变 auto)'
              % (c['overflowX'], c['overflowY']))
        print('  容器  top %.2f  bottom %.2f  h %.2f | clientH %d  scrollH %d  offsetH %d  padT/B %s/%s'
              % (c['scrollRect']['t'], c['scrollRect']['b'], c['scrollRect']['h'],
                 c['clientH'], c['scrollH'], c['offsetH'], c['padT'], c['padB']))
        print('  月块  top %.2f  bottom %.2f  h %.2f' % (c['blkRect']['t'], c['blkRect']['b'], c['blkRect']['h']))
        print('  标签  top %.2f  bottom %.2f  h %.2f  left %.2f  right %.2f  (font-size %g, line-height %s = %s)'
              % (c['labRect']['t'], c['labRect']['b'], c['labRect']['h'],
                 c['labRect']['l'], c['labRect']['r'],
                 c['fontSize'], c['lineHeight'], c['lineHeightPx']))
        print('  字体 %s' % c['fontFamily'])
        print('  字体box ascent %.2f descent %.2f → 合计 %.2f；行盒 %.2f → 半行距 %+.2f'
              % (c['fontAscent'], c['fontDescent'],
                 c['fontAscent']+c['fontDescent'], c['lineHeightPx'], c['halfLeading']))
        print('  推断基线 y=%.2f ；墨迹 ascent %.2f descent %.2f → 墨迹 [%.2f, %.2f]'
              % (c['baseY'], c['inkAscent'], c['inkDescent'], c['inkTop'], c['inkBot']))
        print('  ★ 墨迹超出行盒：上方 %+.2f  下方 %+.2f' % (c['lineBoxOverflowAbove'], c['lineBoxOverflowBelow']))
        print('  ★ 墨迹超出**容器**：上方 %+.2f  下方 %+.2f  (>0 即被裁)'
              % (c['overflowAbove'], c['overflowBelow']))
        print('  标签底 到 网格顶 间距 %s' % c['gapToGrid'])


if __name__ == '__main__':
    main()
