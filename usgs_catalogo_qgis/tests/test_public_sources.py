# SPDX-License-Identifier: GPL-2.0-or-later
import copy
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from usgs_catalogo_qgis.public_sources import MultiCatalog, normalize_inpe, merge_scenes, SearchResults
from usgs_catalogo_qgis.stac import CatalogError, natural_rgb_keys, default_rgb_keys, ndvi_keys, preview_url
from usgs_catalogo_qgis.archive import LocalArchive
from usgs_catalogo_qgis.tests import test_archive

RECT=(-50,-7,-49,-6)
INPE='https://data.inpe.br/bdc/data/landsat/v2/223/064/2000/'
PC='https://landsateuwest.blob.core.windows.net/landsat-c2/'

def scene(host=INPE, collection='landsat-2', identifier='LT05_L2SP_223064_20000101_20200901_02_T1', cloud=0):
    return {'id':identifier,'collection':collection,'properties':{'datetime':'2000-01-01T00:00:00Z','eo:cloud_cover':cloud},
            'assets':{key:{'href':host+key+'.TIF'} for key in ('red','green','blue','nir08','swir16','swir22','qa_pixel','qa_radsat')}}

def response(items=(), links=()):
    return {'type':'FeatureCollection','features':list(items),'links':list(links)}

class PublicSourceTests(unittest.TestCase):
    def test_sensor_bands_calibration_and_original_collection(self):
        for prefix in ('LT04','LT05','LE07','LC08','LC09'):
            raw=scene(identifier=prefix+'_L2SP_223064_20000101_20200901_02_T1')
            item=normalize_inpe(raw)
            self.assertEqual(item['collection'],'landsat-c2-l2')
            self.assertEqual(raw['collection'],'landsat-2')
            self.assertEqual(natural_rgb_keys(item),('red','green','blue'))
            self.assertEqual(default_rgb_keys(item),('swir16','nir08','red'))
            self.assertEqual(ndvi_keys(item),('nir08','red'))
            self.assertEqual(item['assets']['red']['raster:bands'][0]['scale'],.0000275)
        for raw in (scene(collection='LANDSAT-16D-1'),scene(identifier='MSS_unknown')):
            with self.assertRaises(CatalogError):normalize_inpe(raw)

    def test_public_inpe_asset_no_token_and_url_restrictions(self):
        client=MultiCatalog();client.json_request=lambda *a: self.fail('No token request needed')
        self.assertEqual(client.signed_url(INPE+'red.TIF'),INPE+'red.TIF')
        for href in (INPE.replace('https:','http:')+'red.TIF',INPE.replace('data.inpe.br','user@data.inpe.br')+'red.TIF',
                     'https://data.inpe.br/private/red.TIF',INPE+'red.TIF?token=test',INPE.replace('data.inpe.br','data.inpe.br:bad')+'red.TIF'):
            with self.assertRaises(CatalogError):client.signed_url(href)

    def test_federation_merges_same_product_and_keeps_mirror(self):
        calls=[];client=MultiCatalog()
        pc=normalize_inpe(scene(PC));pc['catalog:sources']=['Microsoft Planetary Computer']
        def request(url,payload=None):
            calls.append((url,payload))
            return response([scene()]) if 'data.inpe.br' in url else response([pc])
        client.json_request=request
        items,nxt=client.search(['landsat-c2-l2'],RECT,'2000-01-01','2000-12-31')
        self.assertIsNone(nxt);self.assertEqual(len(items),1);self.assertEqual(len(items[0]['catalog:sources']),2)
        self.assertEqual(items[0]['assets']['red']['catalog:alternate_hrefs'],[INPE+'red.TIF'])
        query=parse_qs(urlparse(calls[1][0]).query)
        self.assertEqual(query['collections'],['landsat-2'])
        self.assertNotIn('query',query)  # INPE rejects the STAC query extension; filtered locally.
        self.assertEqual(query['bbox'],['-50,-7,-49,-6'])

    def test_pagination_only_continues_unfinished_source(self):
        calls=[];client=MultiCatalog();nxt={'rel':'next','href':'https://data.inpe.br/bdc/stac/v1/search?token=next'}
        def request(url,payload=None):
            calls.append(url)
            if 'data.inpe.br' not in url:return response()
            return response([scene(identifier='LT05_other')]) if 'token=next' in url else response([scene()], [nxt])
        client.json_request=request
        first,token=client.search(['landsat-c2-l2'],RECT,'2000-01-01','2000-12-31')
        second,end=client.search(['landsat-c2-l2'],RECT,'2000-01-01','2000-12-31',token)
        self.assertEqual(len(calls),3);self.assertIsNone(end);self.assertNotEqual(first[0]['id'],second[0]['id'])

    def test_failed_source_warns_without_discarding_other(self):
        client=MultiCatalog()
        def request(url,payload=None):
            if 'data.inpe.br' not in url:raise CatalogError('offline PC')
            return response([scene()])
        client.json_request=request
        items,nxt=client.search(['landsat-c2-l2'],RECT,'2000-01-01','2000-12-31')
        self.assertEqual(len(items),1);self.assertIn('offline PC',items.warnings[0])
        client.json_request=lambda *a: (_ for _ in ()).throw(CatalogError('offline both'))
        with self.assertRaises(CatalogError):client.search(['landsat-c2-l2'],RECT,'2000-01-01','2000-12-31')

    def test_sentinel_search_does_not_query_inpe(self):
        calls=[];client=MultiCatalog();client.json_request=lambda url,payload=None:(calls.append(url) or response())
        client.search(['sentinel-2-l2a'],RECT,'2020-01-01','2020-12-31')
        self.assertEqual(len(calls),1);self.assertNotIn('data.inpe.br',calls[0])

    def test_cloud_unknown_and_twenty_excluded_and_bad_next_rejected(self):
        client=MultiCatalog();client.json_request=lambda *a:response([scene(cloud=c) for c in (0,19.9,20,None)])
        items,_=client.search_inpe(RECT,'2000-01-01','2000-12-31');self.assertEqual(len(items),2)
        for link in ({'href':'https://evil.test/search'}, {'href':'https://data.inpe.br/bdc/stac/v1/search','method':'POST'}):
            with self.assertRaises(CatalogError):client.search_inpe(RECT,'2000-01-01','2000-12-31',link)

    def test_failed_band_uses_mirror_and_records_source(self):
        item=normalize_inpe(scene(PC));item['assets']['red']['catalog:alternate_hrefs']=[INPE+'red.TIF']
        warps=[];gdal=test_archive.ArchiveTests().fake_gdal(warps,[]);original=gdal.Warp
        def warp(path,source,options):
            if 'blob.core' in source:
                warps.append(source);raise RuntimeError('primary unavailable')
            return original(path,source,options)
        gdal.Warp=warp;client=MultiCatalog();client.signed_url=lambda href:href
        with tempfile.TemporaryDirectory() as folder,patch.dict(sys.modules,{'osgeo':types.SimpleNamespace(gdal=gdal)}):
            files,errors=client.cache_bands(item,folder,RECT,'EPSG:31982',lambda _:None,['red'])
            self.assertEqual(errors,[]);self.assertTrue(os.path.isfile(files['red']));self.assertEqual(len(warps),2)
            self.assertEqual(item['catalog:download_sources']['red'],'data.inpe.br')
            self.assertFalse(os.path.exists(files['red']+'.part.tif'))

    def test_archive_retains_mirror_and_actual_download_across_updates(self):
        item=normalize_inpe(scene(PC));item['catalog:sources']=['Microsoft Planetary Computer']
        other=normalize_inpe(scene());other['catalog:download_sources']={'red':'data.inpe.br'}
        with tempfile.TemporaryDirectory() as folder:
            archive=LocalArchive(folder,RECT,'EPSG:31982');archive.remember(item);archive.remember(other);archive.remember_many([item])
            stored=archive.search(['landsat-c2-l2'],'2000-01-01','2000-12-31')
            self.assertEqual(len(stored),1);self.assertEqual(len(stored[0]['catalog:sources']),2)
            self.assertEqual(stored[0]['catalog:download_sources']['red'],'data.inpe.br')
            self.assertEqual(stored[0]['assets']['red']['catalog:alternate_hrefs'],[INPE+'red.TIF'])

    def test_thumbnail_is_inpe_only_and_not_spectral_data(self):
        item=normalize_inpe(scene());item['assets']['thumb_large.jpeg']={'href':INPE+'thumb_large.jpeg'}
        self.assertEqual(preview_url(item,560),INPE+'thumb_large.jpeg')
        self.assertEqual(natural_rgb_keys(item),('red','green','blue'))
        item['assets']['thumb_large.jpeg']['href']='https://evil.test/preview.jpeg'
        self.assertNotEqual(preview_url(item,560),'https://evil.test/preview.jpeg')

if __name__=='__main__':unittest.main()
