# SPDX-License-Identifier: GPL-2.0-or-later
import json
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from usgs_catalogo_qgis.environmental import (EnvironmentalClient,car_code,display_car,judicial_number,parse_ldi,
    run_assessment,result,LABELS,ConsultationError)
from usgs_catalogo_qgis.environmental_http import Budget,BudgetExpired,ConsultationCancelled,allowed_url
from usgs_catalogo_qgis.environmental_report import render_html,save_report,land_summary

CODE='PA-1502152-'+'A'*32
RECT=[-50,-7,-49,-6]
WKT='POLYGON((-50 -7,-49 -7,-49 -6,-50 -6,-50 -7))'
CONTEXT={'wkt':WKT,'rect':RECT,'uf':'PA','name':'Imóvel teste','car':CODE,'datajud_key':'fixture'}

def feature(i,inside=True,props=None):
    return {'type':'Feature','id':str(i),'geometry':{'inside':inside},'properties':props or {}}

def collection(features=(),**extra):return {'type':'FeatureCollection','features':list(features),**extra}

def overlay(wkt):
    def intersection(geom):
        if not geom:raise ConsultationError('Sem geometria')
        return {'overlap_ha':5.0,'parcel_percent':20,'relation':'interseção poligonal'} if geom.get('inside') else None
    intersection.esri_geometry=lambda:{'rings':[[[-50,-7],[-50,-6],[-49,-6],[-49,-7],[-50,-7]]],'spatialReference':{'wkid':4326}}
    return intersection

def ldi_page(code=CODE,embargo='clear',process='clear'):
    alert='<div class="alert alert-success"><p>Este imóvel não está embargado pela SEMAS e não faz parte da Lista de Desmatamento Ilegal do Estado do Pará.</p></div>' if embargo=='clear' else '<div class="alert alert-danger"><p>Este imóvel está embargado e consta da Lista de Desmatamento Ilegal.</p></div>' if embargo=='found' else ''
    body='Não foram encontrados Processos Punitivos relacionados a este imóvel.' if process=='clear' else '<table><tr><td>2022/0000123456</td></tr></table>' if process=='found' else 'Formato novo'
    return '<html><div id="informacoesImovel">'+code+'</div>'+alert+'<div class="alert alert-danger hide"><div class="alert-content">Este imóvel está embargado.</div></div><div class="content-box"><h3>PROCESSO(S) ADMINISTRATIVO(S) PUNITIVO(S)</h3>'+body+'</div></html>'

