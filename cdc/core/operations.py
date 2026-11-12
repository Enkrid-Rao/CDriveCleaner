"""迁移 / 撤销 / 冷数据归档 / 回迁 / 清理 与审计。

安全原则（任何改动都不要绕过）：
1. 复制 → 校验 → 才允许删除源；
2. 删除只走 ``windows.safe_delete_tree``，永不跟随 Junction；
3. 迁移链接创建失败 → 自动把数据回拷到原位置；
4. 每一次操作（成功 / 失败 / 回滚 / 取消）都写 audit.jsonl。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .. import paths
from . import safety, windows
from .models import (
    ACTION_ARCHIVE, ACTION_CLEAN, ACTION_LINK, ACTION_MIGRATE, ACTION_RESTORE,
    ACTION_UNDO, ACTION_UNLINK, MODE_COPY, MODE_LINK, MODE_MOVE, OperationItem, OperationRecord,
    OperationResult, PreflightResult, Progress, ProgressCallback, human_bytes,
)

MANIFEST_MAX_FILES = 250_000
MTIME_TOLERANCE_NS = 3 * 10**9


# ============================================================
# 审计
# ============================================================

class AuditLog:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or str(paths.audit_path())
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)

    def append(self, record: OperationRecord) -> None:
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError:
            pass

    def read(self, limit: int | None = None) -> list[OperationRecord]:
        rows: list[OperationRecord] = []
        if not os.path.isfile(self.path):
            return rows
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(OperationRecord.from_dict(json.loads(line)))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
        except OSError:
            return []
        rows.sort(key=lambda r: r.ts, reverse=True)
        return rows[:limit] if limit else rows

    def find(self, record_id: str) -> OperationRecord | None:
        for row in self.read():
            if row.id == record_id:
                return row
        return None


# ============================================================
# 清单
# ============================================================

@dataclass
class Manifest:
    root: str
    files: int = 0
    bytes: int = 0
    links_skipped: int = 0
    truncated: bool = False
    entries: dict[str, tuple[int, int]] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root, "files": self.files, "bytes": self.bytes,
            "links_skipped": self.links_skipped, "truncated": self.truncated,
            "entries": self.entries, "hashes": self.hashes,
            "errors": self.errors[:50], "created_at": self.created_at,
        }

    def save(self, directory: str, op_id: str) -> str:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{op_id}.json")
        windows.write_json_atomic(path, self.to_dict())
        return path


def _is_marker_file(path: str, root: str) -> bool:
    try:
        return (os.path.normcase(os.path.dirname(os.path.abspath(path))) ==
                os.path.normcase(os.path.abspath(root)) and
                os.path.basename(path) == safety.MARKER_NAME)
    except (OSError, ValueError):
        return False


def _hash_file(path: str, cancel: Callable[[], bool] | None = None) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                if cancel and cancel():
                    return ""
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def build_manifest(root: str, *, cancel: Callable[[], bool] | None = None,
                   strict: bool = False,
                   on_progress: Callable[[int, int], None] | None = None) -> Manifest:
    manifest = Manifest(root=os.path.abspath(root))
    count = 0
    total = 0
    for path, size, mtime_ns in windows.iter_files(
            root, cancel=cancel, on_progress=on_progress):
        if _is_marker_file(path, root):
            continue
        count += 1
        total += size
        if count <= MANIFEST_MAX_FILES:
            rel = os.path.relpath(path, root)
            manifest.entries[rel] = (size, mtime_ns)
            if strict:
                digest = _hash_file(path, cancel)
                if digest:
                    manifest.hashes[rel] = digest
        else:
            manifest.truncated = True
        if cancel and cancel():
            break
    manifest.files = count
    manifest.bytes = total
    return manifest


def verify_manifest(manifest: Manifest, dest: str, *,
                    cancel: Callable[[], bool] | None = None,
                    strict: bool = False,
                    on_progress: Callable[[int, int], None] | None = None) -> tuple[bool, list[str]]:
    """校验目标副本：文件数 / 字节数 / 逐文件大小；strict 时再比哈希。"""
    problems: list[str] = []
    if not os.path.isdir(dest):
        return False, ["目标目录不存在"]
    matched = 0
    total = 0
    checked = 0
    for path, size, mtime_ns in windows.iter_files(dest, cancel=cancel):
        if _is_marker_file(path, dest):
            continue
        checked += 1
        total += size
        rel = os.path.relpath(path, dest)
        expected = manifest.entries.get(rel)
        if expected is not None:
            if int(expected[0]) != size:
                problems.append(f"大小不一致：{rel}（源 {expected[0]} / 目标 {size}）")
                if len(problems) >= 12:
                    break
            else:
                matched += 1
            if strict and rel in manifest.hashes:
                digest = _hash_file(path, cancel)
                if digest and digest != manifest.hashes[rel]:
                    problems.append(f"哈希不一致：{rel}")
                    if len(problems) >= 12:
                        break
    if checked != manifest.files:
        problems.append(f"文件数不一致：源 {manifest.files} / 目标 {checked}")
    if total != manifest.bytes:
        problems.append(f"总字节不一致：源 {manifest.bytes} / 目标 {total}")
    if not manifest.truncated and matched != manifest.files:
        missing = manifest.files - matched
        if missing > 0 and not problems:
            problems.append(f"{missing} 个文件缺失")
    return (not problems), problems


# ============================================================
# 操作上下文
# ============================================================

@dataclass
class OperationContext:
    config: Any
    audit: AuditLog
    drives: list | None = None
    progress: ProgressCallback | None = None
    cancel: Callable[[], bool] | None = None
    job_id: str = ""
    strict: bool = False
    manifest_dir: str = ""
    _started: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.manifest_dir:
            self.manifest_dir = str(paths.manifests_dir())

    @property
    def canceled(self) -> bool:
        try:
            return bool(self.cancel and self.cancel())
        except Exception:
            return False

    def emit(self, phase: str, percent: float, message: str = "", *,
             bytes_done: int = 0, bytes_total: int = 0, speed: float = 0.0,
             eta: float = 0.0, item_index: int = 0, item_count: int = 1,
             detail: str = "") -> None:
        if not self.progress:
            return
        try:
            self.progress(Progress(
                phase=phase, percent=max(0.0, min(100.0, percent)),
                message=message, bytes_done=bytes_done, bytes_total=bytes_total,
                speed_bps=speed, eta_s=eta, item_index=item_index,
                item_count=item_count, detail=detail,
            ))
        except Exception:
            pass


def _new_id(prefix: str = "op") -> str:
    return f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _join_errors(rows: Iterable[str]) -> str:
    text = "；".join([r for r in rows if r])
    return text[:800] if len(text) > 800 else text


def _record(ctx: OperationContext, item: OperationItem, status: str,
            started: float, *, verified: bool, error: str = "",
            bytes_moved: int = 0, files: int = 0,
            extra: dict[str, Any] | None = None) -> str:
    rec = OperationRecord(
        id=ctx.job_id or _new_id(item.action),
        ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
        action=item.action,
        mode=item.mode,
        source=item.source,
        dest=item.dest,
        name=item.name or os.path.basename(item.source.rstrip("\\/")),
        status=status,
        bytes_moved=int(bytes_moved),
        files=int(files),
        duration_s=round(time.time() - started, 2),
        verified=bool(verified),
        needs_admin=bool(item.needs_admin),
        error=error,
        extra=extra or {},
    )
    ctx.audit.append(rec)
    return rec.id


def _result(item: OperationItem, *, ok: bool, started: float,
            error: str = "", warnings: list[str] | None = None,
            verified: bool = False, bytes_moved: int = 0, files: int = 0,
            record_id: str = "", rolled_back: bool = False,
            extra: dict[str, Any] | None = None) -> OperationResult:
    return OperationResult(
        ok=ok, action=item.action, source=item.source, dest=item.dest,
        name=item.name or os.path.basename(item.source.rstrip("\\/")),
        mode=item.mode, bytes_total=bytes_moved, files_total=files,
        duration_s=round(time.time() - started, 2), verified=verified,
        error=error, warnings=list(warnings or []), record_id=record_id,
        rolled_back=rolled_back, extra=extra or {},
    )


def _ensure_admin_warning(pre: PreflightResult) -> list[str]:
    warnings = list(pre.warnings)
    if pre.requires_admin:
        warnings.append("该操作需要管理员权限（将由提权 helper 执行）")
    return warnings


def _grant_permissions(path: str) -> str:
    user = os.environ.get("USERNAME") or ""
    if not user or not os.path.isdir(path):
        return ""
    res = windows.run_cmd(
        ["icacls", path, "/grant", f"{user}:F", "/t", "/q", "/c"],
        timeout=300,
    )
    return "" if res.code == 0 else (res.stderr or res.stdout or "icacls 失败")


def _prune_manifests(directory: str, keep: int = 30) -> None:
    try:
        files = sorted(
            [p for p in os.scandir(directory) if p.is_file()],
            key=lambda e: e.stat().st_mtime, reverse=True,
        )
        for entry in files[max(1, keep):]:
            try:
                os.unlink(entry.path)
            except OSError:
                pass
    except OSError:
        pass


def _prune_logs(directory: str, keep_days: int) -> None:
    if keep_days <= 0:
        return
    cutoff = time.time() - keep_days * 86400
    try:
        for entry in os.scandir(directory):
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                try:
                    os.unlink(entry.path)
                except OSError:
                    pass
    except OSError:
        pass


# ============================================================
# 迁移
# ============================================================

def _copy_with_progress(src: str, dst: str, manifest: Manifest,
                        ctx: OperationContext, *, base_pct: float,
                        span_pct: float, cancel_ok: bool = True,
                        exclude_marker: bool = False) -> tuple[bool, str, windows.CopyResult]:
    ctx.emit("复制文件", base_pct, f"正在复制 {human_bytes(manifest.bytes)}…",
             bytes_total=manifest.bytes)

    def on_progress(done: int, total: int, speed: float) -> None:
        total = total or manifest.bytes or 1
        pct = base_pct + min(1.0, done / total) * span_pct
        eta = (total - done) / speed if speed > 1 else 0.0
        ctx.emit("复制文件", pct,
                 f"已复制 {human_bytes(done)} / {human_bytes(total)}",
                 bytes_done=done, bytes_total=total, speed=speed, eta=eta)

    result = windows.robocopy_copy(
        src, dst, total_bytes=manifest.bytes,
        cancel=ctx.cancel if cancel_ok else None,
        on_progress=on_progress, mirror=False,
        exclude_marker=exclude_marker,
    )
    if result.canceled:
        return False, "用户已取消", result
    if not result.ok:
        tail = (result.output or "").splitlines()[-6:]
        return False, result.error + ("：" + " | ".join(tail) if tail else ""), result
    return True, "", result


def _write_marker(dst: str, src: str, item: OperationItem, op_id: str,
                  size: int) -> None:
    try:
        safety.write_origin(dst, src, action=item.action, mode=item.mode,
                            op_id=op_id, size_bytes=size)
    except OSError:
        pass


def _rollback_migration(src: str, dst: str, manifest: Manifest,
                        ctx: OperationContext) -> tuple[bool, str]:
    """链接创建失败：把已验证的副本回拷到原位置。"""
    ctx.emit("回滚", 96, "链接创建失败，正在把数据回拷到原位置…")
    try:
        os.makedirs(os.path.dirname(src), exist_ok=True)
    except OSError:
        pass
    copy = windows.robocopy_copy(dst, src, total_bytes=manifest.bytes,
                                 cancel=None, mirror=False,
                                 exclude_marker=True)
    if not copy.ok:
        return False, f"回滚复制失败：{copy.error}"
    ok, problems = verify_manifest(manifest, src, cancel=None)
    if not ok:
        return False, "回滚校验失败：" + _join_errors(problems)
    # 目标副本已无用，且来源标记匹配才删除
    origin = safety.read_origin(dst)
    try:
        if safety._canon(origin.get("source", "")) == safety._canon(src):
            windows.safe_delete_tree(dst)
    except Exception:
        pass
    return True, ""


def migrate_item(item: OperationItem, ctx: OperationContext,
                 item_index: int = 0, item_count: int = 1) -> OperationResult:
    started = time.time()
    pre = safety.preflight_migrate(item, ctx.config, ctx.drives)
    if not pre.ok:
        err = _join_errors(pre.errors)
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      extra={"stage": "preflight"})
        return _result(item, ok=False, started=started, error=err,
                       warnings=_ensure_admin_warning(pre), record_id=rec)

    src = os.path.abspath(item.source)
    dst = os.path.abspath(item.dest)
    op_id = ctx.job_id or _new_id("mig")
    ctx.job_id = op_id
    ctx.emit("生成清单", 2, "扫描源目录，生成校验清单…",
             item_index=item_index, item_count=item_count)

    def manifest_progress(count: int, total: int) -> None:
        ctx.emit("生成清单", 2 + min(6, count / 5000 * 6),
                 f"已记录 {count:,} 个文件…", bytes_done=total,
                 item_index=item_index, item_count=item_count)

    manifest = build_manifest(src, cancel=ctx.cancel, on_progress=manifest_progress,
                              strict=ctx.strict)
    if ctx.canceled:
        _record(ctx, item, "canceled", started, verified=False,
                error="用户取消", bytes_moved=manifest.bytes, files=manifest.files)
        return _result(item, ok=False, started=started, error="用户已取消",
                       bytes_moved=manifest.bytes, files=manifest.files)
    if manifest.files == 0:
        err = "源目录为空，未执行迁移"
        rec = _record(ctx, item, "failed", started, verified=False, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    manifest_path = manifest.save(str(paths.manifests_dir()), op_id)

    try:
        os.makedirs(dst, exist_ok=True)
    except OSError as exc:
        err = f"无法创建目标目录：{exc}"
        rec = _record(ctx, item, "failed", started, verified=False, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    _write_marker(dst, src, item, op_id, manifest.bytes)

    ok, err, _copy = _copy_with_progress(src, dst, manifest, ctx,
                                         base_pct=9, span_pct=58)
    if not ok:
        status = "canceled" if ctx.canceled else "failed"
        rec = _record(ctx, item, status, started, verified=False, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "copy", "dest": dst, "manifest": manifest_path})
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"dest": dst})

    ctx.emit("校验副本", 69, "逐文件比对大小与数量…",
             item_index=item_index, item_count=item_count)
    verified, problems = verify_manifest(manifest, dst, cancel=ctx.cancel,
                                         strict=ctx.strict)
    if not verified:
        err = "复制校验失败，源目录未删除：" + _join_errors(problems)
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "verify", "dest": dst, "manifest": manifest_path})
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"dest": dst})

    ctx.emit("设置权限", 78, "继承原目录访问权限…",
             item_index=item_index, item_count=item_count)
    acl_warn = _grant_permissions(dst)
    warnings = _ensure_admin_warning(pre)
    if acl_warn:
        warnings.append(f"权限设置部分失败：{acl_warn[:200]}")

    if ctx.config.check_locks:
        locks = windows.processes_using(src)
        if locks:
            err = "复制完成后检测到源目录仍被占用，已停止删除：" + safety.lock_summary(locks)
            rec = _record(ctx, item, "failed", started, verified=True, error=err,
                          bytes_moved=manifest.bytes, files=manifest.files,
                          extra={"stage": "lock", "dest": dst, "manifest": manifest_path})
            return _result(item, ok=False, started=started, error=err,
                           warnings=warnings, verified=True,
                           bytes_moved=manifest.bytes, files=manifest.files,
                           record_id=rec, extra={"dest": dst})

    ctx.emit("删除源目录", 82, "副本已校验，正在删除 C 盘原目录…",
             item_index=item_index, item_count=item_count)

    def del_progress(files: int, size: int) -> None:
        ctx.emit("删除源目录", 82 + min(10, files / 5000 * 10),
                 f"已删除 {files:,} 个文件…", bytes_done=size,
                 bytes_total=manifest.bytes, item_index=item_index,
                 item_count=item_count)

    delete = windows.safe_delete_tree(src, cancel=None, on_progress=del_progress)
    if not delete.ok:
        err = ("原目录删除不完整（数据已完整复制并校验，位于目标目录）："
               + _join_errors(delete.errors))
        rec = _record(ctx, item, "failed", started, verified=True, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "delete", "dest": dst,
                             "manifest": manifest_path, "delete_errors": delete.errors[:20]})
        return _result(item, ok=False, started=started, error=err,
                       warnings=warnings, verified=True,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"dest": dst})

    ctx.emit("创建链接", 94, "在原位置创建 Junction…",
             item_index=item_index, item_count=item_count)
    ok_link, link_err = windows.create_junction(src, dst)
    if not ok_link:
        rolled, rollback_err = _rollback_migration(src, dst, manifest, ctx)
        err = f"链接创建失败：{link_err}。"
        if rolled:
            err += "数据已回拷到原位置并校验。"
        else:
            err += f"自动回滚未完成（{rollback_err}）；数据完整保存在 {dst}。"
        rec = _record(ctx, item, "rolled_back" if rolled else "failed", started,
                      verified=True, error=err, bytes_moved=manifest.bytes,
                      files=manifest.files,
                      extra={"stage": "junction", "dest": dst,
                             "manifest": manifest_path, "rollback": rolled})
        return _result(item, ok=False, started=started, error=err,
                       warnings=warnings, verified=True,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, rolled_back=rolled,
                       extra={"dest": dst, "rollback": rolled})

    ctx.emit("完成", 100, f"迁移完成，释放 {human_bytes(manifest.bytes)}",
             bytes_done=manifest.bytes, bytes_total=manifest.bytes,
             item_index=item_index, item_count=item_count)
    rec = _record(ctx, item, "success", started, verified=True,
                  bytes_moved=manifest.bytes, files=manifest.files,
                  extra={"dest": dst, "manifest": manifest_path})
    _prune_manifests(str(paths.manifests_dir()),
                     int(ctx.config.raw.get("safety", {}).get("keep_manifests", 30) or 30))
    return _result(item, ok=True, started=started, warnings=warnings,
                   verified=True, bytes_moved=manifest.bytes,
                   files=manifest.files, record_id=rec,
                   extra={"dest": dst, "manifest": manifest_path})


# ============================================================
# 撤销迁移
# ============================================================

def undo_item(item: OperationItem, ctx: OperationContext,
              item_index: int = 0, item_count: int = 1) -> OperationResult:
    started = time.time()
    pre = safety.preflight_undo(item, ctx.config, ctx.drives)
    if not pre.ok:
        err = _join_errors(pre.errors)
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      extra={"stage": "preflight"})
        return _result(item, ok=False, started=started, error=err,
                       warnings=pre.warnings, record_id=rec)

    src = os.path.abspath(item.source)
    target = windows.junction_target(src)
    op_id = ctx.job_id or _new_id("undo")
    ctx.job_id = op_id
    ctx.emit("生成清单", 2, "扫描链接目标，生成校验清单…",
             item_index=item_index, item_count=item_count)
    manifest = build_manifest(target, cancel=ctx.cancel, strict=ctx.strict)
    if manifest.files == 0:
        err = "链接目标为空，未执行撤销"
        rec = _record(ctx, item, "failed", started, verified=False, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    manifest_path = manifest.save(str(paths.manifests_dir()), op_id)

    ctx.emit("移除链接", 8, "删除 Junction（不会删除目标数据）…",
             item_index=item_index, item_count=item_count)
    if not windows.remove_link(src):
        err = "无法删除 Junction，可能有程序正在占用"
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      extra={"stage": "unlink", "target": target})
        return _result(item, ok=False, started=started, error=err, record_id=rec)

    ok, err, _copy = _copy_with_progress(target, src, manifest, ctx,
                                         base_pct=12, span_pct=58,
                                         exclude_marker=True)
    if not ok:
        # 复制失败：恢复链接，保证原路径仍可用
        restored, _ = windows.create_junction(src, target)
        err += "；" + ("已恢复链接，数据仍可访问" if restored else
                       f"链接未能恢复，数据完整保存在 {target}")
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "copy_back", "target": target,
                             "relinked": restored})
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"target": target})

    ctx.emit("校验副本", 72, "逐文件比对回迁结果…",
             item_index=item_index, item_count=item_count)
    verified, problems = verify_manifest(manifest, src, cancel=ctx.cancel,
                                         strict=ctx.strict)
    if not verified:
        restored, _ = windows.create_junction(src, target)
        err = "回迁校验失败：" + _join_errors(problems)
        err += ("；已恢复链接" if restored else f"；数据完整保存在 {target}")
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "verify_back", "target": target,
                             "relinked": restored})
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"target": target})

    acl_warn = _grant_permissions(src)
    warnings = list(pre.warnings)
    if acl_warn:
        warnings.append(f"权限设置部分失败：{acl_warn[:200]}")

    origin = safety.read_origin(target)
    marker_ok = bool(origin) and safety._canon(origin.get("source", "")) == safety._canon(src)
    want_delete = bool(item.extra.get("delete_target", False)) or (
        marker_ok and ctx.config.delete_after_undo)
    removed = False
    if want_delete:
        ctx.emit("释放目标盘", 90, "回迁已校验，正在释放迁移目标…",
                 item_index=item_index, item_count=item_count)
        if not marker_ok:
            warnings.append("目标目录没有来源标记：默认保留目标副本（可在历史中手动清理）")
        else:
            report = windows.safe_delete_tree(target)
            removed = report.ok
            if not removed:
                warnings.append("目标副本删除不完整：" + _join_errors(report.errors))

    ctx.emit("完成", 100, f"回迁完成，{human_bytes(manifest.bytes)} 已回到原分区",
             item_index=item_index, item_count=item_count)
    rec = _record(ctx, item, "success", started, verified=True,
                  bytes_moved=manifest.bytes, files=manifest.files,
                  extra={"target": target, "manifest": manifest_path,
                         "target_removed": removed, "marker": marker_ok})
    return _result(item, ok=True, started=started, warnings=warnings,
                   verified=True, bytes_moved=manifest.bytes,
                   files=manifest.files, record_id=rec,
                   extra={"target": target, "target_removed": removed})


# ============================================================
# 冷数据归档
# ============================================================

def archive_item(item: OperationItem, ctx: OperationContext,
                 item_index: int = 0, item_count: int = 1) -> OperationResult:
    started = time.time()
    pre = safety.preflight_archive(item, ctx.config, ctx.drives)
    if not pre.ok:
        err = _join_errors(pre.errors)
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      extra={"stage": "preflight"})
        return _result(item, ok=False, started=started, error=err,
                       warnings=pre.warnings, record_id=rec)

    src = os.path.abspath(item.source)
    dst = os.path.abspath(item.dest)
    mode = item.mode or MODE_MOVE
    is_link_source = windows.is_link(src)
    work_src = windows.junction_target(src) if is_link_source else src
    if is_link_source and not work_src:
        err = "无法读取源目录的链接目标"
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)

    op_id = ctx.job_id or _new_id("arc")
    ctx.job_id = op_id
    ctx.emit("生成清单", 2, "扫描归档源，生成校验清单…",
             item_index=item_index, item_count=item_count)
    manifest = build_manifest(work_src, cancel=ctx.cancel, strict=ctx.strict)
    if ctx.canceled:
        _record(ctx, item, "canceled", started, verified=False, error="用户取消",
                bytes_moved=manifest.bytes, files=manifest.files)
        return _result(item, ok=False, started=started, error="用户已取消",
                       bytes_moved=manifest.bytes, files=manifest.files)
    if manifest.files == 0:
        err = "源目录为空，未执行归档"
        rec = _record(ctx, item, "failed", started, verified=False, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    manifest_path = manifest.save(str(paths.manifests_dir()), op_id)

    try:
        os.makedirs(dst, exist_ok=True)
    except OSError as exc:
        err = f"无法创建归档目录：{exc}"
        rec = _record(ctx, item, "failed", started, verified=False, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    _write_marker(dst, src, item, op_id, manifest.bytes)

    ok, err, _copy = _copy_with_progress(work_src, dst, manifest, ctx,
                                         base_pct=9, span_pct=58)
    if not ok:
        status = "canceled" if ctx.canceled else "failed"
        rec = _record(ctx, item, status, started, verified=False, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "copy", "dest": dst, "manifest": manifest_path})
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"dest": dst})

    ctx.emit("校验副本", 69, "逐文件比对归档副本…",
             item_index=item_index, item_count=item_count)
    verified, problems = verify_manifest(manifest, dst, cancel=ctx.cancel,
                                         strict=ctx.strict)
    if not verified:
        err = "归档校验失败，源目录未删除：" + _join_errors(problems)
        rec = _record(ctx, item, "failed", started, verified=False, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"stage": "verify", "dest": dst, "manifest": manifest_path})
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec, extra={"dest": dst})

    warnings = list(pre.warnings)
    if mode == MODE_COPY:
        ctx.emit("完成", 100, "仅复制完成，源目录保留",
                 item_index=item_index, item_count=item_count)
        rec = _record(ctx, item, "success", started, verified=True,
                      bytes_moved=manifest.bytes, files=manifest.files,
                      extra={"dest": dst, "manifest": manifest_path, "mode": mode,
                             "junction_source": is_link_source,
                             "old_target": work_src if is_link_source else ""})
        return _result(item, ok=True, started=started, warnings=warnings,
                       verified=True, bytes_moved=manifest.bytes,
                       files=manifest.files, record_id=rec,
                       extra={"dest": dst, "mode": mode})

    if ctx.config.check_locks:
        locks = windows.processes_using(work_src)
        if locks:
            err = "副本已校验，但源目录仍被占用，未删除：" + safety.lock_summary(locks)
            rec = _record(ctx, item, "failed", started, verified=True, error=err,
                          bytes_moved=manifest.bytes, files=manifest.files,
                          extra={"stage": "lock", "dest": dst})
            return _result(item, ok=False, started=started, error=err,
                           warnings=warnings, verified=True,
                           bytes_moved=manifest.bytes, files=manifest.files,
                           record_id=rec, extra={"dest": dst})

    ctx.emit("删除源目录", 82, "副本已校验，正在删除源目录…",
             item_index=item_index, item_count=item_count)

    def del_progress(files: int, size: int) -> None:
        ctx.emit("删除源目录", 82 + min(10, files / 5000 * 10),
                 f"已删除 {files:,} 个文件…", bytes_done=size,
                 bytes_total=manifest.bytes, item_index=item_index,
                 item_count=item_count)

    if is_link_source:
        # 先移除链接，再删旧目标：链接是 0 字节，删它不会碰数据
        if not windows.remove_link(src):
            err = "副本已校验，但无法移除原目录的 Junction"
            rec = _record(ctx, item, "failed", started, verified=True, error=err,
                          bytes_moved=manifest.bytes, files=manifest.files,
                          extra={"stage": "unlink", "dest": dst, "old_target": work_src})
            return _result(item, ok=False, started=started, error=err,
                           warnings=warnings, verified=True,
                           bytes_moved=manifest.bytes, files=manifest.files,
                           record_id=rec, extra={"dest": dst})
        ctx.emit("删除旧目标", 84, f"正在释放旧目标 {human_bytes(manifest.bytes)}…",
                 item_index=item_index, item_count=item_count)
        delete = windows.safe_delete_tree(work_src, cancel=None,
                                          on_progress=del_progress)
        if not delete.ok:
            restored_link, _ = windows.create_junction(src, work_src)
            err = ("旧目标删除不完整；数据已校验并保存在归档目标。"
                   + ("已恢复原链接。" if restored_link else
                      f"原链接未能恢复，数据完整保存在 {dst}。"))
            rec = _record(ctx, item, "failed", started, verified=True, error=err,
                          bytes_moved=manifest.bytes, files=manifest.files,
                          extra={"stage": "delete_old_target", "dest": dst,
                                 "old_target": work_src,
                                 "delete_errors": delete.errors[:20]})
            return _result(item, ok=False, started=started, error=err,
                           warnings=warnings, verified=True,
                           bytes_moved=manifest.bytes, files=manifest.files,
                           record_id=rec, extra={"dest": dst})
        if mode == MODE_LINK:
            ctx.emit("重建链接", 94, "正在把原路径链接到归档目标…",
                     item_index=item_index, item_count=item_count)
            ok_link, link_err = windows.create_junction(src, dst)
            if not ok_link:
                # 目标数据已在归档盘，旧目标已删除；尝试再建一次链接
                retry_ok, _retry = windows.create_junction(src, dst)
                err = (f"旧目标已释放、数据已校验保存在 {dst}，但链接创建失败：{link_err}"
                       + ("" if retry_ok else "；原路径当前不可用，可在链接管理页重试"))
                rec = _record(ctx, item, "failed", started, verified=True, error=err,
                              bytes_moved=manifest.bytes, files=manifest.files,
                              extra={"stage": "relink", "dest": dst,
                                     "old_target": work_src, "relinked": retry_ok})
                return _result(item, ok=False, started=started, error=err,
                               warnings=warnings, verified=True,
                               bytes_moved=manifest.bytes, files=manifest.files,
                               record_id=rec, extra={"dest": dst})
    else:
        delete = windows.safe_delete_tree(src, cancel=None, on_progress=del_progress)
        if not delete.ok:
            err = ("源目录删除不完整（数据已完整校验并保存在归档目标）："
                   + _join_errors(delete.errors))
            rec = _record(ctx, item, "failed", started, verified=True, error=err,
                          bytes_moved=manifest.bytes, files=manifest.files,
                          extra={"stage": "delete", "dest": dst,
                                 "manifest": manifest_path,
                                 "delete_errors": delete.errors[:20]})
            return _result(item, ok=False, started=started, error=err,
                           warnings=warnings, verified=True,
                           bytes_moved=manifest.bytes, files=manifest.files,
                           record_id=rec, extra={"dest": dst})

        if mode == MODE_LINK:
            ctx.emit("创建链接", 94, "在原位置创建 Junction…",
                     item_index=item_index, item_count=item_count)
            ok_link, link_err = windows.create_junction(src, dst)
            if not ok_link:
                restored, rollback_err = _rollback_archive_link(src, dst, manifest, ctx)
                err = f"链接创建失败：{link_err}。"
                err += ("数据已回拷到原位置并校验。" if restored else
                        f"自动回滚未完成（{rollback_err}）；数据完整保存在 {dst}。")
                rec = _record(ctx, item, "rolled_back" if restored else "failed",
                              started, verified=True, error=err,
                              bytes_moved=manifest.bytes, files=manifest.files,
                              extra={"stage": "junction", "dest": dst,
                                     "rollback": restored})
                return _result(item, ok=False, started=started, error=err,
                               warnings=warnings, verified=True,
                               bytes_moved=manifest.bytes, files=manifest.files,
                               record_id=rec, rolled_back=restored,
                               extra={"dest": dst, "rollback": restored})

    ctx.emit("完成", 100, f"归档完成，释放 {human_bytes(manifest.bytes)}",
             bytes_done=manifest.bytes, bytes_total=manifest.bytes,
             item_index=item_index, item_count=item_count)
    rec = _record(ctx, item, "success", started, verified=True,
                  bytes_moved=manifest.bytes, files=manifest.files,
                  extra={"dest": dst, "manifest": manifest_path, "mode": mode,
                         "junction_source": is_link_source,
                         "old_target": work_src if is_link_source else ""})
    _prune_manifests(str(paths.manifests_dir()),
                     int(ctx.config.raw.get("safety", {}).get("keep_manifests", 30) or 30))
    return _result(item, ok=True, started=started, warnings=warnings,
                   verified=True, bytes_moved=manifest.bytes,
                   files=manifest.files, record_id=rec,
                   extra={"dest": dst, "mode": mode,
                          "junction_source": is_link_source,
                          "old_target": work_src if is_link_source else ""})


def _rollback_archive_link(src: str, dst: str, manifest: Manifest,
                           ctx: OperationContext) -> tuple[bool, str]:
    ctx.emit("回滚", 96, "链接创建失败，正在回拷数据…")
    try:
        os.makedirs(os.path.dirname(src), exist_ok=True)
    except OSError:
        pass
    copy = windows.robocopy_copy(dst, src, total_bytes=manifest.bytes,
                                 cancel=None, mirror=False,
                                 exclude_marker=True)
    if not copy.ok:
        return False, f"回滚复制失败：{copy.error}"
    ok, problems = verify_manifest(manifest, src, cancel=None)
    if not ok:
        return False, "回滚校验失败：" + _join_errors(problems)
    try:
        origin = safety.read_origin(dst)
        if safety._canon(origin.get("source", "")) == safety._canon(src):
            windows.safe_delete_tree(dst)
    except Exception:
        pass
    return True, ""


# ============================================================
# 归档回迁
# ============================================================

def restore_archive(item: OperationItem, ctx: OperationContext,
                    item_index: int = 0, item_count: int = 1) -> OperationResult:
    """把归档目标的数据复制回原路径（移动归档的逆操作）。"""
    started = time.time()
    src = os.path.abspath(item.source)   # 原路径（可能不存在）
    dst = os.path.abspath(item.dest)     # 归档目标
    if not os.path.isdir(dst):
        err = f"归档数据不存在：{dst}"
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    if os.path.lexists(src):
        if windows.is_link(src):
            pass
        elif os.path.isdir(src) and not os.listdir(src):
            pass
        else:
            err = "原路径已存在数据，不能回迁（请先清理）"
            rec = _record(ctx, item, "failed", started, error=err)
            return _result(item, ok=False, started=started, error=err, record_id=rec)

    manifest = build_manifest(dst, cancel=ctx.cancel, strict=ctx.strict)
    free = windows.free_bytes(os.path.dirname(src))
    need = manifest.bytes + max(safety.MIN_FREE_MARGIN, int(manifest.bytes * 0.02))
    if free < need:
        err = f"C 盘空间不足：需要 {human_bytes(need)}，当前 {human_bytes(free)}"
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    if windows.is_link(src):
        if not windows.remove_link(src):
            err = "无法移除原路径的链接"
            rec = _record(ctx, item, "failed", started, error=err)
            return _result(item, ok=False, started=started, error=err, record_id=rec)

    op_id = ctx.job_id or _new_id("res")
    manifest_path = manifest.save(str(paths.manifests_dir()), op_id)
    ok, err, _copy = _copy_with_progress(dst, src, manifest, ctx,
                                         base_pct=8, span_pct=62,
                                         exclude_marker=True)
    if not ok:
        _record(ctx, item, "failed", started, error=err,
                bytes_moved=manifest.bytes, files=manifest.files)
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files)
    verified, problems = verify_manifest(manifest, src, cancel=ctx.cancel,
                                         strict=ctx.strict)
    if not verified:
        err = "回迁校验失败：" + _join_errors(problems)
        rec = _record(ctx, item, "failed", started, error=err,
                      bytes_moved=manifest.bytes, files=manifest.files)
        return _result(item, ok=False, started=started, error=err,
                       bytes_moved=manifest.bytes, files=manifest.files,
                       record_id=rec)
    warnings: list[str] = []
    _grant_permissions(src)
    origin = safety.read_origin(dst)
    if safety._canon(origin.get("source", "")) == safety._canon(src):
        report = windows.safe_delete_tree(dst)
        if not report.ok:
            warnings.append("归档副本删除不完整：" + _join_errors(report.errors))
    else:
        warnings.append("归档目录没有来源标记，已保留副本")
    rec = _record(ctx, item, "success", started, verified=True,
                  bytes_moved=manifest.bytes, files=manifest.files,
                  extra={"dest": dst, "manifest": manifest_path})
    return _result(item, ok=True, started=started, warnings=warnings,
                   verified=True, bytes_moved=manifest.bytes,
                   files=manifest.files, record_id=rec, extra={"dest": dst})


# ============================================================
# 重建链接
# ============================================================

def relink_item(item: OperationItem, ctx: OperationContext,
                item_index: int = 0, item_count: int = 1) -> OperationResult:
    started = time.time()
    pre = safety.preflight_link(item, ctx.config, ctx.drives)
    if not pre.ok:
        err = _join_errors(pre.errors)
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    src = os.path.abspath(item.source)
    dst = os.path.abspath(item.dest)
    if os.path.lexists(src):
        if not windows.remove_link(src):
            err = "无法移除旧链接"
            rec = _record(ctx, item, "failed", started, error=err)
            return _result(item, ok=False, started=started, error=err, record_id=rec)
    ok, err = windows.create_junction(src, dst)
    if not ok:
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    rec = _record(ctx, item, "success", started, verified=True,
                  extra={"dest": dst})
    return _result(item, ok=True, started=started, verified=True, record_id=rec)


def unlink_item(item: OperationItem, ctx: OperationContext,
                item_index: int = 0, item_count: int = 1) -> OperationResult:
    """只移除目录链接，不触碰目标数据（用于清理失效链接）。"""
    started = time.time()
    src = os.path.abspath(item.source)
    if not os.path.lexists(src):
        err = "链接不存在"
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    if not windows.is_link(src):
        err = "该路径不是目录链接"
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    target = windows.junction_target(src)
    if not windows.remove_link(src):
        err = "无法移除链接，可能被占用"
        rec = _record(ctx, item, "failed", started, error=err)
        return _result(item, ok=False, started=started, error=err, record_id=rec)
    rec = _record(ctx, item, "success", started, verified=True,
                  extra={"target": target, "unlinked": True})
    return _result(item, ok=True, started=started, verified=True,
                   record_id=rec, extra={"target": target})


# ============================================================
# 清理
# ============================================================

def clean_temp(ctx: OperationContext, retention_days: int | None = None) -> OperationResult:
    started = time.time()
    temp = os.environ.get("TEMP") or os.path.join(
        os.environ.get("USERPROFILE", ""), "AppData", "Local", "Temp")
    days = retention_days if retention_days is not None else ctx.config.temp_retention_days
    cutoff = time.time() - max(0, days) * 86400
    files_deleted = 0
    bytes_deleted = 0
    skipped = 0
    errors: list[str] = []
    ctx.emit("扫描临时文件", 5, f"扫描 {temp}…")
    stack = [temp]
    all_dirs: list[str] = []
    while stack:
        if ctx.canceled:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_junction() or entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            all_dirs.append(entry.path)
                            continue
                        st = entry.stat(follow_symlinks=False)
                        if st.st_mtime > cutoff:
                            skipped += 1
                            continue
                        try:
                            if entry.name and entry.path:
                                windows._force_writable(entry.path)
                                os.unlink(entry.path)
                            files_deleted += 1
                            bytes_deleted += int(st.st_size)
                        except OSError:
                            skipped += 1
                    except OSError:
                        skipped += 1
        except OSError as exc:
            errors.append(f"{current}: {exc}")
    # 清空空目录（只处理本次遍历过的真实目录，不跟随链接）
    for directory in reversed(all_dirs):
        if os.path.normcase(directory) == os.path.normcase(temp):
            continue
        try:
            if not os.listdir(directory):
                os.rmdir(directory)
        except OSError:
            pass
    item = OperationItem(action=ACTION_CLEAN, source=temp, dest="",
                         name="Temp 清理", size_bytes=bytes_deleted)
    rec = _record(ctx, item, "success", started, verified=True,
                  bytes_moved=bytes_deleted, files=files_deleted,
                  extra={"skipped": skipped, "errors": errors[:10],
                         "retention_days": days})
    _prune_logs(str(paths.logs_dir()), ctx.config.keep_days)
    return OperationResult(
        ok=True, action=ACTION_CLEAN, source=temp, name="Temp 清理",
        bytes_total=bytes_deleted, files_total=files_deleted,
        duration_s=round(time.time() - started, 2), verified=True,
        warnings=[f"跳过 {skipped} 个占用/新文件"] if skipped else [],
        record_id=rec, extra={"skipped": skipped},
    )


def empty_recycle_bin(letters: list[str], ctx: OperationContext) -> OperationResult:
    started = time.time()
    before = windows.free_bytes(f"{letters[0]}:\\") if letters else 0
    for letter in letters:
        letter = letter.strip().rstrip(":").upper()[:1]
        if not letter:
            continue
        windows.run_ps(
            f"try {{ Clear-RecycleBin -DriveLetter {letter} -Force -ErrorAction Stop }} catch {{ }}",
            timeout=180,
        )
    after = windows.free_bytes(f"{letters[0]}:\\") if letters else 0
    freed = max(0, after - before)
    item = OperationItem(action=ACTION_CLEAN, source="回收站",
                         dest=",".join(letters), name="回收站清理",
                         size_bytes=freed)
    rec = _record(ctx, item, "success", started, verified=True,
                  bytes_moved=freed, extra={"drives": letters})
    return OperationResult(ok=True, action=ACTION_CLEAN, source="回收站",
                           name="回收站清理", bytes_total=freed,
                           duration_s=round(time.time() - started, 2),
                           verified=True, record_id=rec)


# ============================================================
# 批处理入口
# ============================================================

def run_item(item: OperationItem, ctx: OperationContext,
             item_index: int = 0, item_count: int = 1) -> OperationResult:
    try:
        if item.action == ACTION_MIGRATE:
            return migrate_item(item, ctx, item_index, item_count)
        if item.action == ACTION_UNDO:
            return undo_item(item, ctx, item_index, item_count)
        if item.action == ACTION_ARCHIVE:
            return archive_item(item, ctx, item_index, item_count)
        if item.action == ACTION_RESTORE:
            return restore_archive(item, ctx, item_index, item_count)
        if item.action == ACTION_LINK:
            return relink_item(item, ctx, item_index, item_count)
        if item.action == ACTION_UNLINK:
            return unlink_item(item, ctx, item_index, item_count)
        if item.action == ACTION_CLEAN:
            if item.extra.get("clean") == "recycle":
                return empty_recycle_bin(item.extra.get("drives", []), ctx)
            return clean_temp(ctx, retention_days=item.extra.get("retention_days"))
        return _result(item, ok=False, started=time.time(),
                       error=f"未知操作：{item.action}")
    except Exception as exc:  # 兜底：任何异常都写审计，不让 GUI 崩
        started = time.time()
        try:
            _record(ctx, item, "failed", started, error=f"未捕获异常：{exc}")
        except Exception:
            pass
        return _result(item, ok=False, started=started,
                       error=f"内部错误：{exc}")


def run_batch(items: list[OperationItem], ctx: OperationContext) -> list[OperationResult]:
    results: list[OperationResult] = []
    total = len(items)
    for index, item in enumerate(items):
        if ctx.canceled:
            results.append(_result(item, ok=False, started=time.time(),
                                   error="用户已取消"))
            continue
        ctx.job_id = ""
        ctx.emit("准备", 0, f"准备{('迁移' if item.action == ACTION_MIGRATE else '处理')}：{item.name}",
                 item_index=index + 1, item_count=total)
        results.append(run_item(item, ctx, index + 1, total))
    return results
