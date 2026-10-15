# -*- coding: utf-8 -*-
"""「逐小时平均柱 / 日均指标 只统计工作日」的探针（v3.13，配套 report_template.html 工作日口径）。

背景：report_template.html 把「历史同时段平均」从「全部日期平均」改成「工作日同时段平均」
      （剔除周末与法定假期，含调休补班视为上班），日均汇总指标（头部三卡 / 总览 / 复制摘要）
      的分子分母也一并改为工作日口径。isWorkday() 的真值来源是模板里内置的
      2026 国办放假调休表（MAKUP/HOLIDAY）。

手法：读产物 HTML -> 注入测量脚本（可选先注入 pre js 把平均切回「全部日期」）-> 无头 Chrome
      `--dump-dom` -> 抠 <pre id="WD"> 里每格平均柱的 data-v -> 与 Python 侧用**同一张
      节假日表**从 heat.db 独立算出的期望值比对。只比真值，不比源码，杜绝假绿。

判据：
  W1 工作日平均柱 = Python 侧工作日口径期望值（24 格逐时比对，四舍五入允许 ±1）
  W2 工作日天数 < 全部天数（过滤确实生效：wdDayCount < DAY_KEYS.length）
  W3 反向验证：注入 pre 把平均切回「全部日期」后，渲染值 == Python 侧全部日期期望值
  W4 反向验证：默认（工作日）与「全部日期」两种口径**不全相同**（证明过滤改变了结果）

用法：
  python _wd_probe_1.py                          # 量现状（heat-report-prototype.html）
  python _wd_probe_1.py --html data/heat-report.html --day 2026-10-08
  python _wd_probe_1.py --pre _pre_wd_alldays.js # 反向验证：强制全部日期平均
"""
import argparse
import html as htmllib
import json
import os
import re
import sqlite3
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_HTML = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_wd_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DB = os.path.join(HERE, 'heat.db')

# —— 与 report_template.html 完全一致的 2026 节假日 / 调休表 ——
HOLIDAY = []
for a, b in [('2026-01-01', '2026-01-03'), ('2026-02-15', '2026-02-23'),
             ('2026-04-04', '2026-04-06'), ('2026-05-01', '2026-05-05'),
             ('2026-06-19', '2026-06-21'), ('2026-09-25', '2026-09-27'),
             ('2026-10-01', '2026-10-07')]:
    d = [int(x) for x in a.split('-')]
    import datetime as _dt
    t = _dt.date(d[0], d[1], d[2])
    e = [int(x) for x in b.split('-')]
    ev = _dt.date(e[0], e[1], e[2])
    while t <= ev:
        HOLIDAY.append(t.isoformat())
        t += _dt.timedelta(days=1)
MAKEUP = set(['2026-01-04', '2026-02-14', '2026-02-28', '2026-05-09',
              '2026-09-20', '2026-10-10'])


def is_workday(iso):
    if iso in MAKEUP:
        return True
    if iso in HOLIDAY:
        return False
    import datetime as _dt
    wd = _dt.date.fromisoformat(iso).weekday()
    return wd < 5


def expected_from_db():
    """返回 (avg_wd[24], avg_all[24], wd_count, all_count)。口径与模板保持一致：
    每格 = Σ(该小时 keys + 鼠标当量) / 天数；鼠标当量 = mv*0.01 + ck*4 + sc*2。"""
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT minute_ts, keystrokes, backspaces, active_secs, "
                "mouse_moves, clicks, scrolls FROM minutes")
    rows = cur.fetchall()
    con.close()
    import datetime as _dt
    days = {}  # iso -> {'all':[24], 'wd':[24]}
    for ts, keys, bs, act, mv, ck, sc in rows:
        dt = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).astimezone()
        iso = dt.date().isoformat()
        h = dt.hour
        val = (keys or 0) + (mv or 0) * 0.01 + (ck or 0) * 4 + (sc or 0) * 2
        if iso not in days:
            days[iso] = {'all': [0] * 24, 'wd': [0] * 24}
        days[iso]['all'][h] += val
        if is_workday(iso):
            days[iso]['wd'][h] += val
    all_days = sorted(days.keys())
    wd_days = [d for d in all_days if is_workday(d)]
    all_count = len(all_days)
    wd_count = len(wd_days)
    avg_all = [sum(days[d]['all'][h] for d in all_days) / max(1, all_count) for h in range(24)]
    avg_wd = [sum(days[d]['wd'][h] for d in wd_days) / max(1, wd_count) for h in range(24)]
    return avg_wd, avg_all, wd_count, all_count


MEASURE_JS = r"""
<script>
(function(){
  var PICK=__DAY__;
  if(PICK){ try{ selectDay(PICK); }catch(e){ window.__pickErr=String(e); } }
  var host=document.getElementById('bars');
  var av=[];
  [].slice.call(host.children).forEach(function(bh,i){
    var bar=bh.querySelector('.bar-avg');
    av.push(bar?+(bar.dataset.v||0):null);
  });
  var el=document.createElement('pre'); el.id='WD';
  el.textContent=JSON.stringify({day:(typeof selectedDay!=='undefined'?selectedDay:null),
    av:av});
  document.body.appendChild(el);
})();
</script>
"""

