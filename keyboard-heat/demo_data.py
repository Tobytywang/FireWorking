"""生成一份逼真的演示数据，用来先看报告长什么样。

写进独立的 data/demo.db，不碰真实的 data/heat.db，随时可以删。

模拟的作息：
    - 工作日  上午 9:00-12:00、下午 13:30-18:30 两个工作块
    - 午休    12:00-13:30 明显低谷
    - 晚上    20:00-22:00 偶发零星输入
    - 周末    六成概率下午有一段轻量活动
两个关键细节让它看着不像随机数：
    - "打字是分段的"：连续几分钟高速输出，然后若干分钟完全为 0。
      均匀铺开的数据看着假，也测不出报告里"工作块"的可读性。
    - "键鼠是交替的"：22% 的分钟是纯浏览 —— 一个键不敲、鼠标移动几百上千。
      这样报告里的鼠标占比、柱内琥珀段才有东西可看。
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from heatcore import PROJECT_DIR, SCHEMA


def _blocks_for(rng, is_weekday):
    """返回当天的工作块列表 [[起, 止), ...]，单位是"当天第几分钟"。"""
    blocks = []
    if is_weekday:
        blocks.append([9 * 60 + rng.randint(-25, 40), 12 * 60 + rng.randint(-40, 15)])
        blocks.append([13 * 60 + rng.randint(-10, 40), 18 * 60 + rng.randint(-70, 70)])
        if rng.random() < 0.35:
            blocks.append([20 * 60 + rng.randint(0, 60), 22 * 60 + rng.randint(-60, 30)])
    else:
        if rng.random() < 0.6:
            a = rng.randint(13 * 60, 16 * 60)
            blocks.append([a, a + rng.randint(60, 240)])
    return [[max(0, s), min(1439, e)] for s, e in blocks if e > s]


def _minutes_for_block(rng, block):
    """块内逐分钟生成 7 个字段。

    block 是 [起, 止) 两元素序列。刻意收成单个参数而不是 (start, end)，
    因为调用侧是遍历块列表，拆成两个参数很容易被 *_blocks_for(...) 的展开
    悄悄凑满位置参数，把一个 list 塞进 start 里（报错还会指向无关的行）。

    这里有两类分钟，混在一起才像真的：
      打字分钟 —— 手在键盘上，鼠标只偶尔碰一下（moves ≈ keys 的 1~4 倍）
      浏览分钟 —— 手在鼠标上，一个键都不敲（22% 概率，moves 几百到上千）
    返回 [(minute_of_day, keys, backspaces, active_secs, moves, clicks, scrolls)]。
    """
    start, end = block
    rows = []
    minute = start
    speed = rng.uniform(0.75, 1.35)         # 这个人的"当日手速系数"

    while minute < end:
        # 连续输出的长度：短则 1-3 分钟，长则一次性冲刺 10-25 分钟
        burst = rng.randint(2, 22) if rng.random() < 0.45 else rng.randint(1, 4)
        for _ in range(burst):
            if minute >= end:
                break

            if rng.random() < 0.22:          # 浏览 / 阅读文档的那一分钟
                rows.append((
                    minute, 0, 0, min(60, int(rng.uniform(25, 60))),
                    int(rng.uniform(180, 1500)), rng.randint(0, 9), rng.randint(0, 34),
                ))
                minute += 1
                continue

            base = rng.gauss(135 * speed, 52)
            if rng.random() < 0.07:          # 少量高强度分钟，把色阶顶到红色
                base *= rng.uniform(1.7, 2.7)
            keys = max(0, int(base))
            bs = int(keys * rng.uniform(0.04, 0.19))
            active = min(60, int(keys * rng.uniform(0.5, 0.75)))
            rows.append((
                minute, keys, bs, active,
                int(keys * rng.uniform(0.5, 4.0)),   # 打字时间歇性扶一下鼠标
                rng.randint(0, 3), rng.randint(0, 6),
            ))
            minute += 1

        # 停顿：倒水、开会、看文档
        minute += rng.choice([0, 1, 2, 3, 5, 8, 13, 21])
    return rows


def generate(days=70, out=None, seed=20260922):
    rng = random.Random(seed)
    out = Path(out or PROJECT_DIR / "data" / "demo.db")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    conn = sqlite3.connect(out)
    conn.executescript(SCHEMA)

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    payload = []

    for back in range(days, -1, -1):
        day = today - timedelta(days=back)
        if day.weekday() >= 5 and rng.random() < 0.4:
            continue                                    # 周末四成完全休息
        base = int(day.timestamp())
        for block in _blocks_for(rng, day.weekday() < 5):
            for minute, keys, bs, active, mv, ck, sc in _minutes_for_block(rng, block):
                payload.append((base + minute * 60, keys, bs, active, mv, ck, sc))

    conn.executemany(
        "INSERT INTO minutes(minute_ts,keystrokes,backspaces,modifiers,active_secs,"
        "mouse_moves,clicks,scrolls) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(minute_ts) DO UPDATE SET "
        "keystrokes=excluded.keystrokes, backspaces=excluded.backspaces, "
        "active_secs=excluded.active_secs, mouse_moves=excluded.mouse_moves, "
        "clicks=excluded.clicks, scrolls=excluded.scrolls",
        [(ts, k, b, int(k * 0.12), a, mv, ck, sc)
         for ts, k, b, a, mv, ck, sc in payload],
    )
    conn.commit()
    conn.close()

    total_keys = sum(r[1] for r in payload)
    total_mv = sum(r[4] for r in payload)
    total_ck = sum(r[5] for r in payload)
    browse = sum(1 for r in payload if r[1] == 0 and r[4] > 0)
    print("演示数据已生成：%s" % out)
    print("  %d 天 / %d 个活跃分钟（其中 %d 个纯鼠标浏览）" % (days + 1, len(payload), browse))
    print("  共 %s 次击键 / %s 次鼠标移动 / %s 次点击"
          % (format(total_keys, ","), format(total_mv, ","), format(total_ck, ",")))
    return out


def main():
    ap = argparse.ArgumentParser(description="生成键盘热度演示数据")
    ap.add_argument("--days", type=int, default=70, help="生成多少天，默认 70")
    ap.add_argument("--out", help="输出数据库路径，默认 data/demo.db")
    args = ap.parse_args()
    generate(args.days, args.out)


if __name__ == "__main__":
    main()
