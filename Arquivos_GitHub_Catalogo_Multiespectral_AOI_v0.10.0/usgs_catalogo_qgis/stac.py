# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Anonymous STAC search and raster download via Microsoft Planetary Computer.

The Landsat collection contains USGS Collection 2 Level-2 imagery. Microsoft's
read-only SAS signing service is public and requires no account from the user.
"""
import json
import logging
import hashlib
import math
import threading
from concurrent.futures import ThreadPoolExecutor
import os
import urllib.parse
from pathlib import Path
from datetime import datetime, timedelta, timezone

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
SAS_ENDPOINT = "https://planetarycomputer.microsoft.com/api/sas/v1/token/"
COLLECTIONS = {
    "landsat-c2-l2": "Landsat 4–9 | USGS Collection 2, nível 2",
    "sentinel-2-l2a": "Sentinel-2 | nível 2A",
}
MAX_CLOUD = 20
RASTER_SUFFIXES = {".tif", ".tiff", ".jp2"}
CROP_PROFILE = {"width": 4.0, "height": 2.4, "min_aspect": 1.6}
RGB_DEFAULTS = ("swir16", "nir08", "red")
NDVI_BANDS = {"landsat-c2-l2": ("nir08", "red"),
              "sentinel-2-l2a": ("B08", "B04")}


class CatalogError(Exception):
    pass


def bbox(rect):
    west, south, east, north = rect
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise CatalogError("O limite do imóvel está fora das coordenadas válidas.")
    return [west, south, east, north]


def context_bbox(rect):
    """Keep the full parcel and surroundings in a landscape crop (at least 1.6:1).

    Longitude distance varies with latitude; compensate using the parcel center.
    """
    west, south, east, north = bbox(rect)
    center_x, center_y = (west + east) / 2, (south + north) / 2
    height = (north - south) * CROP_PROFILE["height"]
    longitude_scale = max(math.cos(math.radians(center_y)), 0.01)
    width = max((east - west) * CROP_PROFILE["width"],
                height * CROP_PROFILE["min_aspect"] / longitude_scale)
    return bbox((center_x - width / 2, center_y - height / 2,
                 center_x + width / 2, center_y + height / 2))


def available_bands(item):
    return [(key, asset) for key, asset in item.get("assets", {}).items()
            if asset.get("eo:bands") and key != "visual" and
            Path(urllib.parse.urlparse(asset.get("href", "")).path).suffix.lower() in RASTER_SUFFIXES]


def band_label(key, asset):
    info = asset.get("eo:bands") or [{}]
    identifier = info[0].get("name", "")
    return "{}  {}".format(key.upper(), "({})".format(identifier) if identifier else "")


def default_rgb_keys(item):
    available_list = [key for key, _ in available_bands(item)]
    available = set(available_list)
    for preferred in (RGB_DEFAULTS, ("B11", "B08", "B04")):
        if all(key in available for key in preferred):
            return preferred
    natural = natural_rgb_keys(item)
    if natural:
        return natural
    keys = available_list
    return tuple((keys + keys + keys)[:3]) if keys else ()


def prodes_label(item):
    """Main spectral composite documented by INPE for PRODES Amazônia."""
    keys = default_rgb_keys(item)
    if keys == ("B11", "B08", "B04"):
        return "PRODES — INPE (11–8–4)"
    if keys == RGB_DEFAULTS:
        platform = str(item.get("properties", {}).get("platform", "")).lower()
        band_name = str((item.get("assets", {}).get("swir16", {}).get("eo:bands") or [{}])[0].get("name", "")).upper()
        oli = platform in ("landsat-8", "landsat-9") or str(item.get("id", "")).startswith(("LC08", "LC09")) or band_name.endswith("B6")
        return "PRODES — INPE ({})".format("6–5–4" if oli else "5–4–3")
    return "PRODES — INPE (indisponível)"


def natural_rgb_keys(item):
    available = {key for key, _ in available_bands(item)}
    for preferred in (("red", "green", "blue"), ("B04", "B03", "B02")):
        if all(key in available for key in preferred):
            return preferred
    return ()


def ndvi_keys(item):
    keys = NDVI_BANDS.get(item.get("collection"), ())
    available = {key for key, _ in available_bands(item)}
    return keys if all(key in available for key in keys) else ()



PRESETS = (
    ("prodes", "PRODES — INPE", ("swir16", "nir08", "red")),
    ("natural", "Cor natural", ("red", "green", "blue")),
    ("infrared", "Infravermelho — vegetação", ("nir08", "red", "green")),
    ("vegetation", "Análise de vegetação", ("swir16", "nir08", "red")),
    ("swir", "Infravermelho de ondas curtas", ("swir22", "nir08", "red")),
    ("agriculture", "Agricultura", ("swir22", "swir16", "blue")),
    ("water", "Terra / água", ("nir08", "swir16", "red")),
)


def preset_keys(item, preset):
    semantic = next((keys for identifier, label, keys in PRESETS if identifier == preset), ())
    sentinel = {"red": "B04", "green": "B03", "blue": "B02", "nir08": "B08",
                "swir16": "B11", "swir22": "B12"}
    keys = tuple(sentinel[key] for key in semantic) if item.get("collection") == "sentinel-2-l2a" else semantic
    available = {key for key, _ in available_bands(item)}
    return keys if keys and all(key in available for key in keys) else ()


def index_keys(item, product):
    if product == "ndvi":
        return ndvi_keys(item)
    if product != "nbr":
        return ()
    keys = ("B08", "B12") if item.get("collection") == "sentinel-2-l2a" else ("nir08", "swir22")
    available = {key for key, _ in available_bands(item)}
    return keys if all(key in available for key in keys) else ()


def slc_gap_scene(item):
    props = item.get("properties", {})
    landsat7 = props.get("platform") == "landsat-7" or str(item.get("id", "")).startswith("LE07")
    return landsat7 and str(props.get("datetime", ""))[:10] >= "2003-05-31"


def validate_raster(path, gdal, cancelled=lambda: False):
    """Read every raster block so truncated tiles cannot be accepted as cached data."""
    dataset = gdal.Open(path)
    if dataset is None or dataset.RasterXSize <= 0 or dataset.RasterYSize <= 0:
        raise CatalogError("Raster vazio ou ilegível; baixe novamente a banda.")
    for index in range(1, dataset.RasterCount + 1):
        band = dataset.GetRasterBand(index)
        width, height = band.GetBlockSize()
        for y in range(0, dataset.RasterYSize, max(1, height)):
            for x in range(0, dataset.RasterXSize, max(1, width)):
                if cancelled():
                    raise CatalogError("Operação cancelada.")
                data = band.ReadRaster(x, y, min(max(1, width), dataset.RasterXSize-x),
                                       min(max(1, height), dataset.RasterYSize-y))
                if not data:
                    raise CatalogError("Bloco raster incompleto; baixe novamente a banda.")
    dataset = None


def validate_cached_raster(path, gdal, cancelled=lambda: False):
    stat = os.stat(path)
    identity = [stat.st_size, stat.st_mtime_ns]
    receipt = path + ".validated.json"
    try:
        with open(receipt, encoding="utf-8") as stream:
            if json.load(stream) == identity:
                return
    except (OSError, ValueError):
        logging.getLogger(__name__).debug("Raster será validado integralmente antes de reutilização.")
    validate_raster(path, gdal, cancelled)
    partial = receipt + ".part"
    with open(partial, "w", encoding="utf-8") as stream:
        json.dump(identity, stream)
    os.replace(partial, receipt)

def reflectance_coefficients(item, key):
    """Apply the product's radiometric scaling before computing an index."""
    if item.get("collection") == "landsat-c2-l2":
        return 0.0000275, -0.2
    asset = item.get("assets", {}).get(key, {})
    metadata = (asset.get("raster:bands") or [{}])[0]
    return float(metadata.get("scale", 0.0001)), float(metadata.get("offset", 0))


