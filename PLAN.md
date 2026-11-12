# CDriveCleaner v2 实施计划

> 目标：从「单点 Junction 迁移」升级为「C 盘空间管理 + 冷数据归档」，
> 并重做整个桌面 UI、交付安装版与便携版。
>
> 详细设计与取舍见 [docs/UPGRADE-PLAN.md](docs/UPGRADE-PLAN.md)。

## 状态

| 阶段 | 内容 | 状态 |
|---|---|---|
| v2-0 | 架构重构：core / ui 分层，v1 兼容 | ✅ |
| v2-1 | 安全底座：清单校验、安全删除、Restart Manager、审计 | ✅ |
| v2-2 | C 盘瘦身：扫描 / 批量 / 迁移 / 撤销 / 自动回滚 | ✅ |
| v2-3 | 冷数据归档：盘符识别、候选分级、移动 / 链接 / 复制、已链接二次归档 | ✅ |
| v2-4 | 新 UI：6 页面、设计系统、进度 / 确认 / Toast、截图验收 | ✅ |
| v2-5 | 提权 helper：一次 UAC 批量执行、文件进度协议 | ✅ |
| v2-6 | 分发：PyInstaller onedir、便携 zip、Inno Setup 安装包 | ✅ |
| v2-7 | 文档、测试、旧版归档 | ✅ |

## 关键决策

- **C 与 D 同盘识别**：界面直接展示物理盘归属，避免用户误以为搬去 D 就多了空间。
- **冷数据按 IO 模式分级**：扩展名构成 + 文件平均大小 + 最近修改时间，而不是单纯按体积。
- **已链接数据可二次归档**：C 路径是 Junction 时，移动真实目标并把链接改指到机械盘。
- **复制 → 校验 → 删源**：绝不用 `/MOVE`；校验失败绝不删源。
- **删除只走安全删除器**：递归时遇到 Junction 只删链接，不进入目标。
- **一次 UAC 批量执行**：GUI 写 job.json，自身 `--elevated` helper 执行并写进度。
- **安装版 + 便携版同源**：同一个 onedir 载荷，便携版仅多 `portable.flag`。

## 验收

- [x] `python -m unittest discover -s tests` 全绿
- [x] 真实临时目录完成迁移/撤销、移动归档/回迁、链接归档
- [x] 提权 job 协议单测通过
- [x] 离屏渲染 6 个页面 + 弹窗 + 进度 + Toast 截图
- [x] `dist/CDriveCleaner/CDriveCleaner.exe --self-check` / `--smoke` 通过
- [x] 安装包编译、静默安装/卸载（见发布说明）

## 后续

- [ ] 内置 Everything 索引可选加速（当前默认原生扫描，保证准确）
- [ ] 定时归档计划
- [ ] 英文界面
