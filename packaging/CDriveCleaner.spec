# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 打包配置（安装版与便携版共用）。

产物：dist/CDriveCleaner/CDriveCleaner.exe
用法：python -m PyInstaller --noconfirm --clean packaging/CDriveCleaner.spec
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(ROOT, "assets", "CDriveCleaner.ico")
VERSION_FILE = os.path.join(ROOT, "packaging", "version_info.txt")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (ICON, "assets"),
    ],
    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtSvg",
        "PySide6.QtNetwork",
        "cdc.app",
        "cdc.core.applog",
        "cdc.core.config",
        "cdc.core.jobs",
        "cdc.core.operations",
        "cdc.core.scanner",
        "cdc.core.windows",
        "cdc.ui.window",
        "cdc.ui.pages.dashboard",
        "cdc.ui.pages.slimming",
        "cdc.ui.pages.archive",
        "cdc.ui.pages.links",
        "cdc.ui.pages.history",
        "cdc.ui.pages.settings",
        "cdc.ui.single_instance",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "unittest", "pydoc", "test",
        "PySide6.Qt3D", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia", "PySide6.QtOpenGL", "PySide6.QtQml",
        "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets", "PySide6.QtXml",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtPrintSupport",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSerialBus",
        "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    ],
    cipher=None,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CDriveCleaner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CDriveCleaner",
)
