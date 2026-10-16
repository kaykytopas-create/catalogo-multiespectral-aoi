# SPDX-License-Identifier: GPL-2.0-or-later
"""AOI QA screening and radiometrically consistent natural-color display."""
def natural_limits(item, keys):
    from .stac import natural_rgb_keys, reflectance_coefficients
    if tuple(keys or ()) != tuple(natural_rgb_keys(item)) or len(keys or ()) != 3:
        return None
    limits={}
    for band,key in enumerate(keys,1):
        scale,offset=reflectance_coefficients(item,key)
        if scale<=0:raise ValueError('Escala radiométrica inválida.')
        # Same physical interval for R/G/B: clouds stay neutral, original DN unchanged.
        limits[str(band)]=[(0.0-offset)/scale,(0.30-offset)/scale]
    return limits


def inspect_qa(path, kind, geometry_wkt):
    from osgeo import gdal,ogr,osr
    import numpy as np
    import math
    ds=gdal.Open(path)
    if ds is None:raise ValueError('Máscara de qualidade indisponível.')
    factor=max(1,math.ceil(max(ds.RasterXSize,ds.RasterYSize)/1024))
    w,h=max(1,ds.RasterXSize//factor),max(1,ds.RasterYSize//factor)
    gt=ds.GetGeoTransform();grid=gdal.GetDriverByName('MEM').Create('',w,h,1,gdal.GDT_Byte)
    grid.SetGeoTransform((gt[0],gt[1]*ds.RasterXSize/w,gt[2]*ds.RasterYSize/h,gt[3],gt[4]*ds.RasterXSize/w,gt[5]*ds.RasterYSize/h));grid.SetProjection(ds.GetProjection())
    inside=np.ones((h,w),dtype=bool)
    if geometry_wkt:
        source=osr.SpatialReference();source.ImportFromEPSG(4326)
        target=osr.SpatialReference();target.ImportFromWkt(ds.GetProjection())
        for s in (source,target):s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        geom=ogr.CreateGeometryFromWkt(geometry_wkt)
        if geom is None:raise ValueError('Limite inválido.')
        geom.Transform(osr.CoordinateTransformation(source,target))
        vector=ogr.GetDriverByName('Memory').CreateDataSource('');layer=vector.CreateLayer('aoi',target,ogr.wkbUnknown)
        feature=ogr.Feature(layer.GetLayerDefn());feature.SetGeometry(geom);layer.CreateFeature(feature)
        grid.GetRasterBand(1).Fill(0)
        if gdal.RasterizeLayer(grid,[1],layer,burn_values=[1])!=0:raise ValueError('Falha na inspeção do imóvel.')
        inside=grid.ReadAsArray().astype(bool)
    total=int(inside.sum())
    if not total:raise ValueError('Cena não cobre amostras do imóvel.')
    values=ds.GetRasterBand(1).ReadAsArray(buf_xsize=w,buf_ysize=h)
    if values is None:raise ValueError('Falha ao ler QA.')
    if kind=='landsat':
        bits=values.astype('uint32');valid=((bits&1)==0)&(bits!=0)
        clouds=(bits&14)!=0;clear=(bits&63)==0
    else:
        valid=~np.isin(values,(0,1));clouds=np.isin(values,(8,9,10));clear=np.isin(values,(4,5,6))
    return {'valid_fraction':float((inside&valid).sum()/total),
            'clear_fraction':float((inside&valid&clear).sum()/total),
            'cloud_percent':float(100*(inside&valid&clouds).sum()/total),
            'sample_pixels':total,'sampled':factor>1,'basis':'QA no imóvel: amostra de nuvens, sombra, neve e preenchimento; não prova nitidez ou exatidão'}


def quality_allowed(quality, plan):
    cloud=quality.get('cloud_percent')
    if cloud is None or quality.get('valid_fraction',0)<.99 or quality.get('clear_fraction',0)<.98:return False
    maximum=plan.get('cloud_max',20)
    return cloud<maximum if plan.get('cloud_strict',True) else cloud<=maximum
