"""Everything 索引加速（可选，只读）。

通过 Everything 的 CLI（``es.exe``）查询 NTFS 索引，用于**统计类**工作：
文件数、总大小、扩展名构成、最新 / 最早修改时间、全盘大文件排行。

安全边界：
- 只用于「分析 / 展示」，绝不用于归档复制、校验、删除判断——那些必须以真实
  文件系统为准，避免索引滞后几毫秒到几秒造成误判。
- Everything 没安装、没运行、索引没加载、目录不在索引里时，调用方必须回退到
  逐文件遍历（``windows.directory_stats``）。

环境变量 ``CDC_NO_EVERYTHING=1`` 可强制禁用（测试用）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache

from . import windows

NO_WINDOW = 0x08000000

# <DIR> 或带千分位的大小 + 可选日期 + 绝对路径
_LINE = re.compile(
    r"^\s*(?P<size><DIR>|[\d,]+)"
    r"(?:\s+(?P<date>\d{4}[/-]\d{1,2}[/-]\d{1,2}"
    r"\s+\d{1,2}:\d{2}(?::\d{2})?))?"
    r"\s+(?P<path>[A-Za-z]:\\.*)$"
)


class EverythingError(RuntimeError):
    """Everything 查询失败（CLI 缺失、索引未加载、超时等）。"""


@dataclass
class IndexedFile:
    path: str
    size: int
    modified: float = 0.0


def _run(args: list[str], timeout: float = 120.0) -> str:
    """执行 es.exe 并解码输出（Windows 控制台是 mbcs/GBK）。"""
    try:
        proc = subprocess.run(
            args, capture_output=True, timeout=timeout,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EverythingError(str(exc)) from exc
    return proc.stdout.decode("mbcs", errors="replace")


def _parse_rows(text: str) -> list[IndexedFile]:
    rows: list[IndexedFile] = []
    for line in text.splitlines():
        match = _LINE.match(line.rstrip())
        if not match or match.group("size") == "<DIR>":
            continue
        try:
            size = int(match.group("size").replace(",", ""))
        except ValueError:
            continue
        modified = 0.0
        raw_date = match.group("date")
        if raw_date:
            for fmt in ("%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
                try:
                    modified = time.mktime(time.strptime(raw_date, fmt))
                    break
                except (ValueError, OverflowError):
                    continue
        rows.append(IndexedFile(match.group("path"), size, modified))
    return rows


@lru_cache(maxsize=1)
def find_cli() -> str:
    """定位 es.exe：PATH → 注册表安装路径 → 常见安装目录。"""
    if os.environ.get("CDC_NO_EVERYTHING"):
        return ""
    exe = shutil.which("es.exe")
    if exe:
        return exe
    locations: list[str] = []
    try:
        import winreg

        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            key = (r"SOFTWARE\voidtools\Everything"
                   if hive == winreg.HKEY_LOCAL_MACHINE
                   else r"Software\voidtools\Everything")
            try:
                with winreg.OpenKey(hive, key) as handle:
                    location, _ = winreg.QueryValueEx(handle, "InstallLocation")
                if location:
                    locations.append(str(location))
            except OSError:
                continue
    except Exception:  # noqa: BLE001
        pass
    locations.extend((
        r"D:\Program Files\Everything",
        r"C:\Program Files\Everything",
        r"C:\Program Files (x86)\Everything",
    ))
    for base in locations:
        candidate = os.path.join(base, "es.exe")
        if os.path.isfile(candidate):
            return candidate
    return ""


@lru_cache(maxsize=1)
def available() -> bool:
    """Everything 可用：CLI 存在且索引里至少有一个文件。"""
    cli = find_cli()
    if not cli:
        return False
    try:
        text = _run([cli, "-get-result-count", "*"], timeout=8.0)
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line:
                return int(line) > 0
    except (EverythingError, ValueError):
        return False
    return False


def refresh() -> None:
    """清掉可用性缓存（用户刚启动 Everything 时重新探测）。"""
    find_cli.cache_clear()
    available.cache_clear()


def query_files(root: str, *, with_date: bool = False,
                timeout: float = 180.0) -> list[IndexedFile]:
    """列出 root 下所有文件（递归，含隐藏 / 系统文件）。"""
    cli = find_cli()
    if not cli:
        raise EverythingError("没有找到 es.exe（Everything 未安装或未在 PATH）")
    args = [cli, "-path", root, "*", "-size"]
    if with_date:
        args.append("-dm")
    args.append("/a-d")
    rows = _parse_rows(_run(args, timeout=timeout))
    base = os.path.abspath(root).rstrip("\\/")
    prefix = base + "\\"
    # 索引里偶尔会混入同名前缀的其他路径，按前缀过滤一次
    return [row for row in rows if row.path.lower().startswith(prefix.lower())]


def _accumulate(stats: windows.DirStats, row: IndexedFile) -> None:
    stats.bytes += row.size
    stats.files += 1
    ext = os.path.splitext(row.path)[1].lower().lstrip(".")
    if ext:
        stats.ext_bytes[ext] = stats.ext_bytes.get(ext, 0) + row.size
    if row.modified:
        if not stats.newest or row.modified > stats.newest:
            stats.newest = float(row.modified)
        if not stats.oldest or row.modified < stats.oldest:
            stats.oldest = float(row.modified)


def dir_stats(root: str, *, timeout: float = 180.0) -> windows.DirStats:
    """用索引统计一个目录（文件数 / 字节 / 扩展名构成 / 新旧时间）。"""
    stats = windows.DirStats()
    for row in query_files(root, with_date=True, timeout=timeout):
        _accumulate(stats, row)
    return stats


def subdir_stats(root: str, *, timeout: float = 180.0) -> dict[str, windows.DirStats]:
    """一次查询 root，按「第一层子目录名」聚合出各自的统计。

    返回的 key 是小写目录名（用于和 ``windows.child_directories`` 的结果匹配）。
    """
    base = os.path.abspath(root).rstrip("\\/")
    prefix_len = len(base) + 1
    buckets: dict[str, windows.DirStats] = {}
    for row in query_files(base, with_date=True, timeout=timeout):
        relative = row.path[prefix_len:]
        if not relative:
            continue
        name, sep, _rest = relative.partition("\\")
        if not sep:
            continue  # root 直接下的文件，不计入任何子目录
        key = name.casefold()
        stats = buckets.get(key)
        if stats is None:
            stats = windows.DirStats()
            buckets[key] = stats
        _accumulate(stats, row)
    return buckets


def top_files(limit: int = 30, *, timeout: float = 30.0) -> list[IndexedFile]:
    """全盘最大的文件（按大小倒序）。"""
    cli = find_cli()
    if not cli:
        raise EverythingError("没有找到 es.exe")
    text = _run([cli, "/a-d", "-size", "-dm",
                 "-sort", "size-descending", "-n", str(max(1, limit))],
                timeout=timeout)
    return _parse_rows(text)[:limit]
