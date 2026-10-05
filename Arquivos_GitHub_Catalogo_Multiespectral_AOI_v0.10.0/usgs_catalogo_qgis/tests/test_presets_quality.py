# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from usgs_catalogo_qgis.stac import (CatalogError, PublicCatalog, preset_keys,
    index_keys, slc_gap_scene, validate_raster, validate_cached_raster, write_index)


def scene(sentinel=False):
    keys = ("B02", "B03", "B04", "B08", "B11", "B12") if sentinel else (
        "blue", "green", "red", "nir08", "swir16", "swir22")
    return {"id": "LC08_TEST", "collection": "sentinel-2-l2a" if sentinel else "landsat-c2-l2",
            "assets": {key: {"href": "https://host/" + key + ".tif",
                             "eo:bands": [{"name": key}]} for key in keys}}


class QualityTests(unittest.TestCase):
    def test_presets_follow_spectral_roles_for_both_sensors(self):
        for sentinel in (False, True):
            item = scene(sentinel)
            self.assertEqual(preset_keys(item, "infrared"),
                             ("B08", "B04", "B03") if sentinel else ("nir08", "red", "green"))
            self.assertEqual(preset_keys(item, "swir"),
                             ("B12", "B08", "B04") if sentinel else ("swir22", "nir08", "red"))
            self.assertEqual(preset_keys(item, "vegetation"), preset_keys(item, "prodes"))
            self.assertEqual(index_keys(item, "nbr"),
                             ("B08", "B12") if sentinel else ("nir08", "swir22"))
        del item["assets"]["B12"]
        self.assertFalse(preset_keys(item, "swir"))
        self.assertFalse(index_keys(item, "nbr"))

    def test_slc_warning_only_applies_to_affected_landsat7_dates(self):
        for identifier, date, expected in (("LE07_TEST", "2003-05-30", False),
                ("LE07_TEST", "2003-06-01", True), ("LC08_TEST", "2020-01-01", False)):
            self.assertEqual(slc_gap_scene({"id": identifier, "properties": {"datetime": date}}), expected)

    def test_every_block_is_read_and_unreadable_blocks_are_rejected(self):
        calls = []
        def read(*args):
            calls.append(args)
            return b"xx" if args[0] == 0 else None
        dataset = types.SimpleNamespace(RasterXSize=3, RasterYSize=2, RasterCount=1,
            GetRasterBand=lambda index: types.SimpleNamespace(GetBlockSize=lambda: (2, 2), ReadRaster=read))
        gdal = types.SimpleNamespace(Open=lambda path: dataset)
        with self.assertRaises(CatalogError):
            validate_raster("broken.tif", gdal)
        self.assertEqual(calls, [(0, 0, 2, 2), (2, 0, 1, 2)])
        with self.assertRaises(CatalogError):
            validate_raster("cancelled.tif", gdal, lambda: True)

    def test_validation_receipt_is_invalidated_when_file_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "band.tif")
            with open(path, "wb") as stream:
                stream.write(b"raster")
            with patch("usgs_catalogo_qgis.stac.validate_raster") as check:
                validate_cached_raster(path, None)
                validate_cached_raster(path, None)
                self.assertEqual(check.call_count, 1)
                with open(path, "ab") as stream:
                    stream.write(b"changed")
                validate_cached_raster(path, None)
                self.assertEqual(check.call_count, 2)

    def test_nbr_uses_swir2_scaled_reflectance_and_preserves_nodata(self):
        import numpy as np
        written = []
        class Dataset:
            RasterXSize, RasterYSize = 2, 1
            def __init__(self, key): self.key = key
            def GetGeoTransform(self): return (0, 30, 0, 30, 0, -30)
            def GetProjection(self): return "EPSG:31982"
            def GetRasterBand(self, index): return self
            def GetNoDataValue(self): return 0
            def ReadAsArray(self, *args):
                return np.array([[15000 if self.key == "nir08" else 10000, 0]], dtype="uint16")
            def WriteArray(self, values, *args): written.append(values)
            def SetNoDataValue(self, value): self.nodata = value
            def SetGeoTransform(self, value): self.gt = value
            def SetProjection(self, value): self.projection = value
            def FlushCache(self): self.flushed = True
        gdal = types.SimpleNamespace(Open=Dataset, GDT_Float32=6,
            GetDriverByName=lambda name: types.SimpleNamespace(Create=lambda *args, **kwargs: Dataset("out")))
        write_index(scene(), {"nir08": "nir08", "swir22": "swir22"}, "out.tif", gdal, "nbr")
        self.assertAlmostEqual(float(written[0][0, 0]),
            ((15000*.0000275-.2)-(10000*.0000275-.2))/((15000*.0000275-.2)+(10000*.0000275-.2)), places=5)
        self.assertEqual(written[0][0, 1], -9999)


if __name__ == "__main__":
    unittest.main()
