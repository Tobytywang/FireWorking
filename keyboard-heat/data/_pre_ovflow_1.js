/* O7 反向验证夹具（新窄砖契约版）：把时间行每块 `.sub` 小字换成**超长句**。

   动机：v3.15 起时间行从 4/12 宽砖（343px + 右列 `.wside`）改成与键盘/鼠标同宽的
   2/12 窄砖（≈165px），次要信息也从右列 `.wside` 精简成**数值下方一行 `.sub` 小字**。
   `.sub` 是 `white-space:nowrap` + `text-overflow:ellipsis` —— 一旦有人往里塞长句
   （例如把「标准活跃 / 标准工作时长」这种带分母的全称写回去），超出的部分会被
   **静默截成「…」**：DOM 里 textContent 完整、探针查标签查得到、截图上只多一个
   省略号，肉眼很容易放过。只有量几何（Range 墨迹 vs 砖边）才看得见。

   本夹具正是这种「长句形态」：给 `.sub` 塞一条远超 133px 的句子 →
   期望 O7 报红（文字越出砖边），以此证明 O7 对小字这一路**不是恒真空判据**。

   ⚠ 注入后必须让 .sub 的 ellipsis 失效（overflow:visible + clip 解除），
   否则浏览器会替我们把长句截成一行、墨迹仍在砖内 → 夹具失效、假绿。 */
(function () {
  var s = document.createElement('style');
  /* 解除 ellipsis/裁剪：让超长句真实溢出到砖外，O7 的墨迹检测才抓得到 */
  s.textContent =
    '.tiles .tile .sub{overflow:visible;text-overflow:clip;white-space:nowrap}';
  var long = '实际活跃时长（= 全时段活跃秒累计，与首块同源，不另计）· 日均 5.8 小时';
  document.head.appendChild(s);
  var subs = document.querySelectorAll('#stats .tile .sub');
  for (var i = 0; i < subs.length; i++) {
    subs[i].textContent = long;
  }
})();