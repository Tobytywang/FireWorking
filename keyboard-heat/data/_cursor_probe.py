# -*- coding: utf-8 -*-
"""轻量「可交互暗示」探针：**只读 computed `cursor`**，不真发鼠标事件。

与 `_hover_cdp.mjs` 的分工：那边用 CDP 真移动鼠标、能验证 `:hover` 伪类真的生效；
这边只读声明值，够用来守「cursor 语义与"能不能点 / 有没有内容可看"一致」这条判据，
且不依赖 CDP 长连接（后者曾整跑 9 分钟不返回，被 kill 掉）。

判据（卡片化改动后重跑，确认没被牵连）：
  · 活动日历里**带 data-k**（真能点）的格子 → `cursor: pointer`
  · 活动日历里**不带 data-k**（没内容可点）的格子 → 不是 pointer
  · 跨月占位格 `.blank` → 不是 pointer
  · 倒计时日历**有日期无数据**的格子 → `default`（只能看，不能点）
用 Python 3.13 跑（起无头 Chrome 抠 `<pre id="CUR">`）。"""
import html
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_cur_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

INJ = """
<script>
(function(){
  function cur(sel){
    var e=document.querySelector(sel);
    if(!e) return null;
    var cs=getComputedStyle(e);
    return {cursor:cs.cursor, hasTip:!!e.dataset.tip, hasK:!!e.dataset.k,
            outlineStyle:cs.outlineStyle};
  }
  function n(sel){ return document.querySelectorAll(sel).length; }
  var out={
    /* 样本：优先挑"有数据"的那些，挑不到就退回第一个匹配 */
    calPicked: cur('#year-cal .ycell[data-k]') || cur('#year-cal .ycell'),
    calNoK:    cur('#year-cal .ycell:not([data-k]):not(.blank)') || cur('#year-cal .ycell:not([data-k])'),
    calBlank:  cur('#year-cal .ycell.blank'),
    cdNoData:  cur('#cd-cal .ycell[data-v="0"]'),
    counts:{
      calK:n('#year-cal .ycell[data-k]'), calAll:n('#year-cal .ycell'),
      calTip:n('#year-cal .ycell[data-tip]'), calBlank:n('#year-cal .ycell.blank'),
      cdZero:n('#cd-cal .ycell[data-v="0"]'), cdAll:n('#cd-cal .ycell'),
      bars:n('#bars .bar')
    }
  };
  var p=document.createElement('pre'); p.id='CUR';
  p.style.display='none'; p.textContent=JSON.stringify(out);
  document.body.appendChild(p);
})();
</script>
"""

src = io.open(SRC, encoding='utf-8').read().replace('</body>', INJ + '</body>', 1)
io.open(TMP, 'w', encoding='utf-8').write(src)
out = subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
                      '--hide-scrollbars', '--window-size=1280,900',
                      '--virtual-time-budget=3000', '--dump-dom',
                      'file:///' + TMP.replace('\\', '/')], capture_output=True)
dump = out.stdout.decode('utf-8', 'replace')
os.remove(TMP)
m = re.search(r'<pre id="CUR"[^>]*>(.*?)</pre>', dump, re.S)
if not m:
    raise SystemExit('!! 没拿到测量块（dump %d 字符）' % len(dump))
r = json.loads(html.unescape(m.group(1)))

print('计数：', json.dumps(r['counts'], ensure_ascii=False))
bad = []
for key, want in (('calPicked', 'pointer'), ('calNoK', 'not-pointer'),
                  ('calBlank', 'not-pointer'), ('cdNoData', 'default')):
    s = r.get(key)
    if not s:
        print('  %-9s —— 没找到样本（跳过）' % key)
        continue
    c = s['cursor']
    ok = (c == want) if want != 'not-pointer' else (c != 'pointer')
    print('  %-9s cursor=%-8s tip=%-5s k=%-5s → %s'
          % (key, c, s['hasTip'], s['hasK'], '✓' if ok else '★ 与预期不符（应 %s）' % want))
    if not ok:
        bad.append(key)
if r['counts']['calK'] == 0:
    bad.append('活动日历里一个可点格子都没有？')
if bad:
    print('★ 有问题：%s' % bad)
    sys.exit(1)
print('全部 ✓')
