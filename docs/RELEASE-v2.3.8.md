# CDriveCleaner v2.3.8 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.8.exe` | 36.0 MB | `78BF1F6B3F468405976109195A105D4CF929C53CF1FECC768B0B2835BF171528` |
| `CDriveCleaner-Portable-v2.3.8.zip` | 50.1 MB | `540E1DF304F8A683E36CC2E8C8FB1EA2DE85009D7DDCDA1032357E6F71FC940D` |
| `CDriveCleaner-v2.3.8-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.8-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 本版变更：接入 Everything 索引

### 冷数据分析加速

检测到 Everything（`es.exe` 在 PATH 或注册表安装路径）且索引已加载时：

- 用 NTFS 索引统计每个目录的文件数、体积、扩展名构成、最新修改时间，不再逐文件遍历
- 查询失败、索引未加载、目录不在索引里、超时 → 自动回退逐文件遍历
- 设置 → 冷数据归档 → 「用 Everything 加速分析」可关闭

### 总览页「空间构成」

- 秒级列出全盘最大的 25 个文件（大小 + 路径 + 打开所在目录）
- 首次进入自动查询，「重新扫描」手动刷新
- 未检测到 Everything 时显示提示、按钮置灰

### 安全边界

归档复制、校验、复原**全部以真实文件系统为准**，不使用可能滞后的索引。

## 验证

- 75 项单元测试通过（新增：解析千分位大小 / 两种日期格式 / 目录行过滤 /
  一级目录聚合 / 可用性禁用 / 扫描器索引优先 / 总览卡片）
- 真实环境：`D:\Projects`（12.3 万文件）分析约 15 秒完成（含 Junction 与二级展开）
- 实测 Everything 索引统计与逐文件遍历结果一致（Downloads 29,243 文件 / 15.11 GiB 完全一致）
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整；安装包 Inno Setup 6.7.3 编译成功

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
