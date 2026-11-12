# 自动更新

## 行为

- 启动 2.6 秒后后台检查 `https://api.github.com/repos/Enkrid-Rao/CDriveCleaner/releases/latest`。
- 每 24 小时最多自动检查一次；设置页可关闭，也可手动检查。
- 只有 tag 版本高于当前 `cdc/version.py` 时提示；不处理预发布。
- 发现新版本会在主窗口顶部显示提示条，点击查看 release notes。

## 下载与安装

| 运行方式 | 更新包 | 安装方式 |
|---|---|---|
| 安装版 | `CDriveCleaner-Setup-vX.Y.Z.exe` | 退出后 PowerShell 等待安装完成，再启动新版本；安装程序参数 `/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /FORCECLOSEAPPLICATIONS` |
| 便携版 | `CDriveCleaner-Portable-vX.Y.Z.zip` | 退出后 PowerShell 解压覆盖程序目录（保留 `data\`），重启 |
| 源码运行 | 无 | 只打开发布页 |

下载使用 GitHub Release asset 的 `digest`（`sha256:...`）校验；校验失败删除文件并报错。

## 缓存

- 下载目录：`data_dir()/updates`
- 检查时间/跳过版本：`cache_dir()/update.json`
- 便携版更新日志：`%TEMP%\CDriveCleaner_update.log`

## 限制

- 只支持 GitHub Release 资产，不处理私有仓库或需要登录的下载。
- 未做代码签名；Windows SmartScreen 可能提示，需自行核对 SHA256。
- 安装版若安装在所有用户目录，更新时可能触发 UAC。
