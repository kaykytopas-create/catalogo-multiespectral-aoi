# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded public-source screening. No claim of legal or universal clearance."""
import hashlib
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlencode
from .environmental_http import Budget, PublicHttp, ConsultationError

CAR = 'https://geoserver.car.gov.br/geoserver/sicar/wfs'
ICMBIO = 'https://geoservicos.inde.gov.br/geoserver/ICMBio/ows'
IBAMA = 'https://pamgia.ibama.gov.br/server/rest/services/01_Publicacoes_Bases/adm_embargos_ibama_a/MapServer/0/query'
LDI = 'https://monitoramento.semas.pa.gov.br/ldi/pesquisa/pesquisarComCar'
DATAJUD = 'https://api-publica.datajud.cnj.jus.br/'
ITERPA = 'https://arcgisportal.iterpa.pa.gov.br/server/rest/services/SICARF/acervoFundiarioMapserver/MapServer/'
LAND_LAYERS = {
    'assent_estadual':(63,'Assentamentos estaduais — ITERPA (PA)','objectid','nmassent,modalidade,orgaogest,processo,municipio,dataatual,portaria,decreto'),
    'assent_federal':(64,'Assentamentos federais — base ITERPA (PA)','objectid_1','nmprojeto,codsipra,fase,orgaogest,municipio,datamodif'),
    'gleba_estadual':(72,'Glebas estaduais — ITERPA (PA)','objectid','denominaca,situacao,processo,municipio,matricula,orgaogest,dataatual'),
    'gleba_federal':(73,'Glebas federais — base ITERPA (PA)','objectid','denominaca,situacao,municipio,matricula,codcertif,atualizaca'),
    'sigef':(98,'Parcelas SIGEF — base ITERPA (PA)','objectid_1','nomearea,parcelaco,situacimov,status,registrom,dataaprov,orgaogest,datamodif'),
    'snci':(97,'Parcelas SNCI — base ITERPA (PA)','objectid_1','nmimovel,numprocess,numcertif,datacerti,codimovel,orgaogest,datamodif'),
    'requerimento':(93,'Requerimentos fundiários SICARF — ITERPA (PA)','objectid','imovel,ano,processo,parcela,situacao,municipio,data'),
}
DATAJUD_ACCESS = 'https://datajud-wiki.cnj.jus.br/api-publica/acesso/'
UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SE SP TO'.split()
STATUSES = {'found':'Registros encontrados', 'clear_in_source':'Sem registro no recorte consultado',
            'partial':'Consulta parcial', 'unavailable':'Fonte indisponível', 'pending':'Pendente de consulta',
            'not_applicable':'Fora da cobertura', 'timeout':'Prazo atingido', 'cancelled':'Cancelado'}
CAR_STATUS = {'AT':'Ativo', 'PE':'Pendente', 'SU':'Suspenso', 'CA':'Cancelado'}
LABELS = {'car':'CAR — SICAR/SFB', 'ibama':'Embargos — IBAMA/Pamgia', 'icmbio':'Embargos — ICMBio',
          'autos_icmbio':'Autos de infração — ICMBio', 'ldi':'Embargos e processos punitivos — SEMAS/LDI (PA)',
          'datajud':'Processos judiciais — CNJ/DataJud', 'other_processes':'Outros processos públicos'}
LINKS = {'car':'https://www.car.gov.br/publico/imoveis/index',
         'ibama':'https://aie-consultapublica.ibama.gov.br/',
         'icmbio':'https://www.gov.br/icmbio/pt-br/dados-icmbio/dados_geoespaciais',
         'autos_icmbio':'https://www.gov.br/icmbio/pt-br/dados-icmbio/dados_geoespaciais',
         'ldi':'https://monitoramento.semas.pa.gov.br/ldi/',
         'datajud':'https://www.cnj.jus.br/sistemas/datajud/api-publica/',
         'other_processes':'https://monitoramento.semas.pa.gov.br/simlam/ListarProcessos2.aspx'}


