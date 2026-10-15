/* 复现 v3.11 及以前的形态（"改前"）：每格**两根并排柱** —— 左 = 当天（实色柱，底部叠鼠标段）、
   右 = 全周期同时段平均（同色相 28% 透明）。

   一份文件三件事 —— 这三件合起来才等于"改前"，少一件对照图就在骗人：
     ① 布局：把「同轴叠加」改回「并排双柱」；
     ② 文案：卡片右上角说明行改前是"浅色=全周期同时段平均（刻度固定）"，
             不还原的话，改前帧的图注说的是改后的事；
     ③ 日期：切到 2026-10-08（heat.db 里活跃小时最多的一天，14 个），
             两帧必须同一天才可比。

   ⚠ 必须用 order 把左右摆回来：DOM 顺序是 [平均柱, 当天线]，而改前是 [当天柱, 平均柱]，
     不写 order 渲出来是"左平均、右当天"，那不是改前形态。
   ⚠ .dline 要显式 position:relative 并清掉 left/transform：它是 .bar-m（鼠标段）的包含块，
     一旦落回 static，鼠标段会跑到 .bh 上，柱底那段颜色会错位。
   ⚠ *{transition:none} —— 注入会把 .dline 的 width 从 3px 变成 ~18px，150ms 的过渡会让
     紧接着读到的 rect 落在动画中间值上。

   用途：① 对照图的"改前"帧（_shot_tiles.mjs --pre）；
        ② 探针的反向验证用例（_dline_probe_1.py --pre，D1 同轴必须报红）。 */
(function () {
  var CSS = [
    '.bh{display:flex;align-items:flex-end;gap:2px;position:static}',
    '.bh>.bar{position:static;flex:1 1 0;min-width:0;order:2}',
    '.bh>.dline{position:relative;left:auto;bottom:auto;transform:none;flex:1 1 0;order:1;',
    '  width:auto;background:var(--accent-2);border-radius:5px 5px 3px 3px;overflow:hidden}',
    '.bh>.dline>.dl-tip{display:none}',
    '.bh>.dline::before{display:none}',
    '*{transition:none!important}'
  ].join('\n');
  /* ⚠ selectDay 必须先于 CSS 注入执行：实测若先把 .bh 改成 display:flex 再调 selectDay，
     调用会被吞掉（帧停在默认日，活跃小时变成 [1,2,3] 这种稀疏日），对照图就失真了。
     先切日、再改布局，渲染才会落在 2026-10-08 上。 */
  if (typeof selectDay === 'function') selectDay('2026-10-08');

  var s = document.createElement('style');
  s.textContent = CSS;
  document.head.appendChild(s);

  /* 补一根 2% 的灰柱给"当天无活动"的格子。
     ⚠ 必须放在 selectDay **之后**：selectDay 会重建整个 #bars，先补的节点会被冲掉。
     ⚠ 不补的话那些格子里只剩平均柱一根 flex item，`flex:1 1 0` 会让它撑满整格 ——
       那不是改前形态（改前是「左 2% 灰柱 + 右 平均柱」各占一半），而且会把像素扫描的
       格内中心算错（实测轴心偏差从 19.6px 缩到 10px，对照图上的数字就假了）。
     插到 avg 之前、两者 order 都是 2（同 order 按 DOM 顺序）⇒ 灰柱在左、平均柱在右，与改前一致。 */
  [].forEach.call(document.querySelectorAll('#bars .bh'), function (bh) {
    if (bh.querySelector('.dline')) return;
    var g = document.createElement('div');
    g.className = 'bar off';
    g.style.height = '2%';
    bh.insertBefore(g, bh.firstChild);
  });
})();
