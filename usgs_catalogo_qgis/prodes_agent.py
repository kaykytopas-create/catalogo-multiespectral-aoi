# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded adaptive investigation, evidence ledger and reproducible hypotheses."""
import hashlib
import json
import os
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4
from .prodes import ProdesError
from .prodes_knowledge import retrieve, KNOWLEDGE_VERSION

AGENT_VERSION = '3.2.0-agent-1'
PROFILES = {'rapido': {'candidate_limit':3,'refinements':1,'fallback_radius':45},
            'equilibrado': {'candidate_limit':5,'refinements':3,'fallback_radius':60},
            'aprofundado': {'candidate_limit':8,'refinements':6,'fallback_radius':60}}


def settings(payload):
    profile = payload.get('agent_profile','equilibrado')
    if profile not in PROFILES:raise ProdesError('Perfil de investigação desconhecido.')
    return dict(PROFILES[profile], profile=profile)


class Audit:
    def __init__(self, root, payload):
        self.run_id=uuid4().hex
        self.directory=Path(root)/'investigacoes'/self.run_id
        self.directory.mkdir(parents=True,exist_ok=False)
        self.previous='';self.sequence=0
        self.state={'run_id':self.run_id,'version':AGENT_VERSION,'status':'planejada',
                    'created_utc':datetime.now(timezone.utc).isoformat(),
                    'input_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()}
        self.checkpoint('planejada')
    def event(self, kind, details):
        self.sequence+=1
        value={'sequence':self.sequence,'utc':datetime.now(timezone.utc).isoformat(),
               'kind':kind,'details':details,'previous_sha256':self.previous}
        self.previous=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        value['sha256']=self.previous
        with (self.directory/'events.jsonl').open('a',encoding='utf8') as stream:
            stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
            stream.flush()
        return value
    def checkpoint(self,status,**extra):
        self.state.update(status=status,events=self.sequence,last_sha256=self.previous,**extra)
        path=self.directory/'session.json';temp=path.with_suffix('.part')
        temp.write_text(json.dumps(self.state,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
        os.replace(temp,path)
    def receipt(self):return dict(self.state,directory=str(self.directory))


def verify_events(path):
    previous='';count=0
    for line in Path(path).read_text(encoding='utf8').splitlines():
        value=json.loads(line);digest=value.pop('sha256');count+=1
        if value['sequence']!=count or value['previous_sha256']!=previous:
            return False
        previous=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
        if digest!=previous:return False
    return True


def refinement_targets(history, used=()):
    """Search an intermediate date in eligible intervals, never invent an event."""
    targets=[];seen=set(used)
    pairs=history.get('pairs',[])
    ordered=sorted(pairs,key=lambda p:(not p.get('loss'),not p.get('burn_signal'),-(p.get('gap_days') or 0)))
    for pair in ordered:
        if not pair.get('usable'):continue
        before,after=date.fromisoformat(pair['before']),date.fromisoformat(pair['after'])
        if (after-before).days < 120:continue
        middle=before+(after-before)//2
        if (after-before).days>550:
            middle=date(middle.year,before.month,min(before.day,28))
        elif (after-before).days>180:
            middle=before+timedelta(days=24)
        if not before<middle<after:continue
        key=middle.isoformat()
        if key not in seen:
            targets.append({'date':key,'before':pair['before'],'after':pair['after'],
                            'platform':pair.get('platform',''),'reason':'Reduzir intervalo de mudança' if pair.get('loss') else 'Conferir lacuna entre observações'})
            seen.add(key)
    return targets


def dossier(item,result,selections,technical=False):
    history=result.get('history',{})
    valid=[v for v in history.get('observations',[]) if v.get('usable')]
    losses=[v for v in history.get('pairs',[]) if v.get('usable') and v.get('loss')]
    year=item.get('year',0)
    def h(code,title,values,explanation):
        return {'id':code,'title':title,'status':'Indício a conferir' if values else 'Não demonstrada neste processamento',
                'evidence_ids':list(dict.fromkeys(scene for v in values for scene in
                    ([v['scene_id']] if 'scene_id' in v else [v.get('before_scene',''),v.get('after_scene','')]) if scene)),
                'explanation':explanation}
    hypotheses=[
        h('H_EARLY','Alteração anterior ao registro',[v for v in losses if int(v['after'][:4])<year-1], 'Intervalo espectral não é data exata nem identifica a origem da vegetação.'),
        h('H_CURRENT','Alteração próxima do registro',[v for v in losses if year-1<=int(v['after'][:4])<=year], 'Um novo evento pode coexistir com ocupação antiga; conferir o mesmo recorte.'),
        h('H_LATE','Alteração posterior à referência',[v for v in losses if int(v['after'][:4])>year and v['before']>=str(item.get('image_date') or f'{year}-07-31')[:10]], 'Conferir o estado da área na imagem oficial antes de propor outra data.'),
        h('H_FIRE','Perturbação compatível com fogo',[history['burn_event']] if history.get('burn_event') else [], 'Sinal exploratório; não identifica causa, autoria ou exclusão do PRODES.')]
    pre=[v for v in valid if v['date']<'2008-07-22']
    hypotheses.append({'id':'H_OCCUPATION','title':'Ocupação anterior ao marco','status':('Classificação técnica a corroborar' if technical else 'Sobreposição geométrica; enquadramento técnico não confirmado') if item.get('consolidated_ha',0)>0 else 'Sem sobreposição consolidada informada',
        'evidence_ids':[v['scene_id'] for v in pre if v.get('scene_id')],
        'explanation':'A ocupação e o uso devem ser comprovados. Imagens pré-marco disponíveis não reconhecem consolidação jurídica automaticamente.'})
    missing=history.get('missing_years',[])
    questions=[]
    if not pre:questions.append('Obter evidência utilizável anterior a 22/07/2008 para conferir a ocupação técnica informada.')
    if not losses:questions.append('A série não localizou uma perda comparável; conferir textura e imagem oficial sem atribuir uma nova data.')
    if missing:questions.append('Conferir os anos sem observação utilizável: '+', '.join(map(str,missing))+'.')
    if not valid:questions.append('A amostra não permite interpretação espectral: considerar imagem de resolução adequada e análise técnica independente.')
    if len(losses)>1:questions.append('Distinguir perda antiga, nova perda e regeneração antes de propor correção temporal.')
    overlap=item.get('consolidated_ha',0);clip=item.get('clip_ha',0)
    if overlap and clip and overlap/clip<.95:questions.append('Limitar a indicação documental aos {:.4f} ha sobrepostos; não estendê-la ao restante do recorte.'.format(overlap))
    evidence=[{'id':v.get('scene_id',''),'date':v['date'],'usable':v.get('usable',False),
               'pixels':v.get('pixels'), 'coverage':v.get('coverage'),'ndvi':v.get('ndvi'),'ndmi':v.get('ndmi')} for v in history.get('observations',[])]
    tags=['consolidada'] if overlap else []
    if history.get('burn_event'):tags.append('fogo')
    if item.get('core_ha') is not None:tags.append('borda')
    return {'version':AGENT_VERSION,'hypotheses':hypotheses,'evidence':evidence,'questions':questions,
            'selection':selections,'references':retrieve(tags),'knowledge_version':KNOWLEDGE_VERSION,
            'visual_status':'Não solicitada','adequacy':('Amostra utilizável para pares compatíveis; interpretação requer revisão' if any(p.get('usable') for p in history.get('pairs',[])) else 'Há observação utilizável, mas falta comparação temporal compatível') if valid else 'Amostra insuficiente',
            'conclusion_scope':'Triagem experimental, sem precisão temática validada'}


def run_investigation(payload, progress=lambda text:None,cancelled=lambda:False,fetcher=None):
    from .prodes_autofetch import run_autofetch
    fetcher=fetcher or run_autofetch
    options=settings(payload)
    audit=Audit(payload['archive_root'],payload)
    plan=[{'uuid':row.get('uuid'),'year':row.get('year'),'start_year':max(1982,min(row['year']-2,int(payload.get('history_start_year',1985)))),
           'end_year':min(date.today().year,row['year']+2),'questions':['data','qualidade','consolidada','perturbacao']} for row in payload['rows']]
    audit.event('plano',{'polygons':plan,'profile':options,'cloud_filter':'<20% da cena + QA local'})
    audit.checkpoint('adquirindo_imagens',plan=plan)
    try:
        value=fetcher(dict(payload,agent_enabled=True),progress,cancelled,audit=audit.event)
        for item,result in zip(payload['rows'],value['results']):
            choices=result.get('acquisition',{}).get('selection',[])
            result['agent']=dossier(item,result,choices,payload.get('consolidated_technical',False))
            audit.event('analise_poligono',{'uuid':item.get('uuid'),'status':result.get('contestability',{}).get('status'),
                'hypotheses':result['agent']['hypotheses'],'adequacy':result['agent']['adequacy']})
        audit.checkpoint('analise_espectral_concluida',polygons=len(value['results']))
        value['payload']['investigation']=audit.receipt()
        return value
    except Exception as exc:
        audit.event('interrupcao',{'error':str(exc)})
        audit.checkpoint('cancelada' if cancelled() else 'falhou')
        raise


def visual_scene_order(row):
    history=row.get('history',{})
    wanted=[]
    for key in ('first_observed_loss','burn_event'):
        event=history.get(key,{})
        wanted.extend(event.get(field) for field in ('before_scene','after_scene','recovery_scene') if event.get(field))
    reference=str(row.get('image_date') or '{}-07-31'.format(row.get('year',0)))[:10]
    valid=[v for v in history.get('observations',[]) if v.get('usable') and v.get('scene_id')]
    valid.sort(key=lambda v:abs((date.fromisoformat(v['date'])-date.fromisoformat(reference)).days))
    wanted.extend(v['scene_id'] for v in valid)
    return list(dict.fromkeys(wanted))[:4]


def append_event(receipt,kind,details):
    """Continue the same local chain for map and visual-assistant stages."""
    directory=Path(receipt['directory'])
    state=json.loads((directory/'session.json').read_text(encoding='utf8'))
    if not verify_events(directory/'events.jsonl'):raise ProdesError('Registro de investigação inconsistente.')
    lines=(directory/'events.jsonl').read_text(encoding='utf8').splitlines()
    last=json.loads(lines[-1]) if lines else {}
    if len(lines)!=state['events'] or last.get('sha256','')!=state['last_sha256']:
        raise ProdesError('Estado e cadeia de eventos não correspondem.')
    audit=Audit.__new__(Audit);audit.directory=directory;audit.state=state
    audit.run_id=state['run_id'];audit.sequence=state['events'];audit.previous=state['last_sha256']
    audit.event(kind,details);audit.checkpoint(state['status'])
    receipt.update(audit.receipt())
