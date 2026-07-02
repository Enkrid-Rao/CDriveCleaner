# Changelog

本文件记录 DiskJunction 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 已完成
- 去硬编码：动态获取用户名/路径（`os.getenv('USERPROFILE')`/`USERNAME`/`TEMP`），支持任意 Windows 环境
- Junction 扫描输出完整 source 路径，前端不再猜路径
- 启动脚本去除 WorkBuddy 私人 Python 路径，改用系统 `python`

### 计划中
- 配置文件 `config.json`：zone 规则、阈值、目标盘符可配置
- 架构重构：拆分 `server.py` 为 `scanner/migrator/admin_ops/config/logger/web_api` 模块
- 安全加固：文件日志、迁移前快照、自动回滚机制
- PyInstaller 打包为单 exe
- GitHub Actions 自动构建

## [4.0.0] - 2026-07-02

### 个人版本（开源化前的最后版本）

这是 DiskJunction 开源化前的基线版本，已在作者电脑上稳定使用并成功迁移 41+ 个 Junction（释放 43+ GB C 盘空间）。

#### 功能
- Web UI 扫描 C 盘大目录，按区域分组显示
- robocopy 复制 + mklink /J 创建 NTFS Junction
- UAC 自动提权：生成 .bat 脚本并调用 ShellExecute 触发管理员权限
- 一键撤销：回迁数据到 C 盘并删除 Junction
- 进程检查：迁移前检测目标程序是否运行
- 临时 PowerShell 脚本获取磁盘容量信息

#### 已知限制（开源化待解决）
- 硬编码用户名 `C:\Users\raoxi`
- 启动脚本写死 WorkBuddy 私人 Python 路径
- 无持久化日志，无迁移前快照
- 单文件 781 行，未模块化
- 无配置文件，zone 规则写死在代码里
- `scan.ps1` 文件损坏（变量名丢失，运行时动态生成替代）
