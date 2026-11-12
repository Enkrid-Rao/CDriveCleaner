# D 盘目录重组方案

> 目标：把散落在 `D:\` 根目录的「C 盘迁移产物」收进一个仿 C 结构的容器目录，
> 让 D 盘根目录只剩用户自己会主动打开的东西；并同步重写 CDriveCleaner 的目标路径配置。
>
> 状态：**方案待确认，未执行任何改动。**

---

## 0. 结论先行

| 问题 | 结论 |
|---|---|
| 能不能做 | **能。技术上没有障碍。** |
| 改动量 | config.json 改 2 处 + config.py 同步默认值；业务代码零改动 |
| 存量数据怎么搬 | 51 个 junction 逐个「拆链 → 同卷 move → 重建链」，同卷 move 是元数据操作，**每个目录亚秒级**，不复制数据 |
| 真正难点 | **不是技术，是进程占用和管理员权限**——必须先关掉一批应用 |
| 为什么之前越迁越不够 | C: 和 D: 在**同一块 1TB SSD** 上，迁移只是分区内搬运，总容量不变 |

---

## 1. 现状诊断

### 1.1 物理拓扑（关键）

```
Disk 0  UMIS RPJYJ1T24MLR1HWY  NVMe  953.9 GB
        ├─ C:  Windows-SSD  400.0 GB   已用 329.6  剩 70.4  (82.4%)
        └─ D:  Data         551.6 GB   已用 322.5  剩 229.1 (58.5%)

Disk 1  Lenovo F308           USB    931.5 GB
        └─ E:  HD           931.5 GB   已用 172.1  剩 759.4 (18.5%)
