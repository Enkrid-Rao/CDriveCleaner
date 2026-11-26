"""测试公共环境：必须在导入 cdc 前设置数据目录。"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import shutil
import tempfile
import uuid
from pathlib import Path

_BASE = Path(tempfile.mkdtemp(prefix="cdc_test_data_"))
os.environ["CDC_DATA_DIR"] = str(_BASE)
os.environ["CDC_NO_PROBE"] = "1"


def temp_tree(prefix: str = "cdc_test") -> tuple[Path, Path]:
    """返回 (D 盘临时目录, E 盘临时目录)，确保跨分区。"""
    token = uuid.uuid4().hex[:10]
    d = Path("D:/Temp") / f"{prefix}_{token}"
    e = Path("E:/Temp") / f"{prefix}_{token}"
    d.mkdir(parents=True, exist_ok=True)
    e.mkdir(parents=True, exist_ok=True)
    return d, e


def cleanup(*paths: Path) -> None:
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)


def data_root() -> Path:
    return _BASE


def lock_dir(path: str) -> tuple:
    """以「不允许删除」的共享方式打开目录，模拟占用者。返回 (kernel32, handle)。"""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                     wt.DWORD, wt.DWORD, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateFileW(os.path.abspath(path), 0x80000000, 0x1, None, 3,
                                  0x02000000 | 0x00200000, None)
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise OSError("无法打开目录句柄")
    return kernel32, handle


def unlock_dir(kernel32, handle) -> None:
    kernel32.CloseHandle(ctypes.c_void_p(handle))


class _FILE_BASIC_INFO(ctypes.Structure):
    _fields_ = [
        ("CreationTime", ctypes.c_longlong),
        ("LastAccessTime", ctypes.c_longlong),
        ("LastWriteTime", ctypes.c_longlong),
        ("ChangeTime", ctypes.c_longlong),
        ("FileAttributes", wt.DWORD),
    ]


def set_link_readonly(path: str) -> bool:
    """给链接对象自身加只读属性（不跟随到目标）。"""
    attrs = os.lstat(path).st_file_attributes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                     wt.DWORD, wt.DWORD, ctypes.c_void_p]
    kernel32.SetFileInformationByHandle.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                    ctypes.c_void_p, wt.DWORD]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateFileW(os.path.abspath(path), 0x0080 | 0x0100, 0x7, None, 3,
                                  0x02000000 | 0x00200000, None)
    if not handle or handle == ctypes.c_void_p(-1).value:
        return False
    try:
        info = _FILE_BASIC_INFO(0, 0, 0, 0, attrs | 0x1)
        return bool(kernel32.SetFileInformationByHandle(
            handle, 0, ctypes.byref(info), ctypes.sizeof(info)))
    finally:
        kernel32.CloseHandle(ctypes.c_void_p(handle))

os.environ.setdefault("CDC_NO_EVERYTHING", "1")  # 测试固定走真实文件系统