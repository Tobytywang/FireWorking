# -*- coding: utf-8 -*-
"""量「倒计时功能的统计」那排 4 张统计卡 与 其下「按类型分布」卡片 之间的**垂直间隙**。

背景：用户在截图里圈出这两块之间的缝，说"间隙有点问题"。
本探针把它量成 CSS px，并**同时量出同页参照量**，避免把正常间距误判成缺陷：
  · 同排 4 卡之间的横向 gap（.cd-sum 的 gap，应 12px）
  · 同节内 .panel + .panel 的纵向 gap（应 14px）
  · h2 → 首块内容的间距（h2 margin-bottom，应 16px）
  · 相邻 section 之间的间距（section margin-top，应 40px）

判据（数值化）：4 卡底 → 下方卡片顶 的间隙，应当与"同类相邻块"的间距同一量级。
实测若为 0（贴死）或显著偏离 12/14/16，就是观感异常的来源。

手法沿用 _ui_geom_probe.py：读产物 HTML → 往 </body> 前注入测量脚本
→ 无头 Chrome --dump-dom → 正则抠 <pre id="CDGAP"> 里的 JSON。

用法：
  python _cdgap_probe.py                          # 1280 档
  python _cdgap_probe.py --width 900 --width 620  # 多档
  python _cdgap_probe.py --css ".cd-sum{margin-bottom:14px}"   # 量实验 CSS 下的效果
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_cdgap_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# 只**读**几何，不改任何样式 —— 与 _ui_geom_probe.py 同一套"量真代码"原则：
# 把两个 section 的所有相关盒子的 rect 原样吐出来，间隙由 Python 端相减得出，
# 免得在 JS 里写死"谁是参照物"。
MEASURE_JS = r"""
<script>
(function(){
  function R(el){ if(!el) return null;
    var b=el.getBoundingClientRect();
    return {t:+b.top.toFixed(1),b:+b.bottom.toFixed(1),
            l:+b.left.toFixed(1),r:+b.right.toFixed(1),
            w:+b.width.toFixed(1),h:+b.height.toFixed(1)};}
  var out={vw:window.innerWidth,dpr:window.devicePixelRatio||1};
  function dumpSec(sec){
    if(!sec) return null;
    var h2=sec.querySelector(':scope > h2');
    var panels=[].slice.call(sec.querySelectorAll(':scope > .panel'));
    var statsHost=sec.querySelector('.stats');
    var grid=statsHost?statsHost.querySelector('.cd-sum'):null;
    /* 卡片网格不一定叫 .cd-sum（别把量法绑死在类名上）：退化成"statsHost 的第一个元素子" */
    if(!grid&&statsHost) grid=statsHost.firstElementChild;
    var tiles=grid?[].slice.call(grid.children):[];
    return {
      h2:R(h2), statsHost:R(statsHost), grid:R(grid),
      tiles:tiles.map(R), panels:panels.map(R),
      gridCS:grid?{display:getComputedStyle(grid).display,
        rowGap:getComputedStyle(grid).rowGap,colGap:getComputedStyle(grid).columnGap,
        mt:getComputedStyle(grid).marginTop,mb:getComputedStyle(grid).marginBottom}:null,
      hostCS:statsHost?{display:getComputedStyle(statsHost).display,
        mt:getComputedStyle(statsHost).marginTop,mb:getComputedStyle(statsHost).marginBottom}:null,
      panelCS:panels.length?{mt:getComputedStyle(panels[0]).marginTop}:null
    };
  }
  /* ⚠ 别用 `section:has(#year-cal)` 定位：`:has()` 在旧 Chrome 上是**语法错误**，
     会直接把整段测量脚本抛崩（连 CDGAP 都吐不出来）。用 id 反查 closest('section') 最稳。 */
  function secOf(id){var e=document.getElementById(id);return e?e.closest('section'):null;}
  out.cd=dumpSec(secOf('cd-stats'));                          /* 倒计时节（目标） */
  out.act=dumpSec(secOf('year-cal'));                         /* 活动节（对照） */
  var pre=document.createElement('pre'); pre.id='CDGAP';
  pre.style.display='none';                                    /* 不参与布局、不进截图 */
  pre.textContent=JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""


def build(extra_css=''):
    src = open(SRC, encoding='utf-8').read()
    if extra_css:
        src = src.replace('</head>', '<style id="_probe_css">' + extra_css + '</style></head>', 1)
    src = src.replace('</body>', MEASURE_JS + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)


def run(width, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,%d' % (width, 900),
           '--virtual-time-budget=3000', '--dump-dom',
           'file:///' + TMP.replace('\\', '/')]
    r = subprocess.run(cmd, capture_output=True)
    dump = r.stdout.decode('utf-8', 'replace')
    m = re.search(r'<pre id="CDGAP"[^>]*>(.*?)</pre>', dump, re.S)
    if not m:
        print('!! 没拿到测量块，dump 长度 %d' % len(dump))
        print(dump[:600])
        return None
    return json.loads(htmllib.unescape(m.group(1)).strip())


def gap(a, b):
    """a 的底 → b 的顶（CSS px）；任一为 None 时返回 None。"""
    if not a or not b:
        return None
    return round(b['t'] - a['b'], 1)


def report(r, strict=True):
    if not r:
        return 'MISS'
    verdict = 'green'   # 默认判绿；一旦触到坏形态翻红
    print('=== viewport %d (dpr %g) ===' % (r['vw'], r['dpr']))
    for key, name in (('cd', '倒计时节'), ('act', '活动节(对照)')):
        d = r.get(key)
        if not d:
            print('  [%s] 找不到' % name)
            continue
        tiles = d['tiles'] or []
        panels = d['panels'] or []
        print('  [%s] 卡 %d 张 / 面板 %d 个' % (name, len(tiles), len(panels)))
        if tiles:
            rows = sorted(set(round(t['t']) for t in tiles if t))
            print('        卡行数 %d（顶 y = %s）| 卡高 %s'
                  % (len(rows), ','.join(str(x) for x in rows),
                     ','.join('%.1f' % t['h'] for t in tiles if t)))
            # 同排相邻卡的横向 gap
            for i in range(1, len(tiles)):
                if abs(tiles[i]['t'] - tiles[0]['t']) < 1:
                    print('        · 同排卡 #%d→#%d 横向 gap %.1f' % (i, i + 1,
                          round(tiles[i]['l'] - tiles[i - 1]['r'], 1)))
        # 页内参照：卡片与卡片之间的纵向间距（.panel + .panel）
        pgaps = [round(panels[j]['t'] - panels[j - 1]['b'], 1) for j in range(1, len(panels))]
        for j in range(1, len(panels)):
            print('        · 面板 #%d→#%d 纵向 gap %.1f' % (j, j + 1, pgaps[j - 1]))
        if d['h2'] and d['statsHost']:
            print('        · h2 底 → 卡片网格顶 = %.1f' % round(d['statsHost']['t'] - d['h2']['b'], 1))
        print('        CSS: grid=%s rowGap=%s colGap=%s mt/mb=%s/%s | stats mt/mb=%s/%s | panel mt=%s'
              % (d['gridCS'] and d['gridCS']['display'],
                 d['gridCS'] and d['gridCS']['rowGap'], d['gridCS'] and d['gridCS']['colGap'],
                 d['gridCS'] and d['gridCS']['mt'], d['gridCS'] and d['gridCS']['mb'],
                 d['hostCS'] and d['hostCS']['mt'], d['hostCS'] and d['hostCS']['mb'],
                 d['panelCS'] and d['panelCS']['mt']))
        # ── 判据 ──
        # 4 卡也是卡片（有边框/圆角/阴影），它与**紧随其后的**卡片之间是"卡 → 卡"的关系，
        # 间距必须与页内其它"卡 → 卡"（.panel + .panel，实测 14px）一致。
        # 曾经是 0（贴死、两条边框重合），用户圈出来说"间隙有点问题"。
        if tiles and panels:
            g = gap({'b': max(t['b'] for t in tiles if t)}, panels[0])
            ref = pgaps[0] if pgaps else None
            bad = []
            if g is None:
                bad.append('· 量不到（缺参照）')
            elif abs(g) < 0.5:
                bad.append('★ 4 卡与其下卡片**贴死**（gap %.1f）—— 两条边框重合，'
                           '与页内卡片间距%s不一致' % (g, (' %.1f' % ref) if ref else ''))
            elif ref is not None and abs(g - ref) > 1:
                bad.append('★ 4 卡与其下卡片的间距 %.1f ≠ 页内卡片间距 %.1f' % (g, ref))
            print('        ★ 卡底(y=%.1f) → 面板顶(y=%.1f)  垂直 gap = %s'
                  % (max(t['b'] for t in tiles if t), panels[0]['t'], g))
            print('             → %s'
                  % ('；'.join(bad) if bad else '与页内卡片间距一致（%.1f）✓' % g))
            if bad:
                verdict = 'red'
        elif strict:
            print('        ! 本帧没有卡片网格 —— 判据不适用（空模板）')
    return verdict


def main():
    ap = argparse.ArgumentParser(description='量倒计时节 4 卡与其下面板之间的垂直间隙')
    ap.add_argument('--width', type=int, action='append', default=None,
                    help='视口宽（可重复）；默认 1280')
    ap.add_argument('--css', default='', help='注入实验 CSS')
    ap.add_argument('--json', action='store_true', help='同时打印原始 JSON')
    ap.add_argument('--nogap', action='store_true',
                    help='反向验证：注入 .stats + .panel{margin-top:0!important} '
                         '把修复抵回缺陷态，断言必须报红（证明判据非死代码）')
    a = ap.parse_args()
    widths = a.width or [1280]
    # 反向：用 !important 强制把那道缝压回 0（重现"贴死"缺陷），
    # 正向（默认）走的是产物里已修好的 .stats + .panel{margin-top:14px}。
    extra = a.css or ('.stats + .panel{margin-top:0 !important}' if a.nogap else '')
    build(extra)
    ok = True
    for w in widths:
        r = run(w)
        if a.json and r:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        if report(r) == 'red':
            ok = False
    if a.nogap:
        print('\n=== 反向验证（--nogap）===')
        print('  注入 .stats + .panel{margin-top:0!important} → 把修复压回缺陷态')
        print('  期望：判据报红（★ 4 卡与其下卡片贴死）；  实际：%s'
              % ('REVERSE-OK ✓ 断言命中' if not ok else '✗ 反向失败：未报红（判据疑似死代码）'))
    else:
        print('\n=== 正向验证（现状）===')
        print('  走产物已修好的 .stats + .panel{margin-top:14px}')
        print('  期望：判据报绿（gap≈页内 14px）；  实际：%s'
              % ('FORWARD-OK ✓' if ok else '✗ 正向失败：出现红标'))


if __name__ == '__main__':
    main()
