CDriveCleaner 便携版
====================

1. 解压整个文件夹到任意位置（不要只复制 exe，程序需要同目录的 _internal）。
2. 双击 CDriveCleaner.exe 启动。
3. 本目录下的 data\ 保存配置、审计记录与日志；整个文件夹可以随 U 盘移动。

注意
----
- 这是「便携版」：不会写注册表，也不会安装开始菜单项。
- 迁移 / 归档需要访问文件系统；ProgramData、Program Files 会按需弹出 UAC。
- 关闭程序前请确保没有正在复制或校验的任务。

数据位置
--------
data\config.json         配置
data\state\audit.jsonl   操作审计
data\state\cache\        扫描缓存
data\logs\               运行日志

安全
----
本工具会移动文件并创建 NTFS Junction。虽然内置清单校验、失败回滚与审计，
仍建议在重要操作前备份数据。详见 README.md。
