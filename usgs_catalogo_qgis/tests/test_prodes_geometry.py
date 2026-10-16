# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import unittest

from usgs_catalogo_qgis.prodes import ProdesError
from usgs_catalogo_qgis.prodes_geometry import polygon_copy

try:
    from qgis.core import QgsGeometry
except ImportError:
    QgsGeometry = None


@unittest.skipIf(QgsGeometry is None, "PyQGIS real requerido para testes de geometria")
class ProdesGeometryTests(unittest.TestCase):
    def test_valid_polygon_is_unchanged_in_area_and_input(self):
        original = QgsGeometry.fromWkt("POLYGON((0 0,4 0,4 4,0 4,0 0))")
        original_wkt = original.asWkt()
        value, repaired = polygon_copy(original)
        self.assertFalse(repaired)
        self.assertEqual(value.area(), 16)
        self.assertEqual(original.asWkt(), original_wkt)
        self.assertTrue(value.isMultipart())

    def test_collection_preserves_both_polygons_without_line_area(self):
        original = QgsGeometry.fromWkt("GEOMETRYCOLLECTION(POLYGON((0 0,1 0,1 1,0 1,0 0)),POLYGON((2 0,3 0,3 1,2 1,2 0)),LINESTRING(0 0,100 100),POINT(1000 1000))")
        value, repaired = polygon_copy(original)
        self.assertTrue(repaired)
        self.assertEqual(value.area(), 2)
        self.assertEqual(len(value.asMultiPolygon()), 2)
        self.assertTrue(value.isGeosValid())

    def test_makevalid_polygon_with_collapsed_spur(self):
        original = QgsGeometry.fromWkt("POLYGON((0 0,2 0,2 2,1 2,1 3,1 2,0 2,0 0))")
        self.assertFalse(original.isGeosValid())
        value, repaired = polygon_copy(original)
        self.assertTrue(repaired)
        self.assertTrue(value.isGeosValid())
        self.assertEqual(value.area(), 4)

    def test_nested_multipart_surface_is_not_dropped(self):
        original = QgsGeometry.fromWkt("GEOMETRYCOLLECTION(GEOMETRYCOLLECTION(MULTIPOLYGON(((0 0,2 0,2 2,0 2,0 0)),((3 0,4 0,4 1,3 1,3 0))),POINT(0 0)),MULTILINESTRING((0 0,20 20)))")
        value, repaired = polygon_copy(original)
        self.assertTrue(repaired)
        self.assertEqual(value.area(), 5)
        self.assertEqual(len(value.asMultiPolygon()), 2)

    def test_contact_collection_does_not_expand_overlay(self):
        source = QgsGeometry.fromWkt("MULTIPOLYGON(((0 0,2 0,2 2,0 2,0 0)),((3 0,4 0,4 1,3 1,3 0)))")
        parcel = QgsGeometry.fromWkt("POLYGON((1 0,3 0,3 2,1 2,1 0))")
        intersection = source.intersection(parcel)
        value, repaired = polygon_copy(intersection)
        self.assertTrue(repaired)
        self.assertEqual(value.area(), 2)

    def test_nonpolygon_and_empty_are_refused_with_identity(self):
        for text in ("GEOMETRYCOLLECTION(LINESTRING(0 0,1 1),POINT(0 0))", "POLYGON EMPTY", "LINESTRING(0 0,1 1)"):
            with self.assertRaisesRegex(ProdesError, "UUID-regressao"):
                polygon_copy(QgsGeometry.fromWkt(text), "UUID-regressao")


if __name__ == "__main__":
    unittest.main()