LABELS.update({key:value[1] for key,value in LAND_LAYERS.items()})
LINKS.update({key:ITERPA+str(value[0]) for key,value in LAND_LAYERS.items()})


def now():
    return datetime.now(timezone.utc).isoformat()


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)) if not unicodedata.combining(c)).lower()


def car_code(value):
    value = re.sub(r'[^A-Z0-9]', '', str(value).upper())
    if value and (not re.fullmatch(r'[A-Z]{2}\d{7}[A-F0-9]{32}', value) or value[:2] not in UFS):
        raise ConsultationError('Informe o recibo federal completo do CAR, com UF, município e código de 32 caracteres.')
    return value


def display_car(code):
    code = car_code(code)
    return code[:2]+'-'+code[2:9]+'-'+code[9:] if code else ''


def result(source, status='pending', note='', records=None, **extra):
    return dict(source=source, label=LABELS[source], status=status, note=note,
                records=list(records or []), consulted_at=now(), portal=LINKS[source],
                complete=status in ('found','clear_in_source'), **extra)


def read_json(fetch, url, payload=None, headers=None):
    raw = fetch(url, payload, headers)
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ConsultationError('Resposta não é JSON público válido; possível bloqueio ou mudança do serviço.') from exc
    if not isinstance(value, dict) or 'error' in value or value.get('exceptions'):
        raise ConsultationError('Serviço retornou erro; não foi possível concluir a consulta.')
    return value


def process_numbers(props):
    values = []
    for key, value in props.items():
        if ('process' in key.lower() or key.lower() in ('nup','n_processo','num_proc')) and value:
            value = str(value).strip()
            if value.lower() not in ('null','none','sem processo','0'):
                values.append(value[:160])
    return list(dict.fromkeys(values))


PUBLIC_FIELDS = ('cod_imovel','status_imovel','condicao','situacao','condicao_i','area','municipio','uf',
    'data_atualizacao','dat_atuali','numero_emb','num_tad','serie_tad','numero_ai','num_auto_infracao',
    'data','dat_embargo','dat_ult_alteracao','julgamento','obs','des_tad','des_infracao','desc_inf_1',
    'tipo_infra','num_processo','processo','nr_process','nome_imovel') + tuple(dict.fromkeys(field for spec in LAND_LAYERS.values() for field in spec[3].split(',')))


