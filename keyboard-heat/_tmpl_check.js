
const DATA = __DATA_JSON__;
const META = __META_JSON__;

const DAY_KEYS = Object.keys(DATA).sort();
const dataMinute = (k) => DATA[k] || [];

const fmt = (n) => n.toLocaleString('zh-CN');
const pad2 = (n) => String(n).padStart(2, '0');
const dstr = (d) => d.getFullYear() + '-' + pad2(d.getMonth()+1) + '-' + pad2(d.getDate());
const parseD = (s) => { const p = s.split('-'); return new Date(+p[0], +p[1]-1, +p[2]); };
const hhmm = (m) => pad2(Math.floor(m/60)) + ':' + pad2(m%60);

// 折算系数必须和 heatcore.py 的 w_move / w_click / w_scroll 保持一致 ——
// 报告里的「综合活跃」和悬浮窗中心那个大数字才会是同一个口径。
const W_MOVE = 0.01, W_CLICK = 4, W_SCROLL = 2;
const mouseEquiv = (r) => r[4]*W_MOVE + r[5]*W_CLICK + r[6]*W_SCROLL;

// 一行 7 个字段：0=分钟序号 1=击键 2=退格 3=活跃秒 4=鼠标移动 5=点击 6=滚轮
function dayTotals(k){
  let keys=0, bs=0, act=0, mv=0, ck=0, sc=0, meq=0;
  for(const r of dataMinute(k)){
    keys+=r[1]; bs+=r[2]; act+=r[3];
    mv+=r[4]; ck+=r[5]; sc+=r[6];
    meq += mouseEquiv(r);
  }
  return {keys, bs, act, mv, ck, sc, meq, equiv: keys + meq};
}

let maxDayEquiv = 1;
for(const k of DAY_KEYS) maxDayEquiv = Math.max(maxDayEquiv, dayTotals(k).equiv);
const lvOf = (v) => v <= 0 ? 0 : Math.min(5, 1 + Math.floor(Math.sqrt(v / maxDayEquiv) * 4.999));

let ALL_KEYS=0, ALL_BS=0, ALL_ACT=0, ALL_MV=0, ALL_CK=0, ALL_SC=0, ALL_MEQ=0;
let BEST_DAY=null, BEST_EQUIV=0;
for(const k of DAY_KEYS){
  const t = dayTotals(k);
  ALL_KEYS += t.keys; ALL_BS += t.bs; ALL_ACT += t.act;
  ALL_MV += t.mv; ALL_CK += t.ck; ALL_SC += t.sc; ALL_MEQ += t.meq;
  if(t.equiv > BEST_EQUIV){ BEST_EQUIV = t.equiv; BEST_DAY = k; }
}
const MOUSE_SHARE = (ALL_KEYS + ALL_MEQ) ? (ALL_MEQ / (ALL_KEYS + ALL_MEQ) * 100) : 0;
const ALL_EQUIV = ALL_KEYS + ALL_MEQ;

// 活跃分钟 = 这一分钟里键盘或鼠标任意一路有动作（不只是打字）
const ACTIVE_MIN = DAY_KEYS.reduce((a,k)=>
  a + dataMinute(k).filter(r => r[1]>0 || r[4]>0 || r[5]>0 || r[6]>0).length, 0);

const fmtShort = (n) => n >= 10000 ? (n/10000).toFixed(1) + '万' : fmt(n);

function renderStats(){
  const hours = ALL_ACT / 3600;
  const avgRate = ACTIVE_MIN ? Math.round(ALL_EQUIV / ACTIVE_MIN) : 0;
  const bsRate = (ALL_KEYS + ALL_BS) ? (ALL_BS / (ALL_KEYS + ALL_BS) * 100) : 0;
  const perDay = DAY_KEYS.length ? Math.round(ALL_EQUIV / DAY_KEYS.length) : 0;
  const items = [
    ['总击键数', fmt(ALL_KEYS), ''],
    ['鼠标移动', fmtShort(ALL_MV), '次'],
    ['鼠标点击', fmtShort(ALL_CK), '次'],
    ['鼠标滚轮', fmtShort(ALL_SC), '格'],
    ['活跃时长', hours.toFixed(1), '小时'],
    ['日均活跃', fmtShort(perDay), ''],
    ['活跃时段均速', fmt(avgRate), '活跃/分'],
    ['退格占比', bsRate.toFixed(1), '%'],
    ['鼠标占比', MOUSE_SHARE.toFixed(1), '%'],
    ['最热一天', BEST_DAY ? BEST_DAY.slice(5) : '--', BEST_DAY ? fmtShort(Math.round(BEST_EQUIV)) : ''],
  ];
  document.getElementById('stats').innerHTML = items.map(([k,v,u])=>
    '<div class="stat"><div class="k">'+k+'</div><div class="v">'+v+(u?'<small>'+u+'</small>':'')+'</div></div>'
  ).join('');
}

