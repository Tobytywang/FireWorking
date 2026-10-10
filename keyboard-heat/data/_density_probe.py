# -*- coding: utf-8 -*-
"""信息密度探针：量「总览」KPI 卡片把多少面积真正用来承载信息。

背景：`.stat` 卡片是 `padding:14px 16px` 的盒子，里面只有一个 12px 灰标签
（`.k`）和一个 22px 数值（`.v`）。卡片宽度由 `repeat(auto-fit,minmax(150px,1fr))`
撑满容器 —— 于是**卡越宽、右边空白越多**：数值只有 ~60px 宽，卡片却有 200+px。
观感是「信息密度差」，但目视说不清差多少，只能量。

手法与 `_ui_geom_probe.py` 一致：读产物 -> 注入测量脚本 -> 无头 Chrome
`--dump-dom` -> 抠 <pre id="EGEOM"> 里的 JSON。

判据（每张卡）：
  hFill   横向填充率 = 墨迹宽 / 内容区宽
  vFill   纵向填充率 = 墨迹高 / 内容区高
  areaFill 面积利用率 = 墨迹面积 / 卡片面积
  wasteR  右侧空白（内容区右缘 − 墨迹右缘）
  wasteB  底部空白（内容区底缘 − 墨迹底缘）
判据（整块）：
  colW 离散度 —— 三个组的卡片宽度是否一致（不一致则跨组列对不齐）
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_probe_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

MEASURE_JS = r"""<script>
(function(){
  function rect(el){ if(!el) return null; var r=el.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  /* 文字「墨迹」盒：Range.selectNodeContents 量的是字形实际占的矩形，不是行盒。 */
  function ink(el){ if(!el) return null; var rg=document.createRange();
    rg.selectNodeContents(el); var r=rg.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  var host=document.getElementById('stats'); if(!host) return;
  var sec=host.closest('section');
  var out={vw:innerWidth, dpr:devicePixelRatio, sec:rect(sec), tiles:[], donuts:[]};
  /* 单块「墨迹」= 文字（标签/标题/值/脚注/环图注）的并集 + 环图盒子。
     铺地砖布局里主砖含环图（图形元素），必须计入，否则面积利用率被低估。 */
  function tileInk(c){
    var xs=[],ys=[];
    ['.k','.comp-h','.v','.comp-foot','.dlab','.wside'].forEach(function(sel){
      var e=c.querySelector(sel); if(e){ var r=ink(e); xs.push(r.l,r.l+r.w); ys.push(r.t,r.t+r.h);} });
    [].slice.call(c.querySelectorAll('.donut')).forEach(function(d){
      var r=d.getBoundingClientRect(); xs.push(r.left,r.left+r.width); ys.push(r.top,r.top+r.height);});
    if(!xs.length) return null;
    return {l:Math.min.apply(null,xs),t:Math.min.apply(null,ys),
      w:Math.max.apply(null,xs)-Math.min.apply(null,xs),
      h:Math.max.apply(null,ys)-Math.min.apply(null,ys)};
  }
  [].slice.call(host.querySelectorAll('.tile')).forEach(function(c){
    var cs=getComputedStyle(c), cr=c.getBoundingClientRect();
    var padL=parseFloat(cs.paddingLeft), padR=parseFloat(cs.paddingRight),
        padT=parseFloat(cs.paddingTop), padB=parseFloat(cs.paddingBottom);
    var ik=tileInk(c)||{l:cr.left+padL,t:cr.top+padT,w:0,h:0};
    var cl=cr.left+padL, ct=cr.top+padT, cw=cr.width-padL-padR, ch=cr.height-padT-padB;
    var isComp=c.classList.contains('comp');
    var lbl=isComp?'输入构成':(c.querySelector('.k')?c.querySelector('.k').textContent.trim():'');
    var val=isComp?(c.querySelector('.comp-foot')?c.querySelector('.comp-foot').textContent.trim():''):(c.querySelector('.v')?c.querySelector('.v').textContent.trim():'');
    out.tiles.push({comp:isComp,lbl:lbl,val:val,
      w:+cr.width.toFixed(1),h:+cr.height.toFixed(1),
      contentW:+cw.toFixed(1),contentH:+ch.toFixed(1),
      inkW:+ik.w.toFixed(1),inkH:+ik.h.toFixed(1),
      hFill:+(ik.w/cw*100).toFixed(1),vFill:+(ik.h/ch*100).toFixed(1),
      areaFill:+(ik.w*ik.h/(cr.width*cr.height)*100).toFixed(1),
      wasteR:+((cl+cw)-(ik.l+ik.w)).toFixed(1),wasteB:+((ct+ch)-(ik.t+ik.h)).toFixed(1),
      over:+(c.scrollWidth-c.clientWidth).toFixed(0)});
  });
  [].slice.call(host.querySelectorAll('.donut')).forEach(function(d){
    var r=d.getBoundingClientRect();
    out.donuts.push({w:+r.width.toFixed(1),h:+r.height.toFixed(1),
      p:+(parseFloat(d.style.getPropertyValue('--p'))||0).toFixed(1),
      c:d.style.getPropertyValue('--c')});
  });
  var pre=document.createElement('pre'); pre.id='EGEOM';
  pre.style.display='none'; pre.textContent=JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>"""


def build(extra_css='', pre_js=''):
    src = open(SRC, encoding='utf-8').read()
    if extra_css:
        src = src.replace('</head>',
                          '<style id="_density_css">' + extra_css + '</style></head>', 1)
    pre = '<script>' + pre_js + '</script>' if pre_js else ''
    src = src.replace('</body>', pre + MEASURE_JS + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)


def chrome(args, width, height, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,%d' % (width, height), '--virtual-time-budget=3000']
    cmd += args + ['file:///' + TMP.replace('\\', '/')]
    return subprocess.run(cmd, capture_output=True).stdout.decode('utf-8', 'replace')


def measure(width, dsf=1):
    dump = chrome(['--dump-dom'], width, 900, dsf)
    m = re.search(r'<pre id="EGEOM"[^>]*>(.*?)</pre>', dump, re.S)
    if not m:
        print('!! 没拿到测量块，dump 长度 %d' % len(dump))
        return None
    return json.loads(htmllib.unescape(m.group(1)).strip())


BAD = []


def show(r):
    if not r:
        return
    vw = r['vw'] - 16      # 无头 Chrome 的测量视口比 --window-size 窄 16
    print('=== [%s] 视口 %d (dpr %g) ===' % (r.get('_name', ''), vw, r['dpr']))
    comp = [t for t in r['tiles'] if t['comp']]
    print('  [总览] section 高 %.0f | 砖数 %d（含主砖 %d）'
          % (r['sec']['h'], len(r['tiles']), len(comp)))
    if r['donuts']:
        ds = ', '.join('%.0f%%' % d['p'] for d in r['donuts'])
        sz = r['donuts'][0]['w']
        bad = any(d['w'] < 40 for d in r['donuts'])
        print('  环图: %d 个，尺寸 %.0fpx，占比 %s %s'
              % (len(r['donuts']), sz, ds, '★ 未渲染/占比为0' if bad else '✓'))
        if bad:
            BAD.append('环图未渲染或占比为0')
    print('  %-10s %-9s %5s %5s | %5s %5s %6s | %6s %6s | %5s'
          % ('标签', '值', '宽', '高', 'hFill', 'vFill', 'areaFill', '右空', '底空', '溢出'))
    for c in r['tiles']:
        print('  %-10s %-9s %5.0f %5.0f | %4.0f%% %4.0f%% %5.0f%% | %5.0f %6.0f | %5.0f'
              % (c['lbl'][:10], c['val'][:8], c['w'], c['h'], c['hFill'], c['vFill'],
                 c['areaFill'], c['wasteR'], c['wasteB'], c['over']))
        if c['over'] > 0:
            BAD.append('砖内溢出 %dpx（%s）' % (c['over'], c['lbl']))
    n = len(r['tiles'])
    mh = sum(c['hFill'] for c in r['tiles']) / n
    mv = sum(c['vFill'] for c in r['tiles']) / n
    ma = sum(c['areaFill'] for c in r['tiles']) / n
    mwr = sum(c['wasteR'] for c in r['tiles']) / n
    print('  均值: hFill %.0f%%  vFill %.0f%%  面积利用率 %.0f%%  | 平均右侧空白 %.0fpx'
          % (mh, mv, ma, mwr))
    return {'hFill': mh, 'vFill': mv, 'areaFill': ma, 'wasteR': mwr}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--widths', default='1280,1113,900,760,620')
    ap.add_argument('--dsf', type=float, default=1)
    ap.add_argument('--css', default='', help='实验 CSS：量候选布局的真实密度')
    ap.add_argument('--pre', default='', help='实验 JS：测量前重建 DOM（量结构性方案）')
    ap.add_argument('--name', default='现状')
    a = ap.parse_args()
    build(a.css, a.pre)
    for w in [int(x) for x in a.widths.split(',')]:
        r = measure(w, a.dsf)
        if r:
            r['_name'] = a.name
        show(r)
    if BAD:
        print('\n★ 共 %d 处报红' % len(BAD))


if __name__ == '__main__':
    main()
