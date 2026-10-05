# Changelog

## 0.10.0 — 2026-10-05

- Added a spectral preset dropdown with vegetation infrared, vegetation analysis, SWIR, agriculture, land/water, natural color and the PRODES default.
- Added scaled NBR calculation and retained NDVI/manual RGB selection.
- Read all raster blocks before accepting downloads or unvalidated cache files; validation receipts avoid repeat scans of unchanged bands.
- Added HTTP retries, exact warp transformation, explicit output NoData and lossless compressed TIFF crops.
- Added a manual cache repair option; rebuilt RGB composites and indices when source bands change.
- Increased display contrast sampling to 262144 pixels and kept source resolution and optional display smoothing.
- Marked affected Landsat 7 SLC-off scenes and added an optional filter without synthesizing missing observations.
- 36 tests passed; Qt5/Qt6 controls checked with mocked PyQGIS. Full QGIS/GDAL runtime validation remains pending.

## 0.9.3 — 2026-10-01

- Fixed all 22 Qt6 compatibility findings in the submitted 0.9.2 package.
- Used scoped Qt and PyQGIS enums and QDialog.exec().
- Imported QAction from QtGui with a Qt5 fallback to QtWidgets.
- Checked Qt references with PyQt5 5.15.11 and PyQt6 6.11.0; 30 core tests passed.
- Compatibility remains declared for QGIS 3.22–3.99. QGIS runtime and full QGIS 4 validation are still pending.

## 0.9.2 — 2026-10-01

- Replaced urllib requests with native QGIS networking for STAC and temporary SAS signing.
- Restricted catalog requests to authorized HTTPS endpoints and refused redirects.
- Removed unused full-scene download code and reported cache errors instead of ignoring them.
- Replaced hardcoded credential-like test fixtures with ephemeral synthetic values.
- Added network validation and error-handling tests; 30 tests passed locally.
- Bandit 1.9.4 and detect-secrets 1.5.0 reported no findings.

## 0.9.1 — 2026-09-30

- Fixed literal percent sign in metadata that caused public QGIS upload parsing to fail.
- Added validation with ConfigParser BasicInterpolation and regression tests.
- Imagery retrieval and rendering are unchanged.

## 0.9.0 — 2026-09-30

- Prepared experimental publication metadata with an English description.
- Added GPL-2.0-or-later license, author notice and PNG icon.
- Added publication guide, release builder, contribution guide and synthetic test parcel.
- Configured author email and public GitHub project links supplied by the author. Source upload and runtime validation remain pending.
- No change to imagery retrieval, RGB processing, NDVI or archive format.

## 0.8.0

- Wider landscape crop and preview window.
- Optional RGB display smoothing and highest-resolution composite grid.
- Offline fallback to older local archives.

## 0.7.0

- INPE/PRODES spectral preset labels by sensor.
- Up to three independent band download workers.
- Cached contrast limits and VRT reuse.

## 0.6.0

- Georeferenced preview with parcel boundary.
- Incremental local imagery archive and offline mode.
