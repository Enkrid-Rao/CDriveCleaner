# Changelog

本文件记录 CDriveCleaner 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 已完成
- 去硬编码：动态获取用户名/路径（`os.getenv('USERPROFILE')`/`USERNAME`/`TEMP`），支持任意 Windows 环境
- Junction 扫描输出完整 source 路径，前端不再猜路径
- 启动脚本去除 WorkBuddy 私人 Python 路径，改用系统 `python`
- 配置文件 `config.json`：zone 规则、阈值、端口、Temp 保留天数可配置，支持 `{USERPROFILE}` 占位符
- 架构重构：781 行单文件拆分为 7 个模块（`config/powershell/scanner/migrator/admin_ops/web_api/__main__`）
- 启动方式改为 `python -m src`（包模式，支持相对导入）

### 计划中
- 安全加固：文件日志、迁移前快照、自动回滚机制
- PyInstaller 打包为单 exe
- GitHub Actions 自动构建

## [0.1.0] - 2026-07-02

### 首个开源版本

这是 CDriveCleaner 开源化后的首个版本，基于个人版 v4 重构而来。已在作者电脑上稳定使用并成功迁移 48+ 个 Junction（释放 59+ GB C 盘空间）。

#### 功能
- Web UI 扫描 C 盘大目录，按区域分组显示
- robocopy 复制 + mklink /J 创建 NTFS Junction
- UAC 自动提权：生成 .bat 脚本并调用 ShellExecute 触发管理员权限
- 一键撤销：回迁数据到 C 盘并删除 Junction
- 进程检查：迁移前检测目标程序是否运行
- 临时 PowerShell 脚本获取磁盘容量信息

#### 已知限制（后续版本解决）
- 无持久化日志，无迁移前快照
- 暂无 PyInstaller 打包的 exe 分发版
