/* 「本次改前」夹具：逐小时分布**只有当天一根柱**（没有历史平均参考柱）。
   用途两处，共用这一份实现：
     · `_ui_geom_probe.py --noavg` —— 反向验证：判据必须点名它（平均柱 0 根）；
     · `_shot_tiles.mjs --pre _pre_noavg.js` —— 渲对照图的「改前」帧。
   （Python 探针读它**内容**注入，node 截图脚本按**文件名**注入。）

   还原要点 —— 三件事缺一件就不是"改前"：
     ① 拆掉 .bh 双柱容器：改前 .bars 的直接子级就是 .bar（否则 grid 列数会错）；
     ② 删掉参考柱 .bar-avg；
     ③ 刻度退回「只看当天峰值」。⚠ 这条最容易漏：改后的刻度是 max(当天, 平均)，
        不退回的话当天柱会无端变矮，"改前/改后"比的就不是同一件事了。
   另外把当时不存在的东西也去掉：图例（本次才加）与卡片注释的新文案。 */
(function () {
  var bars = document.getElementById('bars');
  if (!bars) return;

  /* ⚠ 先关掉过渡 —— `.bar{transition:.15s}` 会让"改完 height 立刻量/截"读到**过渡起点**：
     实测 style 已经写成 39.3%，`getBoundingClientRect()` 仍是 170px（100% 的位置），
     于是几何探针与对照图全部失真（表现为"夹具没生效"的假象）。
     改高度做反向验证/对照图时，这一条必须先做。 */
  var st = document.createElement('style');
  st.textContent = '.bars .bar{transition:none !important}';
  document.head.appendChild(st);
  void document.body.offsetHeight;            /* 强制一次 reflow，让 transition 规则立刻生效 */

  /* ① 拆容器：把两根柱提升到 .bars 直接子级 */
  [].slice.call(bars.querySelectorAll('.bh')).forEach(function (bh) {
    while (bh.firstChild) bh.parentNode.insertBefore(bh.firstChild, bh);
    bh.parentNode.removeChild(bh);
  });

  /* ② 删参考柱 */
  [].slice.call(bars.querySelectorAll('.bar-avg')).forEach(function (el) { el.remove(); });

  /* ③ 刻度退回当天峰值 */
  var day = [].slice.call(bars.querySelectorAll('.bar')), mx = 1;
  day.forEach(function (b) { var v = +b.getAttribute('data-v') || 0; if (v > mx) mx = v; });
  day.forEach(function (b) {
    var v = +b.getAttribute('data-v') || 0;
    b.style.height = (v > 0 ? Math.max(3, v / mx * 100) : 2).toFixed(1) + '%';
  });

  /* ④ 图例是本次才加的 */
  var lg = document.querySelector('#day-card .legend');
  if (lg) lg.parentNode.removeChild(lg);

  /* ⑤ 卡片注释用旧文案 */
  var meta = document.querySelector('#day-card .row .meta');
  if (meta) meta.textContent = '按小时统计键盘按键与鼠标活动折算后的综合活跃';
})();
