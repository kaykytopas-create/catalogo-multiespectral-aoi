# SPDX-License-Identifier: GPL-2.0-or-later
import unittest, tempfile, json, os
from usgs_catalogo_qgis.commands import parse_command, select_scenes, collect_scenes, download_batch
from usgs_catalogo_qgis.archive import LocalArchive
from usgs_catalogo_qgis.stac import CatalogError


def scene(when,cloud=5,identifier=None,platform='landsat-8'):
    return {'id':identifier or when,'collection':'landsat-c2-l2','properties':{'datetime':when+'T00:00:00Z','eo:cloud_cover':cloud,'platform':platform},
            'assets':{k:{'href':'https://example.org/'+k+'.tif','eo:bands':[{'name':k}]} for k in ['red','green','blue','nir08','swir16','swir22']}}


class CommandsTests(unittest.TestCase):
    def test_fluent_download_import_exact_zero(self):
        p=parse_command('Quero que baixe e importe no QGIS uma imagem por ano de 2000 a 2008 com uma taxa de 0% de nuvens')
        self.assertTrue(p['auto_import']);self.assertEqual(p['cloud_max'],0);self.assertFalse(p['cloud_strict']);self.assertEqual(p['preset'],'prodes')
        self.assertEqual([x['id'] for x in select_scenes([scene('2000-01-01',0),scene('2001-01-01',.01)],p)],['2000-01-01'])
    def test_acervo_offline_is_destination_not_source(self):
        p=parse_command('Baixe imagens cor natural de 2000 a 2008 e salve no acervo offline')
        self.assertFalse(p['auto_import']);self.assertFalse(p['offline'])
    def test_do_not_import_negation(self):
        p=parse_command('Baixe imagens cor natural de 2000 a 2008, não quero importar no QGIS')
        self.assertFalse(p['auto_import'])
    def test_offline_source_explicit(self):
        p=parse_command('Importe no QGIS imagens cor natural de 2000 a 2008 usando somente o acervo local, sem internet')
        self.assertTrue(p['auto_import']);self.assertTrue(p['offline'])
    def test_cloud_comparators(self):
        p=parse_command('Baixe cor natural de 2000 a 2008 com menos de 5% de nuvens')
        self.assertTrue(p['cloud_strict']);self.assertEqual(select_scenes([scene('2000-01-01',5)],p),[])
        p=parse_command('Baixe cor natural de 2000 a 2008 com até 5% de nuvens')
        self.assertEqual(len(select_scenes([scene('2000-01-01',5)],p)),1)
    def test_invalid_cloud_not_silently_ignored(self):
        for text in ['Baixe cor natural de 2000 a 2008 menos de 0% de nuvens','Baixe cor natural de 2000 a 2008 com 30% de nuvens','Baixe cor natural de 2000 a 2008 com 0% e 5% de nuvens']:
            with self.assertRaises(CatalogError):parse_command(text)
    def test_investigate_year_and_cloud(self):
        p=parse_command('Investigue o PRODES de 2020 do meu imóvel e gere relatório com 0% de nuvens')
        self.assertEqual(p['action'],'investigate');self.assertEqual(p['year'],2020);self.assertEqual(p['cloud_max'],0)
    def test_download_notifications_only_successes(self):
        ready=[]
        class Client:
            def cancelled(self):return False
            def search(self,*a):return [scene('2000-01-01'),scene('2001-01-01')],None
            def download_scene(self,item,*args):
                if item['id'].startswith('2001'):raise OSError('fixture')
                return [],[],'fixture.vrt'
        with tempfile.TemporaryDirectory() as root:
            a=LocalArchive(root,[-50,-5,-49,-4],'EPSG:4326')
            result=download_batch(Client(),a,parse_command('Baixe e importe cor natural de 2000 a 2001'),lambda x:None,on_ready=ready.append)
            self.assertEqual(len(ready),1);self.assertEqual(ready[0]['result']['date'],'2000-01-01')
            self.assertEqual(result['receipt']['results'][1]['status'],'failed')

    def test_natural_period_default_annual_landsat(self):
        p=parse_command('Baixar imagens com banda de cor natural de 1985 até 2008',2026)
        self.assertEqual((p['action'],p['preset'],p['selection'],p['start']),('download','natural','annual','1985-01-01'))
    def test_1885_not_silently_changed(self):
        with self.assertRaisesRegex(CatalogError,'1985'):parse_command('baixar cor natural de 1885 ate 2008')
    def test_reversed_future_ambiguous_and_classification_rejected(self):
        for text in ['baixar cor natural de 2008 ate 1985','baixar cor natural de 2000 ate 2999','baixar cor natural PRODES de 1985 ate 2008','classificar k-means de 1985 ate 2008']:
            with self.assertRaises(CatalogError):parse_command(text)
    def test_investigation_profile(self):
        self.assertEqual(parse_command('Analisar PRODES e gerar relatório aprofundado offline')['profile'],'aprofundado')
    def test_mixed_task_rejected(self):
        with self.assertRaises(CatalogError):parse_command('baixar imagens prodes e analisar imóvel')
    def test_select_cloud_strict_deduplicate_date_best_year(self):
        p=parse_command('baixar cor natural de 2000 ate 2001')
        items=[scene('2000-07-02',7),scene('2000-08-01',3),scene('2001-07-02',20),scene('2001-07-03',4)]
        self.assertEqual([v['id'] for v in select_scenes(items,p)],['2000-08-01','2001-07-03'])
    def test_all_dates_dedup(self):
        p=parse_command('baixar NDVI de 2000 ate 2001 todas as datas')
        self.assertEqual(len(select_scenes([scene('2000-07-01',4,'a'),scene('2000-07-01',2,'b'),scene('2000-07-02')],p)),2)
    def test_slc_excluded_when_enabled(self):
        p=parse_command('baixar PRODES de 2004 ate 2005')
        self.assertEqual(select_scenes([scene('2004-07-01',1,platform='landsat-7')],p,True),[])
    def test_offline_no_search(self):
        with tempfile.TemporaryDirectory() as root:
            a=LocalArchive(root,[-50,-5,-49,-4],'EPSG:4326');a.remember_many([scene('2000-07-01')])
            class Client:
                def search(self,*a):raise AssertionError('network')
            p=parse_command('baixar cor natural de 2000 ate 2001 offline')
            self.assertEqual(len(collect_scenes(Client(),a,p,lambda x:None)),1)
    def test_pagination_cycle_rejected(self):
        class Client:
            def cancelled(self):return False
            def search(self,*a):return [scene('2000-07-01')],{'href':'repeat'}
        with tempfile.TemporaryDirectory() as root:
            a=LocalArchive(root,[-50,-5,-49,-4],'EPSG:4326')
            with self.assertRaisesRegex(CatalogError,'repetida'):collect_scenes(Client(),a,parse_command('baixar cor natural de 2000 ate 2001'),lambda x:None)
    def test_batch_failure_receipt_and_missing_years(self):
        class Client:
            def cancelled(self):return False
            def search(self,*a):return [scene('2000-07-01'),scene('2001-07-01')],None
            def download_scene(self,item,*args):
                if item['id'].startswith('2001'):raise OSError('fixture fail')
                return [],[],os.path.join(args[0],'rgb.vrt')
        with tempfile.TemporaryDirectory() as root:
            a=LocalArchive(root,[-50,-5,-49,-4],'EPSG:4326')
            value=download_batch(Client(),a,parse_command('baixar cor natural de 2000 ate 2002'),lambda x:None)
            self.assertEqual(value['missing_years'],[2001,2002])
            with open(value['manifest']) as f:receipt=json.load(f)
            self.assertEqual([v['status'] for v in receipt['results']],['completed','failed'])
            self.assertEqual(receipt['results'][0]['bands'],['red','green','blue'])


