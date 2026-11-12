# CDriveCleaner v2.0.0 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.0.0.exe` | 35.8 MB | `E6EB9A78863920848D3C4E9C4EBA6334F4B67227B4AC78FC8AA10ECCF0B942B0` |
| `CDriveCleaner-Portable-v2.0.0.zip` | 49.9 MB | `D50B759A6FF3DDF2B87604B9D452442C38011E7EFDCE5B4A6A7F3231738421ED` |

未做代码签名，Windows SmartScreen 可能提示，请核对哈希后再运行。

`dist/CDriveCleaner/` 是两个包共用的 onedir 载荷（含 `_internal`）。

## 安装

```powershell
# 图形安装
.\CDriveCleaner-Setup-v2.0.0.exe

# 静默安装到指定目录（当前用户）
.\CDriveCleaner-Setup-v2.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES `
    /NORESTART /CURRENTUSER /DIR="D:\Apps\CDriveCleaner"
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`
（卸载程序不会删除配置与审计记录，便于排查。）

## 便携版

1. 解压整个 zip，保留 `_internal` 目录。
2. 双击 `CDriveCleaner.exe`。
3. 配置、日志、审计在 `data\`，整个文件夹可移动。

## 验证

```powershell
# 源码
python -m unittest discover -s tests -v
python -m cdc --self-check

# 打包后的 exe
dist\CDriveCleaner\CDriveCleaner.exe --self-check
dist\CDriveCleaner\CDriveCleaner.exe --smoke
```

本次构建已实际验证：

- 27 个单元测试 / UI smoke 全绿
- 真实临时目录完成迁移 → 撤销、移动归档 → 回迁、链接归档
- 提权 helper job/progress/result 协议
- 安装包静默安装 → 自检 → 卸载
- 便携包解压 → 自检 / smoke → `data\` 生成

## 已知限制

- 未签名：SmartScreen 可能拦截，需“更多信息 → 仍要运行”。
- 冷数据归档默认使用原生扫描，速度受文件数量影响；Everything 索引目前作为可选配置。
- 链接归档依赖目标盘在线；USB 外置盘拔掉后原路径不可用。
- 已链接冷数据归档后暂不支持一键回迁（普通移动归档支持）。
