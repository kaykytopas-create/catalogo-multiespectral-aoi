# SPDX-License-Identifier: GPL-2.0-or-later
"""Evidence-grounded explanations; never upgrade a computed recommendation."""
from datetime import date

ARGUMENT_VERSION = '3.3.0-argument-2'
LAW_URL = 'https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm'
INPE_URL = 'https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf'


def number(value, digits=4):
    return ('{:.' + str(digits) + 'f}').format(float(value or 0)).replace('.', ',')


def observed_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def describe_observation(value):
    metrics = []
    for key in ('ndvi', 'ndmi'):
        if value.get(key) is not None:
            metrics.append('{} {}'.format(key.upper(), number(value[key], 3)))
    return '{}: {} pixels válidos, {}% de cobertura{}'.format(value['date'], value.get('pixels', 0),
        number(100 * value.get('coverage', 0), 0), '; ' + ', '.join(metrics) if metrics else '')


def review_directions(row):
    """Separate temporal/thematic/spatial leads without changing computed verdict."""
    history=row.get('history',{});verdict=row.get('contestability',{})
    year=row.get('year');event=history.get('first_observed_loss') or {}
    before=observed_date(event.get('before'));after=observed_date(event.get('after'))
    reference=observed_date(row.get('image_date'))
    usable=[o for o in history.get('observations',[]) if o.get('usable') and observed_date(o.get('date'))]
    if before and after and before<after:
        temporal='A série encontrou alteração entre {} e {}. Esse é um intervalo de observação, não uma data oficial proposta.'.format(before.isoformat(),after.isoformat())
        if year and after.year<int(year):
            temporal+=' O intervalo termina antes do ano PRODES {}: há uma pista para investigar revisão temporal, desde que corresponda à mesma porção e ao mesmo evento de supressão nativa. Conferir a máscara acumulada e as imagens oficiais antes de propor a classe adequada.'.format(year)
        elif reference and before<reference<=after:
            temporal+=' A imagem de referência {} está dentro do intervalo. Só esse achado não demonstra erro na data oficial; é necessário avaliar a sequência imediatamente anterior e posterior.'.format(reference.isoformat())
        else:
            temporal+=' Não foi demonstrado que esse intervalo substitua o ano oficial. Investigar se é uma nova perda, regeneração removida, expansão ou evento distinto.'
    else:
        temporal='Não foi identificado um intervalo de alteração utilizável. Não propor outra data apenas pela sobreposição com consolidada ou por uma imagem isolada. Complementar a série e confrontar a imagem oficial.'
    thematic='O processamento não classificou automaticamente floresta primária, pastagem ou vegetação secundária. Na composição PRODES, o técnico deve comparar textura, forma, continuidade da cobertura e limites de uso no mesmo local, registrando a feição observada e a carta/data que a sustenta. Diferença de cor ou NDVI isolado não demonstra mudança de classe.'
    if usable:
        thematic+=' Há {} observações utilizáveis para apoiar essa leitura; confirmar se a cobertura já era antrópica antes do registro e se ocorreu nova perda de cobertura nativa.'.format(len(usable))
    else:thematic+=' Faltam observações utilizáveis para sustentar essa leitura nesta execução.'
    if history.get('burn_event'):
        thematic+=' O sinal de perturbação compatível com fogo exige avaliar manutenção/perda estrutural e conversão posterior; não justifica exclusão automaticamente.'
    clip=float(row.get('clip_ha',0) or 0);overlap=float(row.get('consolidated_ha',0) or 0)
    spatial='A discussão espacial deve se limitar ao recorte de {} ha do UUID {}. A consolidada coincide com {} ha; os {} ha restantes precisam de fundamento próprio.'.format(number(clip),row.get('uuid','não informado'),number(overlap),number(max(0,clip-overlap)))
    spatial+=' Nenhuma geometria alternativa foi comprovada por esta argumentação. Não deslocar o polígono para outro setor só para remover a sobreposição: um ajuste exige delimitar o evento realmente observado e conferir georreferenciamento, limites e cenas oficiais. Croqui indicativo não substitui vetor validado.'
    status=verdict.get('status',row.get('status','Evidências insuficientes'))
    if status=='Evidências insuficientes':
        next_step='Prioridade: obter a evidência faltante antes de escolher contestação ou outra data. O resultado permanece inconclusivo; não confirma nem refuta o registro.'
    elif status=='Sem indícios suficientes para contestação':
        next_step='Prioridade: manter o registro como referência de trabalho nesta revisão, pois o conjunto não demonstrou divergência suficiente. Isso não certifica acerto definitivo ou regularidade; reabrir a avaliação se surgirem evidências contrárias.'
    else:
        next_step='Prioridade: investigar a divergência descrita pela regra calculada e demonstrá-la por porção e UUID. Formular encaminhamento principal e alternativa somente após a conferência temática, temporal e espacial; a triagem não determina exclusão.'
    scope=verdict.get('scope_ha',0) or 0
    next_step+=' Área indicada pela triagem: {} ha. Relacionar cada afirmação à data, à carta e à delimitação correspondente; registrar também a evidência contrária e por que ela não explica o achado.'.format(number(scope))
    return [{'axis':'temporal','title':'Revisão temporal e correspondência com o evento','text':temporal},
            {'axis':'thematic','title':'Revisão temática e leitura multitemporal','text':thematic},
            {'axis':'spatial','title':'Revisão espacial e alcance da porção questionada','text':spatial},
            {'axis':'next_step','title':'Encaminhamento individualizado para o técnico','text':next_step}]