def write_index(item, files_by_key, destination, gdal, product="ndvi", cancelled=lambda: False):
    """Calculate reflectance NDVI in row blocks, preserving NoData as -9999."""
    import numpy as np

    nir_key, red_key = index_keys(item, product)
    red = gdal.Open(files_by_key[red_key])
    nir = gdal.Open(files_by_key[nir_key])
    if red is None or nir is None:
        raise CatalogError("Não foi possível abrir as bandas para calcular o NDVI.")
    aligned = None
    if (red.RasterXSize != nir.RasterXSize or red.RasterYSize != nir.RasterYSize or
            red.GetGeoTransform() != nir.GetGeoTransform() or
            red.GetProjection() != nir.GetProjection()):
        gt = red.GetGeoTransform()
        bounds = (gt[0], gt[3] + red.RasterYSize * gt[5],
                  gt[0] + red.RasterXSize * gt[1], gt[3])
        aligned = gdal.Warp("", nir, format="MEM", outputBounds=bounds,
                            width=red.RasterXSize, height=red.RasterYSize,
                            dstSRS=red.GetProjection(), resampleAlg="near")
        if aligned is None:
            raise CatalogError("Não foi possível alinhar as bandas do NDVI.")
        nir = aligned
    output = gdal.GetDriverByName("GTiff").Create(destination, red.RasterXSize,
        red.RasterYSize, 1, gdal.GDT_Float32, options=["TILED=YES"])
    if output is None:
        raise CatalogError("Não foi possível criar o raster NDVI.")
    output.SetGeoTransform(red.GetGeoTransform())
    output.SetProjection(red.GetProjection())
    out_band = output.GetRasterBand(1)
    out_band.SetNoDataValue(-9999)
    red_band, nir_band = red.GetRasterBand(1), nir.GetRasterBand(1)
    red_scale, red_offset = reflectance_coefficients(item, red_key)
    nir_scale, nir_offset = reflectance_coefficients(item, nir_key)
    for y in range(0, red.RasterYSize, 256):
        if cancelled():
            raise CatalogError("Operação cancelada.")
        count = min(256, red.RasterYSize - y)
        raw_red = red_band.ReadAsArray(0, y, red.RasterXSize, count)
        raw_nir = nir_band.ReadAsArray(0, y, red.RasterXSize, count)
        valid = np.isfinite(raw_red) & np.isfinite(raw_nir)
        for raw, band in ((raw_red, red_band), (raw_nir, nir_band)):
            nodata = band.GetNoDataValue()
            if nodata is not None:
                valid &= raw != nodata
        if item.get("collection") == "landsat-c2-l2":
            valid &= (raw_red != 0) & (raw_nir != 0)
        red_value = raw_red.astype("float32") * red_scale + red_offset
        nir_value = raw_nir.astype("float32") * nir_scale + nir_offset
        denominator = nir_value + red_value
        valid &= denominator > 0
        values = np.full(raw_red.shape, -9999, dtype="float32")
        np.divide(nir_value - red_value, denominator, out=values, where=valid)
        values[(values < -1) | (values > 1)] = -9999
        out_band.WriteArray(values, 0, y)
    output.FlushCache()
    output = None
    aligned = None
    red = nir = None
    return destination



