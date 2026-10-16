# SPDX-License-Identifier: GPL-2.0-or-later
"""Restricted Portuguese task planner. Does not run Python or shell from text."""
import re
import unicodedata
from datetime import date
from .stac import CatalogError, preset_keys, index_keys, slc_gap_scene


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if unicodedata.category(c) != 'Mn')


def cloud_constraint(value):
    matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*%', value)
    if not matches:
        if re.search(r'nuvens|nebulosidade', value):
            raise CatalogError('Informe a taxa com o símbolo %: por exemplo, 0% de nuvens.')
        return 20.0, True
    if len(matches)!=1 or not re.search(r'nuvens|nebulosidade', value):
        raise CatalogError('Informe uma única taxa de nuvens, como 0% de nuvens.')
    maximum=float(matches[0].replace(',','.'))
    if not 0 <= maximum <= 20:raise CatalogError('O limite permitido de nuvens é de 0 a 20%; o catálogo permanece restrito a menos de 20%.')
    strict = bool(re.search(r'menos de\s*'+re.escape(matches[0])+r'\s*%|<\s*'+re.escape(matches[0])+r'\s*%', value)) or maximum==20
    if strict and maximum==0:raise CatalogError('Menos de 0% não é possível. Use 0% de nuvens.')
    return maximum,strict


def offline_source(value):
    if re.search(r'modo offline|sem internet|sem rede|somente (?:o )?acervo local',value):return True
    return 'offline' in value and 'acervo offline' not in value


def parse_command(text, current_year=None, default_preset='prodes'):
    value = normalize(text)
    current_year = current_year or date.today().year
    if len(value)>1000:raise CatalogError('Comando muito longo. Use uma tarefa por vez.')
    if any(word in value for word in ('classificar','classificacao','k-means','kmeans')):
        raise CatalogError('Classificação temática não está implementada. É possível baixar/importar bandas, mas nenhum classificador será executado silenciosamente.')
    cloud,strict=cloud_constraint(value)
    years=re.findall(r'(?<!\d)\d{4}(?!\d)',value)
    if re.search(r'analis|investig|relatorio',value) and re.search(r'prodes|prodios|imovel',value):
        if re.search(r'baix|import',value):raise CatalogError('Separe download de imagens e investigação PRODES em duas tarefas.')
        if len(years)>1:raise CatalogError('Para investigar, indique um ano PRODES ou todos os anos. O período histórico é configurado na central.')
        year=int(years[0]) if years else None
        if year is not None and not 1988<=year<=current_year:raise CatalogError('Ano PRODES inválido.')
        return {'action':'investigate','profile':'aprofundado' if 'aprofund' in value else ('rapido' if 'rapid' in value else 'equilibrado'),
                'offline':offline_source(value),'year':year,'cloud_max':cloud,'cloud_strict':strict,'cloud_explicit':'%' in value}
    if not re.search(r'baix|busc|pesquis|import|salv|peg',value):
        raise CatalogError('Use: baixe e importe uma imagem por ano de 2000 a 2008 com 0% de nuvens; ou investigue PRODES e gere relatório.')
    if len(years)!=2:raise CatalogError('Informe exatamente dois anos: de 2000 a 2008.')
    start,end=map(int,years)
    if start<1982:raise CatalogError('O catálogo começa em 1982. Se quis dizer 1985 em vez de 1885, corrija o comando.')
    if start>end or end>current_year:raise CatalogError('Período inválido: verifique a ordem dos anos e não use um ano futuro.')
    matches=[]
    for pattern,identifier in [(r'\bcor natural\b|\bcores naturais\b|\bnatural\b','natural'),(r'prodes','prodes'),(r'infravermelho(?: de)? vegetacao','infrared'),(r'ndvi','ndvi'),(r'nbr','nbr')]:
        if re.search(pattern,value):matches.append(identifier)
    if len(set(matches))>1:raise CatalogError('Escolha uma composição por tarefa, como cor natural ou PRODES.')
    preset=matches[0] if matches else default_preset
    if preset not in ('natural','prodes','infrared','ndvi','nbr'):raise CatalogError('Especifique cor natural, PRODES, infravermelho vegetação, NDVI ou NBR.')
    action='download' if re.search(r'baix|import|salv|peg',value) else 'search'
    negative=bool(re.search(r'sem importar|nao.{0,40}(?:import|qgis)|somente baixar|apenas baixar|so baixar|so baixe',value))
    auto_import=bool(re.search(r'import|qgis',value)) and not negative
    return {'action':action,'start':f'{start}-01-01','end':f'{end}-12-31','preset':preset,
            'selection':'all_dates' if 'todas as datas' in value else 'annual',
            'collections':['sentinel-2-l2a'] if 'sentinel' in value else ['landsat-c2-l2'],'offline':offline_source(value),
            'cloud_max':cloud,'cloud_strict':strict,'auto_import':action=='download' and auto_import}


def describe_plan(plan):
    cloud=('menos de ' if plan.get('cloud_strict',True) else 'até ')+str(plan.get('cloud_max',20)).replace('.0','')+'% de nuvens da cena'
    if plan['action']=='investigate':
        return 'Investigar PRODES {} e gerar relatório; perfil {}; {}. Usa o limite selecionado e a consolidada configurada na central. Fonte: {}.'.format(plan.get('year') or 'todos os anos configurados',plan['profile'],cloud,'acervo/cache local' if plan['offline'] else 'online com cache')
    return '{} {} · {} a {} · {} · {} · {}. {} Sem relaxar filtros; ausência/falha será informada.'.format(
        'Baixar' if plan['action']=='download' else 'Buscar',plan['preset'],plan['start'],plan['end'],
        'uma cena por data, até 200' if plan['selection']=='all_dates' else 'uma cena por ano','offline' if plan['offline'] else 'online com cache',cloud,
        'Adicionar camadas automaticamente ao QGIS.' if plan.get('auto_import') else 'Somente listar/salvar no acervo.')


def cloud_allowed(cloud, plan):
    try:cloud=float(cloud)
    except (TypeError,ValueError):return False
    if not 0<=cloud<20:return False
    maximum=plan.get('cloud_max',20)
    return cloud<maximum if plan.get('cloud_strict',True) else cloud<=maximum


def select_scenes(items, plan, hide_slc=False, all_candidates=False):
    from .public_sources import merge_scenes
    items=merge_scenes(items)
    eligible=[]
    for item in items:
        props=item.get('properties',{});when=str(props.get('datetime',''))[:10]
        try: cloud=float(props.get('eo:cloud_cover'))
        except (TypeError,ValueError):continue
        keys=index_keys(item,plan['preset']) if plan['preset'] in ('ndvi','nbr') else preset_keys(item,plan['preset'])
        if not (plan['start'] <= when <= plan['end'] and item.get('collection') in plan['collections'] and cloud_allowed(cloud,plan) and keys):continue
        if hide_slc and slc_gap_scene(item):continue
        eligible.append(item)
    eligible.sort(key=lambda x:(float(x['properties']['eo:cloud_cover']),str(x['properties']['datetime']),str(x.get('id'))))
    if all_candidates:return eligible
    selected={}
    for item in eligible:
        when=str(item['properties']['datetime'])[:10]
        key=when if plan['selection']=='all_dates' else when[:4]
        selected.setdefault(key,item)
    result=[selected[k] for k in sorted(selected)]
    if len(result)>200:raise CatalogError('Mais de 200 datas elegíveis. Reduza o período antes de baixar.')
    return result


def collect_scenes(client, archive, plan, progress, hide_slc=False, all_candidates=False):
    from .archive import digest
    if plan['offline']:
        return select_scenes(archive.search(plan['collections'],plan['start'],plan['end']),plan,hide_slc,all_candidates)
    items=[];link=None;visited=set();warnings=[]
    for page_number in range(100):
        if client.cancelled():raise CatalogError('Operação cancelada; arquivos concluídos foram preservados.')
        progress('Consultando página {} do período…'.format(page_number+1))
        page,link=client.search(plan['collections'],archive.rect,plan['start'],plan['end'],link)
        items.extend(page);warnings.extend(getattr(page,'warnings',[]))
        if not link:
            from .public_sources import SearchResults
            return SearchResults(select_scenes(items,plan,hide_slc,all_candidates),list(dict.fromkeys(warnings)))
        signature=digest(link)
        if signature in visited:raise CatalogError('Paginação repetida na fonte. Busca interrompida sem baixar uma seleção incompleta.')
        visited.add(signature)
    raise CatalogError('Consulta excedeu 100 páginas; reduza o período.')


