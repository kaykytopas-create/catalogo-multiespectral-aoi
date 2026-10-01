# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import os
import tempfile
import unittest
import uuid
import sys
import types
from unittest.mock import patch

from usgs_catalogo_qgis.stac import (
    PublicCatalog, raster_assets, safe_name, search_payload, visible_scenes,
    preview_url, context_bbox, default_rgb_keys, natural_rgb_keys,
    ndvi_keys, reflectance_coefficients, write_ndvi, prodes_label)


class PublicCatalogTests(unittest.TestCase):
    def test_bbox_and_cloud_filter(self):
        payload = search_payload(["landsat-c2-l2"],
                                 (-49.81, -6.54, -49.79, -6.52),
                                 "2020-01-01", "2020-12-31")
        self.assertEqual(payload["bbox"], [-49.81, -6.54, -49.79, -6.52])
        self.assertEqual(payload["query"], {"eo:cloud_cover": {"lt": 20}})
        scenes = [{"properties": {"eo:cloud_cover": cloud}} for cloud in (0, 19.9, 20, None, 80)]
        self.assertEqual(len(visible_scenes(scenes)), 2)
        extended = context_bbox((-49.81, -6.54, -49.79, -6.52))
        self.assertAlmostEqual(extended[2] - extended[0], .08)
        self.assertAlmostEqual(extended[3] - extended[1], .048)

    def test_tall_parcel_gets_landscape_crop_without_clipping(self):
        import math
        rect = (-50.002, -6.54, -49.998, -6.52)
        crop = context_bbox(rect)
        width_m = (crop[2] - crop[0]) * math.cos(math.radians((rect[1] + rect[3]) / 2))
        height_m = crop[3] - crop[1]
        self.assertAlmostEqual(width_m / height_m, 1.6)
        self.assertLess(crop[0], rect[0]); self.assertLess(crop[1], rect[1])
        self.assertGreater(crop[2], rect[2]); self.assertGreater(crop[3], rect[3])
        self.assertAlmostEqual((crop[0] + crop[2]) / 2, (rect[0] + rect[2]) / 2)
        self.assertAlmostEqual((crop[1] + crop[3]) / 2, (rect[1] + rect[3]) / 2)

    def test_band_assets_without_previews(self):
        item = {"assets": {
            "red": {"href": "https://example.com/B4.TIF", "roles": ["data"], "eo:bands": [{"common_name": "red"}]},
            "qa": {"href": "https://example.com/QA.tif"},
            "preview": {"href": "https://example.com/preview.jpg", "roles": ["thumbnail"]},
            "metadata": {"href": "https://example.com/MTL.xml"}}}
        self.assertEqual([key for key, _ in raster_assets(item)], ["red"])
        self.assertEqual([key for key, _ in raster_assets(item, True)], ["red", "qa"])
        self.assertEqual(safe_name("LC08/scene", "red", "https://host/B4.TIF"),
                         "LC08_scene_red.tif")
        sentinel = {"collection": "sentinel-2-l2a", "assets": {key: {"href": "https://host/{}.TIF".format(key),
                                "eo:bands": [{"name": key}]}
                    for key in ("B02", "B03", "B04", "B08", "B11")}}
        self.assertEqual(default_rgb_keys(sentinel), ("B11", "B08", "B04"))
        self.assertEqual(natural_rgb_keys(sentinel), ("B04", "B03", "B02"))
        self.assertEqual(ndvi_keys(sentinel), ("B08", "B04"))

    def test_prodes_preset_matches_sensor_bands(self):
        landsat = {"assets": {key: {"href": "https://host/" + key + ".tif",
                   "eo:bands": [{"name": key}]}
                   for key in ("red", "nir08", "swir16")}}
        for identifier, combination in (("LT04_TEST", "5–4–3"), ("LT05_TEST", "5–4–3"),
                                        ("LE07_TEST", "5–4–3"), ("LC08_TEST", "6–5–4"),
                                        ("LC09_TEST", "6–5–4")):
            landsat["id"] = identifier
            self.assertEqual(default_rgb_keys(landsat), ("swir16", "nir08", "red"))
            self.assertEqual(prodes_label(landsat), "PRODES — INPE (" + combination + ")")
        sentinel = {"assets": {key: {"href": "https://host/" + key + ".tif",
                    "eo:bands": [{"name": key}]} for key in ("B11", "B08", "B04")}}
        self.assertEqual(default_rgb_keys(sentinel), ("B11", "B08", "B04"))
        self.assertEqual(prodes_label(sentinel), "PRODES — INPE (11–8–4)")
        self.assertEqual(prodes_label({}), "PRODES — INPE (indisponível)")

    def test_ndvi_scales_landsat_and_masks_fill(self):
        import numpy as np
        item = {"collection": "landsat-c2-l2", "assets": {
            key: {"href": "https://host/{}.tif".format(key),
                  "eo:bands": [{"name": key}]}
            for key in ("red", "nir08")}}
        self.assertEqual(ndvi_keys(item), ("nir08", "red"))
        self.assertEqual(reflectance_coefficients(item, "red"), (0.0000275, -0.2))
        source = {"red": np.array([[10000, 0]], dtype="uint16"),
                  "nir08": np.array([[15000, 10000]], dtype="uint16")}
        written = []
        class Band:
            def __init__(self, key): self.key = key
            def ReadAsArray(self, x, y, width, count): return source[self.key][y:y+count, x:x+width]
            def GetNoDataValue(self): return 0
            def SetNoDataValue(self, value): self.nodata = value
            def WriteArray(self, values, x, y): written.append(values.copy())
        class Dataset:
            RasterXSize, RasterYSize = 2, 1
            def __init__(self, key): self.key = key
            def GetGeoTransform(self): return (0, 30, 0, 0, 0, -30)
            def GetProjection(self): return 'EPSG:31982'
            def GetRasterBand(self, index): return Band(self.key)
            def SetGeoTransform(self, value): pass
            def SetProjection(self, value): pass
            def FlushCache(self): pass
        fake_gdal = types.SimpleNamespace(Open=lambda path: Dataset(path),
            GDT_Float32=6, GetDriverByName=lambda name:
                types.SimpleNamespace(Create=lambda *args, **kwargs: Dataset('out')))
        write_ndvi(item, {"red": "red", "nir08": "nir08"}, "ndvi.tif", fake_gdal)
        self.assertAlmostEqual(float(written[0][0, 0]),
            ((15000 * .0000275 - .2) - (10000 * .0000275 - .2)) /
            ((15000 * .0000275 - .2) + (10000 * .0000275 - .2)), places=5)
        self.assertEqual(written[0][0, 1], -9999)

    def test_pagination_merges_search_filter(self):
        catalog = PublicCatalog()
        cursor = uuid.uuid4().hex
        calls = []
        def fake_request(url, payload=None):
            calls.append((url, payload))
            return {"type": "FeatureCollection", "features": [], "links": []}
        catalog.json_request = fake_request
        link = {"href": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
                "rel": "next", "method": "POST", "merge": True, "body": {"token": cursor}}
        catalog.search(["landsat-c2-l2"], (-50, -7, -49, -6),
                       "2022-01-01", "2022-12-31", next_link=link)
        self.assertEqual(calls[0][1]["query"]["eo:cloud_cover"]["lt"], 20)
        self.assertEqual(calls[0][1]["token"], cursor)

    def test_preview_link(self):
        item = {"assets": {"rendered_preview": {"href":
            "https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png?collection=landsat"}}}
        self.assertIn("max_size=180", preview_url(item))

    def test_anonymous_token_reused(self):
        catalog = PublicCatalog()
        signature = "sig=" + uuid.uuid4().hex
        calls = []
        def fake_json(url, payload=None):
            calls.append(url)
            return {"token": signature}
        catalog.json_request = fake_json
        a = "https://landsateuwest.blob.core.windows.net/landsat-c2/band1.tif"
        b = "https://landsateuwest.blob.core.windows.net/landsat-c2/band2.tif"
        self.assertTrue(catalog.signed_url(a).endswith("?" + signature))
        self.assertTrue(catalog.signed_url(b).endswith("?" + signature))
        self.assertEqual(len(calls), 1)

    def test_cropped_bands_without_full_scene_download(self):
        catalog = PublicCatalog()
        catalog.signed_url = lambda href: "https://test.blob.core.windows.net/container/band.tif?sig=short"
        captured, composites = [], []
        def fake_warp(path, source, options):
            captured.append((path, source, options))
            with open(path, "wb") as output:
                output.write(b"II*\x00")
            return object()
        def fake_vrt(path, sources, options):
            composites.append((path, sources, options))
            with open(path, "w") as output:
                output.write("<VRTDataset/>")
            return object()
        gdal = types.SimpleNamespace(UseExceptions=lambda: None, SetConfigOption=lambda *a: None,
            WarpOptions=lambda **opts: opts, Warp=fake_warp,
            BuildVRTOptions=lambda **opts: opts, BuildVRT=fake_vrt)
        item = {"id": "LT05/scene", "assets": {
            key: {"href": "https://host/{}.TIF".format(key), "eo:bands": [{"name": key}]}
            for key in ("red", "nir08", "swir16", "blue")}}
        self.assertEqual(default_rgb_keys(item), ("swir16", "nir08", "red"))
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(sys.modules, {"osgeo": types.SimpleNamespace(gdal=gdal)}):
                files, errors, composite = catalog.download_scene(item, folder,
                    (-49.81, -6.54, -49.79, -6.52), "EPSG:31982",
                    lambda _: None, ("swir16", "nir08", "red"))
            self.assertEqual(len(files), 3)
            self.assertEqual(errors, [])
            self.assertTrue(os.path.isfile(files[0]))
            self.assertTrue(os.path.isfile(composite))
            self.assertEqual(composites[0][2]["resolution"], "highest")
            self.assertEqual(composites[0][2]["resampleAlg"], "nearest")
            self.assertEqual(composites[0][1],
                [next(path for path in files if "_" + key + "." in path)
                 for key in ("swir16", "nir08", "red")])
            self.assertAlmostEqual(captured[0][2]["outputBounds"][2] -
                                   captured[0][2]["outputBounds"][0], .08)
            self.assertEqual(captured[0][2]["dstSRS"], "EPSG:31982")


if __name__ == "__main__":
    unittest.main()
