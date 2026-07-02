# DiskJunction 开源化规划

> 把个人脚本「C盘瘦身助手 v4」变成可公开发布的 Windows 开源工具。
>
> 本文件是执行的纲领，每个 Phase 完成后勾选并更新状态。

---

## 1. 项目定位

| 项 | 内容 |
|---|---|
| 工具名 | **DiskJunction**（暂定，可改） |
| 一句话定位 | 用 NTFS Junction 把 C 盘大目录无损迁移到 D 盘，释放系统盘空间 |
| 核心机制 | robocopy 复制 → 校验 → 删原目录 → mklink /J 创建 Junction（可撤销） |
| 目标用户 | Windows 10/11 用户，C 盘空间紧张，不想重装系统 |
| 区别于普通清理工具 | 不删数据，只搬位置；应用无感知；可一键回迁 |
| 协议 | MIT |
| 分发 | PyInstaller 单 exe + GitHub Release |
| 仓库 | GitHub 公开 |

## 2. 现状诊断（基线）

当前项目 = 历史目录 `c-drive-tool` 的副本，v4 已能稳定工作（2026-07-02 13:17 成功迁移 JetBrains 16GB）。

**阻断开源的硬伤**：

| 严重度 | 问题 | 位置 |
|---|---|---|
| P0 | 硬编码用户名 `C:\Users\raoxi` | server.py:15,319,415,580 / index.html:537-542 |
| P0 | 启动.bat 写死 WorkBuddy 私人 Python 3.13.12 路径 | 启动.bat:13 |
| P1 | scan.ps1 变量名丢失（坏文件，靠运行时重写 _temp_script.ps1 才不报错） | scan.ps1 |
| P1 | 未 git init，无 README/LICENSE/.gitignore | 项目根 |
| P2 | 无配置文件、无持久化日志、无回滚机制 | 架构层 |

## 3. 技术决策记录

| 决策 | 选择 | 理由 |
|---|---|---|
| 开源协议 | MIT | 最宽松最流行，利于传播 |
| 打包方式 | PyInstaller 单 exe | 用户零依赖，双击即用 |
| 代码托管 | GitHub | Actions CI 免费，国际可见度 |
| 命名 | DiskJunction（纯英文） | 体现核心机制，国际化 |
| 后端语言 | Python（保持现状） | 已有成熟代码，不重写 |
| 前端 | 原生 HTML/JS（保持现状） | 单文件易打包，无需构建链 |
| 外部依赖 | 仅 Python 标准库 | 降低打包体积和供应链风险 |

## 4. 六阶段路线图

### Phase 0 · 项目骨架
**目标**：散装文件 → 正规项目。不动业务代码。

- [ ] `git init` + 首次提交（保留当前可工作版本作为 baseline）
- [ ] 建立目录结构：
  ```
  DiskJunction/
    src/              # Python 源码（Phase 2 拆分后填入）
    web/              # 前端资源
    scripts/          # 构建/打包脚本
    tests/            # 测试
    docs/             # 文档与截图
    .github/          # CI + Issue 模板（Phase 5 填入）
  ```
- [ ] LICENSE (MIT)
- [ ] README.md（中文为主，含截图占位、功能、用法、原理、风险声明）
- [ ] .gitignore（Python + Windows + PyInstaller + _temp_script.ps1 + _admin_result_*.txt + __pycache__）
- [ ] CHANGELOG.md
- [ ] requirements.txt（当前为空或仅标注"仅标准库"）
- [ ] 把现有 5 个文件归位到 src/ 和 web/，保持可运行

**验收**：`git log` 有 baseline 提交；目录结构清晰；README 能让人 30 秒看懂这工具干啥。

### Phase 1 · 去硬编码（最关键）
**目标**：让工具能在任何 Windows 用户电脑跑。不做这步开源出来等于发废品。

- [ ] `server.py` `BASE_USER` → `os.getenv('USERPROFILE')`
- [ ] `server.py:319,415` `icacls /grant "raoxi:F"` → `os.getenv('USERNAME')`
- [ ] `server.py:580` Temp 路径 → `tempfile.gettempdir()` 或 `%TEMP%`
- [ ] `index.html:537-542` `getJunctionSource()` 硬编码用户名 → 后端返回完整路径，前端不猜
- [ ] `启动.bat` 去掉 WorkBuddy Python 路径 → 自适应（优先 exe，其次系统 python，最后提示）
- [ ] 修复 `scan.ps1`（当前变量名全丢，是损坏文件）—— 实际可删除，因 server.py 运行时动态生成 `_temp_script.ps1`
- [ ] 引入 `config.json`：
  ```json
  {
    "threshold_mb": 100,
    "target_drive": "D",
    "dest_base": "AppData",
    "zones": { ... },
    "no_go": { ... }
  }
  ```
- [ ] 所有 zone 配置（source/dest_base/no_go）从代码搬到 config.json
- [ ] 首次运行自动生成默认 config.json（如果不存在）

**验收**：换一台电脑（或换用户名）能直接跑，无需改任何代码。

### Phase 2 · 架构重构
**目标**：781 行单文件 → 清晰模块。可测试、可维护。

- [ ] 拆分 `server.py`：
  ```
  src/
    scanner.py      # 扫描逻辑 + PowerShell 调用
    migrator.py     # 迁移/撤销/Junction 逻辑
    admin_ops.py    # UAC 提权 + bat 生成
    config.py       # 配置加载与默认值
    logger.py       # 日志
    web_api.py      # HTTP server（瘦身后只剩路由分发）
    models.py       # 数据类 + 类型注解
    __main__.py     # 入口（python -m diskjunction）
  ```
