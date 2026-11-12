"""测试公共环境：必须在导入 cdc 前设置数据目录。"""

from __future__ import annotations

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
