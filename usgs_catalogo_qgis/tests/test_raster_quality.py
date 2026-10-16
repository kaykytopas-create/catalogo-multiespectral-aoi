# SPDX-License-Identifier: GPL-2.0-or-later
import tempfile,unittest
from pathlib import Path
try:
 from osgeo import gdal,osr
 import numpy as np
 NATIVE=True
except ImportError:NATIVE=False
from usgs_catalogo_qgis.raster_quality import inspect_raster

@unittest.skipUnless(NATIVE,'GDAL necessário')
class RasterQualityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.path=str(Path(self.temp.name)/'image.tif')
  ds=gdal.GetDriverByName('GTiff').Create(self.path,20,20,3,gdal.GDT_UInt16)
  ds.SetGeoTransform((-50,.001,0,-4.98,0,-.001));srs=osr.SpatialReference();srs.ImportFromEPSG(4326);ds.SetProjection(srs.ExportToWkt())
  for i in range(1,4):
   arr=np.full((20,20),1000,np.uint16)
   if i==3:arr[:5,:]=0
   ds.GetRasterBand(i).WriteArray(arr);ds.GetRasterBand(i).SetNoDataValue(0)
  ds=None
 def test_missing_band_pixels_are_not_ignored(self):
  self.assertEqual(inspect_raster(self.path)['valid_fraction'],.75)
 def test_nodata_outside_property_not_counted(self):
  value=inspect_raster(self.path,'POLYGON((-50 -5,-49.98 -5,-49.98 -4.99,-50 -4.99,-50 -5))')
  self.assertEqual(value['valid_fraction'],1)
 def test_outside_area_insufficient_not_complete(self):
  value=inspect_raster(self.path,'POLYGON((-40 -5,-39.98 -5,-39.98 -4.99,-40 -4.99,-40 -5))')
  self.assertEqual(value['status'],'insufficient_sample');self.assertIsNone(value['valid_fraction'])
 def test_original_raster_not_modified(self):
  before=Path(self.path).read_bytes();inspect_raster(self.path);self.assertEqual(before,Path(self.path).read_bytes())
