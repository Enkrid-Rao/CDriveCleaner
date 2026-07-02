# DiskJunction

> 用 NTFS Junction 把 C 盘大目录无损迁移到 D 盘，释放系统盘空间。
>
> 不删数据，只搬位置。应用无感知，可一键回迁。

<!-- 截图占位：docs/screenshots/main-ui.png -->

## 为什么需要

Windows 用久了 C 盘越来越满——JetBrains、微信、QQ、Steam、各种 IDE 的数据都堆在 `AppData`、`Program Files`、`ProgramData` 里。重装系统太折腾，手动搬家怕搞坏。

DiskJunction 用 Windows 原生的 **NTFS Junction**（目录符号链接）解决这个问题：

1. 把大目录从 C 盘复制到 D 盘
2. 删除 C 盘原目录
3. 在原位置创建 Junction 指向 D 盘

应用以为文件还在 C 盘，实际读写的是 D 盘。零感知、可撤销。

## 功能特性

- **扫描分析**：一键扫描 C 盘大目录，按区域分组（用户数据 / 程序文件 / 系统数据）
- **Junction 迁移**：robocopy 复制 + 校验 + mklink 创建 Junction，支持 UAC 自动提权
- **一键撤销**：已迁移的目录可回迁到 C 盘，删除 Junction
- **进程检查**：迁移前检测目标程序是否运行，避免文件占用
- **Web UI**：浏览器操作，不装客户端，localhost 自闭环

## 快速开始

### 方式一：下载 exe（推荐普通用户）

1. 前往 [Releases](../../releases) 下载最新版
2. 解压双击 `DiskJunction.exe`
3. 浏览器自动打开 `http://localhost:8765`

### 方式二：源码运行（开发者）

```bash
git clone https://github.com/raoxi/DiskJunction.git
cd DiskJunction
python src/server.py
```

需要 Python 3.10+，仅依赖标准库。

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
DiskJunction/
  src/
    server.py        # HTTP 后端 + 扫描/迁移/撤销逻辑
  web/
    index.html       # 前端 UI (自包含, 无构建依赖)
  启动.bat           # Windows 启动入口
```

> 当前处于开源化重构早期（Phase 0），代码尚未模块化。完整架构见 [PLAN.md](PLAN.md)。

### 本地开发

```bash
# 启动开发服务器
python src/server.py

# 访问 UI
# http://localhost:8765
```

### 贡献

欢迎提 Issue 和 PR。开发前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)（待添加）。

## 路线图

- [x] Phase 0: 项目骨架与开源化基础
- [ ] Phase 1: 去硬编码，支持任意用户环境
- [ ] Phase 2: 架构重构与模块化
- [ ] Phase 3: 安全加固（日志/快照/回滚）
- [ ] Phase 4: PyInstaller 打包与 CI
- [ ] Phase 5: 开源治理与文档完善

详见 [PLAN.md](PLAN.md)。

## 许可证

[MIT](LICENSE)