function renderCalendar(){
  const cal = document.getElementById('cal');
  if(!DAY_KEYS.length){ cal.innerHTML=''; return; }
  const first = parseD(DAY_KEYS[0]);
  const last  = parseD(DAY_KEYS[DAY_KEYS.length-1]);
  const start = new Date(first); start.setDate(start.getDate() - ((start.getDay()+6)%7));
  const end   = new Date(last);  end.setDate(end.getDate() + (6-((end.getDay()+6)%7)));

  const cells=[], months=[];
  let cur = new Date(start), week = 0, lastMonth = -1;
  while(cur <= end){
    const k = dstr(cur);
    const t = DATA[k] ? dayTotals(k) : null;
    const lv = t ? lvOf(t.equiv) : 0;      // 分级看综合活跃，和悬浮窗同口径
    const cls = 'cell' + (k === selectedDay ? ' sel' : '');
    const tip = t ? (' · 键 ' + fmt(t.keys) + ' · 鼠 ' + fmt(t.mv) + ' 次移动') : ' · 无数据';
    cells.push('<div class="'+cls+'" data-lv="'+lv+'" data-d="'+k+'" title="'+k+tip+'"></div>');
    if(cur.getDay() === 0){
      const m = cur.getMonth();
      if(m !== lastMonth){
        months.push({week, label:(m+1)+'月'});
        lastMonth = m;
      }
      week++;
    }
    cur.setDate(cur.getDate()+1);
  }
  cal.innerHTML = cells.join('');
  document.getElementById('cal-months').innerHTML = months.map(m=>
    '<span style="position:relative;left:'+(m.week*16)+'px;position:absolute">'+m.label+'</span>'
  ).join('');
  cal.querySelectorAll('.cell').forEach(el=>{
    el.addEventListener('click', ()=>{
      const d = el.dataset.d;
      if(DATA[d]) selectDay(d);
    });
  });
}

let selectedDay = META.last_day || (DAY_KEYS.length ? DAY_KEYS[DAY_KEYS.length-1] : '');

function selectDay(k){
  selectedDay = k;
  const idx = DAY_KEYS.indexOf(k);
  document.getElementById('day-title').textContent = k + ' 周' + '日一二三四五六'[parseD(k).getDay()];
  const t = dayTotals(k);
  const activeMin = dataMinute(k).filter(r => r[1]>0 || r[4]>0 || r[5]>0 || r[6]>0).length;
  document.getElementById('day-meta').textContent =
    fmt(t.keys) + ' 次击键 · 鼠标 ' + fmt(t.mv) + ' 移动 / ' + fmt(t.ck) + ' 点击 · ' +
    fmt(Math.round(t.equiv)) + ' 综合活跃 · ' + (t.act/3600).toFixed(1) + ' 小时 · ' +
    fmt(activeMin) + ' 个活跃分钟';
  document.getElementById('day-prev').disabled = idx <= 0;
  document.getElementById('day-next').disabled = idx < 0 || idx >= DAY_KEYS.length-1;
  drawTimeline(k);
  drawBars(k);
  document.querySelectorAll('.cell').forEach(el=> el.classList.toggle('sel', el.dataset.d === k));
}

document.getElementById('day-prev').onclick = ()=>{ const i=DAY_KEYS.indexOf(selectedDay); if(i>0) selectDay(DAY_KEYS[i-1]); };
document.getElementById('day-next').onclick = ()=>{ const i=DAY_KEYS.indexOf(selectedDay); if(i>=0 && i<DAY_KEYS.length-1) selectDay(DAY_KEYS[i+1]); };

function cssVar(n){ return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }

