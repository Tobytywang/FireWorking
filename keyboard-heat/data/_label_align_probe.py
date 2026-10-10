# -*- coding: utf-8 -*-
"""标题探针：量每张卡片的「标签/标题」是否够深、与右上角标是否顶对齐。

背景：所有砖共用 `.tile .k{color:var(--fg3)}`（#a3988c），而右上角标 `.tk` 是
绝对定位 `top:11px`。于是有两个只能量、不能靠目视断言的问题：
  ① 标题色 `--fg3` 在白底上对比度只有 ~2.8:1（低于 WCAG AA 的 4.5:1）→「太浅」；
  ② 标题墨迹顶边比角标墨迹顶边低几个 px →「上边沿没对齐、离 TOP 太远」。

手法与 `_density_probe.py` 一致：读产物 -> 注入测量脚本 -> 无头 Chrome
`--dump-dom` -> 抠 <pre id="EGEOM"> 里的 JSON。

判据（卡片内的「标题」= 普通砖的 `.k` / 主砖的 `.comp-h`）：
  dTop   = 标题墨迹顶边 − 右上角标墨迹顶边   （距各卡**自身顶边**算，跨卡可比）→ 期望 |dTop| ≤ 1px
  kTop   = 标题墨迹顶边 − 卡片顶边           → 同组内应当完全一致
  ratio  = 标题色 vs 卡片底色 的 WCAG 对比度 → 期望 ≥ 4.5（AA 正文）
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_label_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 三组卡片的宿主：hero 三卡 / 总览铺砖 / 倒计时四卡
GROUPS = [('hero', '#hero-stats'), ('总览', '#stats'), ('倒计时', '#cd-stats')]

MEASURE_JS = r"""<script>
(function(){
  function rect(el){ if(!el) return null; var r=el.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  /* 文字「墨迹」盒：Range.selectNodeContents 量字形实际矩形，不是行盒。 */
  function ink(el){ if(!el) return null; var rg=document.createRange();
    rg.selectNodeContents(el); var r=rg.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  function rgb(s){ var m=/rgba?\(([^)]+)\)/.exec(s); if(!m) return null;
    var a=m[1].split(',').map(function(x){return parseFloat(x);}); return [a[0],a[1],a[2]]; }
  /* ⚠ 卡底别读 .tile 的 computed backgroundColor：`.tile{transition:.2s}` 对 background-color
     也生效，同一 tick 内切主题（注入 _dark.js）会读到**过渡起点的白底** → 暗色对比度假性偏低。
     卡底就是 var(--card)，自定义属性不参与过渡，从 :root 读即刻生效。 */
  function anyColor(s){ s=(s||'').trim();
    if(s.charAt(0)==='#'){
      if(s.length===5) s='#'+s[1]+s[1]+s[2]+s[2]+s[3]+s[3];   /* #abc（本页无，但别假设长度 7） */
      if(s.length===7) return [parseInt(s.substr(1,2),16),parseInt(s.substr(3,2),16),parseInt(s.substr(5,2),16)];
      return null; }
    return rgb(s); }
  var CARD_BG=anyColor(getComputedStyle(document.documentElement).getPropertyValue('--card'));
  /* WCAG 相对亮度与对比度 */
  function lum(c){ var f=c.map(function(v){ v/=255;
    return v<=0.03928? v/12.92 : Math.pow((v+0.055)/1.055,2.4); });
    return 0.2126*f[0]+0.7152*f[1]+0.0722*f[2]; }
  function ratio(fg,bg){ var a=lum(fg),b=lum(bg);
    return +(((Math.max(a,b)+0.05)/(Math.min(a,b)+0.05))).toFixed(2); }

  var GROUPS=__GROUPS__;
  var out={vw:innerWidth, dpr:devicePixelRatio, groups:[]};
  GROUPS.forEach(function(g){
    var host=document.querySelector(g[1]); if(!host) return;
    var tiles=[].slice.call(host.querySelectorAll('.tile'));
    if(!tiles.length) return;
    var recs=[];
    tiles.forEach(function(c){
      var cs=getComputedStyle(c), cr=c.getBoundingClientRect();
      var isComp=c.classList.contains('comp');
      var lblEl=isComp? c.querySelector('.comp-h') : c.querySelector('.k');
      var tagEl=c.querySelector('.tk');
      if(!lblEl) return;
      var li=ink(lblEl), ti=tagEl?ink(tagEl):null;
      var vEl=c.querySelector('.v');              /* 大号数字（值锚点）；主砖没有 .v */
      var vi=vEl?ink(vEl):null;
      var vr=vEl?vEl.getBoundingClientRect():null;   /* ⚠ 用**行盒**不用墨迹框：
         墨迹框是字形并集，受内容影响（「8.6万」vs「13.2小时」差 5px），量的是字不是位置。 */
      var cBot=cr.bottom-parseFloat(cs.paddingBottom)-(parseFloat(cs.borderBottomWidth)||0);
      var fg=rgb(getComputedStyle(lblEl).color), bg=CARD_BG||rgb(cs.backgroundColor);
      var tagFg=tagEl?getComputedStyle(tagEl).color:'';
      recs.push({
        comp:isComp, tk:tagEl?tagEl.textContent.trim():'',
        lbl:lblEl.textContent.trim().slice(0,14),
        val:vEl?vEl.textContent.trim().slice(0,10):'',
        color:getComputedStyle(lblEl).color,
        tagColor:tagFg,
        size:parseFloat(getComputedStyle(lblEl).fontSize),
        cardH:+(cr.height).toFixed(1),
        /* 值锚点：vTop = 数值行盒顶边 − 卡顶；vBot = 卡内容盒底边 − 数值行盒底边。
           跨组要「和谐」就得让这两个数有共同取值（卡高一不同，space-between 的贴底项必然错位）。 */
        vTop:vr?+(vr.top-cr.top).toFixed(1):null,
        vBot:vr?+(cBot-vr.bottom).toFixed(1):null,
        vH:vr?+vr.height.toFixed(1):null,
        vInkTop:vi?+(vi.t-cr.top).toFixed(1):null,
        kTop:+(li.t-cr.top).toFixed(1),
        tkTop:ti?+(ti.t-cr.top).toFixed(1):null,
        dTop:ti?+((li.t-cr.top)-(ti.t-cr.top)).toFixed(1):null,
        alignL:+(li.l-(cr.left+parseFloat(cs.paddingLeft))).toFixed(1),
        ratio:(fg&&bg)?ratio(fg,bg):null,
        over:+(c.scrollWidth-c.clientWidth).toFixed(0)});
    });
    out.groups.push({name:g[0], n:recs.length, tiles:recs});
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
                          '<style id="_label_css">' + extra_css + '</style></head>', 1)
    pre = '<script>' + pre_js + '</script>' if pre_js else ''
    js = MEASURE_JS.replace('__GROUPS__', json.dumps(GROUPS))
    src = src.replace('</body>', pre + js + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)


def measure(width, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,900' % width, '--virtual-time-budget=3000',
           '--dump-dom', 'file:///' + TMP.replace('\\', '/')]
    dump = subprocess.run(cmd, capture_output=True).stdout.decode('utf-8', 'replace')
    m = re.search(r'<pre id="EGEOM"[^>]*>(.*?)</pre>', dump, re.S)
    if not m:
        print('!! 没拿到测量块，dump 长度 %d' % len(dump))
        return None
    return json.loads(htmllib.unescape(m.group(1)).strip())


BAD = []
VT = []         # 全页「值锚点」样本：(组名, 卡标签, vTop, vBot, cardH)
DTOL = 1.0      # 顶边差容差 px
RTOL = 4.5      # WCAG AA 正文对比度
VTOL = 2.0      # 值锚点跨组容差 px


def show(r):
    if not r:
        BAD.append('测量失败（没拿到测量块）')
        return
    del VT[:]
    vw = r['vw'] - 16
    print('=== [%s] 视口 %d (dpr %g) ===' % (r.get('_name', ''), vw, r['dpr']))
    for g in r['groups']:
        ts = g['tiles']
        dt = [t['dTop'] for t in ts if t['dTop'] is not None]
        kt = [t['kTop'] for t in ts]
        ch = [t['cardH'] for t in ts]
        vt = [t['vTop'] for t in ts if t['vTop'] is not None]
        vb = [t['vBot'] for t in ts if t['vBot'] is not None]
        vh = [t['vH'] for t in ts if t['vH'] is not None]
        # 主砖标题用的是 .comp-h（--fg 更深的「主标题」层级），不参与普通砖的「同色」检查
        col = set(t['color'] for t in ts if not t['comp'])
        rt = [t['ratio'] for t in ts if t['ratio'] is not None]
        print('  [%s] %d 张 | 标题色 %s | 对比度 %.2f–%.2f | kTop %.0f–%.0f | dTop %s'
              % (g['name'], g['n'], '/'.join(sorted(col)),
                 min(rt) if rt else 0, max(rt) if rt else 0,
                 min(kt), max(kt),
                 '%.0f–%.0f' % (min(dt), max(dt)) if dt else 'n/a'))
        print('         卡高 %.0f–%.0f | 值行盒 vTop %.0f–%.0f | vH %.0f–%.0f | vBot %.0f–%.0f'
              % (min(ch), max(ch),
                 min(vt) if vt else -1, max(vt) if vt else -1,
                 min(vh) if vh else -1, max(vh) if vh else -1,
                 min(vb) if vb else -1, max(vb) if vb else -1))
        for t in ts:
            flag = ''
            if t['dTop'] is not None and abs(t['dTop']) > DTOL:
                flag += ' ★顶边差'
                BAD.append('%s「%s」标题与角标顶边差 %.1fpx' % (g['name'], t['lbl'], t['dTop']))
            if t['ratio'] is not None and t['ratio'] < RTOL:
                flag += ' ★太浅'
                BAD.append('%s「%s」标题对比度 %.2f < %.1f' % (g['name'], t['lbl'], t['ratio'], RTOL))
            if t['over'] > 0:
                flag += ' ★溢出'
                BAD.append('%s「%s」溢出 %dpx' % (g['name'], t['lbl'], t['over']))
            if t['vTop'] is not None:
                VT.append((g['name'], t['lbl'], t['vTop'], t['vBot']))
            print('     %-14s %-8s %-8s 卡高%4.0f kTop%4.0f vTop%5s vH%4s vBot%4s %5.2f%s'
                  % (t['lbl'], t['tk'], t['val'], t['cardH'], t['kTop'],
                     '%.0f' % t['vTop'] if t['vTop'] is not None else '--',
                     '%.0f' % t['vH'] if t['vH'] is not None else '--',
                     '%.0f' % t['vBot'] if t['vBot'] is not None else '--',
                     t['ratio'] if t['ratio'] else 0, flag))
        # 同组内 kTop 应当完全一致（同一套文字位置契约）
        if max(kt) - min(kt) > DTOL:
            BAD.append('%s 组内 kTop 不一致（%.0f–%.0f）' % (g['name'], min(kt), max(kt)))
        if len(col) > 1:
            BAD.append('%s 组内标题色不统一：%s' % (g['name'], '/'.join(sorted(col))))
    # 跨组「值锚点」：大号数字在卡内的纵向位置应当一致。
    # 卡高来路不同（总览定高 88 / hero·倒计时内容撑高）时，space-between 的贴底项必然错位。
    if VT:
        tops = [x[2] for x in VT]
        print('  → 值锚点跨组 vTop %.0f–%.0f（极差 %.0fpx）'
              % (min(tops), max(tops), max(tops) - min(tops)))
        for grp in ('hero', '总览', '倒计时'):
            gt = [x[2] for x in VT if x[0] == grp]
            if gt:
                print('       %-5s %2d 张 vTop %.0f–%.0f' % (grp, len(gt), min(gt), max(gt)))
        if max(tops) - min(tops) > VTOL:
            BAD.append('值锚点跨组不一致：vTop %.0f–%.0f（极差 %.0fpx > %.0f）'
                       % (min(tops), max(tops), max(tops) - min(tops), VTOL))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--widths', default='1280,900,620')
    ap.add_argument('--dsf', type=float, default=1)
    ap.add_argument('--css', default='')
    ap.add_argument('--pre', default='')
    ap.add_argument('--name', default='现状')
    a = ap.parse_args()
    build(a.css, a.pre)
    for w in [int(x) for x in a.widths.split(',')]:
        r = measure(w, a.dsf)
        if r:
            r['_name'] = a.name
        show(r)
    print('')
    if BAD:
        uniq = []
        for b in BAD:
            if b not in uniq:
                uniq.append(b)
        print('★ 共 %d 处报红：' % len(uniq))
        for b in uniq[:24]:
            print('   - ' + b)
    else:
        print('全绿：全部卡片标题颜色 ≥ %.1f:1，且与右上角标顶边对齐（|dTop| ≤ %.0fpx）' % (RTOL, DTOL))


if __name__ == '__main__':
    main()
