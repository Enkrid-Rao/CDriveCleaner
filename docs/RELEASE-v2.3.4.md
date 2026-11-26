# CDriveCleaner v2.3.4 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.4.exe` | 35.9 MB | `2B9BCE1A8EF9E752799F25A34F751A3B4648ABB79C8917C3224C10DD760F0A83` |
| `CDriveCleaner-Portable-v2.3.4.zip` | 50.0 MB | `82E43277D2AF55F169DB31A8BD52906E70A35E53DD394975796692E817025F9E` |
| `CDriveCleaner-v2.3.4-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.4-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.4.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；v2.1.0 及更早版本需要手动安装一次。
下载更新包时会自动在直连与本机代理之间切换并记忆可用线路（v2.3.3 起）。

## 本版变更

- **目录选择器重写**（`cdc/ui/dir_picker.py`）：不再使用 `QFileDialog` 目录模式，
  改为自绘目录树；Junction 标 `→` 且可展开，隐藏目录灰色显示，勾选框多选、路径栏跳转、
  无权限目录给提示行。修复进入 `.lmstudio` 这类 Junction 目录时列表空白的问题。
- **冷数据分析支持二级展开**：体积大的混合目录（如 `Downloads` / `D:\Projects`）会自动展开一层，
  把 `Software` / `ISOs` / `Sill-Promo` 这类真正的冷数据子目录单独列为候选，并标注「在 X 里」。
- 分析结果增加总览：目录数、合计体积、推荐归档个数与体积。

## 验证

- 56 项单元测试通过（新增：目录树列出隐藏目录与 Junction 并可展开、勾选结果、
  二级候选展开、UI 目标路径随目录结构变化）
- 本机实跑分析：29 个候选 / 66 秒，正确列出 `Sill-Promo 91.0 GiB`、`.lmstudio 38.7 GiB`、
  `.android 13.6 GiB` 等
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整；安装包 Inno Setup 6.7.3 编译成功
- 未在本机做覆盖安装测试，避免覆盖已安装的旧版本

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