function drawTimeline(k){
  const cvs = document.getElementById('tl');
  const wrap = cvs.parentElement;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  cvs.width = Math.max(1, W*dpr); cvs.height = Math.max(1, H*dpr);
  const ctx = cvs.getContext('2d');
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.clearRect(0,0,W,H);

  const padL=46, padR=10, padT=14, padB=26;
  const pw = W-padL-padR, ph = H-padT-padB;

  const series = new Float64Array(1440);    // 每分钟击键数 —— 曲线的 y 轴
  const mseries = new Float64Array(1440);   // 每分钟鼠标移动次数 —— 只进 tooltip，不画线
  for(const r of dataMinute(k)){ series[r[0]] = r[1]; mseries[r[0]] = r[4]; }
  let yMax = 1;
  for(let i=0;i<1440;i++) yMax = Math.max(yMax, series[i]);
  yMax = Math.ceil(yMax*1.15/20)*20 || 20;

  const line = cssVar('--line'), fg3 = cssVar('--fg3');

  ctx.strokeStyle = line; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(padL, padT+ph+.5); ctx.lineTo(padL+pw, padT+ph+.5); ctx.stroke();

  ctx.font = '11px Consolas, monospace'; ctx.fillStyle = fg3;
  ctx.textAlign='right'; ctx.textBaseline='middle';
  for(const v of [0, yMax/2, yMax]){
    const y = padT + ph - (v/yMax)*ph;
    ctx.fillText(String(Math.round(v)), padL-8, y);
    if(v>0){ ctx.strokeStyle = line; ctx.beginPath(); ctx.moveTo(padL, y+.5); ctx.lineTo(padL+pw, y+.5); ctx.stroke(); }
  }
  ctx.textAlign='center'; ctx.textBaseline='top';
  for(let h=0; h<=24; h+=6){
    ctx.fillText(pad2(h)+':00', padL + (h*60/1439)*pw, padT+ph+7);
  }

  const X = (m)=> padL + (m/1439)*pw;
  const Y = (v)=> padT + ph - (v/yMax)*ph;

  ctx.beginPath();
  ctx.moveTo(X(0), Y(series[0]));
  for(let m=1;m<1440;m++) ctx.lineTo(X(m), Y(series[m]));
  const grad = ctx.createLinearGradient(0, padT, 0, padT+ph);
  grad.addColorStop(0, 'rgba(90,167,216,.30)');
  grad.addColorStop(1, 'rgba(90,167,216,.02)');
  ctx.lineTo(X(1439), Y(0)); ctx.lineTo(X(0), Y(0)); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  ctx.beginPath();
  ctx.moveTo(X(0), Y(series[0]));
  for(let m=1;m<1440;m++) ctx.lineTo(X(m), Y(series[m]));
  ctx.strokeStyle = '#3f86c4'; ctx.lineWidth = 1.6; ctx.lineJoin='round'; ctx.stroke();

  cvs._geo = {padL, padT, pw, ph, yMax, series, mseries};
}

function drawBars(k){
  const hourly = new Array(24).fill(0);
  const hourlyAct = new Array(24).fill(0);
  const hourlyMv = new Array(24).fill(0);
  const hourlyMeq = new Array(24).fill(0);
  for(const r of dataMinute(k)){
    const h = Math.floor(r[0]/60);
    hourly[h] += r[1];
    hourlyAct[h] += r[3];
    hourlyMv[h] += r[4];
    hourlyMeq[h] += mouseEquiv(r);
  }
  // 柱高按「综合活跃」而不是纯击键排 —— 一个只动鼠标的小时同样该有高度
  const hourlyEquiv = hourly.map((v,h)=> v + hourlyMeq[h]);
  let mx = 1; for(const v of hourlyEquiv) mx = Math.max(mx, v);
  const bars = document.getElementById('bars');
  bars.innerHTML = hourlyEquiv.map((eq,h)=>{
    if(!eq) return '<div class="bar off" style="height:2%" title="'+pad2(h)+':00 — 无活动"></div>';
    const pct = Math.max(3, eq/mx*100);
    const mPct = Math.min(100, hourlyMeq[h]/eq*100);
    const title = pad2(h)+':00 — 键 '+fmt(hourly[h])+' · 鼠 '+fmt(hourlyMv[h])+' 次移动，'
                + (hourlyAct[h]/60).toFixed(0)+' 分钟活跃';
    return '<div class="bar" style="height:'+pct+'%" title="'+title+'">'
         + '<div class="bar-m" style="height:'+mPct+'%"></div></div>';
  }).join('');
  const bx = document.getElementById('bar-x');
  bx.innerHTML = hourly.map((_,h)=> '<div'+(h%3?' class="hide"':'')+'>'+(h%3===0?pad2(h):'')+'</div>').join('');
}

