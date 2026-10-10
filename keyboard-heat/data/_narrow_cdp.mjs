/* 窄视口几何探针（CDP 版）
 *
 * 为什么要另起一个：`--headless=new --window-size=W,H` 在 Windows 上被 Chrome 钳到
 * **最小窗口宽 ~516px**（实测请求 480/420/380/360/340 全部拿到 vw=500），
 * 于是「手机宽度下会不会挤爆/裁不到位」这类问题**根本量不到**。
 * CDP 的 `Emulation.setDeviceMetricsOverride` 不受窗口限制，可以量任意 CSS 宽度，
 * 且媒体查询按模拟宽度重新求值（`mobile:false`，避免移动端 layout-viewport 缩放）。
 *
 * 测量脚本由调用方（_ui_geom_probe.py）写成文件传入 —— **不在这里再写一份**，
 * 免得量法与判据两头跑偏。输出：每个宽度一行 EGEOM JSON，交给 Python 侧的判据打印。
 *
 * 用法（一般不用手敲，用 `_ui_geom_probe.py --emul 360,414,480`）：
 *   node _narrow_cdp.mjs --widths 360,414,480 --js _probe_measure.js \
 *        --html heat-report-prototype.html [--css "…"] [--pre pre.js] [--shotdir .]
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const argv = process.argv.slice(2);
const get = (n, d) => { const i = argv.indexOf('--' + n); return i >= 0 ? argv[i + 1] : d; };
const has = n => argv.includes('--' + n);

const CHROME = get('chrome', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
const HTML = path.resolve(get('html', 'heat-report-prototype.html'));
const JSF = path.resolve(get('js', '_probe_measure.js'));
const PORT = +get('port', 9344);
const H = +get('height', 1000);
const CSS = get('css', '');
const PREFIX = get('shotprefix', '');
const WIDTHS = get('widths', '360,414,480,600,768').split(',').map(Number);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const MEASURE = fs.readFileSync(JSF, 'utf8')
  .replace(/^\s*<script[^>]*>/, '').replace(/<\/script>\s*$/, '');
const PRE = get('pre', '') ? fs.readFileSync(path.resolve(get('pre')), 'utf8')
  .replace(/^\s*<script[^>]*>/, '').replace(/<\/script>\s*$/, '') : '';

const udir = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-narrow-'));
const fileUrl = 'file:///' + HTML.replace(/\\/g, '/');

/* ⚠ 窗口给得足够大（1400）是刻意的：模拟宽度与真实窗口宽无关，
   但窗口若小于钳制值会引入无谓的变量。 */
const child = spawn(CHROME, [
  '--headless=new', '--remote-debugging-port=' + PORT, '--user-data-dir=' + udir,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars',
  '--force-device-scale-factor=1', '--window-size=1400,' + H, fileUrl,
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

async function main() {
  const target = await findPage();
  const cdp = new CDP(target.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Runtime.enable');
  await cdp.send('Page.enable');

  const evalJs = async expr => {
    const r = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('页面异常: ' + JSON.stringify(r.exceptionDetails.exception || r.exceptionDetails));
    return r.result ? r.result.value : undefined;
  };
  const inject = async code => await evalJs(
    `(function(){var s=document.createElement('script');s.textContent=${JSON.stringify(code)};document.body.appendChild(s);return 1;})()`);

  for (const w of WIDTHS) {
    await cdp.send('Emulation.setDeviceMetricsOverride',
      { width: w, height: H, deviceScaleFactor: 1, mobile: false });
    await cdp.send('Page.reload', { ignoreCache: false });
    let ok = false;
    for (let i = 0; i < 60; i++) {
      /* ⚠ 别拿 `window.DATA` 当就绪标志：原型里的 DATA 是块级 const，**不挂在 window 上**
         （实测 typeof window.DATA === 'undefined'，但页面早已渲染完）。用真实的 DOM 节点。 */
      ok = await evalJs(`(function(){return document.readyState==='complete'&&!!document.querySelector('#day-info .seg')&&!!document.querySelector('#day-nav');})()`);
      if (ok) break;
      await sleep(150);
    }
    if (!ok) {
      let diag = '?';
      try {
        diag = await evalJs(`(function(){return JSON.stringify({rs:document.readyState,
          DATA:typeof window.DATA,seg:!!document.querySelector('#day-info .seg'),
          nav:!!document.querySelector('#day-nav'),vw:innerWidth,url:location.href});})()`);
      } catch (e) { diag = '诊断也失败: ' + e.message; }
      throw new Error('页面没渲染完（width=' + w + '）: ' + diag);
    }
    await sleep(120);
    if (CSS) await inject('(function(){var s=document.createElement("style");s.textContent=' + JSON.stringify(CSS) + ';document.head.appendChild(s);})();');
    if (PRE) await inject(PRE);
    if (CSS || PRE) await sleep(150);
    await inject(MEASURE);
    const raw = await evalJs(`(function(){var p=document.getElementById('EGEOM');return p?p.textContent:'';})()`);
    process.stdout.write((raw || '').trim() + '\n');
    if (PREFIX) {
      const shot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
      fs.writeFileSync(PREFIX + w + '.png', Buffer.from(shot.data, 'base64'));
    }
  }
  cdp.close();
  child.kill();
}

main().catch(e => { console.error('!! ' + e.message); child.kill(); process.exit(1); });
