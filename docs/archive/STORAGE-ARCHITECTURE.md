# 三盘存储架构规划

> 回答「C/D 盘该怎么分工」「媒体文件怎么规划」「Downloads 怎么重排」「聊天记录怎么理」「怎么迁移」。
> 状态：**方案待确认，未执行。**

---

## 0. 先回答几个疑问

### 0.1 联想那 18.3 GB 不是缓存，是 AI 模型

`D:\ProgramData\Lenovo\CreatorZone\` 是**联想 CreatorZone（AI 创作工具）**的安装目录，
里面是一整套本地 Stable Diffusion 推理环境：

| 文件 | 大小 |
|---|---|
| `lora_train_models\v3-epoch2.2-emaonly.ckpt` | 3.79 GB |
| `lora_train_models\model_large_caption.pth` | 1.70 GB |
| `lora_train_models\clip-vit-large-patch14\pytorch_model.bin` | 1.63 GB |
| `image_generate_models\stable_diffusion\cn_unet_fp16.pt.flat` | 1.50 GB |
| `torch\lib\torch_cuda.dll` | 878 MB |
| `controlnet_*.pt.flat` × 4 | 2.84 GB |
| `cudnn_cnn_infer64_8.dll` / `dnnl.lib` / `cublasLt64_12.dll` | 1.62 GB |
| 其余 SD 组件（vae / text_encoder / depth / translator …） | ~2 GB |

**这是模型权重 + CUDA 运行时，不是可清缓存。** 不用联想 AI 画图就整个卸载，回收 18.3 GB。
（你说不急，那就先挂着，**不占本次执行计划**。）

### 0.2 冷数据能不能放机械盘

能。判据是 **IO 模式**，不是数据量：

| 数据类型 | IO 模式 | 机械盘 |
|---|---|---|
| 影视、课程视频、电子书、成片 | 顺序读，读几次就不再读 | ✅ 非常合适 |
| 安装包 / ISO / 压缩包 | 写一次，读一次 | ✅ 非常合适 |
| 取证镜像（E01/dd） | 顺序读 | ✅ 合适 |
| 归档文档、历史资料 | 几乎不读 | ✅ 合适 |
| **微信 / QQ 数据库** | 常驻进程频繁随机读写 SQLite | ⚠️ 见 4.3 |
| 浏览器缓存、IDE 索引 | 高频随机读写 | ❌ 不要放 |

**机械盘怕「小文件高频随机读写」，不怕「大文件顺序读写」。**

### 0.3 为什么你会觉得「D 盘不知道放什么」

因为你之前做的是 **D 盘根目录仿 C**（`D:\Documents`、`D:\Downloads`、`D:\Videos`…），
结果 **C 盘和 D 盘各有一套同名目录、内容却不同**，找东西两边都要翻。

**真正该仿 C 的只有 `_CDrive` 一个容器**——它存在的意义就是 1:1 对应 C 盘路径。
**D 盘根目录该按「用途」分，不按 C 盘的目录名分。**

---

## 1. 三盘分工模型

| 盘 | 物理 | 定位 | 放什么 | 判据 |
|---|---|---|---|---|
| **C:** | SSD 400 GB | 系统盘 | Windows、驱动、MSI 安装、必须装 C 的程序 | **只减不增**，定期迁出 |
| **D:** | SSD 551.6 GB | 工作盘 | 活跃项目、常用程序、`_CDrive`、当前下载、聊天数据、媒体库 | **每天会碰** |
| **E:** | HDD 931.5 GB | 仓库盘 | 归档、媒体仓库、安装包、镜像、历史资料 | **读写一两次**；USB 外接，**可能被拔** |

### 一条硬规则

> **E 盘上不放任何「程序运行必需」的东西。** 它是 USB 外接盘，拔掉 = 该路径消失。

---

## 2. D 盘目标结构

```
D:\
├── _CDrive\              ← 【迁移容器】C 盘迁移项，1:1 仿 C 结构
│
├── Projects\             ← 代码 / 项目（活跃）
├── Learning\             ← 学习资料
├── Downloads\            ← 下载缓冲区（第 3 节重构）
├── ChatData\             ← 聊天记录收口（第 4 节）
├── Media\                ← 媒体库（第 2.2 节，系统库重定向落点）
│
├── Tools\  Scoop\  Software\
├── MYOS\  AppStore\  VirtualMachines\  MYEmulatorCase\   ← 取证
└── …
```

### 2.1 媒体文件怎么规划（你的核心困惑）

**现状：媒体散在三块，互相不知道对方存在**

| 位置 | 大小 | 性质 |
|---|---|---|
| `C:\Users\raoxi\Pictures` | 0.02 GB | 系统「图片」库（默认位置） |
| `C:\Users\raoxi\Videos` | 0.28 GB | 系统「视频」库（默认位置） |
| `C:\Users\raoxi\Music` | 0 GB | 系统「音乐」库（默认位置） |
| `D:\Media\Pictures` | 0.16 GB | **实际图片内容**（Screenshots 的 junction 落点） |
| `D:\Videos\剪映` | **10.19 GB** | 剪映成片 + 素材（多版本并存） |
| `D:\Videos\屏幕录制` | 2.13 GB | 屏幕录制 + 剪辑成片 |

**你的困惑**：「软件默认往 `C:\Users\raoxi\Pictures` 存，但我想让数据在 D 盘，难道要一个个做 junction？」

**不用。Windows 有个原生功能，专门解决这个：**

### 2.2 系统库「位置重定向」——比 junction 干净得多

在资源管理器里：

```
右键 C:\Users\raoxi\Pictures
  → 属性
  → 【位置】选项卡        ← 关键，平时注意不到
  → 移动 → 选 D:\Media\Pictures
  → 确定（系统自动搬移现有内容）
