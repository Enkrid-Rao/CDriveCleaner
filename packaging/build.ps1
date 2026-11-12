# CDriveCleaner v2 构建脚本
# 用法（在仓库根目录）：
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipInstaller
#
# 产物：
#   dist\CDriveCleaner\CDriveCleaner.exe              安装版 / 便携版共用的 onedir 载荷
#   dist\CDriveCleaner-Portable-v2.0.0.zip            便携版（解压即用）
#   dist\CDriveCleaner-Setup-v2.0.0.exe               安装版（Inno Setup）

param(
    [switch]$SkipInstaller,
    [switch]$SkipPortable,
    [switch]$NoClean
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = '2.0.0'
$dist = Join-Path $root 'dist'
$payload = Join-Path $dist 'CDriveCleaner'
$exe = Join-Path $payload 'CDriveCleaner.exe'
$iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'

function Step($text) { Write-Host "`n== $text ==" -ForegroundColor Cyan }

Step "环境检查"
python --version
python -m PyInstaller --version
if (-not (Test-Path $iscc)) {
    Write-Warning "未找到 Inno Setup: $iscc（安装包将被跳过）"
    $SkipInstaller = $true
}

if (-not $NoClean) {
    Step "清理旧产物"
    Remove-Item -Recurse -Force (Join-Path $root 'build') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $payload -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $dist 'portable') -ErrorAction SilentlyContinue
    foreach ($stale in @('CDriveCleaner.exe', 'config.json', '_temp_script.ps1', 'logs')) {
        Remove-Item -Recurse -Force (Join-Path $dist $stale) -ErrorAction SilentlyContinue
    }
    Remove-Item -Force (Join-Path $dist "CDriveCleaner-Portable-v$version.zip") -ErrorAction SilentlyContinue
    Remove-Item -Force (Join-Path $dist "CDriveCleaner-Setup-v$version.exe") -ErrorAction SilentlyContinue
}

Step "PyInstaller onedir 构建"
python -m PyInstaller --noconfirm --clean packaging\CDriveCleaner.spec
if (-not (Test-Path $exe)) { throw "构建失败：找不到 $exe" }
Write-Host ("载荷大小：{0:N1} MB" -f ((Get-ChildItem $payload -Recurse -File | Measure-Object Length -Sum).Sum / 1MB))

Step "可执行文件自检"
$proc = Start-Process -FilePath $exe -ArgumentList '--self-check' -Wait -PassThru -WindowStyle Hidden
if ($proc.ExitCode -ne 0) { throw "自检失败，退出码 $($proc.ExitCode)" }
Write-Host "自检通过" -ForegroundColor Green

if (-not $SkipPortable) {
    Step "便携版打包"
    $portable = Join-Path $dist 'portable\CDriveCleaner'
    New-Item -ItemType Directory -Force -Path $portable | Out-Null
    Copy-Item -Path (Join-Path $payload '*') -Destination $portable -Recurse -Force
    Set-Content -Path (Join-Path $portable 'portable.flag') -Value 'CDriveCleaner portable mode' -Encoding UTF8
    Copy-Item (Join-Path $root 'README.md') $portable -Force
    Copy-Item (Join-Path $root 'LICENSE') $portable -Force
    Copy-Item (Join-Path $root 'packaging\PORTABLE-README.txt') (Join-Path $portable '使用说明.txt') -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $portable 'docs') | Out-Null
    Copy-Item (Join-Path $root 'docs\screenshots') (Join-Path $portable 'docs\screenshots') -Recurse -Force
    $zip = Join-Path $dist "CDriveCleaner-Portable-v$version.zip"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    $sevenZip = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
    if ($sevenZip) {
        & $sevenZip a -tzip -mx=9 $zip (Join-Path $portable '*') | Out-Null
    } else {
        Compress-Archive -Path (Join-Path $portable '*') -DestinationPath $zip -CompressionLevel Optimal
    }
    Write-Host ("便携包：{0} ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green
}

if (-not $SkipInstaller) {
    Step "安装包编译"
    & $iscc 'packaging\installer.iss'
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败（$LASTEXITCODE）" }
    $setup = Join-Path $dist "CDriveCleaner-Setup-v$version.exe"
    Write-Host ("安装包：{0} ({1:N1} MB)" -f $setup, ((Get-Item $setup).Length / 1MB)) -ForegroundColor Green
}

Step "产物与 SHA256"
Get-ChildItem $dist -File | Where-Object { $_.Name -match 'CDriveCleaner.*\.(exe|zip)$' } | ForEach-Object {
    $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    Write-Host ("{0}`n  {1:N1} MB  {2}" -f $_.Name, ($_.Length / 1MB), $hash)
}

Write-Host "`n完成。" -ForegroundColor Green
