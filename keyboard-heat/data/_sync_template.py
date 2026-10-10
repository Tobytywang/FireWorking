# -*- coding: utf-8 -*-
"""一次性迁移：把 v2 设计落地成工具真正使用的报告模板，并消除"双模板漂移"。

背景（症结）
  · 工具正式报告的生成器是 report.py，它读 **report_template.html**（占位符
    __DATA_JSON__ / __META_JSON__ / __COUNTDOWN_JSON__）→ 写出 data/heat-report.html。
    main.py --report / overlay.py / overlay_tk.py 三处托盘入口都调它。
  · 而 v2（暖橙/ember、3 小节、v3.6–v3.11 + 间隙修复）这套设计**只存在于**
    data/_make_prototype.py 的硬编码 TPL 里（占位符 __DATA__ / __META__ / __COUNTDOWN__），
    生成的是 heat-report-prototype.html。
  ⇒ 两个模板各存一份、内容却要一致；先前把原型 cp 到 heat-report.html 当"正式版"，
    只要工具再跑一次 report.generate（重启 / 点托盘「生成报告」）就被 v1 模板重生成冲掉。

本脚本做两件事，从此**报告模板单一数据源**
  1) 把 _make_prototype.py 里的 TPL 抽出来，占位符改名为 report.py 认的那三个，
     写进 report_template.html（旧 v1 版本另存 report_template.html.v1bak）。
  2) 把 _make_prototype.py 改成"读 report_template.html"，不再自带一份 TPL
     （旧版另存 _make_prototype.py.v1bak）。

幂等性：若 .v1bak 已存在则不再覆盖备份；模板与生成器可重复生成同一结果。
"""
import io
import os
import shutil

BASE = r"D:\Workspace\HardWorking\keyboard-heat"
PROTO_PY = os.path.join(BASE, "data", "_make_prototype.py")
TEMPLATE = os.path.join(BASE, "report_template.html")


def rd(p):
    return io.open(p, "r", encoding="utf-8").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)


def backup(p):
    b = p + ".v1bak"
    if not os.path.exists(b):
        shutil.copy2(p, b)
        print("backup  ->", b)
    else:
        print("backup  -> 已存在，跳过", b)


# 0) 备份
backup(PROTO_PY)
backup(TEMPLATE)

# 1) 从 _make_prototype.py 抽出 TPL 字面量
src = rd(PROTO_PY)
marker = 'TPL = r"""'
mi = src.index(marker)
i = mi + len(marker)
j = src.index('"""', i)                 # TPL 内容里不含三引号，最近的即闭合
tpl = src[i:j]
for slot in ("__DATA__", "__META__", "__COUNTDOWN__"):
    assert slot in tpl, "TPL 里没找到占位符 %s" % slot
print("extract -> TPL %d chars" % len(tpl))

# 2) 占位符改名为 report.py 认的名字，写出 report_template.html
tpl2 = (tpl.replace("__DATA__", "__DATA_JSON__")
           .replace("__META__", "__META_JSON__")
           .replace("__COUNTDOWN__", "__COUNTDOWN_JSON__"))
assert "__DATA_JSON__" in tpl2 and "__DATA__" not in tpl2.replace("__DATA_JSON__", "")
wr(TEMPLATE, tpl2)
print("write   -> %s  (%d bytes)" % (TEMPLATE, len(tpl2.encode("utf-8"))))

# 3) 把 _make_prototype.py 改成"读模板"，并同步末尾 replace 的占位符名
head = ('TEMPLATE = r"%s"\nTPL = io.open(TEMPLATE, "r", encoding="utf-8").read()'
        % TEMPLATE)
src2 = src[:mi] + head + src[j + 3:]
old_call = ('TPL.replace("__DATA__", DATA_JS)'
            '.replace("__META__", META_JS)'
            '.replace("__COUNTDOWN__", CD_JS)')
new_call = ('TPL.replace("__DATA_JSON__", DATA_JS)'
            '.replace("__META_JSON__", META_JS)'
            '.replace("__COUNTDOWN_JSON__", CD_JS)')
assert old_call in src2, "没找到末尾的 TPL.replace(...) 调用"
src2 = src2.replace(old_call, new_call)
wr(PROTO_PY, src2)
print("rewire  -> %s  (%d bytes)" % (PROTO_PY, len(src2.encode("utf-8"))))
print("done.")
