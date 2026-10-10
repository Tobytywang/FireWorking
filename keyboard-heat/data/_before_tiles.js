/* 「改前」：把 总览 还原成原来的「键盘 / 鼠标 / 时间」三簇等高卡网格，
   用于改前/改后对照图。依赖页面顶层的 const（ALL_KEYS 等）与 fmtShort/countUp。 */
(function(){
  var host=document.getElementById('stats'); if(!host) return;
  host.className='stats';
  var hours=ALL_ACT/3600;
  var avgRate=ACTIVE_MIN?Math.round(ALL_EQUIV/ACTIVE_MIN):0;
  var bsRate=(ALL_KEYS+ALL_BS)?(ALL_BS/(ALL_KEYS+ALL_BS)*100):0;
  var perDay=DAY_KEYS.length?Math.round(ALL_EQUIV/DAY_KEYS.length):0;
  var clusters=[
    {name:'⌨ 键盘', items:[
      {k:'总击键数',v:ALL_KEYS,u:''}, {k:'退格占比',v:bsRate,u:'%',d:1}, {k:'活跃时段均速',v:avgRate,u:'活跃/分'}]},
    {name:'🖱 鼠标', items:[
      {k:'鼠标移动',v:fmtShort(ALL_MV),u:'次',num:false}, {k:'鼠标点击',v:fmtShort(ALL_CK),u:'次',num:false},
      {k:'鼠标滚轮',v:fmtShort(ALL_SC),u:'格',num:false}, {k:'鼠标占比',v:MOUSE_SHARE,u:'%',d:1}]},
    {name:'⏱ 时间', items:[
      {k:'活跃时长',v:hours,u:'小时',d:1}, {k:'日均活跃',v:fmtShort(perDay),u:'',num:false},
      {k:'最热一天',v:BEST_DAY?BEST_DAY.slice(5):'--',u:BEST_DAY?fmtShort(Math.round(BEST_EQUIV)):'',num:false}]}
  ];
  host.innerHTML=clusters.map(function(c){
    return '<div class="cluster"><div class="cluster-h">'+c.name+'</div><div class="cluster-grid">'+
      c.items.map(function(it){return '<div class="stat"><div class="k">'+it.k+'</div><div class="v"><span></span>'+(it.u?'<small>'+it.u+'</small>':'')+'</div></div>';}).join('')+
      '</div></div>';}).join('');
  var spans=host.querySelectorAll('.stat .v span'); var acc=0;
  clusters.forEach(function(c){c.items.forEach(function(it){
    var span=spans[acc++];
    if(it.num===false) span.textContent=it.v;
    else if(typeof countUp==='function') countUp(span,it.v,'',it.d||0); else span.textContent=it.v;
  });});
})();
