/* 「更早形态」夹具：把两块又折回**同一张卡**、并退回 tab 互斥切换。
   用途：`_ui_geom_probe.py --tabs`（反向验证：卡片化判据必须点名它）、
        `_shot_tiles.mjs --pre _pre_tabsback.js`（截图对照）。
   **唯一实现**：Python 探针读它**内容**注入，node 截图脚本按**文件名**注入。
   于是渲「改前」不必回退源文件 —— 本项目一贯做法：对照图靠"临时替换驱动渲染的东西"。

   卡片化之后，旧形态要还原三件事才**可信**（否则「改前」帧里会出现当年根本没有的东西）：
     ① 去掉卡片标题行 .row —— 那是这一次才加的；
     ② 把「当天」那三块搬回第一张卡内、再删掉第二张卡 —— 旧形态是一张卡里互斥；
     ③ 插回 tab 栏、把「当天」块藏起来。 */
(function () {
  var cal = document.querySelector('#year-cal');
  var card1 = cal ? cal.closest('.panel') : null;   /* 卡1：全年活动热力 */
  var card2 = document.getElementById('day-card');  /* 卡2：当天逐小时分布 */
  if (!card1 || !card2 || card1 === card2) return;

  /* ① 卡片标题行 .row 是本次新增的，旧形态没有 */
  [card1, card2].forEach(function (c) {
    var r = c.querySelector(':scope > .row');
    if (r) r.remove();
  });

  /* ② 把「当天」块搬回第一张卡末尾，然后删掉空卡片 */
  var moved = [];
  ['.day-nav', '#bars', '#bar-x'].forEach(function (s) {
    var e = card2.querySelector(s);
    if (e) { card1.appendChild(e); moved.push(e); }
  });
  card2.remove();

  /* ③ tab 栏 + 藏起「当天」块 */
  var bar = document.createElement('div');
  bar.className = 'view-tabs';
  [['cal', '日历'], ['heat', '周×小时'], ['day', '当天']].forEach(function (p) {
    var b = document.createElement('button');
    b.className = 'tab' + (p[0] === 'cal' ? ' active' : '');
    b.dataset.view = p[0];
    b.textContent = p[1];
    bar.appendChild(b);
  });
  card1.insertBefore(bar, card1.firstChild);
  moved.forEach(function (e) { e.style.display = 'none'; });

  /* 副标题也要回到旧文案 —— 否则「改前」帧里写着"下方看当天"，与画面（只剩日历）自相矛盾，
     对照图就不可比了。 */
  var h2 = card1.closest('section').querySelector('h2');
  var sub = h2 ? h2.querySelector('span') : null;
  if (sub) sub.textContent =
    '同一位置切换：日历看全年密度、周×小时热力图看逐小时活跃、当天看逐小时分布；点有数据的日期查看当天';

  var st = document.createElement('style');
  st.textContent = [
    '.view-tabs{display:inline-flex;gap:4px;background:var(--card-2);border:1px solid var(--line);',
    '  border-radius:999px;padding:4px;margin-bottom:14px}',
    '.view-tabs .tab{border:0;background:transparent;font:inherit;font-size:13px;font-weight:600;',
    '  color:var(--fg2);padding:6px 18px;border-radius:999px;cursor:pointer;transition:.15s;white-space:nowrap}',
    '.view-tabs .tab.active{background:var(--accent);color:#fff;box-shadow:var(--shadow-sm)}'
  ].join('\n');
  document.head.appendChild(st);
})();
