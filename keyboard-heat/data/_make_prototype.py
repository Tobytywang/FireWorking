# -*- coding: utf-8 -*-
"""从现有 heat-report.html 抽取真实 DATA/META/COUNTDOWN，
生成「高保真原型 v2」 heat-report-prototype.html（仅用于看效果）。
v2 变更：单色相饱和度色阶 / 7x24 周视图(8行+翻周) / 总览聚类 / 全年GitHub日历 /
合并分钟级到小时级 / 倒计时每日改日历热力图。
"""
import re, json, io

SRC = r"D:\Workspace\HardWorking\keyboard-heat\data\heat-report.html"
OUT = r"D:\Workspace\HardWorking\keyboard-heat\data\heat-report-prototype.html"

with io.open(SRC, "r", encoding="utf-8") as f:
    html = f.read()

def grab(name):
    m = re.search(r"const %s\s*=\s*(.*?);\s*\nconst " % name, html, re.S)
    if not m:
        m = re.search(r"const %s\s*=\s*(.*?);" % name, html, re.S)
    return m.group(1)

DATA = json.loads(grab("DATA"))
META = json.loads(grab("META"))
COUNTDOWN = json.loads(grab("COUNTDOWN"))

DATA_JS = json.dumps(DATA, ensure_ascii=False, separators=(",", ":"))
META_JS = json.dumps(META, ensure_ascii=False, separators=(",", ":"))
CD_JS = json.dumps(COUNTDOWN, ensure_ascii=False, separators=(",", ":"))

TEMPLATE = r"D:\Workspace\HardWorking\keyboard-heat\report_template.html"
TPL = io.open(TEMPLATE, "r", encoding="utf-8").read()

out = TPL.replace("__DATA_JSON__", DATA_JS).replace("__META_JSON__", META_JS).replace("__COUNTDOWN_JSON__", CD_JS)
with io.open(OUT, "w", encoding="utf-8") as f:
    f.write(out)
print("written:", OUT, "bytes:", len(out.encode("utf-8")))
print("DATA days:", len(DATA), "countdown days:", len(COUNTDOWN))
