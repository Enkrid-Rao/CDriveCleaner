from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from tests import base  # noqa: F401  (设置 CDC_DATA_DIR)
from cdc.core import config


class ConfigTests(unittest.TestCase):
    def test_first_run_creates_default(self):
        path = Path(tempfile.mkdtemp(prefix="cfg_")) / "config.json"
        cfg = config.load_config(path)
        self.assertTrue(path.exists())
        self.assertEqual(cfg.raw["version"], 2)
        self.assertIn("userhome", cfg.zones)
        self.assertTrue(cfg.link_root)

    def test_v1_migration_keeps_zones_and_paths(self):
        path = Path(tempfile.mkdtemp(prefix="cfg_v1_")) / "config.json"
        v1 = {
            "version": "1.0",
            "target_base": "D:\\_CDrive",
            "threshold_mb": 250,
            "temp_retention_days": 3,
            "ui": {"font_size": 14},
            "zones": {
                "local": {
                    "source": "{USERPROFILE}\\AppData\\Local",
                    "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Local",
                    "no_go": ["Microsoft"],
                    "label": "Local",
                }
            },
        }
        path.write_text(json.dumps(v1), encoding="utf-8")
        cfg = config.load_config(path)
        self.assertEqual(cfg.link_root, "D:\\_CDrive")
        self.assertEqual(cfg.threshold_mb, 250)
        self.assertEqual(cfg.temp_retention_days, 3)
        self.assertEqual(cfg.font_size, 14)
        self.assertIn("local", cfg.zones)
        self.assertNotIn("{TARGET_BASE}", cfg.zones["local"]["dest_base"])
        self.assertTrue(cfg.zones["local"]["dest_base"].startswith("D:\\_CDrive"))

    def test_save_roundtrip_and_backup(self):
        path = Path(tempfile.mkdtemp(prefix="cfg_save_")) / "config.json"
        cfg = config.load_config(path)
        cfg.threshold_mb = 777
        cfg.archive_root = "E:\\Archive"
        cfg.save()
        cfg2 = config.load_config(path)
        self.assertEqual(cfg2.threshold_mb, 777)
        self.assertEqual(cfg2.archive_root, "E:\\Archive")
        self.assertTrue(list((base.data_root() / "state" / "backups").glob("config-*.json")))

    def test_broken_config_falls_back(self):
        path = Path(tempfile.mkdtemp(prefix="cfg_bad_")) / "config.json"
        path.write_text("{not json", encoding="utf-8")
        cfg = config.load_config(path)
        self.assertTrue(cfg.warnings)
        self.assertEqual(cfg.raw["version"], 2)


if __name__ == "__main__":
    unittest.main()
