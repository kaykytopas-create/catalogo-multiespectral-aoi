# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import json
import os
import sys
import tempfile
import types
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid
from unittest.mock import patch

from usgs_catalogo_qgis.archive import LocalArchive, digest
from usgs_catalogo_qgis.stac import CatalogError, PublicCatalog, default_rgb_keys, natural_rgb_keys


def scene(identifier="LT05_TEST", acquired="2000-07-07T00:00:00Z", cloud=10):
    return {"id": identifier, "collection": "landsat-c2-l2",
            "properties": {"datetime": acquired, "eo:cloud_cover": cloud},
            "assets": {key: {"href": "https://host/{}.tif".format(key),
                             "eo:bands": [{"name": key}]}
                       for key in ("blue", "green", "red", "nir08", "swir16")}}


class ArchiveTests(unittest.TestCase):
    def test_catalog_survives_restart_and_filters_dates(self):
        with tempfile.TemporaryDirectory() as root:
            archive = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            archive.remember_many([scene(), scene("NEW", "2026-01-01T00:00:00Z"),
                                   scene("CLOUDY", cloud=21)])
            reopened = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            result = reopened.search(["landsat-c2-l2"], "1982-01-01", "2004-12-31")
            self.assertEqual([item["id"] for item in result], ["LT05_TEST"])
            self.assertNotEqual(archive.area_id,
                LocalArchive(root, (-51, -7, -49, -6), "EPSG:31982").area_id)
            self.assertNotEqual(archive.area_id,
                LocalArchive(root, (-50, -7, -49, -6), "EPSG:4326").area_id)

    def test_legacy_archive_remains_available_offline_but_online_uses_new_crop(self):
        with tempfile.TemporaryDirectory() as root:
            rect, crs = (-50.0, -7.0, -49.0, -6.0), "EPSG:31982"
            legacy_id = digest({"bbox": list(rect), "crs": crs, "context": [3.2, 2.4]})
            folder = os.path.join(root, "areas", legacy_id)
            os.makedirs(folder)
            with open(os.path.join(folder, "catalogo.json"), "w") as stream:
                json.dump({"version": 1, "scenes": {"scene": {"item": scene()}}}, stream)
            offline = LocalArchive(root, rect, crs, allow_legacy=True)
            self.assertTrue(offline.uses_legacy_extent)
            self.assertEqual(offline.area_id, legacy_id)
            self.assertEqual(len(offline.search(["landsat-c2-l2"], "1982-01-01", "2026-12-31")), 1)
            online = LocalArchive(root, rect, crs)
            self.assertNotEqual(online.area_id, legacy_id)
            self.assertFalse(online.uses_legacy_extent)
            online.remember(scene("NEW"))
            reopened = LocalArchive(root, rect, crs, allow_legacy=True)
            self.assertFalse(reopened.uses_legacy_extent)
            self.assertEqual(reopened.area_id, online.area_id)
            self.assertTrue(os.path.isfile(os.path.join(folder, "catalogo.json")))

    def test_full_pagination_updates_without_duplicate_downloads(self):
        with tempfile.TemporaryDirectory() as root:
            archive = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            downloaded = set()
            class Client:
                def cancelled(self): return False
                def search(self, collections, rect, start, end, link):
                    return ([scene("SECOND", "2001-01-01T00:00:00Z")], None) if link else (
                        [scene(), scene()], {"href": "https://example/page2"})
                def cache_bands(self, item, folder, rect, crs, progress, keys):
                    downloaded.add(item["id"])
                    return {}, []
            result = archive.sync(Client(), ["landsat-c2-l2"], "1982-01-01", "2026-12-31", lambda _: None)
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(result["completed"], 2)
            self.assertEqual(downloaded, {"LT05_TEST", "SECOND"})
            self.assertEqual(len(archive.read()["scenes"]), 2)

    def test_partial_downloads_are_not_reported_as_complete(self):
        with tempfile.TemporaryDirectory() as root:
            archive = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            item = scene()
            folder = archive.scene_folder(item)
            os.makedirs(folder)
            red_path = PublicCatalog.cached_band_path(item, folder, "red", item["assets"]["red"]["href"])
            with open(red_path + ".part.tif", "wb") as stream:
                stream.write(b"incomplete")
            self.assertEqual(archive.status(item), "Não baixado")
            with open(red_path, "wb") as stream:
                stream.write(b"complete")
            self.assertEqual(archive.status(item), "Parcial (1/5)")

    def test_corrupt_catalog_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            archive = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            archive.remember(scene())
            with open(archive.index_path, "w") as stream:
                stream.write("{broken")
            with self.assertRaises(CatalogError): archive.remember(scene("NEW"))
            with open(archive.index_path) as stream: self.assertEqual(stream.read(), "{broken")

    def fake_gdal(self, warps, vrts, fail=False):
        def warp(path, source, options):
            warps.append(source)
            with open(path, "wb") as stream: stream.write(b"II*")
            if fail: raise RuntimeError("connection lost")
            return object()
        def vrt(path, sources, options):
            vrts.append(path)
            with open(path, "w") as stream: stream.write(json.dumps(sources))
            return object()
        return types.SimpleNamespace(UseExceptions=lambda: None, SetConfigOption=lambda *args: None,
            Open=lambda path: types.SimpleNamespace(RasterXSize=1, RasterYSize=1, RasterCount=1,
                GetRasterBand=lambda index: types.SimpleNamespace(GetBlockSize=lambda: (1, 1),
                    ReadRaster=lambda *args: b"xx")), WarpOptions=lambda **kwargs: kwargs, Warp=warp,
            BuildVRTOptions=lambda **kwargs: kwargs, BuildVRT=vrt)

    def test_repair_option_downloads_cached_band_again(self):
        with tempfile.TemporaryDirectory() as folder:
            warps = []
            client = PublicCatalog()
            client.signed_url = lambda href: href
            with patch.dict(sys.modules, {"osgeo": types.SimpleNamespace(gdal=self.fake_gdal(warps, []))}):
                arguments = (scene(), folder, (-50, -7, -49, -6), "EPSG:31982", lambda _: None, ["red"])
                client.cache_bands(*arguments)
                client.cache_bands(*arguments)
                self.assertEqual(len(warps), 1)
                result, errors = client.cache_bands(*arguments, force_download=True)
                self.assertFalse(errors)
                self.assertIn("red", result)
                self.assertEqual(len(warps), 2)

    def test_two_compositions_share_bands_and_reopen_offline_without_network(self):
        warps, vrts = [], []
        client = PublicCatalog()
        client.signed_url = lambda href: href + "?sig=abc"
        item = scene()
        with tempfile.TemporaryDirectory() as root, patch.dict(sys.modules,
            {"osgeo": types.SimpleNamespace(gdal=self.fake_gdal(warps, vrts))}):
            archive = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            args = (item, archive.scene_folder(item), archive.rect, archive.target_crs, lambda _: None)
            false = client.download_scene(*args, default_rgb_keys(item))[2]
            natural = client.download_scene(*args, natural_rgb_keys(item))[2]
            self.assertNotEqual(false, natural)
            self.assertEqual(len(warps), 5)  # shared red band reused
            offline = PublicCatalog()
            offline.signed_url = lambda href: self.fail("Offline must not request a token")
            offline.json_request = lambda *args: self.fail("Offline must not query the API")
            self.assertEqual(offline.download_scene(*args, default_rgb_keys(item), offline=True)[2], false)
            self.assertEqual(len(warps), 5)
            self.assertEqual(len(vrts), 2)  # reopening does not rebuild composites

    def test_missing_offline_band_never_falls_back_to_network(self):
        client = PublicCatalog()
        client.signed_url = lambda href: self.fail("Network called in offline mode")
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules,
            {"osgeo": types.SimpleNamespace(gdal=self.fake_gdal([], []))}):
            with self.assertRaises(CatalogError):
                client.download_scene(scene(), folder, (-50, -7, -49, -6), "EPSG:31982",
                    lambda _: None, ("red", "green", "blue"), offline=True)

    def test_failure_removes_partial_band_and_retry_downloads_it(self):
        warps = []
        client = PublicCatalog(); client.signed_url = lambda href: href
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules, {"osgeo": types.SimpleNamespace(gdal=self.fake_gdal(warps, [], True))}):
                result, errors = client.cache_bands(scene(), folder, (-50, -7, -49, -6),
                    "EPSG:31982", lambda _: None, ["red"])
                self.assertFalse(result); self.assertTrue(errors)
                self.assertEqual(os.listdir(folder), [])
            with patch.dict(sys.modules, {"osgeo": types.SimpleNamespace(gdal=self.fake_gdal(warps, []))}):
                result, errors = client.cache_bands(scene(), folder, (-50, -7, -49, -6),
                    "EPSG:31982", lambda _: None, ["red"])
                self.assertIn("red", result); self.assertFalse(errors)

    def test_update_adds_new_scenes_without_downloading_old_bands_again(self):
        warps = []
        client = PublicCatalog()
        remote_items = [scene()]
        client.search = lambda *args: (list(remote_items), None)
        client.signed_url = lambda href: href + "?sig=abc"
        with tempfile.TemporaryDirectory() as root, patch.dict(sys.modules,
            {"osgeo": types.SimpleNamespace(gdal=self.fake_gdal(warps, []))}):
            archive = LocalArchive(root, (-50, -7, -49, -6), "EPSG:31982")
            arguments = (client, ["landsat-c2-l2"], "1982-01-01", "2026-12-31", lambda _: None)
            self.assertEqual(archive.sync(*arguments)["completed"], 1)
            self.assertEqual(len(warps), 5)
            remote_items.append(scene("NEW", "2026-09-29T00:00:00Z"))
            result = archive.sync(*arguments)
            self.assertEqual(result["completed"], 2)
            self.assertEqual(len(warps), 10)
            self.assertEqual(archive.status(scene()), "Completo")
            self.assertEqual(len(archive.search(["landsat-c2-l2"], "1982-01-01", "2026-12-31")), 2)

    def test_parallel_band_downloads_have_separate_config_and_restore_it(self):
        warps, vrts = [], []
        fake = self.fake_gdal(warps, vrts)
        local = threading.local()
        barrier = threading.Barrier(3)
        thread_ids, restored = set(), []
        def get_config(name):
            return getattr(local, "options", {}).get(name)
        def set_config(name, value):
            if not hasattr(local, "options"):
                local.options = {}
            local.options[name] = value
            if value is None:
                restored.append((threading.get_ident(), name))
        original_warp = fake.Warp
        def warp(path, source, options):
            thread_ids.add(threading.get_ident())
            self.assertEqual(get_config("GDAL_HTTP_MULTIPLEX"), "YES")
            self.assertEqual(options["warpMemoryLimit"], 32)
            barrier.wait(timeout=5)
            return original_warp(path, source, options)
        fake.SetThreadLocalConfigOption = set_config
        fake.GetThreadLocalConfigOption = get_config
        fake.Warp = warp
        client = PublicCatalog(); client.signed_url = lambda href: href
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules,
            {"osgeo": types.SimpleNamespace(gdal=fake)}):
            result, errors = client.cache_bands(scene(), folder, (-50, -7, -49, -6),
                "EPSG:31982", lambda _: None, ["red", "nir08", "swir16"])
            self.assertFalse(errors)
            self.assertEqual(set(result), {"red", "nir08", "swir16"})
            self.assertEqual(len(thread_ids), 3)
            for thread_id in thread_ids:
                self.assertIn((thread_id, "GDAL_HTTP_MULTIPLEX"), restored)
                self.assertIn((thread_id, "GDAL_DISABLE_READDIR_ON_OPEN"), restored)
            self.assertIsNone(get_config("GDAL_HTTP_MULTIPLEX"))

    def test_parallel_signing_requests_share_one_access_token(self):
        client = PublicCatalog()
        signature = "sig=" + uuid.uuid4().hex
        calls = []
        barrier = threading.Barrier(3)
        def request(url, payload=None):
            calls.append(url)
            return {"token": signature}
        client.json_request = request
        def sign(index):
            barrier.wait(timeout=5)
            return client.signed_url("https://landsateuwest.blob.core.windows.net/landsat-c2/"
                                     + str(index) + ".tif")
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(sign, range(3)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(value.endswith("?" + signature) for value in results))

    def test_expired_access_token_is_refreshed_for_long_updates(self):
        client = PublicCatalog()
        signature = "?sig=" + uuid.uuid4().hex
        client._tokens[("landsateuwest", "landsat-c2")] = "sig=old&se=2000-01-01T00%3A00%3A00Z"
        calls = []
        def request(url, payload=None):
            calls.append(url)
            return {"token": signature}
        client.json_request = request
        result = client.signed_url("https://landsateuwest.blob.core.windows.net/landsat-c2/red.tif")
        self.assertTrue(result.endswith(signature))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__": unittest.main()
