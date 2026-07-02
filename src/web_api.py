"""HTTP API 服务。

提供 Web UI 和 REST API：
  GET  /              → 前端页面
  POST /api/scan      → 扫描所有区域
  POST /api/migrate   → 迁移目录
  POST /api/undo      → 撤销迁移
  POST /api/admin-migrate → 管理员迁移（生成 bat + UAC）
  POST /api/admin-undo    → 管理员撤销
  POST /api/admin-result  → 查询管理员脚本结果
  POST /api/clean-temp    → 清理 Temp
  POST /api/status        → 查询磁盘空间
  POST /api/quit          → 关闭服务
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .config import PORT
from .scanner import scan_all, get_drive_info
from .migrator import migrate_dir, undo_junction, clean_temp
from .admin_ops import (
    generate_admin_bat,
    elevate_and_run,
    get_junction_target,
    read_admin_result,
)


def _get_web_dir() -> Path:
    """获取 web 目录路径，兼容源码运行和 PyInstaller 打包。

    - 源码运行：项目根目录下的 web/
    - 打包运行：exe 同级的 web/（datas 打包的文件 PyInstaller 会解压到临时目录）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "web"
    return Path(__file__).resolve().parent.parent / "web"


_WEB_DIR = _get_web_dir()
_INDEX_HTML = _WEB_DIR / "index.html"


class APIHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器。"""

    def _send_json(self, data: dict[str, Any]) -> None:
        """发送 JSON 响应。"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self) -> dict[str, Any]:
        """读取 POST body 并解析为 JSON。"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def do_POST(self) -> None:
        """处理 POST 请求，路由到对应 API。"""
        body = self._read_body()
        handler = _ROUTES.get(self.path)
        if handler:
            result = handler(body)
            self._send_json(result)
        else:
            self._send_json({"error": "unknown endpoint"})

    def do_GET(self) -> None:
        """处理 GET 请求，返回前端页面。"""
        if self.path in ("/", "/index.html"):
            self._serve_index()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_index(self) -> None:
        """返回前端 HTML。"""
        if _INDEX_HTML.exists():
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_INDEX_HTML.read_bytes())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"index.html not found")

    def log_message(self, *args: Any) -> None:
        """静默日志输出（不打印到控制台）。"""
        pass


# ===== API 路由处理函数 =====

def _handle_scan(body: dict[str, Any]) -> dict[str, Any]:
    """扫描所有区域。"""
    threshold = body.get("threshold", 100)
    return scan_all(threshold)


def _handle_migrate(body: dict[str, Any]) -> dict[str, Any]:
    """迁移目录。"""
    source = body.get("path", "")
    dest = body.get("dest", "")
    name = body.get("name", "")
    if not source or not dest:
        return {"success": False, "error": "缺少参数"}

    result = migrate_dir(source, dest, name)
    _add_drive_info(result)
    return result


def _handle_undo(body: dict[str, Any]) -> dict[str, Any]:
    """撤销迁移。"""
    source = body.get("path", "")
    name = body.get("name", "")
    if not source:
        return {"success": False, "error": "缺少路径参数"}

    result = undo_junction(source, name)
    _add_drive_info(result)
    return result


def _handle_admin_migrate(body: dict[str, Any]) -> dict[str, Any]:
    """管理员迁移：生成 bat + 触发 UAC。"""
    source = body.get("path", "")
    dest = body.get("dest", "")
    name = body.get("name", "")
    size_mb = body.get("sizeMB", 0)
    if not source or not dest or not name:
        return {"success": False, "error": "缺少参数"}

    try:
        bat_path, bat_name, result_file = generate_admin_bat(
            name, source, dest, size_mb, "migrate"
        )
        uac_ok = elevate_and_run(bat_path)
        return {
            "success": True,
            "uacTriggered": uac_ok,
            "scriptFile": bat_name,
            "scriptPath": bat_path,
            "resultFile": result_file,
            "instructions": (
                "UAC prompt should appear. Click Yes to proceed."
                if uac_ok
                else f'Right-click CMD -> Run as administrator -> cd /d "{os.path.dirname(bat_path)}" -> {bat_name}'
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _handle_admin_undo(body: dict[str, Any]) -> dict[str, Any]:
    """管理员撤销：查询 target → 生成 bat → 触发 UAC。"""
    source = body.get("path", "")
    name = body.get("name", "")
    dest = body.get("dest", "")
    if not source or not name:
        return {"success": False, "error": "缺少参数"}

    try:
        # 优先从 Junction 查询 target
        if not dest:
            target = get_junction_target(source)
            if target:
                dest = target
        if not dest:
            return {"success": False, "error": "Cannot determine Junction target"}

        bat_path, bat_name, result_file = generate_admin_bat(
            name, source, dest, 0, "undo"
        )
        uac_ok = elevate_and_run(bat_path)
        return {
            "success": True,
            "uacTriggered": uac_ok,
            "scriptFile": bat_name,
            "scriptPath": bat_path,
            "resultFile": result_file,
            "instructions": (
                "UAC prompt should appear. Click Yes to proceed."
                if uac_ok
                else f'Right-click CMD -> Run as administrator -> cd /d "{os.path.dirname(bat_path)}" -> {bat_name}'
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _handle_admin_result(body: dict[str, Any]) -> dict[str, Any]:
    """查询管理员脚本执行结果。"""
    name = body.get("name", "")
    if not name:
        return {"success": False, "error": "缺少name参数"}
    return read_admin_result(name)


def _handle_clean_temp(body: dict[str, Any]) -> dict[str, Any]:
    """清理 Temp 目录。"""
    result = clean_temp()
    _add_drive_info(result)
    return result


def _handle_status(body: dict[str, Any]) -> dict[str, Any]:
    """查询磁盘空间状态。"""
    c_total, c_free, d_free = get_drive_info()
    return {"cTotalGB": c_total, "cFreeGB": c_free, "dFreeGB": d_free}


def _handle_quit(body: dict[str, Any]) -> dict[str, Any]:
    """关闭服务器（异步 shutdown）。"""
    # 延迟 shutdown，让响应先发出去
    def _shutdown() -> None:
        import time
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return {"success": True}


# ===== 辅助函数 =====

def _add_drive_info(result: dict[str, Any]) -> None:
    """给结果追加磁盘空间信息。"""
    _, c_free, d_free = get_drive_info()
    result["cFreeGB"] = c_free
    result["dFreeGB"] = d_free


# ===== 路由表 =====

_ROUTES = {
    "/api/scan": _handle_scan,
    "/api/migrate": _handle_migrate,
    "/api/undo": _handle_undo,
    "/api/admin-migrate": _handle_admin_migrate,
    "/api/admin-undo": _handle_admin_undo,
    "/api/admin-result": _handle_admin_result,
    "/api/clean-temp": _handle_clean_temp,
    "/api/status": _handle_status,
    "/api/quit": _handle_quit,
}


def create_server() -> HTTPServer:
    """创建 HTTP 服务器实例。"""
    return HTTPServer(("localhost", PORT), APIHandler)
