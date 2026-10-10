# -*- coding: utf-8 -*-
"""标题行探针：量「卡片标题行」右侧空掉多少。

背景：面板里的标题行长这样 `<div class="row"><span class="title">按类型分布</span>
<span class="meta">三种时长各自被启动的次数（…）</span></div>` —— 两个 span 左对齐
挤在一起，标题短、注释也短，于是**整行右侧一大段空白**，观感是"这块没做完"。
目视能看出"空"，但空多少必须量。

手法与 `_density_probe.py` 一致：读产物 -> 注入测量脚本 -> 无头 Chrome
`--dump-dom` -> 抠 <pre id="EGEOM"> 里的 JSON。

判据（每行）：
  wasteR   右侧空白 = 容器内容右缘 − 注释墨迹右缘
  gap      标题墨迹右缘 → 注释墨迹左缘 的空档（右对齐后这里会变大，属预期）
  lines    注释占几个行盒（>1 = 换行了，右对齐可能变难看，要单独看）
  over     行内横向溢出（>0 = 注释撑破了容器）
  alignL   标题墨迹左缘 − 容器内容左缘（应 ≈ 0，修复不许把左边也带跑）
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_headrow_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

MEASURE_JS = r"""<script>
(function(){
  function rect(el){ var r=el.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  /* 文字「墨迹」盒：Range.selectNodeContents 量字形实际占的矩形，不是行盒。 */
  function ink(el){ var rg=document.createRange(); rg.selectNodeContents(el);
    var r=rg.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  function box(el){ var cs=getComputedStyle(el), r=el.getBoundingClientRect();
    var pl=parseFloat(cs.paddingLeft)||0, pr=parseFloat(cs.paddingRight)||0,
        bl=parseFloat(cs.borderLeftWidth)||0, br=parseFloat(cs.borderRightWidth)||0;
    return {L:r.left+bl+pl, R:r.right-br-pr, w:r.width-pl-pr-bl-br}; }
  function lines(el){ return el.getClientRects().length; }
  /* 参考物 = 标题行下面那块「内容」的内容盒右缘（面板要剥掉 padding）。
     右对齐的意义在于「注释右缘 ↔ 图表内容右缘」同一条竖线，
     若两者本来就不在一条线上，右对齐只会制造新的错位（故量 flushR）。 */
  function refR(el){
    var n=el.nextElementSibling; if(!n) return null;
    return +box(n).R.toFixed(1);
  }
  var out={vw:innerWidth, dpr:devicePixelRatio, rows:[]};

  /* ① 面板标题行 .row（title + meta） */
  [].slice.call(document.querySelectorAll('.row')).forEach(function(row){
    var t=row.querySelector('.title'), m=row.querySelector('.meta');
    if(!t||!m) return;
    var b=box(row), ti=ink(t), mi=ink(m), rf=refR(row);
    out.rows.push({kind:'row', t:t.textContent.trim(), m:m.textContent.trim(),
      contR:+b.R.toFixed(1),
      wasteR:+(b.R-(mi.l+mi.w)).toFixed(1),
      gap:+(mi.l-(ti.l+ti.w)).toFixed(1),
      alignL:+(ti.l-b.L).toFixed(1),
      flushR:rf==null?null:+(b.R-rf).toFixed(1),
      /* 换行判定：注释顶落到标题**下一行**才算换行；阈值随字号走（字号不同时基线对齐
         也会让墨迹 top 差几 px，写死 2px 会误判）。 */
      wrap:(mi.t>ti.t+Math.max(ti.h,mi.h)*0.5)?1:0,
      lines:lines(m), over:+(row.scrollWidth-row.clientWidth).toFixed(0),
      mW:+mi.w.toFixed(1)});
  });

  /* ② 小节标题 h2（标题 + 副标题 span），量副标题右侧留白 */
  [].slice.call(document.querySelectorAll('h2')).forEach(function(h){
    var sp=h.querySelector('span'); if(!sp) return;
    var b=box(h), si=ink(sp), rf=refR(h);
    out.rows.push({kind:'h2', t:h.childNodes[0].textContent.trim(), m:sp.textContent.trim(),
      contR:+b.R.toFixed(1),
      wasteR:+(b.R-(si.l+si.w)).toFixed(1),
      gap:0, alignL:+(sp.getBoundingClientRect().left-b.L).toFixed(1),
      flushR:rf==null?null:+(b.R-rf).toFixed(1),
      lines:lines(sp), over:+(h.scrollWidth-h.clientWidth).toFixed(0),
      mW:+si.w.toFixed(1)});
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
                          '<style id="_headrow_css">' + extra_css + '</style></head>', 1)
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
# 右侧空白容忍度：注释右缘贴容器内容右缘（差 2px 内算对齐）
TOL = 2


def show(r):
    if not r:
        return
    vw = r['vw'] - 16      # 无头 Chrome 的测量视口比 --window-size 窄 16
    print('=== [%s] 视口 %d (dpr %g) ===' % (r.get('_name', ''), vw, r['dpr']))
    print('  %-4s %-14s %6s %6s %6s | %5s %5s %5s %6s'
          % ('类型', '标题', '注释宽', '右空', '标题→注', '行数', '左偏', '溢出', 'flushR'))
    for x in r['rows']:
        flag = ''
        if x['kind'] == 'row':
            if x['wasteR'] > TOL:
                flag = '  ★右空'
                BAD.append('%s 注释右空 %.0fpx' % (x['t'], x['wasteR']))
            if x['alignL'] > TOL:
                flag += '  ★左偏'
                BAD.append('%s 标题左偏 %.0fpx' % (x['t'], x['alignL']))
        if x['over'] > 0:
            flag += '  ★溢出'
            BAD.append('%s 行内溢出 %dpx' % (x['t'], x['over']))
        if x['lines'] > 1:
            flag += '  (%d 行)' % x['lines']
        if x.get('wrap'):
            flag += '  ↳注释换到第2行'
        print('  %-4s %-14s %6.0f %6.0f %6.0f | %5d %5.0f %5d %6s%s'
              % (x['kind'], x['t'][:14], x['mW'], x['wasteR'], x['gap'],
                 x['lines'], x['alignL'], x['over'],
                 '--' if x['flushR'] is None else '%+.0f' % x['flushR'], flag))
    rows = [x for x in r['rows'] if x['kind'] == 'row']
    if rows:
        print('  面板标题行注释平均右空 %.0fpx（共 %d 行）'
              % (sum(x['wasteR'] for x in rows) / len(rows), len(rows)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--widths', default='1280,900,760,620,390')
    ap.add_argument('--dsf', type=float, default=1)
    ap.add_argument('--css', default='', help='实验 CSS：量候选标注的真实位置')
    ap.add_argument('--pre', default='', help='实验 JS：测量前重建 DOM')
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
    else:
        print('\n全绿')


if __name__ == '__main__':
    main()
