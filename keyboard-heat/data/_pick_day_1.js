/* 截图 / 对照用：把「当天逐小时分布」切到 2026-10-08 —— heat.db 里活跃小时最多的一天（14 个），
   线的高度层次最丰富，比默认的"最近一天"更能看出造型。

   ⚠ 这个文件由 _shot_tiles.mjs 的 --pre 注入到 </body> 之后执行，那时模板脚本已经跑完，
      selectDay 是全局函数（模板里是 function 声明 + let selectedDay，同一全局作用域可见）。 */
(function () {
  if (typeof selectDay === 'function') selectDay('2026-10-08');
})();
