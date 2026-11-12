"""生成 v2 应用图标（PNG + ICO）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

app = QApplication(sys.argv[:1])
from cdc.ui import icons  # noqa: E402

size = 256
pix = icons.logo_pixmap(size)
image = pix.toImage()
png_path = ROOT / "assets" / "CDriveCleaner-v2.png"
image.save(str(png_path), "PNG")
print("saved", png_path, image.width(), image.height())

from PIL import Image  # noqa: E402
img = Image.open(png_path).convert("RGBA")
img = img.resize((size, size), Image.LANCZOS)
ico_path = ROOT / "assets" / "CDriveCleaner.ico"
img.save(ico_path, format="ICO",
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                (128, 128), (256, 256)])
print("saved", ico_path)
