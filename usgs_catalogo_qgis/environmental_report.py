# SPDX-License-Identifier: GPL-2.0-or-later
"""Short readable report, with complete local evidence outside the summary."""
import csv
import html
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .environmental import STATUSES, LAND_LAYERS


def land_summary(report):
    values={s['source']:s for s in report['sources']}
    settlements=[values[s] for s in ('assent_estadual','assent_federal')]
    found=[(s,r) for s in settlements for r in s['records']]
    if found:
        names=[r.get('properties',{}).get('nmassent') or r.get('properties',{}).get('nmprojeto') or r['id'] for s,r in found]
        assent='Há sobreposição com assentamento: '+', '.join(dict.fromkeys(names))+'. A consulta confirma interseção, que pode abranger apenas parte do imóvel; não foi calculada a fração de área.'
    elif all(s['complete'] for s in settlements):
        assent='Não foi identificada sobreposição com assentamentos nas duas camadas consultadas (federal e estadual, recorte Pará).'
    else:
        assent='Localização em assentamento: inconclusiva, pois uma ou mais bases não foram concluídas ou estão fora da cobertura.'
    glebas=[(s,r) for key in ('gleba_estadual','gleba_federal') for s in [values[key]] for r in s['records']]
    if glebas:
        names=[r.get('properties',{}).get('denominaca') or r['id'] for s,r in glebas]
        gleba='Gleba(s) com interseção: '+', '.join(dict.fromkeys(names))+'. As esferas estadual/federal constam no detalhamento; a fração de área não foi calculada.'
    else:
        gleba='Gleba não identificada nas respostas disponíveis; não inferir que a terra é particular, devoluta ou sem destinação.'
    cadastral=[(s,r) for key in ('sigef','snci','requerimento') for s in [values[key]] for r in s['records']]
    fund='Situação fundiária documental não determinada por esta triagem. '
    if cadastral:
        fund+='Foram encontrados registros cadastrais e/ou requerimentos; confira os nomes, números e a situação original informada pela fonte. '
    fund+='CAR, SIGEF/SNCI, gleba, assentamento e requerimento não comprovam, isoladamente, domínio, matrícula vigente, legitimidade da posse ou titulação. Conferir certidão atualizada de matrícula, cadeia dominial, título/CCU/CDRU quando cabível e manifestação do órgão fundiário.'
    return {'settlement':assent,'gleba':gleba,'tenure':fund}


FIELD_LABELS = {
 'cod_imovel':'CAR','status_legivel':'Situação cadastral','condicao':'Condição da análise','situacao':'Situação na base',
 'nmassent':'Assentamento','nmprojeto':'Projeto de assentamento','denominaca':'Gleba','nomearea':'Denominação da parcela',
 'nmimovel':'Imóvel na base','imovel':'Denominação no requerimento','nome_imovel':'Imóvel na base',
 'numero_emb':'Termo de embargo','num_tad':'Termo de embargo','numero_ai':'Auto de infração','num_auto_infracao':'Auto de infração',
 'municipio':'Município','orgaogest':'Órgão gestor','codsipra':'Código SIPRA','parcelaco':'Parcela SIGEF','numcertif':'Certificação SNCI',
 'codcertif':'Código de certificação','situacimov':'Situação do imóvel na base','status':'Status na base',
 'matricula':'Referência à matrícula na base','registrom':'Referência ao registro na base',
 'data_atualizacao':'Atualização cadastral','dataatual':'Atualização da base','atualizaca':'Atualização da base',
 'datamodif':'Modificação na base','dat_embargo':'Data de embargo','data':'Data do registro','julgamento':'Julgamento informado',
 'des_infracao':'Descrição da infração','desc_inf_1':'Descrição da infração',
}
DATE_FIELDS={'data_atualizacao','dataatual','datamodif','dat_embargo','data'}

def display_field(key,value):
    text=str(value)
    if key in DATE_FIELDS:
        try:
            if text.lstrip('-').isdigit() and len(text.lstrip('-'))>=12:
                text=datetime.fromtimestamp(int(text)/1000,timezone.utc).strftime('%d/%m/%Y')
            elif len(text)>=10 and text[4]=='-' and text[7]=='-':
                text=datetime.strptime(text[:10],'%Y-%m-%d').strftime('%d/%m/%Y')
        except (ValueError,OverflowError,OSError):pass
    if key in ('des_infracao','desc_inf_1') and len(text)>450:text=text[:450]+'… (íntegra recebida no JSON)'
    return FIELD_LABELS.get(key,key.replace('_',' '))+': '+text