class EnvironmentalTests(unittest.TestCase):
    def test_car_normalization_validation_and_uf(self):
        self.assertEqual(display_car(car_code(CODE)),CODE)
        self.assertEqual(car_code(CODE.lower().replace('-','.')),car_code(CODE))
        for invalid in ('PA-1','ZZ-1502152-'+'A'*32,'PA-1502152-'+'G'*32):
            with self.assertRaises(ConsultationError):car_code(invalid)
        with self.assertRaises(ConsultationError):run_assessment({**CONTEXT,'uf':'TO'},fetch=lambda *a:self.fail('No network'))

    def test_public_url_allowlist_prevents_other_paths_mutations_and_credentials(self):
        valid=['https://geoserver.car.gov.br/geoserver/sicar/wfs?service=WFS',
               'https://arcgisportal.iterpa.pa.gov.br/server/rest/services/SICARF/acervoFundiarioMapserver/MapServer/72/query?f=geojson',
               'https://api-publica.datajud.cnj.jus.br/api_publica_tjpa/_search']
        for url in valid:self.assertTrue(allowed_url(url),url)
        invalid=['file:///etc/passwd','http://geoserver.car.gov.br/geoserver/sicar/wfs',
            'https://user@geoserver.car.gov.br/geoserver/sicar/wfs','https://geoserver.car.gov.br:bad/geoserver/sicar/wfs',
            valid[0]+'#fragment','https://example.org/geoserver/sicar/wfs',valid[1].replace('/query?','/applyEdits?'),
            valid[2].replace('/_search','/_delete_by_query'),valid[1].replace('/72/','/100/')]
        for url in invalid:self.assertFalse(allowed_url(url),url)

    def test_time_budget_and_cancel_are_distinct_and_capped(self):
        clock=[0];b=Budget(1000,clock=lambda:clock[0]);self.assertEqual(b.remaining(),295)
        clock[0]=295
        with self.assertRaises(BudgetExpired):b.check()
        with self.assertRaises(ConsultationCancelled):Budget(20,cancelled=lambda:True).check()

    def test_actual_geometry_gate_not_bbox_defines_records(self):
        data=collection([feature('inside',True,{'cod_imovel':CODE,'status_imovel':'AT','cpf':'12345678901'}),feature('outside',False)])
        client=EnvironmentalClient(Budget(),lambda *a:json.dumps(data).encode(),overlay)
        value=client.spatial('car',{**CONTEXT,'car':car_code(CODE)})
        self.assertEqual(value['status'],'found');self.assertEqual(len(value['records']),1)
        self.assertEqual(value['records'][0]['properties']['status_legivel'],'Ativo')
        self.assertNotIn('cpf',value['records'][0]['properties'])
        self.assertIn('não equivale',value['note'])

    def test_wfs_pagination_and_explicit_axis_order(self):
        calls=[]
        def fetch(url,*args):
            q=parse_qs(urlparse(url).query);calls.append(q)
            return json.dumps(collection([feature('A' if q['startIndex']==['0'] else 'B')],numberMatched=2)).encode()
        value=EnvironmentalClient(Budget(),fetch,overlay).spatial('icmbio',CONTEXT)
        self.assertEqual(len(value['records']),2);self.assertEqual(len(calls),2)
        self.assertEqual(calls[0]['srsName'],['urn:ogc:def:crs:OGC:1.3:CRS84'])
        self.assertTrue(calls[0]['bbox'][0].endswith('CRS84'))

    def test_repeated_page_and_invalid_geometry_are_partial_never_clear(self):
        data=collection([feature('A')],numberMatched=2)
        value=EnvironmentalClient(Budget(),lambda *a:json.dumps(data).encode(),overlay).spatial('icmbio',CONTEXT)
        self.assertEqual(value['status'],'partial');self.assertFalse(value['complete'])
        data=collection([{'id':'missing','properties':{},'geometry':None}])
        value=EnvironmentalClient(Budget(),lambda *a:json.dumps(data).encode(),overlay).spatial('icmbio',CONTEXT)
        self.assertNotEqual(value['status'],'clear_in_source');self.assertTrue(value['warnings'])

    def test_http_error_empty_html_bad_crs_never_become_negative(self):
        for data in (b'<html>captcha</html>',b'{"error":{"code":403}}',json.dumps(collection([],crs={'properties':{'name':'EPSG:3857'}})).encode()):
            value=EnvironmentalClient(Budget(),lambda *a:data,overlay).spatial('ibama',CONTEXT)
            self.assertEqual(value['status'],'unavailable');self.assertFalse(value['complete'])

    def test_land_columns_names_processes_and_state_coverage(self):
        calls=[]
        def fetch(url,*a):calls.append(url);return json.dumps({'features':[{'attributes':{'objectid':1,'denominaca':'Gleba teste','processo':'2020/12345','situacao':'Arrecadada','interessad':'Não guardar'}}]}).encode()
        client=EnvironmentalClient(Budget(),fetch,overlay);value=client.spatial('gleba_estadual',CONTEXT)
        self.assertEqual(value['records'][0]['properties']['denominaca'],'Gleba teste')
        self.assertEqual(value['records'][0]['processes'],['2020/12345']);self.assertNotIn('interessad',value['records'][0]['properties'])
        self.assertIn('/72/query',calls[0]);self.assertEqual(client.spatial('sigef',{**CONTEXT,'uf':'AM'})['status'],'not_applicable');self.assertEqual(len(calls),1)

    def test_ldi_negative_positive_hidden_alert_and_process_section(self):
        negative=parse_ldi(ldi_page(),CODE)
        self.assertEqual(negative['embargo'],'clear');self.assertTrue(negative['processes_complete']);self.assertEqual(negative['processes'],[])
        positive=parse_ldi(ldi_page(embargo='found',process='found'),CODE)
        self.assertEqual(positive['embargo'],'found');self.assertEqual(positive['processes'],['2022/0000123456'])
        changed=parse_ldi(ldi_page(embargo='changed',process='changed'),CODE)
        self.assertEqual(changed['embargo'],'unknown');self.assertFalse(changed['processes_complete'])
        with self.assertRaises(ConsultationError):parse_ldi(ldi_page(code='PA-1502152-'+'B'*32),CODE)
        with self.assertRaises(ConsultationError):parse_ldi('<input value="'+CODE+'">captcha',CODE)

    def test_missing_car_ldi_pending_and_multiple_car_limit_reported(self):
        client=EnvironmentalClient(Budget(),lambda url,*a:ldi_page(code=parse_qs(urlparse(url).query)['codigoImovel'][0]).encode(),overlay)
        self.assertEqual(client.ldi({**CONTEXT,'car':''},[])['status'],'pending')
        cars=[{'properties':{'cod_imovel':'PA-1502152-'+str(i)*32}} for i in range(6)]
        value=client.ldi({**CONTEXT,'car':''},cars)
        self.assertEqual(value['status'],'partial');self.assertIn('cinco',value['warnings'][0])

    def test_datajud_checksum_routing_and_query_uses_exact_number(self):
        number,tribunal=judicial_number('0000832-35.2018.4.01.3202');self.assertEqual(tribunal,'trf1')
        with self.assertRaises(ConsultationError):judicial_number('00008323620184013202')
        captured=[]
        def fetch(url,payload,headers):
            captured.append((url,payload,headers));return json.dumps({'hits':{'total':{'value':1,'relation':'eq'},'hits':[{'_id':'1','_source':{'numeroProcesso':number,'nivelSigilo':0,'tribunal':'TRF1','movimentos':[{'nome':'Antigo','dataHora':'2020'},{'nome':'Novo','dataHora':'2021'}]}}]}}).encode()
        value=EnvironmentalClient(Budget(),fetch,overlay).judicial({**CONTEXT,'judicial_numbers':[number]})
        self.assertEqual(value['status'],'found');self.assertEqual(value['records'][0]['last_movement']['nome'],'Novo')
        self.assertEqual(captured[0][1]['query']['match']['numeroProcesso'],number)
        self.assertNotIn('APIKey',json.dumps(value))

    def test_judicial_failure_no_numbers_sigilo_and_mismatch_are_not_clearance(self):
        client=EnvironmentalClient(Budget(),lambda *a:json.dumps({'hits':{'hits':[{'_source':{'numeroProcesso':'00008323520184013202','nivelSigilo':1}}]}}).encode(),overlay)
        self.assertEqual(client.judicial(CONTEXT)['status'],'pending')
        value=client.judicial({**CONTEXT,'judicial_numbers':['00008323520184013202']})
        self.assertEqual(value['status'],'partial');self.assertEqual(value['records'],[])

    def test_parallel_assessment_is_bounded_and_preserves_failures(self):
        def fetch(url,*args):
            if '/ldi/' in url:return ldi_page().encode()
            if 'pamgia' in url:raise ConsultationError('HTTP 403')
            return json.dumps(collection()).encode()
        report=run_assessment(CONTEXT,fetch=fetch,overlay_factory=overlay)
        self.assertEqual(len(report['sources']),len(LABELS));sources={s['source']:s for s in report['sources']}
        self.assertEqual(sources['ibama']['status'],'unavailable');self.assertEqual(sources['icmbio']['status'],'clear_in_source')
        self.assertEqual(sources['other_processes']['status'],'pending');self.assertNotIn('datajud_key',json.dumps(report))
        report=run_assessment(CONTEXT,seconds=5,fetch=lambda *a:self.fail('Deadline expired'),overlay_factory=overlay)
        self.assertEqual(report['state'],'time_limit');self.assertTrue(any(s['status']=='timeout' for s in report['sources']))

    def test_cancel_preserves_report_and_distinct_pending_coverage(self):
        report=run_assessment({**CONTEXT,'car':''},cancelled=lambda:True,fetch=lambda *a:self.fail('No network'),overlay_factory=overlay)
        self.assertEqual(report['state'],'cancelled');self.assertEqual(len(report['sources']),len(LABELS))

    def test_land_conclusions_require_completed_sources_not_unavailable(self):
        report={'sources':[result(s,'unavailable') for s in LABELS]}
        self.assertIn('inconclusiva',land_summary(report)['settlement'])
        for source in report['sources']:
            if source['source'].startswith('assent_'):source.update(status='clear_in_source',complete=True)
        self.assertIn('Não foi identificada',land_summary(report)['settlement'])
        report['sources'][list(LABELS).index('assent_federal')]['records']=[{'id':'PA','properties':{'nmprojeto':'Projeto teste'},'overlap_ha':2,'parcel_percent':3}]
        self.assertIn('Projeto teste',land_summary(report)['settlement']);self.assertIn('não comprovam',land_summary(report)['tenure'])

    def test_saved_report_escapes_html_csv_and_keeps_machine_evidence(self):
        report=run_assessment({**CONTEXT,'name':'<script>alert(1)</script>'},fetch=lambda *a:json.dumps(collection()).encode() if '/ldi/' not in a[0] else ldi_page().encode(),overlay_factory=overlay)
        value=report['sources'][0];value['records']=[{'id':'=1+2','processes':['2020/12345'],'properties':{'cod_imovel':'<img src=x onerror=alert(1)>'},'relation':'registro'}]
        text=render_html(report);self.assertNotIn('<script>alert',text);self.assertIn('&lt;script&gt;',text);self.assertNotIn('<img src=x',text)
        with tempfile.TemporaryDirectory() as folder:
            paths=save_report(report,folder)
            self.assertTrue(all(Path(p).exists() for p in paths.values()));self.assertIn("'=1+2",Path(paths['csv']).read_text('utf-8-sig'))
            data=json.loads(Path(paths['json']).read_text());self.assertEqual(data['version'],'3.5.2');self.assertFalse(list(Path(folder).glob('*.part')))

