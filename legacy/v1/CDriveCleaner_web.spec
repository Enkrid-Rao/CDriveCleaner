# CDriveCleaner_web.spec
# PyInstaller 打包配置（Web 服务版，独立程序）
# 用法: python build_helper.py --target web
#
# 产物：dist/CDriveCleaner_web.exe（控制台程序，带终端窗口）
# 关键：不打包 PySide6，体积仅几 MB 量级（桌面 GUI 版约 80-120MB）。
#       Web UI 由浏览器访问 http://localhost:8765，本程序只跑 HTTP 服务。

block_cipher = None

a = Analysis(
    ['run_web.py'],                         # Web 入口（中转导入 src 包）
    pathex=['.'],                           # 模块搜索路径
    binaries=[],
    datas=[
        ('config.json', '.'),               # 默认配置（运行时从 exe 所在目录读取）
        ('web/index.html', 'web'),          # Web UI 前端页面
    ],
    hiddenimports=[
        # 仅 Web 服务链路需要的业务模块，刻意不包含任何 PySide6 模块
        'src.web_api',
        'src.scanner',
        'src.migrator',
        'src.admin_ops',
        'src.config',
        'src.logger',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # 彻底排除 PySide6（体积优化 + 避免 GUI 依赖）
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.Qt3D',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia',
        'PySide6.QtNetwork',
        'PySide6.QtOpenGL',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuick3D',
        'PySide6.QtQuickWidgets',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets',
        'PySide6.QtXml',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtPrintSupport',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtSerialBus',
        'PySide6.QtSpatialAudio',
        'PySide6.QtTextToSpeech',
        # 其他不需要的大模块
        'tkinter',
        'unittest',
        'pydoc',
        'test',
    ],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CDriveCleaner_web',
    console=True,                           # Web 服务：保留终端窗口，可见日志、Ctrl+C 关闭
    icon='assets/CDriveCleaner.ico',
    onefile=True,                            # 打成单 exe
    upx=True,                                # UPX 压缩减小体积
    upx_exclude=[
        # 这些 dll 被 UPX 压缩后可能加载失败，排除压缩
        'python3.dll',
        'vcruntime140.dll',
        'vcruntime140_1.dll',
    ],
)
