"""离屏渲染 UI 截图（开发 / 文档用，不随安装包分发）。

用法：
    python tools/preview_ui.py [输出目录]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("CDC_DATA_DIR",
                      str(Path(tempfile.mkdtemp(prefix="cdc_preview_"))))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])
from cdc.app import ensure_fonts, _pick_fonts  # noqa: E402

ensure_fonts()
from cdc.ui import theme  # noqa: E402
from cdc.ui.state import AppState  # noqa: E402
from cdc.ui.window import MainWindow  # noqa: E402
from cdc.core.models import (  # noqa: E402
    AnalysisResult, ArchiveCandidate, JunctionInfo, OperationRecord, Progress,
    ScanItem, ScanResult, TIER_OPTIONAL, TIER_RECOMMEND, TIER_SKIP, TIER_STRONG,
    human_bytes,
)

theme.set_motion(False)


def now_ts(days_ago: float = 0) -> float:
    return time.time() - days_ago * 86400


def make_scan() -> ScanResult:
    items = [
        ("DeepSeek Harness", 22.4, "programs", "应用程序", True),
        ("JetBrains", 16.8, "programfiles", "应用本体 · Program Files", True),
        ("Code", 8.9, "roaming", "应用数据 · Roaming", False),
        ("Doubao", 7.2, "local", "应用数据 · Local", False),
        ("Adobe", 5.6, "local", "应用数据 · Local", False),
        ("Tencent", 4.3, "local", "应用数据 · Local", False),
        ("Blackmagic Design", 3.8, "programdata", "共享数据 · ProgramData", True),
        ("FlowLauncher", 1.2, "local", "应用数据 · Local", False),
    ]
    rows = []
    for name, gb, zone, label, admin in items:
        size = int(gb * 1024 ** 3)
        rows.append(ScanItem(
            name=name,
            path=f"C:\\Users\\raoxi\\AppData\\Local\\{name}",
            size_bytes=size, zone_key=zone, zone_label=label,
            dest_path=f"D:\\_CDrive\\Users\\raoxi\\AppData\\Local\\{name}",
            needs_admin=admin, file_count=int(gb * 4200), newest_ts=now_ts(30),
        ))
    junctions = []
    for name, gb, target, zone, broken, usb in [
        ("Steam", 12.4, "D:\\_CDrive\\Users\\raoxi\\AppData\\Local\\Steam", "local", False, False),
        ("Google", 6.1, "D:\\_CDrive\\Users\\raoxi\\AppData\\Local\\Google", "local", False, False),
        ("Tencent\\xwechat", 3.4, "D:\\_CDrive\\Users\\raoxi\\AppData\\Roaming\\Tencent\\xwechat", "roaming", False, False),
        ("JetBrains", 16.8, "D:\\_CDrive\\Program Files\\JetBrains", "programfiles", False, False),
        ("NVIDIA", 2.2, "E:\\ColdStore\\C\\NVIDIA", "roaming", False, True),
        ("CodeBuddy CN", 1.9, "D:\\_CDrive\\Users\\raoxi\\AppData\\Roaming\\CodeBuddy CN", "roaming", False, False),
        ("Bionic", 0.8, "E:\\Archive\\Bionic", "programs", True, True),
    ]:
        junctions.append(JunctionInfo(
            name=name, path=f"C:\\Users\\raoxi\\AppData\\{name}", target=target,
            zone_key=zone, zone_label=zone, size_bytes=int(gb * 1024 ** 3),
            file_count=int(gb * 3000), target_exists=not broken,
            target_on_usb=usb, target_drive=target[:1], mine=target.startswith("D:\\_CDrive"),
            broken=broken,
        ))
    protected = [
        ScanItem("AppData", "C:\\Users\\raoxi\\AppData", 48 * 1024 ** 3,
                 "userhome", "用户主目录", "", protected=True, protected_reason="受保护"),
        ScanItem("Microsoft", "C:\\Users\\raoxi\\AppData\\Roaming\\Microsoft", 9 * 1024 ** 3,
                 "roaming", "应用数据 · Roaming", "", protected=True, protected_reason="受保护"),
        ScanItem("Microsoft", "C:\\ProgramData\\Microsoft", 12 * 1024 ** 3,
                 "programdata", "共享数据 · ProgramData", "", protected=True, protected_reason="受保护"),
    ]
    return ScanResult(
        scanned_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        duration_s=18.6, items=rows, junctions=junctions, protected_items=protected,
        potential_bytes=sum(i.size_bytes for i in rows),
        released_bytes=sum(j.size_bytes for j in junctions),
        temp_bytes=int(6.4 * 1024 ** 3), backend="everything",
    )


def make_analysis() -> AnalysisResult:
    rows = [
        ("Videos", "C:\\Users\\raoxi\\Videos", 12.3, TIER_STRONG,
         "视频为主，顺序读取，机械盘非常适合", {"video": 0.94, "image": 0.03}, 210, False, ""),
        ("ISO", "C:\\Users\\raoxi\\Downloads\\ISO", 11.1, TIER_STRONG,
         "镜像/虚拟磁盘，读一次就归档", {"iso": 0.86, "installer": 0.09}, 320, False, ""),
        ("AppStore", "D:\\AppStore", 17.7, TIER_STRONG,
         "安装包/应用包，装完即弃", {"installer": 0.88, "archive": 0.07}, 160, False, ""),
        ("Downloads", "C:\\Users\\raoxi\\Downloads", 30.1, TIER_RECOMMEND,
         "下载缓冲目录：消耗品多，归档后可随时回看 · 已通过 Junction 存放在其他盘，归档后会更新链接",
         {"installer": 0.36, "archive": 0.28, "iso": 0.2}, 18, True,
         "D:\\_CDrive\\Users\\raoxi\\Downloads"),
        (".lmstudio", "C:\\Users\\raoxi\\.lmstudio", 38.7, TIER_RECOMMEND,
         "模型权重文件，读取以顺序大块为主 · 已通过 Junction 存放在其他盘，归档后会更新链接",
         {"model": 0.91, "other": 0.05}, 70, True,
         "D:\\_CDrive\\Users\\raoxi\\.lmstudio"),
        ("软件安装包", "C:\\Users\\raoxi\\Downloads\\软件安装包", 8.4, TIER_RECOMMEND,
         "安装包/应用包，装完即弃", {"installer": 0.72, "archive": 0.18}, 96, False, ""),
        ("Pictures", "C:\\Users\\raoxi\\Pictures", 3.2, TIER_RECOMMEND,
         "图片素材为主，适合机械盘", {"image": 0.88, "document": 0.04}, 180, False, ""),
        (".android", "C:\\Users\\raoxi\\.android", 13.6, TIER_OPTIONAL,
         "Android 模拟器 / 镜像目录：不跑模拟器时是冷数据，运行时随机 IO 很多 · 已通过 Junction 存放在其他盘，归档后会更新链接",
         {"iso": 0.72, "other": 0.2}, 25, True,
         "D:\\_CDrive\\Users\\raoxi\\.android"),
        ("Documents", "C:\\Users\\raoxi\\Documents", 4.1, TIER_OPTIONAL,
         "体积很大但构成混合，建议打开确认后再归档", {"document": 0.41, "image": 0.22}, 45, False, ""),
        ("Projects", "D:\\Projects", 8.2, TIER_SKIP,
         "代码/版本库目录：小文件随机读写多，不建议放机械盘", {"code": 0.66, "other": 0.22}, 2, False, ""),
        ("qq聊天记录", "D:\\qq聊天记录", 4.2, TIER_SKIP,
         "聊天/数据库目录：高频随机读写，机械盘会明显变慢", {"other": 0.72, "image": 0.2}, 2, False, ""),
    ]
    cands = []
    for name, path, gb, tier, reason, exts, age, linked, target in rows:
        size = int(gb * 1024 ** 3)
        ext_bytes = {k: int(size * v) for k, v in exts.items()}
        drive = path[:1]
        rel = path[3:]
        cands.append(ArchiveCandidate(
            name=name, path=path, size_bytes=size, file_count=int(gb * 850),
            newest_ts=now_ts(age), oldest_ts=now_ts(age + 400),
            ext_bytes=ext_bytes, tier=tier,
            score=94 if tier == TIER_STRONG else 80 if tier == TIER_RECOMMEND else 52,
            reason=reason,
            dest_path=f"E:\\ColdStore\\{name}",
            source_drive=drive, is_junction=linked, target_path=target,
        ))
    return AnalysisResult(
        scanned_at=time.strftime("%Y-%m-%dT%H:%M:%S"), duration_s=26.2,
        candidates=cands, roots=["C:\\Users\\raoxi", "D:\\"],
        total_recommended_bytes=sum(c.size_bytes for c in cands
                                    if c.tier in (TIER_STRONG, TIER_RECOMMEND)),
    )


def seed_history(state: AppState) -> None:
    rows = [
        ("mig", "migrate", "move", "success", "JetBrains", 16.8, 3600, 42.1, True, ""),
        ("arc", "archive", "move", "success", "ISO", 11.1, 2310, 96.4, True, ""),
        ("und", "undo", "move", "success", "Adobe", 5.6, 1180, 51.2, True, ""),
        ("arc2", "archive", "copy", "success", "Pictures", 3.2, 680, 22.8, True, ""),
        ("bad", "migrate", "move", "failed", "Blackmagic Design", 3.8, 1200, 8.4, False,
         "目标目录正在被 DaVinci Resolve 使用，已停止删除。"),
        ("clean", "clean", "move", "success", "Temp 清理", 6.4, 6240, 18.2, True, ""),
    ]
    for idx, (rid, action, mode, status, name, gb, files, dur, verified, err) in enumerate(rows):
        rec = OperationRecord(
            id=rid, ts=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - idx * 86400)),
            action=action, mode=mode, source=f"C:\\Users\\raoxi\\{name}",
            dest=f"D:\\_CDrive\\Users\\raoxi\\{name}", name=name, status=status,
            bytes_moved=int(gb * 1024 ** 3), files=files, duration_s=dur,
            verified=verified, error=err,
        )
        state.audit.append(rec)


def pump(ms: int = 250) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    state = AppState()
    seed_history(state)
    scan = make_scan()
    analysis = make_analysis()
    ui_family, mono = _pick_fonts()
    app.setStyleSheet(theme.build_qss(13, False))
    window = MainWindow(state)
    window.resize(1440, 900)
    window.show()
    pump(300)
    state.scan = scan
    state.analysis = analysis
    state.scan_finished.emit(scan)
    state.analysis_finished.emit(analysis)
    state.history_changed.emit()
    pump(400)

    for key in ["dashboard", "slimming", "archive", "links", "history", "settings"]:
        window.navigate(key, refresh=True)
        pump(350)
        window.grab().save(str(out / f"{key}.png"))
        print("saved", key)

    # 批量选择状态
    window.navigate("slimming", refresh=True)
    pump(250)
    slim = window.pages["slimming"]
    for row in slim._rows[:3]:
        row.set_checked(True)
    pump(250)
    window.grab().save(str(out / "slimming_selected.png"))
    slim._clear_selection()

    window.navigate("archive", refresh=True)
    pump(250)
    arc = window.pages["archive"]
    picked = 0
    for row in arc._rows:
        if row.candidate.tier == TIER_SKIP:
            continue
        row.set_checked(True)
        picked += 1
        if picked >= 3:
            break
    pump(250)
    window.grab().save(str(out / "archive_selected.png"))
    arc._clear_selection()

    # 已链接冷数据：用更高的窗口同时展示顶部与链接行
    window.resize(1440, 1180)
    pump(250)
    for row in arc._rows:
        if row.candidate.is_junction:
            arc.scroll.ensureWidgetVisible(row)
            break
    pump(300)
    window.grab().save(str(out / "archive_linked.png"))
    window.resize(1440, 900)
    pump(200)

    # 确认弹窗
    from cdc.ui.widgets import ConfirmDialog
    window.navigate("slimming", refresh=True)
    pump(200)
    dlg = ConfirmDialog(
        window, "迁移 3 个目录？",
        "复制到迁移容器后建立 Junction，原路径保持不变。预计释放 48.3 GB。",
        "开始迁移", tone="brand",
        details="· DeepSeek Harness  22.4 GB\n· JetBrains  16.8 GB\n· Code  8.9 GB\n\n"
                "目标根路径：D:\\_CDrive",
        note="需要管理员权限：会先弹出 UAC，输入管理员凭据后整批执行。",
        note_tone="warn", require_check=True,
    )
    dlg.show()
    pump(220)
    dlg.grab().save(str(out / "confirm.png"))
    dlg.close()

    # 进度面板
    window.navigate("slimming", refresh=True)
    window.overlay.show_operation(
        "正在归档 2 个目录", "复制 → 校验 → 删除源，冷数据移入机械盘", 2,
        ["准备", "复制", "校验", "完成"], "archive")
    window.overlay.update_progress(Progress(
        phase="复制文件", percent=47, message="已复制 23.6 GB / 49.8 GB",
        bytes_done=int(23.6 * 1024 ** 3), bytes_total=int(49.8 * 1024 ** 3),
        speed_bps=118 * 1024 ** 2, eta_s=226, item_index=1, item_count=2,
        detail="E:\\ColdStore\\C\\Users\\raoxi\\Videos",
    ))
    pump(250)
    window.grab().save(str(out / "progress.png"))
    window.overlay.finish()

    # Toast
    from cdc.ui.widgets import Toast
    window.navigate("dashboard", refresh=True)
    Toast.show_message(window, "迁移完成 · JetBrains · 释放 16.8 GB", "success")
    pump(450)
    window.grab().save(str(out / "toast.png"))
    print("done", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
