# -*- coding: utf-8 -*-
"""总览铺砖「布局健康」探针（v3.14）

守护两类失败模式：
 ① `.tile` 内联 `--a:<name>` → `grid-area:var(--a)`，若该 name **未在 `.tiles` 的
    `grid-template-areas` 里定义**，Chrome 不会回退成 auto，而是开「幻影隐式轨道」
    把砖压扁/顶到错位 —— 用户实测到过这个 bug（新砖 tm4~tm8 孤零零飘在右下角、
    其余不可见）。
 ② 新增砖后砖宽变成 4/12（343px），右列的次要信息（.wside，white-space:nowrap）
    可能撑破砖宽被 `overflow:hidden` 裁掉，或与左列数值叠在一起 —— 只看 DOM 文字
    在不在是抓不到的，必须量几何。

判据（宽屏 1280，走显式 areas 路径）：
  O1砖块齐全：恰好 17 块，区域名 = {kb1..3, ms1..3, g1..3, s1..3, a1..3, ot, comp}
        （分组依据是**语义关系**：g* 概览量无对照对象 / s* 与 a* 严格逐列对照 / ot 满宽收尾）
  O2 无幻影压扁：每块 h >= 80（幻影轨道会压到 ~32）
  O3 无零宽：每块 w >= 60
  O4 无重叠：任意两块砖矩形不相交
  O5 网格高度：6 排×88 + 5×12 gap = 588
  O6 反向验证：注入「旧 areas（缺 s*/a*/ot）」→ 必塌成一格重叠
  O7 无裁切：每块文字墨迹（标签/数值/次要信息/小字）都在砖内
  O8 小字无静默截断：.sub 的 scrollWidth <= clientWidth（否则显示为「…」）
  O9 反向验证：注入「小字长句」→ O7/O8 必报红
  O10 **标准侧/实际侧逐列对齐**：s1-s3 与 a1-a3 同 x 同宽（对照语义的几何前提；
         只在宽档判 —— 窄档 auto-fill 按序自填不保证列对齐）
  O11 反向验证：注入「实际侧整体右移一列」→ 几何仍全合法但只有 O10 报红
  O12 areas 有效：浏览器解析出的每行正好 12 格（任一行格数不符 → Chrome **静默丢弃整条
         声明**，所有砖塌到隐式行；O1 查名字齐全抓不到这种失败）
  O13 加班砖贴住最右缘：不允许「独占一行 + auto 放置居中」→ 右侧留白显突兀

CLI：--html 产物路径；--width 视口宽（默认 1280）；--dsf 缩放
"""
import os, sys, json, re, argparse, subprocess, html as htmllib

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

MEASURE = r"""
(function(){
  function ink(el){
    if(!el) return null;
    var r=document.createRange(); r.selectNodeContents(el);
    var rects=r.getClientRects(), l=1e9, rr=-1e9, t=1e9, b=-1e9;
    for(var i=0;i<rects.length;i++){ var q=rects[i];
      if(q.width>0||q.height>0){ if(q.left<l) l=q.left; if(q.right>rr) rr=q.right;
        if(q.top<t) t=q.top; if(q.bottom>b) b=q.bottom; } }
    if(rr<0) return null;
    return {l:Math.round(l), r:Math.round(rr), t:Math.round(t), b:Math.round(b)};
  }
  var host=document.getElementById('stats');
  if(!host){var e=document.createElement('pre');e.id='OV';e.textContent='NOHOST';document.body.appendChild(e);return;}
  function cs(el,p){ return window.getComputedStyle(el).getPropertyValue(p); }
  var out=[], tiles=host.querySelectorAll('.tile');
  for(var i=0;i<tiles.length;i++){
    var t=tiles[i], r=t.getBoundingClientRect();
    out.push({a:(t.style.getPropertyValue('--a')||'').trim(),
              x:Math.round(r.left), y:Math.round(r.top),
              w:Math.round(r.width), h:Math.round(r.height),
              sw:t.scrollWidth, cw:t.clientWidth,
              k:ink(t.querySelector('.k')), v:ink(t.querySelector('.v')),
              s:ink(t.querySelector('.wside')), b:ink(t.querySelector('.sub')),
              bw:(function(){var e=t.querySelector('.sub');return e?e.scrollWidth:null})(),
              bc:(function(){var e=t.querySelector('.sub');return e?e.clientWidth:null})(),
              fd:cs(t,'flex-direction'), ga:cs(t,'grid-area')});
  }
  var hr=host.getBoundingClientRect();
  var el=document.createElement('pre'); el.id='OV';
  // ⚠ 形态判档的唯一权威信号：宿主 .tiles 的 grid-template-areas。
  //   宽档=显式字符串（6 排）、窄档=none（auto-fill 自填）。
  //   不能读瓷砖自身的 grid-area（窄屏媒体查询的 grid-area:auto 盖不住内联
  //   style="--a:tmX" 经 .tile{grid-area:var(--a)} 解析出的命名区域，
  //   计算样式恒为具体区域名、读不出 auto → 会误判成宽档）。
  el.textContent=JSON.stringify({host:{w:Math.round(hr.width),h:Math.round(hr.height),
    gta:cs(host,'grid-template-areas')}, tiles:out});
  document.body.appendChild(el);
})();
"""

