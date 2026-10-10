"""报告层（含鼠标）实测：造一份带鼠标数据的库，生成 HTML，校验数据形状。

不是单元测试的替代，是端到端确认 —— 之前 report.py 的 SELECT 写死 4 列，
加了鼠标列之后如果忘记改，这里会直接炸在 no such column 上。
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report
from heatcore import ensure_schema, log_countdown

OK = 0
BAD = 0


def check(name, got, want):
    global OK, BAD
    if got == want:
        OK += 1
        print("  [PASS] %-38s %s" % (name, got))
    else:
        BAD += 1
        print("  [FAIL] %-38s got=%r want=%r" % (name, got, want))


def build_db(path: Path):
    with sqlite3.connect(path) as conn:
        ensure_schema(conn)
        rows = []
        base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        def add(day_offset, hour, minute, keys, bs, act, mv, ck, sc):
            ts = int((base - timedelta(days=day_offset)).timestamp()) + hour * 3600 + minute * 60
            rows.append((ts, keys, bs, act, mv, ck, sc))

        # 两天前：纯打字，3 小时（鼠标全 0，用来验证"零鼠标"这条支路不崩）
        for m in range(0, 180):
            add(2, 9 + m // 60, m % 60, 120, 6, 60, 0, 0, 0)
        # 一天前：纯鼠标浏览（浏览文档 / 拖拽），2 小时
        for m in range(0, 120):
            add(1, 14 + m // 60, m % 60, 0, 0, 60, 900, 6, 4)
        # 今天：混合，1 小时
        for m in range(0, 60):
            add(0, 10, m, 80, 4, 60, 400, 3, 1)

        conn.executemany(
            "INSERT INTO minutes(minute_ts,keystrokes,backspaces,active_secs,"
            "mouse_moves,clicks,scrolls) VALUES(?,?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="heat-report-"))
    db = tmp / "heat.db"
    out = tmp / "report.html"
    n = build_db(db)
    print("== 造数据 ==")
    print("  插入 %d 行分钟数据 → %s" % (n, db))

    cfg = {"storage": {"db_path": str(db)}, "report": {"keep_days": 30, "output": str(out)}}

    print("\n== 倒计时落库（真实 log_countdown round-trip）==")
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_ago = lambda n, h, m: int((base - timedelta(days=n)).timestamp()) + h * 3600 + m * 60
    # 今天：菜单 5 / 菜单 10 / 双击 25 / 热键 5  → 5:2, 10:1, 25:1
    log_countdown(5, "menu", db)
    log_countdown(10, "menu", db)
    log_countdown(25, "double_click", db)
    log_countdown(5, "hotkey", db)
    # 两天前：混来源三条（菜单 5 / 双击 10 / 热键 25）
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO countdown_log(ts,minutes,source) VALUES(?,?,?)",
                     (days_ago(2, 8, 0), 5, "menu"))
        conn.execute("INSERT INTO countdown_log(ts,minutes,source) VALUES(?,?,?)",
                     (days_ago(2, 9, 0), 10, "double_click"))
        conn.execute("INSERT INTO countdown_log(ts,minutes,source) VALUES(?,?,?)",
                     (days_ago(2, 10, 0), 25, "hotkey"))

    path = report.generate(cfg, db_path=db, output=out)

    print("\n== 生成的报告 ==")
    check("文件已写出", path.exists(), True)
    html = path.read_text(encoding="utf-8")

    print("\n== 模板占位符 ==")
    check("DATA 占位符已替换", "__DATA_JSON__" not in html, True)
    check("META 占位符已替换", "__META_JSON__" not in html, True)
    check("COUNTDOWN 占位符已替换", "__COUNTDOWN_JSON__" not in html, True)
    check("报告含倒计时统计区块", 'id="countdown"' in html, True)
    check("报告含按类型分布容器", 'id="cd-types"' in html, True)

    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    check("能从 HTML 里取回 DATA", bool(m), True)
    data = json.loads(m.group(1))
    days = sorted(data)
    check("天数", len(days), 3)

    print("\n== 每分钟字段数 ==")
    for d in days:
        lens = {len(r) for r in data[d]}
        check("%s 行宽" % d, lens, {7})

    print("\n== 鼠标数字进得来 ==")
    pure_kb = data[days[0]]
    pure_mouse = data[days[1]]
    mixed = data[days[2]]
    check("纯打字日 鼠标移动全 0", sum(r[4] for r in pure_kb), 0)
    check("纯打字日 点击滚轮全 0",
          (sum(r[5] for r in pure_kb), sum(r[6] for r in pure_kb)), (0, 0))
    check("纯鼠标日 击键全 0", sum(r[1] for r in pure_mouse), 0)
    check("纯鼠标日 移动总量", sum(r[4] for r in pure_mouse), 900 * 120)
    check("纯鼠标日 点击总量", sum(r[5] for r in pure_mouse), 6 * 120)
    check("纯鼠标日 滚轮总量", sum(r[6] for r in pure_mouse), 4 * 120)
    check("混合日 键鼠都非 0",
          (sum(r[1] for r in mixed) > 0, sum(r[4] for r in mixed) > 0), (True, True))

    print("\n== 倒计时按日/类型聚合 ==")
    cd = report._collect_countdown(db, 30)
    today = base.strftime("%Y-%m-%d")
    day2 = (base - timedelta(days=2)).strftime("%Y-%m-%d")
    check("倒计时覆盖天数", len(cd), 2)
    check("今天总次数", cd[today]["total"], 4)
    check("今天 5 分钟次数", cd[today]["by_type"]["5"], 2)
    check("今天 10 分钟次数", cd[today]["by_type"]["10"], 1)
    check("今天 25 分钟次数", cd[today]["by_type"]["25"], 1)
    check("今天 double_click 来源", cd[today]["by_source"]["double_click"], 1)
    check("今天 hotkey 来源", cd[today]["by_source"]["hotkey"], 1)
    check("by_type 含全部三种类型键", set(cd[today]["by_type"].keys()) >= {"5", "10", "25"}, True)
    check("两天前总次数", cd[day2]["total"], 3)
    check("两天前 25 分钟次数", cd[day2]["by_type"]["25"], 1)
    check("两天前 hotkey 来源", cd[day2]["by_source"]["hotkey"], 1)
    # 关闭（minutes=0）不计入：直接调 log_countdown(0) 应被忽略
    log_countdown(0, "menu", db)
    cd2 = report._collect_countdown(db, 30)
    check("关闭(0)不计入总次数", cd2[today]["total"], 4)

    print("\n== 老库（5 列）也能出报告 ==")
    old = tmp / "old.db"
    with sqlite3.connect(old) as conn:
        conn.execute("CREATE TABLE minutes(minute_ts INTEGER PRIMARY KEY, keystrokes INTEGER,"
                     " backspaces INTEGER, modifiers INTEGER, active_secs INTEGER)")
        ts = int(datetime.now().replace(second=0, microsecond=0).timestamp())
        conn.executemany("INSERT INTO minutes VALUES(?,?,?,?,?)",
                         [(ts - i * 60, 50, 2, 1, 60) for i in range(20)])
    days_old = report._collect(old, 30)
    check("老库补列后可读", len(days_old), 1)
    check("老库鼠标列补 0", {r[4] for r in list(days_old.values())[0]}, {0})
    # 补列要落盘，不是只改内存
    with sqlite3.connect(old) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(minutes)")]
    check("老库物理列已补齐", cols[-3:], ["mouse_moves", "clicks", "scrolls"])

    print("\n结果：%s（%d 通过 / %d 失败）" % ("全部通过" if not BAD else "有失败", OK, BAD))

    # 留一份样例给前端 harness 跑（_report_js_test.js），下划线前缀是一次性产物
    sample = Path(__file__).resolve().parent / "_report_sample.html"
    sample.write_text(html, encoding="utf-8")
    print("SAMPLE=%s" % sample)
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