def write_ndvi(item, files_by_key, destination, gdal, cancelled=lambda: False):
    return write_index(item, files_by_key, destination, gdal, "ndvi", cancelled)

def search_payload(collections, rect, start, end, cloud=MAX_CLOUD):
    if not collections or not set(collections).issubset(COLLECTIONS):
        raise CatalogError("Selecione uma coleção disponível.")
    return {"collections": list(collections), "bbox": bbox(rect),
            "datetime": start + "T00:00:00Z/" + end + "T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": cloud}},
            "sortby": [{"field": "datetime", "direction": "desc"}],
            "limit": 100}


def visible_scenes(items, cloud=MAX_CLOUD):
    result = []
    for item in items:
        cover = item.get("properties", {}).get("eo:cloud_cover")
        try:
            if cover is not None and float(cover) < cloud:
                result.append(item)
        except (ValueError, TypeError):
            logging.getLogger(__name__).warning("Cena ignorada: metadado de nuvens inválido.")
    return result


def raster_assets(item, include_auxiliary=False):
    """Spectral bands by default; optionally add QA/auxiliary rasters."""
    assets = []
    for key, value in item.get("assets", {}).items():
        href = value.get("href", "")
        parsed = urllib.parse.urlparse(href)
        if parsed.scheme != "https" or Path(parsed.path).suffix.lower() not in RASTER_SUFFIXES:
            continue
        if "thumbnail" in value.get("roles", []) or "overview" in value.get("roles", []):
            continue
        if not include_auxiliary and not value.get("eo:bands"):
            continue
        if not include_auxiliary and key == "visual":
            continue
        assets.append((key, href))
    return assets


