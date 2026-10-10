# -*- coding: utf-8 -*-
"""UI 几何探针：量「块级内容」相对其卡片内边距的左右留白是否对称。

背景：日历热力图（`.year-cal`）是 `width:max-content` 的 flex 容器，
内容一旦窄于卡片内容区，就会**左对齐**、右侧空出一大块 —— 观感上
「左边贴着边、右边空一条」，而这在整页截图目视时很容易漏掉。

手法：读产物 HTML -> 往 </head> 注入实验 CSS（可选）-> 往 </body> 前注入
测量脚本 -> 无头 Chrome `--dump-dom` -> 正则抠 <pre id="EGEOM"> 里的 JSON。

用法：
  python _ui_geom_probe.py                     # 量现状（1280 / 1128 / 900 三档宽）
  python _ui_geom_probe.py --css ".year-cal{margin:0 auto}"   # 量实验 CSS
  python _ui_geom_probe.py --shot out.png --clip countdown    # 只截倒计时区
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import html as htmllib

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'heat-report-prototype.html')
TMP = os.path.join(HERE, '_probe_tmp.html')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _find_node():
    """CDP 版探针要 node。本机 PATH 时好时坏，所以按「环境变量 → PATH → 已知安装位」找。"""
    cand = [os.environ.get('NODE_BIN'), shutil.which('node'),
            os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node',
                         'versions', '22.22.2-3', 'node.exe'),
            r'D:\Apps\Pnpm\bin\node.EXE']
    for p in cand:
        if p and os.path.exists(p):
            return p
    return 'node'


NODE = _find_node()

MEASURE_JS = r"""
<script>
(function(){
  function R(el){var b=el.getBoundingClientRect();
    return {l:+b.left.toFixed(1),r:+b.right.toFixed(1),w:+b.width.toFixed(1),h:+b.height.toFixed(1)};}
  var out={vw:window.innerWidth,dpr:window.devicePixelRatio||1,cases:[]};
  ['year-cal','cd-cal'].forEach(function(id){
    var host=document.getElementById(id); if(!host) return;
    /* 平铺后两个日历面板（活动日历 / 倒计时日历）都恒可见，正常不会命中这个分支；
       保留它是因为**隐藏元素没有 rect**：一旦哪天又引入互相隐藏的容器，
       不跳过就会拿 0 宽去算填充率（除零 / 假 100%）。 */
    if(!host.getBoundingClientRect().width) return;
    var scroll=host.parentElement;          // .cal-scroll
    var panel=scroll.parentElement;         // .panel
    var cs=getComputedStyle(panel);
    var hcs=getComputedStyle(host);
    var vis=[].slice.call(host.children).filter(function(b){return b.style.display!=='none';});
    var all=host.children.length;
    var box=panel.getBoundingClientRect();
    var padL=parseFloat(cs.paddingLeft), padR=parseFloat(cs.paddingRight);
    var boxL=box.left+padL, boxR=box.right-padR;
    var hr=host.getBoundingClientRect();
    var rec={
      id:id,
      panel:{l:+box.left.toFixed(1),w:+box.width.toFixed(1)},
      padL:padL, padR:padR,
      boxW:+(boxR-boxL).toFixed(1),
      scroll:{w:+scroll.getBoundingClientRect().width.toFixed(1),
              clientW:scroll.clientWidth, offsetW:scroll.offsetWidth,
              scrollW:scroll.scrollWidth},
      hostLeft:+hr.left.toFixed(1), hostW:+hr.width.toFixed(1),
      justify:hcs.justifyContent, marginL:hcs.marginLeft, marginR:hcs.marginRight,
      hostWidthStyle:hcs.width,
      gap:parseFloat(hcs.columnGap)||0,
      blocksVisible:vis.length, blocksTotal:all,
      /* 关键三量：内容左侧留白 / 右侧留白 / 两者的差 */
      blankL:+(hr.left-boxL).toFixed(1),
      blankR:+(boxR-hr.right).toFixed(1),
      asym:+(Math.abs((boxR-hr.right)-(hr.left-boxL))).toFixed(1),
      fillPct:+((hr.width/(boxR-boxL))*100).toFixed(1),
      blocks:vis.map(function(b){
        var r=R(b), lab=b.querySelector('.ym-label');
        return {lab:lab?lab.textContent:'', l:r.l, w:r.w, cols:b.querySelectorAll('.ycell').length/7};
      }),
      hiddenLabels:all>vis.length?[]:null
    };
    /* 被 fitCalendar 隐藏的块（display:none）也报一下，便于判断"是否还能再塞" */
    rec.hiddenLabels=[].slice.call(host.children).filter(function(b){
      return b.style.display==='none';}).map(function(b){
      var lab=b.querySelector('.ym-label'); return lab?lab.textContent:''; });
    out.cases.push(rec);
  });
  /* 通用扫描：块级子元素若“内容窄于容器”就会左对齐、右侧堆空 —— 全页点名同类问题。
     只挑父级是普通块流（flex/grid 的子项由 justify 控制，不算这类问题）。 */
  var suspects=[];
  [].slice.call(document.querySelectorAll('*')).forEach(function(el){
    var ps=getComputedStyle(el);
    if(ps.display!=='block'&&ps.display!=='list-item') return;
    var p=el.parentElement; if(!p) return;
    var pcs=getComputedStyle(p);
    if(pcs.display==='flex'||pcs.display==='inline-flex'||pcs.display==='grid') return;
    var pr=p.getBoundingClientRect(), er=el.getBoundingClientRect();
    if(pr.width<20||er.width<20) return;
    var padL=parseFloat(pcs.paddingLeft), padR=parseFloat(pcs.paddingRight);
    var avail=pr.width-padL-padR;
    var blankL=er.left-(pr.left+padL);
    var blankR=(pr.right-padR)-er.right;
    /* 有意限宽（max-width）的元素不算缺陷：那是排版意图（控每行字数），
       不是"忘了居中"。例：.hero p{max-width:680px} 左 1px / 右 311px。 */
    var mw=parseFloat(ps.maxWidth);
    if(!isNaN(mw)&&mw<=er.width+1) return;
    if(er.width<avail-8 && Math.abs(blankR-blankL)>8)
      suspects.push({sel:el.id?'#'+el.id:('.'+String(el.className).trim().split(/\s+/).slice(0,2).join('.')),
        w:+er.width.toFixed(1), avail:+avail.toFixed(1),
        L:+blankL.toFixed(1), R:+blankR.toFixed(1),
        asym:+Math.abs(blankR-blankL).toFixed(1)});
  });
  /* 逐小时分布的「历史平均参考柱」：每格两根柱（当天 + 平均）必须**共用同一条刻度**。
     验证是**自洽**的 —— 不需要知道刻度上限：同刻度下「值 ÷ 像素高」应当是常量。
     若某根柱按自己的 max 缩放（典型错法：平均柱自归一化 → 又一根永远顶格的柱），
     这个比值立刻分叉，rel 变大。探针不必知道数据。
     只用「够高」的柱取样：矮柱触发了 2%/3% 的下限兜底，比值本就不该一致。 */
  out.hourRef=(function(){
    /* ⚠ 卡片存在就**必须**返回对象（哪怕 cells = 0）：返回 null 会让判据整段跳过，
       反向验证（把双柱拆回单柱）就变成"判据自己消失"的假绿 —— 实测踩过。
       只有卡片本身不在（空模板）才返回 null，那时确实没什么可量的。 */
    if(!document.getElementById('bars')) return null;
    var bh=[].slice.call(document.querySelectorAll('#bars .bh'));
    var day=[],avg=[];
    bh.forEach(function(b){
      var d=b.querySelector('.bar:not(.bar-avg)'),a=b.querySelector('.bar-avg');
      if(d) day.push({v:+d.getAttribute('data-v')||0,h:d.getBoundingClientRect().height});
      if(a) avg.push({v:+a.getAttribute('data-v')||0,h:a.getBoundingClientRect().height});
    });
    var all=day.concat(avg);
    /* ⚠ `Math.max.apply(null, [])` 是 -Infinity，`-Infinity || 1` 仍是 -Infinity，
       再经 JSON.stringify 变 null → 下游格式化直接 TypeError。
       退化态（--noavg：一根柱都没有）必须显式兜住。 */
    var base=all.length?Math.max.apply(null,all.map(function(o){return o.h;})):0;
    if(!(base>0)) base=1;
    var samp=all.filter(function(o){return o.v>0&&o.h>=base*0.15;});
    var rs=samp.map(function(o){return o.v/o.h;});
    var hi=rs.length?Math.max.apply(null,rs):0, lo=rs.length?Math.min.apply(null,rs):0;
    return {cells:bh.length,dayN:day.length,avgN:avg.length,
      dayHit:day.filter(function(o){return o.v>0;}).length,
      avgHit:avg.filter(function(o){return o.v>0;}).length,
      base:+base.toFixed(1),samp:samp.length,
      rel:rs.length?+((hi-lo)/hi*100).toFixed(1):null};
  })();
  /* 图例对齐：图例是它所描述内容的「注脚」，墨迹右边缘应与内容右边缘对齐。
     判据是 flushR = 图例墨迹右边缘 − 参照物右边缘，对齐则该值为 0。 */
  out.legends=[].slice.call(document.querySelectorAll('.legend')).map(function(lg){
    var panel=lg.closest('.panel');
    var pr=panel.getBoundingClientRect(), pcs=getComputedStyle(panel);
    var padL=parseFloat(pcs.paddingLeft), padR=parseFloat(pcs.paddingRight);
    var boxL=pr.left+padL, boxR=pr.right-padR;
    var rects=[].slice.call(lg.children).filter(function(el){
      var r=el.getBoundingClientRect();
      return r.width>0&&r.height>0&&getComputedStyle(el).visibility!=='hidden';
    }).map(function(el){return el.getBoundingClientRect();});
    if(!rects.length) return null;
    var il=Math.min.apply(null,rects.map(function(r){return r.left;}));
    var ir=Math.max.apply(null,rects.map(function(r){return r.right;}));
    /* 参照物 = 本卡片里那个"内容本体"。挑第一个**有 rect** 的：
       空数据态下 #year-cal 会存在但高度为 0，把它的 0 矩形当基准会得出全错的 flushR。
       `#bars` 是柱图（逐小时分布卡）的参照物 —— 同一页的图例可能挂在柱图卡片上，
       此时 panel 里根本没有日历，不加这一项会让 flushR 变成 null（那是"没基准"，
       不是"偏右"）。 */
    var ref=(function(){var c=['#year-cal','.cd-cal','#bars'];
      for(var i=0;i<c.length;i++){var e=panel.querySelector(c[i]);if(e&&e.getBoundingClientRect().width>0)return e;}
      return panel.querySelector('#year-cal')||panel.querySelector('.cd-cal')||panel.querySelector('#bars');})();
    var rr=ref?ref.getBoundingClientRect():null;
    return {
      host:(ref&&(ref.id||ref.className))||'?',
      boxL:+boxL.toFixed(1), boxR:+boxR.toFixed(1),
      lgT:+lg.getBoundingClientRect().top.toFixed(1),
      lgB:+lg.getBoundingClientRect().bottom.toFixed(1),
      lgL:+lg.getBoundingClientRect().left.toFixed(1),
      lgR:+lg.getBoundingClientRect().right.toFixed(1),
      inkL:+il.toFixed(1), inkR:+ir.toFixed(1),
      blankL:+(il-boxL).toFixed(1), blankR:+(boxR-ir).toFixed(1),
      /* 参照物 = 同一卡片里的日历/热力图本体 */
      refL:rr?+rr.left.toFixed(1):null, refR:rr?+rr.right.toFixed(1):null,
      refW:rr?+rr.width.toFixed(1):null,
      /* ★ 关键判据：图标右边缘相对内容右边缘的偏移（0 = 对齐） */
      flushR:rr?+(ir-rr.right).toFixed(1):null,
      flushL:rr?+(il-rr.left).toFixed(1):null
    };
  }).filter(Boolean);
  /* 注脚带（图例/说明）的**垂直开销**。图例是它所描述内容的注脚，两者之间只该隔
     "半行距"级别的空隙；隔出一条完整空行（>20px）时，观感就是"内容下面空了一大块"
     —— 用户圈的就是这一块。两个子判据：
       footGap  = 内容墨迹底 → 注脚墨迹顶（要紧贴内容，不能像另起一段）
       rowSlack = 注脚行盒高 − 注脚墨迹高（行盒里看不见的空白，>4px 就是在浪费行高）
     注意"内容墨迹底"必须取**最后一排可见格子**的底，不能取块盒的底：
     .ym-grid 是 repeat(7,13px) 的显式轨道，块盒底与格子底一致，但带内边距的
     滚动容器（.cal-scroll）取块盒会低估 footGap。 */
  out.foots=[].slice.call(document.querySelectorAll('.legend')).map(function(lg){
    var panel=lg.closest('.panel'); if(!panel) return null;
    var ref=(function(){var c=['#year-cal','#cd-cal','#bars'];
      for(var i=0;i<c.length;i++){var e=panel.querySelector(c[i]);if(e&&e.getBoundingClientRect().width>0)return e;}
      return panel.querySelector('#year-cal')||panel.querySelector('#cd-cal')||panel.querySelector('#bars');})();
    if(!ref) return null;
    var pcs=getComputedStyle(panel), pr=panel.getBoundingClientRect();
    var contentBot=pr.bottom-parseFloat(pcs.paddingBottom);
    var cells=[].slice.call(ref.querySelectorAll('.ycell,.hc'));
    /* 柱图（#bars）的"内容墨迹底"是它下面那行小时刻度（#bar-x），不是柱图容器的盒底：
       柱子只长到 #bars 的 170px 里，容器底本身没有墨迹，取盒底会把轴标签算成"内容"。 */
    var inkBot=cells.length?Math.max.apply(null,cells.map(function(c){
      return c.getBoundingClientRect().bottom;})):(function(){
        if(ref.id==='bars'){ var ax=document.getElementById('bar-x');
          if(ax) return ax.getBoundingClientRect().bottom; }
        return ref.getBoundingClientRect().bottom; })();
    /* 墨迹基准：**全部子元素**（色块 + 文字），并把行盒里的半行距扣掉。
       两处坑都踩过：
         · 只取色块（.legend i）：注脚一换行、色块被挤到**第二行**时，inkT 量到的是第二行的
           顶，凭空多出一个行高 —— 实测窄屏 360 下 footGap 虚报 27px，其实只有 8px；
         · 半行距必须按**单行**的行盒算（line-height），不能用元素盒高：文字一换行，
           盒高是 2~3 行，写 (盒高−字体盒)/2 会把首行的字形顶算到第二行去
           —— 实测窄屏 320 下 footGap 虚报 14.2px，其实 8px。
       字体盒按 ≈1.18em 估（Consolas + 中文回退实测 11px 字体 ≈13px 盒）。 */
    var kids=[].slice.call(lg.children).map(function(el){
      var r=el.getBoundingClientRect(), cs=getComputedStyle(el), fs=parseFloat(cs.fontSize)||0;
      var lh=parseFloat(cs.lineHeight); if(!isFinite(lh)) lh=1.18*fs;
      var half=Math.max(0,(lh-1.18*fs)/2);   /* 字形居中于行盒 ⇒ 上下各留 half */
      return {top:r.top+half, bottom:r.bottom-half, w:r.width, h:r.height, t:r.top};
    }).filter(function(r){return r.w>0&&r.h>0;});
    if(!kids.length) return null;
    var inkT=Math.min.apply(null,kids.map(function(k){return k.top;}));
    var inkB=Math.max.apply(null,kids.map(function(k){return k.bottom;}));
    var lr=lg.getBoundingClientRect();
    var scroll=ref.parentElement, scs=scroll?getComputedStyle(scroll):null;
    return {
      host:ref.id||String(ref.className).split(/\s+/)[0],
      gridInkBot:+inkBot.toFixed(1), contentBot:+contentBot.toFixed(1),
      rowT:+lr.top.toFixed(1), rowB:+lr.bottom.toFixed(1),
      rowH:+lr.height.toFixed(1),
      inkT:+inkT.toFixed(1), inkB:+inkB.toFixed(1),
      inkH:+(inkB-inkT).toFixed(1),
      footGap:+(inkT-inkBot).toFixed(1),      /* 内容 → 注脚 */
      footTail:+(contentBot-inkB).toFixed(1), /* 注脚 → 卡片内容底 */
      rowSlack:+(lr.height-(inkB-inkT)).toFixed(1),
      /* 注脚自己换了几行（按子元素盒顶去重，0.5px 容差）。
         换行后 rowSlack 天然含行间距 ⇒ "行盒藏空白"判据不适用，要跳过而不是误报。 */
      rows:(function(){var seen={},n=0;kids.forEach(function(k){
        var q=Math.round(k.t*2)/2; if(!seen[q]){seen[q]=1;n++;}}); return n;})(),
      scrollPadB:scroll?parseFloat(getComputedStyle(scroll).paddingBottom):null,
      scrollbarH:scroll?scroll.offsetHeight-scroll.clientHeight:null,
      overX:scroll?scroll.scrollWidth-scroll.clientWidth:null
    };
  }).filter(Boolean);
  /* 导航条：方向相反的**两个动作按钮必须分列两端**（同一页的「小时分布」卡片就是
     `[前一天] 标题 … [后一天]`）。缺陷有两种，都要点名：
       ① 两个按钮挨在一起（btnGap ≈ 行内 gap 10px）—— 用户找不到"下一周"；
       ② 左右不对称（sym 大）—— 一端贴边、另一端空。
     判据：btnGap > 40px（确实被拉开）且 sym ≤ 2px（两端对称）。 */
  out.navs=[].slice.call(document.querySelectorAll('.day-nav,.row')).map(function(nav){
    var panel=nav.closest('.panel'); if(!panel) return null;
    var pr=panel.getBoundingClientRect(), pcs=getComputedStyle(panel);
    var padL=parseFloat(pcs.paddingLeft), padR=parseFloat(pcs.paddingRight);
    var boxL=pr.left+padL, boxR=pr.right-padR;
    var btns=[].slice.call(nav.querySelectorAll('button'));
    if(btns.length<2) return null;
    /* ⚠ 曾被隐藏容器坑过：隐藏元素没有 rect，直接量会得到 btnGap≈0 的**误报**
       （"两按钮挨在一起"）。平铺后卡片内不再有互相 hidden 的容器，但这套量法
       仍要求"量之前元素必须真的在布局里"。 */
    var br=btns.map(function(b){return b.getBoundingClientRect();});
    var first=br[0], second=br[1], last=br[br.length-1];
    var lab=nav.querySelector('.lbl,.day-info,.title,.meta');
    var lr=lab?lab.getBoundingClientRect():null;
    var boxes=lr?br.concat([lr]):br;
    /* ── 「小时分布」日期信息块（.day-info）专有判据；别的导航行没有它，字段为 null ──
       ① 整块必须**水平居中于卡片内容区**（ctrOff ≤ 2）；
       ② 两行必须**上传下续、各自居中对齐**（stacked / lineOff ≤ 2）；
       ③ 不得压住左右按钮、导航行不得横向溢出（gapL/gapR ≥ 6、navOver ≤ 1）；
       ④ 宽度不足时统计行要**逐段裁剪**：可见集合必须是按 data-p 的**后缀集**
          （p 小的被裁 ⇒ 更小的也必须被裁），裁完必须装得下（fitOk）。
          分隔点用 getComputedStyle(seg,'::before').content 实读，不用 class 自证。 */
    var info=nav.querySelector('.day-info'), di=null;
    if(info){
      var ir=info.getBoundingClientRect();
      var ti=info.querySelector('.day-title'), me=info.querySelector('.day-meta');
      var trr=ti.getBoundingClientRect(), mrr=me.getBoundingClientRect();
      var pvb=br[0], nxb=br[br.length-1];
      var nvGap=10;                                  /* = .day-nav 的 gap */
      var btnW=Math.max(pvb.width,nxb.width);
      var avail=nav.clientWidth-2*(btnW+nvGap)-2;
      var segEls=[].slice.call(info.querySelectorAll('.seg'));   /* 两行统排一条梯子 */
      var segs=segEls.map(function(s){return {p:+s.dataset.p,
        hidden:getComputedStyle(s).display==='none', lead:s.classList.contains('lead'),
        title:s.parentNode===ti};});
      var visP=[], hidP=[], visN=0, dotN=0, leadN=0, titleN=0;
      var maxP=segs.reduce(function(a,s){return Math.max(a,s.p);},0);
      var dateVis=false;
      segs.forEach(function(s){ if(s.p===maxP&&!s.hidden) dateVis=true;
        if(s.hidden){hidP.push(s.p);return;}
        visN++; visP.push(s.p); if(s.lead)leadN++;
        if(s.title) titleN++; });
      segEls.forEach(function(s){ if(getComputedStyle(s).display==='none')return;
        if(getComputedStyle(s,'::before').content!=='none') dotN++; });
      di={
        ctrOff:+Math.abs((ir.left+ir.right)/2-(boxL+boxR)/2).toFixed(1),
        infoW:+ir.width.toFixed(1),
        lineOff:+Math.abs((trr.left+trr.right)/2-(mrr.left+mrr.right)/2).toFixed(1),
        stacked:trr.bottom<=mrr.top+0.6,
        gapL:+(ir.left-pvb.right).toFixed(1),
        gapR:+(nxb.left-ir.right).toFixed(1),
        navOver:nav.scrollWidth-nav.clientWidth,
        /* 两行取宽的那一行才是约束：量 `.day-info` 整体，别只量统计行 */
        fitOk:info.scrollWidth<=avail+0.5,
        tight:info.classList.contains('tight'),
        avail:+avail.toFixed(1), metaW:+info.scrollWidth.toFixed(1),
        line1W:+trr.width.toFixed(1), line2W:+mrr.width.toFixed(1),
        titleW:+trr.width.toFixed(1), btnW:+btnW.toFixed(1),
        /* 后缀集判据：被裁的最大 p 必须小于留下的最小 p */
        cropOk:(!hidP.length)||(!visP.length)||(Math.max.apply(null,hidP)<Math.min.apply(null,visP)),
        visN:visN, segN:segs.length, pVis:visP.join(','), pHid:hidP.join(','),
        /* 点只长在统计行内部：可见点应 = 统计行可见段数 − 1；
           若统计段全被裁掉（只剩标题行）则应为 0，不能是 -1。 */
        dotNeed:Math.max(0,(visN-titleN)-1), dotN:dotN,
        titleN:titleN, dateVis:dateVis,
        /* `.lead` 类只会被 fitDayInfo 加在「唯一一个可见统计行段」上；
           dotN==dotNeed 已校验它是否落在正确位置（放错/缺失/双份都会让点数对不上）。
           无可见统计段（极端窄屏全裁）时理应 0 个 lead，也合法。 */
        leadOk:((visN-titleN)>0) ? (leadN===1) : (leadN===0)
      };
    }
    return {
      key:nav.className.split(/\s+/)[0],
      di:di,
      btnIds:btns.map(function(b){return b.id||b.textContent.trim();}),
      n:btns.length,
      /* 整条导航的纵向墨迹范围（CSS px）—— 对照图据此裁带，不必做 CSS→设备换算 */
      bandT:+Math.min.apply(null,boxes.map(function(r){return r.top;})).toFixed(1),
      bandB:+Math.max.apply(null,boxes.map(function(r){return r.bottom;})).toFixed(1),
      leftInset:+(first.left-boxL).toFixed(1),
      rightInset:+(boxR-last.right).toFixed(1),
      sym:+Math.abs((boxR-last.right)-(first.left-boxL)).toFixed(1),
      btnGap:+(second.left-first.right).toFixed(1),
      wrapped:br.some(function(r){return Math.abs(r.top-first.top)>1;}),
      labGap:lr?+(lr.left-first.right).toFixed(1):null
    };
  }).filter(Boolean);
  /* 卡片化（本版契约）：日历与当天**各自成一张卡**（参照倒计时那节的卡片形式：每个内容
     单元一张 .panel，卡内用 .row 标题行"标题左 / 注释右"带头），两块同时可见，
     页面上不得出现 tab 控件、也不得有被互斥隐藏的内容块。
     —— 「分开，参考倒计时统计中的不同卡片」这一改动的验收点。
     判据必须能反向抓两种退化形态，否则它就是永远为真的死代码：
       ① 折回同一张卡（`--merged`）→ cards 由 2 变 1；
       ② 退回 tab 互斥（`--tabs`）→ tabN > 0、cards 1、当天块不可见。 */
  var _tabs=[].slice.call(document.querySelectorAll(".view-tabs .tab,[role='tab']"));
  var _calHost=document.querySelector('#year-cal');
  var _sec=_calHost?_calHost.closest('section'):null;
  var _cards=_sec?[].slice.call(_sec.querySelectorAll('.panel')):[];
  /* 「当天」那块是否真的露出来：卡片化后它不再有 .view-pane 包着，就按三个实体各自判。
     用**计算后 display** 判可见，而不是 hidden 属性 —— 任何方式造成的实际隐藏
     （CSS 覆盖、内联样式、[hidden]）都逃不过。 */
  var _dayBits=['#day-nav','#bars','#bar-x'].filter(function(s){
    var e=document.querySelector(s);
    return !!e && getComputedStyle(e).display!=='none';});
  out.flat={tabN:_tabs.length, cards:_cards.length,
    /* 每张卡都必须有**可见的**标题行，且标题文字非空 —— 卡片化不只是"多一层盒子" */
    rowVis:_cards.map(function(c){var r=c.querySelector(':scope > .row');
      return !!r && getComputedStyle(r).display!=='none';}),
    rowTitles:_cards.map(function(c){var t=c.querySelector(':scope > .row .title');
      return t?t.textContent.trim():null;}),
    dayVis:_dayBits.length, want:2};
  /* ── 参考序列的**跨日期一致性**（本版新增判据） ──
     历史同时段平均本身是**常量**（全周期同时段平均），所以它在每一天画出来也必须**一样高**。
     这一点只有在「刻度也不随日期变」时才成立：
       ⚠ 曾经实现成 `mx = max(当天峰值, 平均峰值)`（每天重算）→ 值不变、刻度变，
         同一根参考柱在不同日期高度不同 —— 观感上"参考自己也在动"，等于没有基线。
     判据三条：
       ① `refVSpread == 0`：参考柱的**数值**逐日恒定（数据侧，永远应为 0 —— 用来证明
          "变的是刻度不是数据"，把锅定死）；
       ② `refSpread ≤ 1`（px）：参考柱的**高度**逐日恒定（本判据真正要守的东西）；
       ③ `daySpread > 0`：当天柱高度确实随日期变（否则采样退化 —— 所有日期一模一样时
          判据恒真，就成了永远为真的死代码）。
     ⚠ 量完必须 `selectDay(keep)` 还原：后续的 suspects 扫描按选中那天的版面走。 */
  out.hourAxis=(function(){
    if(!document.getElementById('bars')||typeof selectDay!=='function'
       ||typeof DAY_KEYS==='undefined'||!DAY_KEYS.length) return null;
    /* 柱子被整块藏起来时（`--tabs` 那种互斥显隐）所有高度都是 0 → 判据会误报
       "采样退化"。这不是缺陷，是本判据在这一形态下无从量起 —— 显式跳过并说明。 */
    var b0=document.getElementById('bars').getBoundingClientRect();
    if(!b0.width||!b0.height) return {samples:0,hidden:true};
    var n=DAY_KEYS.length, pick=[], step=Math.max(1,Math.floor(n/9));
    for(var i=0;i<n;i+=step) pick.push(DAY_KEYS[i]);
    if(pick.indexOf(DAY_KEYS[n-1])<0) pick.push(DAY_KEYS[n-1]);
    var keep=selectedDay||DAY_KEYS[n-1];
    var rows=pick.map(function(k){
      selectDay(k);
      var a=[].slice.call(document.querySelectorAll('#bars .bar-avg'));
      var d=[].slice.call(document.querySelectorAll('#bars .bar:not(.bar-avg)'));
      function sumH(arr){var s=0;arr.forEach(function(e){s+=e.getBoundingClientRect().height;});return s;}
      function sumV(arr){var s=0;arr.forEach(function(e){s+=+e.getAttribute('data-v')||0;});return s;}
      return {k:k,refH:+sumH(a).toFixed(1),refV:sumV(a),dayH:+sumH(d).toFixed(1),dayV:sumV(d)};
    });
    selectDay(keep);
    function spread(arr){return Math.max.apply(null,arr)-Math.min.apply(null,arr);}
    return {samples:rows.length,dayList:rows.map(function(r){return r.k;}).join(','),
      refN:rows.length?document.querySelectorAll('#bars .bar-avg').length:0,
      refH:rows.map(function(r){return r.refH;}).join(','),
      refVSpread:spread(rows.map(function(r){return r.refV;})),
      refSpread:+spread(rows.map(function(r){return r.refH;})).toFixed(1),
      daySpread:+spread(rows.map(function(r){return r.dayH;})).toFixed(1)};
  })();
  out.suspects=suspects;
  var pre=document.createElement('pre'); pre.id='EGEOM';
  /* display:none 有两个好处：① 这行 JSON 不再出现在截图里（曾漏进对照图底部）；
     ② 不参与布局，连页面总高都不影响。--dump-dom 照样能抠到它的 textContent。 */
  pre.style.display='none';
  pre.textContent=JSON.stringify(out);
  document.body.appendChild(pre);
})();
</script>
"""

def remove_js(sel):
    """截图时只留「包含 sel 的那个 section」，方便把某张卡片单独截出来做对照。
    平铺后卡片内的两个块恒可见，不再需要"截图前先点 tab 把目标面板显示出来"那一步。"""
    return (r"""
