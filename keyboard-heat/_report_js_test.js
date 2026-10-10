/**
 * 报告模板前端逻辑实测（v2 暖橙版）。
 *
 * 只做 HTML/JS 静态校验是不够的 —— 数据格式从 4 列变 7 列时，肉眼过一遍模板
 * 很容易漏掉某个 r[3]/r[4] 的索引。这里把生成的报告 HTML 里的 <script> 抠出来，
 * 套一层最小 DOM stub 在 node 里真跑一遍，然后断言算出来的数字。
 *
 * ⚠ v2 的渲染大量走 querySelectorAll + innerHTML，DOM 无法也不需要在 node 里复刻。
 * 所以 stub 用「黑洞元素」：任何 getElementById / querySelector(All) 都返回可写的
 * 假元素（写 textContent/style/innerHTML 都不炸），只把**根元素的 innerHTML 字符串**
 * 留下来供断言 —— 于是真正守住的仍是两件事：
 *   ① 聚合口径（折算系数 / 活跃分钟 / 逐小时刻度）；
 *   ② 渲染确实产出了结构（砖块数、标签、柱图、倒计时横条）。
 *
 * 用法：node _report_js_test.js <report.html>
 *       node _report_js_test.js --smoke <report.html>   只验证"跑得通 + 渲染出来了"
 *
 * --smoke 用在真实数据生成的报告上：那时提前手算不出期望值，能跑通、卡片齐全、
 * 数值落在合理区间就够了。
 */
const fs = require('fs');
const vm = require('vm');

const args = process.argv.slice(2);
const smoke = args[0] === '--smoke';
const htmlPath = smoke ? args[1] : args[0];
const html = fs.readFileSync(htmlPath, 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('找不到 <script> 块'); process.exit(1); }
const code = m[1];

// ---- 最小 DOM stub：黑洞元素，任何查询都返回"吸收一切"的假元素 ----
const ctxStub = new Proxy({}, {
  get(t, k) {
    if (k === 'createLinearGradient') return () => ({ addColorStop() {} });
    if (k === 'measureText') return () => ({ width: 10 });
    if (k in t) return t[k];
    return () => {};
  },
  set(t, k, v) { t[k] = v; return true; },
});

function blackHole(id) {
  const styleProxy = new Proxy({}, { get: () => () => {}, set: () => true });
  const el = {
    id, innerHTML: '', textContent: '', value: '', disabled: false, onclick: null,
    style: styleProxy, dataset: {}, children: [],
    clientWidth: 900, clientHeight: 230, scrollWidth: 0, offsetWidth: 100,
    addEventListener() {}, removeEventListener() {},
    classList: { toggle() {}, add() {}, remove() {} },
    querySelector() { return blackHole('qs'); },
    querySelectorAll() { return blackHoleList(); },
    getBoundingClientRect() { return { left: 0, top: 0, width: 900, height: 230 }; },
    getContext() { return ctxStub; },
  };
  el.parentElement = el;   // 自指：fitCalendar 里 scroll.parentElement.style.setProperty(...) 不炸
  return el;
}
function blackHoleList() {
  // 数字索引 → 新假元素；length=0 → [].slice.call 得到空数组；其余方法调用 → 空操作
  return new Proxy({ length: 0 }, {
    get(t, k) {
      if (k === 'length') return 0;
      if (typeof k === 'string' && /^\d+$/.test(k)) return blackHole('item' + k);
      if (k in t) return t[k];
      return () => {};
    },
  });
}

const els = {};
const document = {
  documentElement: { dataset: {}, style: {} },
  getElementById(id) { return els[id] || (els[id] = blackHole(id)); },
  querySelectorAll() { return blackHoleList(); },
  querySelector() { return blackHole('qs'); },
  createElement(tag) { return blackHole('<' + tag + '>'); },
};

