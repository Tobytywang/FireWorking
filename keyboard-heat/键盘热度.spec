# -*- mode: python ; coding: utf-8 -*-
# 产物文件名从 version.py 取（**唯一数据源**），带上版本号：键盘热度-v1.2.0.exe
#   带版本号是为了防止混淆：开发期反复打包，旧产物可能带已知缺陷，
#   文件名不带版本时根本分不清手上跑的是哪一份。
# 改版本号只需改 version.py 的 VERSION，本文件不用动。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath('.')))
from version import exe_name

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('config.json', '.'), ('report_template.html', '.'), ('assets', 'assets')],
    hiddenimports=['report', 'overlay', 'overlay_tk', 'heatcore', 'version'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name(),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
