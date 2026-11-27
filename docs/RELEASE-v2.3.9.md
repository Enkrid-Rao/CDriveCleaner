# CDriveCleaner v2.3.9 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.9.exe` | 36 MB | `55F810519882E6E01F4B1203D8535158CFC2DAD163D798825CB363EEF7D4D00B` |
| `CDriveCleaner-Portable-v2.3.9.zip` | 50.1 MB | `851B41311F9A6D1EECF88D5D074A765DCA38351BC620DC2FAE92CF334354E673` |
| `CDriveCleaner-v2.3.9-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.9-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.9.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；下载更新包时自动在本机代理与直连之间切换并记忆线路。

## 本版变更

详见 `docs/RELEASE-NOTES-v2.3.9.md`。

## 构建环境

- Python 3.14.x / PyInstaller / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）