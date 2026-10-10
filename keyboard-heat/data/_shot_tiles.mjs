/* 区块截图：把 clip 对准某个锚点元素的 section，只截该区块，
   在多个模拟宽度 + DPR 下各截一张，便于目视验收（含环图最终占比）。
   --sel 指定锚点（默认 #stats 总览）；锚点需位于目标 <section> 内。
   --only "<选择器>" + --idx N：只截第 N 个匹配元素的自身盒子（用于裁「单张卡」做对照，
   --pad 给四周留几 px 白边；不带 --pad 时图内坐标 = 卡片内相对坐标，方便按 vTop 画标尺线）。 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const argv = process.argv.slice(2);
const get = (n, d) => { const i = argv.indexOf('--' + n); return i >= 0 ? argv[i + 1] : d; };

const CHROME = get('chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
const HTML = path.resolve(get('html', 'heat-report-prototype.html'));
const OUT = path.resolve(get('out', '.'));
const PORT = +get('port', 9355);
const WIDTHS = get('widths', '1280,900,620,390').split(',').map(Number);
const DPR = +get('dpr', 1);
const TAG = get('tag', 'tiles');
const SEL = get('sel', '#stats');
const ONLY = get('only', '');
const IDX = +get('idx', 0);
const PAD = +get('pad', 0);
const CSSF = get('cssfile', '');
const PREF = get('pre', '');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fileUrl = 'file:///' + HTML.replace(/\\/g, '/');
const CSS_TXT = CSSF ? fs.readFileSync(path.resolve(CSSF), 'utf8') : '';
const PRE_TXT = PREF ? fs.readFileSync(path.resolve(PREF), 'utf8')
  .replace(/^\s*<script[^>]*>/, '').replace(/<\/script>\s*$/, '') : '';

const udir = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-tiles-'));
const child = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=' + PORT, '--user-data-dir=' + udir,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars',
  '--force-device-scale-factor=' + DPR, '--window-size=1400,1200', fileUrl,
], { stdio: 'ignore' });

class CDP {
  constructor(url) {
    this.ws = new WebSocket(url); this.id = 0; this.pend = new Map();
    this.ready = new Promise((res, rej) => { this.ws.onopen = () => res(); this.ws.onerror = () => rej(new Error('ws')); });
    this.ws.onmessage = ev => { const m = JSON.parse(ev.data);
      if (m.id && this.pend.has(m.id)) { const p = this.pend.get(m.id); this.pend.delete(m.id);
        m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } };
  }
  send(method, params = {}) { const id = ++this.id;
    return new Promise((res, rej) => { this.pend.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id, method, params })); }); }
  close() { try { this.ws.close(); } catch { } }
}
async function findPage() {
  for (let i = 0; i < 80; i++) {
    try { const j = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const p = j.find(t => t.type === 'page' && t.webSocketDebuggerUrl); if (p) return p; } catch { }
    await sleep(250);
  }
  throw new Error('chrome 未就绪');
}
async function main() {
  const target = await findPage();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Runtime.enable');
  const ev = async e => { const r = await cdp.send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(JSON.stringify(r.exceptionDetails.exception || r.exceptionDetails));
    return r.result ? r.result.value : undefined; };
  for (const w of WIDTHS) {
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: 1200, deviceScaleFactor: DPR, mobile: false });
    await cdp.send('Page.reload', {});
    let ok = false;
    for (let i = 0; i < 60; i++) {
      ok = await ev(`(function(){var e=document.querySelector(${JSON.stringify(SEL)});return document.readyState==='complete'&&!!e&&e.children.length>0;})()`);
      if (ok) break; await sleep(150);
    }
    if (!ok) { console.error('!! 未渲染完 width=' + w); continue; }
    if (CSS_TXT) await ev(`(function(){var s=document.createElement('style');s.textContent=${JSON.stringify(CSS_TXT)};document.head.appendChild(s);return 1;})()`);
    if (PRE_TXT) await ev(`(function(){var s=document.createElement('script');s.textContent=${JSON.stringify(PRE_TXT)};document.body.appendChild(s);return 1;})()`);
    await sleep(1300); // 等环图动画跑完
    // 量目标盒的**页面绝对坐标**，用 clip 精确截该段（不动视口）
    const box = await ev(`(function(){
      var only=${JSON.stringify(ONLY)}, idx=${IDX}, pad=${PAD};
      if(only){
        var el=document.querySelectorAll(only)[idx]; if(!el) return null;
        var r=el.getBoundingClientRect();
        return {x:Math.round(r.left+window.scrollX-pad), y:Math.round(r.top+window.scrollY-pad),
                w:Math.round(r.width+pad*2), h:Math.round(r.height+pad*2)};
      }
      var s=document.querySelector(${JSON.stringify(SEL)}).closest('section');
      var sr=s.getBoundingClientRect();
      return {x:Math.round(sr.left+window.scrollX), y:Math.round(sr.top+window.scrollY),
              w:Math.round(sr.width), h:Math.round(sr.height)};})()`);
    if (!box) { console.error('!! --only 未命中：' + ONLY + ' idx=' + IDX); continue; }
    await sleep(150);
    const shot = await cdp.send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: true,
      clip: ONLY
        ? { x: box.x, y: box.y, width: box.w, height: box.h, scale: 1 }
        : { x: box.x, y: Math.max(0, box.y - 12), width: box.w, height: box.h + 34, scale: 1 },
    });
    const name = `${TAG}_${w}_${DPR}x.png`;
    fs.writeFileSync(path.join(OUT, name), Buffer.from(shot.data, 'base64'));
    console.log('saved', name, ONLY ? ('el ' + box.w + 'x' + box.h) : ('section ' + box.w + 'x' + box.h));
  }
  cdp.close(); child.kill();
}
main().catch(e => { console.error('!! ' + e.message); child.kill(); process.exit(1); });
