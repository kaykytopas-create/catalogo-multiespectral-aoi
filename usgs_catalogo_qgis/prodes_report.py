# SPDX-License-Identifier: GPL-2.0-or-later
"""Plain-language report, self-contained map images and explicit evidence gaps."""
import base64
import html
import os
import struct
from .prodes_argument import argumentation, ARGUMENT_VERSION


def esc(value):
    if value is None or value == 'None':value='Não informado'
    if isinstance(value,bool):value='Sim' if value else 'Não'
    return html.escape(str(value),quote=True)


def image_uri(path):
    if os.path.isfile(path) and os.path.getsize(path) <= 32*1024*1024:
        with open(path,'rb') as stream:raw=stream.read()
        if raw.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'data:image/png;base64,'+base64.b64encode(raw).decode('ascii')
    return path


def image_tag(path, width=640):
    """Bound native layout maps to the page while preserving their aspect ratio."""
    height = round(width * 210 / 297)
    if os.path.isfile(path):
        with open(path, 'rb') as stream:
            header = stream.read(24)
        if len(header) == 24 and header.startswith(b'\x89PNG\r\n\x1a\n'):
            native_width, native_height = struct.unpack('>II', header[16:24])
            if native_width and native_height:
                height = round(width * native_height / native_width)
    return '<img width="{}" height="{}" src="{}">'.format(width, height, esc(image_uri(path)))


def normalized_maps(maps):
    return [value if isinstance(value,dict) else {'caption':value[0],'filename':value[1],'scene_id':''} for value in maps]


