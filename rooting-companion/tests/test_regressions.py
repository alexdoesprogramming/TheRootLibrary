"""Regression tests for safety-critical, offline helpers."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from main import safe_extract_zip
from quest_features import _load_json_file


class JsonLoadingTests(unittest.TestCase):
    def test_loads_valid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.json"
            path.write_text('{"ok": true}', encoding="utf-8")
            self.assertEqual(_load_json_file(path, {}), {"ok": True})

    def test_missing_file_returns_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "missing.json"
            fallback = {"schema": 1}
            self.assertEqual(_load_json_file(path, fallback), fallback)

    def test_malformed_json_returns_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.json"
            path.write_text("{ definitely not json", encoding="utf-8")
            self.assertEqual(_load_json_file(path, []), [])


class SafeZipExtractionTests(unittest.TestCase):
    def test_extracts_normal_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "safe.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("folder/hello.txt", "hello")
            safe_extract_zip(archive, destination)
            self.assertEqual((destination / "folder" / "hello.txt").read_text(encoding="utf-8"), "hello")

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            destination = root / "out"
            outside = root / "escaped.txt"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escaped.txt", "should never be written")
            with self.assertRaises(RuntimeError):
                safe_extract_zip(archive, destination)
            self.assertFalse(outside.exists())

    def test_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "absolute.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(str((root / "outside.txt").resolve()), "nope")
            with self.assertRaises(RuntimeError):
                safe_extract_zip(archive, destination)


if __name__ == "__main__":
    unittest.main(verbosity=2)
