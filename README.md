# CDriveCleaner

> 用 NTFS Junction 把 C 盘大目录无损迁移到 D 盘，释放系统盘空间。
>
> 不删数据，只搬位置。应用无感知，可一键回迁。

<!-- 截图占位：docs/screenshots/main-ui.png -->

## 为什么需要

Windows 用久了 C 盘越来越满——JetBrains、微信、QQ、Steam、各种 IDE 的数据都堆在 `AppData`、`Program Files`、`ProgramData` 里。重装系统太折腾，手动搬家怕搞坏。

CDriveCleaner 用 Windows 原生的 **NTFS Junction**（目录符号链接）解决这个问题：

1. 把大目录从 C 盘复制到 D 盘
2. 删除 C 盘原目录
3. 在原位置创建 Junction 指向 D 盘

应用以为文件还在 C 盘，实际读写的是 D 盘。零感知、可撤销。

## 功能特性

- **原生桌面 GUI**：基于 PySide6 的 Windows 桌面程序，双击即用，无需浏览器、无需 localhost 访问
- **扫描分析**：一键扫描 C 盘大目录，按区域分组（用户数据 / 程序文件 / 系统数据）
- **Junction 迁移**：robocopy 复制 + 校验 + mklink 创建 Junction，支持 UAC 自动提权
- **一键撤销**：已迁移的目录可回迁到 C 盘，删除 Junction
- **进程检查**：迁移前检测目标程序是否运行，避免文件占用
- **操作日志**：底部彩色日志面板实时记录扫描 / 迁移 / 撤销 / 清理 Temp 等任务进度，并按天自动落盘到 `logs/`，关闭重开仍可查看历史
- **折叠分区**：「已迁移到 D 盘」区与「操作日志」面板均可点击标题栏折叠 / 展开，长列表不再占用空间
- **中英分字体**：英文走 JetBrains Mono 等宽字体，中文自动回退微软雅黑，数字对齐不抖动

## 快速开始

### 方式一：下载 exe（推荐普通用户）

1. 前往 [Releases](https://github.com/Enkrid-Rao/CDriveCleaner/releases) 下载最新版
2. 解压后双击 `CDriveCleaner.exe`
3. 直接弹出桌面 GUI 窗口，即可开始扫描 / 迁移（**无需浏览器，无 localhost 访问**）

> 日志文件会自动写在 `CDriveCleaner.exe` 同级的 `logs/` 目录下，方便排查问题。

### 方式二：源码运行（开发者）

```bash
git clone https://github.com/Enkrid-Rao/CDriveCleaner.git
cd CDriveCleaner
pip install PySide6          # 桌面 GUI 依赖
python -m src               # 默认启动桌面 GUI
# python -m src --web       # 可选：旧版浏览器模式 (http://localhost:PORT)
```

- 桌面 GUI 模式需要 **Python 3.10+** 与 **PySide6**
- 旧版 `--web` 浏览器模式仅依赖标准库（当环境缺少 PySide6 时，GUI 模式会自动回退到此）

## 工作原理

```
迁移前：
  C:\Users\你\AppData\Roaming\JetBrains  (16 GB 实际数据)

迁移后：
  C:\Users\你\AppData\Roaming\JetBrains  → Junction (0 KB)
  D:\AppData\JetBrains                    (16 GB 实际数据)
```

应用读写 `C:\...\JetBrains` 时，NTFS 自动重定向到 `D:\AppData\JetBrains`。对应用完全透明。

## 风险声明

**此工具会移动文件位置并修改文件系统链接。** 虽然已包含校验和回滚机制，但任何文件操作都有风险。

- 迁移前请**关闭相关应用程序**
- 建议**先备份重要数据**
- 不建议迁移正在运行的系统关键目录
- 仅供个人使用，作者不对数据丢失负责

## 开发指南

### 项目结构

```
CDriveCleaner/
  config.json        # 配置文件 (zones/阈值/端口, 支持 {USERPROFILE} 占位符)
  src/
    __init__.py      # 包初始化
    __main__.py      # 入口 (python -m src)，默认桌面 GUI，--web 回退
    _version.py      # 版本号 (唯一真相源)
    config.py        # 配置加载与路径解析
    powershell.py    # PowerShell 执行辅助 (隐藏子进程窗口)
    scanner.py       # 磁盘扫描逻辑
    migrator.py      # 目录迁移与撤销
    admin_ops.py     # UAC 提权与 .bat 生成
    gui.py           # PySide6 原生桌面 GUI (主窗口/卡片/日志面板/折叠)
    gui_styles.py    # GUI 样式表 (QSS 设计令牌 + 动画)
    logger.py        # 操作日志 (单例, 按天落盘 + GUI 面板订阅)
    web_api.py       # [旧版/可选] HTTP API 服务 (--web 模式)
  web/
    index.html       # [旧版/可选] 前端 UI (--web 模式)
  启动.bat           # Windows 启动入口
```

### 本地开发

```bash
pip install PySide6
python -m src               # 启动桌面 GUI (默认)

# 可选：旧版浏览器模式
python -m src --web         # 访问 http://localhost:8765
```

桌面 GUI 模式需要 PySide6；`--web` 旧版模式仅依赖标准库。

### 配置

首次运行自动生成 `config.json`，可自定义：

- `port`: `--web` 浏览器模式的服务端口（默认 8765，**桌面 GUI 不使用**）
- `threshold_mb`: 扫描阈值（默认 100 MB）
- `temp_retention_days`: Temp 清理保留天数（默认 1 天）
- `zones`: 扫描区域配置，source 路径支持 `{USERPROFILE}` 占位符
- `target_drive`: 迁移目标盘符（默认 `D`，**必须带冒号**，如 `D:`）

### 贡献

欢迎提 Issue 和 PR。开发前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)（待添加）。

## 路线图

- [x] Phase 0: 项目骨架与开源化基础
- [x] Phase 1: 去硬编码，支持任意用户环境
- [x] Phase 2: 架构重构与模块化
- [x] Phase 3: 安全加固（操作日志模块已实现；快照 / 回滚待完善）
- [x] Phase 4: PyInstaller 打包与 CI
- [ ] Phase 5: 开源治理与文档完善

详见 [PLAN.md](PLAN.md)。

## 许可证

[MIT](LICENSE)
