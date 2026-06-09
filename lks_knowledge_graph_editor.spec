# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('lks_utils.gui_qt.canvas2d')
datas += collect_data_files('lks_utils.gui_qt')
datas += collect_data_files('lks_utils.input')
datas += collect_data_files('lks_utils.knowledge')
datas += collect_data_files('lks_utils.knowledge.ui')


a = Analysis(
    ['src\\lks_utils\\knowledge\\demo\\demo_workbench_ui_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['_cffi_backend'],
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
    name='lks_knowledge_graph_editor',
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
