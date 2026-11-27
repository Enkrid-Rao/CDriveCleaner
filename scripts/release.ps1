#Requires -Version 5.1
<#
.SYNOPSIS
    CDriveCleaner 一键发布：改版本号 → 跑测试 → 打包 → 生成校验 → 提交/打标签/推送 → 建 GitHub Release → 校验资产。

.DESCRIPTION
    用法（在仓库根目录或任意目录）：
        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -Version 2.3.9

    发布说明放在 docs\RELEASE-NOTES-v<版本>.md（可用 -NotesFile 指定其它路径）。

    常用参数：
        -DryRun        只检查并打印计划，不动任何文件
        -SkipTests     跳过单元测试（不建议）
        -NoPush        只改版本 + 测试 + 打包 + 本地提交/打标签，不推送、不发 Release
        -AllowDirty    工作区有未提交改动也继续（发布提交会一并带上这些改动）
        -Draft         创建草稿 Release（不发布）
        -Proxy         代理地址，默认 http://127.0.0.1:7899
        -Title         Release 标题，默认 "CDriveCleaner v<版本>"

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\release.ps1 -Version 2.3.9
#>
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$NotesFile = "",
    [string]$Title = "",
    [string]$Proxy = "http://127.0.0.1:7899",
    [switch]$DryRun,
    [switch]$SkipTests,
    [switch]$SkipBuild,
    [switch]$NoPush,
    [switch]$AllowDirty,
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-Step([string]$text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
}

function Write-Ok([string]$text) {
    Write-Host "    [OK] $text" -ForegroundColor Green
}

function Fail([string]$text) {
    Write-Host ""
    Write-Host "!! $text" -ForegroundColor Red
    exit 1
}

function Get-RepoRoot {
    $dir = $PSScriptRoot
    while ($dir) {
        if (Test-Path (Join-Path $dir '.git')) { return $dir }
        $parent = Split-Path $dir -Parent
        if ($parent -eq $dir) { break }
        $dir = $parent
    }
    Fail "找不到仓库根目录（scripts\release.ps1 应在仓库里）"
}

function Save-TextPreserveBom([string]$path, [string]$text) {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $bom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $utf8 = New-Object System.Text.UTF8Encoding($bom)
    [System.IO.File]::WriteAllText($path, $text, $utf8)
}

function Replace-InFile([string]$path, [string]$old, [string]$new) {
    $full = Join-Path $root $path
    if (-not (Test-Path $full)) { Fail "找不到文件：$path" }
    $text = [System.IO.File]::ReadAllText($full)
    if (-not $text.Contains($old)) {
        Fail "$path 里找不到待替换内容：$old"
    }
    Save-TextPreserveBom $full ($text.Replace($old, $new))
    Write-Ok "$path"
}

function Invoke-WithRetry([scriptblock]$action, [string]$what, [int]$tries = 2, [int]$delaySec = 5) {
    for ($i = 1; $i -le $tries; $i++) {
        try {
            & $action
            if ($LASTEXITCODE -ne 0) { throw "$what 退出码 $LASTEXITCODE" }
            return
        } catch {
            if ($i -ge $tries) { throw }
            Write-Host "    $what 失败（$($_.Exception.Message)），$delaySec 秒后重试…" -ForegroundColor Yellow
            Start-Sleep -Seconds $delaySec
        }
    }
}

# ---------------------------------------------------------------------------
$root = Get-RepoRoot
Set-Location $root
$stage = "检查参数"

# 网络请求（git ls-remote / push / gh）统一走代理；api.github.com 直连也快，但代理更稳
$env:GIT_TERMINAL_PROMPT = '0'
$env:HTTPS_PROXY = $Proxy
$env:HTTP_PROXY = $Proxy
$env:NO_PROXY = 'localhost,127.0.0.1,::1'


if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Fail "版本号格式应为 x.y.z，例如 2.3.9（收到：$Version）"
}