const tip = document.getElementById('tl-tip');
document.getElementById('tl').addEventListener('mousemove', (e)=>{
  const cvs = e.currentTarget, g = cvs._geo;
  if(!g) return;
  const rect = cvs.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  if(mx < g.padL || mx > g.padL+g.pw){ tip.style.opacity = 0; return; }
  const m = Math.round((mx-g.padL)/g.pw*1439);
  tip.textContent = hhmm(m) + '  键 ' + g.series[m] + ' · 鼠 ' + g.mseries[m];
  tip.style.opacity = 1;
  tip.style.left = Math.min(rect.width-110, Math.max(0, mx+12)) + 'px';
  tip.style.top = Math.max(0, e.clientY - rect.top - 34) + 'px';
});
document.getElementById('tl').addEventListener('mouseleave', ()=>{ tip.style.opacity = 0; });

document.getElementById('btn-copy').onclick = ()=>{
  const hours = (ALL_ACT/3600).toFixed(1);
  const avgRate = ACTIVE_MIN ? Math.round(ALL_EQUIV/ACTIVE_MIN) : 0;
  const txt = [
    '键盘热度报告 ' + META.range,
    '总击键数：' + fmt(ALL_KEYS),
    '鼠标活动：' + fmt(ALL_MV) + ' 次移动 / ' + fmt(ALL_CK) + ' 次点击 / ' + fmt(ALL_SC) + ' 格滚轮',
    '鼠标占比：' + MOUSE_SHARE.toFixed(1) + '%（按折算后的等效活跃计）',
    '活跃时长：' + hours + ' 小时',
    '日均活跃：' + fmt(DAY_KEYS.length ? Math.round(ALL_EQUIV/DAY_KEYS.length) : 0),
    '活跃时段均速：' + fmt(avgRate) + ' 活跃/分',
    '退格占比：' + ((ALL_KEYS+ALL_BS)?(ALL_BS/(ALL_KEYS+ALL_BS)*100).toFixed(1):'0') + '%',
    '最热一天：' + (BEST_DAY || '--') + '（综合活跃 ' + fmt(Math.round(BEST_EQUIV)) + '）',
  ].join('\n');
  navigator.clipboard.writeText(txt).then(()=>{
    const b = document.getElementById('btn-copy');
    b.textContent = '已复制'; setTimeout(()=> b.textContent = '复制摘要', 1400);
  });
};

document.getElementById('btn-csv').onclick = ()=>{
  const rows = ['date,minute,keystrokes,backspaces,active_seconds,mouse_moves,clicks,scrolls'];
  for(const k of DAY_KEYS){
    for(const r of dataMinute(k)) rows.push(k + ',' + hhmm(r[0]) + ',' + r.slice(1).join(','));
  }
  const blob = new Blob(['\ufeff' + rows.join('\n')], {type:'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'keyboard-heat-' + dstr(new Date()) + '.csv';
  a.click();
  URL.revokeObjectURL(a.href);
};

const btnTheme = document.getElementById('btn-theme');
btnTheme.onclick = ()=>{
  const dark = document.documentElement.dataset.theme === 'dark';
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  btnTheme.textContent = dark ? '切换深色' : '切换浅色';
  if(selectedDay) selectDay(selectedDay);
};
if(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches){
  document.documentElement.dataset.theme = 'dark';
  btnTheme.textContent = '切换浅色';
}

let rt;
window.addEventListener('resize', ()=>{ clearTimeout(rt); rt = setTimeout(()=>{ if(selectedDay) selectDay(selectedDay); }, 120); });

document.getElementById('hdr-range').textContent = META.range ? (META.range + ' · ' + DAY_KEYS.length + ' 天') : '暂无数据';

if(!DAY_KEYS.length){
  document.querySelectorAll('.panel').forEach(p=> p.innerHTML = '<div class="empty">还没有采集到数据。先运行程序打打字、动动鼠标，再点托盘图标重新生成报告。</div>');
  document.getElementById('stats').innerHTML = '';
} else {
  renderStats();
  renderCalendar();
  selectDay(selectedDay);
}