try:
    from qgis.core import QgsApplication
except ImportError:QgsApplication=None

@unittest.skipIf(QgsApplication is None,'PyQGIS required')
class EnvironmentalGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QgsApplication.instance() or QgsApplication([],False);cls.app.initQgis()
    def test_real_hole_bbox_false_positive_and_boundary_only(self):
        from usgs_catalogo_qgis.environmental_geometry import ParcelOverlay
        overlay=ParcelOverlay('POLYGON((0 0,4 0,4 4,0 4,0 0),(1 1,3 1,3 3,1 3,1 1))')
        self.assertIsNone(overlay({'type':'Polygon','coordinates':[[[1.1,1.1],[2,1.1],[2,2],[1.1,2],[1.1,1.1]]]}))
        self.assertIsNone(overlay({'type':'Polygon','coordinates':[[[4,0],[5,0],[5,1],[4,1],[4,0]]]}))
    def test_geodesic_overlap_not_declared_car_area_and_points(self):
        from usgs_catalogo_qgis.environmental_geometry import ParcelOverlay
        overlay=ParcelOverlay(WKT)
        point=overlay({'type':'Point','coordinates':[-49.5,-6.5]});self.assertIsNone(point['overlap_ha'])
        value=overlay({'type':'Polygon','coordinates':[[[-50,-7],[-49,-7],[-49,-6],[-50,-6],[-50,-7]]]})
        self.assertAlmostEqual(value['parcel_percent'],100);self.assertGreater(value['overlap_ha'],1000000)
        with self.assertRaises(ConsultationError):overlay({'type':'Point','coordinates':[500000,9000000]})