$versionPy = Join-Path $root 'cdc\version.py'
$versionText = [System.IO.File]::ReadAllText($versionPy)
$match = [regex]::Match($versionText, '__version__\s*=\s*"(\d+\.\d+\.\d+)"')
if (-not $match.Success) { Fail "无法从 cdc\version.py 读取当前版本号" }
$oldVersion = $match.Groups[1].Value
$sameVersion = ($oldVersion -eq $Version)

$tag = "v$Version"
$oldTag = "v$oldVersion"
if ($NotesFile -eq "") { $NotesFile = "docs\RELEASE-NOTES-$tag.md" }
if (-not (Test-Path (Join-Path $root $NotesFile))) {
    Fail "发布说明不存在：$NotesFile`n请先把发布说明写到该文件，或用 -NotesFile 指定。"
}
if ($Title -eq "") { $Title = "CDriveCleaner $tag" }

# 标签已存在？
git rev-parse -q --verify "refs/tags/$tag" 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { Fail "本地已存在标签 $tag，换个版本号或先删除标签" }
$remoteTag = (git ls-remote --tags origin $tag 2>$null)
if ($remoteTag) { Fail "远端已存在标签 $tag，换个版本号或先删除远端标签" }

# 工作区检查
$dirty = @(git status --porcelain)
if ($dirty.Count -gt 0 -and -not $AllowDirty -and -not $DryRun) {
    Write-Host "工作区有未提交改动：" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Fail "如果用 -AllowDirty，这些改动会一起进入发布提交；否则请先提交或还原。"
}

$changelog = Join-Path $root 'CHANGELOG.md'
$changelogText = [System.IO.File]::ReadAllText($changelog)
if ($sameVersion) {
    if (-not $changelogText.Contains("## [$Version]")) {
        Fail "版本号已是 $Version，但 CHANGELOG.md 里没有 '## [$Version]' 段落"
    }
} elseif (-not $changelogText.Contains('## [未发布]')) {
    Fail "CHANGELOG.md 里没有 '## [未发布]' 段落，无法自动归档本次发布说明"
}

if ($SkipBuild -and -not $NoPush) {
    Fail "-SkipBuild 只能配合 -NoPush 使用（它只验证版本/提交逻辑，不产出可发布包）"
}

$date = Get-Date -Format 'yyyy-MM-dd'
$plan = @(
    $(if ($sameVersion) { "版本：$Version（已是目标值，跳过改版本号，标签 $tag）" }
      else { "版本：$oldVersion -> $Version（标签 $tag）" }),
    "发布说明：$NotesFile",
    "标题：$Title",
    "步骤：改版本号 -> $(if ($SkipTests) { '跳过测试' } else { '跑测试' }) -> 打包 -> 生成 SHA256 -> 提交/打标签",
    $(if ($NoPush) { "结束：不推送（-NoPush）" } else { "推送 main + $tag -> gh release create（$(if ($Draft) { '草稿' } else { '正式，Latest' })）-> 校验资产" })
)

if ($DryRun) {
    Write-Step "DryRun：以下是将要执行的操作（不会修改任何文件）"
    $plan | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    Write-Host "工作区改动：$($dirty.Count) 项" -ForegroundColor Yellow
    exit 0
}

Write-Step "开始发布 CDriveCleaner $tag"

