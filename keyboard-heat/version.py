# -*- coding: utf-8 -*-
"""版本号的**唯一数据源**。

为什么要有这个文件：打包产物的文件名里要带版本号（`键盘热度-v1.2.0.exe`），
托盘/关于里也想显示版本 —— 两处都写一份必然会漂。所以只在这里定义一次：

- `VERSION`     语义化版本号（改功能就改这里）
- `BUILD_DATE`  打包日期（由 build.py 在打包时自动写入，也可手工填）

`build.py` 读这份文件生成带版本号的 exe；程序里 `overlay.py` 用它填托盘 tooltip。
"""

VERSION = "1.2.0"
BUILD_DATE = "2026-10-15"

# 便捷别名：程序里 `from version import APP_NAME, VERSION` 就能拿到完整标识
APP_NAME = "键盘热度"


def full_version():
    """用于「关于」类展示：名称 + 版本 + 构建日期。"""
    return "%s v%s（构建 %s）" % (APP_NAME, VERSION, BUILD_DATE)


def exe_name():
    """打包产物文件名：键盘热度-v1.2.0.exe

    带版本号是为了**防止混淆**：开发过程中反复打包，旧 exe 里可能带着已知缺陷
    （例如 2026-10-15 之前那份一旦双击就 0xC0000409 秒退），文件名不带版本时
    根本分不清手上跑的是哪一份。
    """
    return "%s-v%s" % (APP_NAME, VERSION)