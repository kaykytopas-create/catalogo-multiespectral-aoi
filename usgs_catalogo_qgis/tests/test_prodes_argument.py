import copy
import json
import unittest
from usgs_catalogo_qgis.prodes_argument import argumentation, attach_argumentation
from usgs_catalogo_qgis.prodes_report import readable_report

class ArgumentTests(unittest.TestCase):
    def row(self):
        return {'year':2022,'uuid':'unique','clip_ha':13.7379,'consolidated_ha':.1096,
                'contestability':{'status':'Passível de contestação (triagem)',
                    'action':'Investigar sobreposição com consolidada técnica','reason':'Classificação fornecida pelo técnico.'},
                'history':{'observations':[], 'searched_years':[2020,2021,2022,2023,2024],
                    'missing_years':[2020,2021,2022,2023,2024],'opening':'Não localizado','fire':'Não conclusivo'}}
    def text(self,row):return ' '.join(t for _,t in argumentation(row))
    def test_small_overlap_does_not_support_whole_polygon(self):
        row=self.row();before=copy.deepcopy(row);text=self.text(row)
        self.assertIn('0,1096 ha',text);self.assertIn('0,8%',text)
        self.assertIn('13,6283 ha',text)
        self.assertIn('indicação é documental',text)
        self.assertEqual(row,before)
    def test_green_pre_cutoff_is_not_claimed_as_proof_of_consolidation(self):
        row=self.row();row['history']['observations']=[{'date':'2007-08-11','usable':True,'pixels':150,'coverage':.99,'ndvi':.826,'ndmi':.315}]
        self.assertIn('não é uma comprovação de solo aberto',self.text(row))
        self.assertIn('não refuta, isoladamente, pastagem',self.text(row))
    def test_full_coverage_two_pixels_remains_insufficient(self):
        row=self.row();row['history']['observations']=[{'date':'2022-07-27','usable':False,'pixels':2,'coverage':1}]
        text=self.text(row);self.assertIn('Nenhuma imagem forneceu',text)
        self.assertIn('maior amostra teve 2 pixels',text)
    def test_interval_crossing_cutoff_does_not_date_legal_consolidation(self):
        row=self.row();row['history']['first_observed_loss']={'before':'2007-08-11','after':'2009-07-01','changed_fraction':.8}
        text=self.text(row);self.assertIn('atravessa 22/07/2008',text)
        self.assertIn('não é correto escolher',text)
    def test_recovery_does_not_erase_historical_loss(self):
        row=self.row();row['history']['burn_event']={'before':'2021-07-01','after':'2022-07-01','dnbr':.4,'recovery':True,'recovery_date':'2024-07-01'}
        text=self.text(row);self.assertIn('0,400',text);self.assertIn('nem apaga uma supressão',text)
    def test_manual_no_history_does_not_invent_dates(self):
        row=self.row();row.pop('history');text=self.text(row)
        self.assertIn('histórico automático anterior e posterior não foi pesquisado',text)
        self.assertNotIn('primeira observação utilizável',text)
    def test_source_diagnostics_do_not_call_small_clip_wrong_mapping(self):
        row=self.row();row['contestability'].update(status='Evidências insuficientes',reason='O polígono ORIGINAL é menor que 6,25 ha.')
        self.assertIn('não comprova que o desenho',self.text(row))
    def test_html_escapes_documentary_input_and_preserves_verdict(self):
        row=self.row();row['uuid']='<script>alert(1)</script>';before=copy.deepcopy(row)
        text=readable_report({},[row])
        self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)
        self.assertEqual(row,before);self.assertIn('Como transformar a análise',text)

    def test_analysis_persists_expanded_reason_and_preserves_status_scope(self):
        row=self.row();result=copy.deepcopy(row)
        status=result['contestability']['status'];result['contestability']['scope_ha']=.1096
        attach_argumentation(row,result)
        self.assertEqual(result['contestability']['status'],status)
        self.assertEqual(result['contestability']['scope_ha'],.1096)
        self.assertIn('indicação é documental',result['contestability']['reason'])
        self.assertEqual(result['contestability']['rule_reason'],'Classificação fornecida pelo técnico.')
        json.dumps(result)
        first=copy.deepcopy(result);attach_argumentation(row,result)
        self.assertEqual(first,result)
    def test_report_uses_persisted_engine_argumentation(self):
        row=self.row();attach_argumentation(row,row)
        row['argumentation']['sections'][0]['text']='Argumento persistido pelo motor de análise.'
        text=readable_report({},[row]);self.assertIn('Argumento persistido pelo motor',text)

class ReviewDirectionsTests(unittest.TestCase):
    def test_case_names_and_claims_from_reference_are_not_copied(self):
        row=ArgumentTests().row();text=ArgumentTests().text(row)
        self.assertIn('Revisão temporal e correspondência com o evento',[title for title,_ in argumentation(row)])
        self.assertNotIn('Flor do Líbano',text);self.assertNotIn('69,02',text)
        self.assertIn('não classificou automaticamente floresta primária',text)
        self.assertNotIn('Minuta para',text)
    def test_older_interval_is_conditional_and_partial_scope_preserved(self):
        from usgs_catalogo_qgis.prodes_argument import review_directions
        row=ArgumentTests().row();row['history']['first_observed_loss']={'before':'2005-01-01','after':'2007-01-01'}
        value=review_directions(row);self.assertIn('pista para investigar',value[0]['text']);self.assertIn('máscara acumulada',value[0]['text'])
        self.assertIn('13,6283 ha',value[2]['text']);self.assertIn('Não deslocar',value[2]['text'])
    def test_no_evidence_is_not_a_positive_contestation(self):
        from usgs_catalogo_qgis.prodes_argument import review_directions
        row=ArgumentTests().row();row['contestability']['status']='Evidências insuficientes'
        directions=review_directions(row)
        self.assertIn('não confirma nem refuta',directions[-1]['text'])
        self.assertIn('Não propor outra data',directions[0]['text'])
    def test_reference_inside_interval_is_not_redating_proof(self):
        from usgs_catalogo_qgis.prodes_argument import review_directions
        row=ArgumentTests().row();row['image_date']='2022-06-01';row['history']['first_observed_loss']={'before':'2021-06-01','after':'2022-07-01'}
        self.assertIn('não demonstra erro',review_directions(row)[0]['text'])
    def test_engine_persists_review_axes_without_changing_verdict(self):
        row=ArgumentTests().row();old=row['contestability']['status'];attach_argumentation(row,row)
        self.assertEqual(row['contestability']['status'],old)
        self.assertEqual([d['axis'] for d in row['argumentation']['review_directions']],['temporal','thematic','spatial','next_step'])