# 1) 版本号
if ($sameVersion) {
    Write-Step "1/7 版本号已是 $Version，跳过更新（继续测试 / 打包 / 提交）"
} else {
Write-Step "1/7 更新版本号"
Replace-InFile 'cdc\version.py' "__version__ = `"$oldVersion`"" "__version__ = `"$Version`""
Replace-InFile 'packaging\build.ps1' "`$version = '$oldVersion'" "`$version = '$Version'"
Replace-InFile 'packaging\installer.iss' "#define MyAppVersion `"$oldVersion`"" "#define MyAppVersion `"$Version`""

$tupleOld = "(" + ($oldVersion -replace '\.', ', ') + ", 0)"
$tupleNew = "(" + ($Version -replace '\.', ', ') + ", 0)"
Replace-InFile 'packaging\version_info.txt' $tupleOld $tupleNew
Replace-InFile 'packaging\version_info.txt' "'$oldVersion'" "'$Version'"

# README 资源名 / 文档链接
$readmePath = Join-Path $root 'README.md'
$readmeText = [System.IO.File]::ReadAllText($readmePath)
if ($readmeText.Contains($oldTag)) {
    Save-TextPreserveBom $readmePath ($readmeText.Replace($oldTag, $tag))
    Write-Ok "README.md"
}

# CHANGELOG 归档
$changelogNew = $changelogText.Replace('## [未发布]', "## [$Version] - $date")
Save-TextPreserveBom $changelog $changelogNew
Write-Ok "CHANGELOG.md -> [$Version] - $date"

}
# 2) 测试
if ($SkipTests) {
    Write-Step "2/7 跳过测试（-SkipTests）"
} else {
    Write-Step "2/7 运行单元测试"
    python -m unittest discover -t . -s tests
    if ($LASTEXITCODE -ne 0) { Fail "测试失败，已中止发布" }
    Write-Ok "测试通过"
}

# 3) 打包
if ($SkipBuild) {
    Write-Step "3/7 跳过打包（-SkipBuild，仅验证版本与提交流程）"
    Write-Step "5/7 提交并打标签"
    git add -A
    git commit -m "release: $tag"
    if ($LASTEXITCODE -ne 0) { Fail "git commit 失败" }
    git tag -a $tag -m "CDriveCleaner $tag"
    if ($LASTEXITCODE -ne 0) { Fail "git tag 失败" }
    Write-Ok "已本地提交并创建标签 $tag（未打包、未推送）"
    exit 0
}
Write-Step "3/7 打包（PyInstaller + Inno Setup）"
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'packaging\build.ps1')
if ($LASTEXITCODE -ne 0) { Fail "打包失败，已中止发布" }

$setup = Join-Path $root "dist\CDriveCleaner-Setup-$tag.exe"
$portable = Join-Path $root "dist\CDriveCleaner-Portable-$tag.zip"
foreach ($file in @($setup, $portable)) {
    if (-not (Test-Path $file)) { Fail "打包产物缺失：$file" }
    if ((Get-Item $file).Length -lt 1MB) { Fail "打包产物异常（<1MB）：$file" }
}
Write-Ok "产物已生成"

# 4) 校验 + 文档
Write-Step "4/7 生成 SHA256 与发布文档"
$setupHash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
$portHash = (Get-FileHash -LiteralPath $portable -Algorithm SHA256).Hash
$sumsFile = Join-Path $root "dist\CDriveCleaner-$tag-SHA256SUMS.txt"
@(
    "$setupHash  CDriveCleaner-Setup-$tag.exe"
    "$portHash  CDriveCleaner-Portable-$tag.zip"
) | Set-Content -LiteralPath $sumsFile -Encoding ASCII
Write-Ok "dist\CDriveCleaner-$tag-SHA256SUMS.txt"

$setupMb = [math]::Round((Get-Item $setup).Length / 1MB, 1)
$portMb = [math]::Round((Get-Item $portable).Length / 1MB, 1)
$releaseDoc = @"
# CDriveCleaner $tag 发布说明

## 产物

| 文件 | 大小 | SHA256 |
|---|---|---|
| ``CDriveCleaner-Setup-$tag.exe`` | $setupMb MB | ``$setupHash`` |
| ``CDriveCleaner-Portable-$tag.zip`` | $portMb MB | ``$portHash`` |
| ``CDriveCleaner-$tag-SHA256SUMS.txt`` | — | — |

哈希值也可从 ``CDriveCleaner-$tag-SHA256SUMS.txt`` 核对；未做代码签名，SmartScreen 可能提示。

## 安装

``````powershell
.\CDriveCleaner-Setup-$tag.exe
``````

安装版数据目录：``%LOCALAPPDATA%\CDriveCleaner\``。

## 便携版

解压整个 zip，保留 ``_internal`` 目录，双击 ``CDriveCleaner.exe``。

## 自动更新