@unittest.skipIf(QgsApplication is None,'PyQGIS required')
class EnvironmentalQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QgsApplication.instance() or QgsApplication([],False);cls.app.initQgis()
    def fake_manager(self,body=b'{}',status=200,hang=False):
        import types
        from unittest.mock import patch
        from qgis.PyQt.QtCore import QObject,QTimer,pyqtSignal
        from qgis.PyQt.QtNetwork import QNetworkReply
        class Reply(QObject):
            finished=pyqtSignal();readyRead=pyqtSignal()
            def __init__(self):
                super().__init__();self.data=body;self.done=False;self.aborted=False
                if not hang:QTimer.singleShot(0,self.deliver)
            def deliver(self):
                self.readyRead.emit();self.done=True;self.finished.emit()
            def isFinished(self):return self.done
            def readAll(self):value,self.data=self.data,b'';return value
            def error(self):return QNetworkReply.NetworkError.OperationCanceledError if self.aborted else QNetworkReply.NetworkError.NoError
            def attribute(self,key):return status
            def abort(self):self.aborted=True;self.done=True;self.finished.emit()
        self.requests=[]
        def request(req,payload=None):
            reply=Reply();self.requests.append((req,payload,reply));return reply
        return patch('qgis.core.QgsNetworkAccessManager',types.SimpleNamespace(instance=lambda:types.SimpleNamespace(get=request,post=request)))
    def test_native_event_loop_timeout_and_cancel_abort_reply(self):
        from usgs_catalogo_qgis.environmental_http import PublicHttp
        url='https://geoserver.car.gov.br/geoserver/sicar/wfs'
        start=time.monotonic()
        with self.fake_manager(hang=True),self.assertRaises(BudgetExpired):PublicHttp(Budget(.03),timeout=10)(url)
        self.assertTrue(self.requests[0][2].aborted);self.assertLess(time.monotonic()-start,.5)
        from qgis.PyQt.QtCore import QTimer
        stop=[False];QTimer.singleShot(10,lambda:stop.__setitem__(0,True))
        with self.fake_manager(hang=True),self.assertRaises(ConsultationCancelled):PublicHttp(Budget(10,lambda:stop[0]))(url)
        self.assertTrue(self.requests[0][2].aborted)
    def test_native_http_redirect_and_byte_limit_are_rejected(self):
        from usgs_catalogo_qgis.environmental_http import PublicHttp
        url='https://geoserver.car.gov.br/geoserver/sicar/wfs'
        with self.fake_manager(status=302),self.assertRaises(ConsultationError):PublicHttp(Budget())(url)
        with self.fake_manager(body=b'0123456789'),self.assertRaises(ConsultationError):PublicHttp(Budget(),max_bytes=4)(url)
    def test_native_readonly_post_form_for_large_parcel_and_json_for_datajud(self):
        from usgs_catalogo_qgis.environmental_http import PublicHttp
        with self.fake_manager():
            PublicHttp(Budget())('https://arcgisportal.iterpa.pa.gov.br/server/rest/services/SICARF/acervoFundiarioMapserver/MapServer/72/query',{'geometry':'with space','f':'json'})
        request,payload,_=self.requests[0];self.assertIn(b'geometry=with+space',bytes(payload));self.assertEqual(bytes(request.rawHeader(b'Content-Type')),b'application/x-www-form-urlencoded')
        with self.fake_manager():PublicHttp(Budget())('https://api-publica.datajud.cnj.jus.br/api_publica_trf1/_search',{'query':{}},{'Authorization':'APIKey abc='})
        self.assertEqual(json.loads(bytes(self.requests[0][1])),{'query':{}})
        with self.assertRaises(ConsultationError):PublicHttp(Budget())('https://geoserver.car.gov.br/geoserver/sicar/wfs',{'unexpected':'post'})
    def test_snapshot_uses_selected_parcel_and_refuses_multifarm_layer(self):
        from qgis.core import QgsProject,QgsVectorLayer,QgsFeature,QgsGeometry
        from usgs_catalogo_qgis.environmental_ui import EnvironmentalTab
        layer=QgsVectorLayer('Polygon?crs=EPSG:4326','Imóveis teste','memory')
        f=QgsFeature();f.setGeometry(QgsGeometry.fromWkt('POLYGON((-50 -7,-49.999 -7,-49.999 -6.999,-50 -6.999,-50 -7))'));layer.dataProvider().addFeatures([f,f]);QgsProject.instance().addMapLayer(layer)
        tab=EnvironmentalTab(None);tab.parcel.setCurrentIndex(tab.parcel.findData(layer.id()))
        with self.assertRaises(ConsultationError):tab.snapshot()
        fid=next(layer.getFeatures()).id();layer.selectByIds([fid]);tab.selected.setChecked(True)
        snap=tab.snapshot();self.assertGreater(snap['parcel_area_ha'],0);self.assertLess(snap['parcel_area_ha'],100)
        before=snap['wkt'];layer.removeSelection();self.assertEqual(snap['wkt'],before)
        tab.close();QgsProject.instance().removeMapLayer(layer.id())

