# CDriveCleaner v2.1.0 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| `CDriveCleaner-Setup-v2.1.0.exe` | 35.6 MB | `9EE98AC8B35FA117ECD8052CB99EA5F31D0910B1BBC18C710F8B0E8510B7ED1A` |
| `CDriveCleaner-Portable-v2.1.0.zip` | 49.8 MB | `404F04FD9184820B66FDEA908E8BC1342BA1B8944E4C09B23232F236B5834FBE` |
| `CDriveCleaner-v2.1.0-SHA256SUMS.txt` | — | — |

哈希值也可从 `CDriveCleaner-v2.1.0-SHA256SUMS.txt` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

```powershell
.\CDriveCleaner-Setup-v2.1.0.exe
```

安装版数据目录：`%LOCALAPPDATA%\CDriveCleaner\`。

## 便携版

解压整个 zip，保留 `_internal` 目录，双击 `CDriveCleaner.exe`。

## 本次重点

- 暖纸张新 UI、字号提升、图标重绘
- 归档目标按目录名同级排列
- 移动归档保留目录结构
- 自定义目录可多选
- 目标路径可设为 `E:\`
- 复制进度改平均速度

## 验证

- 28 项测试通过（归档/撤销/清空结构/扫描/配置/UI smoke）
- 2.1.0 安装包静默安装 → 自检 → 卸载通过
- 2.1.0 便携包解压 → 自检 → `data\` 生成通过
- 打包 exe 自检 / smoke 通过
