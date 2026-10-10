/* 反向验证（`--selfscale`）：只推翻「两根柱共用同一条刻度」这一条判据。
   柱数、图例、配色都不动，只把**参考柱的比例**打乱，`hourRef.rel` 必须报红；
   若它还全绿，说明这条判据是死的（永远为真）。

   ⚠ 这里绕了两个弯，都是实测撞出来的，别再往回改：
     ① 一开始让**参考柱按自己的峰值归一化**，`rel` 纹丝不动 —— 当前数据"平均峰值 >
        当天峰值"，共用刻度取的本来就是平均峰值，那一改与现行实现**逐像素等价**。
     ② 换成让**当天柱按自己的峰值归一化**（= 各用各的 max），还是不动 —— 因为两个
        峰值本来就接近，此时"共用刻度"与"各自刻度"**数学上不可分辨**（图完全一样）。
        这既是夹具的无效，也是这条判据的能力边界：两个峰值差异不大时它抓不到东西，
        而那时也确实没有视觉后果。
   所以反向验证改为**人为放大比例不一致**（参考柱高度减半）—— 它验的是"判据机制能不能
   发现两根柱不成比例"，而不是"某种真实错误长什么样"。真正的结构退化由 `--noavg` 点名
   （参考柱整组消失），两条互补。 */
(function () {
  var bars = document.getElementById('bars');
  if (!bars) return;
  /* ⚠ 先关掉过渡：`.bar{transition:.15s}` 会让"改完 height 立刻量"读到**过渡起点**
     —— 实测 style 已是 50%，`getBoundingClientRect()` 仍报 170px，判据看起来"没反应"。
     这一步不做，整条反向验证就是空转。 */
  var st = document.createElement('style');
  st.textContent = '.bars .bar{transition:none !important}';
  document.head.appendChild(st);
  [].slice.call(bars.querySelectorAll('.bar-avg')).forEach(function (b) {
    var h = parseFloat(b.style.height) || 0;
    b.style.height = (h / 2).toFixed(2) + '%';
  });
})();