class EnvironmentalClient:
    def __init__(self, budget, fetch=None, overlay_factory=None):
        self.budget = budget
        self.fetch = fetch or PublicHttp(budget)
        if overlay_factory is None:
            from .environmental_geometry import ParcelOverlay
            overlay_factory = ParcelOverlay
        self.overlay_factory = overlay_factory

    def spatial(self, source, context):
        if source in LAND_LAYERS and context['uf']!='PA':
            return result(source,'not_applicable','A fonte fundiária integrada do ITERPA cobre o Pará. Fora do PA, a situação fundiária permanece pendente de consulta à base oficial local/INCRA.')
        overlay = self.overlay_factory(context['wkt'])
        records, warnings, seen, pages, offset = [], [], set(), set(), 0
        total, complete = None, False
        endpoint = ITERPA+str(LAND_LAYERS[source][0])+'/query' if source in LAND_LAYERS else CAR if source == 'car' else IBAMA if source == 'ibama' else ICMBIO
        layer = 'sicar:sicar_imoveis_'+context['uf'].lower() if source == 'car' else 'ICMBio:embargos_icmbio' if source == 'icmbio' else 'ICMBio:autos_infracao_icmbio'
        last_url = endpoint
        evidence = []
        try:
            for _ in range(8):
                self.budget.check()
                if source == 'ibama' or source in LAND_LAYERS:
                    params = dict(f='geojson', where='1=1', geometry=','.join(map(str,context['rect'])),
                        geometryType='esriGeometryEnvelope', inSR=4326, outSR=4326, spatialRel='esriSpatialRelIntersects',
                        outFields='objectid,num_tad,serie_tad,num_auto_infracao,num_processo,dat_embargo,dat_ult_alteracao,des_tad,des_infracao,nome_imovel,municipio,uf',
                        returnGeometry='true', resultOffset=offset, resultRecordCount=250, orderByFields='objectid ASC')
                    if source in LAND_LAYERS:
                        params['outFields']=LAND_LAYERS[source][2]+','+LAND_LAYERS[source][3]
                        params['orderByFields']=LAND_LAYERS[source][2]+' ASC'
                        params.update(f='json', geometry=json.dumps(overlay.esri_geometry()),
                            geometryType='esriGeometryPolygon', spatialRel='esriSpatialRelRelation',
                            relationParam='T********', returnGeometry='false')
                else:
                    params = dict(service='WFS', version='2.0.0', request='GetFeature', typeNames=layer,
                        outputFormat='application/json', srsName='urn:ogc:def:crs:OGC:1.3:CRS84',
                        bbox=','.join(map(str,context['rect']))+',urn:ogc:def:crs:OGC:1.3:CRS84', count=250, startIndex=offset)
                last_url = endpoint+'?'+urlencode(params)
                post = source in LAND_LAYERS and len(last_url)>7000
                data = read_json(self.fetch, endpoint if post else last_url, params if post else None)
                if (source not in LAND_LAYERS and data.get('type') != 'FeatureCollection') or not isinstance(data.get('features'),list):
                    raise ConsultationError('Serviço não retornou uma coleção GeoJSON.')
                crs = str((data.get('crs') or {}).get('properties',{}).get('name',''))
                if crs and not ('CRS84' in crs.upper() or crs.endswith(('4326','4326)'))):
                    raise ConsultationError('CRS da resposta difere de longitude/latitude solicitada.')
                features = data['features']
                evidence.append(dict(url=endpoint if post else last_url, query_parameters=params if post else None, received=len(features), sha256=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()))
                declared = data.get('numberMatched',data.get('totalFeatures'))
                if str(declared).isdigit():
                    if total is not None and total != int(declared):
                        raise ConsultationError('A quantidade da base mudou durante a paginação.')
                    total = int(declared)
                signature = hashlib.sha256(json.dumps(features,sort_keys=True).encode()).hexdigest()
                if features and signature in pages:
                    raise ConsultationError('O servidor repetiu uma página; abrangência incompleta.')
                pages.add(signature)
                for feature in features:
                    self.budget.check()
                    props = feature.get('attributes' if source in LAND_LAYERS else 'properties') or {}
                    uid = str(feature.get('id') or props.get('objectid') or props.get('objectid_1') or props.get('ogc_fid') or hashlib.sha256(json.dumps(feature,sort_keys=True).encode()).hexdigest())
                    if uid in seen:
                        continue
                    seen.add(uid)
                    try:
                        overlap = ({'overlap_ha':None,'parcel_percent':None,
                            'relation':'interseção dos interiores confirmada pelo serviço com o polígono real; fração de área não calculada'}
                            if source in LAND_LAYERS else overlay(feature.get('geometry')))
                        if overlap is None:
                            continue
                        if source == 'car' and context.get('car') and car_code(props.get('cod_imovel','')) != context['car']:
                            continue
                        values = {key:str(value)[:2500] for key,value in props.items() if key in PUBLIC_FIELDS and value is not None}
                        if source == 'car':
                            values['status_legivel'] = CAR_STATUS.get(str(props.get('status_imovel','')), 'Código cadastral não reconhecido — conferir no SICAR')
                        records.append(dict(id=uid, properties=values, processes=process_numbers(values), **overlap))
                    except (ConsultationError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as exc:
                        warnings.append('Registro '+uid+': '+str(exc)[:200])
                offset += len(features)
                more = data.get('exceededTransferLimit',False)
                if (total is not None and offset >= total) or (total is None and len(features)<250 and not more):
                    complete = True
                    break
                if not features:
                    raise ConsultationError('Página vazia antes de atingir o total declarado.')
            if not complete:
                warnings.append('Limite de oito páginas atingido; reduza o limite do imóvel ou faça conferência complementar.')
        except Exception as exc:
            warnings.append(str(exc))
        status = ('found' if records else 'clear_in_source') if complete and not warnings else 'partial' if records or evidence else 'unavailable'
        if not records and warnings and self.budget.remaining() <= 0:
            status = 'timeout'
        if self.budget.cancelled():status='cancelled'
        note = 'Cruzamento com o polígono real do imóvel; contato apenas na borda não soma área. Valores de área não devem ser somados entre registros sobrepostos.'
        if source in LAND_LAYERS:
            note = 'Acervo público ITERPA, recorte Pará. Consulta espacial com o polígono real e relação dos interiores (DE-9IM T********), excluindo somente contato na borda. O serviço retorna os atributos sem baixar os grandes polígonos das glebas; frações de área não são calculadas. Data de atualização conforme campos da camada. Interseção cadastral e certificação SIGEF/SNCI não comprovam domínio ou titularidade; requerimento não equivale a título.'
        if source == 'car':
            note = 'Situação e condição declaradas na base pública SICAR; cadastro ativo não equivale a regularidade ambiental ou análise aprovada.'
            if not context.get('car') and len(records)>1:
                note += ' Há mais de um CAR sobreposto: nenhum foi escolhido como o CAR exclusivo do imóvel.'
            if context.get('car') and not records:
                note += ' O CAR informado não foi confirmado dentro do limite nesta consulta.'
        return result(source,status,note,records,endpoint=endpoint,query_url=last_url,warnings=list(dict.fromkeys(warnings)),pages=evidence,matched_in_bbox=total,complete_checked=complete)

    def ldi(self, context, cars):
        if context['uf'] != 'PA':
            return result('ldi','not_applicable','A consulta SEMAS/LDI integrada cobre somente o Pará.')
        codes = [context['car']] if context.get('car') else list(dict.fromkeys(car_code(i['properties'].get('cod_imovel','')) for i in cars))
        codes = [code for code in codes if code]
        if not codes:
            return result('ldi','pending','Informe o recibo CAR federal: a LDI usa esse identificador, não uma busca pública por polígono.')
        rows, warnings, evidence, clear = [], [], [], 0
        if len(codes)>5:
            warnings.append('Há mais de cinco CARs sobrepostos; somente cinco foram consultados dentro do orçamento de tempo.')
        for code in codes[:5]:
            url = LDI+'?'+urlencode({'codigoImovel':display_car(code)})
            try:
                self.budget.check()
                raw = self.fetch(url,None,None)
                parsed = parse_ldi(raw.decode('utf-8'),code)
                evidence.append(dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),car=display_car(code),**parsed))
                if parsed['embargo'] == 'clear':
                    clear += 1
                elif parsed['embargo'] == 'found':
                    rows.append(dict(id=display_car(code),car=display_car(code),kind='Registro de embargo LDI',processes=[],relation='associação pelo recibo CAR; conferir alcance do ato'))
                else:
                    warnings.append(display_car(code)+': situação de embargo não reconhecida na página.')
                for number in parsed['processes']:
                    rows.append(dict(id=number,car=display_car(code),kind='Processo punitivo SEMAS/LDI',processes=[number],relation='associação pelo recibo CAR'))
                if not parsed['processes_complete']:
                    warnings.append(display_car(code)+': seção de processos punitivos incompleta ou não reconhecida.')
            except (ConsultationError, UnicodeError) as exc:
                warnings.append(display_car(code)+': '+str(exc))
        status = 'partial' if warnings else 'found' if rows else 'clear_in_source'
        if not evidence and warnings:
            status = 'timeout' if not self.budget.remaining() else 'unavailable'
        note = 'Consulta por recibo CAR no portal público SEMAS/LDI; processos são os punitivos exibidos nessa consulta. Não abrange todos os processos do SIMLAM ou SEI.'
        if not context.get('car'):
            note += ' CARs candidatos obtidos por interseção; confirmar qual cadastro corresponde ao imóvel.'
        else:
            note += ' CAR fornecido pelo usuário; a correspondência espacial deve ser conferida na seção CAR.'
        return result('ldi',status,note,rows,warnings=warnings,pages=evidence,cars_clear=clear)

    def judicial(self, context):
        numbers = context.get('judicial_numbers',[])
        if not numbers:
            return result('datajud','pending','Sem números CNJ informados. A consulta integrada não descobre todos os processos por nome, CPF, CAR ou polígono.')
        key = context.get('datajud_key','').strip()
        if not key:
            try:
                raw = self.fetch(DATAJUD_ACCESS,None,None)
                page = Page(raw.decode('utf-8'))
                match = re.search(r'APIKey\s+([A-Za-z0-9+/=_-]{24,})',page.text(page.root))
                if not match:
                    raise ConsultationError('A página oficial não informou a chave no formato esperado.')
                key = match.group(1)
            except (ConsultationError, UnicodeError) as exc:
                return result('datajud','pending','Não foi possível obter a chave pública no portal CNJ. Copie a chave vigente da documentação oficial para o campo DataJud e repita a consulta.',warnings=[str(exc)])
        if not re.fullmatch(r'[A-Za-z0-9+/=_-]+',key):
            return result('datajud','pending','Chave pública DataJud inválida; confira a documentação CNJ.')
        records, warnings, evidence = [], [], []
        for number in numbers:
            try:
                self.budget.check()
                normalized, tribunal = judicial_number(number)
                url = DATAJUD+'api_publica_'+tribunal+'/_search'
                payload = {'size':100,'query':{'match':{'numeroProcesso':normalized}},'_source':['numeroProcesso','tribunal','grau','classe','assuntos','orgaoJulgador','movimentos','dataAjuizamento','dataHoraUltimaAtualizacao','nivelSigilo']}
                data = read_json(self.fetch,url,payload,{'Authorization':'APIKey '+key})
                hits = data.get('hits',{});total = hits.get('total',{})
                if isinstance(total,dict) and (total.get('relation','eq')!='eq' or total.get('value',0)>100):
                    warnings.append('Resposta judicial truncada para '+number)
                elif isinstance(total,int) and total>100:
                    warnings.append('Resposta judicial truncada para '+number)
                if not isinstance(hits.get('hits'),list):
                    raise ConsultationError('DataJud não retornou lista de processos válida.')
                evidence.append(dict(url=url,number=normalized,sha256=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()))
                for hit in hits['hits']:
                    value = hit.get('_source',{})
                    if str(value.get('numeroProcesso'))!=normalized:
                        warnings.append('Resultado com numeração diferente foi descartado.');continue
                    if str(value.get('nivelSigilo','0')) not in ('0','None'):
                        warnings.append('Registro com indicação de sigilo foi excluído.');continue
                    movements = sorted(value.get('movimentos') or [],key=lambda m:str(m.get('dataHora','')),reverse=True)
                    records.append(dict(id=str(hit.get('_id',normalized)),processes=[normalized],kind='Metadados judiciais públicos',
                        tribunal=str(value.get('tribunal','')),grau=str(value.get('grau','')),classe=value.get('classe',{}),
                        assuntos=value.get('assuntos',[]),orgao=value.get('orgaoJulgador',{}),updated=value.get('dataHoraUltimaAtualizacao',''),
                        last_movement={k:movements[0].get(k) for k in ('nome','dataHora','codigo')} if movements else {},
                        relation='número fornecido pelo usuário; vínculo com o imóvel não demonstrado automaticamente'))
            except ConsultationError as exc:
                warnings.append(number+': '+str(exc))
        status = 'partial' if warnings else 'found' if records else 'clear_in_source'
        if not evidence and warnings:
            status = 'timeout' if not self.budget.remaining() else 'unavailable'
        return result('datajud',status,'Fonte: Conselho Nacional de Justiça (CNJ), Base Nacional de Dados do Poder Judiciário (DataJud). Consulta dos números informados no tribunal de origem; não confirma inexistência de outros processos nem de recursos em outros tribunais.',records,warnings=warnings,pages=evidence)


