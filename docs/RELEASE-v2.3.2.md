# CDriveCleaner v2.3.2 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.2.exe` | 35.9 MB | `BA1FE96072036E2686222CAB58346DE1532BA4813ED8054B5B191F12DA9A4F66` |
| `CDriveCleaner-Portable-v2.3.2.zip` | 50.0 MB | `D82D7EAC67D9ED8DBF24DBCAB5F6EE34316F0EFC3773CE6EB4F587733F5EEEAA` |
| `CDriveCleaner-v2.3.2-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.2-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.2.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；v2.1.0 及更早版本需要手动安装一次。
安装版下载 Setup 静默更新并重启；便携版下载 zip 后覆盖程序目录并重启。下载使用 SHA256 digest 校验。

## 本版变更

- **归档目录结构**（`storage.archive_layout`，默认「保留原路径」）：
  - 保留原路径：`E:\C\Users\你\Downloads`、`E:\D\Projects\Foo`
  - 按目录名：`E:\Downloads`、`E:\Foo`
  设置页与「冷数据归档」页都能改；候选列表、执行计划、确认框实时显示换算后的目标。
- **「归档后保留原目录」开关加到归档页**（与设置页双向同步）：开 = 清空内容保留骨架，
  关 = 连源目录一起删除。
- 目标路径换算统一收口到 `models.archive_dest()`，扫描器 / 归档页 / 自定义目录不再各算各的。
- 老配置缺 `archive_layout` 时按「保留原路径」处理（等同 v2.0 的目录结构）。

## 验证

- 51 项单元测试通过（新增：`archive_layout` 默认值与保存往返、`E:\C\...` 与 `E:\D\...` 换算、
  归档页切换目录结构后目标路径同步）
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整（含 `portable.flag`、`_internal`、`使用说明.txt`）
- 安装包 Inno Setup 6.7.3 编译成功
- 未在本机做覆盖安装测试，避免覆盖已安装的旧版本

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
