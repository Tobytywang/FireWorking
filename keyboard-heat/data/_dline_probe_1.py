# -*- coding: utf-8 -*-
"""「当天 = 与历史平均同轴的竖线 + 菱形尖端」的几何探针（v3.12）。

背景：逐小时分布原来是每格**两根并排柱**（左当天、右历史平均），现在改成
      底层浅色柱（历史平均）+ 上层竖线（当天），两者**水平居中对齐 = 同轴**，
      线的顶端压一个菱形，菱形中心就是当天数值的位置。

手法：读产物 HTML -> 往 </body> 前注入测量脚本（可选先注入夹具 js）-> 无头 Chrome
      `--dump-dom` -> 抠 <pre id="DLINE"> 里的 JSON -> 逐条断言。
      量的是**真实布局 rect**（不是源码文本），所以"改了一行 CSS 结果没生效"这类
      假绿会被抓住。

判据（每条都配了反向验证，见文件末尾的 SELF-TEST）：
  D1 同轴     线中心 x 与平均柱中心 x 偏差 <= 0.6px（24 格全量）
  D2 菱形中心 = 当天数值   菱形中心 y 与线顶 y 偏差 <= 0.6px
  D3 菱形是"变宽"的标记   菱形宽 >= 线宽 + 4px
  D4 线贴底   线底与平均柱底偏差 <= 0.6px
  D5 鼠标段   贴底 + 高度占比 == min(1, meq/eq)
  D6 线高口径 h(线) == h(格) * max(3, eq/HOUR_AXIS*100)/100（±1px）
  D7 菱形颜色 线通体是鼠标色时（mPct>=99.5）菱形跟 --mouse，否则 --accent-2
  D8 零值不画线  eq=0 的格子里没有线、eq>0 的格子必须有线

用法：
  python _dline_probe_1.py                          # 量现状（全绿 exit 0）
  python _dline_probe_1.py --day 2026-10-08         # 换到活跃日（更多格有线）
  python _dline_probe_1.py --pre _pre_axisbar_1.js  # 反向验证：改前形态，D1 必须报红
  python _dline_probe_1.py --html xxx.html --dump   # 换产物 / 打印原始 JSON
用 keyboard-heat/.pyenv 的 python 跑（本脚本不依赖第三方库，但项目里统一用这个解释器）。
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_HTML = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_dline_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

MEASURE_JS = r"""
<script>
(function(){
  /* 先切到指定日期（不传就保持模板默认的"最近一天"）。
     ⚠ 必须在读取任何 rect 之前切：selectDay 内部同步调 drawBars 重建 #bars，
       晚一步就会量到上一天的 DOM。 */
  var PICK=__DAY__;
  if(PICK){ try{ selectDay(PICK); }catch(e){ window.__pickErr=String(e); } }
  function R(el){var b=el.getBoundingClientRect();
    return {x:+b.left.toFixed(2),y:+b.top.toFixed(2),w:+b.width.toFixed(2),h:+b.height.toFixed(2),
            r:+b.right.toFixed(2),b:+b.bottom.toFixed(2)};}
  /* :root 变量 -> rgb 串（切主题后卡片 computed 背景色不可信，必须读 :root 变量） */
  function toRgb(v){
    if(!v) return '';
    var d=document.createElement('div'); d.style.color=v.trim();
    document.body.appendChild(d); var c=getComputedStyle(d).color; d.remove(); return c;
  }
  var cs=getComputedStyle(document.documentElement);
  var out={cells:[], axis:null, mouseColor:toRgb(cs.getPropertyValue('--mouse')),
           accentColor:toRgb(cs.getPropertyValue('--accent-2')),
           day: (typeof selectedDay!=='undefined')?selectedDay:null,
           vw:window.innerWidth};
  try{ out.axis=hourAxisMax(); }catch(e){ out.axisErr=String(e); }

  var host=document.getElementById('bars');
  if(!host){ throw new Error('没有 #bars'); }
  var bhList=[].slice.call(host.children);
  out.bhN=bhList.length;
  bhList.forEach(function(bh,i){
    var bar=bh.querySelector('.bar-avg'), ln=bh.querySelector('.dline');
    var rec={i:i, eq:(bh.dataset.eq===undefined?null:+bh.dataset.eq)};
    var rb=R(bh); rec.cell={h:rb.h};
    if(bar){ var r=R(bar);
      rec.bar={cx:+((r.x+r.r)/2).toFixed(2),w:r.w,h:r.h,b:r.b,off:bar.classList.contains('off')}; }
    if(!ln){ rec.noLine=true; out.cells.push(rec); return; }
    var d=R(ln);
    rec.line={cx:+((d.x+d.r)/2).toFixed(2),w:d.w,h:d.h,top:d.y,b:d.b,
              v:(ln.dataset.v===undefined?null:+ln.dataset.v),
              meq:(ln.dataset.meq===undefined?null:+ln.dataset.meq)};
    var m=ln.querySelector('.bar-m');
    if(m){ var mr=R(m); rec.m={h:mr.h,b:mr.b,w:mr.w}; }
    var t=ln.querySelector('.dl-tip');
    if(t){ var tr=R(t);
      rec.tip={cx:+((tr.x+tr.r)/2).toFixed(2),cy:+((tr.y+tr.b)/2).toFixed(2),
               w:tr.w,h:tr.h,bg:getComputedStyle(t).backgroundColor}; }
    out.cells.push(rec);
  });
  var el=document.createElement('pre'); el.id='DLINE';
  el.textContent=JSON.stringify(out);
  document.body.appendChild(el);
})();
</script>
"""


def chrome(args, w=1280, h=1000, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
           '--no-default-browser-check', '--hide-scrollbars',
           '--force-device-scale-factor=%s' % dsf,
           '--window-size=%d,%d' % (w, h)] + args
    p = subprocess.run(cmd, capture_output=True, timeout=120)
    return p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def build(html_path, pre_path, day=''):
    """pre_path 是**夹具 js**（不是 css）：它自己插 <style>、改文案、切日期，见 _pre_axisbar_1.js。
    注入顺序很关键 —— 夹具在前、测量脚本在后，这样探针 --day 的 selectDay 能覆盖夹具里的默认日期。"""
    src = open(html_path, encoding='utf-8').read()
    pre = ''
    if pre_path:
        pre = ('<script>%s</script>'
               % open(pre_path, encoding='utf-8').read().replace('</script', '<\\/script'))
    src = src.replace('</body>',
                      pre + MEASURE_JS.replace('__DAY__', json.dumps(day or '')) + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)
    return TMP


def measure(html_path, pre_path, width, dsf, day=''):
    tmp = build(html_path, pre_path, day)
    url = 'file:///' + tmp.replace('\\', '/')
    out, err = chrome(['--dump-dom', url], w=width, h=1200, dsf=dsf)
    m = re.search(r'<pre id="DLINE">(.*?)</pre>', out, re.S)
    if not m:
        print('!! 没抠到 DLINE —— 页面脚本可能抛异常了。')
        print('stderr:', err[-2000:])
        sys.exit(2)
    return json.loads(htmllib.unescape(m.group(1)))


class Report(object):
    def __init__(self):
        self.ok = 0
        self.bad = []

    def check(self, name, cond, detail=''):
        if cond:
            self.ok += 1
            print('  [OK] %s' % name)
        else:
            self.bad.append(name)
            print('  [!!] %s   %s' % (name, detail))


def run(p, rep, tol=0.6):
    cells = p['cells']
    print('\n-- 上下文 --')
    print('  选中日期 %s / 格数 %d / HOUR_AXIS %s / vw %d'
          % (p.get('day'), p.get('bhN'), p.get('axis'), p.get('vw')))
    print('  --mouse %s / --accent-2 %s' % (p.get('mouseColor'), p.get('accentColor')))

    live = [c for c in cells if not c.get('noLine')]
    dead = [c for c in cells if c.get('noLine')]

    # D8 零值不画线（先判，后面几档都只看 live）
    rep.check('D8 格数 == 24', len(cells) == 24, 'bhN=%d' % len(cells))
    bad8 = [c['i'] for c in live if c['eq'] == 0] + [c['i'] for c in dead if c['eq'] != 0]
    rep.check('D8 eq=0 不画线 / eq>0 必有线', not bad8,
              '矛盾格 %s（live eq=0 %d 个 / dead eq>0 %d 个）'
              % (bad8, len([c for c in live if c['eq'] == 0]),
                 len([c for c in dead if c['eq'] != 0])))
    print('      有线的格 %d / 无线的格 %d' % (len(live), len(dead)))

    # 没有一根线时不能静默放过后面几档 —— 那会变成"判据自己消失"的假绿。
    if not live:
        rep.check('D1~D7 有可量的当天竖线', False,
                  '选中日 %s 的 24 个格 eq 全为 0，没有线可量（请用 --day 换一天）' % p.get('day'))
        return rep

    # D1 同轴
    off = [(c['i'], abs(c['line']['cx'] - c['bar']['cx'])) for c in live if 'bar' in c]
    worst = max(off, key=lambda t: t[1]) if off else (None, 0)
    rep.check('D1 线中心 x == 平均柱中心 x（同轴）', bool(off) and worst[1] <= tol,
              '最大偏差 %.2fpx @ %s 点（%s）' % (worst[1], worst[0], off[:5]))

    # D2 菱形中心 = 线顶
    off2 = [(c['i'], abs(c['tip']['cy'] - c['line']['top'])) for c in live if 'tip' in c]
    worst2 = max(off2, key=lambda t: t[1]) if off2 else (None, 0)
    rep.check('D2 菱形中心 y == 线顶 y', len(off2) == len(live) and worst2[1] <= tol,
              '最大偏差 %.2fpx @ %s 点（tip 缺失 %d 个）'
              % (worst2[1], worst2[0], len(live) - len(off2)))

    # D3 菱形比线宽
    d3 = [(c['i'], c['tip']['w'] - c['line']['w']) for c in live if 'tip' in c]
    rep.check('D3 菱形宽 >= 线宽 + 4px', bool(d3) and min(t[1] for t in d3) >= 4,
              '最小差 %.1fpx（线宽 %.1f / 菱形宽 %.1f）'
              % (min([t[1] for t in d3] or [0]), live[0]['line']['w'] if live else 0,
                 live[0]['tip']['w'] if live and 'tip' in live[0] else 0))

    # D4 线贴底
    d4 = [(c['i'], abs(c['line']['b'] - c['bar']['b'])) for c in live if 'bar' in c]
    worst4 = max(d4, key=lambda t: t[1]) if d4 else (None, 0)
    rep.check('D4 线底 == 平均柱底', bool(d4) and worst4[1] <= tol,
              '最大偏差 %.2fpx @ %s 点' % (worst4[1], worst4[0]))

    # D5 鼠标段
    d5, d5b, miss5 = [], [], 0
    for c in live:
        ratio = min(1.0, c['line']['meq'] / c['eq']) if c['eq'] else 0.0
        if 'm' not in c:
            if ratio > 0:
                miss5 += 1
            continue
        d5.append((c['i'], abs(c['m']['h'] / c['line']['h'] - ratio)))
        d5b.append((c['i'], abs(c['m']['b'] - c['line']['b'])))
    worst5 = max(d5, key=lambda t: t[1]) if d5 else (None, 0)
    worst5b = max(d5b, key=lambda t: t[1]) if d5b else (None, 0)
    rep.check('D5 鼠标段贴底 + 高度占比 == meq/eq',
              bool(d5) and worst5[1] <= 0.02 and worst5b[1] <= tol and miss5 == 0,
              '占比最大偏差 %.4f @ %s 点 / 底偏差 %.2fpx / 该有却没有 %d 个'
              % (worst5[1], worst5[0], worst5b[1], miss5))

    # D6 线高口径
    d6 = []
    for c in live:
        exp = max(3.0, c['eq'] / p['axis'] * 100) / 100 * c['cell']['h']
        d6.append((c['i'], abs(c['line']['h'] - exp), c['line']['h'], exp))
    worst6 = max(d6, key=lambda t: t[1]) if d6 else (None, 0, 0, 0)
    rep.check('D6 线高 == 格高 x max(3,eq/HOUR_AXIS*100)%%', bool(d6) and worst6[1] <= 1.0,
              '最大偏差 %.2fpx @ %s 点（实测 %.1f / 期望 %.1f）'
              % (worst6[1], worst6[0], worst6[2], worst6[3]))

    # D7 菱形颜色跟随线顶端
    bad7 = []
    for c in live:
        ratio = min(1.0, c['line']['meq'] / c['eq']) if c['eq'] else 0.0
        want = p['mouseColor'] if ratio >= 0.995 else p['accentColor']
        if c['tip']['bg'] != want:
            bad7.append((c['i'], ratio, c['tip']['bg'], want))
    rep.check('D7 菱形颜色跟随线顶端（全鼠标小时用 --mouse）', not bad7,
              '不符 %s' % bad7[:3])
    pure_mouse = [c['i'] for c in live
                  if c['eq'] and c['line']['meq'] / c['eq'] >= 0.995]
    print('      全鼠标小时（菱形应为 --mouse 色）：%s' % (pure_mouse or '无'))

    return rep


def main():
    ap = argparse.ArgumentParser(description='当天同轴竖线 + 菱形的几何探针')
    ap.add_argument('--html', default=DEF_HTML, help='产物 HTML（默认 heat-report-prototype.html）')
    ap.add_argument('--pre', default='', help='注入夹具 js（反向验证用，如 _pre_axisbar_1.js）')
    ap.add_argument('--width', type=int, default=1280, help='视口宽（默认 1280）')
    ap.add_argument('--dsf', type=float, default=1, help='device scale factor（默认 1）')
    ap.add_argument('--day', default='', help='先切到这一天再量（YYYY-MM-DD；默认取模板的最近一天）')
    ap.add_argument('--dump', action='store_true', help='打印原始测量 JSON')
    a = ap.parse_args()

    pre = a.pre
    if pre and not os.path.isabs(pre):
        pre = os.path.join(HERE, pre)
    if pre and not os.path.exists(pre):
        raise SystemExit('!! 夹具不存在：%s' % pre)

    p = measure(a.html, pre, a.width, a.dsf, a.day)
    if a.dump:
        print(json.dumps(p, ensure_ascii=False, indent=1)[:6000])

    tag = '（注入 %s）' % os.path.basename(pre) if pre else '（现状）'
    print('\n===== 当天同轴竖线 + 菱形 · 几何探针 %s =====' % tag)
    rep = run(p, Report())
    print('\n结果：%d 通过 / %d 失败%s'
          % (rep.ok, len(rep.bad), ('  → ' + ', '.join(rep.bad)) if rep.bad else ''))
    # SELF-TEST（反向验证，手动跑，不写进自动化）：
    #   python _dline_probe_1.py --pre _pre_axisbar_1.js --day 2026-10-08
    #     → D1 必须报红（并排双柱不同轴，实测偏差 ~19.6px）、D2/D3 也跟着红；
    #       D8 应保持绿（夹具只改布局，.bh[data-eq] 仍在）。
    #   真绿：同一份夹具不注入时 D1~D8 全绿。
    return 1 if rep.bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