```

对 `Pictures` / `Videos` / `Music` / `Documents` / `Downloads` 都适用。

**这个方案很正统，但它有个硬性限制：目标目录必须不存在或为空。**

而 `_CDrive` 重组时，`D:\_CDrive\Users\raoxi\Pictures\Screenshots` 已经被建好了
（Screenshots 原本就是个 junction，重组脚本会先把它搬进去）。**目标非空 → 位置重定向直接失败。**

**所以最终改用 junction**，效果完全一样：

```
C:\Users\raoxi\Pictures  →  junction  →  D:\_CDrive\Users\raoxi\Pictures
C:\Users\raoxi\Videos    →  junction  →  D:\_CDrive\Users\raoxi\Videos
C:\Users\raoxi\Music     →  junction  →  D:\_CDrive\Users\raoxi\Music
```

唯一差别：系统索引 / 备份工具可能把 junction 当普通链接，而不是「库」。
日常使用没有任何区别——资源管理器左侧的「图片 / 视频 / 音乐」快捷入口照常工作，
这也是你决定把 Media 并进 `_CDrive` 的原因。

### 2.3 并入后 `_CDrive` 的结构

```
D:\_CDrive\
├── Users\raoxi\
│   ├── AppData\           ← 应用数据（51 项迁移的主体）
│   │   ├── Local\
│   │   ├── Roaming\
│   │   ├── LocalLow\
│   │   └── Programs\
│   ├── Pictures\          ← C:\Users\raoxi\Pictures 的落点
│   │   ├── Screenshots\   截图（按年分 2025/ 2026/）
│   │   ├── Wallpaper\     壁纸
│   │   ├── WeChat\        微信保存的图
│   │   ├── Physics\       学科相关
│   │   ├── Tutorial\      教程截图
│   │   └── Other\         杂图
│   ├── Videos\            ← C:\Users\raoxi\Videos 的落点
│   └── Music\             ← C:\Users\raoxi\Music 的落点
│       └── Recordings\    录音
├── ProgramData\
└── Program Files\
```

**`D:\Media` 并入后即可删除**（内容全部搬进 `_CDrive`）。
现有分类（Screenshots / Wallpaper / WeChat / Physics / Tutorial / Other）直接沿用。

### 2.4 `D:\Videos` 那 12.32 GB 怎么办

内容已确认：**全部是剪映做好的成片和素材**，而且**版本重复严重**：

| 文件 | 大小 |
|---|---|
| `真最终成片.mp4` | 1134 MB |
| `最终成片2.mp4` | 1076 MB |
| `最终成片.mp4` | 1079 MB |
| `成片2.mp4` | 841 MB |
| `成片.mp4` | 820 MB |
| 其余片段（图书馆讲 / A楼教室 / 咖啡 / 结尾 …） | ~1 GB |

**这些是「已完成的项目产出」，属于冷数据。** 建议：

1. **先清理重复版本**——只留一个最终版，其余删掉（这一项能省 5 GB 以上）
2. 保留的成片 → 并入 `D:\_CDrive\Users\raoxi\Videos\Edited\`
3. 如果项目彻底结束 → 整体迁到 `E:\Media\Videos\Projects\`

---

## 3. Downloads 重构

### 3.1 现状：27.7 GB，14 个子目录

| 子目录 | 大小 | 实际内容 |
|---|---|---|
| ISO | 11.12 GB | **名不副实**——90% 是 APK（`com.mojang.minecraftpe.apk` 等），只有一个真 ISO |
| 软件安装包 | 8.45 GB | 各种 `.exe`（aTrust / Burp Suite / BootMagix / 酷安 / 酷狗 / PCL…） |
| 压缩文件 | 6.78 GB | 各种 zip（charles / HiJson / jetbrains-crack / BinaryNinja…） |
| 工具集 | 0.97 GB | JetBrainsMono 字体 / ventoy / OpenSpeedy / 公式编辑器 |
| 待清理 | 0.19 GB | 空壳（1 / CSP38-down / default / DwnlData / 21211.txt） |
| 代码文件 | 0.10 GB | CTF 脚本（chal.py / main.cpp）、`cipher.txt`、Miniforge 安装脚本 |
| 文档资料 | 0.05 GB | 扫描文稿 / 申请表 / 竞赛手册 / 录取通知 |
| 实验与课程 | 0.04 GB | 实验数据 / 六级准考证 / 离散数学 / 课程列表 |
| 扩展插件 | 0.01 GB | `.crx`（Chrome）+ `.vsix`（VSCode） |
| 图片 / 文本 / 网页 / 其他 / DwnlData | <0.01 GB | 零散 |

**两个问题**：
1. **95% 是消耗品**（ISO + 安装包 + 压缩包 = 26.3 GB），却和长期资料混在一起
2. **分类维度不统一**——「压缩文件/图片/文本」按格式分，「软件安装包/工具集/实验与课程」按用途分

### 3.2 重构方案（英文命名，11 个目录）

**按你的要求调整**：
- **英文命名**
- **去掉压缩包目录**——Bandizip 有「解压后自动删除源文件」，不需要中转站

```
D:\Downloads\
├── 01-Software\      安装包 / 绿色软件 / 破解工具        .exe .msi .deb
├── 02-ISOs\          装机镜像                            .iso .img
├── 03-MobileApps\    安卓 / iOS 应用包                   .apk .ipa
├── 04-Code\          源码 / 脚本 / 题目文件              .py .cpp .js .sh .go
├── 05-Extensions\    浏览器扩展 / 编辑器扩展 / 插件包    .crx .vsix
├── 06-Documents\     PDF / Office / 文本                 .pdf .docx .xlsx .txt .md
├── 07-Coursework\    课程资料 / 实验数据 / 作业 / 考试
├── 08-Assets\        图片 / 字体 / 图标 / 音效           .png .ttf .ico
├── 09-Media\         影视 / 音乐                         .mp4 .mkv .mp3
├── 10-WebArchive\    保存的网页                          .htm .mht
└── 99-Others\        确实无法归类的（尽量保持为空）
```

**分类原则**：按**用途**分（用途决定去向：装完就删 / 读完归档 / 长期保留），
不按格式分。格式只在必要时才成为一个维度。

**配套动作**：
- 浏览器 / 迅雷 / 夸克 / 百度网盘 / QQ 接收文件的默认目录 → 统一指向 `D:\Downloads` 根目录
- 下载完立刻拖进对应分类（11 个选一个，不会犹豫）
- Bandizip：`选项 → 解压 → 解压完成后` → 设为「**删除源文件**」（默认可能是「询问」）

### 3.3 顺带处理的下载散落点

| 位置 | 大小 | 处置 |
|---|---|---|
| `D:\Downloads` | 27.7 GB | 重构（本方案） |
| `C:\Users\raoxi\Downloads` | ~50 MB | 并入对应分类；**注意里面有重复的「一键系统升级7.0」两份** |
| `D:\qq聊天记录\Downloads` | 待测 | 并入 `ChatData\QQ\recv` |
| `D:\夸克下载` | 2.75 GB | 改指向 `D:\Downloads` 根目录，或归档 |
| `D:\迅雷云盘` | 2.04 GB | 同上 |
| `D:\迅雷下载` | 0 GB | 同上 |
| `D:\BaiduNetdiskDownload` | 1.08 GB | 同上 |
| `D:\Documents\BaiduNetdiskDownload` | 1.60 GB | 同上（**与上一个内容不同，不是重复**） |
| `D:\MCLDownload` | 1.37 GB | Minecraft 资源，独立保留 |

---

## 4. 聊天记录整理

### 4.1 现状：散在 5 处

| 位置 | 内容 | 大小 | 问题 |
|---|---|---|---|
| `C:\Users\raoxi\Documents\xwechat_files` | 微信 4.0 数据 | **0 GB** | **空壳残留** |
| `D:\Documents\xwechat_files` | 微信 4.0 数据 | **3.40 GB** | 真实数据，埋在文档库里 |
| `D:\AppData\WeChat` | 微信配置/缓存 | 1.48 GB | junction 目标（来自 `Roaming\Tencent\xwechat`） |
| `D:\qq聊天记录\Tencent Files` | QQ 数据 | 1.63 GB | 名字随意，位置孤立 |
| `D:\qq聊天记录\Downloads` | QQ 接收的文件 | 待测 | 与 Downloads 体系脱节 |
| `C:\Users\raoxi\AppData\Roaming\QQ` | QQNT 配置 | 0.05 GB | 正常 |
| `D:\AppData\TencentMeeting` | 腾讯会议 | 0.60 GB | junction 目标 |
| `C:\Users\raoxi\Documents\TencentMeeting` | 腾讯会议残留 | 0.10 GB | 疑似空壳 |

### 4.2 先分清两类目录——处理手段完全不同

| 类型 | 位置 | 能否改路径 | 处理手段 |
|---|---|---|---|
| **数据目录**（聊天记录、图片、接收的文件） | `D:\Documents\xwechat_files` 3.40 GB | ✅ 软件设置里能改 | **直接改设置**，不需要 junction |
| **配置目录**（账号、偏好、缓存） | `C:\Users\raoxi\AppData\Roaming\Tencent\xwechat` 1.48 GB | ❌ 软件不给改 | 只能 junction |

**所以「软链接还是归档」这个问题，只对配置目录成立**——而配置目录已经 junction 到 D 盘了，
跟着 `_CDrive` 走就行。

数据目录用**微信自己的设置**改保存位置，比 junction 干净——软件知道真实路径，不会有兼容问题。

### 4.3 数据目录：改到 E 盘 vs 留 D 盘

你的理解是对的：**junction 不是同步，是重定向**。数据只有一份，物理上就在 E 盘。

| | **A. 改到 E 盘** | **B. 留 D 盘 + 定期归档到 E** |
|---|---|---|
| 数据存在哪 | **只在 E 盘**（唯一副本） | D 盘（工作副本）+ E 盘（备份副本） |
| 微信读写速度 | 每次读写走 USB 机械盘 | 走 D 盘 SSD，无感 |
| **拔掉 E 盘** | **微信立即不可用**，可能报错甚至重建空目录 | 微信照常工作 |
| 占 D 盘空间 | 0 | 3.40 GB 且持续增长 |
| 数据安全 | E 盘坏 = 全丢 | 两份 |

**取舍的关键不是速度，是「E 盘会不会一直插着」。**

**建议 B**：`xwechat_files` 里数据库和媒体文件混在一起——SQLite 是高频随机读写（机械盘最弱项），
图片视频是顺序读写（机械盘强项）。放机械盘等于让数据库陪着媒体一起变慢。3.4 GB 不值得冒这个险。

**如果选 A**：拔盘前必须先完全退出微信/QQ，否则数据库可能损坏。

### 4.4 目标结构

```
D:\ChatData\
├── WeChat\
│   ├── xwechat_files\     ← 数据目录（微信设置里指向这里，3.40 GB）
│   └── config\            ← 配置目录（原 D:\AppData\WeChat，1.48 GB）
├── QQ\
│   ├── Tencent Files\     ← 数据目录（QQ 设置里指向这里，1.63 GB）
│   └── recv\              ← QQ 接收的文件（原 D:\qq聊天记录\Downloads）
└── TencentMeeting\        ← 原 D:\AppData\TencentMeeting（0.60 GB）
```

**无论选 A 还是 B，`C:\Users\raoxi\Documents\xwechat_files`（0 GB 空壳）都应该删掉。**

### 4.5 顺带：`Documents` 被程序侵占

`C:\Users\raoxi\Documents` 下躺着 20+ 个**程序自建目录**（Adobe / Visual Studio / PowerShell /
SweetScape / OneNote Notebooks / Outlook 文件 / vivo办公套件 …），是各家软件把「文档库」
当默认工作目录造成的。**不建议删**（有些是程序必需），但以后你的文档别往这塞。

---

## 5. E 盘规划

### 5.1 现状

```
E:\
├── Forensic\Images\   157 GB  ← 取证镜像（window.e01 51GB、平航杯题目 70GB、长安杯 19GB …）
└── Games\
```

### 5.2 一级 + 二级结构

**原则：按需创建，不预建空目录**（用到哪个建哪个）。

```
E:\
├── Archive\                 归档：不再活跃但可能回查
│   ├── Projects\            完结的项目（按项目名分子目录）
│   ├── Documents\           历史文档
│   └── Misc\
│
├── Media\                   媒体仓库
│   ├── Movies\              电影
│   ├── Series\              剧集
│   ├── Music\               音乐
│   ├── Pictures\            图片素材库
│   └── Videos\              成片归档（剪映项目完成后放这）
│
├── Software\                软件仓库
│   ├── Installers\          安装包（MYOS 那 17.7 GB 放这）
│   ├── ISOs\                镜像
│   └── Portable\            绿色软件
│
├── ChatArchive\             聊天归档
│   ├── WeChat\              按年月分子目录（2026-10\ 等）
│   └── QQ\
│
├── Forensic\                取证（保留现有）
│   ├── Images\              镜像（已有 157 GB）
│   ├── Cases\               案例数据
│   └── Tools\               工具 / 字典
│
├── Coursework\              课程
│   └── （按学期：2026-Autumn\ 等）
│
├── Backup\                  备份
│   ├── Configs\             配置文件备份
│   └── System\              系统镜像 / 还原点
│
└── Games\                   （保留现有）
```

**不用数字前缀**——以后新增类别直接按字母序插入（`Archive` / `Assets` / `Backup` …），
不用重排编号。

**现有 `E:\Forensic\` 建议保留原样**——157 GB 移动一次要很久，收益不大。

---

## 6. 迁移方法（回答「怎么迁」）

**三种场景，方法完全不同。**

### 6.1 同盘搬迁（D 盘内部重组）

用于：`_CDrive` 重组、Downloads 重构、`D:\Videos` 并入 `D:\Media\Videos`

```
move "D:\AppData"  "D:\_CDrive\Users\raoxi\AppData"
```

**只改文件系统索引，不复制数据，秒级完成。** 这是 `_CDrive` 方案能快速落地的根本原因。

### 6.2 跨盘搬迁（D → E，冷数据外迁）

用于：Downloads 消耗品、剪映成片、安装包

**必须真实复制**，速度受 USB 机械盘限制（约 100–150 MB/s）。10 GB ≈ 1–2 分钟。

流程（三步，不要省中间那步）：

```
① 复制   robocopy "D:\源" "E:\目标" /E /COPY:DAT /R:2 /W:2
② 校验   对比文件数 + 总大小，确认一致
③ 删源   确认无误后再删
```

**不要用 `/MOVE`**——它边复制边删，中途失败或断电会丢数据。分开做才安全。

### 6.3 增量同步（定期归档 / 备份）

用于：聊天记录定期归档到 E、配置备份

```
robocopy "D:\ChatData" "E:\04-ChatArchive" /E /XO     # 只复制「源比目标新」的文件
robocopy "D:\ChatData" "E:\04-ChatArchive" /MIR       # 镜像：严格一致，会删目标多余文件
```

**这是定期执行的，不是一次性的。**

### 6.4 所以「直接增量迁移？」的答案是

| 场景 | 方法 | 说明 |
|---|---|---|
| 一次性搬迁 | **全量复制** | E 盘还没有这些数据，无所谓「增量」 |
| 定期归档 | **增量同步** | 只同步变化的部分 |
| D 盘内部重组 | **同盘 move** | 秒级，不复制 |

---

## 7. 空间回收清单

| 项 | 大小 | 处置 | 风险 |
|---|---|---|---|
| `D:\AppStore` | 17.7 GB | MYOS 安装包 → 挪 `E:\03-Software\Installers` | 低 |
| `D:\Videos\剪映` 重复版本 | ~5 GB | 只留最终版，其余删 | **中**（需你确认哪版是最终） |
| `D:\Downloads\ISO` | 11.1 GB | 装完即删 / 挪 E | 低 |
| `D:\Downloads\软件安装包` | 8.45 GB | 同上 | 低 |
| `D:\Downloads\压缩文件` | 6.78 GB | 解压完即删 | 低 |
| `D:\Temp` | 10.6 GB | 清空 | 低 |
| `D:\Cache` | 3.8 GB | 可再生（Steam/npm/uv/dotcache） | 低 |
| `D:\DeliveryOptimization` | 1.13 GB | 清空 | 低 |
| `D:\$RECYCLE.BIN` + `C:\$Recycle.Bin` | 1.76 GB | 清空 | 低 |
| 残留空壳 `D:\c d Local AppCache Program` | 1.4 GB | 删 | 低（已确认无 junction 引用） |
| `C:\Users\raoxi\.lmstudio` | 18.2 GB | 模型挪 D/E（LM Studio 设置里改） | 低 |
| `C:\Users\raoxi\.android` | 13.5 GB | AVD/SDK 挪 D | 中（需改 IDE 配置） |
| `D:\ProgramData\Lenovo\CreatorZone` | 18.3 GB | 你说不急，暂不动 | — |

**合计可回收约 90 GB**（不含 CreatorZone / .lmstudio / .android）。

---

## 8. 工具脚本

三个脚本放在 `tools/`，**全部默认 dry-run**，加 `--execute` 才真正动手。

| 脚本 | 作用 | 关键安全设计 |
|---|---|---|
| `reorganize_cdrive.py` | `_CDrive` 重组：51 个 junction 目标搬家 + 重建链接 | 执行前自动快照；失败自动回滚；`--rollback` 一键反向恢复 |
| `migrate_userlibs.py` | Pictures / Videos / Music 并入 `_CDrive` | 同名冲突跳过不覆盖；只删已搬空的目录 |
| `migrate_to_e.py` | 冷数据 D → E 外迁 | 复制 → 校验 → 删源三步分离，校验不过绝不删源 |

```bash
cd D:\Projects\CDriveCleaner

