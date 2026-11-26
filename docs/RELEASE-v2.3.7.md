# CDriveCleaner v2.3.7 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.3.7.exe` | 36.0 MB | `F4A05A61FC2123A961788FD6F97E1D2C43D71B6BB7F9074C82BA23628D4D01C9` |
| `CDriveCleaner-Portable-v2.3.7.zip` | 50.1 MB | `5F24BC0698AECD1D29051ED3E2EDDEB29171EEF2CE4E7160BDF85E4EEE426E0F` |
| `CDriveCleaner-v2.3.7-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.3.7-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.3.7.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；下载更新包时自动在本机代理与直连之间切换并记忆线路。

## 本版变更：目录选择器重做

此前的选择目录是一个「路径栏 + 裸树」的朴素界面，且每次固定从归档盘 `E:\` 开始。

- **左侧导航**：快速访问（用户目录 / 桌面 / 下载 / 文档 / 归档盘）+ 磁盘列表（C/D/E，含可用空间）
- **右侧**：上一级 + 路径栏（可粘贴路径直达）+ 目录树
- **卡片式弹窗**，与应用其它对话框风格一致
- **目录树**：32px 行高、文件夹图标、悬停高亮；Junction 链接图标 + `→`，可展开浏览；
  隐藏目录灰色；无权限目录给提示行
- **自绘勾选框**：选中为品牌红底 + 白色对勾，底部实时「已选 N 项」，按钮「添加选中（N）」
- **双击展开**：折叠/展开切换，子目录首次展开时才扫描加载
- **记住位置**：打开时回到上次浏览/确认过的目录；自定义归档从用户目录开始，复原入口停在归档盘

## 验证

- 66 项单元测试通过（选择器：隐藏目录与 Junction 可列出并展开、勾选结果、多选项确认框）
- 实测：双击展开 → 懒加载 3 个子目录，再次双击收起；勾选与展开互不干扰
- PyInstaller onedir 载荷构建成功，`CDriveCleaner.exe --self-check` 退出码 0
- 便携包 zip 结构完整；安装包 Inno Setup 6.7.3 编译成功

## 构建环境

- Python 3.14.7 / PyInstaller 6.21.0 / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 `packaging/build.ps1` 校验（`cdc/version.py`、`installer.iss`、`version_info.txt`）