def argumentation(row, context=None):
    """Produce reusable sections from actual observations and already computed rules."""
    context = context or {}
    verdict = row.get('contestability', {})
    history = row.get('history', {})
    year = row.get('year')
    clip = float(row.get('clip_ha', 0) or 0)
    overlap = float(row.get('consolidated_ha', 0) or 0)
    sections = [('Objeto e finalidade da revisão', 'Avaliar a coerência temporal, temática e espacial do registro PRODES para subsidiar a interpretação do responsável técnico. Esta estrutura organiza evidências e encaminhamentos por polígono; não é um pedido pronto ao órgão. O fundamento de eventual revisão deve apontar a incompatibilidade concreta entre a imagem de referência e o mapeamento, e não apenas a situação cadastral ou legal do uso [2, seções 8–9].')]
    question = 'O ponto a conferir é se a área delimitada pelo PRODES corresponde à alteração registrada no ano {}, nas imagens e na localização corretas.'.format(year or 'não informado')
    question += ' O recorte dentro do imóvel mede {} ha'.format(number(clip))
    if row.get('original_ha') is not None:
        question += ', enquanto o polígono original mede {} ha'.format(number(row['original_ha']))
    question += '. A conclusão sobre o imóvel deve respeitar esse recorte; a área original é usada apenas quando o critério exige considerar o polígono inteiro.'
    sections.append(('Qual é a questão deste polígono', question))
    if overlap > 0:
        spatial = 'A consolidada delimitada pelo técnico coincide com {} ha do recorte PRODES, aproximadamente {}% da área analisada.'.format(number(overlap), number(100 * overlap / clip if clip else 0, 1))
        spatial += ' Essa coincidência identifica onde conferir o histórico de ocupação. Ela não confirma, por si só, que o PRODES esteja errado: é necessário verificar qual uso existia ali, desde quando e se houve uma nova alteração da vegetação.'
        if overlap < clip:
            spatial += ' O restante do recorte, de {} ha, não está coberto por essa indicação documental; não se deve estender o argumento de consolidação a toda a área.'.format(number(max(0, clip-overlap)))
    else:
        spatial = 'Não foi identificada sobreposição com a consolidada fornecida. Portanto, esta análise não dispõe de um fundamento espacial de consolidação para este recorte. Uma eventual revisão precisa se apoiar na sequência de imagens ou em outras evidências específicas.'
    sections.append(('O que a sobreposição demonstra', spatial))
    observations = sorted(history.get('observations', []), key=lambda value: value.get('date', ''))
    valid = [value for value in observations if value.get('usable') and observed_date(value.get('date'))]
    if history:
        years = history.get('searched_years', [])
        text = 'A pesquisa consultou o período {}. Foram avaliadas {} observações, das quais {} atenderam aos critérios de qualidade do plugin.'.format(
            '{}–{}'.format(min(years), max(years)) if years else 'não informado', len(observations), len(valid))
        if valid:
            text += ' A primeira observação utilizável é de {} e a última, de {}.'.format(valid[0]['date'], valid[-1]['date'])
        elif observations:
            maximum = max((value.get('pixels', 0) for value in observations), default=0)
            text += ' Nenhuma imagem forneceu uma amostra utilizável neste recorte; a maior amostra teve {} pixels válidos. Mesmo 100% de cobertura pode ser insuficiente quando a área contém poucos pixels.'.format(maximum)
        else:
            text += ' A pesquisa não forneceu observações para medir a cobertura ou a amostra deste recorte.'
        missing = history.get('missing_years', [])
        if missing:
            text += ' Houve {} anos sem observação utilizável: {}. Essas lacunas podem ocultar mudanças e impedem afirmar que nada ocorreu entre as imagens.'.format(len(missing), ', '.join(map(str, missing)))
        pairs = history.get('pairs', [])
        if pairs:
            usable_pairs = sum(bool(pair.get('usable')) for pair in pairs)
            text += ' Dos {} pares de datas examinados, {} puderam ser comparados com pixels comuns, plataforma e época do ano compatíveis. Duas imagens utilizáveis separadamente nem sempre formam um par comparável.'.format(len(pairs), usable_pairs)
        sections.append(('Até onde as imagens permitem avaliar', text))
        if year:
            reference = observed_date(row.get('image_date'))
            if reference:
                text = 'A data da imagem de referência informada na base PRODES é {}. Ela identifica a observação usada no registro, não necessariamente o dia exato da alteração.'.format(reference.isoformat())
                before = [value for value in valid if observed_date(value['date']) < reference]
                after = [value for value in valid if observed_date(value['date']) > reference]
            else:
                text = 'A data exata da imagem oficial não está disponível neste resultado. A comparação abaixo usa o ano {} apenas como referência anual, sem atribuir um dia à supressão.'.format(year)
                before = [value for value in valid if int(value['date'][:4]) < year]
                after = [value for value in valid if int(value['date'][:4]) > year]
            near = [value for value in valid if int(value['date'][:4]) == year]
            if before:text += ' Antes da referência, a observação utilizável mais próxima foi {}.'.format(describe_observation(before[-1]))
            else:text += ' Não há observação utilizável anterior à referência; falta o estado anterior para confirmar uma mudança.'
            if near:text += ' No ano registrado, {}.'.format(describe_observation(near[0]))
            else:text += ' Não há observação utilizável no próprio ano registrado.'
            if after:text += ' Depois da referência, a observação utilizável mais próxima foi {}.'.format(describe_observation(after[0]))
            else:text += ' Não há observação utilizável posterior à referência; a evolução seguinte não foi confirmada.'
            text += ' Esses números descrevem a resposta da vegetação e da umidade. Pastagem verde, floresta e regeneração podem ter respostas semelhantes; a diferença entre os números não substitui a comparação dos mesmos pixels nem a leitura dos mapas.'
            sections.append(('O que aparece antes e depois do registro', text))
        event = history.get('first_observed_loss')
        if event:
            text = 'O primeiro intervalo de perda detectado nesta série está entre {} e {}.'.format(event['before'], event['after'])
            if event.get('changed_fraction') is not None:
                text += ' A queda conjunta dos índices atingiu {}% dos pixels válidos comuns ao par.'.format(number(100 * event['changed_fraction'], 1))
            text += ' A mudança ocorreu em algum momento desse intervalo; não é correto escolher um dos anos como a nova data oficial apenas com esse resultado. Uma abertura ainda mais antiga pode ter ficado fora da série ou nas lacunas.'
            cutoff = date(2008, 7, 22)
            before, after = observed_date(event['before']), observed_date(event['after'])
            if before and after and before < cutoff <= after:
                text += ' Como o intervalo atravessa 22/07/2008, ele não permite determinar se a alteração ocorreu antes ou depois do marco legal.'
            elif after and after < cutoff:
                text += ' O intervalo é anterior a 22/07/2008, o que permite investigar ocupação pré-marco; ainda é necessário identificar o uso antrópico exigido pela lei.'
            elif before and before >= cutoff:
                text += ' Esse intervalo não comprova abertura anterior a 22/07/2008.'
            losses = [pair for pair in history.get('pairs', []) if pair.get('usable') and pair.get('loss')]
            if len(losses)>1:
                text += ' Foram encontrados {} intervalos de perda. É necessário distinguir a alteração antiga de uma possível nova perda, expansão ou perturbação; transferir tudo para o primeiro intervalo pode produzir uma conclusão incorreta.'.format(len(losses))
        else:
            text = 'Não foi localizado um intervalo de perda que atendesse às regras de comparação. Isso significa que o sistema não conseguiu determinar quando a alteração ocorreu, e não que tenha comprovado ausência de desmatamento ou erro na data PRODES.'
            if history.get('already_low_at'):
                text += ' O padrão de pouca cobertura verde já aparecia em {}, mas, sem um estado anterior adequado, a abertura não pode ser datada; esse padrão também pode ter origem natural.'.format(history['already_low_at'])
        sections.append(('É possível indicar outra data', text))
    else:
        sections.append(('Limite da comparação temporal', 'O histórico automático anterior e posterior não foi pesquisado nesta execução. A comparação ficou limitada às imagens escolhidas. Não há base para apresentar um ano de abertura descoberto pelo sistema; a indicação documental deve ser examinada separadamente.'))
    historic = row.get('historical', {})
    pre = [value for value in valid if observed_date(value['date']) < date(2008, 7, 22)]
    legal = 'O art. 3º, IV, da Lei 12.651/2012 vincula a área rural consolidada à ocupação humana anterior a 22/07/2008, com os usos definidos na lei. Por isso, o fundamento é o histórico comprovado de ocupação e de uso, e não o nome da camada ou a cor da imagem [1].'
    if pre:
        legal += ' Neste recorte há {} observações utilizáveis anteriores ao marco, entre {} e {}. Elas permitem examinar o histórico, mas não identificam automaticamente atividade agropecuária, benfeitoria ou pousio.'.format(len(pre), pre[0]['date'], pre[-1]['date'])
        if all(value.get('ndvi') is not None and value['ndvi'] > .35 for value in pre):
            legal += ' Todas essas observações apresentaram NDVI acima de 0,35, ou seja, resposta de cobertura verde. Isso não é uma comprovação de solo aberto; também não refuta, isoladamente, pastagem verde ou pousio. O tipo de vegetação e o uso descrito pelo técnico precisam ser conferidos na imagem e nos documentos.'
    elif history:
        legal += ' Neste processamento não há observação utilizável anterior ao marco para este recorte. Assim, a consolidação não foi corroborada pela série de imagens.'
    if historic:
        legal += ' A avaliação específica da sobreposição consolidada, na imagem de {}, informou: {}.'.format(historic.get('date', 'data não identificada'), historic.get('reason', 'sem conclusão disponível'))
    legal += ' O reconhecimento de consolidação e a revisão do mapeamento são questões distintas. A consolidação não elimina automaticamente um registro histórico nem dispensa a análise das obrigações ambientais da área.'
    sections.append(('Como a consolidada entra no argumento', legal))
    burn = history.get('burn_event')
    if burn:
        fire = 'Foi encontrado sinal de perturbação entre {} e {}, com dNBR {}.'.format(burn['before'], burn['after'], number(burn.get('dnbr'),3))
        if burn.get('recovery'):
            fire += ' Houve recuperação da resposta espectral em {}. A recuperação é uma pista de evolução da cobertura; não demonstra que a floresta manteve sua estrutura nem apaga uma supressão anterior.'.format(burn.get('recovery_date', 'data não informada'))
        fire += ' Para sustentar uma revisão por possível incêndio, é necessário distinguir dano temporário de perda da cobertura florestal, verificando mapas anteriores e posteriores, estrutura da vegetação e registros independentes do evento. O índice não identifica causa ou responsável.'
    else:
        fire = 'A análise não apresentou um sinal conclusivo de incêndio relacionado ao registro. Isso não comprova que não houve fogo. Se o técnico dispõe de informação de incêndio, ela deve ser confrontada com imagens próximas do evento e registros independentes; não se deve afirmar incêndio a partir desta ausência de detecção.'
    sections.append(('O que pode ser dito sobre incêndio', fire))
    reason = verdict.get('reason', row.get('reason', 'Não há justificativa calculada disponível.'))
    technical = 'O resultado calculado foi “{}”. A regra aplicada foi: {} '.format(verdict.get('status', row.get('status', 'Evidências insuficientes')), reason)
    documentary = 'consolidada técnica' in verdict.get('action', '').lower()
    if documentary:
        technical += 'Aqui, a indicação é documental: a consolidação informada pelo técnico justifica conferir a sobreposição, mas a série não demonstrou uma divergência temporal suficiente para definir outra data. Portanto, a formulação defensável é um pedido fundamentado de conferência, condicionado às evidências do uso anterior, e não uma afirmação de falso PRODES.'
    elif verdict.get('status') == 'Evidências insuficientes':
        technical += 'Não é tecnicamente defensável concluir pela exclusão ou por uma nova data com este conjunto. A insuficiência informa o limite da análise; não confirma o acerto do registro nem o erro alegado.'
    elif verdict.get('status') == 'Sem indícios suficientes para contestação':
        technical += 'Esta análise não demonstrou uma divergência suficiente para sustentar a revisão. Isso não é uma certificação de regularidade ambiental e não impede examinar novas evidências.'
    else:
        technical += 'A indicação permite investigar uma divergência específica. Antes de propor alteração, é necessário confirmar o tipo de vegetação, a imagem oficial e se o intervalo corresponde ao mesmo evento mapeado, em vez de regeneração ou nova perda.'
    technical += ' Conforme a orientação do INPE, a revisão depende de demonstrar incompatibilidade entre o mapeamento e a imagem de referência; autorização de desmatamento ou regeneração posterior não são, por si só, fundamento para retirar um registro [2, seções 8–9].'
    sections.append(('Por que esta conclusão foi adotada', technical))
    sections.extend((direction['title'],direction['text']) for direction in review_directions(row))
    small_product = '6,25 ha' in reason and 'ORIGINAL' in reason
    if small_product:
        next_step = 'Separar a discussão sobre o uso desse dado para avaliar conformidade da discussão sobre a exatidão do mapa. Conferir a camada de origem e a área do polígono original: a orientação do INPE para polígonos da Amazônia menores que 6,25 ha trata do uso do produto, não comprova que o desenho do polígono esteja errado [2, seção 7]. Não aplicar esse limite à pequena parte recortada do imóvel.'
    else:
        next_step = 'Identificar o polígono pelo UUID {} e limitar o pedido à área efetivamente questionada, com mapa mostrando o imóvel, o PRODES e a consolidada.'.format(row.get('uuid', 'não informado'))
        if documentary:
            next_step += ' Anexar os elementos que embasaram a delimitação técnica: descrição do uso, datas verificáveis e documentos ou imagens anteriores ao marco. Explicar qual parte já apresentava ocupação e qual característica observada entra em conflito com o registro.'
        else:
            next_step += ' Anexar mapas com datas legíveis antes e depois da alteração, indicar a diferença concreta encontrada e conferir a imagem oficial do ano registrado.'
        if not valid:
            next_step += ' Antes de sustentar uma data, obter imagem adequada ou interpretação técnica com resolução suficiente para este pequeno recorte.'
        next_step += ' O pedido ao INPE deve trazer identificação do proprietário, CAR e UUID; a decisão sobre corrigir o mapa cabe ao órgão [2, seção 9].'
    sections.append(('Como transformar a análise em um pedido verificável', next_step))
    method = 'A unidade de avaliação é o recorte do polígono no imóvel. A seleção e os cálculos espectrais não constituem classificação supervisionada de uso do solo: usam reflectância, máscaras de qualidade, índices e diferenças nos mesmos pixels. Cenas com menos de 20% de nuvens podem continuar inadequadas dentro do recorte. A interpretação de alteração depende dos pares utilizáveis, da amostra, da compatibilidade de sensor/época e da leitura das cartas; cores ou NDVI isolados não identificam floresta primária, pastagem ou uso legal.'
    sections.append(('Método, unidade de análise e alcance da inferência', method))
    alternative = 'Devem ser testadas explicações concorrentes para a resposta observada: ocupação anterior, nova supressão sobre vegetação regenerada, expansão parcial, mudança sazonal, fogo com ou sem conversão posterior, deslocamento e amostra insuficiente. A consolidada informada não elimina essas hipóteses. Para distingui-las, conferir o mesmo local antes/depois, o padrão espacial, a persistência da alteração e a imagem oficial de referência.'
    if not valid:
        alternative += ' Neste caso faltam observações utilizáveis; nenhuma dessas explicações pode ser descartada pelo processamento.'
    elif not history.get('first_observed_loss'):
        alternative += ' A ausência de intervalo de perda detectado não permite escolher automaticamente a hipótese de erro no PRODES.'
    else:
        alternative += ' O intervalo detectado é um resultado da série disponível; sua correspondência com o evento oficial ainda exige conferência técnica.'
    sections.append(('Explicações alternativas que precisam ser confrontadas', alternative))
    draft = 'Roteiro de síntese para revisão do técnico: UUID {}, ano {}, recorte de {} ha. Resultado desta execução: {}. O fundamento calculado é: {}. Organizar a redação em observação verificável, interpretação e providência condicionada. Se as cartas comprovarem ocupação anterior no mesmo setor, explicar o conflito com o incremento anual e conferir a máscara acumulada. Se comprovarem nova supressão em outro setor, delimitar apenas essa feição para discussão espacial. Se não demonstrarem divergência, registrar a manutenção provisória ou a insuficiência de evidências. Não transferir datas, classes ou geometrias de um exemplo para este imóvel; cada conclusão depende das imagens e dos vetores deste caso.'
    draft = draft.format(row.get('uuid','não informado'),year or 'não informado',number(clip),verdict.get('status',row.get('status','Evidências insuficientes')),verdict.get('rule_reason') or verdict.get('reason') or 'não disponível')
    sections.append(('Síntese técnica para subsidiar a redação do revisor', draft))
    return sections


def attach_argumentation(item, result):
    """Persist the explanation in the analysis result, not only in HTML rendering."""
    verdict = result.get('contestability')
    # Rebuilding explanations after historical acquisition must not recursively
    # expand the previous short-series explanation.
    if verdict and verdict.get('rule_reason'):
        verdict['reason'] = verdict['rule_reason']
    row = dict(item, **result)
    row.pop('argumentation', None)
    sections = [{'title': title, 'text': text} for title, text in argumentation(row)]
    documentary = bool(verdict and 'consolidada técnica' in verdict.get('action', '').lower())
    result['argumentation'] = {'version': ARGUMENT_VERSION,
        'basis': 'Indicação documental; divergência temporal não demonstrada' if documentary else
                 ('Comparação histórica e critérios de qualidade' if result.get('history') else 'Comparação limitada às imagens selecionadas'),
        'template': 'Revisão temporal, temática e espacial por UUID; apoio à redação do técnico',
        'review_directions': review_directions(row), 'sections': sections}
    if verdict:
        verdict['rule_reason'] = verdict.get('reason', '')
        verdict['reason'] = next(section['text'] for section in sections if section['title'] == 'Por que esta conclusão foi adotada')
    return result
