# CDriveCleaner v2.3.10

> 目录选择界面还原成 2.3.3 的样子，只修复 Junction 进不去的问题。

## 为什么改回去

2.3.3 的选择目录界面（`QFileDialog`，中文标签「当前位置 / 目录 / 添加选中」，
Ctrl / Shift 多选）本身没问题。当时“选择目录坏了”的真正原因是 Qt 的模型缺陷：

- Junction 目录在列表里可见；
- 但 `QFileSystemModel` 把它的子项数量算成 0，双击进不去，只能停在上一层。

2.3.4 因此重写了整个选择器 UI，这一步是错误的。本版把界面与操作方式还原成 2.3.3，
只针对 Junction 做修复。

## 本版改动

- **界面还原**：确认归档 / 复原时选择目录重新使用 `QFileDialog`（中文标签、Ctrl / Shift 多选、
  双击进入目录），去掉 2.3.4–2.3.9 的自绘目录树。
- **Junction 修复**：拦截双击 / 回车，遇到“模型子项为 0”的 Junction 目录时用
  `setDirectory` 直接进入，可以正常浏览并选择里面的目录。
- 归档页「自定义目录」与操作记录页「从归档目录复原」统一使用该对话框。

## 验证

- 实测：从用户目录双击 Junction（如 `.lmstudio`）能进入，并列出目标目录内的子目录
- 实测：Ctrl / Shift 多选后「添加选中」能正确返回多个目录
- 74 项单元测试通过（新增：选择器列出目录并确认、双击进入 Junction）
- 发布脚本已集成打包 + 推送 + 创建 Release（`scripts/publish.ps1`）

## 下载

| 资产 | 说明 |
|---|---|
| `CDriveCleaner-Setup-v2.3.10.exe` | 安装版 |
| `CDriveCleaner-Portable-v2.3.10.zip` | 便携版，解压即用 |
| `CDriveCleaner-v2.3.10-SHA256SUMS.txt` | 下载校验 |

> 未做代码签名，SmartScreen 可能提示；请核对 SHA256。

## 升级

v2.2.0 及以上可以在应用内自动更新；v2.1.0 及更早需要手动安装一次。
