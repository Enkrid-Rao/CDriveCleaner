"""应用入口：GUI、单实例、自检、提权 helper。"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import traceback
from pathlib import Path

from . import paths
from .version import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="CDriveCleaner",
        description="C 盘瘦身与冷数据归档",
        add_help=True,
    )
    parser.add_argument("--elevated", metavar="JOB", help=argparse.SUPPRESS)
    parser.add_argument("--self-check", action="store_true",
                        help="检查运行环境并输出 JSON 后退出")
    parser.add_argument("--diagnose", action="store_true",
                        help="打印配置、磁盘与路径诊断")
    parser.add_argument("--page", default="", help="启动后直接打开某个页面")
    parser.add_argument("--smoke", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"CDriveCleaner {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.elevated:
        from .core.jobs import run_elevated_job
        return run_elevated_job(args.elevated)

    if args.self_check:
        return _self_check()
    if args.diagnose:
        return _diagnose()

    if args.smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        return _run_gui(args.page, smoke=True)
    return _run_gui(args.page)


# ============================================================
# 环境 / 字体
# ============================================================

def ensure_fonts() -> None:
    """在 offscreen / 字体目录缺失时显式加载 Windows 字体。"""
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:
        return
    try:
        if QFontDatabase.families():
            return
    except Exception:
        return
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\segoeui.ttf",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows"
            / "Fonts" / "JetBrainsMono-Regular.ttf"),
        r"C:\Windows\Fonts\consola.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:
                pass


def _pick_fonts() -> tuple[str, str]:
    from PySide6.QtGui import QFontDatabase
    families = set()
    try:
        families = set(QFontDatabase.families())
    except Exception:
        pass

    def first(options: list[str], fallback: str) -> str:
        for option in options:
            if option in families:
                return option
        return fallback

    ui = first(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI",
                "PingFang SC", "Noto Sans CJK SC"], "Segoe UI")
    mono = first(["JetBrains Mono", "Cascadia Code", "Cascadia Mono",
                  "Consolas"], ui)
    return ui, mono


def _set_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "EnkridRao.CDriveCleaner")
    except Exception:
        pass


# ============================================================
# GUI
# ============================================================

def _run_gui(start_page: str = "", smoke: bool = False) -> int:
    if sys.platform != "win32":
        print("CDriveCleaner 仅支持 Windows。")
        return 2

    _set_app_id()

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("CDriveCleaner")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("EnkridRao")
    app.setStyle("Fusion")
    ensure_fonts()

    from .ui import theme
    from .ui.app_fonts import apply_font
    from .ui.window import MainWindow
    from .ui.state import AppState

    ui_family, mono_family = _pick_fonts()
    apply_font(app, ui_family, mono_family)

    # 单实例：已有实例则唤醒后退出
    from .ui.single_instance import SingleInstance
    instance = SingleInstance()
    if not instance.try_listen():
        instance.activate_existing()
        return 0

    state = AppState()
    if start_page:
        state.config.last_page = start_page
    app.setStyleSheet(theme.build_qss(state.config.font_size, state.config.motion))
    theme.set_motion(state.config.motion)

    window = MainWindow(state)
    window.show()
    instance.set_window(window)

    icon_file = paths.asset_path("assets", "CDriveCleaner.ico")
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    _install_excepthook()
    if smoke:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, app.quit)
    return app.exec()


def _install_excepthook() -> None:
    def handler(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(paths.crash_log_path(), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = handler


# ============================================================
# 自检 / 诊断
# ============================================================

def _self_check() -> int:
    data: dict = {
        "version": __version__,
        "frozen": paths.is_frozen(),
        "portable": paths.is_portable(),
        "data_dir": str(paths.data_dir()),
        "config": str(paths.config_path()),
        "admin": False,
        "drives": [],
        "config_ok": False,
        "qt": "",
        "errors": [],
    }
    try:
        from PySide6 import QtCore
        data["qt"] = QtCore.__version__
    except Exception as exc:
        data["errors"].append(f"Qt 导入失败：{exc}")
    try:
        from .core import windows
        data["admin"] = windows.is_admin()
        for drive in windows.list_drives(force=True):
            data["drives"].append({
                "letter": drive.letter, "free_gb": round(drive.free_bytes / 1024 ** 3, 1),
                "total_gb": round(drive.total_bytes / 1024 ** 3, 1),
                "media": drive.media_label,
            })
    except Exception as exc:
        data["errors"].append(f"磁盘检测失败：{exc}")
    try:
        from .core.config import load_config
        cfg = load_config()
        data["config_ok"] = True
        data["link_root"] = cfg.link_root
        data["archive_root"] = cfg.archive_root
        data["zones"] = len(cfg.zones)
    except Exception as exc:
        data["errors"].append(f"配置加载失败：{exc}")
    try:
        from PySide6.QtWidgets import QApplication
        data["qt_widgets"] = True
    except Exception as exc:
        data["errors"].append(f"QtWidgets 导入失败：{exc}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if not data["errors"] and data["config_ok"] else 1


def _diagnose() -> int:
    from .core import windows
    from .core.config import load_config
    cfg = load_config()
    print(f"CDriveCleaner {__version__}")
    print(f"运行形态 : {'便携版' if paths.is_portable() else '安装版' if paths.is_frozen() else '源码'}")
    print(f"数据目录 : {paths.data_dir()}")
    print(f"配置文件 : {cfg.path}")
    print(f"迁移容器 : {cfg.link_root}")
    print(f"归档根   : {cfg.archive_root}")
    print(f"管理员   : {windows.is_admin()}")
    print("磁盘     :")
    for drive in windows.list_drives(force=True):
        print(f"  {drive.letter}: {drive.total_bytes / 1024**3:7.1f} GB "
              f"可用 {drive.free_bytes / 1024**3:7.1f} GB  {drive.media_label}"
              f"  {drive.model}")
    print("扫描区域 :")
    for key, zone in cfg.zones.items():
        print(f"  {key:12s} {zone.get('source')} → {zone.get('dest_base')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
