# CDriveCleaner v2.3.3 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.3.exe` | 35.9 MB | `F1D03588E76F0B544A3CC4004E701CABBD98C04B298BC4FB205E49C541035B81` |
| `CDriveCleaner-Portable-v2.3.3.zip` | 50.0 MB | `FFF06B70B87BB37B8FBF90535B831844B8B8BE10A9358A713966184E08EE1853` |
| `CDriveCleaner-v2.3.3-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.3-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.3.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；v2.1.0 及更早版本需要手动安装一次。
安装版下载 Setup 静默更新并重启；便携版下载 zip 后覆盖程序目录并重启。下载使用 SHA256 digest 校验。

**本版修复**：下载更新包时自动在「上次成功的代理 → 环境变量代理 → 本机常见代理
（7899 / 7898 / 7890 / 10809 / 1080）→ 直连」之间切换并重试两轮，成功线路写入
`state/cache/update.json` 供下次优先使用。此前裸 `urllib` 直连 `release-assets.githubusercontent.com`，
在会 reset 的网络下必然失败——表现为「能检查到新版本，但一点下载就失败」。

## 本版变更

- 下载多线路自动切换 + 记忆；检查更新同样带代理回退。
- 更新对话框显示实际线路（「经 http://127.0.0.1:7899」），按钮改为「下载并安装」。
- 「稍后 / ✕」不再把版本永久标记为跳过。

## 验证

- 55 项单元测试通过（新增：线路优先级、本地 HTTP 下载、缺 digest 拒绝、检查线路顺序）
- 用程序自己的 `download_asset()` 实测下载 v2.3.2 安装包：35.9 MB / 20.5 s / 1.8 MB/s，
  SHA256 通过，自动选中 7899 并记住
- 更新安装脚本实测：等待主进程退出 → 运行安装包 → 重启新版本，全流程通过
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整（含 `portable.flag`、`_internal`、`使用说明.txt`）
- 安装包 Inno Setup 6.7.3 编译成功
- 未在本机做覆盖安装测试，避免覆盖已安装的旧版本

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
