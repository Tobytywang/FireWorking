"""把 SQLite 里的分钟级数据渲染成单文件 HTML 报告。

两个刻意的取舍：

1. 不用 CDN。办公网络经常没有外网，图表全部手写 Canvas，报告双击就能看，
   既不依赖网络也不依赖本地起 server。
2. 数据内联进 HTML，不写成外链 JSON。因为 file:// 协议下 fetch() 会被
   CORS 拦掉，双击打开只会看到空白页。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from heatcore import PROJECT_DIR, RES_DIR, cfg_get, ensure_schema

TEMPLATE_PATH = RES_DIR / "report_template.html"

DATA_SLOT = "__DATA_JSON__"
META_SLOT = "__META_JSON__"
COUNTDOWN_SLOT = "__COUNTDOWN_JSON__"

# 倒计时的类型（时长，分钟）。超过 30 天的统计窗口里不会冒出别的档位，但写成
# 白名单能让模板的「按类型」横条永远对齐，不出现的类型也显示 0。
COUNTDOWN_TYPES = (5, 10, 25)
COUNTDOWN_SOURCE_LABELS = {
    "menu": "托盘菜单",
    "single_click": "单击快速开始",
    "double_click": "双击快速开始",
    "hotkey": "热键",
}


def _collect(db_path: Path, keep_days: int):
    """读取最近 keep_days 天，按本地日期分组。

    返回 {"YYYY-MM-DD": [[minute_of_day, keys, backspaces, active_secs,
                          mouse_moves, clicks, scrolls], ...]}
    7 个字段与落库 schema 一一对应，不引入任何内容型数据。
    """
    cutoff = int((datetime.now() - timedelta(days=keep_days)).timestamp())
    days: dict[str, list] = {}

    if not db_path.exists():
        return days

    conn = sqlite3.connect(db_path)
    try:
        # 老库只有 5 列，先补列再查 —— 否则 SELECT 鼠标列直接报 no such column。
        # 报告是独立运行的（不一定有采集进程在跑），所以这步不能省。
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT minute_ts, keystrokes, backspaces, active_secs, "
            "mouse_moves, clicks, scrolls FROM minutes "
            "WHERE minute_ts >= ? ORDER BY minute_ts",
            (cutoff,),
        ).fetchall()
    except sqlite3.OperationalError:
        return days
    finally:
        conn.close()

    for ts, keys, bs, active, mv, ck, sc in rows:
        if keys <= 0 and bs <= 0 and active <= 0 and mv <= 0 and ck <= 0 and sc <= 0:
            continue
        dt = datetime.fromtimestamp(ts)
        day = dt.strftime("%Y-%m-%d")
        mod = dt.hour * 60 + dt.minute
        days.setdefault(day, []).append(
            [mod, int(keys), int(bs), int(active), int(mv), int(ck), int(sc)]
        )

    return days


def _collect_countdown(db_path: Path, keep_days: int):
    """读取最近 keep_days 天里每次倒计时开始，按本地日期 + 类型聚合。

    返回 {"YYYY-MM-DD": {"total": int, "by_type": {"5": n,"10": n,"25": n},
                         "by_source": {"menu": n, ...}}}。

    by_type 永远包含白名单里的三种时长（没有就 0），模板横条才能对齐；
    by_source 只列实际出现过的来源。和 minutes 一样，老库没有这张表时
    ensure_schema 会补建，读不到就返回空 dict，不影响其它统计。
    """
    cutoff = int((datetime.now() - timedelta(days=keep_days)).timestamp())
    days: dict[str, dict] = {}

    if not db_path.exists():
        return days

    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT ts, minutes, source FROM countdown_log "
            "WHERE ts >= ? ORDER BY ts",
            (cutoff,),
        ).fetchall()
    except sqlite3.OperationalError:
        return days
    finally:
        conn.close()

    for ts, minutes, source in rows:
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        d = days.get(day)
        if d is None:
            d = {"total": 0,
                 "by_type": {str(t): 0 for t in COUNTDOWN_TYPES},
                 "by_source": {}}
            days[day] = d
        d["total"] += 1
        key = str(int(minutes))
        d["by_type"][key] = d["by_type"].get(key, 0) + 1
        d["by_source"][source] = d["by_source"].get(source, 0) + 1

    return days


def generate(config, db_path=None, output=None, open_after=False):
    """生成报告，返回输出文件路径。"""
    report_cfg = config.get("report", {})
    keep_days = int(cfg_get(report_cfg, "keep_days", 120))

    if db_path is None:
        db_path = PROJECT_DIR / cfg_get(config.get("storage", {}), "db_path", "data/heat.db")
    db_path = Path(db_path)

    out = Path(output or cfg_get(report_cfg, "output", "data/heat-report.html"))
    if not out.is_absolute():
        out = PROJECT_DIR / out
    out.parent.mkdir(parents=True, exist_ok=True)

    days = _collect(db_path, keep_days)
    countdown = _collect_countdown(db_path, keep_days)
    ordered = sorted(days)

    if ordered:
        rng = ordered[0] if len(ordered) == 1 else "%s ~ %s" % (ordered[0], ordered[-1])
    else:
        rng = ""

    meta = {
        "range": rng,
        "last_day": ordered[-1] if ordered else "",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "days": len(ordered),
    }

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError("报告模板缺失：%s" % TEMPLATE_PATH)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if DATA_SLOT not in template or META_SLOT not in template:
        raise ValueError("报告模板里找不到 %s / %s 占位符" % (DATA_SLOT, META_SLOT))

    html = (
        template
        .replace(DATA_SLOT, json.dumps(days, ensure_ascii=False, separators=(",", ":")))
        .replace(META_SLOT, json.dumps(meta, ensure_ascii=False, separators=(",", ":")))
        .replace(COUNTDOWN_SLOT,
                 json.dumps(countdown, ensure_ascii=False, separators=(",", ":")))
    )
    out.write_text(html, encoding="utf-8")

    if open_after:
        import os
        os.startfile(str(out))          # noqa: S606

    return out


def main():
    import argparse
    from heatcore import load_config

    ap = argparse.ArgumentParser(description="生成键盘热度 HTML 报告")
    ap.add_argument("--open", action="store_true", help="生成后用浏览器打开")
    ap.add_argument("--out", help="输出路径")
    ap.add_argument("--db", help="数据库路径（默认用 config.json 里的）")
    args = ap.parse_args()

    path = generate(load_config(), db_path=args.db, output=args.out, open_after=args.open)
    size_kb = path.stat().st_size / 1024
    print("报告已生成：%s （%.0f KB）" % (path, size_kb))


if __name__ == "__main__":
    main()
