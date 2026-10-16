# SPDX-License-Identifier: GPL-2.0-or-later
import unittest
import numpy as np
from datetime import date
from usgs_catalogo_qgis.prodes_history import summarise_timeline, interpret_history
from usgs_catalogo_qgis.prodes_auto import spectral_indices
from usgs_catalogo_qgis.prodes_report import readable_report
from usgs_catalogo_qgis.prodes import record

ITEM={'year':2020,'uuid':'test','clip_ha':10,'consolidated_ha':2,'original_ha':20,'core_ha':10}
BASE={'status':'Evidências insuficientes','scope_ha':0,'reason':'fixture'}


def timeline(years,cover,platforms=None,masks=None,qa=None,nbr_available=True):
    # Explicit calibrated reflectance; same pixel locations.
    values={'green':[.2,.6,.1,.1], 'low':[.3,.3,.25,.4]}
    images=[];indices=[];nir=[];nbr=[]
    for index,(year,state) in enumerate(zip(years,cover)):
        swir,n,r,swir2=values[state]
        arr=np.stack([np.full((10,10),v,dtype='float32') for v in (swir,n,r)])
        vi,mi,valid=spectral_indices(arr);indices.append((vi,mi));nir.append(arr[1])
        nbr.append(np.full((10,10),(n-swir2)/(n+swir2),dtype='float32') if nbr_available else None)
        images.append({'date':f'{year}-07-01','scene_id':f'scene{year}','metadata':{'collection':'landsat-c2-l2','platform':platforms[index] if platforms else 'landsat-8'}})
    return summarise_timeline(images,indices,masks or [np.ones((10,10),bool)]*len(images),np.ones((10,10),bool),qa or [True]*len(images),nir,nbr,30)


class HistoryTests(unittest.TestCase):
    def test_earlier_loss_is_interval_candidate_not_exact_first_clearance(self):
        value=timeline([2004,2005,2019,2020,2021],['green','low','low','low','low'])
        result=interpret_history(ITEM,value,list(range(2004,2022)),BASE)
        self.assertEqual(result['recommendation']['action'],'Solicitar revisão da data, condicionada à conferência técnica')
        self.assertIn('2004-07-01',result['opening']);self.assertIn('2005-07-01',result['opening'])
        self.assertIn('Não comprova a primeira abertura',result['opening'])
        self.assertTrue(result['missing_years'])

    def test_first_image_already_low_does_not_invent_opening_year(self):
        result=interpret_history(ITEM,timeline([2005,2019,2020],['low']*3),[2005,2019,2020],BASE,technical=True)
        self.assertEqual(result['already_low_at'],'2005-07-01')
        self.assertNotIn('first_observed_loss',result)
        self.assertEqual(result['recommendation']['scope_ha'],2)

    def test_repeated_loss_cannot_be_reassigned_to_first_spectral_drop(self):
        result=interpret_history(ITEM,timeline([2004,2005,2018,2019,2020],['green','low','green','green','low']),[2004,2005,2018,2019,2020],BASE)
        self.assertEqual(result['recommendation']['status'],'Evidências insuficientes')
        self.assertIn('novo evento',result['recommendation']['action'])

    def test_burn_and_recovery_do_not_prove_false_prodes(self):
        result=interpret_history(ITEM,timeline([2019,2020,2021],['green','low','green']),[2019,2020,2021],BASE)
        self.assertTrue(result['burn_event']['recovery'])
        self.assertEqual(result['recommendation']['status'],'Evidências insuficientes')
        self.assertIn('autoria não são comprovadas',result['fire'])
        self.assertIn('nem justifica excluir',result['fire'])

    def test_nbr_missing_cannot_assert_fire(self):
        result=interpret_history(ITEM,timeline([2019,2020,2021],['green','low','low'],nbr_available=False),[2019,2020,2021],BASE)
        self.assertNotIn('burn_event',result)
        self.assertFalse(result['pairs'][0]['burn_signal'])

    def test_quality_and_mixed_platform_prevent_false_change(self):
        for args in ({'platforms':['landsat-5','landsat-8']},{'qa':[True,False]}):
            value=timeline([2004,2005],['green','low'],**args)
            self.assertFalse(any(p['loss'] for p in value['pairs']))

    def test_disjoint_valid_pixels_prevent_false_pair_and_recovery(self):
        a=np.zeros((10,10),bool);a[:8,:]=True
        b=np.zeros((10,10),bool);b[2:,:]=True
        value=timeline([2019,2020,2021],['green','low','green'],masks=[a,b,a])
        self.assertTrue(all(o['usable'] for o in value['observations']))
        self.assertFalse(any(p['loss'] or p['recovery'] for p in value['pairs']))

    def test_minimum_area_uses_original_not_clip(self):
        value=timeline([2004,2005],['green','low'])
        good=interpret_history(dict(ITEM,clip_ha=.1),value,[2004,2005],BASE,amazon_forest=True)
        self.assertEqual(good['recommendation']['status'],'Passível de contestação (triagem)')
        bad=interpret_history(dict(ITEM,original_ha=1),value,[2004,2005],BASE,amazon_forest=True)
        self.assertEqual(bad['recommendation']['status'],'Evidências insuficientes')
        self.assertIn('ORIGINAL',bad['recommendation']['reason'])

    def test_readable_report_explains_gaps_and_escapes_without_python_repr(self):
        history=interpret_history(ITEM,timeline([2019,2020],['green','low']),[2018,2019,2020],BASE)
        row=dict(ITEM,history=history,contestability=history['recommendation'],notes='<script>',user_review='Discordo')
        text=readable_report({'Imóvel':'<iframe>','Limiares experimentais próprios':{'false':False}},[row])
        self.assertIn('O que fazer',text);self.assertIn('Linha do tempo',text);self.assertIn('2018',text)
        self.assertNotIn('<script>',text);self.assertNotIn('<iframe>',text);self.assertNotIn('False',text)
        self.assertNotIn("{'false'",text);self.assertIn('Discordo',text)

    @unittest.skipUnless(__import__("importlib.util", fromlist=["find_spec"]).find_spec("qgis"), "QGIS unavailable")
    def test_dates_from_qgis_fields_are_normalized(self):
        from qgis.PyQt.QtCore import QDate
        for value in (QDate(2020,7,27),date(2020,7,27),'2020-07-27'):
            self.assertEqual(record({'class_name':'d2020','image_date':value})['image_date'],'2020-07-27')

    def test_later_loss_requires_observation_at_or_after_official_reference(self):
        series=timeline([2020,2021,2022],['green','low','low'],nbr_available=False)
        candidate=interpret_history(dict(ITEM,image_date='2020-07-01'),series,[2020,2021,2022],BASE)
        self.assertIn('posterior',candidate['recommendation']['action'])
        ambiguous=interpret_history(dict(ITEM,image_date='2020-08-01'),series,[2020,2021,2022],BASE)
        self.assertEqual(ambiguous['recommendation']['status'],'Evidências insuficientes')

    def test_old_recovered_burn_does_not_assign_first_clearance_date(self):
        series=timeline([2004,2005,2006,2019,2020],['green','low','green','green','green'])
        value=interpret_history(ITEM,series,[2004,2005,2006,2019,2020],BASE)
        self.assertEqual(value['recommendation']['status'],'Evidências insuficientes')
        self.assertNotIn('revisão da data',value['recommendation']['action'])
