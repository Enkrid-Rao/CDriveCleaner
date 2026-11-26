# CDriveCleaner v2.3.6 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.6.exe` | 35.9 MB | `BA1AA402A2B182740DDEACE9192CEB42899C1EB0E38C9FFCF024E6B33240F7E9` |
| `CDriveCleaner-Portable-v2.3.6.zip` | 50.1 MB | `43EEED350958DA3A119FAA15123AA7D9102CB2EF8276CADD902C252C167232F2` |
| `CDriveCleaner-v2.3.6-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.6-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.6.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；下载更新包时自动在本机代理与直连之间切换并记忆线路。

## 本版变更

### 确认归档弹窗的三个勾选项

- **压缩成 zip 后归档**：归档目录内生成 `<名称>.zip`，压缩包校验通过后才清空源目录。
  适合大量小文件与外置机械盘；仅「移动归档」且非 Junction 源可用。
- **归档后校验副本**：默认开。复制后遍历目标目录逐文件比对数量/大小（不读内容）；
  关闭可明显加快，但审计记录会标记「未校验」。
- **归档后删除原目录**：覆盖「归档后保留原目录」设置，只影响本次。

三个选项的默认值来自设置页，本次选择会被记住。

### 从归档目录复原

选一个归档目录，按 `.cdc-origin.json` 反推原路径（无标记时按「保留原路径」结构推断），
复制回原位置、校验通过后才删除归档副本；压缩归档会自动解压。

### 修复

- 复制速度改用最近 15 秒增量，目标有旧副本时不再把 ETA 算成 1 秒
- 校验阶段上报进度与剩余时间，不再停在 62%/69%
- ETA 归零显示「剩余 —」
- Temp 清理：忙时提示、新增「全部清理」、完成后报告释放量

## 验证

- 66 项单元测试通过
- 压缩归档在测试里跑通「压缩 → 校验 → 清空源 → 复原解压 → 删归档」全流程
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整；安装包 Inno Setup 6.7.3 编译成功

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
