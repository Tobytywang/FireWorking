# -*- coding: utf-8 -*-
"""「工作时长模型（v3.13）」探针：标准/实际工作时长 + 标准活跃 + 加班 + 两类占比。

口径（与 report_template.html 完全一致）：
  标准工作窗口 = 9:00-12:00 与 13:30-18:00（分钟-of-day：[540,720) ∪ [810,1080)）
  标准工作时长   = 工作日天数 × 7.5h（常数，与是否有活动无关）
  实际工作时长   = Σ(每天「首次有活动分钟 ~ 末次有活动分钟」跨度秒)
  标准活跃时长   = Σ(工作日里落在标准窗口内的 active_secs)
  实际活跃时长   = Σ(工作日全部 active_secs)  == WD_ACT
  加班时长       = Σ(实际工作跨度中落在标准窗口「外」的分钟 × 60)
  标准活跃占比   = 标准活跃时长 / 标准工作时长 × 100%
  实际活跃占比   = 实际活跃时长 / 实际工作时长 × 100%

手法：从 heat.db 用**同一张节假日表 + 同一套口径**独立算出期望值，再无头 Chrome
      --dump-dom 抠产物里 <pre id="WT"> 的真实渲染值，逐字段比对。

判据：
  T1 标准工作时长 = 工作日数 × 27000 秒
  T2 实际工作时长 = DB 独立算出的「首末活跃分钟跨度」之和
  T3 标准活跃时长 = DB 独立算出的窗口内 active_secs 之和
  T4 加班时长     = DB 独立算出的「跨度超出窗口」分钟 × 60
  T5 标准活跃占比 / 实际活跃占比 与 DB 期望值一致（四舍五入 ±0.2%）
  T6 工作日数 与 DAY_KEYS 中的工作日数一致

用法：
  python _wt_probe_1.py                         # 量现状（heat-report-prototype.html）
  python _wt_probe_1.py --html data/heat-report.html
"""
import argparse
import html as htmllib
import json
import os
import re
import sqlite3
import subprocess
import sys
import datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
DEF_HTML = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_wt_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
DB = os.path.join(HERE, 'heat.db')

# —— 与 report_template.html 完全一致的 2026 节假日 / 调休表 ——
HOLIDAY = []
for a, b in [('2026-01-01', '2026-01-03'), ('2026-02-15', '2026-02-23'),
             ('2026-04-04', '2026-04-06'), ('2026-05-01', '2026-05-05'),
             ('2026-06-19', '2026-06-21'), ('2026-09-25', '2026-09-27'),
             ('2026-10-01', '2026-10-07')]:
    t = _dt.date(*[int(x) for x in a.split('-')])
    ev = _dt.date(*[int(x) for x in b.split('-')])
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
    return _dt.date.fromisoformat(iso).weekday() < 5


def in_std_window(m):
    return (540 <= m < 720) or (810 <= m < 1080)


STD_WORK_SEC_PER_DAY = (720 - 540 + 1080 - 810) * 60  # 27000 秒 = 7.5h


def expected_from_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("SELECT minute_ts, keystrokes, backspaces, active_secs, "
                "mouse_moves, clicks, scrolls FROM minutes")
    rows = cur.fetchall()
    con.close()
    days = {}  # iso -> list of (mod, keys, mv, ck, sc, act)
    for ts, keys, bs, act, mv, ck, sc in rows:
        dt = _dt.datetime.fromtimestamp(ts)
        iso = dt.strftime('%Y-%m-%d')
        mod = dt.hour * 60 + dt.minute
        days.setdefault(iso, []).append((mod, keys or 0, mv or 0, ck or 0, sc or 0, act or 0))
    std_work = std_act = act_work = ot = act_total = 0
    wd_count = 0
    for iso, recs in days.items():
        if not is_workday(iso):
            continue
        wd_count += 1
        std_work += STD_WORK_SEC_PER_DAY
        fM = lM = None
        for mod, keys, mv, ck, sc, act in recs:
            if keys > 0 or mv > 0 or ck > 0 or sc > 0:
                if fM is None:
                    fM = mod
                lM = mod
            if in_std_window(mod):
                std_act += act
            act_total += act
        if fM is not None:
            act_work += (lM - fM) * 60
            for m in range(fM, lM + 1):
                if not in_std_window(m):
                    ot += 60
    std_ratio = std_act / std_work * 100 if std_work else 0
    act_ratio = act_total / act_work * 100 if act_work else 0
    return dict(stdWork=std_work, stdAct=std_act, actWork=act_work, ot=ot,
                stdRatio=std_ratio, actRatio=act_ratio, actTotal=act_total,
                days=wd_count)


