"""CDriveCleaner v2 —— C 盘瘦身与冷数据归档。

模块划分：
  cdc.core  纯业务逻辑，不依赖 Qt，可单独测试 / 在提权 helper 中运行
  cdc.ui    PySide6 桌面界面
"""

from .version import __version__

__all__ = ["__version__"]