const sandbox = {
  document,
  console,
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
  getComputedStyle: () => ({ getPropertyValue: () => '#666666' }),
  requestAnimationFrame: () => 0,
  performance: { now: () => 0 },
  setTimeout, clearTimeout,
  Blob: class { constructor() {} },
  URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.window.matchMedia = () => ({ matches: false });
sandbox.window.addEventListener = () => {};

// 探针：把顶层 const 暴露出来做数值断言（v2 用 hueColor / HOUR_AXIS，已无 v1 的 lvOf）
const probe = code + `
;globalThis.__probe = { DATA, META, COUNTDOWN, ALL_KEYS, ALL_MV, ALL_CK, ALL_SC, ALL_MEQ,
  ALL_EQUIV, MOUSE_SHARE, ACTIVE_MIN, DAYS: DAY_KEYS.length, dayTotals, mouseEquiv,
  BEST_DAY, BEST_EQUIV, HOUR_AXIS, hourAxisMax, avgByHour };
`;

let ok = 0, bad = 0;
function check(name, got, want) {
  const same = JSON.stringify(got) === JSON.stringify(want);
  if (same) { ok++; console.log('  [PASS] ' + pad(name, 40) + ' ' + JSON.stringify(got)); }
  else { bad++; console.log('  [FAIL] ' + pad(name, 40) + ' got=' + JSON.stringify(got) + ' want=' + JSON.stringify(want)); }
}
const pad = (s, n) => s + ' '.repeat(Math.max(0, n - s.length));
const near = (a, b, tol) => Math.abs(a - b) <= tol;

try {
  vm.runInNewContext(probe, sandbox, { filename: 'report_template.js' });
} catch (e) {
  console.error('脚本执行抛异常：', e && e.stack || e);
  process.exit(1);
}

const P = sandbox.__probe;
console.log('== 前端脚本能跑通 ==');
check('顶层聚合量已算出', typeof P.ALL_KEYS === 'number' && P.DAYS > 0, true);

if (!smoke) {
console.log('\n== 折算口径 ==');
// 一天前那组：每分 900 移动 + 6 点击 + 4 滚轮，共 120 分钟
const mouseOnly = { moves: 900 * 120, clicks: 6 * 120, scrolls: 4 * 120 };
// 今天那组：每分 80 键 + 400 移动 + 3 点击 + 1 滚轮，共 60 分钟
const mixed = { keys: 80 * 60, moves: 400 * 60, clicks: 3 * 60, scrolls: 60 };
const eqOf = (g) => g.moves * 0.01 + g.clicks * 4 + g.scrolls * 2;

const wantKeys = 120 * 180 + mixed.keys;
const wantMv = mouseOnly.moves + mixed.moves;
const wantMeq = eqOf(mouseOnly) + eqOf(mixed);

check('ALL_KEYS', P.ALL_KEYS, wantKeys);
check('ALL_MV', P.ALL_MV, wantMv);
check('ALL_CK', P.ALL_CK, mouseOnly.clicks + mixed.clicks);
check('ALL_SC', P.ALL_SC, mouseOnly.scrolls + mixed.scrolls);
check('ALL_MEQ 折算正确', near(P.ALL_MEQ, wantMeq, 1e-6), true);
check('ALL_EQUIV = 键 + 鼠折算', P.ALL_EQUIV, wantKeys + wantMeq);

console.log('\n== 鼠标占比 ==');
const wantShare = wantMeq / (wantKeys + wantMeq) * 100;
check('MOUSE_SHARE 与手算一致', near(P.MOUSE_SHARE, wantShare, 1e-9), true);
check('占比落在 0~100', P.MOUSE_SHARE > 0 && P.MOUSE_SHARE < 100, true);

console.log('\n== 活跃分钟口径 ==');
// 180（纯打字）+ 120（纯鼠标）+ 60（混合）= 360，纯鼠标那 120 分钟只有鼠标也该算
check('ACTIVE_MIN 含"只动鼠标"的分钟', P.ACTIVE_MIN, 360);

console.log('\n== 逐日折算 ==');
const days = Object.keys(P.DATA).sort();
const t0 = P.dayTotals(days[0]);
const t1 = P.dayTotals(days[1]);
check('纯打字日 鼠标等效 = 0', t0.meq, 0);
check('纯打字日 综合 = 击键', t0.equiv, t0.keys);
check('纯鼠标日 击键 = 0', t1.keys, 0);
check('纯鼠标日 综合 = 鼠标折算', near(t1.equiv, t1.meq, 1e-9), true);
} else {
console.log('\n== 数值落在合理区间（smoke） ==');
check('ALL_KEYS >= 0', P.ALL_KEYS >= 0, true);
check('ALL_MV >= 0', P.ALL_MV >= 0, true);
check('鼠标占比在 0~100', P.MOUSE_SHARE >= 0 && P.MOUSE_SHARE <= 100, true);
check('活跃分钟 > 0', P.ACTIVE_MIN > 0, true);
check('ALL_EQUIV = 键 + 鼠折算', near(P.ALL_EQUIV, P.ALL_KEYS + P.ALL_MEQ, 1e-6), true);
check('鼠标占比不是 0（演示数据里确实有鼠标活动）', P.MOUSE_SHARE > 0, true);
console.log('  （ALL_KEYS=%d / ALL_MV=%d / 鼠标占比=%s%% / 活跃分钟=%d）',
            P.ALL_KEYS, P.ALL_MV, P.MOUSE_SHARE.toFixed(1), P.ACTIVE_MIN);
}

console.log('\n== 逐小时刻度（v3.11：全周期常量，与选中日期无关）==');
check('HOUR_AXIS ≥ 平均序列峰值', P.HOUR_AXIS >= Math.max(...P.avgByHour), true);
check('hourAxisMax 恒返回同一常量', P.hourAxisMax(), P.HOUR_AXIS);

console.log('\n== 渲染产物（v2：砖块 / 逐小时双柱 / 倒计时横条）==');
const statsHtml = els['stats'] ? els['stats'].innerHTML : '';
const cardCount = (statsHtml.match(/class="tile/g) || []).length;
check('总览砖块数（1 主砖 + 9 砖）', cardCount, 10);
for (const label of ['鼠标移动', '鼠标点击', '鼠标滚轮', '活跃时段均速', '退格占比']) {
  check('含砖块「' + label + '」', statsHtml.includes(label), true);
}
const dayMeta = els['day-meta'] ? els['day-meta'].innerHTML : '';
check('日摘要含鼠标与综合活跃', dayMeta.includes('鼠标') && dayMeta.includes('综合活跃'), true);
check('逐小时柱已渲染', (els['bars'] ? els['bars'].innerHTML.length : 0) > 0, true);
check('柱内有鼠标段', (els['bars'] ? els['bars'].innerHTML.includes('bar-m') : false), true);
check('柱内含历史平均参考柱', (els['bars'] ? els['bars'].innerHTML.includes('bar-avg') : false), true);
check('倒计时按类型横条已渲染', (els['cd-types'] ? els['cd-types'].innerHTML.includes('cd-type') : false), true);

console.log('\n结果：' + (bad ? '有失败' : '全部通过') + '（' + ok + ' 通过 / ' + bad + ' 失败）');
console.log('样例 stats：' + statsHtml.replace(/<[^>]+>/g, ' | ').slice(0, 200));
console.log('样例 day-meta：' + dayMeta.replace(/<[^>]+>/g, ' | '));
process.exit(bad ? 1 : 0);
