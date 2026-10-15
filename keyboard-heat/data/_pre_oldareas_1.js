/* 反向验证夹具：把 `.tiles` 的 grid-template-areas 还原成「只有键盘行/鼠标行/概览行」的旧形态
   （没有 s1~s3 / a1~a3 / ot 这些标准侧、实际侧、加班区域）。

   预期：s1~s3、a1~a3、ot 的 `--a` 引用不存在的命名区域 → Chrome 开幻影隐式轨道把砖压扁/错位，
   探针 O2（最小砖高 >=80）与 O4（无重叠）应同时报红 —— 以此证明「补齐全部区域名」这一步
   确实是修复的关键，而不是碰巧看着正常。

   ⚠ 注入的是**真实存在的旧形态**（少 7 个区域），不是等价变换；这些砖会真的塌进同一隐式格。 */
(function () {
  var s = document.createElement('style');
  s.textContent =
    '.tiles{grid-template-areas:' +
    '"kb1 kb1 kb2 kb2 kb3 kb3 comp comp comp comp comp comp" ' +
    '"ms1 ms1 ms2 ms2 ms3 ms3 comp comp comp comp comp comp" ' +
    '"g1 g1 g1 g1 g1 g1 g2 g2 g2 g2 g3 g3"}';
  document.head.appendChild(s);
})();