class EnvironmentalRegressionTests(unittest.TestCase):
    def test_empty_wfs_with_null_crs_is_a_valid_source_reply(self):
        value=EnvironmentalClient(Budget(),lambda *a:json.dumps(collection([],crs=None)).encode(),overlay).spatial('icmbio',CONTEXT)
        self.assertEqual(value['status'],'clear_in_source')
    def test_multiple_car_candidates_never_become_a_unique_identity(self):
        data=collection([feature('a',True,{'cod_imovel':CODE}),feature('b',True,{'cod_imovel':'PA-1502152-'+'B'*32})])
        value=EnvironmentalClient(Budget(),lambda *a:json.dumps(data).encode(),overlay).spatial('car',{**CONTEXT,'car':''})
        self.assertEqual(len(value['records']),2);self.assertIn('nenhum foi escolhido',value['note'])

class EnvironmentalRetryTests(unittest.TestCase):
    def test_only_transient_failures_retry_within_original_budget(self):
        from usgs_catalogo_qgis.environmental_http import PublicHttp,TemporarySourceError
        from unittest.mock import patch
        http=PublicHttp(Budget(10),timeout=1)
        with patch.object(http,'_request',side_effect=[TemporarySourceError('503'),b'ok']) as call,patch('usgs_catalogo_qgis.environmental_http.time.sleep'),patch.object(http.budget,'clock',side_effect=[0,0,2]):
            self.assertEqual(http('url'),b'ok');self.assertEqual(call.call_count,2)
        http=PublicHttp(Budget(.1),timeout=1)
        with patch.object(http,'_request',side_effect=TemporarySourceError('503')) as call,self.assertRaises(TemporarySourceError):http('url')
        self.assertEqual(call.call_count,1)
        with patch.object(http,'_request',side_effect=ConsultationError('403')) as call,self.assertRaises(ConsultationError):http('url')
        self.assertEqual(call.call_count,1)

    def test_global_deadline_interrupts_wait_for_busy_land_host(self):
        from usgs_catalogo_qgis.environmental_http import PublicHttp
        http=PublicHttp(Budget(.03));http.land_slots.acquire();http.land_slots.acquire()
        start=time.monotonic()
        with self.assertRaises(BudgetExpired):http('https://arcgisportal.iterpa.pa.gov.br/server/rest/services/SICARF/acervoFundiarioMapserver/MapServer/72/query')
        self.assertLess(time.monotonic()-start,.5)
        http.land_slots.release();http.land_slots.release()

