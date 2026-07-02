"""CDriveCleaner 启动入口（PyInstaller 打包用）。

这个文件存在的唯一原因：PyInstaller 把入口脚本视为顶层模块（无包上下文），
如果直接用 src/__main__.py 作入口，里面的相对导入 `from .config import` 会失败。
通过 run.py 中转导入 src 包，__main__.py 就能正确获得包上下文。
"""

from src.__main__ import main

if __name__ == "__main__":
    main()