class CandidateFallbackTests(unittest.TestCase):
    def test_failed_best_scene_falls_back_same_year(self):
        class Client:
            def cancelled(self):return False
            def search(self,*a):return [scene('2000-01-01',0),scene('2000-07-01',1),scene('2001-01-01',0)],None
            def download_scene(self,item,*args):
                if item['id']=='2000-01-01':raise OSError('failed crop')
                return [],[],'fixture.vrt'
        with tempfile.TemporaryDirectory() as root:
            a=LocalArchive(root,[-50,-5,-49,-4],'EPSG:4326');ready=[]
            value=download_batch(Client(),a,parse_command('Baixe e importe cor natural de 2000 a 2001'),lambda x:None,on_ready=ready.append)
            self.assertEqual(value['missing_years'],[])
            self.assertEqual([x['result']['date'] for x in ready],['2000-07-01','2001-01-01'])
            self.assertEqual(len(value['receipt']['attempts']),1)
    def test_qa_rejection_keeps_zero_cloud_constraint(self):
        class Client:
            def cancelled(self):return False
            def search(self,*a):return [scene('2000-01-01',0)],None
            def assess_scene_quality(self,*a):return {'valid_fraction':1,'clear_fraction':.99,'cloud_percent':1}
            def download_scene(self,*a):raise AssertionError('cloudy image not downloaded')
        with tempfile.TemporaryDirectory() as root:
            a=LocalArchive(root,[-50,-5,-49,-4],'EPSG:4326')
            value=download_batch(Client(),a,parse_command('Baixe cor natural de 2000 a 2000 com 0% de nuvens'),lambda x:None)
            self.assertEqual(value['missing_years'],[2000]);self.assertEqual(value['scenes'],[])
            self.assertEqual(value['receipt']['attempts'][0]['status'],'rejected_quality')