v2.2.0 及以上会在启动时检查 GitHub Release；下载更新包时自动在本机代理与直连之间切换并记忆线路。

## 本版变更

详见 ``docs/RELEASE-NOTES-$tag.md``。

## 构建环境

- Python 3.14.x / PyInstaller / Inno Setup 6.7.3 / 7-Zip
- 版本一致性由 ``packaging/build.ps1`` 校验（``cdc/version.py``、``installer.iss``、``version_info.txt``）
"@
$releaseDocPath = Join-Path $root "docs\RELEASE-$tag.md"
[System.IO.File]::WriteAllText($releaseDocPath, $releaseDoc, (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "docs\RELEASE-$tag.md"

# 5) 提交 / 打标签
Write-Step "5/7 提交并打标签"
git add -A
git commit -m "release: $tag"
if ($LASTEXITCODE -ne 0) { Fail "git commit 失败（可能没有可提交内容）" }
git tag -a $tag -m "CDriveCleaner $tag"
if ($LASTEXITCODE -ne 0) { Fail "git tag 失败" }
Write-Ok "已提交并创建标签 $tag"

if ($NoPush) {
    Write-Step "完成（-NoPush）：未推送"
    Write-Host "    推送命令：" -ForegroundColor Yellow
    Write-Host "      git push origin main; git push origin $tag" -ForegroundColor Yellow
    exit 0
}

# 6) 推送
Write-Step "6/7 推送到 GitHub（代理：$Proxy）"
Invoke-WithRetry { git push origin main } 'git push main'
Invoke-WithRetry { git push origin $tag } "git push $tag"
Write-Ok "main 与 $tag 已推送"

# 7) 创建 Release
Write-Step "7/7 创建 GitHub Release 并校验"
$assets = @($setup, $portable, $sumsFile)
$notes = Join-Path $root $NotesFile
$ghArgs = @('release', 'create', $tag) + $assets + @(
    '--title', $Title, '--notes-file', $notes, '--verify-tag'
)
if (-not $Draft) { $ghArgs += '--latest' }
if ($Draft) { $ghArgs += '--draft' }

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail "找不到 gh CLI，请先安装/登录 GitHub CLI"
}
try {
    Invoke-WithRetry { gh @ghArgs } 'gh release create' 2 8
} catch {
    $existing = gh api "repos/Enkrid-Rao/CDriveCleaner/releases/tags/$tag" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "    Release 已存在，改为补传/覆盖资产…" -ForegroundColor Yellow
    Invoke-WithRetry { gh release upload $tag @assets --clobber } 'gh release upload' 2 8
}

# 校验：资产数量与 digest
Start-Sleep -Seconds 2
$releaseJson = gh api "repos/Enkrid-Rao/CDriveCleaner/releases/tags/$tag" 2>$null
if ($LASTEXITCODE -ne 0) { Fail "Release 创建后无法查询（可手动：gh release view $tag）" }
$release = $releaseJson | ConvertFrom-Json
if (@($release.assets).Count -ne 3) {
    Fail "Release 资产数量异常：$((@($release.assets)).Count)（应为 3）"
}
$localHashes = @{ "CDriveCleaner-Setup-$tag.exe" = $setupHash; "CDriveCleaner-Portable-$tag.zip" = $portHash }
foreach ($asset in $release.assets) {
    if ($asset.name -like '*.exe' -or $asset.name -like '*.zip') {
        $expected = $localHashes[$asset.name]
        if ($expected -and $asset.digest -ne "sha256:$($expected.ToLower())") {
            Fail "资产 digest 不一致：$($asset.name)"
        }
    }
}
Write-Ok "Release 已创建，3 个资产 digest 校验通过"
Write-Host ""
Write-Host "发布完成：https://github.com/Enkrid-Rao/CDriveCleaner/releases/tag/$tag" -ForegroundColor Green
Write-Host "安装版：$setupMb MB  Portable：$portMb MB" -ForegroundColor Green
Write-Host ""
Write-Host "本机已装版本需要的话在应用内「检查更新」即可。" -ForegroundColor Gray
