import json
import tempfile
import unittest
from pathlib import Path
from usgs_catalogo_qgis.prodes_agent import Audit,verify_events,append_event,refinement_targets,dossier,run_investigation,visual_scene_order
from usgs_catalogo_qgis.prodes import ProdesError

class AgentTests(unittest.TestCase):
    def test_audit_survives_and_detects_modification_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            audit=Audit(folder,{'year':2022});audit.event('scene',{'id':'a'});audit.checkpoint('done')
            receipt=audit.receipt();append_event(receipt,'maps',{'count':2})
            path=Path(receipt['directory'])/'events.jsonl'
            self.assertTrue(verify_events(path))
            self.assertEqual(receipt['events'],2)
            original=path.read_text();path.write_text(original.replace('"count": 2','"count": 3'))
            self.assertFalse(verify_events(path));path.write_text(original.splitlines()[0]+'\n')
            with self.assertRaises(ProdesError):append_event(receipt,'extra',{})
    def test_refinement_is_inside_interval_and_same_season_for_missing_year(self):
        history={'pairs':[{'before':'2005-07-27','after':'2009-07-27','usable':True,'loss':True,'gap_days':1461}]}
        targets=refinement_targets(history);self.assertEqual(targets[0]['date'],'2007-07-27')
        self.assertFalse(refinement_targets(history,[targets[0]['date']]))
    def test_unusable_pairs_do_not_drive_refinement(self):
        self.assertFalse(refinement_targets({'pairs':[{'before':'2000-01-01','after':'2010-01-01','usable':False}]}))
    def test_dossier_does_not_turn_documentary_overlap_into_temporal_proof(self):
        item={'year':2022,'clip_ha':10,'consolidated_ha':.1}
        result={'history':{'observations':[],'pairs':[],'missing_years':[2022]}}
        report=dossier(item,result,[])
        self.assertTrue(all(h['status']=='Não demonstrada neste processamento' for h in report['hypotheses'][:4]))
        self.assertEqual(report['adequacy'],'Amostra insuficiente')
        self.assertTrue(any('0.1000' in q for q in report['questions']))
        self.assertTrue(any(r['id']=='LAW_CONSOLIDATED' for r in report['references']))
    def test_visual_order_keeps_actual_event_pair(self):
        row={'year':2022,'history':{'first_observed_loss':{'before_scene':'old','after_scene':'loss'},
              'observations':[{'date':'2022-07-01','scene_id':'recent','usable':True}]}}
        self.assertEqual(visual_scene_order(row),['old','loss','recent'])
    def test_controller_calls_real_fetcher_with_agent_and_persists_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            payload={'archive_root':folder,'rows':[{'year':2022,'uuid':'a'}]}
            def fetch(p,*args,**kwargs):
                self.assertTrue(p['agent_enabled']);kwargs['audit']('network',{'offline':True})
                return {'payload':p,'results':[{'history':{'observations':[],'pairs':[]}}]}
            result=run_investigation(payload,fetcher=fetch)
            self.assertIn('agent',result['results'][0])
            self.assertTrue(verify_events(Path(result['payload']['investigation']['directory'])/'events.jsonl'))
            def fail(*args,**kwargs):raise ValueError('offline')
            with self.assertRaises(ValueError):run_investigation(payload,fetcher=fail)
            states=[json.loads(p.read_text())['status'] for p in Path(folder).glob('investigacoes/*/session.json')]
            self.assertIn('falhou',states)

    def test_inserted_off_season_image_does_not_destroy_comparable_pair(self):
        import numpy as np
        from usgs_catalogo_qgis.prodes_history import summarise_timeline
        images=[{'date':d,'scene_id':d,'metadata':{'platform':'landsat-8','collection':'landsat-c2-l2'}} for d in ['2018-07-01','2019-01-01','2019-07-01']]
        inside=np.ones((10,10),bool)
        indices=[(np.full((10,10),v),np.full((10,10),v)) for v in [.7,.7,.1]]
        result=summarise_timeline(images,indices,[inside]*3,inside,[True]*3,[np.full((10,10),.4)]*3,[None]*3,30)
        self.assertTrue(any(p['before']=='2018-07-01' and p['after']=='2019-07-01' and p['loss'] for p in result['pairs']))