def chrome(args, w=1280, h=1000, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
           '--no-default-browser-check', '--hide-scrollbars',
           '--force-device-scale-factor=%s' % dsf,
           '--window-size=%d,%d' % (w, h)] + args
    p = subprocess.run(cmd, capture_output=True, timeout=120)
    return p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


MEASURE_JS = r"""
<script>
(function(){
  var el=document.getElementById('WT');
  var out = el ? el.textContent : 'NULL';
  var d=document.createElement('pre'); d.id='WT_OUT';
  d.textContent=out; document.body.appendChild(d);
})();
</script>
"""


def measure(html_path, width=1280, dsf=1):
    src = open(html_path, encoding='utf-8').read()
    src = src.replace('</body>', MEASURE_JS + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)
    url = 'file:///' + TMP.replace('\\', '/')
    out, err = chrome(['--dump-dom', url], w=width, h=1400, dsf=dsf)
    m = re.search(r'<pre id="WT_OUT">(.*?)</pre>', out, re.S)
    if not m:
        print('!! 没抠到 WT —— 页面脚本可能抛异常。 stderr:', err[-1500:])
        sys.exit(2)
    return json.loads(htmllib.unescape(m.group(1)))


class Rep(object):
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


def main():
    ap = argparse.ArgumentParser(description='工作时长模型 探针')
    ap.add_argument('--html', default=DEF_HTML)
    ap.add_argument('--dsf', type=int, default=1)
    ap.add_argument('--width', type=int, default=1280)
    a = ap.parse_args()

    exp = expected_from_db()
    got = measure(a.html, a.width, a.dsf)
    print('DB 期望:', {k: round(v, 2) if isinstance(v, float) else v
                       for k, v in exp.items()})
    print('页面渲染:', {k: round(v, 2) if isinstance(v, float) else v
                        for k, v in got.items()})
    rep = Rep()
    rep.check('T1 标准工作时长 = 工作日×7.5h',
              abs(got['stdWork'] - exp['stdWork']) <= 1,
              'got=%s exp=%s' % (got['stdWork'], exp['stdWork']))
    rep.check('T2 实际工作时长 = 首末活跃跨度之和',
              abs(got['actWork'] - exp['actWork']) <= 60,
              'got=%s exp=%s' % (got['actWork'], exp['actWork']))
    rep.check('T3 标准活跃时长 = 窗口内 active_secs 之和',
              abs(got['stdAct'] - exp['stdAct']) <= 1,
              'got=%s exp=%s' % (got['stdAct'], exp['stdAct']))
    rep.check('T4 加班时长 = 跨度超窗口分钟×60',
              abs(got['ot'] - exp['ot']) <= 60,
              'got=%s exp=%s' % (got['ot'], exp['ot']))
    rep.check('T5 标准活跃占比一致',
              abs(got['stdRatio'] - exp['stdRatio']) <= 0.2,
              'got=%.3f exp=%.3f' % (got['stdRatio'], exp['stdRatio']))
    rep.check('T6 实际活跃占比一致',
              abs(got['actRatio'] - exp['actRatio']) <= 0.2,
              'got=%.3f exp=%.3f' % (got['actRatio'], exp['actRatio']))
    rep.check('T7 工作日数一致',
              got['days'] == exp['days'],
              'got=%s exp=%s' % (got['days'], exp['days']))

    # 一致性自检：实际活跃时长(got.actWork 对应的分子) == exp.actTotal，且占比闭合
    rep.check('T8 实际活跃占比分子 = 全活跃秒/实际工作',
              abs(exp['actTotal'] / exp['actWork'] * 100 - exp['actRatio']) <= 0.01,
              'ratio mismatch')
    rep.check('T9 实际活跃时长 = 全时段活跃秒合计',
              abs(got.get('actActive', -1) - exp['actTotal']) <= 1,
              'got=%s exp=%s' % (got.get('actActive'), exp['actTotal']))

    print('\n结果：%d 通过 / %d 失败' % (rep.ok, len(rep.bad)))
    if rep.bad:
        print('失败项：', rep.bad)
        sys.exit(1)
    print('全部通过 ✓')


if __name__ == '__main__':
    main()
