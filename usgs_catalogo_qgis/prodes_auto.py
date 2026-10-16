# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Automatic, reproducible spectral screening. No trained model or legal verdict.

GDAL/OGR datasets are opened inside the worker; payloads contain only Python
values. The experimental thresholds are plugin rules, not INPE thresholds.
"""
import json
import math
import os
from datetime import date
from pathlib import Path

from .prodes import ProdesError

AUTO_RULE_VERSION = "2.1.0-spectral-1"
THRESHOLDS = {"min_pixels": 9, "min_coverage": 0.80, "ndvi_drop": 0.20,
              "ndmi_drop": 0.15, "changed_fraction": 0.60,
              "stable_ndvi": 0.05, "stable_ndmi": 0.05, "max_season_days": 60}
LAW = "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm"


def metadata_for_layer(path, scene_id, keys, stored=""):
    """Read catalog provenance, including archives created before version 2.1."""
    if stored:
        value = json.loads(str(stored))
        if value.get("scene_id") != scene_id or value.get("keys") != keys:
            raise ProdesError("Metadados espectrais não correspondem às bandas/cena do raster.")
        return value
    # A catalog VRT lives in areas/<aoi>/cenas/<scene>/. No recursive scan.
    folder = Path(path).resolve().parent
    index = folder.parent.parent / "catalogo.json"
    if scene_id and index.is_file():
        with index.open(encoding="utf-8") as stream:
            entries = json.load(stream).get("scenes", {}).values()
        for entry in entries:
            item = entry.get("item", {})
            if item.get("id") == scene_id:
                return scene_metadata(item, keys, str(folder))
    # Landsat C2 band names are unique in this catalog; Sentinel needs its
    # archived STAC metadata because processing offsets may differ.
    if scene_id and set(keys) <= {"swir16", "nir08", "red", "green", "blue", "swir22", "coastal"}:
        return {"scene_id": scene_id, "keys": keys, "collection": "landsat-c2-l2",
                "coefficients": [[0.0000275, -0.2] for _ in keys],
                "native_resolution": 30, "qa_path": "", "saturation_path": "",
                "qa_kind": "landsat", "calibration_source": "Landsat C2 SR / bandas do catálogo"}
    raise ProdesError("Calibração não identificada. Reimporte a composição PRODES pelo catálogo para preservar os metadados radiométricos.")


def scene_metadata(item, keys, folder):
    from .stac import reflectance_coefficients, PublicCatalog, raster_assets
    collection = item.get("collection", "")
    if collection not in ("landsat-c2-l2", "sentinel-2-l2a"):
        raise ProdesError("Coleção sem calibração suportada na triagem automática.")
    assets = dict(raster_assets(item, include_auxiliary=True))
    def local(key):
        if key not in assets:
            return ""
        path = PublicCatalog.cached_band_path(item, folder, key, assets[key])
        return path if os.path.isfile(path) else ""
    sentinel = collection == "sentinel-2-l2a"
    # Do not silently invent Sentinel offsets absent from its STAC metadata.
    if sentinel and not item.get("properties", {}).get("s2:processing_baseline") and any(not item.get("assets", {}).get(key, {}).get("raster:bands") for key in keys):
        raise ProdesError("Metadados de escala das bandas Sentinel ausentes na cena.")
    return {"scene_id": item.get("id", ""), "keys": list(keys), "collection": collection,
            "sources": list(item.get("catalog:sources", [])),
            "download_sources": dict(item.get("catalog:download_sources", {})),
            "platform": item.get("properties", {}).get("platform", ""),
            "coefficients": [list(reflectance_coefficients(item, key)) for key in keys],
            "native_resolution": 20 if sentinel else 30,
            "qa_kind": "sentinel" if sentinel else "landsat",
            "qa_path": local("SCL" if sentinel else "qa_pixel"),
            "saturation_path": "" if sentinel else local("qa_radsat"),
            "calibration_source": "Metadados STAC / escala oficial e baseline Sentinel quando aplicável",
            "processing_baseline": item.get("properties", {}).get("s2:processing_baseline", "")}


def spectral_indices(values):
    """Input order SWIR1, NIR, red; values already calibrated reflectance."""
    import numpy as np
    swir, nir, red = values
    valid = np.isfinite(values).all(axis=0) & (values >= 0).all(axis=0) & (values <= 1).all(axis=0)
    valid &= (nir + red > 1e-6) & (nir + swir > 1e-6)
    ndvi = np.full(red.shape, np.nan, dtype="float32")
    ndmi = np.full(red.shape, np.nan, dtype="float32")
    np.divide(nir - red, nir + red, out=ndvi, where=valid)
    np.divide(nir - swir, nir + swir, out=ndmi, where=valid)
    return ndvi, ndmi, valid


def qa_valid(values, kind):
    import numpy as np
    if kind == "landsat":
        # QA_PIXEL: fill, dilated cloud, cirrus, cloud, shadow, snow (bits 0..5).
        return np.isfinite(values) & ((values.astype("uint32") & 63) == 0)
    if kind == "sentinel":
        # SCL: vegetation, bare soil and water; exclude uncertain/unclassified,
        # cloud/shadow, snow, defective and missing samples.
        return np.isin(values, (4, 5, 6))
    raise ProdesError("Máscara de qualidade não reconhecida.")


def temporal_issue(item, dates):
    try:
        parsed = [date.fromisoformat(value) for value in dates]
    except (ValueError, TypeError):
        return "Datas inválidas."
    year = item.get("year")
    if len(parsed) != 3 or not parsed[2] < parsed[1] < parsed[0]:
        return "São necessárias três datas distintas, da mais recente para a mais antiga."
    if not year or [d.year for d in parsed] != [year, year - 1, year - 2]:
        return "Conjunto de imagens não cobre este ano PRODES e os dois anteriores. Analise um ano por conjunto."
    # Leap-safe seasonal positions on a common leap year; circular difference.
    slots = [(date(2000, d.month, d.day) - date(2000, 1, 1)).days for d in parsed]
    if any(min(abs(a - b), 366 - abs(a - b)) > THRESHOLDS["max_season_days"] for a in slots for b in slots):
        return "Datas afastadas mais de 60 dias na estação do ano: sazonalidade pode confundir a comparação."
    return ""


def decide(item, stats, dates, annual, tolerance=False, mixed=False):
    result = {"mode": "automatic", "rule_version": AUTO_RULE_VERSION, "dates": list(dates),
              "status": "Inconclusivo", "reason": "", "reviewed": False, "user_review": "A revisar",
              "automatic": stats, "observations": [], "thresholds": dict(THRESHOLDS)}
    failures = []
    if not annual or item.get("year") is None:
        failures.append("Origem sem confirmação de incremento anual por bioma.")
    if not item.get("uuid"):
        failures.append("UUID oficial ausente.")
    issue = temporal_issue(item, dates)
    if issue:
        failures.append(issue)
    if stats.get("error"):
        failures.append(stats["error"])
    if tolerance and item.get("core_ha") is not None and item["core_ha"] <= 0.000001:
        result["status"] = "Sobreposição restrita à borda"
        result["reason"] = "Interseção contida na faixa interna de 60 m do CAR. Diagnóstico espacial separado; não comprova erro espectral nem legalidade."
        return result
    if not stats.get("error"):
        if stats.get("common_pixels", 0) < THRESHOLDS["min_pixels"]:
            failures.append("Menos de 9 pixels comuns válidos: amostra insuficiente na resolução nativa.")
        if stats.get("common_coverage", 0) < THRESHOLDS["min_coverage"]:
            failures.append("Cobertura comum válida inferior a 80% do recorte amostrado.")
        if not stats.get("qa_complete"):
            failures.append("Qualidade local incompleta (máscara de nuvens/sombras ou saturação ausente); nuvens da cena <20% não garantem céu limpo no imóvel.")
        if mixed:
            failures.append("Sensores diferentes: comparação calculada na resolução mais grossa, sem harmonização espectral validada.")
    signal = stats.get("signal", "Evidência espectral insuficiente")
    result["spectral_signal"] = signal
    numbers = ""
    if stats.get("delta_ndvi") is not None:
        numbers = " ΔNDVI={:+.3f}; ΔNDMI={:+.3f}; queda conjunta em {:.1f}% dos pixels comuns.".format(
            stats["delta_ndvi"], stats["delta_ndmi"], 100 * stats["changed_fraction"])
    if failures:
        result["reason"] = " ".join(failures) + " Sinal exploratório: " + signal + "." + numbers
    else:
        statuses = {"Queda espectral no ano registrado": "Sinal compatível com perda de cobertura",
                    "Queda espectral já presente no ano anterior": "Indício espectral de divergência temporal",
                    "Cobertura espectral estável": "Resposta espectral majoritariamente estável",
                    "Resposta ambígua": "Inconclusivo"}
        result["status"] = statuses.get(signal, "Inconclusivo")
        result["reason"] = signal + "." + numbers + " Triagem preliminar; índices não distinguem floresta nativa, pastagem e regeneração, nem demonstram falso PRODES."
    result["reason"] += " Verifique textura, alinhamento, data oficial de referência e histórico de nuvens antes de concordar."
    return result


def summarise(indices, masks, inside, resolution, qa_complete):
    import numpy as np
    total = int(inside.sum())
    valid = [mask & inside for mask in masks]
    common = inside.copy()
    for mask in valid:
        common &= mask
    count = int(common.sum())
    result = {"grid_pixels": total, "common_pixels": count,
              "common_coverage": count / total if total else 0.0,
              "resolution_m": resolution, "qa_complete": qa_complete, "per_date": []}
    for (ndvi, ndmi), mask in zip(indices, valid):
        n = int(mask.sum())
        result["per_date"].append({"valid_pixels": n, "coverage": n / total if total else 0.0,
            "ndvi_median": float(np.median(ndvi[mask])) if n else None,
            "ndmi_median": float(np.median(ndmi[mask])) if n else None})
    if not count:
        result.update(error="Nenhum pixel comum válido nas três datas.", signal="Evidência espectral insuficiente")
        return result
    differences = []
    stable_fractions = []
    for newer, older in ((0, 1), (1, 2)):
        dv = indices[newer][0][common] - indices[older][0][common]
        dm = indices[newer][1][common] - indices[older][1][common]
        differences.append((float(np.median(dv)), float(np.median(dm)),
            float(np.mean((dv <= -THRESHOLDS["ndvi_drop"]) & (dm <= -THRESHOLDS["ndmi_drop"])))))
        stable_fractions.append(float(np.mean((np.abs(dv) <= THRESHOLDS["stable_ndvi"]) & (np.abs(dm) <= THRESHOLDS["stable_ndmi"]))))
    recent, prior = differences
    result.update(delta_ndvi=recent[0], delta_ndmi=recent[1], changed_fraction=recent[2],
                  prior_delta_ndvi=prior[0], prior_delta_ndmi=prior[1], prior_changed_fraction=prior[2],
                  stable_fraction=min(stable_fractions))
    if prior[2] >= THRESHOLDS["changed_fraction"]:
        signal = "Queda espectral já presente no ano anterior"
    elif recent[2] >= THRESHOLDS["changed_fraction"]:
        signal = "Queda espectral no ano registrado"
    elif min(stable_fractions) >= 0.80:
        signal = "Cobertura espectral estável"
    else:
        signal = "Resposta ambígua"
    result["signal"] = signal
    return result


def sample_polygon(wkt, images, cancelled=lambda: False, historical=False, timeline=False):
    """Read only each polygon envelope, same UTM grid, nearest neighbour.

    Pixel centres must be inside the polygon; all_touched is intentionally not
    used. Small slivers therefore remain inconclusive rather than using pixels
    from neighbouring parcels. No gap filling and no styled RGB computation.
    """
    import numpy as np
    from osgeo import gdal, ogr, osr
    gdal.UseExceptions()
    if cancelled():
        raise ProdesError("Operação cancelada.")
    geom = ogr.CreateGeometryFromWkt(wkt)
    if geom is None or geom.IsEmpty():
        raise ProdesError("Recorte vazio ou inválido para amostragem.")
    center = geom.Centroid()
    zone = max(1, min(60, int((center.GetX() + 180) / 6) + 1))
    source = osr.SpatialReference()
    source.ImportFromEPSG(4326)
    target = osr.SpatialReference()
    target.ImportFromEPSG((32700 if center.GetY() < 0 else 32600) + zone)
    for srs in (source, target):
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geom.AssignSpatialReference(source)
    if geom.Transform(osr.CoordinateTransformation(source, target)) != 0:
        raise ProdesError("Falha ao transformar o recorte para a grade métrica.")
    resolution = max(float(image["metadata"]["native_resolution"]) for image in images)
    # Preserve genuinely coarser input resolutions, never claim restored detail.
    for image in images:
        dataset = gdal.Open(image["path"])
        if dataset is None or not dataset.GetProjection():
            raise ProdesError("Raster sem georreferenciamento válido.")
        raster_srs = osr.SpatialReference(wkt=dataset.GetProjection())
        if raster_srs.IsProjected():
            gt = dataset.GetGeoTransform()
            resolution = max(resolution, math.hypot(gt[1], gt[4]) * raster_srs.GetLinearUnits(),
                             math.hypot(gt[2], gt[5]) * raster_srs.GetLinearUnits())
        dataset = None
    minx, maxx, miny, maxy = geom.GetEnvelope()
    bounds = (math.floor(minx / resolution) * resolution, math.floor(miny / resolution) * resolution,
              math.ceil(maxx / resolution) * resolution, math.ceil(maxy / resolution) * resolution)
    width = max(1, int(round((bounds[2] - bounds[0]) / resolution)))
    height = max(1, int(round((bounds[3] - bounds[1]) / resolution)))
    if width * height > 1000000:
        raise ProdesError("Recorte excede um milhão de pixels. Divida a análise sem reduzir a resolução.")
    if timeline and width * height * len(images) > 8000000:
        raise ProdesError("Série histórica excede oito milhões de pixels-data. Divida a área ou reduza o período, preservando a resolução.")
    projection = target.ExportToWkt()
    gt = (bounds[0], resolution, 0, bounds[3], 0, -resolution)
    mask_ds = gdal.GetDriverByName("MEM").Create("", width, height, 1, gdal.GDT_Byte)
    mask_ds.SetGeoTransform(gt)
    mask_ds.SetProjection(projection)
    vectors = ogr.GetDriverByName("Memory").CreateDataSource("")
    layer = vectors.CreateLayer("clip", target, geom_type=ogr.wkbMultiPolygon)
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(geom)
    layer.CreateFeature(feature)
    gdal.RasterizeLayer(mask_ds, [1], layer, burn_values=[1])
    inside = mask_ds.ReadAsArray().astype(bool)
    indices, valid_masks, qa_flags, nir_arrays, nbr_arrays = [], [], [], [], []
    def warp(path):
        if cancelled():
            raise ProdesError("Operação cancelada.")
        value = gdal.Warp("", path, format="MEM", dstSRS=projection, outputBounds=bounds,
            width=width, height=height, resampleAlg="near", outputType=gdal.GDT_Float32,
            dstNodata=-9999, errorThreshold=0, warpMemoryLimit=32,
            callback=lambda fraction, message, userdata: 0 if cancelled() else 1)
        if value is None:
            raise ProdesError("Falha ao alinhar os pixels.")
        return value
    for image in images:
        aligned = warp(image["path"])
        metadata = image["metadata"]
        arrays, valid = [], inside.copy()
        for band in image["bands"]:
            raw = aligned.GetRasterBand(band).ReadAsArray()
            valid &= np.isfinite(raw) & (raw != -9999) & (raw != 0)
            scale, offset = metadata["coefficients"][band - 1]
            if not math.isfinite(scale) or not math.isfinite(offset) or scale <= 0:
                raise ProdesError("Escala radiométrica inválida.")
            arrays.append(raw * scale + offset)
        ndvi, ndmi, numeric = spectral_indices(np.asarray(arrays))
        valid &= numeric
        qa_path = metadata.get("qa_path", "")
        qa_present = bool(qa_path and os.path.isfile(qa_path))
        if qa_present:
            qa = warp(qa_path).ReadAsArray()
            valid &= (qa >= 0) & qa_valid(np.maximum(qa, 0), metadata["qa_kind"])
        saturation = metadata.get("saturation_path", "")
        saturation_present = bool(saturation and os.path.isfile(saturation))
        if saturation_present:
            valid &= warp(saturation).ReadAsArray() == 0
        qa_flags.append(qa_present and (metadata["qa_kind"] != "landsat" or saturation_present))
        valid_masks.append(valid)
        indices.append((ndvi, ndmi))
        if timeline:
            nir_arrays.append(arrays[1])
            nbr = None
            if image.get("nbr_path") and os.path.isfile(image["nbr_path"]):
                candidate = warp(image["nbr_path"]).ReadAsArray()
                nbr = np.where((candidate >= -1) & (candidate <= 1), candidate, np.nan)
            nbr_arrays.append(nbr)
    if timeline:
        from .prodes_history import summarise_timeline
        result = summarise_timeline(images, indices, valid_masks, inside, qa_flags,
                                    nir_arrays, nbr_arrays, resolution)
    elif historical:
        from .prodes_contestation import HISTORICAL_LIMITS
        if len(images) != 1:
            raise ProdesError("A referência pré-marco deve conter uma imagem.")
        valid = valid_masks[0] & inside
        count, total = int(valid.sum()), int(inside.sum())
        ndvi, ndmi = indices[0]
        low = valid & (ndvi >= HISTORICAL_LIMITS["ndvi_min"]) & (ndvi <= HISTORICAL_LIMITS["ndvi_max"])
        low &= (ndmi <= HISTORICAL_LIMITS["ndmi_max"]) & (arrays[1] >= HISTORICAL_LIMITS["nir_min"])
        result = {"grid_pixels": total, "common_pixels": count,
            "common_coverage": count / total if total else 0.0, "qa_complete": all(qa_flags),
            "resolution_m": resolution, "low_cover_fraction": int(low.sum()) / count if count else 0.0,
            "ndvi_median": float(np.median(ndvi[valid])) if count else None,
            "ndmi_median": float(np.median(ndmi[valid])) if count else None,
            "experimental_limits": dict(HISTORICAL_LIMITS)}
        if not count:
            result["error"] = "Nenhum pixel histórico válido na sobreposição consolidada/PRODES."
    else:
        result = summarise(indices, valid_masks, inside, resolution, all(qa_flags))
    result["grid_crs"] = "EPSG:" + str(target.GetAuthorityCode(None))
    result["quality_by_date"] = qa_flags
    return result


def run_analysis(payload, progress=lambda text: None, cancelled=lambda: False):
    from .prodes_contestation import historical_assessment, contestability
    from .prodes_argument import attach_argumentation
    results = []
    images = payload["images"]
    mixed = len({image["metadata"]["collection"] for image in images}) > 1 or len({image["metadata"].get("platform", "") for image in images} - {""}) > 1
    for index, (item, geometry) in enumerate(zip(payload["rows"], payload["geometries"])):
        if cancelled():
            raise ProdesError("Operação cancelada.")
        progress("Analisando pixels do polígono {} de {}…".format(index + 1, len(payload["rows"])))
        if temporal_issue(item, payload["dates"]):
            stats = {"error": temporal_issue(item, payload["dates"])}
        else:
            try:
                stats = sample_polygon(geometry, images, cancelled)
            except Exception as exc:
                if cancelled():
                    raise ProdesError("Operação cancelada.") from exc
                stats = {"error": str(exc)}
        result = decide(item, stats, payload["dates"], payload["annual"], payload["tolerance"], mixed)
        historic = payload.get("historical_image")
        overlap_geometries = payload.get("consolidated_geometries", [])
        historic_result = None
        if historic and index < len(overlap_geometries) and overlap_geometries[index]:
            try:
                historical_stats = sample_polygon(overlap_geometries[index], [historic], cancelled, historical=True)
            except Exception as exc:
                if cancelled():
                    raise ProdesError("Operação cancelada.") from exc
                historical_stats = {"error": str(exc)}
            historic_result = historical_assessment(historical_stats, historic["date"])
        if "consolidated_geometries" in payload:
            result["historical"] = historic_result or {"status": "Não avaliada", "reason": "Referência histórica ausente ou sem sobreposição consolidada/PRODES."}
            technical = payload.get("consolidated_technical", False)
            result["consolidation_assessment"] = ("Área rural consolidada — classificação técnica informada (Lei 12.651/2012, art. 3º, IV)" if technical and item.get("consolidated_ha", 0) > 0 else "Sem classificação técnica de consolidada sobreposta")
            result["contestability"] = contestability(item, result, historic_result, payload["annual"], payload["tolerance"], technical)
        attach_argumentation(item, result)
        results.append(result)
    return results
