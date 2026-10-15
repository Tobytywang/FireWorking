/* O11 反向验证夹具：把**实际侧的列跨度改成非对称**（3/6/3），破坏「与标准侧逐列对齐」。

   动机：最初想用「右移一列 + `.` 空格子」制造错位，但实测发现 Chrome 会把 `.` 规范化、
   命名区域仍按自身声明落位 → 砖根本没动，夹具失效（假绿）。改用**非对称跨度**：
   标准侧是 4/4/4，实际侧变3/6/3，a1 与 s1 的 x 必然不同、a3 与 s3 的宽度必然不同。

   这仍是一个「几何完全合法」的坏形态：所有砖互不重叠、高度仍 88px、文字不越框，
   O1/O2/O3/O4/O7/O8 照样全绿 —— 但「同一列 = 同一维度」的对照语义已破。
   O10（逐列对齐）必须报红，以此证明 O10 不是恒真的空判据。

   每行正好 12 格，不引入幻影轨道。

   ⚠ 踩过的坑：最初用「`. . a1 a1 a1 ... . .`」（右移一列 + 点号空格子）制造错位，
   实测 **Chrome 会把 `.` 规范化掉、命名区域 a1 仍落回第 1 列，砖根本没动** → 夹具失效、
   探针假绿。用 `.` 造偏移在这类「命名区域已声明」的 grid 上不可靠，改用非对称跨度。 */
(function () {
  var s = document.createElement('style');
  s.textContent =
    '.tiles{grid-template-areas:' +
    '"kb1 kb1 kb2 kb2 kb3 kb3 comp comp comp comp comp comp" ' +
    '"ms1 ms1 ms2 ms2 ms3 ms3 comp comp comp comp comp comp" ' +
    '"g1 g1 g1 g1 g1 g1 g2 g2 g2 g2 g3 g3" ' +
    '"s1 s1 s1 s1 s2 s2 s2 s2 s3 s3 s3 s3" ' +
    '"a1 a1 a1 a2 a2 a2 a2 a2 a2 a3 a3 a3" ' +   /* ← 实际侧 3/6/3，与标准侧 4/4/4 错位 */
    '"ot ot ot ot ot ot ot ot ot ot ot ot"}';
  document.head.appendChild(s);
})();