class DatajudAccessTests(unittest.TestCase):
    def test_current_public_key_is_read_from_official_page_without_bundled_value(self):
        from usgs_catalogo_qgis.environmental import DATAJUD_ACCESS
        issued=''.join(['public','fixture','datajud','credential','value'])
        calls=[]
        def fetch(url,payload=None,headers=None):
            calls.append((url,headers))
            if url==DATAJUD_ACCESS:return ('<html><pre>Authorization: APIKey '+issued+'</pre></html>').encode()
            return json.dumps({'hits':{'total':{'value':0,'relation':'eq'},'hits':[]}}).encode()
        value=EnvironmentalClient(Budget(),fetch,overlay).judicial({**CONTEXT,'datajud_key':'','judicial_numbers':['00008323520184013202']})
        self.assertEqual(value['status'],'clear_in_source')
        self.assertEqual(calls[0],(DATAJUD_ACCESS,None));self.assertEqual(calls[1][1],{'Authorization':'APIKey '+issued})
        self.assertNotIn(issued,json.dumps(value));self.assertTrue(allowed_url(DATAJUD_ACCESS))
    def test_blocked_key_page_is_pending_and_does_not_claim_no_process(self):
        def fetch(*a):raise ConsultationError('HTTP 403')
        value=EnvironmentalClient(Budget(),fetch,overlay).judicial({**CONTEXT,'datajud_key':'','judicial_numbers':['00008323520184013202']})
        self.assertEqual(value['status'],'pending');self.assertFalse(value['complete']);self.assertIn('campo DataJud',value['note'])
