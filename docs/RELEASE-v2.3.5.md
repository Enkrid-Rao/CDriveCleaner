# CDriveCleaner v2.3.5 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.5.exe` | 35.9 MB | `301CAD461F8C4DC84498BE04E9A1CE5CA3C3072ED679D68E76E5FA3057E80C3E` |
| `CDriveCleaner-Portable-v2.3.5.zip` | 50.0 MB | `AA786CC262CBB5E1D2F4AFE4316038B0D4C8EDCB034C2C0E2D41F373F691746A` |
| `CDriveCleaner-v2.3.5-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.5-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.5.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；下载更新包时自动在本机代理与直连之间切换并记忆线路。

## 本版变更

- **新增「从归档目录复原」**（操作记录页）：按 `.cdc-origin.json` 来源标记反推原路径，
  没有标记时按「保留原路径」结构推断；复制回原位置、校验通过后才删除归档副本。
- **复制速度改用最近 15 秒增量**：目标里已有旧副本时不再把 ETA 算成 1 秒。
- **校验阶段上报进度与剩余时间**：不再停在 62%/69% 让人以为卡死。
- ETA 归零时显示「剩余 —」，不留旧数字。
- **Temp 清理**：忙时给出提示；新增「全部清理」；完成后报告实际释放量，0 B 时说明原因。

## 验证

- 61 项单元测试通过（新增：来源标记反推原路径 ×3、按归档目录复原全流程、
  校验阶段必须上报进度）
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整；安装包 Inno Setup 6.7.3 编译成功
- 未在本机做覆盖安装测试，避免覆盖正在使用的旧版本

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
