# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import json
import unittest

from usgs_catalogo_qgis.prodes import (TerraBrasilis, ProdesError, capabilities,
    record, evaluate, report_html, annual_layers)


def collection(count, start=0, total=None):
    value = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": str(index), "properties": {"uuid": "fixture-" + str(index)},
         "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}
        for index in range(start, start + count)]}
    if total is not None:
        value["numberMatched"] = total
    return json.dumps(value).encode()


class ProdesTests(unittest.TestCase):
    def test_annual_catalog_excludes_reference_and_accumulated_products(self):
        good = ("prodes-amazon-nb:yearly_deforestation_biome", "Annual")
        layers = [good, ("prodes-amazon-nb:accumulated_deforestation_2007_biome", "Accumulated"),
                  ("deter-amz:prodes_reference", "Reference"),
                  ("prodes-legal-amz:yearly_deforestation", "Legal Amazon"),
                  ("prodes-amazon-nb:yearly_deforestation_smaller", "Small")]
        self.assertEqual(annual_layers(layers), [good])

    def test_class_normalisation_preserves_year(self):
        self.assertEqual(record({"CLASS_NAME": " D2010 "})["year"], 2010)

    def test_capabilities_namespace_and_entity_rejection(self):
        try:
            from qgis.PyQt.QtCore import QXmlStreamReader
        except ImportError:
            try:
                from PyQt5.QtCore import QXmlStreamReader
            except ImportError:
                self.skipTest("Qt XML requerido para teste de GetCapabilities")
        xml = b'<w:WFS_Capabilities xmlns:w="urn:wfs"><w:FeatureType><w:Name>prodes-amz:yearly</w:Name><w:Title>PRODES annual</w:Title></w:FeatureType><w:FeatureType><w:Name>deter:alerts</w:Name></w:FeatureType></w:WFS_Capabilities>'
        self.assertEqual(capabilities(xml, QXmlStreamReader), [("prodes-amz:yearly", "PRODES annual")])
        with self.assertRaises(ProdesError):
            capabilities(b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///fixture">]><x/>')

    def test_known_total_pages_and_crs84(self):
        calls = []
        def request(params):
            calls.append(params)
            return collection(500 if params["startIndex"] == 0 else 1, params["startIndex"], 501)
        result = TerraBrasilis(request=request).features("prodes:yearly", (-50, -5, -49, -4))
        self.assertEqual(len(result["features"]), 501)
        self.assertEqual([call["startIndex"] for call in calls], [0, 500])
        self.assertTrue(calls[0]["bbox"].endswith("urn:ogc:def:crs:OGC:1.3:CRS84"))

    def test_unknown_total_uses_empty_page_not_requested_size(self):
        calls = []
        def request(params):
            start = params["startIndex"]
            calls.append(start)
            return collection(2 if start == 0 else 1 if start == 2 else 0, start)
        self.assertEqual(len(TerraBrasilis(request=request).features("prodes:yearly", (0, 0, 1, 1))["features"]), 3)
        self.assertEqual(calls, [0, 2, 3])

    def test_incomplete_and_repeated_pages_are_refused(self):
        def incomplete(params):
            return collection(1, 0, 2) if params["startIndex"] == 0 else collection(0, 0, 2)
        with self.assertRaisesRegex(ProdesError, "incompleta"):
            TerraBrasilis(request=incomplete).features("prodes:yearly", (0, 0, 1, 1))
        with self.assertRaisesRegex(ProdesError, "repetiu"):
            TerraBrasilis(request=lambda params: collection(1)).features("prodes:yearly", (0, 0, 1, 1))

    def test_invalid_service_and_cancelled(self):
        with self.assertRaises(ProdesError):
            TerraBrasilis(request=lambda params: b'<error/>').features("prodes:yearly", (0, 0, 1, 1))
        with self.assertRaises(ProdesError):
            TerraBrasilis(cancelled=lambda: True).features("prodes:yearly", (0, 0, 1, 1))
        with self.assertRaises(ProdesError):
            TerraBrasilis(request=lambda params: collection(0)).features("prodes:bad&filter", (0, 0, 1, 1))

    def test_residue_not_increment_and_date_alias(self):
        self.assertIsNone(record({"class_name": "r2022"})["year"])
        self.assertEqual(record({"class_name": "d2022", "image_data": "2022-07-01"})["image_date"], "2022-07-01")

    def evaluate(self, observations, reviewed=True, dates=None, **kwargs):
        item = {"year": 2022, "uuid": "fixture", "core_ha": 1.0}
        item.update(kwargs.pop("item", {}))
        return evaluate(item, observations, dates or ["2022-07-01", "2021-07-01", "2020-07-01"], reviewed, kwargs.pop("annual_layer", True), **kwargs)

    def test_compatible_requires_review_and_complete_history(self):
        obs = ["suppressed", "native", "native"]
        self.assertEqual(self.evaluate(obs)["status"], "Compatível com o registro")
        self.assertEqual(self.evaluate(obs, False)["status"], "Inconclusivo")
        self.assertEqual(self.evaluate(["unknown", "native", "native"])["status"], "Inconclusivo")
        self.assertEqual(self.evaluate(obs, dates=["2023-07-01", "2022-07-01", "2021-07-01"])["status"], "Inconclusivo")

    def test_divergence_and_regrowth_is_not_proof(self):
        self.assertEqual(self.evaluate(["suppressed", "suppressed", "native"])["status"], "Indícios de inconsistência temporal")
        # A recent vegetation observation, without historical interpretations,
        # must never become a declaration that a historical polygon is false.
        self.assertEqual(self.evaluate(["native", "unknown", "unknown"])["status"], "Inconclusivo")
        self.assertEqual(self.evaluate(["native"] * 3)["status"], "Indícios de inconsistência temática")

    def test_border_separate_from_false_and_missing_uuid(self):
        result = self.evaluate(["unknown"] * 3, tolerance=True, item={"core_ha": 0})
        self.assertEqual(result["status"], "Sobreposição restrita à borda")
        self.assertIn("não demonstra erro", result["reason"])
        self.assertEqual(self.evaluate(["native"] * 3, item={"uuid": ""})["status"], "Inconclusivo")
        self.assertEqual(self.evaluate(["native"] * 3, annual_layer=False)["status"], "Inconclusivo")

    def test_report_escapes_user_and_source_input(self):
        output = report_html({"Imóvel": '<script>alert("x")</script>'}, [{"uuid": "<iframe>", "notes": "<img>", "reason": "<script>"}], [("<title>", "mapa.png")])
        self.assertNotIn("<script>", output)
        self.assertIn("&lt;script&gt;", output)
        self.assertIn("não há classificador", output)
        self.assertIn("mapa.png", output)


if __name__ == "__main__":
    unittest.main()
