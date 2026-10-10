/* 反向验证夹具：把逐小时柱图的刻度退回**旧的逐日重算**行为
   （`mx = max(当天峰值, 平均峰值)`）—— 也就是本轮修掉的那个缺陷：
   参考序列的值没变，但刻度随选中日期变 → 同一根参考柱在不同日期高度不同。

   做法：**运行时替换** `hourAxisMax`，然后重渲一次。
   渲染路径仍只有一份实现（selectDay → drawBars），这里只换刻度函数，
   不复制任何绘图逻辑 —— 所以"探针看到的就是真代码的行为"。

   ⚠ 当天峰值必须**从数据算**，不能读柱子的 `data-v`：`hourAxisMax()` 是在
     `drawBars` 里、`innerHTML` 被替换**之前**调用的，此刻 DOM 里还是**上一天**的柱，
     读 DOM 会拿到上一天的峰值（夹具会静默测错）。 */
(function(){
  function dayPeak(){
    if(typeof selectedDay==='undefined'||!selectedDay
       ||typeof dataMinute!=='function'||typeof mouseEquiv!=='function') return 1;
    var arr=new Array(24).fill(0);
    for(const r of dataMinute(selectedDay)) arr[Math.floor(r[0]/60)] += r[1]+mouseEquiv(r);
    var m=1; for(var h=0;h<24;h++) if(arr[h]>m) m=arr[h];
    return m;
  }
  function avgPeak(){
    if(typeof avgByHour==='undefined') return 1;
    var m=1; for(var h=0;h<24;h++) if(avgByHour[h]>m) m=avgByHour[h];
    return m;
  }
  hourAxisMax=function(){ return Math.max(1, dayPeak(), avgPeak()); };
  if(typeof selectDay==='function'&&typeof selectedDay!=='undefined'&&selectedDay)
    selectDay(selectedDay);
})();