def judicial_number(value):
    digits = re.sub(r'[^0-9]','',str(value))
    if len(digits)!=20:
        raise ConsultationError('Número CNJ deve conter 20 dígitos.')
    # CNJ MOD 97-10: the check digits move to the end after the court/origin.
    if int(digits[:7]+digits[9:]+digits[7:9]) % 97 != 1:
        raise ConsultationError('Dígitos verificadores do número CNJ inválidos.')
    branch, region = digits[13],int(digits[14:16])
    if branch == '4' and 1<=region<=6:
        tribunal = 'trf'+str(region)
    elif branch == '8' and 1<=region<=27:
        tribunal = 'tjdft' if region==7 else 'tj'+UFS[region-1].lower()
    elif branch == '5' and 1<=region<=24:
        tribunal = 'trt'+str(region)
    else:
        raise ConsultationError('Ramo/tribunal não integrado: confira a consulta pública do tribunal.')
    return digits,tribunal


class Page(HTMLParser):
    """Small DOM for public LDI output; never executes remote JavaScript."""
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.root={'tag':'root','attrs':{},'children':[]};self.stack=[self.root]
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        node={'tag':tag,'attrs':dict(attrs),'children':[]};self.stack[-1]['children'].append(node)
        if tag not in ('input','br','hr','img','meta','link','source','wbr'):
            self.stack.append(node)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i]['tag']==tag:
                del self.stack[i:];break
    def handle_data(self,data):
        self.stack[-1]['children'].append(data)
    def nodes(self,node=None):
        node=self.root if node is None else node
        yield node
        for child in node['children']:
            if isinstance(child,dict):yield from self.nodes(child)
    def text(self,node):
        classes=node['attrs'].get('class','').split()
        if node['tag'] in ('script','style') or any(c in classes for c in ('hide','hidden','hidden-with-size')) or 'hidden' in node['attrs'] or 'display:none' in node['attrs'].get('style','').replace(' ',''):
            return ''
        return ' '.join(self.text(c) if isinstance(c,dict) else c for c in node['children'])


