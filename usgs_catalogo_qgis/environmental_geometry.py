# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact parcel intersection in independent worker-owned QGIS geometries."""
import math
from .environmental_http import ConsultationError


class ParcelOverlay:
    def __init__(self, wkt):
        from qgis.core import QgsGeometry, QgsDistanceArea, QgsCoordinateReferenceSystem, QgsCoordinateTransformContext
        from .prodes_geometry import polygon_copy
        self.parcel, _ = polygon_copy(QgsGeometry.fromWkt(wkt), 'Limite do imóvel')
        self.measure = QgsDistanceArea()
        self.measure.setSourceCrs(QgsCoordinateReferenceSystem('EPSG:4326'), QgsCoordinateTransformContext())
        self.measure.setEllipsoid('WGS84')
        self.parcel_ha = self.measure.measureArea(self.parcel) / 10000

    def esri_geometry(self):
        rings = []
        for polygon in self.parcel.asMultiPolygon():
            for index, ring in enumerate(polygon):
                coords = [[p.x(), p.y()] for p in ring]
                signed = sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(coords,coords[1:]))
                # Esri outer rings clockwise; holes counterclockwise.
                if (index == 0 and signed > 0) or (index > 0 and signed < 0):
                    coords.reverse()
                rings.append(coords)
        return {'rings':rings, 'spatialReference':{'wkid':4326}}

    def __call__(self, value):
        from qgis.core import QgsGeometry, QgsPointXY
        if not isinstance(value, dict):
            raise ConsultationError('Registro sem geometria: abrangência espacial não verificada.')
        typ, coordinates = value.get('type'), value.get('coordinates')
        def point(c):
            x, y = float(c[0]), float(c[1])
            if not math.isfinite(x) or not math.isfinite(y) or not -180 <= x <= 180 or not -90 <= y <= 90:
                raise ConsultationError('Coordenadas públicas fora de longitude/latitude.')
            return QgsPointXY(x, y)
        if typ == 'Polygon':
            geom = QgsGeometry.fromPolygonXY([[point(c) for c in ring] for ring in coordinates])
        elif typ == 'MultiPolygon':
            geom = QgsGeometry.fromMultiPolygonXY([[[point(c) for c in ring] for ring in poly] for poly in coordinates])
        elif typ == 'Point':
            geom = QgsGeometry.fromPointXY(point(coordinates))
        elif typ == 'MultiPoint':
            geom = QgsGeometry.fromMultiPointXY([point(c) for c in coordinates])
        else:
            raise ConsultationError('Tipo geométrico não suportado: ' + str(typ))
        repaired = not geom.isGeosValid()
        if repaired:
            geom = geom.makeValid()
        if geom.isEmpty() or not geom.isGeosValid():
            raise ConsultationError('Geometria pública inválida; registro pendente de conferência.')
        if not self.parcel.intersects(geom):
            return None
        if typ in ('Point', 'MultiPoint'):
            return {'relation': 'ponto no limite/imóvel; sem área de embargo calculável', 'overlap_ha': None,
                    'parcel_percent': None, 'geometry_repaired': repaired}
        overlap = self.parcel.intersection(geom)
        if overlap.isNull():
            raise ConsultationError('Falha na interseção espacial; consulta parcial.')
        area = self.measure.measureArea(overlap) / 10000
        if area <= 0:
            return None  # boundary-only contact is not overlapping area
        return {'relation': 'interseção poligonal', 'overlap_ha': area,
                'parcel_percent': min(100, 100 * area / self.parcel_ha), 'geometry_repaired': repaired}
