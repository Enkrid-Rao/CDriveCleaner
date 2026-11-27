#Requires -Version 5.1
<#
.SYNOPSIS
    CDriveCleaner 一键发布：打包 → 推送 main 与标签 → 创建/完成 GitHub Release。

.DESCRIPTION
    开发侧已经：改好版本号、写好发布说明、commit 并打过标签 v<版本>。
    这条命令负责剩下的事（不跑测试、不改版本号）：
      1. 打包（PyInstaller + Inno Setup）
      2. 生成 SHA256SUMS
      3. 推送 main 与 v<版本>
      4. 创建 Release；如果已有草稿（上传中断留下的），补传资产并正式发布

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish.ps1 -Version 2.3.9

.EXAMPLE
    # 跳过打包（dist 里已经有包时）
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish.ps1 -Version 2.3.9 -SkipBuild
#>
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$NotesFile = "",
    [string]$Title = "",
    [string]$Proxy = "http://127.0.0.1:7899",
    [switch]$SkipBuild,
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'

function Fail([string]$text) {
    Write-Host ""
    Write-Host "!! $text" -ForegroundColor Red
    exit 1
}

function Step([string]$text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
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

# 仓库根目录
$dir = $PSScriptRoot
while ($dir) {
    if (Test-Path (Join-Path $dir '.git')) { break }
    $parent = Split-Path $dir -Parent
    if ($parent -eq $dir) { break }
    $dir = $parent
}
if (-not $dir) { Fail "找不到仓库根目录" }
Set-Location $dir

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Fail "版本号格式应为 x.y.z，例如 2.3.9（收到：$Version）"
}
$tag = "v$Version"
if ($NotesFile -eq "") { $NotesFile = "docs\RELEASE-NOTES-$tag.md" }
if ($Title -eq "") { $Title = "CDriveCleaner $tag" }
if (-not (Test-Path (Join-Path $dir $NotesFile))) { Fail "发布说明不存在：$NotesFile" }

# 版本号一致性（打包脚本也会校验）
$codeVersion = (python -c "from cdc.version import __version__; print(__version__)").Trim()
if ($LASTEXITCODE -ne 0) { Fail "无法读取 cdc/version.py（python 不可用？）" }
if ($codeVersion -ne $Version) {
    Fail "版本号不一致：源码是 $codeVersion，命令是 $Version。请让开发侧先改版本并提交。"
}

# 标签必须已在本地（推送权限归发布者）
git rev-parse -q --verify "refs/tags/$tag" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "本地没有标签 $tag，请让开发侧先提交并打标签" }

$env:GIT_TERMINAL_PROMPT = '0'
$env:HTTPS_PROXY = $Proxy
$env:HTTP_PROXY = $Proxy
$env:NO_PROXY = 'localhost,127.0.0.1,::1'

# ---------------------------------------------------------------------------
if ($SkipBuild) {
    Step "跳过打包（-SkipBuild）"
} else {
    Step "打包 CDriveCleaner $tag（约 2-3 分钟）"
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dir 'packaging\build.ps1')
    if ($LASTEXITCODE -ne 0) { Fail "打包失败" }
}

$setup = Join-Path $dir "dist\CDriveCleaner-Setup-$tag.exe"
$portable = Join-Path $dir "dist\CDriveCleaner-Portable-$tag.zip"
foreach ($file in @($setup, $portable)) {
    if (-not (Test-Path $file)) { Fail "打包产物缺失：$file" }
    if ((Get-Item $file).Length -lt 1MB) { Fail "打包产物异常（<1MB）：$file" }
}

Step "生成 SHA256SUMS"
$setupHash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
$portHash = (Get-FileHash -LiteralPath $portable -Algorithm SHA256).Hash
$sumsFile = Join-Path $dir "dist\CDriveCleaner-$tag-SHA256SUMS.txt"
@(
    "$setupHash  CDriveCleaner-Setup-$tag.exe"
    "$portHash  CDriveCleaner-Portable-$tag.zip"
) | Set-Content -LiteralPath $sumsFile -Encoding ASCII
Write-Host "    Setup    $setupHash" -ForegroundColor Gray
Write-Host "    Portable $portHash" -ForegroundColor Gray

Step "推送 main 与 $tag（代理 $Proxy）"
Invoke-WithRetry { git push origin main } 'git push main'
Invoke-WithRetry { git push origin $tag } "git push $tag"

# 找到该标签的 Release（可能不存在、可能是上传中断留下的草稿）
function Get-ReleaseByTag([string]$tagName) {
    $page = 1
    while ($page -le 3) {
        $json = gh api "repos/Enkrid-Rao/CDriveCleaner/releases?per_page=100&page=$page" 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $list = @($json | ConvertFrom-Json)
        if ($list.Count -eq 0) { return $null }
        $found = $list | Where-Object { $_.tag_name -eq $tagName } | Select-Object -First 1
        if ($found) { return $found }
        $page++
    }
    return $null
}

$assets = @($setup, $portable, $sumsFile)
$forceDraft = [bool]$Draft
$existing = Get-ReleaseByTag $tag

if ($existing) {
    $state = if ($existing.draft) { "草稿" } else { "已发布" }
    Step "发现已有 Release（$state），补传资产"
    Invoke-WithRetry { gh release upload $tag @assets --clobber } 'gh release upload' 2 8
    if ($existing.draft -and -not $forceDraft) {
        Step "将草稿转为正式发布"
        Invoke-WithRetry { gh release edit $tag --draft=false --latest } 'gh release edit' 2 5
    } elseif ($forceDraft) {
        Write-Host "    保持草稿状态（-Draft）" -ForegroundColor Yellow
    }
} else {
    Step "创建 GitHub Release"
    $ghArgs = @('release', 'create', $tag) + $assets + @(
        '--title', $Title, '--notes-file', (Join-Path $dir $NotesFile), '--verify-tag'
    )
    if ($forceDraft) { $ghArgs += '--draft' } else { $ghArgs += '--latest' }
    Invoke-WithRetry { gh @ghArgs } 'gh release create' 2 8
}

Write-Host ""
Write-Host "发布完成：https://github.com/Enkrid-Rao/CDriveCleaner/releases/tag/$tag" -ForegroundColor Green
