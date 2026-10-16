# SPDX-License-Identifier: GPL-2.0-or-later
import unittest,tempfile
from pathlib import Path
from usgs_catalogo_qgis.catalog_quality import natural_limits,quality_allowed,inspect_qa
from usgs_catalogo_qgis.tests.test_commands import scene
try:
 from osgeo import gdal,osr
 import numpy as np
 NATIVE=True
except ImportError:NATIVE=False

class NaturalLimitsTests(unittest.TestCase):
 def test_common_physical_interval_preserves_neutral_cloud(self):
  item=scene('2006-01-01',0,platform='landsat-5');limits=natural_limits(item,['red','green','blue'])
  for low,high in limits.values():
   self.assertAlmostEqual(low*.0000275-.2,0)
   self.assertAlmostEqual(high*.0000275-.2,.3)
  self.assertEqual(limits['1'],limits['2']);self.assertEqual(limits['2'],limits['3'])
 def test_false_color_not_changed(self):
  self.assertIsNone(natural_limits(scene('2006-01-01'),['swir16','nir08','red']))
 def test_local_quality_thresholds(self):
  p={'cloud_max':0,'cloud_strict':False}
  self.assertTrue(quality_allowed({'valid_fraction':1,'clear_fraction':1,'cloud_percent':0},p))
  self.assertFalse(quality_allowed({'valid_fraction':1,'clear_fraction':.99,'cloud_percent':.01},p))
  self.assertFalse(quality_allowed({'valid_fraction':.8,'clear_fraction':.8,'cloud_percent':0},p))

@unittest.skipUnless(NATIVE,'GDAL necessário')
class LocalQATests(unittest.TestCase):
 def test_cloud_in_property_not_hidden_by_scene_metadata(self):
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'qa.tif');ds=gdal.GetDriverByName('GTiff').Create(path,20,20,1,gdal.GDT_UInt16)
   ds.SetGeoTransform((-50,.001,0,-4.98,0,-.001));srs=osr.SpatialReference();srs.ImportFromEPSG(4326);ds.SetProjection(srs.ExportToWkt())
   arr=np.full((20,20),64,np.uint16);arr[:5,:]=8;ds.GetRasterBand(1).WriteArray(arr);ds=None
   all_area=inspect_qa(path,'landsat',None);self.assertEqual(all_area['cloud_percent'],25);self.assertEqual(all_area['clear_fraction'],.75)
   clear=inspect_qa(path,'landsat','POLYGON((-50 -5,-49.98 -5,-49.98 -4.99,-50 -4.99,-50 -5))')
   self.assertEqual(clear['cloud_percent'],0);self.assertEqual(clear['clear_fraction'],1)
 def test_zero_fill_and_cloud_shadow_are_unusable(self):
  with tempfile.TemporaryDirectory() as folder:
   path=str(Path(folder)/'qa.tif');ds=gdal.GetDriverByName('GTiff').Create(path,4,1,1,gdal.GDT_UInt16)
   ds.SetGeoTransform((-50,.001,0,-5,0,-.001));srs=osr.SpatialReference();srs.ImportFromEPSG(4326);ds.SetProjection(srs.ExportToWkt())
   ds.GetRasterBand(1).WriteArray(np.array([[0,1,16,64]],np.uint16));ds=None
   q=inspect_qa(path,'landsat',None);self.assertEqual(q['valid_fraction'],.5);self.assertEqual(q['clear_fraction'],.25)
