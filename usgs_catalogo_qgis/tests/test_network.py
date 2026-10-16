# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import json
import types
import unittest
from unittest.mock import patch

from usgs_catalogo_qgis.stac import CatalogError, PublicCatalog, STAC_URL


class Request:
    class Attribute:
        RedirectPolicyAttribute = 1
        HttpStatusCodeAttribute = 3

    class RedirectPolicy:
        ManualRedirectPolicy = 2

    def __init__(self, url):
        self.url, self.headers, self.attributes = url, {}, {}

    def setRawHeader(self, key, value):
        self.headers[key] = value

    def setAttribute(self, key, value):
        self.attributes[key] = value


class Reply:
    def __init__(self, body=b'{"type":"FeatureCollection"}', status=200, error=0):
        self.body, self.status, self.code = body, status, error

    def error(self):
        return self.code

    def attribute(self, key):
        return self.status

    def content(self):
        return self.body


class NetworkTests(unittest.TestCase):
    def network(self, reply):
        self.calls = []

        def get(request, **kwargs):
            self.calls.append((request, None, kwargs))
            return reply

        def post(request, body, **kwargs):
            self.calls.append((request, body, kwargs))
            return reply

        return patch.dict("sys.modules", {
            "qgis.core": types.SimpleNamespace(QgsNetworkAccessManager=
                types.SimpleNamespace(blockingGet=get, blockingPost=post)),
            "qgis.PyQt.QtCore": types.SimpleNamespace(QUrl=lambda value: value, QByteArray=bytes),
            "qgis.PyQt.QtNetwork": types.SimpleNamespace(QNetworkRequest=Request,
                QNetworkReply=types.SimpleNamespace(NetworkError=types.SimpleNamespace(NoError=0))),
        })

    def test_rejects_untrusted_urls_before_network_access(self):
        client = PublicCatalog()
        for url in ("file:///tmp/image", "http://planetarycomputer.microsoft.com/api/stac/v1/search",
                    "https://example.org/api/stac/v1/search",
                    "https://user@planetarycomputer.microsoft.com/api/stac/v1/search",
                    "https://planetarycomputer.microsoft.com:bad/api/stac/v1/search",
                    "https://planetarycomputer.microsoft.com/other"):
            with self.subTest(url=url), self.assertRaises(CatalogError):
                client.json_request(url)

    def test_get_and_post_use_qgis_network_without_redirects(self):
        client = PublicCatalog()
        with self.network(Reply()):
            self.assertEqual(client.json_request(STAC_URL)["type"], "FeatureCollection")
            client.json_request(STAC_URL, {"collections": ["landsat-c2-l2"]})
        get, post = self.calls
        self.assertIsNone(get[1])
        self.assertEqual(json.loads(post[1]), {"collections": ["landsat-c2-l2"]})
        self.assertEqual(post[0].headers[b"Content-Type"], b"application/json")
        for request, body, options in self.calls:
            self.assertEqual(request.url, STAC_URL)
            self.assertTrue(options["forceRefresh"])
            self.assertEqual(request.attributes[Request.Attribute.RedirectPolicyAttribute], Request.RedirectPolicy.ManualRedirectPolicy)

    def test_network_errors_redirects_and_invalid_json_are_reported(self):
        for reply in (Reply(error=1), Reply(status=302), Reply(status=403), Reply(body=b"invalid")):
            with self.subTest(reply=reply), self.network(reply), self.assertRaises(CatalogError):
                PublicCatalog().json_request(STAC_URL)

    def test_cancelled_request_never_starts_network(self):
        with self.network(Reply()), self.assertRaises(CatalogError):
            PublicCatalog(cancelled=lambda: True).json_request(STAC_URL)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