def render_html(report):
    esc=lambda value:html.escape(str(value if value is not None else 'Não informado'))
    prop=report['property'];lines=['<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8"><title>Consulta ambiental e fundiária</title>',
        '<style>body{font-family:Arial,sans-serif;color:#203141;font-size:10.5pt;line-height:1.25;max-width:1080px;margin:30px auto}h1{font-size:21pt;color:#163e4d}h2{font-size:13pt;margin-top:14px;color:#163e4d}table{border-collapse:collapse;width:100%;font-size:9pt}th{background:#e8f0f1;text-align:left}td,th{padding:4px;border:1px solid #ccd7dd;vertical-align:top;word-break:break-word}.note{background:#f1f5f5;padding:12px}.muted{color:#526477;font-size:10pt}a{color:#155a7a}p{margin-top:4px;margin-bottom:6px}h3{font-size:11pt;margin:10px 0 4px}tr{page-break-inside:avoid}@media print{body{margin:0}h2{page-break-after:avoid}thead{display:table-header-group}}</style></head><body>',
        '<h1>Consulta ambiental e fundiária</h1>',
        '<p><b>'+esc(prop['name'])+'</b> · UF '+esc(prop['uf'])+' · CAR '+esc(prop.get('car') or 'não informado')+'</p>',
        '<p class="muted">Consulta em '+esc(report['generated_at'])+' (UTC) · duração '+esc(report['elapsed_seconds'])+' s · orçamento de consulta: até 5 minutos.</p>',
        '<p class="note">'+esc(report['scope'])+'</p>']
    found=[s for s in report['sources'] if s['records']]
    pending=[s for s in report['sources'] if not s['complete'] and s['status']!='not_applicable']
    lines+=['<h2>1. Resultado breve</h2>','<p>'+esc('Há registros para conferência nas fontes: '+', '.join(s['label'] for s in found)+'.' if found else 'Não foram identificados registros nas respostas concluídas. Isso não demonstra regularidade integral do imóvel.')+'</p>']
    if pending:lines+=['<p>'+esc(str(len(pending))+' fonte(s)/escopo(s) permanecem pendentes ou parciais. A ausência de resposta não é uma consulta negativa.')+'</p>']
    lines+=['<table><thead><tr><th>Base pública</th><th>Resultado</th><th>Registros</th></tr></thead><tbody>']
    for s in report['sources']:
        lines+=['<tr><td><a href="'+esc(s['portal'])+'">'+esc(s['label'])+'</a></td><td>'+esc(STATUSES[s['status']])+'</td><td>'+str(len(s['records']))+'</td></tr>']
    lines+=['</tbody></table>','<h2>2. Gleba, assentamento e situação fundiária</h2>']
    for value in land_summary(report).values():lines+=['<p>'+esc(value)+'</p>']
    lines+=['<h2>3. Registros relevantes</h2>']
    any_records=False
    for s in report['sources']:
        if not s['records']:continue
        any_records=True;lines+=['<h3>'+esc(s['label'])+'</h3>']
        for r in s['records'][:3]:
            props=r.get('properties',{})
            fields=[]
            for key in ('cod_imovel','status_legivel','condicao','situacao','nmassent','nmprojeto','denominaca','nomearea','nmimovel','imovel','nome_imovel','numero_emb','num_tad','numero_ai','num_auto_infracao','municipio','orgaogest','codsipra','parcelaco','numcertif','codcertif','situacimov','status','matricula','registrom','data_atualizacao','dataatual','atualizaca','datamodif','dat_embargo','data','julgamento','des_infracao','desc_inf_1'):
                if props.get(key):fields.append(display_field(key,props[key]))
            if r.get('car'):fields.append('CAR associado: '+r['car'])
            if r.get('kind'):fields.append(r['kind'])
            if r.get('tribunal'):fields.append('Tribunal: '+r['tribunal']+'; grau: '+r['grau'])
            if r.get('classe'):fields.append('Classe: '+str(r['classe'].get('nome','')))
            if r.get('last_movement'):fields.append('Último movimento disponível: '+str(r['last_movement'].get('nome',''))+' · '+str(r['last_movement'].get('dataHora','')))
            if r.get('processes'):fields.append('Processo(s): '+', '.join(r['processes']))
            if r.get('overlap_ha') is not None:
                fields.append('Interseção: {:.4f} ha ({:.2f}% do imóvel); não somar áreas de registros que se sobrepõem'.format(r['overlap_ha'],r['parcel_percent']))
            fields.append('Vínculo: '+r.get('relation','registro público'))
            lines+=['<p><b>Registro '+esc(r['id'])+'</b><br>'+ '; '.join(esc(v) for v in fields)+'</p>']
        if len(s['records'])>3:lines+=['<p class="muted">Exibidos 3 de '+str(len(s['records']))+' registros; todos estão no arquivo de evidências JSON/CSV.</p>']
    if not any_records:lines+=['<p>Nenhum registro disponível para detalhar nesta execução.</p>']
    lines+=['<h2>4. Alcance, fontes e próximas verificações</h2>']
    notes=set()
    for s in report['sources']:
        if s['note'] not in notes:
            notes.add(s['note'])
            title='Bases fundiárias ITERPA' if s['source'] in LAND_LAYERS else s['label']
            lines+=['<p><b>'+esc(title)+':</b> '+esc(s['note'])+'</p>']
        if s.get('warnings'):
            lines+=['<p><b>'+esc(s['label'])+' — pendências:</b> '+esc('; '.join(s['warnings'][:3]))+'</p>']
    lines+=['<p class="muted">Os nomes das bases no quadro de resultados abrem os portais oficiais. Data/hora de cada consulta, páginas e identificadores de evidência constam no JSON. As consultas sem data de atualização publicada representam a resposta obtida, sem garantia de atualização da base no dia da consulta.</p>']
    lines+=['<p class="note">CAR ativo não significa análise aprovada. Um registro espacial de embargo exige confirmar o termo, sua vigência e eventuais suspensões no órgão competente. Processo vinculado não significa decisão condenatória. Não foi pesquisado todo o universo de processos públicos. Registros fundiários não constituem certidão de domínio.</p>',
            '<p class="muted">Catálogo Multiespectral AOI 3.5 · Kayky Pessoa de Araujo · desenvolvido com assistência do OpenAI Codex. Dados: SICAR/SFB, IBAMA, ICMBio, SEMAS/PA, ITERPA e CNJ/DataJud, conforme disponibilidade. Projeto independente.</p></body></html>']
    return '\n'.join(lines)


