# CDriveCleaner v2.3.10 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.10.exe` | 36 MB | `5DAC8EC041FFE8F4F553A537B1422C588CF912EDDC1B295A9F922AEE5E09252E` |
| `CDriveCleaner-Portable-v2.3.10.zip` | 50.1 MB | `A341E0975212777EEE15656D158C8013CFD3E8825A54AE7D2F01FED32B407287` |
| `CDriveCleaner-v2.3.10-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.10-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.10.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；下载更新包时自动在本机代理与直连之间切换并记忆线路。

## 本版变更

详见 `docs/RELEASE-NOTES-v2.3.10.md`。

## 构建环境

- Python 3.14.x / PyInstaller / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）