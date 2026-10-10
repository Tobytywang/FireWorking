# -*- coding: utf-8 -*-
"""实测「点日历上的日期 → 下方当天块是否更新、是否被带进视野」。

平铺后点日期不再切换视图（当天块一直可见），所以原来的"切视图"反馈由
`revealDayPane()`（scrollIntoView block:nearest）承担。本脚本用真实 click 触发，
等滚动跑完再读最终状态。

实测（2026-09-29，1280×805 视口）：
  behavior=smooth → yEnd 0（**一次都没滚**，当天块仍在视口外 inView:false）
  behavior=auto   → yEnd 498、当天块底边贴到视口底（inView:true）
⇒ 生成器里因此用 `auto`。传参可复测： python _click_link_probe.py smooth|auto
"""
import html
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_clk_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
BEHAVIOR = sys.argv[1] if len(sys.argv) > 1 else 'auto'

INJ = """
<script>
(function(){
  var cells=document.querySelectorAll('#year-cal .ycell[data-k]');
  var cell=cells[cells.length-1];
  /* 当天那块现在整张卡（#day-card）就是目标 —— 卡片化后它不再有 .view-pane 容器 */
  var pane=document.getElementById('day-card');
  var t0=document.getElementById('day-title').textContent;
  /* 先把当天块滚出视野，才能验证"点日期会把它带回来" */
  window.scrollTo(0,0);
  var y0=window.scrollY;
  if(cell) cell.click();
  setTimeout(function(){
    var r=pane.getBoundingClientRect();
    var p=document.createElement('pre'); p.id='CLC';
    var prev=cell?cells[cells.length-2]:null;
    var before2=t0;
    if(prev) prev.click();                       /* 再点另一个有数据的日期，看标题是否真的变 */
    p.textContent=JSON.stringify({
      behavior:'__B__', cells:cells.length, key:cell?cell.dataset.k:null,
      y0:y0, yEnd:Math.round(window.scrollY),
      titleBefore:before2, titleAfterClickOther:document.getElementById('day-title').textContent,
      paneTop:Math.round(r.top), paneBot:Math.round(r.bottom), vpH:window.innerHeight,
      inView:(r.top<window.innerHeight&&r.bottom>0)});
    document.body.appendChild(p);
  },1500);
})();
</script>
"""

src = io.open(SRC, encoding='utf-8').read().replace(
    '</body>', INJ.replace('__B__', BEHAVIOR) + '</body>', 1)
# 把 revealDayPane 的 behavior 换成待测值（探针只改这一处，不动源文件）。
# ⚠ 这里必须按**源文件当前的**字面值去替换，并断言命中：源文件从 smooth 改成 auto 之后，
#   旧写法（只在非 smooth 时才替换 `behavior:'smooth'`）会**静默失效** —— 传 smooth 测出来
#   的其实还是 auto，得出"平滑滚动有效"的错误结论。命中数断言就是防这个。
_OLD = "scrollIntoView({behavior:'auto',block:'nearest'})"
assert src.count(_OLD) == 1, '没找到 revealDayPane 的 scrollIntoView 调用（源文件改了？）'
src = src.replace(_OLD, "scrollIntoView({behavior:'%s',block:'nearest'})" % BEHAVIOR)
io.open(TMP, 'w', encoding='utf-8').write(src)
out = subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
                      '--hide-scrollbars', '--window-size=1280,900',
                      '--virtual-time-budget=4000', '--dump-dom',
                      'file:///' + TMP.replace('\\', '/')], capture_output=True)
dump = out.stdout.decode('utf-8', 'replace')
os.remove(TMP)
m = re.search(r'<pre id="CLC">(.*?)</pre>', dump, re.S)
if not m:
    print('!! 没拿到测量块（dump %d 字符）—— 注入脚本可能语法错' % len(dump))
else:
    print('实测：', html.unescape(m.group(1)))
