#!/usr/bin/env node
/*
 * 可交互暗示探针（真实指针版）
 * ------------------------------------------------------------------
 * 背景：热力图/日历里的格子分三种 —— 有内容（可点 / 有 tooltip）、有日期但无数据、
 * 纯占位（blank，不属于该月的日期）。三者长得像，但只有第一种真的可交互。
 * 若 `:hover` 规则对三者一视同仁，用户就会看到「一个不存在的日期被框住」，
 * 以为可以选中 —— 这属于**可交互暗示与真实可交互不一致**的缺陷。
 *
 * 判据（硬指标，不靠目视）：
 *   1) 把真实指针移到格子上，读该格 computed outlineStyle / transform / cursor：
 *      非 hover 态 vs hover 态。`none -> solid` 即「出现了橙框」。
 *      ⚠ 不要用 outlineWidth 判断：outline-style 为 none 时 Chrome 仍返回默认
 *        medium = 3px，看着像「有边框」，会假阳性/假阴性。
 *   2) 静态扫描：所有含 `:hover` 的 CSS 规则 × 它们实际命中的**可见**元素，
 *      按「是否真的可点 / 是否有内容」分类统计 —— 全量点名，不漏。
 *
 * 用法：
 *   node _hover_cdp.mjs                                       # 量现状 + 截 hover 图
 *   node _hover_cdp.mjs --css ".ycell:hover{outline:none}"     # 量实验 CSS（对照用）
 *   node _hover_cdp.mjs --no-shot                              # 只出数字
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const argv = process.argv.slice(2);
const get = (n, d) => { const i = argv.indexOf('--' + n); return i >= 0 ? argv[i + 1] : d; };
const has = n => argv.includes('--' + n);

const CHROME = get('chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
const HTML = path.resolve(get('html', 'heat-report-prototype.html'));
const PORT = +get('port', 9333);
const W = +get('width', 1200);
const H = +get('height', 900);
const CSS = get('css', '');
const PREFIX = get('prefix', '_hover_');
const SHOT = !has('no-shot');
const sleep = ms => new Promise(r => setTimeout(r, ms));

const udir = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-hover-'));
const fileUrl = 'file:///' + HTML.replace(/\\/g, '/');

const child = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=' + PORT, '--user-data-dir=' + udir,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars',
  '--force-device-scale-factor=1', `--window-size=${W},${H}`, fileUrl,
], { stdio: 'ignore' });

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.id = 0; this.pend = new Map();
    this.ready = new Promise((res, rej) => {
      this.ws.onopen = () => res();
      this.ws.onerror = () => rej(new Error('ws error'));
    });
    this.ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pend.has(m.id)) {
        const p = this.pend.get(m.id); this.pend.delete(m.id);
        m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
      }
    };
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((res, rej) => { this.pend.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); });
  }
  close() { try { this.ws.close(); } catch { } }
}

async function findPage() {
  for (let i = 0; i < 80; i++) {
    try {
      const j = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const p = j.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (p) return p;
    } catch { }
    await sleep(250);
  }
  throw new Error('chrome 未就绪');
}

/* 页面内联 helper：只挑「可见」的匹配元素（被 fitCalendar 隐藏的月块 rect 全 0，会骗人） */
const HELPER = `
function firstVisible(sel){
  var els=[].slice.call(document.querySelectorAll(sel));
  for(var i=0;i<els.length;i++){
    var r=els[i].getBoundingClientRect();
    if(r.width>0 && r.height>0) return els[i];
  }
  return null;
}`;

/* 每个待测目标：选择器 + 人话标签 + 「应该出现 hover 反馈吗」+ 「光标语义」
   cursor 规则：真能点 -> pointer；只能看 tooltip -> help；都没有 -> default */
const CASES = [
  ['日历-纯占位', '#year-cal .ycell.blank', false, 'default'],
  ['日历-有日期无数据', '#year-cal .ycell[data-v="0"]', false, 'default'],
  ['日历-有数据', '#year-cal .ycell[data-k]', true, 'pointer'],
  ['倒计时-有日期无数据', '#cd-cal .ycell[data-v="0"]', false, 'default'],
  ['倒计时-有数据', '#cd-cal .ycell[data-tip]', true, 'help'],
];

