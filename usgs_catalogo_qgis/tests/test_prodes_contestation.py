# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
import unittest
from usgs_catalogo_qgis.prodes_contestation import historical_assessment,contestability
from usgs_catalogo_qgis.prodes import report_html
ITEM={'year':2022,'uuid':'synthetic','clip_ha':10,'consolidated_ha':2,'core_ha':5}
QUALITY={'common_pixels':20,'common_coverage':1,'qa_complete':True,'low_cover_fraction':.8}


class ContestationTests(unittest.TestCase):
    def test_name_or_theme_alone_is_not_technical_legal_evidence(self):
        spectral={'status':'Inconclusivo','reason':'sem histórico'}
        self.assertEqual(contestability(ITEM,spectral,annual=True)['status'],'Evidências insuficientes')
        result=contestability(ITEM,spectral,annual=True,technical=True)
        self.assertEqual(result['status'],'Passível de contestação (triagem)')
        self.assertEqual(result['scope_ha'],2)
        self.assertIn('classificação técnica fornecida',result['reason'])
        self.assertIn('não foi corroborada',result['reason'])

    def test_quality_cutoff_and_native_bare_ambiguity(self):
        good=historical_assessment(QUALITY,'2007-07-01')
        self.assertTrue(good['usable']);self.assertTrue(good['low_cover'])
        self.assertIn('também pode ocorrer naturalmente',good['reason'])
        for when in ('2008-07-22','2008-07-23','invalid'):
            self.assertFalse(historical_assessment(QUALITY,when)['usable'])
        for updates in ({'qa_complete':False},{'common_pixels':8},{'common_coverage':.79}):
            self.assertFalse(historical_assessment({**QUALITY,**updates},'2007-07-01')['usable'])
        low=historical_assessment({**QUALITY,'low_cover_fraction':.1},'2007-07-01')
        self.assertTrue(low['usable']);self.assertFalse(low['low_cover']);self.assertIn('pastagem verde',low['reason'])

    def test_historical_low_green_without_technical_input_not_contestation(self):
        history=historical_assessment(QUALITY,'2007-07-01')
        self.assertEqual(contestability(ITEM,{'status':'Inconclusivo'},history,True)['status'],'Evidências insuficientes')

    def test_conflict_with_actual_later_loss(self):
        spectral={'status':'Sinal compatível com perda de cobertura'}
        self.assertEqual(contestability(ITEM,spectral,annual=True,technical=True)['status'],'Evidências insuficientes')
        self.assertIn('conflitantes',contestability(ITEM,spectral,annual=True,technical=True)['reason'])
        self.assertEqual(contestability(ITEM,spectral,annual=True)['status'],'Sem indícios suficientes para contestação')

    def test_no_overlap_no_extrapolation_and_prior_drop(self):
        result=contestability({**ITEM,'consolidated_ha':0},{'status':'Inconclusivo'},annual=True,technical=True)
        self.assertEqual(result['status'],'Evidências insuficientes')
        prior=contestability(ITEM,{'status':'Indício espectral de divergência temporal'},annual=True)
        self.assertEqual(prior['status'],'Passível de contestação (triagem)')
        self.assertEqual(prior['scope_ha'],10)
        self.assertIn('nova data correta',prior['reason'])

    def test_base_uuid_and_border_constraints(self):
        spectral={'status':'Indício espectral de divergência temporal'}
        for item,annual,tolerance in ((ITEM,False,False),({**ITEM,'uuid':''},True,False),({**ITEM,'core_ha':0},True,True)):
            self.assertEqual(contestability(item,spectral,annual=annual,tolerance=tolerance,technical=True)['status'],'Evidências insuficientes')

    def test_report_separates_technical_source_spectral_hypothesis_and_review(self):
        result=contestability(ITEM,{'status':'Inconclusivo'},annual=True,technical=True)
        row={**ITEM,'mode':'automatic','contestability':result,'consolidation_assessment':'Classificação técnica <script>',
            'historical':historical_assessment(QUALITY,'2007-07-01'),'user_review':'Discordo'}
        text=report_html({'Incremento confirmado':False},[row])
        self.assertIn('Passível de contestação',text);self.assertIn('Discordo',text)
        self.assertIn('art. 3º, IV',text);self.assertIn('Arts. 29 e 61-A',text)
        self.assertNotIn('<script>',text);self.assertNotIn('False',text);self.assertIn('Não',text)