def safe_name(scene_id, key, href):
    """Use only sanitized catalog identifiers as local file names."""
    def clean(value):
        return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in value)[:140]
    suffix = Path(urllib.parse.urlparse(href).path).suffix.lower()
    return clean(scene_id) + "_" + clean(key) + suffix


def preview_url(item, size=180):
    asset = item.get("assets", {}).get("rendered_preview", {})
    url = asset.get("href", "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "planetarycomputer.microsoft.com":
        return None
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("max_size", str(size)))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


class PublicCatalog:
    def __init__(self, cancelled=lambda: False):
        self.cancelled = cancelled
        self._tokens = {}
        self._token_lock = threading.Lock()

    def json_request(self, url, payload=None):
        if self.cancelled():
            raise CatalogError("Operação cancelada.")
        headers = {"Accept": "application/geo+json, application/json",
                   "User-Agent": "QGIS-Public-Satellite-Catalog/0.9"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        parsed = urllib.parse.urlparse(url)
        try:
            allowed = (parsed.scheme == "https" and parsed.hostname == "planetarycomputer.microsoft.com"
                       and parsed.port in (None, 443) and not parsed.username and not parsed.password
                       and parsed.path.startswith(("/api/stac/v1/", "/api/sas/v1/")))
        except ValueError as exc:
            raise CatalogError("Endereço inválido do catálogo público.") from exc
        if not allowed:
            raise CatalogError("A consulta exige HTTPS no servidor autorizado do catálogo.")
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtCore import QUrl, QByteArray
        from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        for key, value in headers.items():
            request.setRawHeader(key.encode("ascii"), value.encode("ascii"))
        try:
            if payload is None:
                response = QgsNetworkAccessManager.blockingGet(request, forceRefresh=True)
            else:
                response = QgsNetworkAccessManager.blockingPost(
                    request, QByteArray(json.dumps(payload).encode("utf-8")), forceRefresh=True)
            if self.cancelled():
                raise CatalogError("Operação cancelada.")
            if response.error() != QNetworkReply.NetworkError.NoError:
                raise CatalogError("Falha de rede ao consultar o catálogo público (código {}).".format(int(response.error())))
            status = response.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if status is None or not 200 <= int(status) < 300:
                raise CatalogError("O catálogo respondeu com status HTTP {}.".format(status))
            return json.loads(bytes(response.content()).decode("utf-8"))
        except (OSError, ValueError) as exc:
            raise CatalogError("Resposta inválida do catálogo público.") from exc

    def search(self, collections, rect, start, end, next_link=None):
        if next_link:
            url = next_link.get("href", "")
            if not url.startswith("https://planetarycomputer.microsoft.com/api/stac/v1/"):
                raise CatalogError("Endereço de paginação inválido.")
            method = next_link.get("method", "GET").upper()
            if method not in ("POST", "GET"):
                raise CatalogError("Método de paginação inválido.")
            if method == "POST":
                payload = next_link.get("body") or {}
                if next_link.get("merge"):
                    payload = {**search_payload(collections, rect, start, end), **payload}
            else:
                payload = None
        else:
            url = STAC_URL
            payload = search_payload(collections, rect, start, end)
        response = self.json_request(url, payload)
        if response.get("type") != "FeatureCollection":
            raise CatalogError("O catálogo não retornou uma lista de cenas.")
        next_page = next((link for link in response.get("links", [])
                          if link.get("rel") == "next"), None)
        return visible_scenes(response.get("features", [])), next_page

    def signed_url(self, href):
        with self._token_lock:
            return self._signed_url(href)

    def _signed_url(self, href):
        parsed = urllib.parse.urlparse(href)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not host.endswith(".blob.core.windows.net"):
            raise CatalogError("O servidor não forneceu endereço raster válido.")
        container = parsed.path.strip("/").split("/", 1)[0]
        account = host.split(".", 1)[0]
        key = (account, container)
        cached = self._tokens.get(key)
        if cached:
            expires = dict(urllib.parse.parse_qsl(cached.lstrip("?"))).get("se")
            if expires:
                try:
                    expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                    if expiry <= datetime.now(timezone.utc) + timedelta(minutes=5):
                        self._tokens.pop(key, None)
                except (ValueError, TypeError):
                    self._tokens.pop(key, None)
        if key not in self._tokens:
            data = self.json_request(SAS_ENDPOINT + account + "/" + container)
            token = data.get("token", "")
            if not token or "sig=" not in token:
                raise CatalogError("Não foi possível autorizar o acesso público à banda.")
            self._tokens[key] = token.lstrip("?")
        separator = "&" if parsed.query else "?"
        return href + separator + self._tokens[key]

    @staticmethod
    def cached_band_path(item, folder, key, href):
        return os.path.join(folder, safe_name(item.get("id", "cena"), key, href).rsplit(".", 1)[0] + ".tif")

    def cache_bands(self, item, folder, rect, target_crs, progress, keys, offline=False, force_download=False):
        selected = set(keys)
        assets = [(key, href) for key, href in raster_assets(item) if key in selected]
        if not selected or not selected.issubset({key for key, _ in assets}):
            raise CatalogError("Uma das bandas selecionadas não está disponível na cena.")
        os.makedirs(folder, exist_ok=True)
        try:
            from osgeo import gdal
        except ImportError as exc:
            raise CatalogError("O QGIS precisa disponibilizar o GDAL Python para recortar bandas.") from exc
        errors, by_key = [], {}
        config = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
                  "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MULTIPLEX": "YES",
                  "GDAL_HTTP_VERSION": "2TLS", "GDAL_HTTP_CONNECTTIMEOUT": "15",
                  "GDAL_HTTP_TIMEOUT": "60", "GDAL_HTTP_MAX_RETRY": "3",
                  "GDAL_HTTP_RETRY_DELAY": "1"}
        thread_config = getattr(gdal, "SetThreadLocalConfigOption", None)
        set_config = thread_config or gdal.SetConfigOption
        get_config = getattr(gdal, "GetThreadLocalConfigOption", None) if thread_config else None
        get_config = get_config or getattr(gdal, "GetConfigOption", lambda name: None)

        def prepare(index_asset):
            index, (key, href) = index_asset
            if self.cancelled():
                raise CatalogError("Operação cancelada.")
            gdal.UseExceptions()
            previous = {name: get_config(name) for name in config}
            for name, value in config.items():
                set_config(name, value)
            target = self.cached_band_path(item, folder, key, href)
            partial = target + ".part.tif"
            try:
                if not force_download and os.path.isfile(target) and os.path.getsize(target) > 0:
                    try:
                        check = gdal.Open(target) if hasattr(gdal, "Open") else True
                        if check is not None:
                            check = None
                            if hasattr(gdal, "Open"):
                                validate_cached_raster(target, gdal, self.cancelled)
                            by_key[key] = target
                            progress("Reutilizando banda local {} ({}/{})".format(key, index, len(assets)))
                            return
                    except Exception:
                        logging.getLogger(__name__).warning("Banda local inválida; será recuperada se houver rede.")
                if offline:
                    errors.append("{}: banda não disponível no acervo local".format(key))
                    return
                progress("Baixando recorte {} ({}/{})".format(key, index, len(assets)))
                signed = self.signed_url(href)
                options = gdal.WarpOptions(format="GTiff", outputBounds=context_bbox(rect),
                    outputBoundsSRS="EPSG:4326", dstSRS=target_crs,
                    resampleAlg="near", multithread=True, warpMemoryLimit=32,
                    errorThreshold=0, dstNodata=0,
                    warpOptions=["INIT_DEST=NO_DATA"],
                    creationOptions=["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=2"],
                    callback=lambda fraction, message, user_data: 0 if self.cancelled() else 1)
                result = gdal.Warp(partial, "/vsicurl/" + signed, options=options)
                if result is None:
                    raise CatalogError("GDAL não conseguiu abrir a banda remota.")
                result = None
                if self.cancelled():
                    raise CatalogError("Operação cancelada.")
                if hasattr(gdal, "Open"):
                    validate_raster(partial, gdal, self.cancelled)
                os.replace(partial, target)
                if hasattr(gdal, "Open"):
                    stat = os.stat(target)
                    with open(target + ".validated.json", "w", encoding="utf-8") as stream:
                        json.dump([stat.st_size, stat.st_mtime_ns], stream)
                by_key[key] = target
            except Exception as exc:
                if self.cancelled():
                    raise CatalogError("Operação cancelada.") from exc
                errors.append("{}: {}".format(key, exc))
            finally:
                if os.path.exists(partial):
                    os.remove(partial)
                for name, value in previous.items():
                    set_config(name, value)

        indexed = list(enumerate(assets, 1))
        # Each worker owns its GDAL dataset. Older bindings use serial fallback.
        workers = min(3, len(assets)) if thread_config and not offline else 1
        if workers == 1:
            for index_asset in indexed:
                prepare(index_asset)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for _ in pool.map(prepare, indexed):
                    pass
        return by_key, errors

    def download_scene(self, item, folder, rect, target_crs, progress, rgb_keys,
                       product="rgb", offline=False, force_download=False):
        if product in ("ndvi", "nbr"):
            rgb_keys = index_keys(item, product)
            if not rgb_keys:
                raise CatalogError("Esta cena não contém as bandas necessárias ao índice selecionado.")
        elif product != "rgb" or len(rgb_keys) != 3:
            raise CatalogError("Escolha as bandas vermelha, verde e azul da composição.")
        by_key, errors = self.cache_bands(item, folder, rect, target_crs, progress,
                                         rgb_keys, offline, force_download)
        if not all(key in by_key for key in rgb_keys):
            raise CatalogError("Não foi possível preparar as bandas: " + "; ".join(errors[:3]))
        from osgeo import gdal
        files = list(by_key.values())
        if product in ("ndvi", "nbr"):
            composite = os.path.join(folder, product.upper() + ".tif")
            if not os.path.isfile(composite) or any(os.stat(path).st_mtime_ns > os.stat(composite).st_mtime_ns for path in files):
                progress("Calculando {} a partir das reflectâncias…".format(product.upper()))
                partial = composite + ".part.tif"
                try:
                    write_index(item, by_key, partial, gdal, product, self.cancelled)
                    os.replace(partial, composite)
                finally:
                    if os.path.exists(partial):
                        os.remove(partial)
            return files, errors, composite
        fingerprint = hashlib.sha256(json.dumps({"bands": list(rgb_keys), "resolution": "highest", "nodata": 0, "profile": 2, "sources": [(key, os.stat(by_key[key]).st_size, os.stat(by_key[key]).st_mtime_ns) for key in rgb_keys]}).encode()).hexdigest()[:12]
        composite = os.path.join(folder, "RGB_" + fingerprint + ".vrt")
        if os.path.isfile(composite) and os.path.getsize(composite) > 0:
            return files, errors, composite
        result = gdal.BuildVRT(composite, [by_key[key] for key in rgb_keys],
                               options=gdal.BuildVRTOptions(separate=True, resolution="highest", resampleAlg="nearest", VRTNodata=0))
        if result is None:
            raise CatalogError("Não foi possível montar a composição RGB.")
        result = None
        return files, errors, composite
