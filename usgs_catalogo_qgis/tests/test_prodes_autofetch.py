# SPDX-License-Identifier: GPL-2.0-or-later
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
from usgs_catalogo_qgis.prodes_autofetch import run_autofetch, candidates, window
from usgs_catalogo_qgis.archive import LocalArchive
from usgs_catalogo_qgis.prodes import ProdesError


def scene(year, satellite='landsat-8', day='07-27', cloud=4, suffix=''):
    return {'id': str(year)+satellite+suffix, 'collection': 'landsat-c2-l2',
            'properties': {'datetime': str(year)+'-'+day+'T00:00:00Z', 'eo:cloud_cover':cloud,'platform':satellite},
            'assets': {k:{'href':'https://example.org/'+k+'.tif'} for k in ('swir16','nir08','red')}}


class Client:
    downloaded=[]
    options={}
    def __init__(self,cancelled=lambda:False):self.cancelled=cancelled
    def search(self,collections,rect,start,end,next_link=None):
        return self.options.get(int(start[:4]),[]),None
    def download_scene(self,item,folder,rect,crs,progress,keys):
        self.downloaded.append(item['id'])
        return [],[],folder+'/'+item['id']+'.vrt'


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        Client.downloaded=[];Client.options={y:[scene(y)] for y in (2022,2021,2020,2019,2007)}
        self.payload={'rows':[{'year':2022,'image_date':'2022-07-27','uuid':'one','clip_ha':4,'consolidated_ha':1}],
            'geometries':['g'], 'consolidated_geometries':['c'], 'parcel_geometry':'parcel',
            'archive_root':self.temp.name,'rect':[-49.84,-4.74,-49.82,-4.71],'target_crs':'EPSG:31982',
            'annual':True,'tolerance':False,'consolidated_technical':True,'consolidated_origin':'Técnico'}
        self.metadata=patch('usgs_catalogo_qgis.prodes_autofetch.scene_metadata',side_effect=lambda i,k,f:{'platform':i['properties']['platform'],'collection':i['collection'],'calibration_source':'fixture'})
        self.sample=patch('usgs_catalogo_qgis.prodes_autofetch.sample_polygon',return_value={'qa_complete':True,'common_coverage':1})
        self.analyse=patch('usgs_catalogo_qgis.prodes_autofetch.run_analysis',side_effect=lambda p,*a:[{'status':'fixture','dates':p['dates']} for row in p['rows']])
        for mock in (self.metadata,self.sample,self.analyse):mock.start();self.addCleanup(mock.stop)

    def test_acquires_three_dates_and_historical_without_project_rasters(self):
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertEqual(result['results'][0]['dates'],['2022-07-27','2021-07-27','2020-07-27'])
        self.assertEqual(result['payload']['historical_image']['date'],'2007-07-27')
        self.assertEqual(len(Client.downloaded),4)
        self.assertEqual(result['results'][0]['acquisition']['scene_ids'],[scene(y)['id'] for y in (2022,2021,2020)])

    def test_each_prodes_year_gets_own_series_and_reuses_shared_scene(self):
        self.payload['rows'].append(dict(self.payload['rows'][0],year=2021,image_date='2021-07-27',uuid='two'))
        self.payload['geometries'].append('g2');self.payload['consolidated_geometries'].append('c2')
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertEqual(result['results'][1]['dates'],['2021-07-27','2020-07-27','2019-07-27'])
        self.assertEqual(len(Client.downloaded),5)
        self.assertEqual(len(result['payload']['images']),5)

    def test_prefers_common_platform_over_mixed_newest_sensor(self):
        Client.options[2022]=[scene(2022,'landsat-9',cloud=0),scene(2022)]
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertTrue(all(i['metadata']['platform']=='landsat-8' for i in result['payload']['acquisition_groups'][0]['images']))
        self.assertNotIn(scene(2022,'landsat-9')['id'],Client.downloaded)

    def test_failed_quality_tries_next_scene_and_uses_local_coverage(self):
        Client.options[2022]=[scene(2022,suffix='cloudy'),scene(2022,suffix='clear')]
        self.sample.stop()
        self.sample=patch('usgs_catalogo_qgis.prodes_autofetch.sample_polygon',side_effect=lambda g,images,*a,**k:{'qa_complete':True,'common_coverage':.1 if 'cloudy' in images[0]['scene_id'] else 1})
        self.sample.start();self.addCleanup(self.sample.stop)
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertTrue(result['payload']['acquisition_groups'][0]['images'][0]['scene_id'].endswith('clear'))

    def test_cloud_twenty_rejected_and_missing_sequence_is_explicit(self):
        Client.options[2020]=[scene(2020,cloud=20)]
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertEqual(result['results'][0]['contestability']['status'],'Evidências insuficientes')
        self.assertIsNone(result['results'][0]['acquisition']['dates'][2])

    def test_network_failure_can_reuse_archive_items(self):
        archive=LocalArchive(self.temp.name,self.payload['rect'],self.payload['target_crs'])
        archive.remember_many([scene(2022)])
        class Offline(Client):
            def search(self,*a,**k):raise OSError('offline')
        warnings=[]
        values=candidates(Offline(),archive,2022,date(2022,7,27),lambda:False,warnings)
        self.assertEqual([v['id'] for v in values],[scene(2022)['id']]);self.assertTrue(warnings)

    def test_repeated_paging_is_bounded_and_deduplicated(self):
        class Repeat(Client):
            def search(self,*a,**k):return [scene(2022)],{'href':'same'}
        warnings=[];archive=LocalArchive(self.temp.name,self.payload['rect'],self.payload['target_crs'])
        values=candidates(Repeat(),archive,2022,date(2022,7,27),lambda:False,warnings)
        self.assertEqual(len(values),1);self.assertTrue(any('repetida' in w for w in warnings))

    def test_cancel_is_not_swallowed_as_offline(self):
        with self.assertRaises(ProdesError):run_autofetch(self.payload,cancelled=lambda:True,client_factory=Client)

    def test_requested_zero_cloud_is_not_relaxed_in_investigation(self):
        self.payload.update(agent_cloud_max=0,agent_cloud_strict=False)
        Client.options[2022]=[scene(2022,cloud=0)]
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertEqual(result['results'][0]['acquisition']['dates'][0],'2022-07-27')
        self.assertIsNone(result['results'][0]['acquisition']['dates'][1])
        self.assertEqual(Client.downloaded,[scene(2022,cloud=0)['id']])
        self.assertEqual(result['payload']['acquisition_policy']['requested_cloud_max'],0)

    def test_calendar_windows_do_not_cross_year_and_leap_anchor_valid(self):
        _,start,end=window(2021,date(2020,2,29))
        self.assertEqual(end,date(2021,3,30));self.assertEqual(start.year,2021)
        _,start,end=window(2021,date(2022,1,1));self.assertEqual(start,date(2021,1,1))

    def test_history_search_includes_years_after_record_and_prepares_nbr(self):
        self.payload['rows'][0].update(year=2020,image_date='2020-07-27')
        self.payload.update(history_enabled=True,history_start_year=2018)
        Client.options[2018]=[scene(2018)]
        class WithNBR(Client):
            products=[]
            def download_scene(self,item,*args,product='rgb',**kwargs):
                self.products.append(product)
                return [],[],self.__class__.__name__+'/'+item['id']+product+'.vrt'
        self.analyse.stop()
        self.analyse=patch('usgs_catalogo_qgis.prodes_autofetch.run_analysis',side_effect=lambda p,*a:[{'status':'Inconclusivo','contestability':{'status':'Evidências insuficientes','reason':'fixture','scope_ha':0}} for row in p['rows']])
        self.analyse.start();self.addCleanup(self.analyse.stop)
        self.sample.stop()
        def sample(g,images,*args,**kwargs):
            if kwargs.get('timeline'):
                return {'observations':[{'date':image['date'],'scene_id':image['scene_id'],'usable':True,'low_cover_fraction':0} for image in images],'pairs':[]}
            return {'qa_complete':True,'common_coverage':1}
        self.sample=patch('usgs_catalogo_qgis.prodes_autofetch.sample_polygon',side_effect=sample)
        self.sample.start();self.addCleanup(self.sample.stop)
        result=run_autofetch(self.payload,client_factory=WithNBR)
        history=result['results'][0]['history']
        self.assertEqual(history['searched_years'],[2018,2019,2020,2021,2022])
        self.assertFalse(history['missing_years'])
        self.assertIn('argumentation', result['results'][0])
        self.assertIn('Indicação documental', result['results'][0]['argumentation']['basis'])
        self.assertIn('rule_reason', result['results'][0]['contestability'])
        self.assertIn('nbr',WithNBR.products)
        self.assertTrue(any(image['date'].startswith('2022') for image in result['payload']['available_images']))

    def test_nbr_only_selected_candidate_not_discarded(self):
        self.payload.update(history_enabled=True, history_start_year=2020, agent_enabled=True, agent_profile='rapido')
        self.payload['consolidated_technical']=False
        Client.options[2022]=[scene(2022,suffix='bad'),scene(2022,suffix='good')]
        calls=[]
        class WithNBR(Client):
            def download_scene(self,item,*args,product='rgb',**kwargs):
                calls.append((item['id'],product));return [],[],item['id']+product+'.vrt'
        self.sample.stop()
        def sample(g,images,*args,**kwargs):
            if kwargs.get('timeline'):return {'observations':[],'pairs':[]}
            return {'qa_complete':True,'common_pixels':100,'common_coverage':.1 if 'bad' in images[0]['scene_id'] else 1}
        self.sample=patch('usgs_catalogo_qgis.prodes_autofetch.sample_polygon',side_effect=sample)
        self.sample.start();self.addCleanup(self.sample.stop)
        with patch('usgs_catalogo_qgis.prodes_autofetch.run_analysis',return_value=[{'status':'Inconclusivo','contestability':{'status':'Evidências insuficientes','reason':'fixture','scope_ha':0}}]):
            run_autofetch(self.payload,client_factory=WithNBR)
        self.assertIn((scene(2022,suffix='bad')['id'],'rgb'),calls)
        self.assertNotIn((scene(2022,suffix='bad')['id'],'nbr'),calls)
        self.assertIn((scene(2022,suffix='good')['id'],'nbr'),calls)

    def test_robot_scores_each_polygon_and_reuses_downloads(self):
        self.payload.update(agent_enabled=True,agent_profile='rapido')
        self.payload['rows'].append(dict(self.payload['rows'][0],uuid='two'))
        self.payload['geometries']=['g1','g2'];self.payload['consolidated_geometries']=['c1','c2']
        Client.options[2022]=[scene(2022,suffix='x'),scene(2022,suffix='y')]
        self.sample.stop()
        def quality(geometry,images,*args,**kwargs):
            selected=(geometry=='g1' and images[0]['scene_id'].endswith('y')) or (geometry=='g2' and images[0]['scene_id'].endswith('x'))
            return {'qa_complete':True,'common_coverage':1 if selected or not images[0]['date'].startswith('2022') else .2,'common_pixels':100}
        self.sample=patch('usgs_catalogo_qgis.prodes_autofetch.sample_polygon',side_effect=quality)
        self.sample.start();self.addCleanup(self.sample.stop)
        result=run_autofetch(self.payload,client_factory=Client)
        self.assertTrue(result['results'][0]['acquisition']['scene_ids'][0].endswith('y'))
        self.assertTrue(result['results'][1]['acquisition']['scene_ids'][0].endswith('x'))
        self.assertEqual(Client.downloaded.count(scene(2022,suffix='x')['id']),1)
        self.assertEqual(Client.downloaded.count(scene(2022,suffix='y')['id']),1)

    def test_offline_candidate_query_never_calls_network(self):
        archive=LocalArchive(self.temp.name,self.payload['rect'],self.payload['target_crs'])
        archive.remember_many([scene(2022)])
        class Never(Client):
            def search(self,*args):raise AssertionError('Network forbidden offline')
        values=candidates(Never(),archive,2022,date(2022,7,27),lambda:False,[],offline=True)
        self.assertEqual(len(values),1)