```

**C: 与 D: 是同一块物理 SSD 的两个分区。**
CDriveCleaner 的 junction 迁移，本质是把数据从 SSD 的 C 分区搬到 D 分区，
**这块盘的总可用空间一分没多**。所以「迁完还是不够」是必然结果。

真正的增量空间只在 E 盘（USB 机械盘，931.5 GB，剩 759.4 GB）。

### 1.2 D 盘根目录构成（49 项）

| 类别 | 目录 | 合计 |
|---|---|---|
| **迁移目标**（工具建的，非用户主动） | `AppData` 79.6 / `Program Files` 60.5 / `ProgramData` 23.5 / `Cache` 3.8 / `Media` 0.2 | ~167.6 GB |
| **用户自己的数据/程序** | `Projects` `Learning` `Tools` `Scoop` `Downloads` 27.1 `Documents` 6.4 `Videos` 12.3 `Temp` 10.6 `Drivers` `Software` `MYOS` 26.8 `AppStore` 17.7 `VirtualMachines` 6.2 `MYEmulatorCase` 8.3 `UniversalPlatform` `qq聊天记录` `夸克下载` `迅雷云盘` `迅雷下载` `MCLDownload` `BaiduNetdiskDownload` `Backup` `OAMS` `mystream` `WorkBuddy` `WindowsApps` `WpSystem` | ~155 GB |
| **早期迁移残留**（空壳/孤儿） | `c`(Users) `d`(Temp) `Local`(Huawei/OpenHarmony 空目录) `AppCache`(Wechat 空) `Program`(MYAssistant) `tmp`(pyd 工具) `.pogget` | ~1.4 GB |

> `D:\c\Users\raoxi\.workbuddy\binaries` 说明之前尝试过「仿 C 结构」但没走完，留下了壳。

### 1.3 需要重组的迁移项：51 个

完整映射清单见同目录 `junction_map.txt`（格式：`C盘路径 <TAB> 当前D盘目标 <TAB> 建议新路径`）。

**注意：D 盘侧目录名与 C 盘侧不一致**（历史手工改名导致），所以**不能整目录 move**，必须逐项处理：

| C 盘路径 | 当前 D 盘目标 | 名称是否一致 |
|---|---|---|
| `...\AppData\Local\Google` | `D:\AppData\Chrome` | ✗ |
| `...\AppData\Roaming\Code` | `D:\AppData\VSCode` | ✗ |
| `...\AppData\Roaming\Tencent\xwechat` | `D:\AppData\WeChat` | ✗ |
| `...\AppData\Roaming\Tencent\WeMeet` | `D:\AppData\TencentMeeting` | ✗ |
| `...\AppData\Local\mineru-updater` | `D:\AppData\mineru` | ✗ |
| `...\AppData\Local\npm-cache` | `D:\Cache\npm` | ✗ |
| `...\AppData\Local\Steam` | `D:\Cache\Steam` | ✓ |
| `...\AppData\Local\FlowLauncher` | `D:\AppData\Others\FlowLauncher` | 路径层级不同 |
| `...\.cache` | `D:\Cache\dotcache` | ✗ |
| `...\Pictures\Screenshots` | `D:\Media\Pictures\Screenshots` | ✓ |
| 其余 40 项 | 基本同名 | ✓ |

---

## 2. 目标结构

```
D:\
├── _CDrive\                          ← 唯一容器：所有从 C 盘迁移来的，1:1 复刻 C 盘结构
│   ├── Users\
│   │   └── raoxi\
│   │       ├── .cache\
│   │       ├── Pictures\
│   │       │   └── Screenshots\
│   │       └── AppData\
│   │           ├── Local\            (24 项：Google / Huawei / OpenHarmony / Steam / pip / nvm …)
│   │           ├── Roaming\          (11 项：Code / bilibili / IDM / Qwen / Tencent\xwechat …)
│   │           ├── LocalLow\
│   │           └── Programs\         (10 项：Python / Trae / Xmind / MiKTeX / QuickLook …)
│   ├── ProgramData\
│   │   └── Blackmagic Design\
│   └── Program Files\
│       └── JetBrains\
│
├── Projects\        ← 用户自己的，保持在根目录
├── Learning\
├── Tools\
├── Scoop\
├── Downloads\
├── Documents\
├── Videos\
├── MYOS\
├── AppStore\
└── …（其余用户目录）
```

**命名备选**（待定）：`_CDrive`（下划线开头，资源管理器排序置顶）／ `CDrive` ／ `_from_C` ／ `C_Backup`。

**空目录不建**：新结构按实际有数据的目录生成，`LocalLow` 等若为空则不创建。

---

## 3. CDriveCleaner 改造

### 3.1 只改配置，业务代码零改动

`migrator.py` / `scanner.py` 全部通过 `zone["dest_base"]` 取目标路径，
`config.py` 负责占位符展开。因此**只需要改配置**。

### 3.2 `config.json` 改动

```diff
- "target_base": "D:",
+ "target_base": "D:\\_CDrive",

  "zones": {
    "programs": {
-     "dest_base": "{TARGET_BASE}\\AppData\\Programs",
+     "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Local\\Programs",
    },
    "local": {
-     "dest_base": "{TARGET_BASE}\\AppData\\Local",
+     "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Local",
    },
    "roaming": {
-     "dest_base": "{TARGET_BASE}\\AppData\\Roaming",
+     "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Roaming",
    },
    "localLow": {
-     "dest_base": "{TARGET_BASE}\\AppData\\LocalLow",
+     "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\LocalLow",
    },
    "programdata": {
-     "dest_base": "{TARGET_BASE}\\ProgramData",
+     "dest_base": "{TARGET_BASE}\\ProgramData",
    },
    "programfiles": {
-     "dest_base": "{TARGET_BASE}\\Program Files",
+     "dest_base": "{TARGET_BASE}\\Program Files",
    },
  }
```

说明：
- `{TARGET_BASE}` = `D:\_CDrive`，`{USERNAME}` = `raoxi`（`_BASE_PLACEHOLDERS` 已支持，无需新增占位符）
- `programdata` / `programfiles` 两项**路径值不变**，但因为 `TARGET_BASE` 变了，实际落点自动变成 `D:\_CDrive\ProgramData` 和 `D:\_CDrive\Program Files`
- 展开后示例：`C:\Users\raoxi\AppData\Local\Google` → `D:\_CDrive\Users\raoxi\AppData\Local\Google`

### 3.3 `src/config.py` 同步

`_default_config()` 里的 `target_base` 与 6 个 `dest_base` 默认值需与 `config.json` 保持一致，
否则删掉 config.json 重新生成时会退回旧结构。

### 3.4 需要顺带处理的两个细节

1. **`.cache` / `Pictures\Screenshots` / `Tencent\WeMeet` / `Tencent\xwechat`**
   这 4 项是手工迁移的，不属于任何 zone。要么在 config.json 里新增 zone，要么由搬迁脚本单独处理。

2. **`settings.py` 的 UI**
   设置页只暴露 `target_base` 一个可编辑项，zone 的 `dest_base` 走 config.json。
   改完配置后 UI 会显示 `D:\_CDrive`，符合预期，无需改 UI。

---

## 4. 存量数据搬迁

### 4.1 单项目处理流程

```
对每个映射项  C:\P  →  D:\Old  （新路径 D:\_CDrive\P'）：

  ① 检查进程        相关应用必须已关闭
  ② rd "C:\P"       删除 junction 本身（只删链接，不碰数据）
  ③ move "D:\Old" "D:\_CDrive\P'"    同卷移动 = 改 MFT，秒级，不复制
  ④ mklink /J "C:\P" "D:\_CDrive\P'"  重建链接指向新位置
  ⑤ 验证            Get-Item "C:\P" 的 Target 是否等于新路径
