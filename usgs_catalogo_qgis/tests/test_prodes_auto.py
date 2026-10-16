# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from usgs_catalogo_qgis.prodes_auto import (spectral_indices, qa_valid, summarise,
    decide, temporal_issue, metadata_for_layer, scene_metadata, run_analysis)
from usgs_catalogo_qgis.prodes import report_html, ProdesError
from usgs_catalogo_qgis.stac import reflectance_coefficients

DATES = ['2022-07-01', '2021-07-01', '2020-07-01']
ITEM = {'year': 2022, 'uuid': 'synthetic', 'core_ha': 1, 'clip_ha': 1}


def stats(values, masks=None):
    pairs, valid = [], []
    for values_for_date in values:
        arr = np.stack([np.full((10, 10), v, dtype='float32') for v in values_for_date])
        ndvi, ndmi, ok = spectral_indices(arr)
        pairs.append((ndvi, ndmi)); valid.append(ok)
    return summarise(pairs, masks or valid, np.ones((10, 10), bool), 30, True)


class AutomaticTests(unittest.TestCase):
    def test_indices_use_swir1_and_calibrated_values(self):
        v, m, mask = spectral_indices(np.array([[[.2]], [[.6]], [[.1]]], dtype='float32'))
        self.assertAlmostEqual(float(v[0, 0]), 5/7, places=5)
        self.assertAlmostEqual(float(m[0, 0]), .5, places=5)
        self.assertTrue(mask[0, 0])
        self.assertFalse(spectral_indices(np.array([[[0]], [[0]], [[0]]]))[2][0, 0])
        self.assertFalse(spectral_indices(np.array([[[2]], [[.2]], [[.1]]]))[2][0, 0])

    def test_quality_masks_reject_cloud_shadow_fill_and_uncertain(self):
        self.assertEqual(qa_valid(np.array([64, 1, 2, 4, 8, 16, 32]), 'landsat').tolist(), [True] + [False]*6)
        self.assertEqual(qa_valid(np.arange(12), 'sentinel').tolist(), [False]*4 + [True]*3 + [False]*5)

    def test_current_drop_and_prior_drop_are_distinct(self):
        vegetation = [.2, .6, .1]; cleared = [.3, .3, .25]
        recent = stats([cleared, vegetation, vegetation])
        self.assertEqual(recent['changed_fraction'], 1)
        result = decide(ITEM, recent, DATES, True)
        self.assertEqual(result['status'], 'Sinal compatível com perda de cobertura')
        self.assertFalse(result['reviewed'])
        self.assertEqual(result['user_review'], 'A revisar')
        prior = stats([cleared, cleared, vegetation])
        self.assertEqual(decide(ITEM, prior, DATES, True)['status'], 'Indício espectral de divergência temporal')

    def test_regeneration_not_classified_as_false(self):
        result = decide(ITEM, stats([[.2,.6,.1],[.3,.3,.25],[.3,.3,.25]]), DATES, True)
        self.assertEqual(result['status'], 'Inconclusivo')
        stable = decide(ITEM, stats([[.2,.6,.1]]*3), DATES, True)
        self.assertNotIn('falso', stable['status'].lower())

    def test_common_pixels_not_different_locations(self):
        a = np.zeros((10,10), bool); a[:5,:] = True
        b = ~a
        result = stats([[.2,.6,.1]]*3, [a,b,a])
        self.assertEqual(result['common_pixels'], 0)
        self.assertEqual(decide(ITEM,result,DATES,True)['status'], 'Inconclusivo')

    def test_missing_qa_mixed_sensor_tiny_and_low_coverage(self):
        base = stats([[.3,.3,.25],[.2,.6,.1],[.2,.6,.1]])
        for updates in ({'qa_complete':False}, {'common_pixels':8}, {'common_coverage':.79}):
            self.assertEqual(decide(ITEM,{**base,**updates},DATES,True)['status'],'Inconclusivo')
        self.assertEqual(decide(ITEM,base,DATES,True,mixed=True)['status'],'Inconclusivo')
        self.assertEqual(decide(ITEM,base,DATES,False)['status'],'Inconclusivo')
        self.assertEqual(decide({**ITEM,'uuid':''},base,DATES,True)['status'],'Inconclusivo')

    def test_year_season_and_border(self):
        self.assertTrue(temporal_issue(ITEM,['2023-07-01','2022-07-01','2021-07-01']))
        self.assertTrue(temporal_issue(ITEM,['2022-01-01','2021-07-01','2020-07-01']))
        self.assertFalse(temporal_issue(ITEM,['2022-01-01','2021-12-31','2020-01-01']))
        result=decide({**ITEM,'core_ha':0}, {'error':'sem pixels'}, DATES,True,True)
        self.assertEqual(result['status'],'Sobreposição restrita à borda')

    def test_baseline_not_date_for_sentinel_offset(self):
        for baseline,offset in [('03.01',0),('04.00',-.1),('05.13',-.1)]:
            item={'collection':'sentinel-2-l2a','properties':{'s2:processing_baseline':baseline},'assets':{}}
            self.assertEqual(reflectance_coefficients(item,'B04'),(.0001,offset))
        with self.assertRaises(Exception):
            reflectance_coefficients({'collection':'sentinel-2-l2a'},'B04')

    def test_archive_metadata_migration_and_unknown_calibration(self):
        with tempfile.TemporaryDirectory() as folder:
            scene=Path(folder)/'cenas'/'hash';scene.mkdir(parents=True)
            item={'id':'s','collection':'sentinel-2-l2a','properties':{'s2:processing_baseline':'05.13'}}
            (Path(folder)/'catalogo.json').write_text(json.dumps({'scenes':{'k':{'item':item}}}))
            metadata=metadata_for_layer(str(scene/'RGB.vrt'),'s',['B11','B08','B04'])
            self.assertEqual(metadata['coefficients'][0],[.0001,-.1])
            with self.assertRaises(ProdesError):
                metadata_for_layer(str(scene/'RGB.vrt'),'other',['B11','B08','B04'])
            with self.assertRaises(ProdesError):
                metadata_for_layer(str(scene/'RGB.vrt'),'other',['B11','B08','B04'],json.dumps(metadata))

    def test_report_separates_algorithm_and_review_and_escapes(self):
        row={**ITEM,**decide(ITEM,stats([[.3,.3,.25],[.2,.6,.1],[.2,.6,.1]]),DATES,True),
             'user_review':'Discordo','notes':'<script>'}
        text=report_html({'Revisor':'<iframe>'},[row])
        self.assertIn('Discordo',text);self.assertIn('ΔNDVI',text)
        self.assertIn('não classificam origem nativa',text)
        self.assertIn('legalidade permanece não avaliada',text)
        self.assertNotIn('<script>',text);self.assertNotIn('<iframe>',text)

    def test_cancelled_and_temporal_mismatch_skip_pixels(self):
        payload={'rows':[ITEM],'geometries':['invalid'],'images':[],
                 'dates':['2023-07-01','2022-07-01','2021-07-01'],'annual':True,'tolerance':False}
        result=run_analysis(payload)
        self.assertEqual(result[0]['status'],'Inconclusivo')
        with self.assertRaises(ProdesError):
            run_analysis(payload,cancelled=lambda:True)


