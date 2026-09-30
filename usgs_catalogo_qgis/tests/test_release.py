# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import tempfile
import unittest
from pathlib import Path
import zipfile

from usgs_catalogo_qgis.tools.prepare_release import build, release_errors


class ReleaseTests(unittest.TestCase):
    def fixture(self, root):
        for filename in ("__init__.py", "LICENSE", "NOTICE", "README.md", "icon.png"):
            (root / filename).write_bytes(b"test fixture")
        return {"name": "Fixture", "description": "Test imagery tool", "about": "Test only",
                "version": "0.9.0", "author": "Fixture", "qgisMinimumVersion": "3.22",
                "email": "unit@example.org", "homepage": "https://github.com/fixture/project#readme",
                "repository": "https://github.com/fixture/project",
                "tracker": "https://github.com/fixture/project/issues",
                "license": "GPL-2.0-or-later", "icon": "icon.png"}

    def test_release_blocks_missing_public_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self.fixture(root)
            self.assertFalse(release_errors(root, values))
            for key in ("homepage", "repository", "tracker"):
                values[key] = ""
            errors = release_errors(root, values)
            self.assertEqual(len(errors), 3)
            self.assertTrue(any("repository" in error for error in errors))

    def test_release_rejects_url_credentials_and_placeholder_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = self.fixture(root)
            for url in ("https://example.com/repo", "https://user:token@github.com/repo",
                        "http://github.com/fixture/repo", "https://project.invalid/repo"):
                values["repository"] = url
                self.assertTrue(any("repository" in error for error in release_errors(root, values)))

    def test_package_has_one_folder_and_excludes_releases_and_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "usgs_catalogo_qgis"
            root.mkdir()
            self.fixture(root)
            (root / "metadata.txt").write_text("[general]\nversion=0.9.0\n")
            (root / "old.zip").write_bytes(b"exclude")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "module.py").write_text("exclude")
            (root / ".git").mkdir()
            (root / ".git" / "config.txt").write_text("exclude")
            target = Path(directory) / "release.zip"
            build(root, target)
            with zipfile.ZipFile(target) as archive:
                names = archive.namelist()
                self.assertTrue(all(name.startswith("usgs_catalogo_qgis/") for name in names))
                self.assertIn("usgs_catalogo_qgis/LICENSE", names)
                self.assertIn("usgs_catalogo_qgis/icon.png", names)
                self.assertFalse(any("__pycache__" in name or ".git" in name or name.endswith(".zip")
                                     for name in names))
                self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
