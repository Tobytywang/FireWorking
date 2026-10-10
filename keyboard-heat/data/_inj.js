<script>
(function(){
  var out={vw:innerWidth, dpr:devicePixelRatio, rows:[]};
  try{
  function box(el){ var cs=getComputedStyle(el), r=el.getBoundingClientRect();
    var pl=parseFloat(cs.paddingLeft)||0, pr=parseFloat(cs.paddingRight)||0,
        bl=parseFloat(cs.borderLeftWidth)||0, br=parseFloat(cs.borderRightWidth)||0;
    return {L:r.left+bl+pl, R:r.right-br-pr}; }
  /* 文字「墨迹」盒：Range.selectNodeContents 量字形实际占的矩形，不是行盒。 */
  function ink(el){ var rg=document.createRange(); rg.selectNodeContents(el);
    var r=rg.getBoundingClientRect();
    return {l:+r.left.toFixed(1),t:+r.top.toFixed(1),w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; }
  function lines(el){ return el.getClientRects().length; }
  /* 参考物 = 行的下一个兄弟元素的内容盒右缘（面板要剥掉 padding） */
  function refR(el){ var n=el.nextElementSibling; return n?+box(n).R.toFixed(1):null; }

  var ROW=".row", TITLE=".title", META=".meta";
  function push(kind, host, ti, mi){
    var b=box(host), rf=refR(host);
    out.rows.push({kind:kind, t:String(ti.el.textContent||'').trim().slice(0,16),
      contR:+b.R.toFixed(1),
      wasteR:+(b.R-(mi.l+mi.w)).toFixed(1),
      gap:+(mi.l-(ti.l+ti.w)).toFixed(1),
      alignL:+(ti.l-b.L).toFixed(1),
      flushR:rf==null?null:+(b.R-rf).toFixed(1),
      wrap:(mi.t>ti.t+2)?1:0,
      lines:lines(mi.el), mW:+mi.w.toFixed(1),
      over:+(host.scrollWidth-host.clientWidth).toFixed(0)});
  }
  [].slice.call(document.querySelectorAll(ROW)).forEach(function(host){
    var t=host.querySelector(TITLE), m=host.querySelector(META);
    if(!t||!m) return;
    var ti=ink(t), mi=ink(m); ti.el=t; mi.el=m;
    push('row', host, ti, mi);
  });
  /* 可选：把 section 级「标题 + 副标题」也量进来（用于判断该不该一起改） */
  if(true){
    [].slice.call(document.querySelectorAll('h2')).forEach(function(h){
      var sp=h.querySelector('span'); if(!sp) return;
      var tn=null;                                   /* 标题文字节点（比 h2 盒更准） */
      for(var i=0;i<h.childNodes.length;i++){
        if(h.childNodes[i].nodeType===3 && h.childNodes[i].textContent.trim()){ tn=h.childNodes[i]; break; } }
      var rg=document.createRange(); rg.selectNodeContents(tn||h);
      var tr=rg.getBoundingClientRect();
      var ti={l:+tr.left.toFixed(1),t:+tr.top.toFixed(1),w:+tr.width.toFixed(1),el:tn||h};
      var mi=ink(sp); mi.el=sp;
      push('h2', h, ti, mi);
    });
  }
  }catch(e){ out.err=String((e&&e.stack)||e); }
  var pre=document.createElement('pre'); pre.id='EGEOM';
  pre.style.display='none'; pre.textContent=JSON.stringify(out);
  document.body.appendChild(pre);
})();