```

**关键点：②③④ 之间窗口期，该目录在 C 盘不可用。** 所以必须先关应用。

### 4.2 为什么这个顺序是安全的

- `rd` 删的是 reparse point 本体，**不递归删目标数据**（前提：用 `rd` 而非 `rd /s`）
- `move` 在同一个卷内不复制数据，断电/失败风险极低
- 全程保留 `Old → New` 映射表，任何一步失败都能反向重建 junction 指回旧位置

### 4.3 分批执行建议

| 批次 | 内容 | 前置条件 |
|---|---|---|
| **1** | 5 个 `*-updater` 目录、`.cache`、`Pictures\Screenshots`、`NGR`、`OfficePLUS`、`Pandoc` 等冷门项（约 15 个） | 无需关应用、无需管理员 |
| **2** | Chrome、VSCode(Code)、微信、WeMeet、bilibili、Doubao、JianyingPro、Quark、FlowLauncher、Adobe、IDM、WorkBuddy、ZTools、Qwen、NVIDIA、Huawei、OpenHarmony、pip、nvm、npm-cache、uv、Steam、`Programs\*` 10 项（约 34 个） | **关闭对应应用** |
| **3** | `C:\ProgramData\Blackmagic Design`、`C:\Program Files\JetBrains` | **管理员权限** + 关闭 DaVinci / JetBrains IDE |

### 4.4 不做的事

- **不动** `AppData\Local\Packages\*`（MSIX 应用，指向 `D:\WpSystem`，受 TrustedInstaller 保护）
- **不动** `node_modules` 下的 npx 缓存链接（`D:\Cache\npm\_npx\*`，随 npm 缓存走）
- **不动** 系统自带的兼容链接（`Application Data` / `Cookies` / `OneDrive\*` 等，目标在 C 盘内部）
- **不删** 任何真实数据；残留空壳目录（`D:\c`、`D:\d`、`D:\Local`、`D:\AppCache`、`D:\Program`）单独确认后再清

---

## 5. 风险与边界

| 风险 | 影响 | 应对 |
|---|---|---|
| 应用正在运行 | `move` 失败，目录卡在中间状态 | 批次 2/3 执行前逐一检查进程；失败项跳过并记录，稍后重试 |
| `rd` 用错参数 | 误删目标数据 | **只用 `rd`（删链接），禁用 `rd /s`**；脚本里硬校验 reparse 属性 |
| 中途失败 | C 盘目录暂时不可用 | 保留映射表，反向 `mklink` 指回旧路径即可恢复 |
| ProgramData / Program Files | 权限不足 | 单独用管理员会话执行 |
| 杀软 / 索引服务占用 | 个别目录 move 失败 | 重试或加入排除项 |

**边界声明**：本次方案只处理「C 盘 junction → D 盘目标」这一条链路，
不涉及注册表、不涉及服务配置、不涉及 `WindowsApps`/`WpSystem`。

---

## 6. 待你拍板

1. **容器目录名**：`D:\_CDrive` / `D:\CDrive` / 其他？
2. **执行方式**：我写一个带 dry-run 和回滚的 Python 脚本，还是逐批给命令你手动跑？
3. **要不要连带做空间回收**（与结构重组独立，可后做）：
   - `D:\AppStore` 17.7 GB —— 全是 MYOS 取证工具**安装包**（`setup_trial_*.exe/.iso/.zip`），装完即废
   - `D:\ProgramData\Lenovo` 18.3 GB —— 联想电脑管家缓存
   - `D:\Temp` 10.6 GB —— 临时文件
   - `D:\Cache` 3.8 GB + `D:\DeliveryOptimization` 1.1 GB
   - 冷数据外迁 E 盘：`Downloads` 27.1 / `Videos` 12.3 / `qq聊天记录` 4.2 / `夸克下载` 2.8 / `迅雷云盘` 2.0 / `BaiduNetdiskDownload` 1.1 / `Drivers` 5.4
   - 合计可回收 **约 105 GB**
