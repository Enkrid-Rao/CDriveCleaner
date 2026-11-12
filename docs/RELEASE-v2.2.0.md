# CDriveCleaner v2.2.0 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.2.0.exe` | 35.9 MB | `F72B3BD34F37F3FCEAEFD12B35DC386D90ABF769C63E0C71F2EEF0EED94BCF17` |
| `CDriveCleaner-Portable-v2.2.0.zip` | 50.0 MB | `2B808C25B5101BB6D41FF82F4C96D3E1D2D64FE0400F4D8C87C96C630C05C11A` |
| `CDriveCleaner-v2.2.0-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.2.0-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.2.0.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

首次使用自动更新需要手动安装 v2.2.0；之后启动时会检查 GitHub Release，并在顶部提示新版本。安装版下载 Setup 静默更新并重启；便携版下载 zip 后覆盖程序目录并重启。下载使用 SHA256 digest 校验。

## 验证

- 32 项测试通过
- 安装包静默安装 → 自检 → 卸载通过
- 便携包解压 → 自检 → `data\` 生成通过
- 打包 exe 自检 / smoke 通过
