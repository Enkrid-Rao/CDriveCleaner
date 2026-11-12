# v1 源码归档

这里是 CDriveCleaner v1（`src/` 单页 GUI + Web 服务模式 + PyInstaller onefile）的完整源码与
配置备份，**仅用于回溯，不参与 v2 构建与发布**。

v2 已完全替换为：

- `cdc/`：core + PySide6 UI
- `packaging/`：onedir + 便携版 + Inno Setup 安装包
- `tests/`：真实临时目录与 Junction 测试

保留原因：v1 有未提交的本地改动（设置页、窗口缩放、Web 模式），归档在这里避免丢失。
`legacy/v1/tools/` 还保留了早期一次性数据重组脚本（`reorganize_cdrive.py` /
`migrate_userlibs.py` / `migrate_to_e.py`），v2 已用归档功能取代。
