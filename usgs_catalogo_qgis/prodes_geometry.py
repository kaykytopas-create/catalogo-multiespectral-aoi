# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Polygon-only copies for parcel/PRODES overlays, retaining area components."""
from .prodes import ProdesError


def polygon_copy(geometry, context="Geometria"):
    from qgis.core import QgsGeometry, QgsWkbTypes

    value = QgsGeometry(geometry)
    if value.isNull() or value.isEmpty():
        raise ProdesError(context + ": geometria vazia.")
    repaired = not value.isGeosValid()
    if repaired:
        value = value.makeValid()
    if value.isNull() or value.isEmpty():
        raise ProdesError(context + ": falha ao corrigir geometria: " + value.lastError())
    polygon_type = QgsWkbTypes.GeometryType.PolygonGeometry
    # GEOS makeValid/intersection can return polygon(s) alongside collapsed
    # lines or points. Keep existing polygon components, without buffering or
    # creating artificial area from lower-dimensional remnants.
    if QgsWkbTypes.flatType(value.wkbType()) == QgsWkbTypes.Type.GeometryCollection:
        # A repaired collection may contain a MultiPolygon rather than direct
        # Polygon children. Flatten recursively so these surfaces are retained
        # on QGIS versions whose subclass conversion filters multipart children.
        pending, parts = [value], []
        while pending:
            child = pending.pop()
            if child.isNull() or child.isEmpty():
                continue
            collection = QgsWkbTypes.flatType(child.wkbType()) == QgsWkbTypes.Type.GeometryCollection
            if collection or (child.type() == polygon_type and child.isMultipart()):
                pending.extend(child.asGeometryCollection())
            elif child.type() == polygon_type:
                parts.append(child)
        if not parts:
            raise ProdesError(context + ": sem superfície poligonal utilizável após validação.")
        value = QgsGeometry.collectGeometry(parts)
        repaired = True
    if value.isNull() or value.isEmpty() or value.type() != polygon_type or value.area() <= 0:
        raise ProdesError(context + ": sem superfície poligonal utilizável após validação.")
    if not value.isGeosValid():
        raise ProdesError(context + ": as partes poligonais permanecem inválidas após correção.")
    if not value.convertToMultiType():
        raise ProdesError(context + ": falha na conversão para MultiPolygon.")
    return value, repaired
