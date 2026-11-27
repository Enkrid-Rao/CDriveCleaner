#Requires -Version 5.1
<#
.SYNOPSIS
    CDriveCleaner 快速发布：推送已提交的 main 与标签，然后创建 GitHub Release。

.DESCRIPTION
    前提（由开发侧完成）：
      - 版本号已改好并 commit，标签 v<版本> 已在本地创建
      - dist\ 下已有 CDriveCleaner-Setup-v<版本>.exe 与 CDriveCleaner-Portable-v<版本>.zip
      - docs\RELEASE-NOTES-v<版本>.md 已写好

    这条命令只做三件事：推送 main → 推送标签 → 创建 Release（含 3 个资产）。
    不跑测试、不打包、不改版本号。

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\publish.ps1 -Version 2.3.9
#>
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$NotesFile = "",
    [string]$Title = "",
    [string]$Proxy = "http://127.0.0.1:7899",
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

# 最小前置检查
git rev-parse -q --verify "refs/tags/$tag" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { Fail "本地没有标签 $tag，请先让开发侧提交并打标签" }
if (-not (Test-Path (Join-Path $dir $NotesFile))) { Fail "发布说明不存在：$NotesFile" }

$setup = Join-Path $dir "dist\CDriveCleaner-Setup-$tag.exe"
$portable = Join-Path $dir "dist\CDriveCleaner-Portable-$tag.zip"
foreach ($file in @($setup, $portable)) {
    if (-not (Test-Path $file)) { Fail "打包产物缺失：$file（请先让开发侧打包）" }
}

# 校验文件（缺了就现生成，很快）
$sumsFile = Join-Path $dir "dist\CDriveCleaner-$tag-SHA256SUMS.txt"
if (-not (Test-Path $sumsFile)) {
    $setupHash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
    $portHash = (Get-FileHash -LiteralPath $portable -Algorithm SHA256).Hash
    @(
        "$setupHash  CDriveCleaner-Setup-$tag.exe"
        "$portHash  CDriveCleaner-Portable-$tag.zip"
    ) | Set-Content -LiteralPath $sumsFile -Encoding ASCII
}

$env:GIT_TERMINAL_PROMPT = '0'
$env:HTTPS_PROXY = $Proxy
$env:HTTP_PROXY = $Proxy
$env:NO_PROXY = 'localhost,127.0.0.1,::1'

Step "推送 main 与 $tag（代理 $Proxy）"
Invoke-WithRetry { git push origin main } 'git push main'
Invoke-WithRetry { git push origin $tag } "git push $tag"

Step "创建 GitHub Release"
$assets = @($setup, $portable, $sumsFile)
$ghArgs = @('release', 'create', $tag) + $assets + @(
    '--title', $Title, '--notes-file', (Join-Path $dir $NotesFile), '--verify-tag'
)
if ($Draft) { $ghArgs += '--draft' } else { $ghArgs += '--latest' }

try {
    Invoke-WithRetry { gh @ghArgs } 'gh release create' 2 8
} catch {
    $existing = gh api "repos/Enkrid-Rao/CDriveCleaner/releases/tags/$tag" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "    Release 已存在，改为补传/覆盖资产…" -ForegroundColor Yellow
    Invoke-WithRetry { gh release upload $tag @assets --clobber } 'gh release upload' 2 8
}

Write-Host ""
Write-Host "发布完成：https://github.com/Enkrid-Rao/CDriveCleaner/releases/tag/$tag" -ForegroundColor Green
