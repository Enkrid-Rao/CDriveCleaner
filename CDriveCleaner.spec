# CDriveCleaner.spec
# PyInstaller 打包配置
# 用法: python build_helper.py
#
# 产物：dist/CDriveCleaner.exe（单文件，含 PySide6 GUI）
# 体积约 80-120MB（PySide6 本身较大，已排除 Qt3D/Qml/WebEngine 等）

block_cipher = None

a = Analysis(
    ['run.py'],                             # 入口（中转导入 src 包，避免相对导入失败）
    pathex=['.'],                           # 模块搜索路径
    binaries=[],
    datas=[
        ('web/index.html', 'web'),          # Web 模式备用（--web 参数）
        ('config.json', '.'),               # 默认配置
        ('assets/CDriveCleaner.ico', 'assets'),  # 应用图标
    ],
    hiddenimports=[
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'src.gui',
        'src.gui_styles',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',                           # 排除不需要的大模块，减小体积
        'unittest',
        'pydoc',
        'test',
        'PySide6.Qt3D',                      # 排除 PySide6 用不到的大模块
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
    name='CDriveCleaner',
    console=False,                          # GUI 模式无控制台窗口（Web 模式调试可改 True）
    icon='assets/CDriveCleaner.ico',
    onefile=True,                            # 打成单 exe
    upx=True,                                # UPX 压缩减小体积
    upx_exclude=[
        # PySide6 / Qt 的 dll 被 UPX 压缩后可能加载失败，排除压缩
        'Qt6Core.dll',
        'Qt6Gui.dll',
        'Qt6Widgets.dll',
        'Qt6OpenGL.dll',
        'Qt6OpenGLWidgets.dll',
        'shiboken6.abi3.dll',
        'python3.dll',
        'vcruntime140.dll',
        'vcruntime140_1.dll',
    ],
)