ALLDAYS_PRE = r"""
(function(){
  var diag={hook:typeof window.__redrawDayAvg, sel:(typeof selectedDay!=='undefined'?selectedDay:'UNDEF')};
  var r=null;
  if(typeof window.__redrawDayAvg==='function'){ r=window.__redrawDayAvg(true); }
  diag.afterR = r? r.slice(0,3) : 'NA';
  var el=document.createElement('pre'); el.id='DIAG';
  el.textContent=JSON.stringify(diag);
  document.body.appendChild(el);
})();
"""


def chrome(args, w=1280, h=1000, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
           '--no-default-browser-check', '--hide-scrollbars',
           '--force-device-scale-factor=%s' % dsf,
           '--window-size=%d,%d' % (w, h)] + args
    p = subprocess.run(cmd, capture_output=True, timeout=120)
    return p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def measure(html_path, pre_js, width, dsf, day=''):
    src = open(html_path, encoding='utf-8').read()
    pre = ('<script>%s</script>' % pre_js.replace('</script', '<\\/script')) if pre_js else ''
    src = src.replace('</body>', pre + MEASURE_JS.replace('__DAY__', json.dumps(day or '')) + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)
    url = 'file:///' + TMP.replace('\\', '/')
    out, err = chrome(['--dump-dom', url], w=width, h=1200, dsf=dsf)
    m = re.search(r'<pre id="WD">(.*?)</pre>', out, re.S)
    if not m:
        print('!! 没抠到 WD —— 页面脚本可能抛异常。 stderr:', err[-1500:])
        sys.exit(2)
    res = json.loads(htmllib.unescape(m.group(1)))
    dm = re.search(r'<pre id="DIAG">(.*?)</pre>', out, re.S)
    if dm:
        res['diag'] = json.loads(htmllib.unescape(dm.group(1)))
    return res


class Rep(object):
    def __init__(self): self.ok = 0; self.bad = []
    def check(self, name, cond, detail=''):
        if cond: self.ok += 1; print('  [OK] %s' % name)
        else: self.bad.append(name); print('  [!!] %s   %s' % (name, detail))


def round_eq(a, b, tol=1):
    return abs(a - b) <= tol


def main():
    ap = argparse.ArgumentParser(description='工作日口径平均 探针')
    ap.add_argument('--html', default=DEF_HTML)
    ap.add_argument('--day', default='')
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--dsf', type=float, default=1)
    ap.add_argument('--pre', default='')
    a = ap.parse_args()

    avg_wd, avg_all, wd_count, all_count = expected_from_db()
    print('Python 侧期望：工作日天数 %d / 全部天数 %d' % (wd_count, all_count))
    print('  工作日平均[9] %.1f  全部日期平均[9] %.1f' % (avg_wd[9], avg_all[9]))

    tag = '（注入 %s）' % a.pre if a.pre else '（现状·工作日口径）'
    print('\n===== 工作日口径平均探针 %s =====' % tag)
    rep = Rep()

    p = measure(a.html, '', a.width, a.dsf, a.day)
    av_wd = p['av']
    if len(av_wd) != 24:
        rep.check('W0 量到 24 格平均柱', False, '只量到 %d 格' % len(av_wd))
        print('\n结果：%d 通过 / %d 失败 → %s' % (rep.ok, len(rep.bad), rep.bad or '全过'))
        return 1 if rep.bad else 0

    # W1 工作日口径匹配
    bad = []
    for h in range(24):
        if not round_eq(av_wd[h], round(avg_wd[h])):
            bad.append((h, av_wd[h], round(avg_wd[h])))
    rep.check('W1 工作日平均柱 == 工作日口径期望值（24 格）', not bad,
              '不符 %s' % bad[:6])

    # W2 过滤确实生效
    rep.check('W2 工作日天数 < 全部天数（过滤生效）', wd_count < all_count,
              'wd=%d all=%d' % (wd_count, all_count))

    # W3 + W4 反向验证：全部日期平均
    p2 = measure(a.html, ALLDAYS_PRE, a.width, a.dsf, a.day)
    if p2.get('diag'):
        print('  [DIAG] 钩子诊断：%s' % p2['diag'])
    av_all = p2['av']
    bad3 = []
    for h in range(24):
        if not round_eq(av_all[h], round(avg_all[h])):
            bad3.append((h, av_all[h], round(avg_all[h])))
    rep.check('W3 反向：强制全部日期平均 == 全部日期期望值', not bad3, '不符 %s' % bad3[:6])

    diff = sum(abs(av_wd[h] - av_all[h]) for h in range(24))
    rep.check('W4 工作日口径与全部日期口径不全相同（过滤改变结果）', diff > 0,
              '两口径总和差 %.1f' % diff)

    print('\n结果：%d 通过 / %d 失败 → %s' % (rep.ok, len(rep.bad), rep.bad or '全过'))
    return 1 if rep.bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