def parse_ldi(text, code):
    page=Page(text);nodes=list(page.nodes())
    info=next((n for n in nodes if n['attrs'].get('id')=='informacoesImovel'),None)
    if info is None or car_code(code) not in re.sub(r'[^A-Z0-9]','',page.text(info).upper()):
        raise ConsultationError('A página não confirmou o recibo CAR; não interpretar como ausência de embargo.')
    alerts=[plain(page.text(n)) for n in nodes if 'alert' in n['attrs'].get('class','').split() and any(c in n['attrs'].get('class','').split() for c in ('alert-danger','alert-warning')) and page.text(n)]
    # Inspect alert parent visibility too; the site's hidden generic error is always present.
    visible=plain(page.text(page.root))
    negative='este imovel nao esta embargado pela semas e nao faz parte da lista' in visible
    positive=any(('embargad' in a or 'lista de desmatamento ilegal' in a) and ('imovel' in a or 'area' in a) and 'nao esta' not in a and 'nao faz parte' not in a for a in alerts)
    embargo='clear' if negative and not positive else 'found' if positive and not negative else 'unknown'
    sections=[n for n in nodes if 'content-box' in n['attrs'].get('class','').split() and 'processo(s) administrativo(s) punitivo(s)' in plain(page.text(n))]
    proc_text=' '.join(page.text(n) for n in sections)
    no_process='nao foram encontrados processos punitivos relacionados a este imovel' in plain(proc_text)
    patterns=r'\b(?:\d{5}\.\d{6}/\d{4}-\d{2}|\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}|20\d{2}/\d{4,12}|\d{4,12}/20\d{2})\b'
    numbers=list(dict.fromkeys(re.findall(patterns,proc_text)))
    return dict(embargo=embargo,processes=numbers,processes_complete=bool(sections) and (no_process or bool(numbers)),
                process_status='clear_in_source' if no_process and not numbers else 'found' if numbers else 'pending')


