# Contributing

Development requires Python 3. The interface requires QGIS 3.22–3.99, its GDAL Python bindings and NumPy. Do not install a separate PyQt distribution into QGIS.

Run core tests from the directory containing `usgs_catalogo_qgis`:

```sh
python3 -m unittest discover -s usgs_catalogo_qgis/tests -v
```

These tests simulate GDAL downloads. They do not verify QGIS rendering or live provider availability. Follow the runtime checks in PUBLICACAO.md before publishing.

For a report, include plugin version, QGIS and GDAL versions, operating system, scene ID, selected bands, CRS, offline state, reproducible steps and the full error message. Use the public issue tracker once configured. Remove owner identifiers and private project paths. Do not attach credentials, SAS tokens or client data.

Keep comments in English, use `qgis.PyQt`, preserve source band values and NDVI scaling, and keep all network operations out of the UI thread. New download providers should respect the QGIS proxy configuration; STAC and SAS requests use QgsNetworkAccessManager; GDAL raster reads still need manual proxy verification where required.

Contributions are distributed under GPL-2.0-or-later. Do not commit caches, downloaded imagery, ZIP releases, compiled Python files or private parcel data. The source repository must contain the unpacked source matching the submitted ZIP.