<script>
(function(){
  var keep=document.querySelector(%s);
  var sec=keep?keep.closest('section'):null;
  [].slice.call(document.querySelectorAll('header,.wrap > section,.wrap > .note')).forEach(function(e){
    if(e!==sec) e.style.display='none';
  });
  if(sec) sec.style.marginTop='0';
})();
</script>
""" % json.dumps(sel))


# 反向验证（一）`--merged`：把两块**折回同一张卡**（= 上一版"平铺在同一张卡片里、中间一条
# 细线"的形态）。断言必须点名它（cards 由 2 变 1），否则「必须拆成两张独立卡」这组判据
# 就是永远为真的死代码。
# 反向验证（二）`--tabs`：再往前退一步，连 tab 栏一起回来（两块互斥显隐）。断言必须同时
# 点名 tabN > 0、cards 1、当天块不可见 —— 这是最极端的退化形态。
# ⚠ 两者各只读对应的 `_pre_*.js`（**单一实现**）：node 截图脚本 _shot_tiles.mjs 的 --pre
#   也用同一个文件，于是"反向验证"与"对照图渲改前"用的是同一段逻辑，不会各自漂移。
# ⚠ 这条反向验证当年是**逐字匹配源码字符串**再替换（NOW_NAV/THEN_NAV + assert "串没对上"），
#   改一次结构就得同步改两处字符串 —— 脆且常忘。现在改成**运行时注入**，与源码解耦。
def _pre_js(name):
    return '<script>' + open(os.path.join(HERE, name), encoding='utf-8').read() + '</script>'


MERGED_BACK_JS = _pre_js('_pre_merged.js')
TABS_BACK_JS = _pre_js('_pre_tabsback.js')
# 反向验证（三）`--noavg`：逐小时分布退回「只有当天一根柱」（本次改前的形态）。断言必须
# 点名「平均柱 0 根」。它同时是 `_avg_compare.py` 渲对照图「改前」帧用的同一份夹具。
# 反向验证（四）`--selfscale`：柱数不变，只让参考柱**按自己的峰值**归一化 —— 专门推翻
# 「两根柱共用同一条刻度」那一条（`hourRef.rel`）。两种退化分开点名，避免判据里有摆设。
NOAVG_BACK_JS = _pre_js('_pre_noavg.js')
SELFSCALE_BACK_JS = _pre_js('_pre_selfscale.js')
# 反向验证（五）`--datescale`：柱数、共用刻度都不动，只把**刻度退回逐日重算**
# （`mx = max(当天峰值, 平均峰值)`）—— 专门推翻「参考序列逐日恒定」（`hourAxis.refSpread`）。
# 这是用户直接报出来的那个观感缺陷：历史平均值明明是常量，切日期却"看起来不一样"。
DATESCALE_BACK_JS = _pre_js('_pre_datescale.js')
# 另一类反向验证（导航条「改前」形态 = 两个方向相反的按钮并排、信息块被 flex:1 顶偏）
# 不再单开开关，直接用通用注入即可：
#   --css '.day-nav{display:flex}.day-info{flex:1}.day-nav>button:first-child{width:160px}'
# 断言应报「★ 信息块没居中于卡片（偏 47.3px）」。⚠ 必须让两侧按钮不等宽才复现得出来，
# 细节见 --help 文本与 argparse 处的注释。

# 反向验证用：把「按宽度逐段裁剪」关掉（所有统计段一律显示），注入在测量脚本之前，
# 于是测量看到的是「裁剪没生效」的状态 —— 断言必须点名「没裁到装得下 / 压住按钮」，
# 否则这组裁剪判据就是永远为真的死代码。
UNCROP_JS = r"""<script>
(function(){
  [].slice.call(document.querySelectorAll('#day-meta .seg')).forEach(function(s){
    s.style.display=''; s.classList.remove('lead'); });
  var f=document.querySelector('#day-meta .seg'); if(f) f.classList.add('lead');
})();
</script>"""

def build(extra_css='', clip=False, only='#countdown', tabs=False, uncrop=False, extra_pre='',
          merged=False, noavg=False, selfscale=False, datescale=False):
    src = open(SRC, encoding='utf-8').read()
    if extra_css:
        src = src.replace('</head>', '<style id="_probe_css">' + extra_css + '</style></head>', 1)
    pre = ((MERGED_BACK_JS if merged else '') + (TABS_BACK_JS if tabs else '')
           + (NOAVG_BACK_JS if noavg else '') + (SELFSCALE_BACK_JS if selfscale else '')
           + (DATESCALE_BACK_JS if datescale else '')
           + (UNCROP_JS if uncrop else '') + extra_pre)
    # ⚠ pre 必须在 remove_js **之前**跑：extra_pre 可能重建 DOM（新增 section），
    #   而 remove_js 负责把「非目标 section」隐藏 —— 顺序反了，新建的段就漏在截图里。
    src = src.replace('</body>', pre + (remove_js(only) if clip else '') +
                      MEASURE_JS + '</body>', 1)
    open(TMP, 'w', encoding='utf-8').write(src)


def chrome(args, width, height, dsf=1):
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--force-device-scale-factor=%g' % dsf,
           '--window-size=%d,%d' % (width, height),
           '--virtual-time-budget=3000']
    cmd += args + ['file:///' + TMP.replace('\\', '/')]
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout.decode('utf-8', 'replace')


def measure(width, dsf=1):
    dump = chrome(['--dump-dom'], width, 900, dsf)
    # ⚠ 别写死成 <pre id="EGEOM">：加了 style 属性后属性与 > 之间会有别的字符
    m = re.search(r'<pre id="EGEOM"[^>]*>(.*?)</pre>', dump, re.S)
    if not m:
        print('!! 没拿到测量块，dump 长度 %d' % len(dump))
        print(dump[:600])
        return None
    raw = htmllib.unescape(m.group(1)).strip()
    return json.loads(raw)


def show(r):
    if not r:
        return
    print('=== viewport %d (dpr %g) ===' % (r['vw'], r['dpr']))
    for c in r['cases']:
        print('  [%s] 卡片内容宽 %.1f (padding L/R %.0f/%.0f) | 块可见 %d/%d  隐藏:%s'
              % (c['id'], c['boxW'], c['padL'], c['padR'], c['blocksVisible'],
                 c['blocksTotal'], ','.join(c['hiddenLabels']) or '无'))
        print('        内容 左%.1f 宽%.1f | 留白 左 %.1f 右 %.1f  不对称度 %.1f  填充率 %.1f%%'
              % (c['hostLeft'], c['hostW'], c['blankL'], c['blankR'], c['asym'], c['fillPct']))
        print('        justify=%s margin=%s/%s width=%s gap=%.0f scrollClientW=%d scrollW=%d'
              % (c['justify'], c['marginL'], c['marginR'], c['hostWidthStyle'],
                 c['gap'], c['scroll']['clientW'], c['scroll']['scrollW']))
        print('        blocks: ' + ' '.join('%s(%.0f,w%.0f,c%g)'
              % (b['lab'], b['l'], b['w'], b['cols']) for b in c['blocks']))
    for g in (r.get('legends') or []):
        # 拿不到横向参照物时 flushR 为 None —— 那是"没有基准"，不是"偏右"，不能报红。
        # （新增的柱图卡片图例曾因此假红：`参照物 ? None..None | ★ 偏右 +0.0`。）
        if g['flushR'] is None:
            tag, fr = '· 无横向参照物（该卡片没有可比的日历/柱图本体）', '—'
        else:
            tag = '对齐' if abs(g['flushR']) <= 2 else '★ 偏右 %+.1f' % g['flushR']
            fr = '%+.1f' % g['flushR']
        print('  [图例] 卡片内容 %s..%s | 图例墨迹 %s..%s (左留白 %.1f 右留白 %.1f)'
              % (g['boxL'], g['boxR'], g['inkL'], g['inkR'], g['blankL'], g['blankR']))
        print('         参照物 %s %s..%s (宽 %s) | 图例右缘相对内容右缘 %s  →  %s'
              % (g['host'], g['refL'], g['refR'], g['refW'], fr, tag))
    hr = r.get('hourRef')
    if hr:
        # 逐小时分布：每格两根柱（当天 + 全周期同时段平均）必须**共用同一条刻度**。
        # rel 是自洽指标 —— 探针不必知道数据：同刻度下「值 ÷ 像素高」是常量，
        # 谁要是按自己的 max 归一化，这个比值立刻分叉。
        hb = []
        if hr['cells'] != 24:
            hb.append('★ 逐小时格子 %d ≠ 24（双柱容器 #bars .bh 缺失，即退回单柱）' % hr['cells'])
        if hr['dayN'] != 24 or hr['avgN'] != 24:
            hb.append('★ 每格应有「当天 + 平均」两根柱（实测 当天 %d / 平均 %d）'
                      % (hr['dayN'], hr['avgN']))
        if hr['samp'] >= 3 and (hr['rel'] or 0) > 5:
            hb.append('★ 两根柱没共用同一条刻度（值/像素高 离散 %.1f%%）' % hr['rel'])
        print('  [逐小时参考] 格子 %d 个 | 当天柱 %d（有值 %d）/ 平均柱 %d（有值 %d）| 取样 %d 根'
              '| 最高柱 %.1fpx'
              % (hr['cells'], hr['dayN'], hr['dayHit'], hr['avgN'], hr['avgHit'], hr['samp'],
                 hr['base']))
        print('               刻度共用：等高柱「值/像素高」离散 rel %s（同刻度应 ≈ 0）'
              % ('—' if hr['rel'] is None else '%.1f%%' % hr['rel']))
        print('               → %s' % ('；'.join(hb) if hb else '两根柱共用同一条刻度 ✓'))
    ha = r.get('hourAxis')
    if ha and ha.get('hidden'):
        # 柱图被整块隐藏（互斥显隐的旧形态）→ 本判据无从量起，交给「卡片化」那条去抓
        print('  [刻度恒定] 柱图区被隐藏（宽高为 0）—— 本判据不适用，跳过')
        ha = None
    if ha:
        # 参考序列的跨日期一致性：参考值是常量 ⇒ 它每一天都该**一样高**。
        # 只有刻度也恒定才成立；刻度跟着当天走的话，基线会"自己动"。
        ab = []
        if not ha.get('refN'):
            # 一根参考柱都没有 → refSpread 必然为 0，这条判据是**空转**（不能说它"通过"）；
            # 真正的缺陷由 `[逐小时参考]` 那组抓（--noavg 会报「格子 0 ≠ 24」）。
            ab.append('· 本帧没有参考柱 —— 极差为 0 是空转，不是通过')
        if ha['refVSpread'] != 0:
            ab.append('★ 参考柱的**数值**逐日不一致（极差 %g）—— 数据侧就错了' % ha['refVSpread'])
        if ha['refSpread'] > 1:
            ab.append('★ 参考柱高度逐日不一致（极差 %.1fpx）—— 刻度随日期变，基线自己在动'
                      % ha['refSpread'])
        if ha['daySpread'] <= 0:
            ab.append('★ 当天柱高度逐日完全相同 —— 采样退化，本判据恒真（等于死代码）')
        print('  [刻度恒定] 采样 %d 天：%s' % (ha['samples'], ha['dayList']))
        print('             参考柱高度(px) %s | 极差 %.1f（应 ≤1）| 数值极差 %g（应 0）| 当天柱极差 %.1f（应 >0）'
              % (ha['refH'], ha['refSpread'], ha['refVSpread'], ha['daySpread']))
        print('             → %s' % ('；'.join(ab) if ab else '参考序列逐日恒定 ✓'))
    for f in (r.get('foots') or []):
        # 判据：footGap ≤ 12px（注脚紧跟内容）且 rowSlack ≤ 4px（行盒不藏空白）
        bad = []
        if f['footGap'] > 20:
            bad.append('★ 内容与注脚之间空出一整行（%.1fpx）' % f['footGap'])
        elif f['footGap'] > 12:
            bad.append('· 内容与注脚间距偏大（%.1fpx，宜 ≤12）' % f['footGap'])
        if f['rowSlack'] > 4 and f['rows'] <= 1:
            bad.append('★ 注脚行盒比墨迹高 %.1fpx（藏着看不见的空白）' % f['rowSlack'])
        print('  [注脚带] %-12s 内容墨迹底 %.1f → 注脚墨迹 %s | footGap %.1f  footTail %.1f  行数 %d'
              % (f['host'], f['gridInkBot'], '—', f['footGap'], f['footTail'], f['rows']))
        print('           行盒高 %.1f 墨迹高 %.1f rowSlack %.1f | 滚动容器 paddingB %s 滚动条 %s 横向溢出 %s'
              % (f['rowH'], f['inkH'], f['rowSlack'], f['scrollPadB'], f['scrollbarH'], f['overX']))
        if f['rows'] > 1 and f['rowSlack'] > 4:
            bad.append('· 注脚已换 %d 行 —— rowSlack 含行间距，该判据跳过（只看 footGap）' % f['rows'])
        print('           → %s' % ('；'.join(bad) if bad else '紧凑 ✓'))
    for nv in (r.get('navs') or []):
        # ⚠ 换行时「两端分列」判据不适用：flex-wrap 把末按钮折到第二行，
        #   它的 x 与首按钮重叠，btnGap 会算出负数 —— 那是误报，不是缺陷。
        if nv['wrapped']:
            tag = '· 窄屏已换行 —— 两端分列判据不适用（跳过）'
        elif nv['btnGap'] <= 40:
            tag = '★ 两个按钮挨在一起（间距仅 %.0fpx）' % nv['btnGap']
        elif nv['sym'] > 2:
            tag = '★ 左右不对称（差 %.1fpx）' % nv['sym']
        else:
            tag = '两端分列 ✓'
        print('  [导航] %-10s 按钮: %s' % (nv['key'], ' / '.join(nv['btnIds'])))
        print('        左端内缩 %.1f | 右端内缩 %.1f | 对称差 %.1f | 首两个按钮间距 %.1f | 换行 %s | 标签距首按钮 %.1f'
              % (nv['leftInset'], nv['rightInset'], nv['sym'], nv['btnGap'],
                 '是' if nv['wrapped'] else '否',
                 nv['labGap'] if nv['labGap'] is not None else -1))
        print('        → %s' % tag)
        if nv.get('di'):
            d = nv['di']
            bad = []
            if not d['stacked']:
                bad.append('★ 日期与统计没分成上下两行（还是并排）')
            if d['lineOff'] > 2:
                bad.append('★ 上下两行没对齐（中心差 %.1fpx）' % d['lineOff'])
            if d['ctrOff'] > 2:
                bad.append('★ 信息块没居中于卡片（偏 %.1fpx）' % d['ctrOff'])
            if d['gapL'] < 6 or d['gapR'] < 6:
                bad.append('★ 压住按钮了（左 %.1f / 右 %.1f）' % (d['gapL'], d['gapR']))
            if d['navOver'] > 1:
                bad.append('★ 导航行横向溢出 %dpx' % d['navOver'])
            if not d['fitOk']:
                bad.append('★ 统计行没裁到装得下（%.1f > 可用 %.1f）' % (d['metaW'], d['avail']))
            if not d['cropOk']:
                bad.append('★ 裁剪顺序不是按优先级（裁了 p=[%s]，却留着 p=[%s]）'
                           % (d['pHid'], d['pVis']))
            if not d['leadOk'] or d['dotN'] != d['dotNeed']:
                bad.append('★ 段间分隔点与可见段不匹配（实读点 %d / 应为 %d）'
                           % (d['dotN'], d['dotNeed']))
            if not d['dateVis']:
                bad.append('★ 日期被裁掉了（它必须是梯子的最后一档）')
            print('        [日期块] 居中偏 %.1f | 两行中心差 %.1f 分上下 %s | 与按钮间距 %.1f/%.1f 溢出 %d'
                  % (d['ctrOff'], d['lineOff'], '是' if d['stacked'] else '否',
                     d['gapL'], d['gapR'], d['navOver']))
            print('                 两行 %s/%.1f 可用 %.1f | 段 %d/%d 可见 p=[%s] 裁 p=[%s] 点 %d/%d 标题段 %d'
                  % (d['line1W'], d['line2W'], d['avail'], d['visN'], d['segN'],
                     d['pVis'], d['pHid'], d['dotN'], d['dotNeed'], d['titleN']))
            for b in bad:
                print('                 %s' % b)
            if not bad:
                print('                 → 居中 + 两行 + 按宽度依次裁剪 ✓%s'
                      % ('（已收字号 .tight）' if d['tight'] else ''))
    fb = r.get('flat')
    if fb:
        want = fb['want']
        rows = fb['rowVis'] or []
        titles = fb['rowTitles'] or []
        ok = (fb['tabN'] == 0 and fb['cards'] == want and fb['dayVis'] == 3
              and len(rows) == want and all(rows)
              and all(t for t in titles))
        if ok:
            why = '两块各自成卡、每卡都有可见标题行、页面上没有 tab 控件 ✓'
        elif fb['tabN']:
            why = '★ 又出现了 tab 控件（%d 个）—— 要求拆成两张卡，不该有切换控件' % fb['tabN']
        elif fb['cards'] != want:
            why = '★ 卡片数 %d ≠ %d（两块必须各自成卡，不能折回同一张）' % (fb['cards'], want)
        elif fb['dayVis'] != 3:
            why = '★ 「当天」块只有 %d/3 个实体可见（#day-nav/#bars/#bar-x 必须都露出来）' % fb['dayVis']
        elif not all(rows):
            why = '★ 有卡片缺标题行 .row（或它被隐藏）—— 卡片化要求每卡自带"标题左 / 注释右"'
        else:
            why = '★ 有卡片标题行文字为空：%s' % (titles,)
        print('  [卡片化] tab 控件 %d 个 | 卡片 %d 张（应 %d）| 当天块 %d/3 可见'
              % (fb['tabN'], fb['cards'], want, fb['dayVis']))
        print('           标题行 %s | 标题 %s'
              % ('/'.join('有' if v else '★缺' for v in rows), titles))
        print('             → %s' % why)
    sus = r.get('suspects') or []
    print('  [全页同类扫描] ' + ('干净，没有“窄于容器却左对齐”的块' if not sus else ''))
    for s in sus:
        print('        %-26s 宽 %.1f / 可用 %.1f | 左 %.1f 右 %.1f  不对称 %.1f'
              % (s['sel'], s['w'], s['avail'], s['L'], s['R'], s['asym']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--css', default='', help='注入 <head> 的实验 CSS')
    ap.add_argument('--widths', default='1280,1128,900')
    ap.add_argument('--shot', default='', help='截图输出路径')
    ap.add_argument('--clip', action='store_true', help='截图时只留 --only 命中的那个 section')
    ap.add_argument('--only', default='#countdown', help='--clip 时保留哪一块（选择器，默认 #countdown）')
    ap.add_argument('--height', type=int, default=900)
    ap.add_argument('--dsf', type=float, default=1,
                    help='device scale factor；分数 DPR（1.25/1.5）会暴露取整导致的 0.5px 错位')
    ap.add_argument('--merged', action='store_true',
                    help='反向验证：把两块折回同一张卡（上一版"平铺在同一卡片里、中间一条细线"的形态），'
                         '断言必须报红（卡片数 2 → 1）')
    ap.add_argument('--tabs', action='store_true',
                    help='反向验证：再退一步到「tab 互斥」旧结构（插回 tab 栏 + 藏起当天块），断言必须报红')
    ap.add_argument('--uncrop', action='store_true',
                    help='反向验证：关掉日期统计行的「按宽度逐段裁剪」，断言必须报红')
    ap.add_argument('--noavg', action='store_true',
                    help='反向验证：逐小时分布退回「只有当天一根柱」（删参考柱与图例、刻度退回当天峰值），'
                         '断言必须报红（平均柱 0 根）。该夹具同时用于渲对照图的「改前」帧')
    ap.add_argument('--selfscale', action='store_true',
                    help='反向验证：参考柱按自己的峰值归一化（柱数不变、只有刻度错），'
                         '断言必须报红（刻度共用自洽离散 rel 变大）')
    ap.add_argument('--datescale', action='store_true',
                    help='反向验证：刻度退回「按当天峰值逐日重算」的旧行为（柱数不变、'
                         '单帧内两柱仍共刻度，但参考柱高度逐日不一致），'
                         '断言必须报红（参考柱跨日高度极差变大）')
    # 导航条判据（两端分列 / 信息块居中）的反向验证不用单开开关，直接注入「改前」形态：
    #   --css '.day-nav{display:flex}.day-info{flex:1}.day-nav>button:first-child{width:160px}'
    #   预期：★ 信息块没居中于卡片（偏 47.3px）
    # ⚠ 必须**同时让两侧按钮不等宽**。只写 `display:flex + flex:1` 是复现不出来的：
    #   两个按钮等宽时 flex:1 盒的中点恰好落在卡片中点，实测 ctrOff = 0（会以为判据失效）。
    #   偏差恒等于 (左按钮宽 − 右按钮宽) / 2，实测 160 与 65.5 → 偏 47.3px，与公式吻合。
    ap.add_argument('--emul', default='',
                    help='窄视口模拟（CDP Emulation）：逗号分隔的 CSS 宽度，'
                         '走 _narrow_cdp.mjs。--window-size 在 Windows 上被钳到最小 ~516px，'
                         '小于它的宽度只能这样量')
    ap.add_argument('--shotprefix', default='',
                    help='配合 --emul：每个宽度截一张图，前缀如 _nar_（得到 _nar_360.png …）')
    ap.add_argument('--pre', default='',
                    help='测量前注入的 JS **内容**，如 --pre "$(cat _dark.js)" 切暗色做同一组判据。'
                         '⚠ 这里传内容；node 截图脚本 _shot_tiles.mjs 的 --pre 传的是**文件名**')
    a = ap.parse_args()

    if a.emul:
        # ⚠ 把测量脚本写成文件交给 mjs，**不在 JS 里再写一份量法**，否则两边会跑偏。
        js = os.path.join(HERE, '_probe_measure.js')
        open(js, 'w', encoding='utf-8').write(MEASURE_JS)
        pre = os.path.join(HERE, '_probe_pre.js')
        pre_src = ('<script>'+a.pre+'</script>' if a.pre else '') + \
                  (MERGED_BACK_JS if a.merged else '') + \
                  (TABS_BACK_JS if a.tabs else '') + \
                  (NOAVG_BACK_JS if a.noavg else '') + \
                  (SELFSCALE_BACK_JS if a.selfscale else '') + \
                  (DATESCALE_BACK_JS if a.datescale else '') + \
                  (UNCROP_JS if a.uncrop else '')
        if pre_src:
            open(pre, 'w', encoding='utf-8').write(pre_src)
        cmd = [NODE, os.path.join(HERE, '_narrow_cdp.mjs'),
               '--widths', a.emul, '--js', js, '--html', SRC,
               '--height', str(a.height)]
        if a.css:
            cmd += ['--css', a.css]
        if pre_src:
            cmd += ['--pre', pre]
        if a.shotprefix:
            cmd += ['--shotprefix', os.path.join(HERE, a.shotprefix)]
        r = subprocess.run(cmd, capture_output=True)
        err = r.stderr.decode('utf-8', 'replace').strip()
        if err:
            print(err)
        for line in r.stdout.decode('utf-8', 'replace').splitlines():
            line = line.strip()
            if line.startswith('{'):
                show(json.loads(line))
        return

    build(a.css, a.clip, a.only, a.tabs, a.uncrop,
          ('<script>' + a.pre + '</script>') if a.pre else '', a.merged,
          a.noavg, a.selfscale, a.datescale)

    if a.shot:
        out = os.path.abspath(a.shot)
        widths = [int(w) for w in a.widths.split(',')]
        base = out.rsplit('.', 1)
        for w in widths:
            target = base[0] + '_%d.' % w + base[1]
            # ⚠ 视口/图像尺寸差（实测确认，别想当然）：
            #   两个模式的**视口宽都是 W − 16**（截图里注入测量脚本可读到 innerWidth=1112 当 W=1128）；
            #   但 --screenshot 的**图像宽 = W**，比视口多 16px，那 16px 在右侧是未绘制的空白带。
            #   ⇒ 截图传 W，取像素坐标时只用到 [0, W−16) 这一段（CROP 右边界别越过 W−16）。
            chrome(['--screenshot=' + target], w, a.height, a.dsf)
            print('shot -> %s  (图像宽 %d = 窗口 %d × dsf %g；视口 %d)'
                  % (target, int(w * a.dsf), w, a.dsf, w - 16))
        return

    for w in [int(x) for x in a.widths.split(',')]:
        show(measure(w, a.dsf))


if __name__ == '__main__':
    main()