def run_assessment(context, progress=lambda source,status:None, cancelled=lambda:False, seconds=300,
                   fetch=None, overlay_factory=None, clock=time.monotonic):
    context=dict(context)
    if context.get('uf') not in UFS:
        raise ConsultationError('Selecione uma UF brasileira válida.')
    context['car']=car_code(context.get('car',''))
    if context['car'] and context['car'][:2]!=context['uf']:
        raise ConsultationError('A UF do recibo CAR difere da UF selecionada.')
    for number in context.get('judicial_numbers',[]):judicial_number(number)
    if len(context.get('judicial_numbers',[]))>20:
        raise ConsultationError('Máximo de vinte números CNJ por consulta de cinco minutos.')
    start=clock();budget=Budget(max(0,min(300,seconds)-5),cancelled,clock)
    client=EnvironmentalClient(budget,fetch,overlay_factory)
    sources={}
    tasks={source:(lambda source=source:client.spatial(source,context)) for source in ('car','ibama','icmbio','autos_icmbio')}
    tasks['datajud']=lambda:client.judicial(context)
    if context.get('car'):
        tasks['ldi']=lambda:client.ldi(context,[])
    for source in LAND_LAYERS:
        tasks[source]=lambda source=source:client.spatial(source,context)
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(fn):key for key,fn in tasks.items()}
        while pending:
            done,_=wait(pending,timeout=.1,return_when=FIRST_COMPLETED)
            for future in done:
                source=pending.pop(future)
                try:value=future.result()
                except Exception as exc:value=result(source,'cancelled' if cancelled() else 'timeout' if not budget.remaining() else 'unavailable','Não foi possível concluir a consulta a esta fonte; confira o portal oficial.',diagnostic=str(exc)[:300])
                sources[source]=value;progress(source,value['status'])
                if source=='car' and 'ldi' not in tasks:
                    cars=sorted(value['records'],key=lambda r:-(r.get('overlap_ha') or 0))
                    tasks['ldi']=lambda:client.ldi(context,cars)
                    pending[pool.submit(tasks['ldi'])]='ldi'
    sources['other_processes']=result('other_processes','pending',
        'A busca não cobre todos os processos administrativos, judiciais, municipais, SEI, SIMLAM, recursos ou registros sem geometria. Os processos identificados são os vinculados nos dados consultados e os números CNJ informados; confira os portais dos órgãos.')
    report=dict(version='3.5.2',generated_at=now(),elapsed_seconds=round(clock()-start,2),time_budget_seconds=min(300,seconds),
        state='cancelled' if cancelled() else 'time_limit' if not budget.remaining() else 'finished',
        property={'name':str(context.get('name','Imóvel')),'uf':context['uf'],'car':display_car(context['car']),
                  'bbox':context['rect'],'geometry_wkt':context['wkt'],'crs':'EPSG:4326','geometry_sha256':hashlib.sha256(context['wkt'].encode()).hexdigest(),
                  'parcel_area_ha':context.get('parcel_area_ha')},
        sources=[sources[s] for s in LABELS],
        scope='Triagem documental e espacial de bases públicas. Não é certidão negativa, decisão de regularidade ambiental, confirmação de vigência do ato ou garantia de inexistência de processos.')
    return report