async function main() {
  const target = await findPage();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');

  const evalJs = async (expr) => {
    const r = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' | ' + (r.exceptionDetails.exception?.description || ''));
    return r.result.value;
  };

  for (let i = 0; i < 60; i++) {
    const ok = await evalJs(`(function(){return document.readyState==='complete' && !!window.DATA && !!document.querySelector('#year-cal .ycell');})()`);
    if (ok) break;
    await sleep(200);
  }
  if (CSS) {
    await evalJs(`(function(){var s=document.createElement('style');s.textContent=${JSON.stringify(CSS)};document.head.appendChild(s);return 1;})()`);
    await sleep(150);
  }

  /* ---------- 1) 静态全量扫描 ---------- */
  const scan = await evalJs(`(function(){${HELPER}
    function vis(el){var r=el.getBoundingClientRect();return r.width>0&&r.height>0;}
    function hasContent(el){ return !!(el.dataset.tip || el.getAttribute('title')); }
    function classify(el){
      var host = el.closest('#year-cal') ? '日历' : (el.closest('#cd-cal') ? '倒计时' : '');
      if(el.classList.contains('ycell'))
        return host+'.'+(el.classList.contains('blank') ? 'blank占位' : (hasContent(el) ? '有数据' : '有日期无数据'));
      if(el.classList.contains('bar'))
        return '柱.'+(el.classList.contains('off') ? '无活动' : '有活动');
      if(el.id) return '#'+el.id;
      return null;
    }
    var rows=[], tally={};
    for(var i=0;i<document.styleSheets.length;i++){
      var sh=document.styleSheets[i], rules;
      try{ rules=sh.cssRules; }catch(e){ continue; }
      for(var k=0;k<rules.length;k++){
        var r=rules[k];
        if(!r.selectorText || r.selectorText.indexOf(':hover')<0) continue;
        var bases=r.selectorText.split(',').map(function(s){return s.replace(/:hover/g,'').trim();}).filter(Boolean);
        bases.forEach(function(b){
          var els; try{ els=[].slice.call(document.querySelectorAll(b)); }catch(e){ return; }
          var stat={};
          els.forEach(function(el){
            if(!vis(el)) return;              // 被隐藏的月块不算（用户看不见）
            var c=classify(el); if(!c) return;
            stat[c]=stat[c]||{n:0,click:0,tip:0};
            stat[c].n++;
            if(el.dataset.k) stat[c].click++;
            if(hasContent(el)) stat[c].tip++;
          });
          if(Object.keys(stat).length){
            rows.push({sel:r.selectorText, stat:stat});
            for(var key in stat){
              var s=stat[key];
              if(s.click===0 && s.tip===0) tally[key]=(tally[key]||0)+s.n;   // 误伤：会被高亮但既不可点也无内容
            }
          }
        });
      }
    }
    return {rows:rows, tally:tally};
  })()`);

  console.log('=== 1. 静态扫描：哪些 :hover 规则命中了哪些可见格子 ===');
  for (const r of scan.rows) {
    const parts = Object.keys(r.stat).sort().map(k => {
      const s = r.stat[k];
      return `${k} ${s.n}个[可点${s.click}/有内容${s.tip}]`;
    });
    console.log(`  ${r.sel.padEnd(24)} -> ${parts.join('  |  ')}`);
  }
  console.log('\n  ★ 会被 hover 高亮、却既不可点也没有任何内容的格子：');
  const bad = Object.keys(scan.tally).filter(k => !k.startsWith('#'));
  if (!bad.length) console.log('    （无）');
  for (const k of bad.sort()) console.log(`    ${k}  ${scan.tally[k]} 个`);

  /* ---------- 2) 真实指针 hover ---------- */
  const fmt = s => s === 'none' ? 'none' : `${s} 2px`;
  console.log('\n=== 2. 真实指针 hover（判据：outlineStyle none → solid 即「出现橙框」；cursor 语义须匹配）===');
  console.log('  ' + '目标'.padEnd(22) + 'hover前'.padEnd(11) + 'hover后'.padEnd(11) + 'transform'.padEnd(24) + 'cursor(期望)'.padEnd(16) + '期望 / 结果');
  const shots = [];
  let wrong = 0;
  for (const [label, sel, shouldBtn, wantCursor] of CASES) {
    const found = await evalJs(`(function(){${HELPER}
      var el=firstVisible(${JSON.stringify(sel)});
      if(!el) return 0; el.scrollIntoView({block:'center'}); return 1;})()`);
    if (!found) { console.log('  ' + label.padEnd(20) + '(无此元素)'); continue; }
    await sleep(180);
    const pos = await evalJs(`(function(){${HELPER}
      var el=firstVisible(${JSON.stringify(sel)}); var r=el.getBoundingClientRect();
      /* 给鼠标用视口坐标，给截图 clip 用页面坐标（要加 scroll 偏移，否则截到空白区） */
      return {x:r.left+r.width/2, y:r.top+r.height/2,
              px:r.left+window.scrollX, py:r.top+window.scrollY, w:r.width, h:r.height};})()`);
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 4, y: 4, buttons: 0 });
    await sleep(100);
    const before = await evalJs(`(function(){${HELPER}
      var el=firstVisible(${JSON.stringify(sel)}); var cs=getComputedStyle(el);
      return {o:cs.outlineStyle, tr:cs.transform, cur:cs.cursor};})()`);
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pos.x, y: pos.y, buttons: 0 });
    await sleep(180);
    const after = await evalJs(`(function(){${HELPER}
      var el=firstVisible(${JSON.stringify(sel)}); var cs=getComputedStyle(el);
      var hit=document.elementFromPoint(${pos.x},${pos.y});
      var who = hit ? (hit.tagName.toLowerCase()+(hit.className?('.'+String(hit.className).trim().replace(/\\s+/g,'.')):'')) : 'null';
      return {o:cs.outlineStyle, tr:cs.transform, cur:cs.cursor, who:who};})()`);
    const gotBtn = after.o !== 'none';
    const okOutline = gotBtn === shouldBtn;
    const okCursor = after.cur === wantCursor;
    const ok = okOutline && okCursor;
    if (!ok) wrong++;
    console.log('  ' + label.padEnd(20) + fmt(before.o).padEnd(11) + fmt(after.o).padEnd(11)
      + String(after.tr === 'none' ? 'none' : after.tr).padEnd(24)
      + `${after.cur}(${wantCursor})`.padEnd(16)
      + (shouldBtn ? '应有橙框' : '应无反馈') + (ok ? '  ✓' : '  ✗ ' + (okOutline ? '' : '描边不符 ') + (okCursor ? '' : '光标不符'))
      + (after.who.indexOf('ycell') < 0 && after.who.indexOf('hc') < 0 ? `  (指针落在 ${after.who})` : ''));
    if (SHOT) {
      const pad = 22;
      const clip = { x: Math.max(0, pos.px - pad), y: Math.max(0, pos.py - pad), width: pos.w + pad * 2, height: pos.h + pad * 2, scale: 3 };
      const s = await cdp.send('Page.captureScreenshot', { format: 'png', clip });
      const name = `${PREFIX}${shots.length + 1}.png`;
      fs.writeFileSync(path.join(path.dirname(HTML), name), Buffer.from(s.data, 'base64'));
      shots.push({ name, label });
    }
  }
  if (shots.length) {
    console.log('\n  放大 3 倍截图：');
    for (const s of shots) console.log('    ' + s.name + '  ' + s.label);
  }
  console.log(`\n  结论：${wrong === 0 ? '全部符合预期' : wrong + ' 处「可交互暗示」与实际不符'}`);

  cdp.close();
  try { child.kill('SIGKILL'); } catch { }
  try { fs.rmSync(udir, { recursive: true, force: true }); } catch { }
}

main().catch(e => { console.error('探针失败: ' + e.message); try { child.kill('SIGKILL'); } catch { } process.exit(1); });
