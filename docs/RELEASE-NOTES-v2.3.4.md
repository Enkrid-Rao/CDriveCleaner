# CDriveCleaner v2.3.4

> 目录选择器重写（Junction / 隐藏目录不再空白），冷数据分析补上「二级展开」。

## 目录选择器重写

旧的「选择要归档的目录」用的是 Qt `QFileDialog` 的目录模式（`ShowDirsOnly + ExistingFiles`
凑多选）。这套组合在 Junction、隐藏目录、深层目录下不可靠——进入 `.lmstudio` 这类链接目录时
列表可能直接空白，确认按钮还会变成「进入目录」。

新实现 `cdc/ui/dir_picker.py`：

- 用 `os.scandir` 自己枚举，**Junction 标 `→`、可以展开浏览目标内容**
- 隐藏目录用灰色显示（不再被过滤掉）
- 勾选框多选、路径栏直接跳转、双击展开、上一级
- 无权限目录给一行提示，不再空白

## 冷数据分析：二级展开

旧逻辑只扫「用户目录」和 `D:\` 的下一层，`D:\Projects` 因为小文件多被判 SKIP 后，里面
91 GB 的 `Sill-Promo` 根本不会出现。

现在体积大的混合目录会自动展开一层，把真正该归档的子目录单独列成候选，并标注「在 Projects 里」；
顶部增加总览：目录数、合计体积、推荐归档个数与体积。

## 验证

- 56 项单元测试通过（新增：目录树列出隐藏目录 / Junction 并可展开、勾选结果、
  Downloads 展开出 Software 的二级候选、UI 目标路径随目录结构变化）
- 在本机实跑分析：29 个候选 / 66 秒，正确列出 `Sill-Promo 91.0 GiB`、`.lmstudio 38.7 GiB`、
  `.android 13.6 GiB` 等

## 下载

| 资产 | 说明 |
|---|---|
| `CDriveCleaner-Setup-v2.3.4.exe` | 安装版 |
| `CDriveCleaner-Portable-v2.3.4.zip` | 便携版，解压即用 |
| `CDriveCleaner-v2.3.4-SHA256SUMS.txt` | 下载校验 |

> 未做代码签名，SmartScreen 可能提示；请核对 SHA256。

## 升级

v2.2.0 及以上可以在应用内自动更新（设置 → 自动检查更新）；v2.1.0 及更早需要手动安装一次。
