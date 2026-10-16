# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Explainable time-series evidence. Dates are observation intervals, never proof
of first clearance, native forest, fire causation or legal compliance."""
from datetime import date
import numpy as np
from .prodes_auto import THRESHOLDS

HISTORY_RULE_VERSION = '3.0.0-history-1'
HISTORY_LIMITS = {'dnbr': .27, 'fire_fraction': .60, 'recovery_tolerance': .10,
                  'recovery_fraction': .60, 'minimum_year': 1985, 'after_years': 2}


def usable(count, total, qa):
    return bool(qa and count >= THRESHOLDS['min_pixels'] and total and count / total >= THRESHOLDS['min_coverage'])


def comparable(a, b):
    am, bm = a['metadata'], b['metadata']
    if not am.get('platform') or am.get('platform') != bm.get('platform') or am['collection'] != bm['collection']:
        return False
    da, db = [date.fromisoformat(i['date']) for i in (a, b)]
    slots = [(date(2000, d.month, d.day) - date(2000, 1, 1)).days for d in (da, db)]
    distance = abs(slots[0] - slots[1])
    return min(distance, 366-distance) <= THRESHOLDS['max_season_days']


def summarise_timeline(images, indices, masks, inside, qa_flags, nir, nbr, resolution):
    total = int(inside.sum())
    observations, pairs = [], []
    for index, image in enumerate(images):
        valid = inside & masks[index]
        count = int(valid.sum())
        dv, dm = indices[index]
        low = valid & (dv >= .05) & (dv <= .35) & (dm <= .10) & (nir[index] >= .15)
        observations.append({'date': image['date'], 'scene_id': image['scene_id'],
            'platform': image['metadata'].get('platform', ''), 'pixels': count,
            'coverage': count / total if total else 0, 'qa_complete': qa_flags[index],
            'usable': usable(count, total, qa_flags[index]),
            'ndvi': float(np.median(dv[valid])) if count else None,
            'ndmi': float(np.median(dm[valid])) if count else None,
            'low_cover_fraction': int(low.sum()) / count if count else None})
    valid_positions = [i for i, observation in enumerate(observations) if observation['usable']]
    candidate_pairs=set(zip(valid_positions, valid_positions[1:]))
    # Keep a comparable seasonal/sensor pair even when an inserted observation
    # has a different season or platform. No cross-sensor numeric comparison.
    for older in valid_positions:
        newer=next((i for i in valid_positions if i>older and comparable(images[older],images[i])),None)
        if newer is not None:candidate_pairs.add((older,newer))
    for older, newer in sorted(candidate_pairs):
        a, b = images[older], images[newer]
        common = inside & masks[older] & masks[newer]
        count = int(common.sum())
        eligible = usable(count, total, qa_flags[older] and qa_flags[newer]) and comparable(a, b)
        pair = {'before': a['date'], 'after': b['date'], 'before_scene': a['scene_id'], 'after_scene': b['scene_id'],
            'pixels': count, 'coverage': count / total if total else 0, 'usable': eligible, 'platform':a['metadata'].get('platform',''),
            'gap_days': (date.fromisoformat(b['date']) - date.fromisoformat(a['date'])).days,
            'loss': False, 'burn_signal': False, 'recovery': False,
            'reason': '' if eligible else 'Pixels comuns, época do ano ou mesma plataforma insuficientes para comparar.'}
        if eligible:
            dv = indices[newer][0] - indices[older][0]
            dm = indices[newer][1] - indices[older][1]
            changed = common & (dv <= -THRESHOLDS['ndvi_drop']) & (dm <= -THRESHOLDS['ndmi_drop'])
            pair.update(delta_ndvi=float(np.median(dv[common])), delta_ndmi=float(np.median(dm[common])),
                changed_fraction=int(changed.sum()) / count,
                loss=int(changed.sum()) / count >= THRESHOLDS['changed_fraction'])
            if nbr[older] is not None and nbr[newer] is not None:
                fire_common = common & np.isfinite(nbr[older]) & np.isfinite(nbr[newer])
                nfire = int(fire_common.sum())
                qa_fire = usable(nfire, total, True)
                if qa_fire:
                    dnbr = nbr[older] - nbr[newer]
                    burned = fire_common & (dnbr >= HISTORY_LIMITS['dnbr'])
                    pair.update(dnbr=float(np.median(dnbr[fire_common])), burn_fraction=int(burned.sum())/nfire,
                        burn_signal=int(burned.sum())/nfire >= HISTORY_LIMITS['fire_fraction'])
                    # Recovery is measured on the SAME pixels in all three dates.
                    for follow in valid_positions:
                        if follow <= newer or int(images[follow]['date'][:4]) > int(b['date'][:4])+2:
                            continue
                        if not comparable(a, images[follow]) or nbr[follow] is None:
                            continue
                        three = fire_common & burned & masks[follow] & np.isfinite(nbr[follow])
                        n = int(three.sum())
                        if not usable(n, total, qa_flags[follow]):
                            continue
                        tolerance = HISTORY_LIMITS['recovery_tolerance']
                        recovered = three & (indices[follow][0] >= indices[older][0]-tolerance)
                        recovered &= (indices[follow][1] >= indices[older][1]-tolerance) & (nbr[follow] >= nbr[older]-tolerance)
                        if int(recovered.sum())/n >= HISTORY_LIMITS['recovery_fraction']:
                            pair.update(recovery=True, recovery_date=images[follow]['date'],
                                recovery_scene=images[follow]['scene_id'], recovery_fraction=int(recovered.sum())/n)
                            break
        pairs.append(pair)
    return {'observations': observations, 'pairs': pairs, 'resolution_m': resolution, 'grid_pixels': total,
            'rule_version': HISTORY_RULE_VERSION, 'limits': HISTORY_LIMITS}


def interpret_history(item, timeline, requested_years, base, annual=True, tolerance=False, technical=False, amazon_forest=False):
    result = dict(timeline)
    observations = timeline.get('observations', [])
    valid = [value for value in observations if value['usable']]
    obtained = {int(value['date'][:4]) for value in valid}
    result['missing_years'] = [year for year in requested_years if year not in obtained]
    result['searched_years'] = list(requested_years)
    result['map_scene_ids'] = []
    result['opening'] = 'Não foi possível localizar um intervalo de alteração com qualidade suficiente.'
    result['fire'] = 'Não foi encontrado sinal conclusivo de queimada. Isso não comprova ausência de incêndio.'
    verdict = dict(base, status='Evidências insuficientes', scope_ha=0)
    verdict['action'] = 'Obter mais evidências antes de pedir alteração do registro'
    year = item.get('year')
    loss_pairs = [pair for pair in timeline.get('pairs', []) if pair.get('usable') and pair.get('loss')]
    burns = [pair for pair in timeline.get('pairs', []) if pair.get('usable') and pair.get('burn_signal')]
    loss_pairs.sort(key=lambda p:(p['after'],-date.fromisoformat(p['before']).toordinal()))
    if loss_pairs:
        first = loss_pairs[0]
        result['opening'] = 'Primeiro intervalo de perda espectral observado na série consultada: entre {} e {}. Não comprova a primeira abertura nem identifica sozinho floresta nativa.'.format(first['before'], first['after'])
        result['map_scene_ids'].extend([first['before_scene'], first['after_scene']])
        result['first_observed_loss'] = first
    elif valid and (valid[0].get('low_cover_fraction') or 0) >= .6:
        result['opening'] = 'Pouca cobertura verde já era visível em {}. Sem imagem anterior adequada, o ano da abertura não pode ser determinado; esse padrão também pode ser natural.'.format(valid[0]['date'])
        result['map_scene_ids'].append(valid[0]['scene_id'])
        result['already_low_at'] = valid[0]['date']
    relevant_burns = [pair for pair in burns if year and year-1 <= int(pair['after'][:4]) <= year+1]
    if relevant_burns:
        event = relevant_burns[0]
        result['burn_event'] = event
        result['fire'] = 'Alteração entre {} e {} compatível com queimada OU outra perturbação (dNBR={:.3f}). A causa e a autoria não são comprovadas por esse índice.'.format(event['before'], event['after'], event['dnbr'])
        result['map_scene_ids'].extend([event['before_scene'], event['after_scene']])
        if event['recovery']:
            result['fire'] += ' Houve recuperação da resposta espectral em {}; isso não prova manutenção da estrutura florestal nem justifica excluir um PRODES histórico.'.format(event['recovery_date'])
            result['map_scene_ids'].append(event['recovery_scene'])
    if year:
        result['map_scene_ids'].extend(v['scene_id'] for v in observations if year-2 <= int(v['date'][:4]) <= year+2)
    if not annual or not year or not item.get('uuid'):
        verdict['reason'] = 'Fonte anual, ano ou identificador oficial não confirmados; não há conclusão sobre contestação.'
    elif amazon_forest and item.get('original_ha', 6.25) < 6.25:
        verdict['action'] = 'Conferir enquadramento da camada e o tamanho do polígono original'
        verdict['reason'] = 'O polígono ORIGINAL é menor que 6,25 ha. Na orientação INPE para Amazônia florestal, esse produto não deve fundamentar avaliação de conformidade. Isso não demonstra erro de mapeamento; a área recortada do imóvel não é usada para esse limiar.'
    elif tolerance and item.get('core_ha') is not None and item['core_ha'] <= .000001:
        verdict['reason'] = 'Sobreposição restrita à faixa cartográfica CAR; conferir vínculo espacial antes da análise temática.'
    else:
        early = [pair for pair in loss_pairs if int(pair['after'][:4]) < year-1
                 and not (pair.get('burn_signal') and pair.get('recovery'))]
        current = [pair for pair in loss_pairs if year-1 <= int(pair['after'][:4]) <= year]
        reference = str(item.get('image_date') or '{}-07-31'.format(year))[:10]
        try:
            date.fromisoformat(reference)
        except (TypeError, ValueError):
            reference = '{}-07-31'.format(year)
        late = [pair for pair in loss_pairs if pair['before'] >= reference and int(pair['after'][:4]) > year
                and not (pair.get('burn_signal') and pair.get('recovery'))]
        if early and not current:
            event = early[0]
            verdict.update(status='Passível de contestação (triagem)', action='Solicitar revisão da data, condicionada à conferência técnica', scope_ha=item.get('clip_ha', 0),
                reason='Há perda espectral observada entre {} e {}, anterior à sequência próxima do registro PRODES {}. É um intervalo candidato para investigação, não uma nova data oficial. Confirmar floresta primária, textura, máscara histórica e eventuais novas perdas.'.format(event['before'], event['after'], year))
        elif early and current:
            verdict.update(action='Conferir alteração antiga e novo evento antes de propor uma data',
                reason='Foram detectadas mudanças antigas e próximas ao registro. Pode haver regeneração, repetição de perturbação ou ampliação; não é seguro transferir o registro para a primeira queda do índice.')
        elif late and not current:
            event = late[0]
            verdict.update(status='Passível de contestação (triagem)', action='Solicitar conferência de possível alteração posterior à data de referência',
                scope_ha=item.get('clip_ha', 0),
                reason='A perda espectral foi observada entre {} e {}, com a imagem anterior à perda na data de referência {} ou depois dela. Conferir se havia floresta primária na referência: os índices não comprovam sua origem. O intervalo é candidato para revisão, não uma nova data oficial.'.format(event['before'], event['after'], reference))
        elif relevant_burns:
            verdict.update(action='Investigar possível queimada e perda da estrutura florestal',
                reason='O NBR sugere perturbação compatível com fogo, mas não distingue sozinho queimada sem supressão de perda total do dossel. Fogo ou recuperação posterior, isoladamente, não justificam contestação. Conferir imagens originais, estrutura, uso e registros independentes de incêndio.')
        elif base.get('spectral_status') == 'Sinal compatível com perda de cobertura' and not (technical and item.get('consolidated_ha', 0)>0):
            verdict.update(status='Sem indícios suficientes para contestação', action='Registro sem divergência demonstrada nesta análise',
                reason='A sequência avaliada apresenta perda próxima do registro. Outros documentos podem alterar a interpretação; o resultado não certifica legalidade.')
        elif base.get('status') == 'Passível de contestação (triagem)' and not (technical and item.get('consolidated_ha', 0)>0):
            verdict.update(base, action='Solicitar conferência temporal da sequência próxima ao registro')
        elif technical and item.get('consolidated_ha', 0)>0:
            verdict.update(status='Passível de contestação (triagem)', action='Investigar sobreposição com consolidada técnica', scope_ha=item.get('consolidated_ha', 0),
                reason='A camada técnica declara ocupação anterior ao marco na parte sobreposta. É fundamento documental para revisão, mas as imagens/índices não homologam o uso ou demonstram, sozinhos, erro no PRODES. Verificar documentos e imagem oficial.')
        else:
            verdict['reason'] = 'A série não demonstrou divergência suficiente. Cobertura verde não identifica floresta primária e ausência de queda detectada não prova ausência de supressão.'
    if result['missing_years']:
        verdict['reason'] += ' Há anos sem imagem/amostra utilizável: {}. Nenhuma data foi inventada para essas lacunas.'.format(', '.join(map(str,result['missing_years'])))
    result['map_scene_ids'] = list(dict.fromkeys(result['map_scene_ids']))
    result['recommendation'] = verdict
    return result
