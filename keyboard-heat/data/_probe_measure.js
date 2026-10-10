
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
