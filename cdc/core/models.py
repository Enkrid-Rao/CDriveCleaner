"""核心数据模型（不依赖 Qt / Windows API）。"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field, asdict
from typing import Any, Callable


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def human_bytes(num: float | int, *, precision: int = 1) -> str:
    """人类可读字节数。"""
    n = float(num or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{sign}{int(n)} B"
            return f"{sign}{n:.{precision}f} {unit}"
        n /= 1024
    return f"{sign}{n:.1f} TB"


def human_duration(seconds: float | int) -> str:
    s = max(0, int(seconds or 0))
    if s < 60:
        return f"{s} 秒"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} 分 {s:02d} 秒"
    h, m = divmod(m, 60)
    return f"{h} 时 {m:02d} 分"


# ============================================================
# 磁盘
# ============================================================

@dataclass
class DriveInfo:
    letter: str                    # "C"
    root: str                      # "C:\\"
    label: str = ""
    total_bytes: int = 0
    free_bytes: int = 0
    filesystem: str = "NTFS"
    media_type: str = "Unknown"    # SSD / HDD / USB / Unknown
    bus_type: str = ""
    model: str = ""
    drive_kind: int = 3            # Win32_LogicalDisk.DriveType: 2 可移动 3 固定 4 网络
    disk_number: int | None = None
    physical_name: str = ""
    is_system: bool = False
    is_removable: bool = False

    @property
    def used_bytes(self) -> int:
        return max(0, self.total_bytes - self.free_bytes)

    @property
    def used_ratio(self) -> float:
        return (self.used_bytes / self.total_bytes) if self.total_bytes else 0.0

    @property
    def free_ratio(self) -> float:
        return (self.free_bytes / self.total_bytes) if self.total_bytes else 0.0

    @property
    def is_hdd(self) -> bool:
        return self.media_type.upper() == "HDD"

    @property
    def is_ssd(self) -> bool:
        return self.media_type.upper() == "SSD"

    @property
    def is_usb(self) -> bool:
        return self.bus_type.upper() == "USB" or self.drive_kind == 2

    @property
    def media_label(self) -> str:
        if self.is_removable:
            return "可移动磁盘"
        if self.media_type.upper() == "SSD":
            return "SSD"
        if self.media_type.upper() == "HDD":
            return "机械硬盘"
        if self.is_usb:
            return "USB 外置磁盘"
        return "磁盘"

    @property
    def is_archive_candidate(self) -> bool:
        """适合作为冷数据归档目标：非系统、非网络、空间足够。"""
        return (not self.is_system) and self.drive_kind != 4 and self.total_bytes > 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update({
            "used_bytes": self.used_bytes,
            "used_ratio": round(self.used_ratio, 4),
            "media_label": self.media_label,
            "is_hdd": self.is_hdd,
            "is_ssd": self.is_ssd,
            "is_usb": self.is_usb,
        })
        return d


# ============================================================
# 扫描
# ============================================================

@dataclass
class ScanItem:
    """C 盘扫描出的一个可迁移目录。"""
    name: str
    path: str
    size_bytes: int
    zone_key: str
    zone_label: str
    dest_path: str
    needs_admin: bool = False
    file_count: int = 0
    newest_ts: float = 0.0
    protected: bool = False
    protected_reason: str = ""

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JunctionInfo:
    """已存在的目录链接（Junction / Symlink）。"""
    name: str
    path: str
    target: str = ""
    zone_key: str = ""
    zone_label: str = ""
    size_bytes: int = 0
    file_count: int = 0
    needs_admin: bool = False
    target_exists: bool = True
    target_on_usb: bool = False
    target_drive: str = ""
    mine: bool = True             # 目标位于 link_root 下（本工具管理）
    broken: bool = False
    origin: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    scanned_at: str = ""
    duration_s: float = 0.0
    items: list[ScanItem] = field(default_factory=list)
    junctions: list[JunctionInfo] = field(default_factory=list)
    protected_items: list[ScanItem] = field(default_factory=list)
    potential_bytes: int = 0
    released_bytes: int = 0
    temp_bytes: int = 0
    backend: str = "native"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "duration_s": self.duration_s,
            "items": [i.to_dict() for i in self.items],
            "junctions": [j.to_dict() for j in self.junctions],
            "protected_items": [p.to_dict() for p in self.protected_items],
            "potential_bytes": self.potential_bytes,
            "released_bytes": self.released_bytes,
            "temp_bytes": self.temp_bytes,
            "backend": self.backend,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScanResult":
        return cls(
            scanned_at=d.get("scanned_at", ""),
            duration_s=float(d.get("duration_s", 0) or 0),
            items=[ScanItem(**i) for i in d.get("items", [])],
            junctions=[JunctionInfo(**j) for j in d.get("junctions", [])],
            protected_items=[ScanItem(**p) for p in d.get("protected_items", [])],
            potential_bytes=int(d.get("potential_bytes", 0) or 0),
            released_bytes=int(d.get("released_bytes", 0) or 0),
            temp_bytes=int(d.get("temp_bytes", 0) or 0),
            backend=d.get("backend", "native"),
            errors=list(d.get("errors", [])),
        )


# ============================================================
# 冷数据分析
# ============================================================

TIER_STRONG = "strong"
TIER_RECOMMEND = "recommend"
TIER_OPTIONAL = "optional"
TIER_SKIP = "skip"

TIER_LABELS = {
    TIER_STRONG: "强烈推荐",
    TIER_RECOMMEND: "推荐",
    TIER_OPTIONAL: "可选",
    TIER_SKIP: "不建议",
}


@dataclass
class ArchiveCandidate:
    name: str
    path: str
    size_bytes: int
    file_count: int
    newest_ts: float
    oldest_ts: float
    ext_bytes: dict[str, int] = field(default_factory=dict)
    tier: str = TIER_OPTIONAL
    score: int = 0
    reason: str = ""
    dest_path: str = ""
    source_drive: str = "C"
    is_junction: bool = False
    needs_admin: bool = False
    target_path: str = ""
    warnings: list[str] = field(default_factory=list)
    source_root: str = ""

    @property
    def tier_label(self) -> str:
        return TIER_LABELS.get(self.tier, self.tier)

    @property
    def age_days(self) -> int:
        if not self.newest_ts:
            return 0
        try:
            return max(0, int((_dt.datetime.now().timestamp() - self.newest_ts) / 86400))
        except (OverflowError, OSError):
            return 0

    def top_exts(self, limit: int = 3) -> list[tuple[str, float]]:
        total = sum(self.ext_bytes.values()) or 1
        rows = sorted(self.ext_bytes.items(), key=lambda kv: kv[1], reverse=True)
        return [(k, v / total) for k, v in rows[:limit] if v > 0]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update({
            "tier_label": self.tier_label,
            "age_days": self.age_days,
            "top_exts": self.top_exts(6),
        })
        return d


@dataclass
class AnalysisResult:
    scanned_at: str = ""
    duration_s: float = 0.0
    candidates: list[ArchiveCandidate] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)
    total_recommended_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    def recommended(self) -> list[ArchiveCandidate]:
        return [c for c in self.candidates if c.tier in (TIER_STRONG, TIER_RECOMMEND)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_at": self.scanned_at,
            "duration_s": self.duration_s,
            "candidates": [c.to_dict() for c in self.candidates],
            "roots": self.roots,
            "total_recommended_bytes": self.total_recommended_bytes,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AnalysisResult":
        rows = []
        for raw in d.get("candidates", []):
            raw = dict(raw)
            raw.pop("tier_label", None)
            raw.pop("age_days", None)
            raw.pop("top_exts", None)
            rows.append(ArchiveCandidate(**raw))
        return cls(
            scanned_at=d.get("scanned_at", ""),
            duration_s=float(d.get("duration_s", 0) or 0),
            candidates=rows,
            roots=list(d.get("roots", [])),
            total_recommended_bytes=int(d.get("total_recommended_bytes", 0) or 0),
            errors=list(d.get("errors", [])),
        )


# ============================================================
# 操作
# ============================================================

ACTION_MIGRATE = "migrate"
ACTION_UNDO = "undo"
ACTION_ARCHIVE = "archive"
ACTION_RESTORE = "restore"
ACTION_LINK = "link"
ACTION_UNLINK = "unlink"
ACTION_CLEAN = "clean"

ACTION_LABELS = {
    ACTION_MIGRATE: "迁移",
    ACTION_UNDO: "撤销迁移",
    ACTION_ARCHIVE: "归档",
    ACTION_RESTORE: "回迁",
    ACTION_LINK: "重建链接",
    ACTION_UNLINK: "移除链接",
    ACTION_CLEAN: "系统清理",
}

MODE_MOVE = "move"
MODE_LINK = "link"
MODE_COPY = "copy"

MODE_LABELS = {
    MODE_MOVE: "移动归档",
    MODE_LINK: "链接归档",
    MODE_COPY: "仅复制",
}


@dataclass
class OperationItem:
    action: str
    source: str
    dest: str
    name: str = ""
    size_bytes: int = 0
    file_count: int = 0
    zone_key: str = ""
    needs_admin: bool = False
    mode: str = MODE_MOVE
    strict_verify: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OperationItem":
        return cls(**d)


@dataclass
class Progress:
    phase: str = "准备"
    percent: float = 0.0
    message: str = ""
    bytes_done: int = 0
    bytes_total: int = 0
    speed_bps: float = 0.0
    eta_s: float = 0.0
    item_index: int = 0
    item_count: int = 1
    detail: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProgressCallback = Callable[[Progress], None]
CancelCheck = Callable[[], bool]


@dataclass
class PreflightResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    size_bytes: int = 0
    dest_free_bytes: int = 0
    source_free_bytes: int = 0
    locked_processes: list[dict[str, Any]] = field(default_factory=list)
    requires_admin: bool = False

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False


@dataclass
class OperationResult:
    ok: bool
    action: str
    source: str
    dest: str = ""
    name: str = ""
    mode: str = MODE_MOVE
    bytes_total: int = 0
    files_total: int = 0
    duration_s: float = 0.0
    verified: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    record_id: str = ""
    rolled_back: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperationRecord:
    id: str
    ts: str
    action: str
    mode: str
    source: str
    dest: str
    name: str
    status: str                  # success / failed / rolled_back / canceled
    bytes_moved: int = 0
    files: int = 0
    duration_s: float = 0.0
    verified: bool = False
    needs_admin: bool = False
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def action_label(self) -> str:
        return ACTION_LABELS.get(self.action, self.action)

    @property
    def mode_label(self) -> str:
        return MODE_LABELS.get(self.mode, self.mode)

    @property
    def success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update({
            "action_label": self.action_label,
            "mode_label": self.mode_label,
            "success": self.success,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OperationRecord":
        data = dict(d)
        data.pop("action_label", None)
        data.pop("mode_label", None)
        data.pop("success", None)
        return cls(**data)


# ============================================================
# 作业（提权 helper 协议）
# ============================================================

@dataclass
class JobRequest:
    id: str
    action: str
    items: list[OperationItem]
    created_at: str = field(default_factory=now_iso)
    app_version: str = ""
    strict_verify: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "items": [i.to_dict() for i in self.items],
            "created_at": self.created_at,
            "app_version": self.app_version,
            "strict_verify": self.strict_verify,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobRequest":
        return cls(
            id=d["id"],
            action=d.get("action", ""),
            items=[OperationItem.from_dict(i) for i in d.get("items", [])],
            created_at=d.get("created_at", now_iso()),
            app_version=d.get("app_version", ""),
            strict_verify=bool(d.get("strict_verify", False)),
        )


def safe_join(*parts: str) -> str:
    """os.path.join 的显式封装，便于统一处理反斜杠。"""
    return os.path.join(*parts)