def readable_report(context, rows, maps=()):
    images=normalized_maps(maps)
    searched = any(row.get("history") for row in rows)
    body="""<html><head><meta charset='utf-8'><style>
body{font-family:Arial,sans-serif;color:#233741;font-size:11pt}h1{color:#175c59;font-size:20pt}
h2{color:#175c59;font-size:15pt}h3{font-size:12pt}p{line-height:1.4}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd6db;padding:7px;text-align:left}
th{background:#e8f2f0}.note{background:#fff1d1;padding:10px}
</style></head><body><h1>PRODES — análise técnica para apoio à revisão</h1>"""
    body+='<p><b>Imóvel:</b> {}<br><b>CAR:</b> {}<br><b>Responsável pela revisão:</b> {}</p>'.format(esc(context.get('Imóvel','Não informado')),esc(context.get('CAR','Não informado')),esc(context.get('Revisor','Não informado')))
    body+='<p class="note">Análise experimental para revisão técnica. O resultado indica caminhos para investigar; não é decisão oficial, prova de falso PRODES ou conclusão jurídica. A meta de 80 por cento de acerto ainda não foi validada em casos independentes.</p>'
    body += '<p><b>Finalidade:</b> organizar a evidência e os possíveis encaminhamentos de revisão temporal, temática e espacial por UUID, para o técnico produzir e conferir sua própria interpretação. O texto não é uma solicitação pronta ao INPE.</p>'
    body += '<p><b>Pesquisa histórica:</b> ' + ('Executada; consulte os anos e as lacunas de cada polígono abaixo.' if searched else 'Não executada nesta análise. Foram utilizadas somente as imagens escolhidas; não houve busca automática das imagens anteriores e posteriores.') + '</p>'
    body+='<h2>O que a análise encontrou</h2><table><tr><th>Polígono / ano registrado</th><th>Resultado</th><th>Próximo passo</th></tr>'
    for index,row in enumerate(rows,1):
        verdict=row.get('contestability',{})
        body+='<tr><td>{} · {}<br>{}</td><td>{}</td><td>{}</td></tr>'.format(index,esc(row.get('year')),esc(row.get('uuid','Sem identificador')),esc(verdict.get('status',row.get('status','Evidências insuficientes'))),esc(verdict.get('action','Conferir evidências e justificativa abaixo')))
    body+='</table><p><b>Como ler:</b> “Passível de contestação” indica um fundamento preliminar para investigar. “Sem indícios suficientes para contestação” significa que esta análise não demonstrou divergência. “Evidências insuficientes” significa que não foi possível decidir com segurança.</p>'
    if not rows:body+='<p>Nenhum incremento foi encontrado no recorte consultado. Isso não certifica ausência de supressão.</p>'
    used=set()
    for index,row in enumerate(rows,1):
        verdict=row.get('contestability',{})
        history=row.get('history',{})
        body+='<h2>{}. Polígono PRODES de {}</h2><p><b>Identificador:</b> {}<br><b>Área analisada dentro do imóvel:</b> {:.4f} ha<br><b>Sobreposição com a consolidada técnica:</b> {:.4f} ha</p>'.format(index,esc(row.get('year')),esc(row.get('uuid')),row.get('clip_ha',0),row.get('consolidated_ha',0))
        body+='<p><b>Resultado:</b> {}<br><b>O que fazer:</b> {}<br><b>Por quê:</b> {}</p>'.format(esc(verdict.get('status',row.get('status','Inconclusivo'))),esc(verdict.get('action','Conferir a sequência e os documentos')),esc(verdict.get('reason',row.get('reason','Não calculado'))))
        if row.get('argumentation', {}).get('basis'):
            body += '<p><b>Fundamento desta indicação:</b> {}</p>'.format(esc(row['argumentation']['basis']))
        body+='<p><b>Área a que a indicação se refere:</b> {:.4f} ha. Zero significa que não há uma área indicada para contestação nesta execução.</p>'.format(verdict.get('scope_ha',0))
        if history:
            body+='<p><b>Quando a alteração apareceu:</b> {}<br><b>Possível incêndio:</b> {}</p>'.format(esc(history['opening']),esc(history['fire']))
            years=history.get('searched_years',[])
            body+='<p><b>Período pesquisado:</b> {}. <b>Anos sem observação utilizável:</b> {}.</p>'.format('{}–{}'.format(min(years),max(years)) if years else 'Não disponível',esc(', '.join(map(str,history.get('missing_years',[]))) or 'Nenhum no período consultado'))
            body+='<h3>Linha do tempo das imagens</h3><table><tr><th>Data</th><th>Condição da observação</th><th>NDVI</th><th>NDMI</th></tr>'
            for observation in history.get('observations',[]):
                fmt=lambda value:'—' if value is None else '{:.3f}'.format(value)
                body+='<tr><td>{}</td><td>{} · {} pixels · {:.0f}% de cobertura</td><td>{}</td><td>{}</td></tr>'.format(esc(observation['date']),'Utilizável' if observation['usable'] else 'Insuficiente',observation['pixels'],100*observation['coverage'],fmt(observation['ndvi']),fmt(observation['ndmi']))
            body+='</table>'
        else:
            body+='<p><b>Histórico anterior/posterior não pesquisado nesta execução.</b> A sobreposição com a consolidada é uma indicação documental a investigar, não uma confirmação pelas imagens.</p>'
            body+='<p><b>Comparação das imagens:</b> {}</p>'.format(esc(row.get('reason','Não realizada nesta execução')))
            historical=row.get('historical',{})
            if historical:body+='<p><b>Imagem antiga:</b> {} — {}</p>'.format(esc(historical.get('date')),esc(historical.get('reason','Não avaliada')))
        body += '<h3>Matriz de evidências comparáveis</h3><table><tr><th>Par de datas</th><th>Resultado mensurado</th><th>Limite da inferência</th></tr>'
        pairs = history.get('pairs', [])
        relevant = [p for p in pairs if p.get('usable') and (p.get('loss') or p.get('burn_signal'))]
        if not relevant:
            relevant = [p for p in pairs if p.get('usable')][:6]
        for pair in relevant[:12]:
            finding = 'Perda espectral detectada' if pair.get('loss') else 'Sem perda detectada pelas regras'
            if pair.get('burn_signal'): finding += '; perturbação compatível com fogo'
            if pair.get('changed_fraction') is not None: finding += ' · {:.1f}% de pixels comuns alterados'.format(100*pair['changed_fraction'])
            metrics = []
            for key, title in [('delta_ndvi','ΔNDVI'),('delta_ndmi','ΔNDMI'),('dnbr','dNBR')]:
                if pair.get(key) is not None: metrics.append('{}={:.3f}'.format(title, pair[key]))
            if pair.get('pixels') is not None: metrics.append('{} pixels comuns'.format(pair['pixels']))
            if pair.get('coverage') is not None: metrics.append('{:.1f}% de cobertura'.format(100*pair['coverage']))
            detail = finding + (' · ' + '; '.join(metrics) if metrics else '')
            body += '<tr><td>{} → {}<br>{} / {}</td><td>{}</td><td>Intervalo de observação; não determina dia exato, causa, uso legal ou primeira abertura.</td></tr>'.format(esc(pair.get('before')), esc(pair.get('after')), esc(pair.get('before_scene')), esc(pair.get('after_scene')), esc(detail))
        if not relevant: body += '<tr><td colspan="3">Nenhum par utilizável disponível para demonstrar uma mudança temporal.</td></tr>'
        body += '</table><p>A matriz apresenta até 12 pares relevantes. A série completa e os critérios ficam nos arquivos de investigação; os intervalos não são eventos independentes automaticamente.</p>'
        agent=row.get('agent',{})
        if agent:
            body+='<h3>Investigação do sistema</h3><p><b>Condição da amostra:</b> {}<br><b>Interpretação visual:</b> {}</p>'.format(esc(agent.get('adequacy')),esc(agent.get('visual_status')))
            body+='<table><tr><th>Hipótese investigada</th><th>O que foi encontrado</th></tr>'
            for hypothesis in agent.get('hypotheses',[]):
                body+='<tr><td>{}</td><td>{}<br>{}</td></tr>'.format(esc(hypothesis['title']),esc(hypothesis['status']),esc(hypothesis['explanation']))
            body+='</table>'
            selection=agent.get('selection',[])
            accepted=[v for v in selection if v.get('selected')]
            body+='<p>Foram registradas {} avaliações de candidatas, com {} seleções. O sistema comparou QA, cobertura e quantidade de pixels dentro deste polígono; uma seleção insuficiente é apenas referência visual, sem garantia de análise.</p>'.format(len(selection),len(accepted))
            recent=[v for v in accepted if row.get('year',0)-2<=int(v['date'][:4])<=row.get('year',0)+2][:8]
            if recent:
                body+='<table><tr><th>Cena selecionada próxima ao registro</th><th>Qualidade no polígono</th></tr>'
                for value in recent:
                    body+='<tr><td>{}<br>{}</td><td>{} pixels · {:.0f}% · {}</td></tr>'.format(esc(value['date']),esc(value['scene_id']),value.get('pixels',0),100*value.get('coverage',0),'Utilizável' if value.get('usable') else 'Insuficiente')
                body+='</table><p>A relação completa de candidatas e motivos está no arquivo de seleção exportado.</p>'
            if agent.get('questions'):
                body+='<p><b>Questões que continuam abertas:</b></p><ul>'+''.join('<li>'+esc(q)+'</li>' for q in agent['questions'])+'</ul>'
            visual=agent.get('visual',{})
            if visual.get('argument'):
                body+='<h3>Complemento da IA visual — hipótese para conferência</h3>'
                body+='<p>Modelo {}. Este texto não altera o resultado calculado e não tem precisão temática validada.</p>'.format(esc(visual.get('model')))
                for observation in visual.get('observations',[]):
                    body+='<p><b>{}:</b> {}</p>'.format(esc(', '.join(observation['scene_ids'])),esc(observation['description']))
                body+='<p>{}</p><p><b>Limitações declaradas pelo modelo:</b> {}</p><p><b>Referências indicadas:</b> {}</p>'.format(esc(visual['argument']),esc(visual.get('limitations')),esc(', '.join(visual.get('references',[]))))
        computed = row.get("argumentation", {}).get("sections")
        paragraphs = [(value["title"], value["text"]) for value in computed] if computed else argumentation(row, context)
        for title, paragraph in paragraphs:
            body += '<p><span style="font-size:12pt;font-weight:bold">{}</span><br>{}</p>'.format(esc(title), esc(paragraph))
        body+='<p><b>Sua revisão:</b> {}. <b>Observações:</b> {}</p>'.format(esc(row.get('user_review','A revisar')),esc(row.get('notes','') or 'Sem observações'))
        selected=[image for image in images if image.get('polygon_index') in (None, index-1)
                  and image.get('scene_id') in history.get('map_scene_ids',[])] if history else [image for image in images if image.get('polygon_index') in (None,index-1)]
        if selected:
            body+='<h3>Mapas que acompanham esta conclusão</h3>'
            for image in selected:
                used.add(image['filename'])
                role='Imagem de comparação'
                event=history.get('first_observed_loss',{})
                if image.get('scene_id')==event.get('before_scene'):role='Antes da alteração observada'
                elif image.get('scene_id')==event.get('after_scene'):role='Depois da alteração observada'
                body+='<p style="page-break-before:always"><b>{}:</b> {}<br>{}</p>'.format(role,esc(image['caption']),image_tag(image['filename']))
        else:body+='<p><b>Mapas indisponíveis para este polígono.</b> Sem imagens suficientes, a conclusão permanece limitada às informações descritas.</p>'
    remaining=[image for image in images if image['filename'] not in used]
    if remaining:
        body+='<h2>Outras imagens de referência</h2>'
        for image in remaining:body+='<p>{}</p>{}'.format(esc(image['caption']),image_tag(image['filename']))
    procedure = ('A busca automática consultou o histórico e as imagens posteriores, mantendo a composição SWIR1/NIR/vermelho e verificando nuvens, pixels válidos e calibração. Consulte as lacunas por polígono.' if searched else 'Esta execução comparou somente as imagens fornecidas manualmente. Não foi realizada pesquisa histórica automática; a indicação documental não substitui uma sequência temporal utilizável.')
    body += '<h2>O que foi feito e quais são os limites</h2><p>O plugin cruzou os limites do imóvel, os incrementos PRODES e a consolidada técnica. ' + procedure + '</p>'
    body+='<p>NDVI indica resposta da vegetação; NDMI, resposta relacionada à umidade. NBR e dNBR ajudam a investigar perturbações compatíveis com fogo, mas não provam a causa. Os índices não classificam origem nativa, autoria do incêndio ou manutenção da estrutura florestal. Intervalos entre imagens não são o dia da abertura; a primeira mudança observada pode não ser a primeira supressão.</p>'
    body+='<p>Regras próprias: pelo menos 9 pixels válidos e 80% de cobertura; queda simultânea de NDVI de 0,20 e NDMI de 0,15 em 60% dos pixels; dNBR de 0,27 em 60% para sinal exploratório de perturbação. Comparações exigem época sazonal compatível e mesma plataforma. Esses valores são experimentais, sem precisão temática validada, e não são limiares oficiais do INPE.</p>'
    body+='<p>A consolidada é a classificação fornecida pelo técnico. O enquadramento no art. 3º, IV, da Lei 12.651/2012 depende de ocupação anterior a 22/07/2008 e do uso previsto na lei. O plugin não homologa esse enquadramento nem avalia autorizações, APP ou Reserva Legal. Incêndio, regeneração ou autorização não justificam, isoladamente, remover um registro histórico.</p>'
    body+='<h3>Rastreabilidade</h3><p>Fonte PRODES: {}<br>Data da execução: {}<br>Regras: {}<br>Origem da consolidada: {}</p>'.format(esc(context.get('Fonte PRODES')),esc(context.get('Análise UTC')),esc(context.get('Regras')),esc(context.get('Origem/evidências técnicas da consolidada','Não detalhadas')))
    body += '<p>Versão da argumentação: {}.</p>'.format(esc(ARGUMENT_VERSION))
    references={ref['id']:ref for row in rows for ref in row.get('agent',{}).get('references',[])}
    if references:
        body+='<h3>Base de orientação da investigação</h3><p>Resumos oficiais selecionados por tema; versão consultada em 06/10/2026. Não constitui atualização automática da legislação.</p><ul>'
        for identity,ref in references.items():
            body+='<li><b>{} — {}:</b> {} <a href="{}">{}</a></li>'.format(esc(identity),esc(ref['title']),esc(ref['summary']),esc(ref['url']),esc(ref['locator']))
        body+='</ul>'
    if context.get('Identificador da investigação'):
        body += '<p><b>Investigação:</b> {}<br><b>Sistema:</b> {}</p>'.format(esc(context['Identificador da investigação']),esc(context.get('Sistema de investigação')))
    warnings=context.get('Avisos da aquisição',[])
    if isinstance(warnings,list) and warnings:
        body+='<p><b>Avisos de aquisição:</b></p><ul>'+''.join('<li>'+esc(w)+'</li>' for w in list(dict.fromkeys(warnings)))+'</ul>'
    body+='<p>As cenas, datas, métricas e arquivos de origem completos estão no manifesto exportado. Os mapas usam imagens alternativas públicas; conferir a imagem oficial antes de solicitar revisão.</p>'
    body+='<p>Referências: [2] <a href="https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf">INPE — uso dos dados PRODES (2026)</a>; [1] <a href="https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm">Lei 12.651/2012</a>; <a href="https://www.usgs.gov/landsat-missions/landsat-normalized-burn-ratio">USGS — NBR</a>.</p><p>Kayky Pessoa de Araujo e OpenAI Codex. PRODES: INPE/TerraBrasilis; Landsat: USGS/NASA; catálogo: Microsoft Planetary Computer.</p></body></html>'
    return body