- [ ] `index.html` → `web/index.html`
- [ ] 全量类型注解（Python 3.10+ 风格）
- [ ] ruff 配置 + mypy 配置
- [ ] pytest 测试骨架（mock subprocess，不真跑 robocopy）
- [ ] 包结构：`pyproject.toml`，可 `pip install -e .`

**验收**：`ruff check` 零警告；`pytest` 通过；`python -m diskjunction` 能启动。

### Phase 3 · 安全加固
**目标**：动文件系统的工具，可靠性是底线。回应操作安全红线。

- [ ] **文件日志**：每次操作写 `logs/diskjunction_YYYYMMDD.log`（不只是前端显示）
- [ ] **迁移前快照**：记录源目录文件清单 + 总大小到 `logs/snapshots/`，失败时可比对
- [ ] **回滚机制**：Junction 创建失败时自动回退（已复制到 D 盘的数据保留，重建 C 盘原目录）
- [ ] **权限最小化**：`icacls /grant X:F` → `:(OI)(CI)F` 继承，或按需细化
- [ ] **二次确认**：高危操作（ProgramData/Program Files）前端弹窗 + 后端校验双重
- [ ] **操作审计**：每次迁移/撤销记录到 `logs/audit.jsonl`（时间、路径、大小、结果、操作人）
- [ ] **进程检查加固**：当前 `process_aliases` 列表太窄，改成扫描目录名模糊匹配 + 提示用户确认

**验收**：模拟迁移失败能自动回滚；日志可追溯任一操作的完整链路。

### Phase 4 · 打包分发
**目标**：用户双击 exe 即用，不用装 Python。

- [ ] PyInstaller spec 文件（`--onefile --windowed --name DiskJunction`）
- [ ] 前端资源用 `--add-data` 打包
- [ ] 图标设计（.ico）
- [ ] GitHub Actions workflow：push tag `v*` 时自动构建 Windows exe
- [ ] Release 自动打包：`DiskJunction-vX.Y.Z.zip`（含 exe + README）
- [ ] 版本号语义化（SemVer），版本写入 `__version__.py`
- [ ] 启动时检查单实例（避免端口 8765 冲突）

**验收**：在干净 Windows 上下载 zip → 解压 → 双击 exe → 浏览器自动打开 UI。

### Phase 5 · 开源治理
**目标**：社区可参与、可贡献、可上报问题。

- [ ] `.github/ISSUE_TEMPLATE/bug_report.md`
- [ ] `.github/ISSUE_TEMPLATE/feature_request.md`
- [ ] `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] `CONTRIBUTING.md`（开发环境、提交规范、PR 流程、代码风格）
- [ ] `SECURITY.md`（安全漏洞上报方式——这工具动文件系统，必须有）
- [ ] `CODE_OF_CONDUCT.md`
- [ ] README 中英双语（中文详版 + 英文摘要段）
- [ ] GitHub Actions CI：PR 触发 ruff + mypy + pytest
- [ ] README 徽章（CI status / license / version / downloads）

**验收**：陌生人 clone 仓库后，按 README 能跑起来；按 CONTRIBUTING 能提 PR。

## 5. 目标目录结构（Phase 2 完成后）

```
DiskJunction/
  .github/
    workflows/ci.yml
    ISSUE_TEMPLATE/
    PULL_REQUEST_TEMPLATE.md
  docs/
    screenshots/
    architecture.md
  scripts/
    build.spec
    build.bat
  src/
    __init__.py
    __main__.py
    scanner.py
    migrator.py
    admin_ops.py
    config.py
    logger.py
    web_api.py
    models.py
  web/
    index.html
  tests/
    test_scanner.py
    test_migrator.py
    test_config.py
  .gitignore
  .ruff.toml
  pyproject.toml
  LICENSE
  README.md
  README_EN.md
  CHANGELOG.md
  CONTRIBUTING.md
  SECURITY.md
  CODE_OF_CONDUCT.md
  requirements.txt
```

## 6. 风险与红线

| 风险 | 应对 |
|---|---|
| 迁移中数据丢失（历史教训：dest_exists 跳过 robocopy） | v4 已修复（强制 robocopy）；Phase 3 加快照+回滚 |
| Junction 误删导致数据永久丢失 | 删除前校验 D 盘数据完整性；撤销时先校验再删 Junction |
| ProgramData/Program Files 操作需管理员 | UAC 自动提权（v4 已实现）+ Phase 3 加二次确认 |
| 用户在应用运行时迁移 | 进程检查（v4 已实现）+ Phase 3 加固模糊匹配 |
| exe 被杀软误报 | PyInstaller 签名（可选代码签名证书）；README 说明 |
| 端口 8765 冲突 | 启动时检测，冲突则自动找空闲端口 |

**绝对红线**（来自用户操作安全规范）：
- 任何 `rd /s /q`、`del /f` 类不可逆操作前，必须有可验证的备份/快照
- 复制失败时绝不删除原目录
- 解释"会怎样"之后必须读代码确认，话和代码不一致是最大隐患

## 7. 待定项

- [ ] 工具最终英文名确认（暂定 DiskJunction）
- [ ] 是否需要多语言切换（中/英 UI）
- [ ] 是否支持迁移到 D 盘以外的盘符（config 可配，但 UI 要不要暴露）
- [ ] 图标设计方向
- [ ] 是否做安装版（NSIS）还是只做绿色版

## 8. 执行原则

- **小步提交**：每个子任务一个 commit，便于回溯
- **先保活后优化**：每个 Phase 结束后必须保证工具能正常跑
- **不破坏现有迁移**：已迁移的 41+ Junction 不能因重构失效
- **文档同步**：代码改了 README 同步改，不留过期文档