# 1) 先看计划（不改任何东西）
python tools/reorganize_cdrive.py

# 2) 拿单项试点（选一个不重要的）
python tools/reorganize_cdrive.py --execute --only NGR

# 3) 试点没问题再全量（跳过需管理员的两项）
python tools/reorganize_cdrive.py --execute --skip-admin

# 4) 用户库并入
python tools/migrate_userlibs.py --execute

# 5) 冷数据外迁
python tools/migrate_to_e.py --list
python tools/migrate_to_e.py --src "D:\AppStore" --dst "E:\Software\Installers\MYOS" --execute
```

**出问题怎么办**：`--rollback` 读执行日志反向恢复。

```bash
python tools/reorganize_cdrive.py --rollback "logs/reorganize_20261007-013000.log"
```

---

## 9. 执行顺序

| 阶段 | 内容 | 前置条件 | 风险 |
|---|---|---|---|
| **1** | 空间回收（第 7 节，从零风险项开始） | 无 | 低 |
| **2** | `_CDrive` 重组（51 项） | **关闭 Chrome / VSCode / 微信 / 剪映等** | 中（有回滚） |
| **3** | 用户库并入 `_CDrive` | 无 | 中（有 dry-run） |
| **4** | Downloads 重构 | 确认 Bandizip 设置 | 低 |
| **5** | 聊天记录收口 | 关闭微信 / QQ | 低 |
| **6** | E 盘目录建立 + 冷数据外迁 | E 盘在线 | 低（先复制后删） |
| **7** | `.lmstudio` / `.android` 迁移 | 关闭对应程序 | 中 |

**第 2 步是整个方案里唯一需要「关应用」的环节**，也是唯一可能失败重试的环节。
建议单独找一段时间做，先跑 `--only` 试点。

---

## 10. 执行前检查清单

- [ ] 关闭 Chrome / VSCode / Trae / 微信 / QQ / 剪映 / 豆包 / Steam / IDM / JetBrains IDE
- [ ] 确认 E 盘已插好（如需做外迁）
- [ ] 跑一次全量 dry-run，人工核对 51 项映射
- [ ] 试点单项，验证通过
- [ ] 记下 `logs/` 下的快照与执行日志路径

---

## 11. 待你拍板

1. **聊天记录**：选 A（改到 E 盘）还是 B（留 D 盘 + 定期归档，推荐）？
2. **`D:\Videos\剪映` 的多个版本**：哪一版是最终版？其余的删还是留？
3. **第 2 步什么时候做**（需要关应用）——现在、还是另找时间？