def save_report(report, folder):
    root=Path(folder)
    root.mkdir(parents=True,exist_ok=True)
    stem='consulta_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
    paths={ext:str(root/(stem+'.'+ext)) for ext in ('html','json','csv')}
    contents={'html':render_html(report),'json':json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)}
    for ext,text in contents.items():
        with open(paths[ext]+'.part','w',encoding='utf8') as stream:stream.write(text)
        os.replace(paths[ext]+'.part',paths[ext])
    with open(paths['csv']+'.part','w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream,delimiter=';');writer.writerow(['base','resultado','registro','car','processos','area_intersecao_ha','percentual_imovel','vinculo','atributos_publicos'])
        for source in report['sources']:
            if not source['records']:writer.writerow([source['label'],STATUSES[source['status']],'','','','','',source['note'],''])
            for r in source['records']:
                def safe(value):
                    value=str(value if value is not None else '')
                    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
                writer.writerow([safe(v) for v in (source['label'],STATUSES[source['status']],r['id'],r.get('car',''),', '.join(r.get('processes',[])),r.get('overlap_ha'),r.get('parcel_percent'),r.get('relation',''),json.dumps(r.get('properties',{}),ensure_ascii=False))])
    os.replace(paths['csv']+'.part',paths['csv'])
    return paths


def export_pdf(html_text, path):
    from qgis.PyQt.QtGui import QTextDocument, QPageSize
    from qgis.PyQt.QtPrintSupport import QPrinter
    printer=QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    document=QTextDocument();document.setHtml(html_text)
    document.print_(printer) if hasattr(document,'print_') else document.print(printer)
    if not os.path.isfile(path) or os.path.getsize(path)<100:
        raise RuntimeError('O PDF não foi criado. O relatório HTML e as evidências foram mantidos.')
