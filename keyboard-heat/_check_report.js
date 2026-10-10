const fs = require('fs');
const path = require('path');
const vm = require('vm');

const file = process.argv[2] || path.join(__dirname, 'data', 'demo-report.html');
const html = fs.readFileSync(file, 'utf8');
const out = [];

out.push('文件: ' + file + '  (' + (html.length / 1024).toFixed(1) + ' KB)');

const re = /<script>([\s\S]*?)<\/script>/g;
let m, i = 0;
while ((m = re.exec(html))) {
  i++;
  try {
    new vm.Script(m[1], { filename: 'inline' + i + '.js' });
    out.push('script #' + i + ' 语法 OK  (' + m[1].length + ' 字符)');
  } catch (e) {
    out.push('script #' + i + ' 语法错误: ' + e.message);
  }
}

const dm = html.match(/const DATA = ([\s\S]*?);\s*const META = ([\s\S]*?);\s*const DAY_KEYS/);
if (!dm) {
  out.push('!! 找不到 DATA / META 注入点（模板可能是 CRLF 换行）');
} else {
  const data = JSON.parse(dm[1]);
  const meta = JSON.parse(dm[2]);
  const days = Object.keys(data).sort();
  let rows = 0;
  for (const k of days) rows += data[k].length;
  out.push('DATA 天数: ' + days.length);
  out.push('DATA 总行数: ' + rows);
  out.push('META: ' + JSON.stringify(meta));
  out.push('样例 ' + days[0] + ': ' + JSON.stringify(data[days[0]].slice(0, 3)));
  out.push('样例 ' + days[days.length - 1] + ': ' + JSON.stringify(data[days[days.length - 1]].slice(0, 3)));
}

out.push('占位符残留: ' + (html.includes('__DATA_JSON__') || html.includes('__META_JSON__') ? '有 !!' : '无'));

fs.writeFileSync(path.join(__dirname, '_check.log'), out.join('\n'), 'utf8');
