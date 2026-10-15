/* O14 反向验证：用一个**独立的最小页面**验证「某行格数 ≠ 12 → Chrome 丢弃整条areas 声明」。

   为什么不用注入夹具：往真实报告里注入 `.tiles{grid-template-areas:…}` 时，
   同名选择器要靠文档顺序决胜，实测经常**注入不生效**（假绿）。
   而这条判据要证明的是「Chrome 的行为」，用一个自包含的最小页面更直接、也更稳定。

   页面构造两个 grid：一个每行都 12 格（合法），一个其中一行 13 格（非法）。
   预期：合法者 getComputedStyle().gridTemplateAreas 有值；非法者为 "none"。 */
(function () {
  function mk(rows, id) {
    var d = document.createElement('div');
    d.className = 'probe-' + id;
    d.style.cssText = 'display:grid;grid-template-columns:repeat(12,1fr);' +
      'grid-template-areas:' + rows;
    document.body.appendChild(d);
    return d;
  }
  var good = '"a a a a b b b b c c c c" "d d d d e e e e f f f f"';
  var bad = '"a a a a b b b b c c c c" "d d d d e e e e f f f f g"';
  var gd = mk(good, 'good');
  var bd = mk(bad, 'bad');
  var el = document.createElement('pre');
  el.id = 'BADROW';
  el.textContent = JSON.stringify({
    good: getComputedStyle(gd).gridTemplateAreas.slice(0, 30),
    bad: getComputedStyle(bd).gridTemplateAreas
  });
  document.body.appendChild(el);
})();