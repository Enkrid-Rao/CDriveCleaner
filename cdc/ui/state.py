"""应用状态、后台线程与提权作业控制。"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .. import paths
from ..core import applog, jobs, scanner, windows
from ..core.config import Config, load_config
from ..core.models import (
    ACTION_ARCHIVE, ACTION_CLEAN, ACTION_MIGRATE, ACTION_RESTORE, ACTION_UNDO,
    ACTION_UNLINK, MODE_LINK, MODE_MOVE, AnalysisResult, OperationItem,
    OperationResult, Progress, ScanResult,
)
from ..core.operations import AuditLog, OperationContext, run_batch
from ..version import __version__

_CACHE_SCAN = "last_scan.json"
_CACHE_ANALYSIS = "last_analysis.json"


def _cache_path(name: str) -> str:
    return str(paths.cache_dir() / name)


# ============================================================
# 后台线程
# ============================================================

class ScanWorker(QThread):
    progress = Signal(object)
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, config: Config, drives: list) -> None:
        super().__init__()
        self.config = config
        self.drives = drives
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            result = scanner.scan_zones(
                self.config, self.drives,
                progress=self.progress.emit,
                cancel=self._cancel.is_set,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(f"{exc}")


class AnalysisWorker(QThread):
    progress = Signal(object)
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, config: Config, drives: list,
                 roots: list[tuple[str, str]] | None = None) -> None:
        super().__init__()
        self.config = config
        self.drives = drives
        self.roots = roots
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            result = scanner.analyze_cold(
                self.config, self.roots, drives=self.drives,
                progress=self.progress.emit, cancel=self._cancel.is_set,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(f"{exc}")


class OperationWorker(QThread):
    progress = Signal(object)
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, items: list[OperationItem], config: Config,
                 drives: list, strict: bool) -> None:
        super().__init__()
        self.items = items
        self.config = config
        self.drives = drives
        self.strict = strict
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            ctx = OperationContext(
                config=self.config, audit=AuditLog(), drives=self.drives,
                progress=self.progress.emit, cancel=self._cancel.is_set,
                strict=self.strict,
            )
            results = run_batch(self.items, ctx)
            self.result_ready.emit(results)
        except Exception as exc:
            self.failed.emit(f"{exc}")


class ElevatedController(QObject):
    """轮询提权 helper 的 job/progress/result 文件。"""

    progress = Signal(object)
    result_ready = Signal(object)
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.files: jobs.JobFiles | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._poll)
        self._started = 0.0
        self._last_progress = 0.0
        self._cancelled = False

    def start(self, items: list[OperationItem], strict: bool) -> tuple[bool, str]:
        files = jobs.create_job(items, action=items[0].action if items else "", strict=strict)
        ok, err = jobs.launch_elevated(files)
        if not ok:
            return False, err
        self.files = files
        self._started = time.time()
        self._last_progress = self._started
        self._cancelled = False
        jobs.cleanup_jobs()
        self._timer.start()
        return True, ""

    def cancel(self) -> None:
        if self.files:
            jobs.request_cancel(self.files)
            self._cancelled = True

    def _poll(self) -> None:
        if not self.files:
            self._timer.stop()
            return
        result = jobs.read_result(self.files)
        if result is not None:
            self._finish(result)
            return
        progress = jobs.read_progress(self.files)
        if progress:
            self._last_progress = time.time()
            try:
                self.progress.emit(Progress(**progress))
            except TypeError:
                pass
        elif time.time() - self._last_progress > 600:
            self._timer.stop()
            self.failed.emit("长时间未检测到提权进程的进度（可能已取消 UAC）。请重试。")
            self.files = None

    def _finish(self, data: dict[str, Any]) -> None:
        self._timer.stop()
        results: list[OperationResult] = []
        for raw in data.get("results", []):
            try:
                results.append(OperationResult(**raw))
            except TypeError:
                continue
        if results:
            self.result_ready.emit(results)
        else:
            self.failed.emit(str(data.get("error") or "提权作业未返回结果"))
        self.files = None


# ============================================================
# AppState
# ============================================================

class AppState(QObject):
    drives_changed = Signal(object)
    scan_started = Signal()
    scan_progress = Signal(object)
    scan_finished = Signal(object)
    scan_failed = Signal(str)
    analysis_started = Signal()
    analysis_progress = Signal(object)
    analysis_finished = Signal(object)
    analysis_failed = Signal(str)
    history_changed = Signal()
    operation_busy = Signal(bool)
    operation_started = Signal(str, str, int, object)
    operation_progress = Signal(object)
    operation_finished = Signal(object)
    operation_failed = Signal(str)
    toast = Signal(str, str)
    navigate = Signal(str)
    config_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config: Config = load_config()
        self.drives: list = windows.list_drives(force=True)
        self.audit = AuditLog()
        self.scan: ScanResult = ScanResult()
        self.analysis: AnalysisResult = AnalysisResult()
        self.scanning = False
        self.analysing = False
        self.busy = False
        self.is_admin = windows.is_admin()
        self._scan_worker: ScanWorker | None = None
        self._analysis_worker: AnalysisWorker | None = None
        self._op_worker: OperationWorker | None = None
        self._elevated: ElevatedController | None = None
        self._load_cache()
        applog.log("INFO", f"启动 CDriveCleaner {__version__} · 数据目录 {paths.data_dir()}")
        if self.config.warnings:
            for warning in self.config.warnings:
                QTimer.singleShot(1200, lambda w=warning: self.toast.emit(w, "warn"))

    # ---------- 基础数据 ----------

    def refresh_drives(self, force: bool = True) -> list:
        self.drives = windows.list_drives(force=force)
        self.drives_changed.emit(self.drives)
        return self.drives

    def c_drive(self):
        return windows.get_drive("C", self.drives)

    def archive_drives(self) -> list:
        rows = [d for d in self.drives
                if d.is_archive_candidate and d.letter.upper() != "C"]
        rows.sort(key=lambda d: (d.is_hdd or d.is_usb, d.free_bytes), reverse=True)
        return rows

    def drive_map(self) -> dict[str, Any]:
        return {d.letter.upper(): d for d in self.drives}

    def zone_label(self, key: str) -> str:
        return self.config.zone(key).get("label", key)

    def history(self, limit: int | None = None):
        return self.audit.read(limit)

    def reload_config(self) -> Config:
        self.config = load_config()
        self.config_changed.emit()
        return self.config

    # ---------- 缓存 ----------

    def _load_cache(self) -> None:
        scan_raw = windows.read_json(_cache_path(_CACHE_SCAN), None)
        if scan_raw:
            try:
                self.scan = ScanResult.from_dict(scan_raw)
            except Exception:
                self.scan = ScanResult()
        analysis_raw = windows.read_json(_cache_path(_CACHE_ANALYSIS), None)
        if analysis_raw:
            try:
                self.analysis = AnalysisResult.from_dict(analysis_raw)
            except Exception:
                self.analysis = AnalysisResult()

    def _save_scan_cache(self) -> None:
        try:
            windows.write_json_atomic(_cache_path(_CACHE_SCAN), self.scan.to_dict())
        except Exception:
            pass

    def _save_analysis_cache(self) -> None:
        try:
            windows.write_json_atomic(_cache_path(_CACHE_ANALYSIS),
                                      self.analysis.to_dict())
        except Exception:
            pass

    # ---------- 扫描 ----------

    def start_scan(self) -> None:
        if self.scanning:
            return
        self.scanning = True
        self.scan_started.emit()
        applog.log("INFO", "开始扫描 C 盘")
        worker = ScanWorker(self.config, self.drives)
        worker.progress.connect(self.scan_progress.emit)
        worker.result_ready.connect(self._on_scan_done)
        worker.failed.connect(self._on_scan_failed)
        worker.finished.connect(worker.deleteLater)
        self._scan_worker = worker
        worker.start()

    def cancel_scan(self) -> None:
        if self._scan_worker:
            self._scan_worker.cancel()

    def _on_scan_done(self, result: ScanResult) -> None:
        self.scanning = False
        self.scan = result
        self._save_scan_cache()
        self.refresh_drives(force=True)
        self.scan_finished.emit(result)
        self._scan_worker = None
        applog.log("SUCCESS", f"扫描完成：{len(result.items)} 个可迁移目录，"
                              f"{len(result.junctions)} 个链接，耗时 {result.duration_s:.1f}s")

    def _on_scan_failed(self, error: str) -> None:
        self.scanning = False
        self.scan_failed.emit(error)
        self._scan_worker = None
        applog.log("ERROR", f"扫描失败：{error}")

    # ---------- 冷数据分析 ----------

    def start_analysis(self, roots: list[tuple[str, str]] | None = None) -> None:
        if self.analysing:
            return
        self.analysing = True
        self.analysis_started.emit()
        applog.log("INFO", "开始分析冷数据")
        worker = AnalysisWorker(self.config, self.drives, roots)
        worker.progress.connect(self.analysis_progress.emit)
        worker.result_ready.connect(self._on_analysis_done)
        worker.failed.connect(self._on_analysis_failed)
        worker.finished.connect(worker.deleteLater)
        self._analysis_worker = worker
        worker.start()

    def cancel_analysis(self) -> None:
        if self._analysis_worker:
            self._analysis_worker.cancel()

    def _on_analysis_done(self, result: AnalysisResult) -> None:
        self.analysing = False
        self.analysis = result
        self._save_analysis_cache()
        self.analysis_finished.emit(result)
        self._analysis_worker = None
        applog.log("SUCCESS", f"冷数据分析完成：{len(result.candidates)} 个候选，"
                              f"耗时 {result.duration_s:.1f}s")

    def _on_analysis_failed(self, error: str) -> None:
        self.analysing = False
        self.analysis_failed.emit(error)
        self._analysis_worker = None
        applog.log("ERROR", f"冷数据分析失败：{error}")

    # ---------- 操作 ----------

    def _operation_intro(self, items: list[OperationItem]) -> tuple[str, str, list[str], str]:
        action = items[0].action if items else ""
        count = len(items)
        if action == ACTION_MIGRATE:
            return (f"正在迁移 {count} 个目录", "复制 → 校验 → 删除源 → 建立链接",
                    ["准备", "复制", "校验", "完成"], "sparkles")
        if action == ACTION_ARCHIVE:
            mode = items[0].mode if items else MODE_MOVE
            if mode == MODE_LINK:
                sub = "复制 → 校验 → 清空源内容 → 建立链接"
            elif mode == "copy":
                sub = "复制 → 校验，源目录保留"
            else:
                sub = "复制 → 校验 → 清空源内容（保留目录结构），冷数据移入机械盘"
            return (f"正在归档 {count} 个目录", sub,
                    ["准备", "复制", "校验", "完成"], "archive")
        if action == ACTION_UNDO:
            return (f"正在撤销 {count} 项迁移", "删除链接 → 回迁数据 → 校验",
                    ["准备", "回迁", "校验", "完成"], "undo")
        if action == ACTION_RESTORE:
            return (f"正在回迁 {count} 项归档", "复制回原位置 → 校验 → 释放归档副本",
                    ["准备", "回迁", "校验", "完成"], "download")
        if action == ACTION_UNLINK:
            return (f"正在移除 {count} 个链接", "只删除链接本体，不会触碰目标数据",
                    ["准备", "移除", "校验", "完成"], "link")
        if action == ACTION_CLEAN:
            return ("正在清理", "扫描 → 删除 → 统计释放空间",
                    ["准备", "清理", "统计", "完成"], "trash")
        return (f"正在处理 {count} 项", "", ["准备", "处理", "校验", "完成"], "sparkles")

    def start_operation(self, items: list[OperationItem]) -> bool:
        if self.busy or not items:
            return False
        self.busy = True
        title, subtitle, steps, icon_name = self._operation_intro(items)
        self.operation_busy.emit(True)
        self.operation_started.emit(title, subtitle, len(items), steps)
        applog.log("INFO", f"{title} · {', '.join(i.name for i in items[:5])}"
                           f"{' …' if len(items) > 5 else ''}")
        needs_admin = any(item.needs_admin for item in items)
        strict = bool(self.config.strict_verify or any(item.strict_verify for item in items))
        if needs_admin:
            controller = ElevatedController(self)
            controller.progress.connect(self.operation_progress.emit)
            controller.result_ready.connect(self._on_operation_done)
            controller.failed.connect(self._on_operation_failed)
            ok, err = controller.start(items, strict)
            self._elevated = controller
            if not ok:
                self._elevated = None
                self.busy = False
                self.operation_busy.emit(False)
                self.operation_failed.emit(f"无法启动管理员进程：{err}")
                return False
        else:
            worker = OperationWorker(items, self.config, self.drives, strict)
            worker.progress.connect(self.operation_progress.emit)
            worker.result_ready.connect(self._on_operation_done)
            worker.failed.connect(self._on_operation_failed)
            worker.finished.connect(worker.deleteLater)
            self._op_worker = worker
            worker.start()
        return True

    def cancel_operation(self) -> None:
        if self._op_worker:
            self._op_worker.cancel()
        if self._elevated:
            self._elevated.cancel()

    def _on_operation_done(self, results: list[OperationResult]) -> None:
        self.busy = False
        self.operation_busy.emit(False)
        self._op_worker = None
        self._elevated = None
        self.refresh_drives(force=True)
        self.history_changed.emit()
        self.operation_finished.emit(results)
        successes = [r for r in results if r.ok]
        applog.log("SUCCESS" if not [r for r in results if not r.ok] else "WARN",
                   f"操作结束：{len(successes)}/{len(results)} 成功")
        for result in results:
            applog.log("INFO" if result.ok else "ERROR",
                       f"{result.action} {result.name}: "
                       f"{'OK' if result.ok else result.error[:200]}")
        if successes and any(r.action in (ACTION_MIGRATE, ACTION_UNDO, ACTION_CLEAN,
                                          ACTION_UNLINK) for r in successes):
            QTimer.singleShot(900, self.start_scan)
        if successes and any(r.action in (ACTION_ARCHIVE, ACTION_RESTORE) for r in successes):
            QTimer.singleShot(900, lambda: self.start_analysis())

    def _on_operation_failed(self, error: str) -> None:
        self.busy = False
        self.operation_busy.emit(False)
        self._op_worker = None
        self._elevated = None
        self.operation_failed.emit(error)
        applog.log("ERROR", f"操作失败：{error}")

    def current_progress_text(self) -> str:
        return ""

    # ---------- 设置 ----------

    def apply_config(self, new_config: Config) -> None:
        self.config = new_config
        self.config_changed.emit()
        self.refresh_drives(force=True)
        self.toast.emit("设置已保存并应用", "success")

    def save_window_state(self, page: str, width: int, height: int) -> None:
        try:
            self.config.last_page = page
            self.config.window_size = (width, height)
            self.config.save()
        except Exception:
            pass

    def shutdown(self) -> None:
        self.cancel_scan()
        self.cancel_analysis()
        self.cancel_operation()
        for worker in (self._scan_worker, self._analysis_worker, self._op_worker):
            if worker is not None:
                try:
                    if worker.isRunning():
                        if not worker.wait(3000):
                            worker.terminate()
                            worker.wait(1000)
                except RuntimeError:
                    pass
        self._scan_worker = None
        self._analysis_worker = None
        self._op_worker = None
