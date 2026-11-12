"""CDriveCleaner_web 启动入口（PyInstaller 打包用）。

与 run.py 同理：PyInstaller 把入口脚本视为顶层模块（无包上下文），
直接用 src/web_main.py 作入口会导致相对导入失败。
通过 run_web.py 中转导入 src 包，web_main.py 就能正确获得包上下文。
"""

from src.web_main import main

if __name__ == "__main__":
    main()
