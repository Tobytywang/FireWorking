/* 「本次改前」夹具：把已经拆开的**两张卡**又折回**同一张卡**，两块之间用一条细线分隔
   （= 上一版"平铺在同一卡片里"的形态）。用途：
     · `_shot_tiles.mjs --pre _pre_merged.js` —— 渲对照图的「改前」帧；
     · `_ui_geom_probe.py --merged` —— 反向验证：卡片化判据必须点名它（卡数 1）。
   **唯一实现**：Python 探针读它**内容**注入，node 截图脚本按**文件名**注入。
   与 `_pre_tabsback.js`（更早的 tab 互斥形态）分工不同：那个连 tab 栏一起回来。

   还原要点（不然「改前」帧里会出现当时没有的东西）：
     ① 去掉卡片标题行 .row —— 那是这一次才加的；
     ② 卡1 的内容重新包回 .view-pane[data-pane=cal]，卡2 的三块包回 .view-pane[data-pane=day]；
     ③ 补回那条 `.view-pane + .view-pane` 分隔线；删掉卡2。 */
(function () {
  var cal = document.querySelector('#year-cal');
  var card1 = cal ? cal.closest('.panel') : null;   /* 卡1：全年活动热力 */
  var card2 = document.getElementById('day-card');  /* 卡2：当天逐小时分布 */
  if (!card1 || !card2 || card1 === card2) return;

  /* ① 卡片标题行是本次新增的 */
  [card1, card2].forEach(function (c) {
    var r = c.querySelector(':scope > .row');
    if (r) r.remove();
  });

  /* ② 卡1 的内容包回 pane */
  var paneCal = document.createElement('div');
  paneCal.className = 'view-pane';
  paneCal.dataset.pane = 'cal';
  ['.cal-scroll', '.legend'].forEach(function (s) {
    var e = card1.querySelector(':scope > ' + s);
    if (e) paneCal.appendChild(e);
  });
  card1.appendChild(paneCal);          /* 先移出卡1，再按序放回首位下方 */

  var paneDay = document.createElement('div');
  paneDay.className = 'view-pane';
  paneDay.dataset.pane = 'day';
  ['.day-nav', '#bars', '#bar-x'].forEach(function (s) {
    var e = card2.querySelector(s);
    if (e) paneDay.appendChild(e);
  });
  card1.appendChild(paneDay);
  card2.remove();

  /* ③ 分隔线 + 旧副标题 */
  var st = document.createElement('style');
  st.textContent =
    '.view-pane + .view-pane{margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}';
  document.head.appendChild(st);

  var h2 = card1.closest('section').querySelector('h2');
  var sub = h2 ? h2.querySelector('span') : null;
  if (sub) sub.textContent = '上方日历看全年密度；点有数据的日期，下方看当天逐小时分布';
})();
