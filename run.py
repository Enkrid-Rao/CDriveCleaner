"""CDriveCleaner 启动入口（PyInstaller 打包用）。"""

from cdc.app import main

if __name__ == "__main__":
    raise SystemExit(main())