EXPECT = set(['kb1','kb2','kb3','ms1','ms2','ms3','comp']
             + ['g1','g2','g3']            # 概览组（日均活跃 / 活跃时长 / 最热一天）
             + ['s1','s2','s3']            # 标准侧
             + ['a1','a2','a3']            # 实际侧（与标准侧逐列对齐）
             + ['ot'])                     # 加班（满宽）
N_TILES = len(EXPECT)          # 17（16 块 + comp 主砖）= kb3+ms3+概览3+标准3+实际3+加班1+comp
ROWS    = 5                    # kb / ms / 概览(含加班) / 标准 / 实际
EXP_H   = ROWS*88 + (ROWS-1)*12  # 488


def overlaps(tiles):
    """两两求交：返回重叠的砖对。幻影轨道下 tm4~tm10 会塌到同一隐式格 → 互相重叠。"""
    out = []
    for i in range(len(tiles)):
        for j in range(i + 1, len(tiles)):
            a, b = tiles[i], tiles[j]
            if (a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w'] and
                    a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h']):
                out.append((a['a'], b['a']))
    return out


def measure(html, pre=None, width=1280, dsf=1):
    src = open(html, encoding='utf-8').read()
    inject = ''
    if pre:
        pj = open(os.path.join(HERE, pre), encoding='utf-8').read()
        inject += '<script>' + pj + '</script>'
    inject += '<script>' + MEASURE + '</script>'
    src = src.replace('</body>', inject + '</body>', 1)
    tmp = os.path.join(HERE, '_ov_tmp.html')
    open(tmp, 'w', encoding='utf-8').write(src)
    url = 'file:///' + tmp.replace('\\', '/')
    cmd = [CHROME, '--headless=new', '--disable-gpu', '--no-first-run',
           '--no-default-browser-check', '--hide-scrollbars',
           '--force-device-scale-factor=%d' % dsf,
           '--window-size=%d,1500' % width, '--dump-dom', url]
    out = subprocess.run(cmd, capture_output=True, timeout=180).stdout.decode('utf-8', 'replace')
    m = re.search(r'<pre id="OV">(.*?)</pre>', out, re.S)
    if not m:
        print('!! 没抠到 OV —— 页面可能抛异常'); print(out[-1200:]); sys.exit(2)
    raw = htmllib.unescape(m.group(1))
    if raw == 'NOHOST':
        print('!! 页面里没有 #stats 宿主'); sys.exit(2)
    res = json.loads(raw)
    # 夹具可能自带一个 <pre id="BADROW">（自包含的最小页面用来证明 Chrome 的行为），
    # 把它一并带回主流程，供反向验证读取 —— measure()原本只认 #OV，会把它丢掉。
    mb = re.search(r'<pre id="BADROW">(.*?)</pre>', out, re.S)
    if mb:
        try:
            res['badrow'] = json.loads(htmllib.unescape(mb.group(1)))
        except Exception:
            res['badrow'] = {'raw': htmllib.unescape(mb.group(1))[:120]}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', default='data/heat-report-prototype.html')
    ap.add_argument('--pre')
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--dsf', type=int, default=1)
    a = ap.parse_args()

    res = measure(a.html, pre=a.pre, width=a.width, dsf=a.dsf)
    tiles = res['tiles']
    print('host %dx%d, 砖块 %d 块' % (res['host']['w'], res['host']['h'], len(tiles)))
    for t in tiles:
        print('   %-5s x=%4d y=%4d w=%4d h=%4d  k=%s v=%s s=%s'
              % (t['a'], t['x'], t['y'], t['w'], t['h'],
                 t.get('k'), t.get('v'), t.get('s')))

    fails = []
    names = set(t['a'] for t in tiles)
    if names != EXPECT:
        fails.append(('O1', '区域名不匹配：缺 %s / 多 %s'
                      % (sorted(EXPECT - names), sorted(names - EXPECT))))
    else:
        print('  [OK] O1 砖块齐全：%d 块（kb1-3 / ms1-3 / 概览g1-3 / 标准s1-3 / 实际a1-3 / 加班ot / comp）' % N_TILES)

    minh = min(t['h'] for t in tiles)
    if minh >= 80:
        print('  [OK] O2 无幻影压扁：最小砖高 %dpx (>=80)' % minh)
    else:
        bad = [t['a'] for t in tiles if t['h'] < 80]
        fails.append(('O2', '有砖被压扁 (<80px)：%s（最小 %dpx）' % (bad, minh)))

    minw = min(t['w'] for t in tiles)
    if minw >= 60:
        print('  [OK] O3 无零宽：最小砖宽 %dpx (>=60)' % minw)
    else:
        fails.append(('O3', '有砖零宽 (<60px)：最小 %dpx' % minw))

    # O4 无重叠：任意两块砖的矩形不得相交。
    #   ⚠ 这才是本 bug 的真实显形：`grid-area` 引用未定义区域时，Chrome 不报错，
    #     而是给这些砖开「幻影隐式格」，把 tm4~tm10 **全部塌进同一格**（互相叠住、
    #     只看得见最后渲染的一块）、并额外挤出隐式列把显式列压窄。
    #     注意：它们**不会变矮** —— .tiles 的 grid-auto-rows:88px 让隐式行也是 88px，
    #     所以只量高度是抓不到的（实测过：反向注入后 tm4~tm10 高度仍全是 88）。
    ov = overlaps(tiles)
    if not ov:
        print('  [OK] O4 无重叠：%d 块互不相交' % len(tiles))
    else:
        fails.append(('O4', '砖块重叠：%s' % (ov[:4],)))

    # ── 布局形态判档：≥901px 走 `.tiles` 的显式 grid-template-areas（12 列、行高 88）；
    #    ≤900px 由媒体查询切成 auto-fill 自填（列宽 ~150-200px、行高 92、砖内竖排）。
    #    两档的**合法形态不同**（例如窄档里 .wside 本来就在数值上方），故 O5/O6/O8/O9
    #    只在宽档判；O7（文字是否越出砖）各档通用，但边界按「padding 边」算 ——
    #    overflow:hidden 的裁剪边是 padding 边，文字落在 padding 里不会被裁掉。
    #    ⚠ 判档只读**宿主 .tiles 的 grid-template-areas**：宽档=非 none 的显式字符串、
    #    窄档=none。瓷砖自身的 grid-area 在窄屏读不出 auto（内联 --a 经 var() 解析成命名
    #    区域，媒体查询的 auto 盖不住），故不能用它判档。
    host_gta = str(res['host'].get('gta', '')).strip().lower()
    wide = host_gta != 'none'
    print('  布局形态：%s（host grid-template-areas=%r）'
          % ('宽档（显式 areas，12 列）' if wide else '窄档（auto-fill 自填）', host_gta))

    hh = res['host']['h']
    if not wide:
        print('  [--] O5 跳过（窄档行高由 auto-fill 决定，不比 %d）' % EXP_H)
    elif abs(hh - EXP_H) <= 30:
        print('  [OK] O5 网格高度合理：%dpx（%d 排，期望 %d）' % (hh, ROWS, EXP_H))
    else:
        fails.append(('O5', '网格高度异常：%dpx（期望 %d，%d 排×88+%d×12 gap）'
                      % (hh, EXP_H, ROWS, ROWS - 1)))

    # O7 文字裁切：时间行已从 4/12 宽砖（343px）收窄到 2/12 窄砖（~165px，与键盘/鼠标
    #     同宽），每块多了一行 `.sub` 小字（数值下方）。窄砖 + nowrap 小字更容易撑破砖宽；
    #     `.tile` 有 overflow:hidden → 文字被无声裁掉（DOM 里文字还在，查标签查不到任何异常）。
    #     判据用**墨迹矩形**（Range.getClientRects，报的是布局结果、不受 overflow 裁剪影响），
    #     要求 标签(.k) / 数值(.v) / 右列(.wside) / 小字(.sub) 全部落在砖内。
    def outside(t):
        """返回越出砖的文字（标签 / 数值 / 右列次要信息 / 数值下方小字），含横竖两向。

        竖向这一路在窄档尤其要紧：媒体查询把行高钉成 `grid-auto-rows:92px`，
        砖内内容变多（小字折行）不会把行撑高，只会被 overflow:hidden 裁掉
        —— 被裁的常常正好是大号数值。"""
        l, r = t['x'] + 1, t['x'] + t['w'] - 1        # border 内缘（overflow:hidden 的裁剪边）
        tp, bt = t['y'] + 1, t['y'] + t['h'] - 1
        bad = []
        for key in ('k', 'v', 's', 'b'):
            box = t.get(key)
            if not box:
                continue
            if box['l'] < l - 2 or box['r'] > r + 2 or box['t'] < tp - 2 or box['b'] > bt + 2:
                bad.append((key, box['l'], box['r'], box['t'], box['b']))
        return bad

    clipped = [(t['a'], outside(t)) for t in tiles if outside(t)]
    if not clipped:
        print('  [OK] O7 文字都落在砖内：全部砖墨迹（横竖两向）都没越出砖边')
    else:
        fails.append(('O7', '文字越出砖（会被 overflow:hidden 裁掉）：%s' % (clipped[:4],)))

    # O8 小字不被静默截断：`.sub` 是 `white-space:nowrap` + `text-overflow:ellipsis`，
    #     一旦小字超宽，浏览器只把尾巴截成「…」—— DOM 里 textContent 完整、
    #     查标签查得到、截图上仅多一个省略号，肉眼极易放过。判据用 scrollWidth > clientWidth
    #     （ellipsis 生效时**不会**越出砖边，所以 O7 的墨迹检测抓不到它，必须另判）。
    #     ⚠ 这一条取代了 v3.14 的「宽砖左右两列不叠」：时间行改窄砖后总览里已无
    #       带 .wside 的横排砖（comp 砖也无 .wside），那条判据会恒真 —— 恒真的判据等于没判据。
    trunc = [(t['a'], t.get('bw'), t.get('bc')) for t in tiles
             if (t.get('bw') or 0) > (t.get('bc') or 0) + 1]
    if not trunc:
        print('  [OK] O8 小字未被截断：全部 .sub 的 scrollWidth <= clientWidth（无省略号）')
    else:
        fails.append(('O8', '小字被 ellipsis 静默截断（显示为「…」）：%s' % (trunc[:6],)))

    # ── O10（仅宽档）：标准侧 s1-3 与实际侧 a1-3 必须**逐列对齐** ──
    #   这是本布局的核心语义：「同一列 = 同一维度的工作/活跃/占比」，两行相接即可横向读出
    #   「标准 vs 实际」的差额与比率。若两列 x 不一致（哪怕砖仍不重叠、O4 仍绿），
    #   读者就得逐块数位置才能比对 —— 对照语义在视觉上已经失效，而几何判据抓不到。
    #   故把「逐列对齐」本身立成判据。窄档 auto-fill 按数组顺序自填、不保证列对齐，故跳过。
    if not wide:
        print('  [--] O10 跳过（窄档 auto-fill 自填，不保证逐列对齐）')
    else:
        pos = {t['a']: t for t in tiles}
        mis = []
        for i in (1, 2, 3):
            sa, aa = pos.get('s%d' % i), pos.get('a%d' % i)
            if not sa or not aa:
                mis.append(('s%d/a%d' % (i, i), '缺砖'))
            elif abs(sa['x'] - aa['x']) > 1 or abs(sa['w'] - aa['w']) > 1:
                mis.append(('s%d/a%d' % (i, i), 'x=%d/%d w=%d/%d'
                            % (sa['x'], aa['x'], sa['w'], aa['w'])))
        if not mis:
            print('  [OK] O10 标准/实际两侧逐列对齐：三对砖同 x 同宽 → 对照语义成立')
        else:
            fails.append(('O10', '标准侧与实际侧未逐列对齐：%s' % (mis,)))
            print('  [FAIL] O10 未逐列对齐：%s' % (mis,))

    # ── O12：`grid-template-areas` **每行必须正好 12 格**，否则 Chrome 会把**整条声明
    #     静默丢弃**（不是报错、不是部分生效）：实测某行写成 13 格时，
    #     `getComputedStyle().gridTemplateAreas` 直接变成 `none`、`grid-template-rows`
    #     只剩隐式行 → 所有砖塌到同一处、host 高度从 588 掉到 188。
    #     这类失败靠 O1（查名字齐全）抓不到 —— 名字都在，只是没落到该去的格子。
    #     判据直接量浏览器解析结果，不去数源码字符串（源码可能还有别的失效途径）。
    if not wide:
        print('  [--] O12 跳过（窄档 areas:none，按 auto-fill 自填）')
    else:
        rows = str(res['host'].get('gta', '')).split('" "')
        badrow = [i + 1 for i, r in enumerate(rows) if len(r.split()) != 12]
        if res['host'].get('gta', 'none').strip().lower() != 'none' and not badrow:
            print('  [OK] O12 areas 解析有效：%d 行 × 每行 12 格' % len(rows))
        else:
            fails.append(('O12', 'areas 解析异常：gta=%r，非 12 格的行=%s'
                          % (res['host'].get('gta', '')[:40], badrow)))
            print('  [FAIL] O12 areas 解析异常')

    # ── O13：加班砖不得「独占一行且悬在行内中间」 ──
    #     它曾被声明成整行满宽（`ot`×12），但 Chrome 会让这种单行重复的命名区域
    #     **退化成 auto 放置**：砖按内容宽缩在行内居中（实测 x=392 w=480，host 宽 1052），
    #     右侧空一大片 → 用户反馈「加班时长有点太突兀」。
    #     判据：ot 的右缘应贴近宿主右缘（与最右列砖同右缘），不允许悬在中间。
    #     ⚠ 只在宽档判；窄档 auto-fill 自填不按 areas 定位。
    if not wide:
        print('  [--] O13 跳过（窄档不按 areas 定位）')
    else:
        ot = {t['a']: t for t in tiles}.get('ot')
        rightmost = max(tiles, key=lambda t: t['x'] + t['w'])
        if not ot:
            fails.append(('O13', '找不到加班砖 ot'))
            fails.append(('O13', '找不到加班砖 ot'))
        elif (ot['x'] + ot['w']) < (rightmost['x'] + rightmost['w']) - 2:
            fails.append(('O13', '加班砖未贴住最右缘（右缘 %d，应 ≥ %d）→ 右侧留白、显突兀'
                          % (ot['x'] + ot['w'], rightmost['x'] + rightmost['w'])))
            print('  [FAIL] O13 加班砖悬在行内（未贴最右缘）')
        else:
            print('  [OK] O13 加班砖贴住最右缘（右缘 %d）→ 不再悬空'
                  % (ot['x'] + ot['w']))

    for code, msg in fails:
        print('  [FAIL] %s %s' % (code, msg))

    # 反向验证：注入旧 areas（删掉 tm4~tm10 的定义）→ 应复现「塌进同一格、互相重叠」
    if not a.pre and wide:
        rc = measure(a.html, pre='_pre_oldareas_1.js', width=a.width, dsf=a.dsf)
        rov = overlaps(rc['tiles'])
        gone = sorted(t for t in EXPECT if t not in
                      ('kb1','kb2','kb3','ms1','ms2','ms3','comp','g1','g2','g3'))
        pos = [(t['a'], t['x'], t['y']) for t in rc['tiles'] if t['a'] in gone]
        print('  反向(旧areas)：重叠 %d 对；%s 位置=%s' % (len(rov), gone, pos))
        if rov:
            print('  [OK] O6 反向验证：旧 areas 下砖块塌成一格互相重叠 → O4 判据有效')
        else:
            fails.append(('O6', '反向验证失败：旧 areas 没复现重叠（夹具失效）'))
            print('  [FAIL] O6 反向验证夹具没复现出重叠')

    # 反向验证②：注入「小字长句」夹具 → 越框/截断必报红，
    # 以此证明 O7/O8 不是「永远为真」的空判据。
    if not a.pre and wide:
        rz = measure(a.html, pre='_pre_ovflow_1.js', width=a.width, dsf=a.dsf)
        zt = rz['tiles']
        zclip = [t['a'] for t in zt if outside(t)]
        ztrunc = [(t['a'], t.get('bw'), t.get('bc')) for t in zt
                  if (t.get('bw') or 0) > (t.get('bc') or 0) + 1]
        print('  反向(小字长句)：文字越框砖=%s；小字截断=%s'
              % (zclip[:6], ztrunc[:6]))
        if zclip or ztrunc:
            print('  [OK] O9 反向验证：长句形态下 O7/O8 必报红 → 两条判据有效')
        else:
            fails.append(('O9', '反向验证失败：长句夹具既没触发越框也没触发小字截断'))
            print('  [FAIL] O9 长句夹具没复现出溢出')

    # 反向验证③：注入「实际侧列跨度非对称（3/6/3）」夹具 → 几何仍全合法，但对照语义已破，
    # 必须只有 O10 报红（这正是「几何判据抓不到语义退化」的证明）。
    if not a.pre and wide:
        rm = measure(a.html, pre='_pre_misalign_1.js', width=a.width, dsf=a.dsf)
        mp = {t['a']: t for t in rm['tiles']}
        mmis = ['s%d/a%d' % (i, i) for i in (1, 2, 3)
                if 's%d' % i in mp and 'a%d' % i in mp
                and (abs(mp['s%d' % i]['x'] - mp['a%d' % i]['x']) > 1
                     or abs(mp['s%d' % i]['w'] - mp['a%d' % i]['w']) > 1)]
        mgeom_ok = not overlaps(rm['tiles'])
        print('  反向(实际侧 3/6/3 非对称)：失配列=%s；砖块重叠=%s'
              % (mmis, '有' if mgeom_ok else '无'))
        if mmis and mgeom_ok:
            print('  [OK] O11 反向验证：几何全合法但 O10 报红 → O10 抓得住语义退化')
        else:
            fails.append(('O11', '反向验证失败：非对称夹具未能只让 O10 报红（失配=%s 重叠=%s）'
                          % (mmis, mgeom_ok)))
            print('  [FAIL] O11 非对称夹具没有复现出「几何合法但未对齐」')

    # 反向验证④：夹具自带一个**自包含最小页面**（两个 grid：一个每行 12 格合法、
    #     一个其中一行 13 格非法），验证「格数不符 → Chrome 丢弃整条声明」。
    #     不用注入真实报告的 CSS：同名选择器靠文档顺序决胜，实测经常注入不生效（假绿）。
    #     O12 必须报红 → 证明它抓得住「声明被静默丢弃」这类失败。
    if not a.pre and wide:
        rb = measure(a.html, pre='_pre_badrow_1.js', width=a.width, dsf=a.dsf)
        br = rb.get('badrow') or {}
        bgta = str(br.get('bad', '')).strip().lower()
        print('  反向(最小页面 13 格)：合法=%r非法=%r'
              % (str(br.get('good', ''))[:18], str(br.get('bad', ''))[:18]))
        if bgta == 'none':
            print('  [OK] O14 反向验证：13 格 → Chrome 丢弃整条 areas → O12 必报红')
        else:
            fails.append(('O14', '反向验证失败：13 格并未让 Chrome 丢弃 areas（%r）' % bgta[:40]))
            print('  [FAIL] O14 13 格夹具没有复现出声明失效')

    total = 15 if wide else 9      # 宽档 O1-O13 + O6/O9/O11/O14 反向；窄档跳过 O5/O6/O9~O14
    print('\n结果：%d 通过 / %d 失败' % (total - len(fails), len(fails)))
    if not fails:
        print('全部通过 ✓')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
