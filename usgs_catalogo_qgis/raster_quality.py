# SPDX-License-Identifier: GPL-2.0-or-later
"""Sample actual raster masks within AOI; no reconstruction or smoothing."""
import math


def inspect_raster(path, geometry_wkt=None):
    from osgeo import gdal, ogr, osr
    import numpy as np
    ds = gdal.Open(path)
    if ds is None: raise ValueError('Raster não pôde ser aberto para inspeção.')
    width, height = ds.RasterXSize, ds.RasterYSize
    if not width or not height: raise ValueError('Raster vazio.')
    scale = max(1, math.ceil(max(width, height)/1024))
    sw, sh = max(1,width//scale), max(1,height//scale)
    mask = np.ones((sh,sw), dtype=bool)
    if geometry_wkt:
        source = osr.SpatialReference(); source.ImportFromEPSG(4326)
        target = osr.SpatialReference(); target.ImportFromWkt(ds.GetProjection())
        for srs in (source,target):srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        geometry = ogr.CreateGeometryFromWkt(geometry_wkt)
        if geometry is None:raise ValueError('Limite inválido na inspeção.')
        geometry.Transform(osr.CoordinateTransformation(source,target))
        vector=ogr.GetDriverByName('Memory').CreateDataSource('')
        layer=vector.CreateLayer('aoi',target,ogr.wkbUnknown)
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetGeometry(geometry);layer.CreateFeature(feature)
        grid=gdal.GetDriverByName('MEM').Create('',sw,sh,1,gdal.GDT_Byte)
        gt=ds.GetGeoTransform();grid.SetGeoTransform((gt[0],gt[1]*width/sw,gt[2]*height/sh,gt[3],gt[4]*width/sw,gt[5]*height/sh))
        grid.SetProjection(ds.GetProjection());grid.GetRasterBand(1).Fill(0)
        if gdal.RasterizeLayer(grid,[1],layer,burn_values=[1]) != 0:raise ValueError('Falha ao rasterizar limite para inspeção.')
        mask=grid.GetRasterBand(1).ReadAsArray().astype(bool)
    total=int(mask.sum())
    if not total:return {'status':'insufficient_sample','sample_pixels':0,'valid_fraction':None}
    valid=mask.copy()
    for index in range(1,ds.RasterCount+1):
        band=ds.GetRasterBand(index)
        data=band.ReadAsArray(buf_xsize=sw,buf_ysize=sh)
        if data is None:raise ValueError('Falha de leitura na banda '+str(index))
        valid &= np.isfinite(data) & (band.GetMaskBand().ReadAsArray(buf_xsize=sw,buf_ysize=sh)!=0)
        nodata=band.GetNoDataValue()
        if nodata is not None:valid &= data!=nodata
    fraction=int(valid.sum())/total
    return {'status':'complete_sample' if fraction==1 else 'missing_pixels','sample_pixels':total,'valid_fraction':fraction,
            'sampled':scale>1,'width':width,'height':height,'geotransform':list(ds.GetGeoTransform()),
            'scope':'Amostra de máscaras e dados no limite; não mede nuvens, nitidez temática ou exatidão posicional'}
