# CDriveCleaner v2.3.0 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.0.exe` | 35.9 MB | `02F5D6B41D5E62BBE303A7A6B59F5FBE72401C60E483A1D518DF9DBA612B33C6` |
| `CDriveCleaner-Portable-v2.3.0.zip` | 50.0 MB | `E1B405748B6C697BA3EA4C041EF5CBB04B3171E3E79D5E25F7702698ACEF10CD` |
| `CDriveCleaner-v2.3.0-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.0-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.0.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；v2.1.0 及更早版本需要手动安装一次。
安装版下载 Setup 静默更新并重启；便携版下载 zip 后覆盖程序目录并重启。下载使用 SHA256 digest 校验。

## 本版变更

- 冷数据归档改为「剪切」语义：移除「链接归档」，移动归档不再在源位置留下任何链接。
- 新增设置「归档后保留原目录」（默认开启）：开启时只清空内容、保留目录骨架；
  关闭后连源目录本身一起删除，等同剪切 + 粘贴。
- `preflight_archive` 拒绝「普通目录 + link 模式」；老配置 `default_mode: "link"` 归一为移动归档。
- 只有本身已是 Junction 的目录仍允许改指链接目标（否则原路径消失会让程序坏掉）。
- 冷数据判级不再把整个 `Downloads` 判为推荐，并提示改选其子目录。
- 修复系统深色模式下目录选择框黑底黑字、对话框中文化与宽度自适应（v2.2.0 之后未发布的修复）。

## 验证

- 42 项单元测试通过（`python -m unittest discover -t . -s tests`）
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整（含 `portable.flag`、`_internal`、`使用说明.txt`）
- 安装包 Inno Setup 6.7.3 编译成功
- 未在本机做覆盖安装测试，避免覆盖已安装的旧版本

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
