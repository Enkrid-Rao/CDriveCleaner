# CDriveCleaner.spec
# PyInstaller 打包配置
# 用法: pyinstaller CDriveCleaner.spec

block_cipher = None

a = Analysis(
    ['run.py'],                             # 入口（中转导入 src 包，避免相对导入失败）
    pathex=['.'],                           # 模块搜索路径
    binaries=[],
    datas=[
        ('web/index.html', 'web'),          # 前端文件打包到 web/ 目录
        ('config.json', '.'),               # 默认配置打包到根目录
    ],
    hiddenimports=[],                        # 暂时不需要隐藏导入
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',                           # 排除不需要的大模块，减小体积
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
    name='CDriveCleaner',
    console=True,                            # 保留控制台（能看到日志）
    icon='assets/CDriveCleaner.ico',
    onefile=True,                            # 打成单 exe
    upx=True,                                # UPX 压缩减小体积
)
