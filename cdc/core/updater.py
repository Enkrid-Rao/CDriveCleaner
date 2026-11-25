"""自动更新：检查 GitHub Release、下载、校验、安装。

安装版下载 Setup.exe 静默覆盖安装；
便携版下载 portable zip，退出后由 PowerShell 覆盖程序目录并重启。
源码模式只打开发布页，不自动替换。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .. import paths
from ..version import __version__
from .windows import NO_WINDOW, write_json_atomic, read_json

API_URL = "https://api.github.com/repos/Enkrid-Rao/CDriveCleaner/releases/latest"
RELEASE_URL = "https://github.com/Enkrid-Rao/CDriveCleaner/releases/latest"
CHECK_INTERVAL = 24 * 3600
USER_AGENT = f"CDriveCleaner/{__version__}"


@dataclass
class UpdateAsset:
    name: str
    url: str
    size: int = 0
    digest: str = ""


@dataclass
class UpdateInfo:
    version: str
    tag: str
    title: str
    body: str
    page_url: str
    published_at: str
    assets: list[UpdateAsset] = field(default_factory=list)
    current_version: str = __version__
    portable: bool = False
    source_mode: bool = False

    def asset(self) -> UpdateAsset | None:
        if self.source_mode:
            return None
        wanted = ("portable", ".zip") if self.portable else ("setup", ".exe")
        for asset in self.assets:
            name = asset.name.lower()
            if wanted[0] in name and name.endswith(wanted[1]):
                return asset
        return None

    @property
    def installable(self) -> bool:
        return (not self.source_mode) and self.asset() is not None


def version_tuple(text: str) -> tuple[int, ...]:
    text = (text or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", text.split("-")[0])
    return tuple(int(p) for p in parts[:4]) if parts else (0,)


def is_newer(latest: str, current: str) -> bool:
    a, b = list(version_tuple(latest)), list(version_tuple(current))
    while len(a) < 4:
        a.append(0)
    while len(b) < 4:
        b.append(0)
    return tuple(a) > tuple(b)


def _digest_value(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.lower().startswith("sha256:"):
        raw = raw.split(":", 1)[1]
    return raw.lower()


# ---------------- 网络线路 ----------------
# GitHub 的资产域名（release-assets / objects.githubusercontent.com）在不少网络下
# 直连会被 reset，而 api.github.com 直连通常没问题。所以下载要能自动找到本机代理。

PROXY_CANDIDATES = (
    "http://127.0.0.1:7899",
    "http://127.0.0.1:7898",
    "http://127.0.0.1:7890",
    "http://127.0.0.1:10809",
    "http://127.0.0.1:1080",
)
DOWNLOAD_ROUNDS = 2


class DownloadCanceled(RuntimeError):
    """用户取消下载。"""


def _proxy_opener(proxy: str) -> Any:
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))


def _direct_opener() -> Any:
    # 显式清空代理，避免环境变量 / 系统代理把「直连」也劫走
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _env_proxy() -> str:
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _routes(*, download: bool) -> list[tuple[str, Any]]:
    """按优先级返回 (线路名, opener)。

    下载：上次成功的代理 → 环境变量代理 → 常见本机代理端口 → 直连。
    检查更新：直连 → 环境变量代理 → 上次成功的代理 → 常见端口。
    """
    remembered = str(load_state().get("download_proxy") or "").strip()
    env = _env_proxy()
    routes: list[tuple[str, Any]] = []

    def add(proxy: str) -> None:
        if proxy and all(name != proxy for name, _opener in routes):
            routes.append((proxy, _proxy_opener(proxy)))

    if download:
        add(remembered)
        add(env)
        for proxy in PROXY_CANDIDATES:
            add(proxy)
        routes.append(("direct", _direct_opener()))
    else:
        routes.append(("direct", _direct_opener()))
        add(env)
        add(remembered)
        for proxy in PROXY_CANDIDATES:
            add(proxy)
    return routes


def fetch_latest_release(api_url: str | None = None, timeout: int = 15) -> dict[str, Any]:
    url = api_url or os.environ.get("CDC_UPDATE_API", "").strip() or API_URL
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    errors: list[str] = []
    for name, opener in _routes(download=False):
        try:
            request = urllib.request.Request(url, headers=headers)
            with opener.open(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 换下一条线路
            errors.append(f"{name}: {exc}")
    raise RuntimeError("检查更新失败（直连与代理都不通）：" + "；".join(errors[:4]))


def parse_release(raw: dict[str, Any], current: str = __version__,
                  portable: bool | None = None) -> UpdateInfo | None:
    tag = str(raw.get("tag_name") or "").strip()
    version = tag.lstrip("vV")
    if not version or not is_newer(version, current):
        return None
    assets = []
    for row in raw.get("assets") or []:
        assets.append(UpdateAsset(
            name=str(row.get("name") or ""),
            url=str(row.get("browser_download_url") or ""),
            size=int(row.get("size") or 0),
            digest=_digest_value(str(row.get("digest") or "")),
        ))
    return UpdateInfo(
        version=version,
        tag=tag or f"v{version}",
        title=str(raw.get("name") or f"CDriveCleaner {version}"),
        body=str(raw.get("body") or ""),
        page_url=str(raw.get("html_url") or RELEASE_URL),
        published_at=str(raw.get("published_at") or ""),
        assets=assets,
        current_version=current,
        portable=paths.is_portable() if portable is None else portable,
        source_mode=paths.is_source_checkout(),
    )


def check_for_update(current: str = __version__) -> UpdateInfo | None:
    raw = fetch_latest_release()
    return parse_release(raw, current)


# ---------------- check cache ----------------

def _cache_file() -> Path:
    return paths.cache_dir() / "update.json"


def load_state() -> dict[str, Any]:
    return read_json(str(_cache_file()), {}) or {}


def save_state(data: dict[str, Any]) -> None:
    try:
        write_json_atomic(str(_cache_file()), data)
    except OSError:
        pass


def should_auto_check() -> bool:
    state = load_state()
    try:
        last = float(state.get("last_check") or 0)
    except (TypeError, ValueError):
        last = 0
    return (time.time() - last) >= CHECK_INTERVAL


def mark_checked() -> None:
    state = load_state()
    state["last_check"] = time.time()
    save_state(state)


def skipped_version() -> str:
    return str(load_state().get("skipped_version") or "")


def mark_skipped(version: str) -> None:
    state = load_state()
    state["skipped_version"] = version
    save_state(state)


# ---------------- download ----------------

def _stream_download(opener: Any, asset: UpdateAsset, part: Path, final: Path,
                     progress: Callable[[int, int], None] | None,
                     cancel: Callable[[], bool] | None) -> None:
    part.unlink(missing_ok=True)
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    total = asset.size
    done = 0
    digest = hashlib.sha256()
    with opener.open(request, timeout=30) as response:
        try:
            total = int(response.headers.get("Content-Length") or total or 0)
        except (TypeError, ValueError):
            pass
        with open(part, "wb") as f:
            while True:
                if cancel and cancel():
                    raise DownloadCanceled("下载已取消")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if total and done != total:
        raise RuntimeError(f"下载不完整：{done}/{total} 字节")
    if asset.digest and digest.hexdigest().lower() != asset.digest:
        raise RuntimeError("SHA256 校验失败")
    os.replace(part, final)


def download_asset(asset: UpdateAsset, dest_dir: str | Path,
                   progress: Callable[[int, int], None] | None = None,
                   cancel: Callable[[], bool] | None = None) -> str:
    """下载更新包：自动在「直连 / 上次成功的代理 / 常见本机代理」之间切换重试。

    GitHub 的资产域名在部分网络下直连必被 reset；这里会把成功的线路记下来，
    下次直接用，不再每次都先卡在直连上。
    """
    if not asset.digest:
        raise RuntimeError("更新包缺少 SHA256 校验值，已拒绝自动下载")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / asset.name
    errors: list[str] = []

    for round_index in range(DOWNLOAD_ROUNDS):
        for name, opener in _routes(download=True):
            part = final.with_name(f"{final.name}.part{round_index}")
            try:
                _stream_download(opener, asset, part, final, progress, cancel)
            except DownloadCanceled:
                part.unlink(missing_ok=True)
                raise
            except Exception as exc:  # noqa: BLE001 - 换下一条线路
                part.unlink(missing_ok=True)
                errors.append(f"{name}: {exc}")
                continue
            if name != "direct":
                state = load_state()
                if state.get("download_proxy") != name:
                    state["download_proxy"] = name
                    save_state(state)
            return str(final)

    raise RuntimeError("下载失败（已尝试直连与本机代理）：" + "；".join(errors[:6]))


# ---------------- install ----------------

_INSTALLED_SCRIPT = r"""
param([int]$AppPid, [string]$Installer, [string]$AppDir, [string]$Exe)
$log = Join-Path $env:TEMP "CDriveCleaner_update.log"
function Write-Log($m) { Add-Content -LiteralPath $log -Value ("[{0}] {1}" -f (Get-Date -Format s), $m) }
try {
    for ($i = 0; $i -lt 240; $i++) {
        if (-not (Get-Process -Id $AppPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    Write-Log "run installer $Installer"
    $p = Start-Process -FilePath $Installer -ArgumentList @('/SILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS','/FORCECLOSEAPPLICATIONS') -PassThru -Wait
    Write-Log "installer exit $($p.ExitCode)"
    if ($p.ExitCode -eq 0) {
        Start-Process -FilePath $Exe -WorkingDirectory $AppDir
    }
} catch {
    Write-Log "ERROR: $_"
}
"""


def apply_installed(installer: str) -> tuple[bool, str]:
    if not paths.is_frozen():
        return False, "源码模式不支持自动安装"
    app_dir = str(paths.executable_dir())
    exe = sys.executable
    script = paths.jobs_dir().parent / "updates" / "apply_installed.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_INSTALLED_SCRIPT, encoding="utf-8-sig")
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", str(script),
             "-AppPid", str(os.getpid()), "-Installer", installer,
             "-AppDir", app_dir, "-Exe", exe],
            creationflags=NO_WINDOW,
            cwd=str(script.parent),
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)


_PORTABLE_SCRIPT = r"""
param([int]$AppPid, [string]$Zip, [string]$AppDir, [string]$Exe)
$log = Join-Path $env:TEMP "CDriveCleaner_update.log"
function Write-Log($m) { Add-Content -LiteralPath $log -Value ("[{0}] {1}" -f (Get-Date -Format s), $m) }
try {
    Write-Log "wait for app $AppPid"
    for ($i = 0; $i -lt 240; $i++) {
        if (-not (Get-Process -Id $AppPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
    $stage = Join-Path $env:TEMP ("CDriveCleaner_stage_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    Write-Log "extract $Zip"
    Expand-Archive -LiteralPath $Zip -DestinationPath $stage -Force
    for ($i = 0; $i -lt 60; $i++) {
        try {
            Copy-Item -Path (Join-Path $stage '*') -Destination $AppDir -Recurse -Force
            break
        } catch {
            Write-Log "copy retry $i : $_"
            Start-Sleep -Seconds 1
        }
    }
    Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
    Write-Log "start $Exe"
    Start-Process -FilePath $Exe -WorkingDirectory $AppDir
} catch {
    Write-Log "ERROR: $_"
}
"""


def apply_portable(zip_path: str) -> tuple[bool, str]:
    if not paths.is_frozen() or not paths.is_portable():
        return False, "当前不是便携版，无法自动替换"
    app_dir = str(paths.executable_dir())
    exe = sys.executable
    script = paths.jobs_dir().parent / "updates" / "apply_update.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(_PORTABLE_SCRIPT, encoding="utf-8-sig")
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", str(script),
             "-AppPid", str(os.getpid()), "-Zip", zip_path,
             "-AppDir", app_dir, "-Exe", exe],
            creationflags=NO_WINDOW,
            cwd=str(script.parent),
        )
        return True, ""
    except Exception as exc:
        return False, str(exc)


def apply_update(info: UpdateInfo, file_path: str) -> tuple[bool, str]:
    asset = info.asset()
    if asset is None:
        return False, "当前运行方式不支持自动安装"
    if info.portable:
        return apply_portable(file_path)
    return apply_installed(file_path)


def cleanup_downloads(keep: int = 2) -> None:
    directory = paths.data_dir() / "updates"
    try:
        files = sorted(directory.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[keep:]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass
