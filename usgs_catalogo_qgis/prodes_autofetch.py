# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Anonymous evidence acquisition; plain-value payloads only, safe for workers."""
import calendar
import json
from datetime import date, timedelta

from .archive import LocalArchive
from .public_sources import MultiCatalog as PublicCatalog, merge_scenes
from .prodes import ProdesError
from .prodes_auto import scene_metadata, sample_polygon, run_analysis

COLLECTIONS = ['landsat-c2-l2']
KEYS = ['swir16', 'nir08', 'red']
POLICY = {'season_window_days': 30, 'candidate_limit': 3, 'page_limit': 5,
          'scene_cloud_max_exclusive': 20, 'valid_coverage_min': .8,
          'historical_reference_year': 2007}


def window(year, reference, radius=30):
    month, day = reference.month, reference.day
    anchor = date(year, month, min(day, calendar.monthrange(year, month)[1]))
    return anchor, max(date(year, 1, 1), anchor - timedelta(days=radius)), min(date(year, 12, 31), anchor + timedelta(days=radius))


def platform(item):
    return str(item.get('properties', {}).get('platform', ''))


def candidates(client, archive, year, reference, cancelled, warnings, radius=30, offline=False):
    anchor, start, end = window(year, reference, radius)
    items = archive.search(COLLECTIONS, start.isoformat(), end.isoformat())
    if offline:
        return filter_candidates(merge_scenes(items),archive,start,end,anchor)
    link, visited = None, set()
    try:
        for _ in range(POLICY['page_limit']):
            if cancelled():
                raise ProdesError('Operação cancelada.')
            page, following = client.search(COLLECTIONS, archive.rect, start.isoformat(), end.isoformat(), link)
            items.extend(page)
            warnings.extend(getattr(page,'warnings',[]))
            if not following:
                break
            fingerprint = json.dumps(following, sort_keys=True)
            if fingerprint in visited:
                warnings.append('Paginação repetida; consulta interrompida sem repetir páginas.')
                break
            visited.add(fingerprint)
            link = following
        else:
            warnings.append('Limite de cinco páginas atingido; catálogo do período pode estar incompleto.')
    except Exception as exc:
        if cancelled():
            raise ProdesError('Operação cancelada.') from exc
        warnings.append('Consulta online indisponível; usando acervo local quando existente: ' + str(exc))
    return filter_candidates(merge_scenes(items),archive,start,end,anchor)


def filter_candidates(items,archive,start,end,anchor):
    unique = {}
    for item in items:
        props = item.get('properties', {})
        acquired = str(props.get('datetime', ''))[:10]
        try:
            cloud = float(props['eo:cloud_cover'])
            date.fromisoformat(acquired)
        except (KeyError, TypeError, ValueError):
            continue
        if (item.get('collection') in COLLECTIONS and start.isoformat() <= acquired <= end.isoformat()
                and 0 <= cloud < 20 and all(key in item.get('assets', {}) for key in KEYS)):
            unique[archive.scene_key(item)] = item
    result = list(unique.values())
    result.sort(key=lambda item: (abs((date.fromisoformat(item['properties']['datetime'][:10]) - anchor).days),
                                 float(item['properties']['eo:cloud_cover'])))
    archive.remember_many(result)
    return result


def reference_date(item):
    value = str(item.get('image_date', '') or '')[:10]
    try:
        acquired = date.fromisoformat(value)
        if acquired.year == int(item['year']):
            return acquired
    except (ValueError, TypeError):
        pass
    # July 31 is an explicit fallback, never presented as an official image date.
    return date(int(item['year']), 7, 31)


def run_autofetch(payload, progress=lambda text: None, cancelled=lambda: False,
                  client_factory=PublicCatalog, archive_factory=LocalArchive, audit=lambda kind,details:None):
    from .prodes_agent import settings, refinement_targets
    robotic = bool(payload.get("agent_enabled"))
    agent_settings = settings(payload) if robotic else {"candidate_limit":POLICY["candidate_limit"]}
    selection_geometry = payload["parcel_geometry"]
    selection_log = []
    active_uuid = ""
    quality_cache = {}
    client = client_factory(cancelled=cancelled)
    archive = archive_factory(payload['archive_root'], payload['rect'], payload['target_crs'])
    output = dict(payload, images=[], dates=[], historical_image=None, acquisition_policy=dict(POLICY, requested_cloud_max=payload.get('agent_cloud_max',20), requested_cloud_strict=payload.get('agent_cloud_strict',True)),
                  acquisition_warnings=[], acquisition_groups=[])
    results, acquired_cache, maps, search_cache = [None] * len(payload['rows']), {}, {}, {}
    def options_for(year, reference, radius=30):
        key = (year, reference.month, reference.day, radius)
        if key not in search_cache:
            search_cache[key] = candidates(client, archive, year, reference, cancelled, output['acquisition_warnings'], radius, offline=payload.get('agent_offline',False))
            from .commands import cloud_allowed
            search_cache[key] = [scene for scene in search_cache[key] if cloud_allowed(scene.get('properties',{}).get('eo:cloud_cover'), {'cloud_max':payload.get('agent_cloud_max',20),'cloud_strict':payload.get('agent_cloud_strict',True)})]
        return search_cache[key]
    groups = {}
    for index, item in enumerate(payload['rows']):
        if not item.get('year'):
            raise ProdesError('Polígono sem ano: use incrementos anuais PRODES por bioma.')
        reference = reference_date(item)
        groups.setdefault((int(item['year']), reference.isoformat(), index if robotic else None), []).append(index)

    def prepare_selected_nbr(image):
        if not image or not payload.get('history_enabled') or image.get('nbr_path') or image.get('nbr_error'):
            return image
        item = selected_items[image['scene_id']]
        folder = archive.scene_folder(item)
        try:
            _, errors, path = client.download_scene(item, folder, archive.rect,
                payload['target_crs'], progress, [], product='nbr', **({'offline':True} if payload.get('agent_offline') else {}))
            image['nbr_path'] = path
            output['acquisition_warnings'].extend(errors)
        except Exception as exc:
            if cancelled():raise ProdesError('Operação cancelada.') from exc
            image['nbr_error'] = str(exc)
            output['acquisition_warnings'].append(item['id'] + ': NBR indisponível; fogo não avaliado: ' + str(exc))
        return image

    selected_items = {}
    def acquire(options, preferred=''):
        ordered = sorted(options, key=lambda item: (bool(preferred) and platform(item) != preferred,
                         options.index(item)))
        best, score = None, (-1, -1, -1, -1, -100)
        for item in ordered[:agent_settings['candidate_limit']]:
            if cancelled():
                raise ProdesError('Operação cancelada.')
            selected_items[item['id']] = item
            key = archive.scene_key(item)
            if key in acquired_cache:
                image, quality = acquired_cache[key]
            else:
                try:
                    progress('Preparando PRODES RGB e máscaras: ' + item['id'])
                    folder = archive.scene_folder(item)
                    _, errors, path = client.download_scene(item, folder, archive.rect,
                        payload['target_crs'], progress, KEYS, **({'offline':True} if payload.get('agent_offline') else {}))
                    archive.remember(item, errors)
                    image = {'path': path, 'name': item['id'] + ' · PRODES RGB',
                        'date': item['properties']['datetime'][:10], 'scene_id': item['id'],
                        'bands': [1, 2, 3], 'metadata': scene_metadata(item, KEYS, folder),
                        'scene_cloud_cover': item['properties']['eo:cloud_cover']}
                    quality = sample_polygon(selection_geometry, [image], cancelled, historical=True)
                    quality_cache[(key,selection_geometry)] = quality
                    acquired_cache[key] = image, quality
                except Exception as exc:
                    if cancelled():
                        raise ProdesError('Operação cancelada.') from exc
                    output['acquisition_warnings'].append(item['id'] + ': ' + str(exc))
                    continue
            if robotic:
                quality_key = (key, selection_geometry)
                if quality_key not in quality_cache:
                    try:
                        quality_cache[quality_key] = sample_polygon(selection_geometry, [image], cancelled, historical=True)
                    except Exception as exc:
                        if cancelled():raise ProdesError('Operação cancelada.') from exc
                        quality_cache[quality_key] = {'error':str(exc)}
                quality = quality_cache[quality_key]
            qa = bool(quality.get('qa_complete')) and not quality.get('error')
            coverage = float(quality.get('common_coverage', 0))
            pixels = int(quality.get('common_pixels', 0))
            acceptable = qa and coverage >= POLICY['valid_coverage_min'] and (pixels >= 9 if robotic else True)
            rank = (int(acceptable), int(qa), coverage, pixels, -float(image.get('scene_cloud_cover',100)))
            if robotic:
                entry = {'uuid':active_uuid,'scene_id':image['scene_id'],'date':image['date'],
                         'platform':platform(item),'qa_complete':qa,'coverage':coverage,'pixels':pixels,
                         'usable':acceptable,'selected':False,'reason':'Amostra e QA suficientes' if acceptable else quality.get('error') or 'QA, cobertura ou quantidade de pixels insuficientes'}
                selection_log.append(entry)
                audit('candidata',entry)
            if rank > score:
                best, score = image, rank
                best['aoi_quality'] = quality
            if acceptable and not robotic:
                return prepare_selected_nbr(image)
        if robotic and best:
            for entry in reversed(selection_log):
                if entry['uuid']==active_uuid and entry['scene_id']==best['scene_id']:
                    entry['selected']=True
                    audit('selecao',dict(entry, reason='Maior qualidade local entre as candidatas examinadas; seleção não garante comparação temporal'))
                    break
        return prepare_selected_nbr(best)

    for (year, reference_text, _), indices in groups.items():
        selection_log = []
        active_uuid = payload["rows"][indices[0]].get("uuid", str(indices[0]))
        selection_geometry = payload["geometries"][indices[0]] if robotic else payload["parcel_geometry"]
        reference = date.fromisoformat(reference_text)
        progress('Buscando sequência {} / {} / {}…'.format(year, year - 1, year - 2))
        choices = [options_for(y, reference)
                   for y in (year, year - 1, year - 2)]
        common = set.intersection(*(set(platform(item) for item in values) for values in choices)) - {''}
        priority = ['landsat-8', 'landsat-5', 'landsat-7', 'landsat-9', 'landsat-4']
        preferred = next((value for value in priority if value in common), next(iter(sorted(common)), ''))
        # When a common platform exists do not silently substitute another sensor.
        selected = [acquire([item for item in values if not preferred or platform(item) == preferred], preferred)
                    for values in choices]
        if robotic:
            for position, chosen in enumerate(selected):
                quality = chosen.get('aoi_quality', {}) if chosen else {}
                if not chosen or not (quality.get('qa_complete') and quality.get('common_coverage',0)>=.8 and quality.get('common_pixels',0)>=9):
                    options = options_for(year-position, reference, agent_settings['fallback_radius'])
                    alternative = acquire([v for v in options if not preferred or platform(v)==preferred], preferred)
                    if alternative:selected[position]=alternative
        historic = None
        if payload.get('consolidated_technical') and any(payload['rows'][i].get('consolidated_ha', 0) > 0 for i in indices):
            old = [image for image in selected if image and image['date'] < '2008-07-22']
            historic = old[0] if old else acquire(options_for(2007, reference))
        group = {'year': year, 'reference_date': reference_text, 'indices': indices,
                 'images': selected, 'historical_image': historic, 'preferred_platform': preferred,
                 'reference_date_source': 'image_date PRODES' if str(payload['rows'][indices[0]].get('image_date', ''))[:10] == reference_text else 'Fallback explícito: 31 de julho'}
        output['acquisition_groups'].append(group)
        if all(selected):
            subset = dict(payload, rows=[payload['rows'][i] for i in indices],
                geometries=[payload['geometries'][i] for i in indices],
                consolidated_geometries=[payload['consolidated_geometries'][i] for i in indices],
                images=selected, dates=[image['date'] for image in selected], historical_image=historic)
            group_results = run_analysis(subset, progress, cancelled)
        else:
            reason = 'Sequência anual incompleta: não foram obtidas três imagens com bandas PRODES no período de ±30 dias, nuvens de cena <20%. Consulta/acervo insuficientes; tente novamente ou selecione imagens manualmente.'
            group_results = [{'mode': 'automatic', 'status': 'Evidências insuficientes', 'reason': reason,
                'automatic': {'error': reason}, 'dates': [image['date'] for image in selected if image],
                'contestability': {'status': 'Evidências insuficientes', 'reason': reason,
                    'scope_ha': 0, 'legal_basis': 'Lei 12.651/2012, art. 3º, IV: classificação técnica requer evidências.',
                    'technical_basis': 'INPE: comparação temporal e revisão do registro, sem decisão de legalidade.'},
                'historical': {'status': 'Não avaliada', 'reason': 'Sequência incompleta.'}}
                for _ in indices]
        history_images = []
        requested_years = []
        if payload.get('history_enabled'):
            from .prodes_history import interpret_history
            start = max(1982, min(year-2, int(payload.get('history_start_year', 1985))))
            end = min(date.today().year, year+2)
            requested_years = list(range(start, end+1))
            selected_by_year = {int(image['date'][:4]): image for image in selected if image}
            if historic:
                selected_by_year.setdefault(int(historic['date'][:4]), historic)
            for historic_year in reversed(requested_years):
                if cancelled():
                    raise ProdesError('Operação cancelada.')
                progress('Histórico {}: buscando {} ({}–{})…'.format(year, historic_year, start, end))
                image = selected_by_year.get(historic_year)
                if image is None:
                    values = options_for(historic_year, reference)
                    platforms = {platform(item) for item in values}
                    favorite = next((value for value in priority if value in platforms), '')
                    image = acquire([item for item in values if not favorite or platform(item) == favorite], favorite)
                if image:
                    history_images.append(image)
            history_images.sort(key=lambda image: image['date'])
            group['history_images'] = history_images
            group['searched_years'] = requested_years
            for position, index in enumerate(indices):
                progress('Lendo histórico do polígono {}…'.format(payload['rows'][index].get('uuid', index+1)))
                try:
                    timeline = sample_polygon(payload['geometries'][index], history_images, cancelled, timeline=True) if history_images else {'observations': [], 'pairs': []}
                except Exception as exc:
                    if cancelled():
                        raise ProdesError('Operação cancelada.') from exc
                    timeline = {'observations': [], 'pairs': [], 'error': str(exc)}
                if robotic and history_images and timeline.get('observations'):
                    used = set()
                    for attempt in range(agent_settings['refinements']):
                        targets = refinement_targets(timeline, used)
                        if not targets:break
                        target = targets[0];used.add(target['date'])
                        anchor=date.fromisoformat(target['date'])
                        options=options_for(anchor.year,anchor,16)
                        matching=[v for v in options if target['before'] < v['properties']['datetime'][:10] < target['after']]
                        before_image=next((v for v in history_images if v['date']==target['before']),None)
                        desired=before_image['metadata'].get('platform','') if before_image else ''
                        matching=[v for v in matching if not desired or platform(v)==desired]
                        audit('refinamento',dict(target,uuid=active_uuid,attempt=attempt+1,candidates=len(matching)))
                        image=acquire(matching,desired)
                        if not image or image['scene_id'] in {v['scene_id'] for v in history_images}:continue
                        history_images.append(image);history_images.sort(key=lambda v:v['date'])
                        try:
                            timeline=sample_polygon(payload['geometries'][index],history_images,cancelled,timeline=True)
                        except Exception as exc:
                            if cancelled():raise ProdesError('Operação cancelada.') from exc
                            history_images.remove(image)
                            output['acquisition_warnings'].append('Refinamento não incorporado: '+str(exc))
                base = dict(group_results[position]['contestability'], spectral_status=group_results[position]['status'])
                base['reason'] = base.get('rule_reason', base.get('reason', ''))
                base.pop('rule_reason', None)
                history = interpret_history(payload['rows'][index], timeline, requested_years, base,
                    payload['annual'], payload['tolerance'], payload.get('consolidated_technical', False), payload.get('amazon_forest', False))
                if robotic:
                    history['map_scene_ids']=history['map_scene_ids'][:10]
                group_results[position]['history'] = history
                group_results[position]['contestability'] = history['recommendation']
        for index, result in zip(indices, group_results):
            result['acquisition'] = {'year': year, 'reference_date': reference_text,
                'dates': [image['date'] if image else None for image in selected],
                'scene_ids': [image['scene_id'] if image else None for image in selected],
                'historical_scene': historic['scene_id'] if historic else None, 'selection':selection_log if robotic else []}
            from .prodes_argument import attach_argumentation
            attach_argumentation(payload['rows'][index], result)
            results[index] = result
        map_ids = {scene for result in group_results for scene in result.get('history', {}).get('map_scene_ids', [])}
        for image in selected + [historic] + [image for image in history_images if image['scene_id'] in map_ids]:
            if image:
                maps.setdefault(image['path'], image)
        if historic and output['historical_image'] is None:
            output['historical_image'] = historic
    available = {}
    for group in output['acquisition_groups']:
        for image in group['images'] + [group.get('historical_image')] + group.get('history_images', []):
            if image:
                available.setdefault(image['path'], image)
    output['available_images'] = list(available.values())
    output['images'] = list(maps.values())
    output['dates'] = [image['date'] for image in output['images']]
    return {'results': results, 'payload': output}
