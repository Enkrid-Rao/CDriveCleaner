# CDriveCleaner v2.3.1 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.1.exe` | 35.9 MB | `EB0F3D50CCC6D00F00939E67CF4B99A9886C5427AC7F648A9451F4D1E66005BF` |
| `CDriveCleaner-Portable-v2.3.1.zip` | 50.0 MB | `007B6F9C3569A8E489AEF740DF765B5207F2C7BFDD3C954BE110407345960E09` |
| `CDriveCleaner-v2.3.1-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.1-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.1.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；v2.1.0 及更早版本需要手动安装一次。
安装版下载 Setup 静默更新并重启；便携版下载 zip 后覆盖程序目录并重启。下载使用 SHA256 digest 校验。

## 本版修复

- **Junction 改指改为就地改写重解析点**（`FSCTL_SET_REPARSE_POINT`），不再「删链接 → 重建」：
  不受链接自身只读属性影响，路径全程在线，失败时原链接仍可用；不可用时才回退到删建。
- **所有删除统一走 `windows.delete_entry()`**：链接的只读属性用 `OPEN_REPARSE_POINT` 句柄清理
  （不会改到目标），文件/目录先清只读再删，瞬时占用自动重试，失败返回真实 `WinError`。
- 修复**带只读属性的 Junction 无法删除**（`RemoveDirectory` 返回拒绝访问 5）：
  `Videos` / `Music` / `Pictures` 这类由旧版整理工具创建的链接都会中招。
- 归档清理旧目标失败时降级为警告，不再把已经成功改指的归档记成失败。
- 归档预检的「可删除」探测只在移动归档时执行（改指场景不再需要能删链接）。

## 验证

- 49 项单元测试通过（新增 4 项：只读 Junction 就地改指、Videos 场景端到端回归、
  只读文件删除、占用时预检拦截）
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整（含 `portable.flag`、`_internal`、`使用说明.txt`）
- 安装包 Inno Setup 6.7.3 编译成功
- 在 Windows 11 上对真实的 `Music` / `Pictures`（带只读属性的旧链接）做了空操作改指，均成功
- 未在本机做覆盖安装测试，避免覆盖已安装的旧版本

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