def download_batch(client, archive, plan, progress, hide_slc=False, on_ready=None):
    import json, os, uuid
    from datetime import datetime, timezone
    from .catalog_quality import quality_allowed
    from .raster_quality import inspect_raster
    candidates=collect_scenes(client,archive,plan,progress,hide_slc,True)
    archive.remember_many(candidates)
    groups={}
    for item in candidates:
        when=item['properties']['datetime'][:10]
        groups.setdefault(when if plan['selection']=='all_dates' else when[:4],[]).append(item)
    if len(groups)>200:raise CatalogError('Mais de 200 datas elegíveis; reduza o período.')
    years=set(range(int(plan['start'][:4]),int(plan['end'][:4])+1))
    receipt={'source_warnings':getattr(candidates,'warnings',[]),'missing_years':[], 'plan':plan,'selection_basis':'QA local no imóvel, integridade das bandas e nebulosidade da cena; filtros preservados',
             'created':datetime.now(timezone.utc).isoformat(),'results':[],'attempts':[]}
    path=os.path.join(archive.folder,'lote_'+uuid.uuid4().hex+'.json')
    def persist():
        with open(path+'.part','w',encoding='utf8') as stream:json.dump(receipt,stream,ensure_ascii=False,indent=2)
        os.replace(path+'.part',path)
    def cancelled():
        if client.cancelled():raise CatalogError('Operação cancelada; arquivos concluídos foram preservados.')
    scenes=[]
    persist()
    try:
        for group,items in sorted(groups.items()):
            ranked=[]
            for item in items:
                cancelled();quality=None
                try:
                    if hasattr(client,'assess_scene_quality'):
                        progress('Conferindo qualidade no imóvel: '+item['properties']['datetime'][:10])
                        quality=client.assess_scene_quality(item,archive.scene_folder(item),archive.rect,archive.target_crs,progress,plan.get('geometry_wkt'),plan['offline'])
                        if not quality_allowed(quality,plan):
                            receipt['attempts'].append({'scene_id':item['id'],'status':'rejected_quality','quality':quality});persist();continue
                    ranked.append((item,quality))
                except Exception as exc:
                    cancelled();receipt['attempts'].append({'scene_id':item['id'],'status':'qa_failed','error':str(exc)});persist()
            ranked.sort(key=lambda pair:(-(pair[1] or {}).get('clear_fraction',0),-(pair[1] or {}).get('valid_fraction',0),float(pair[0]['properties']['eo:cloud_cover'])))
            failure=None
            for item,quality in ranked:
                cancelled()
                keys=index_keys(item,plan['preset']) if plan['preset'] in ('ndvi','nbr') else preset_keys(item,plan['preset'])
                progress('Preparando '+item['properties']['datetime'][:10]+' · '+plan['preset'])
                try:
                    files,errors,composite=client.download_scene(item,archive.scene_folder(item),archive.rect,archive.target_crs,progress,keys,
                        plan['preset'] if plan['preset'] in ('ndvi','nbr') else 'rgb',plan['offline'],False)
                    integrity=None
                    if hasattr(client,'assess_scene_quality'):
                        integrity=inspect_raster(composite,plan.get('geometry_wkt'))
                        if integrity.get('valid_fraction') is None or integrity['valid_fraction']<.99:raise CatalogError('Bandas com cobertura insuficiente no imóvel; tentando outra data.')
                    archive.remember(item,errors)
                    record={'scene_id':item['id'],'date':item['properties']['datetime'][:10],'bands':list(keys),'path':composite,'errors':errors,
                            'sources':item.get('catalog:sources',[]),'download_sources':dict(item.get('catalog:download_sources',{})),
                            'quality':quality,'integrity':integrity,'status':'completed' if not errors else 'completed_with_warnings'}
                    receipt['results'].append(record);scenes.append(item);persist()
                    if on_ready:on_ready({'item':item,'result':dict(record),'manifest':path})
                    break
                except Exception as exc:
                    cancelled();failure={'scene_id':item['id'],'date':item['properties']['datetime'][:10],'bands':list(keys),'error':str(exc),'status':'failed'}
                    receipt['attempts'].append(failure);persist()
            else:
                if failure:receipt['results'].append(failure)
        found={int(i['properties']['datetime'][:4]) for i in scenes}
        receipt['missing_years']=sorted(years-found);receipt['status']='completed';persist()
    except Exception:
        receipt['status']='interrupted';persist();raise
    return {'scenes':scenes,'receipt':receipt,'manifest':path,'missing_years':receipt['missing_years']}