class GdalAutomaticTests(unittest.TestCase):
    def setUp(self):
        try:
            from osgeo import gdal,ogr,osr
        except ImportError:
            self.skipTest('GDAL necessário para integração raster')
        self.gdal,self.ogr,self.osr=gdal,ogr,osr
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.crs=osr.SpatialReference();self.crs.ImportFromEPSG(32722)
        self.crs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        wgs=osr.SpatialReference();wgs.ImportFromEPSG(4326);wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        shape=ogr.CreateGeometryFromWkt('POLYGON ((300000 9480000,300360 9480000,300360 9479640,300000 9479640,300000 9480000))')
        shape.Transform(osr.CoordinateTransformation(self.crs,wgs));self.wkt=shape.ExportToWkt()
        self.images=[]
        for i,year in enumerate((2022,2021,2020)):
            values=[.3,.3,.25] if i==0 else [.2,.6,.1]
            path=self.folder/f'{year}.tif';qa=self.folder/f'qa{year}.tif';sat=self.folder/f'sat{year}.tif'
            self.raster(path,[round((v+.2)/.0000275) for v in values],0)
            self.raster(qa,[64],0);self.raster(sat,[0],65535)
            self.images.append({'path':str(path),'bands':[1,2,3],'metadata':{
                'collection':'landsat-c2-l2','coefficients':[[.0000275,-.2]]*3,
                'native_resolution':30,'qa_kind':'landsat','qa_path':str(qa),'saturation_path':str(sat)}})

    def tearDown(self):
        if hasattr(self,'temp'):self.temp.cleanup()

    def raster(self,path,values,nodata,resolution=30):
        size=int(360/resolution)
        ds=self.gdal.GetDriverByName('GTiff').Create(str(path),size,size,len(values),self.gdal.GDT_UInt16)
        ds.SetGeoTransform((300000,resolution,0,9480000,0,-resolution));ds.SetProjection(self.crs.ExportToWkt())
        for i,value in enumerate(values,1):
            band=ds.GetRasterBand(i);band.SetNoDataValue(nodata);band.WriteArray(np.full((size,size),value,dtype='uint16'))
        ds=None

    def test_real_pixels_quality_and_partial_coverage(self):
        from usgs_catalogo_qgis.prodes_auto import sample_polygon
        result=sample_polygon(self.wkt,self.images)
        self.assertEqual(result['common_pixels'],144)
        self.assertTrue(result['qa_complete'])
        self.assertEqual(decide(ITEM,result,DATES,True)['status'],'Sinal compatível com perda de cobertura')
        self.raster(self.folder/'qa2022.tif',[8],0)
        self.assertEqual(sample_polygon(self.wkt,self.images)['common_pixels'],0)
        self.raster(self.folder/'qa2022.tif',[64],0)
        ds=self.gdal.Open(self.images[0]['path'],self.gdal.GA_Update)
        band=ds.GetRasterBand(1);data=band.ReadAsArray();data[:4,:]=0;band.WriteArray(data);ds=None
        result=sample_polygon(self.wkt,self.images)
        self.assertAlmostEqual(result['common_coverage'],2/3)
        self.assertEqual(decide(ITEM,result,DATES,True)['status'],'Inconclusivo')

    def test_coarsest_resolution_and_missing_saturation(self):
        from usgs_catalogo_qgis.prodes_auto import sample_polygon
        self.raster(self.folder/'2020.tif',[14545,29091,10909],0,60)
        result=sample_polygon(self.wkt,self.images)
        self.assertEqual(result['resolution_m'],60)
        self.assertEqual(result['common_pixels'],36)
        (self.folder/'sat2020.tif').unlink()
        self.assertFalse(sample_polygon(self.wkt,self.images)['qa_complete'])

    def test_saturation_and_cancel(self):
        from usgs_catalogo_qgis.prodes_auto import sample_polygon
        self.raster(self.folder/'sat2021.tif',[1],65535)
        self.assertEqual(sample_polygon(self.wkt,self.images)['common_pixels'],0)
        with self.assertRaises(ProdesError):sample_polygon(self.wkt,self.images,lambda:True)

    def test_real_auxiliary_cache_preserves_zero_saturation(self):
        from unittest.mock import patch
        from usgs_catalogo_qgis.stac import PublicCatalog
        from usgs_catalogo_qgis.prodes_auto import sample_polygon
        client=PublicCatalog();sat=str(self.folder/'sat2020.tif')
        item={'id':'fixture','collection':'landsat-c2-l2','assets':{
            'qa_radsat':{'href':'https://fixture.blob.core.windows.net/data/sat.tif','roles':['data']}}}
        client.signed_url=lambda href:sat
        original=self.gdal.Warp
        def local_warp(destination,source,**kwargs):
            return original(destination,source.removeprefix('/vsicurl/'),**kwargs)
        geom=self.ogr.CreateGeometryFromWkt(self.wkt)
        a,b,c,d=geom.GetEnvelope()
        with patch.object(self.gdal,'Warp',local_warp):
            files,errors=client.cache_bands(item,str(self.folder/'cached'),(a,c,b,d),'EPSG:32722',lambda text:None,
                ['qa_radsat'],include_auxiliary=True)
        self.assertEqual(errors,[])
        ds=self.gdal.Open(files['qa_radsat']);self.assertEqual(ds.GetRasterBand(1).GetNoDataValue(),65535)
        self.assertGreater(int((ds.ReadAsArray()==0).sum()),0);ds=None
        self.images[2]['metadata']['saturation_path']=files['qa_radsat']
        self.assertEqual(sample_polygon(self.wkt,self.images)['common_pixels'],144)
