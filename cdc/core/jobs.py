"""提权作业协议。

GUI（普通权限）把一批操作写成 job.json，通过 ShellExecuteW("runas") 启动
自身的 ``--elevated`` 模式；helper 只依赖 core，不加载 Qt，执行期间不断写
progress.json，GUI 轮询即可。一次 UAC 执行整批，避免每个目录弹一次。

文件布局（``data/state/jobs/<job-id>/``）：
    job.json         请求
    progress.json    进度（原子替换）
    result.json      最终结果
    cancel.flag      GUI 请求取消
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import paths
from .config import load_config
from .models import JobRequest, OperationItem, OperationResult
from .operations import AuditLog, OperationContext, run_batch

_PROGRESS_INTERVAL = 0.25


@dataclass
class JobFiles:
    id: str
    directory: Path
    job: Path
    progress: Path
    result: Path
    cancel: Path


def job_files(job_id: str) -> JobFiles:
    directory = paths.jobs_dir() / job_id
    return JobFiles(
        id=job_id,
        directory=directory,
        job=directory / "job.json",
        progress=directory / "progress.json",
        result=directory / "result.json",
        cancel=directory / "cancel.flag",
    )


def create_job(items: list[OperationItem], *, action: str,
               strict: bool = False) -> JobFiles:
    job_id = f"job-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    files = job_files(job_id)
    files.directory.mkdir(parents=True, exist_ok=True)
    from ..version import __version__
    request = JobRequest(id=job_id, action=action, items=items,
                         app_version=__version__, strict_verify=strict)
    _write_json(files.job, request.to_dict())
    return files


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_progress(files: JobFiles) -> dict[str, Any] | None:
    try:
        return json.loads(files.progress.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_result(files: JobFiles) -> dict[str, Any] | None:
    try:
        return json.loads(files.result.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def request_cancel(files: JobFiles) -> None:
    try:
        files.cancel.write_text("1", encoding="utf-8")
    except OSError:
        pass


def launch_elevated(files: JobFiles) -> tuple[bool, str]:
    """通过 UAC 启动自身 ``--elevated``。返回 (已触发, 错误)。"""
    params = f'--elevated "{files.job}"'
    if getattr(sys, "frozen", False):
        exe = sys.executable
        cwd = str(Path(exe).resolve().parent)
    else:
        py = Path(sys.executable)
        pythonw = py.with_name("pythonw.exe")
        exe = str(pythonw if pythonw.exists() else py)
        cwd = str(Path(__file__).resolve().parents[2])
        params = f'-m cdc.app {params}'
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            0, "runas", exe, params, cwd, 1)
    except Exception as exc:
        return False, str(exc)
    if int(ret) <= 32:
        return False, f"UAC 启动失败（ShellExecuteW={int(ret)}）"
    return True, ""


def run_elevated_job(job_path: str | Path) -> int:
    """helper 入口。返回进程退出码。"""
    files = job_files(Path(job_path).parent.name)
    # 允许传入任意路径
    directory = Path(job_path).resolve().parent
    files = JobFiles(
        id=directory.name, directory=directory,
        job=Path(job_path), progress=directory / "progress.json",
        result=directory / "result.json", cancel=directory / "cancel.flag",
    )
    started = time.time()
    try:
        raw = json.loads(files.job.read_text(encoding="utf-8"))
        request = JobRequest.from_dict(raw)
    except Exception as exc:
        _write_json(files.result, {"status": "failed",
                                   "error": f"无法读取作业：{exc}",
                                   "results": []})
        return 2

    config = load_config(create=False)
    audit = AuditLog()
    last_write = 0.0
    last_progress: dict[str, Any] = {}

    def on_progress(progress) -> None:
        nonlocal last_write
        now = time.time()
        if now - last_write < _PROGRESS_INTERVAL and progress.percent < 100:
            return
        last_write = now
        data = progress.to_dict()
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        last_progress = data
        try:
            _write_json(files.progress, data)
        except OSError:
            pass

    def canceled() -> bool:
        try:
            return files.cancel.exists()
        except OSError:
            return False

    ctx = OperationContext(
        config=config, audit=audit, progress=on_progress,
        cancel=canceled, strict=request.strict_verify,
    )
    try:
        results = run_batch(request.items, ctx)
        _write_json(files.result, {
            "status": "success" if all(r.ok for r in results) else "partial",
            "error": "" if all(r.ok for r in results) else "部分操作未完成",
            "results": [r.to_dict() for r in results],
            "duration_s": round(time.time() - started, 2),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return 0 if all(r.ok for r in results) else 1
    except Exception as exc:
        try:
            _write_json(files.result, {
                "status": "failed", "error": f"helper 内部错误：{exc}",
                "results": [], "duration_s": round(time.time() - started, 2),
            })
        except OSError:
            pass
        return 3
    finally:
        try:
            files.cancel.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_jobs(keep: int = 20) -> None:
    try:
        dirs = [p for p in paths.jobs_dir().iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in dirs[keep:]:
            import shutil
            shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass


def wait_for_result(files: JobFiles, timeout: float = 30.0) -> dict[str, Any] | None:
    """测试用：阻塞等待 result.json。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = read_result(files)
        if result is not None:
            return result
        time.sleep(0.2)
    return None
