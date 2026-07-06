"""操作日志模块。

保留老网站「操作日志」的能力，并升级为可持久化的真实任务记录：

- 单例 `OperationLog`：线程安全的 `log(level, message)`。
- 落盘：按天写入 `logs/CDriveCleaner-YYYY-MM-DD.log`，关掉重开仍可看历史。
- 内存：保留最近 N 条，供 GUI 面板实时显示与启动重放。
- 订阅：GUI 面板 `subscribe(callback)` 后，每条新日志会推送给它；
  订阅时自动重放已有条目（含本次启动前从日志文件载入的历史）。

级别（对齐老网站的 addLog type）：
  INFO / SUCCESS / WARN / ERROR
对应颜色在 LEVEL_COLORS 里，GUI 面板直接复用。
"""

from __future__ import annotations

import datetime
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

# 级别 → 颜色（与老网站 .log-line.success/.error/.info/.warn 一致）
LEVEL_COLORS: dict[str, str] = {
    "INFO": "#58a6ff",
    "SUCCESS": "#3fb950",
    "WARN": "#d29922",
    "ERROR": "#f85149",
}

_LEVEL_LINE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+(.*)$")
_MAX_MEMORY = 1000  # 内存最多保留条数


class OperationLog:
    """操作日志单例。"""

    _instance: "OperationLog | None" = None

    def __new__(cls) -> "OperationLog":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    # ---------- 初始化 ----------

    def _init(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict[str, str]] = []
        self._subscribers: list[Callable[[dict[str, str]], None]] = []
        self._log_dir = self._resolve_log_dir()
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # 极少数情况下日志目录不可写（如只读介质），降级为仅内存
            self._log_dir = Path(self._fallback_dir())

        # 启动重放：载入最近的日志文件（含上次会话历史）
        self._load_existing()

    def _resolve_log_dir(self) -> Path:
        """日志目录：打包后写 exe 同级 logs/，源码模式写项目根 logs/。"""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).resolve().parent
        else:
            # src/logger.py → 项目根
            base = Path(__file__).resolve().parent.parent
        return base / "logs"

    def _fallback_dir(self) -> Path:
        import tempfile

        return Path(tempfile.gettempdir()) / "CDriveCleaner_logs"

    # ---------- 文件读写 ----------

    def _today_file(self) -> Path:
        return self._log_dir / f"CDriveCleaner-{datetime.date.today():%Y-%m-%d}.log"

    def _load_existing(self) -> None:
        """载入最近的日志文件，作为历史条目重放（最多 _MAX_MEMORY 条）。"""
        try:
            files = sorted(self._log_dir.glob("CDriveCleaner-*.log"))
        except OSError:
            return
        if not files:
            return
        latest = files[-1]
        try:
            lines = latest.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return
        for line in lines[-_MAX_MEMORY:]:
            m = _LEVEL_LINE.match(line.strip())
            if m:
                self._entries.append(
                    {"ts": m.group(1), "level": m.group(2), "msg": m.group(3)}
                )

    # ---------- 公共 API ----------

    def log(self, level: str, message: str) -> None:
        """记录一条日志。level ∈ INFO/SUCCESS/WARN/ERROR（大小写不限）。"""
        level = level.upper()
        if level not in LEVEL_COLORS:
            level = "INFO"
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = {"ts": ts, "level": level, "msg": str(message)}

        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > _MAX_MEMORY:
                self._entries = self._entries[-_MAX_MEMORY:]
            try:
                with open(self._today_file(), "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] [{level}] {message}\n")
            except OSError:
                pass

        # 推送给订阅者（面板）。订阅者回调需自行保证线程安全，
        # GUI 中由主线程调用的回调直接更新控件即可。
        for cb in list(self._subscribers):
            try:
                cb(entry)
            except Exception:
                pass

    def subscribe(self, cb: Callable[[dict[str, str]], None]) -> None:
        """注册订阅者。注册时立即重放已有条目（含历史）。"""
        self._subscribers.append(cb)
        with self._lock:
            snapshot = list(self._entries)
        for e in snapshot:
            try:
                cb(e)
            except Exception:
                pass

    def clear_memory(self) -> None:
        """清空内存中的条目（不影响已落盘的日志文件）。"""
        with self._lock:
            self._entries.clear()

    @property
    def entries(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._entries)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def log_dir(self) -> Path:
        return self._log_dir
