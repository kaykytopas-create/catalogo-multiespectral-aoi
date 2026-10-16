# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""TerraBrasilis access and conservative, auditable evidence rules.

No image classifier is claimed: spectral interpretation is supplied by the
reviewer, and missing evidence produces an inconclusive result.
"""
import html
import json
import re
from datetime import date
from urllib.parse import urlencode

ENDPOINT = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
GUIDANCE = "https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf"
RULE_VERSION = "2.0.0-assisted-1"


class ProdesError(Exception):
    pass


def capabilities(data, reader_factory=None):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ProdesError("XML com declarações externas não é aceito.")
    if reader_factory is None:
        from qgis.PyQt.QtCore import QXmlStreamReader
        reader_factory = QXmlStreamReader
    reader = reader_factory(data)
    layers = []
    values = None
    while not reader.atEnd():
        reader.readNext()
        tag = str(reader.name())
        if reader.isStartElement():
            if tag == "FeatureType":
                values = {}
            elif values is not None and tag in ("Name", "Title"):
                values[tag] = str(reader.readElementText())
        elif reader.isEndElement() and tag == "FeatureType" and values is not None:
            name, title = values.get("Name", ""), values.get("Title", "")
            if "prodes" in (name + " " + title).lower():
                layers.append((name, title or name))
            values = None
    if reader.hasError():
        raise ProdesError("Resposta WFS inválida: " + str(reader.errorString()))
    if not layers:
        raise ProdesError("O serviço não informou camadas PRODES. Use um arquivo vetorial oficial local.")
    return sorted(set(layers))


def record(properties):
    values = {str(key).lower(): value for key, value in properties.items()}
    classification = str(values.get("class_name", values.get("classname", ""))).strip()
    match = re.fullmatch(r"d(\d{4})", classification.lower())
    acquired = values.get("image_date", values.get("image_data", ""))
    if hasattr(acquired, "toString"):
        acquired = acquired.toString("yyyy-MM-dd")
    elif hasattr(acquired, "isoformat"):
        acquired = acquired.isoformat()[:10]
    return {"uuid": str(values.get("uuid", "")), "class": classification,
            "year": int(match.group(1)) if match else None,
            "image_date": str(acquired or "")}


def annual_layers(layers):
    """Offer annual biome products, avoiding reference and accumulated maps."""
    return [(name, title) for name, title in layers
            if "yearly_deforestation" in name.lower()
            and "legal-amz" not in name.lower()
            and "smaller" not in name.lower()
            and "deter" not in name.lower()]


class TerraBrasilis:
    def __init__(self, cancelled=lambda: False, request=None):
        self.cancelled = cancelled
        self.request = request or self._get

    def _get(self, params):
        if self.cancelled():
            raise ProdesError("Operação cancelada.")
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
        request = QNetworkRequest(QUrl(ENDPOINT + "?" + urlencode(params)))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setRawHeader(b"User-Agent", b"QGIS-Catalogo-Multiespectral/2.0")
        response = QgsNetworkAccessManager.blockingGet(request, forceRefresh=True)
        if self.cancelled():
            raise ProdesError("Operação cancelada.")
        status = response.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if response.error() != QNetworkReply.NetworkError.NoError or status is None or not 200 <= int(status) < 300:
            raise ProdesError("Falha no TerraBrasilis (HTTP {}). Use a fonte oficial local ou tente novamente.".format(status))
        data = bytes(response.content())
        if len(data) > 32 * 1024 * 1024:
            raise ProdesError("Resposta excede 32 MB. Reduza a área consultada.")
        return data

    def layers(self):
        return capabilities(self.request({"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"}))

    def features(self, name, rect, progress=lambda value: None):
        if not re.fullmatch(r"[A-Za-z0-9_:.\-]+", name):
            raise ProdesError("Nome de camada inválido.")
        # Explicit longitude/latitude CRS avoids EPSG:4326 axis ambiguity in WFS2.
        crs = "urn:ogc:def:crs:OGC:1.3:CRS84"
        size, start, all_features, seen, pages = 500, 0, [], set(), set()
        total = None
        while True:
            if self.cancelled():
                raise ProdesError("Operação cancelada.")
            progress("Consultando polígonos PRODES: {} recebidos…".format(len(all_features)))
            raw = self.request({"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": name, "srsName": crs, "bbox": ",".join(map(str, rect)) + "," + crs,
                "outputFormat": "application/json", "count": size, "startIndex": start})
            try:
                data = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise ProdesError("O WFS não retornou GeoJSON. Consulte a disponibilidade da camada.") from exc
            if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
                raise ProdesError("Resposta WFS incompleta ou inválida.")
            features = data["features"]
            declared = data.get("numberMatched", data.get("totalFeatures"))
            if str(declared).isdigit():
                if total is not None and total != int(declared):
                    raise ProdesError("A base mudou durante a consulta. Faça uma nova consulta.")
                total = int(declared)
            if not features:
                break
            signature = json.dumps(features, sort_keys=True)
            if signature in pages:
                raise ProdesError("O WFS repetiu a paginação; resultado parcial recusado.")
            pages.add(signature)
            for feature in features:
                if feature.get("type") != "Feature" or not feature.get("geometry"):
                    raise ProdesError("Feição sem geometria na resposta WFS.")
                uid = record(feature.get("properties") or {})["uuid"]
                key = uid or str(feature.get("id") or json.dumps(feature, sort_keys=True))
                if key not in seen:
                    seen.add(key)
                    all_features.append(feature)
            start += len(features)
            if total is not None and start >= total:
                break
            # Unknown totals require another page even if the server silently
            # caps responses below our requested page size.
            if start >= 50000:
                raise ProdesError("Consulta excedeu 50 mil feições. Reduza a área.")
        if total is not None and len(all_features) != total:
            raise ProdesError("Consulta incompleta: {} de {} polígonos. Nenhum resultado parcial será aplicado.".format(len(all_features), total))
        return {"type": "FeatureCollection", "features": all_features}


def evaluate(item, observations, dates, reviewed, annual_layer, tolerance=False):
    """Evaluate declared evidence, never infer land-cover truth from RGB alone."""
    result = {"status": "Inconclusivo", "reason": "", "rule_version": RULE_VERSION,
              "observations": list(observations), "dates": list(dates), "reviewed": bool(reviewed)}
    if not annual_layer or item.get("year") is None:
        reason = "Classe ou origem sem confirmação de incremento anual por bioma. Não é possível aplicar o protocolo."
    elif not item.get("uuid"):
        reason = "UUID oficial ausente. Identifique o polígono na base oficial antes de emitir conclusão."
    elif tolerance and item.get("core_ha") is not None and item["core_ha"] <= 0.000001:
        result["status"] = "Sobreposição restrita à borda"
        reason = "A interseção está integralmente na faixa interna de 60 m do CAR. Este diagnóstico espacial não demonstra erro de mapeamento."
    elif not reviewed:
        reason = "Falta revisão das imagens, qualidade local, sazonalidade e alinhamento."
    else:
        try:
            parsed = [date.fromisoformat(value) for value in dates]
        except (ValueError, TypeError):
            parsed = []
        if len(parsed) != 3 or not parsed[2] < parsed[1] < parsed[0]:
            reason = "São necessárias três datas distintas, ordenadas da mais recente à mais antiga."
        elif parsed[0].year != item["year"] or parsed[1].year != item["year"] - 1 or parsed[2].year != item["year"] - 2:
            reason = "As imagens não cobrem o ano do registro e os dois anos anteriores. Selecione um conjunto por ano PRODES."
        elif len(observations) != 3 or "unknown" in observations:
            reason = "Interpretação espectrotemporal incompleta ou observação insuficiente."
        elif observations == ["suppressed", "native", "native"]:
            result["status"] = "Compatível com o registro"
            reason = "As interpretações declaradas indicam cobertura nativa nos dois anos anteriores e supressão no ano registrado. Resultado preliminar baseado em revisão visual."
        elif observations[1] == "suppressed" or observations[2] == "suppressed":
            result["status"] = "Indícios de inconsistência temporal"
            reason = "Foi declarada supressão em imagem anterior ao ano registrado. Verificar primeira ocorrência, nuvens históricas, resíduos e expansão de supressão antes de solicitar revisão."
        elif observations == ["native", "native", "native"]:
            result["status"] = "Indícios de inconsistência temática"
            reason = "Foi declarada manutenção de cobertura nativa nas três imagens. Confirmar referência oficial, textura, contexto e ausência de regeneração antes de solicitar revisão."
        else:
            reason = "A sequência declarada é ambígua. Não há evidência suficiente para concluir compatibilidade ou inconsistência."
    result["reason"] = reason
    return result


def report_html(context, rows, maps=()):
    if context.get("Relatório simples") or any(row.get("history") for row in rows) or any(isinstance(value, dict) for value in maps):
        from .prodes_report import readable_report
        return readable_report(context, rows, maps)
    return _technical_report_html(context, rows, maps)


def _technical_report_html(context, rows, maps=()):
    automatic = any(row.get("mode") == "automatic" or row.get("contestability") for row in rows)
    esc = lambda value: html.escape("Sim" if value is True else "Não" if value is False else str(value), quote=True)
    body = """<html><head><meta charset='utf-8'><style>
body{font-family:Arial,sans-serif;color:#20343d;font-size:11pt}h1{font-size:20pt;color:#155b55}
h2{font-size:14pt;color:#155b55}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd8da;padding:6px;text-align:left}
th{background:#eaf3f1}.note{background:#fff3d8;padding:10px}img{width:680px}p{line-height:1.35}
</style></head><body><h1>Análise preliminar PRODES por imóvel</h1>"""
    body += ("<p class='note'>Versão experimental 2.2.0. Triagem de fundamentos para contestação, com classificação técnica de consolidada informada e evidências espectrais. Não é IA treinada, parecer oficial ou homologação da classificação pelo órgão. Resultado automático e revisão do usuário são separados.</p>" if automatic else
        "<p class='note'>Versão experimental 2.2.0. Avaliação assistida por interpretação visual do usuário; não há classificador automático de falsos PRODES. Documento não emitido pelo INPE.</p>")
    body += "<h2>Identificação e fontes</h2><table>"
    for key, value in context.items():
        body += "<tr><th>{}</th><td>{}</td></tr>".format(esc(key), esc(value))
    body += "</table><h2>Procedimento aplicado</h2><p>Interseção exata dos incrementos com o imóvel, preservando UUID e áreas geodésicas. Resultados limitados à parcela interceptada.</p>"
    if automatic:
        body += "<p>Bandas brutas de reflectância calibradas por coleção/baseline; NDVI=(NIR−vermelho)/(NIR+vermelho), NDMI=(NIR−SWIR1)/(NIR+SWIR1). Três datas em grade UTM comum na resolução mais grossa, vizinho mais próximo, sem preencher lacunas. Amostragem pelos centros dos pixels internos; diferenças calculadas nos mesmos pixels válidos nas três datas. Não há verificação automática de deslocamento residual ou análise de textura.</p>"
        body += "<p>QA_PIXEL remove preenchimento, nuvens/cirros, sombras e neve; QA_RADSAT exclui saturação/oclusão. Para Sentinel, SCL aceita classes 4, 5 e 6. Valores fora de [0,1], NoData e denominadores inválidos são excluídos. Máscaras ausentes, sensores mistos sem harmonização validada ou datas sazonais incompatíveis impedem parecer espectral conclusivo.</p>"
        body += "<p>Regras experimentais: ao menos 9 pixels comuns e cobertura de 80%; sinal de queda quando ΔNDVI≤−0,20 e ΔNDMI≤−0,15 em pelo menos 60% dos pixels; estabilidade quando diferenças absolutas em ambos os índices não ultrapassam 0,05 em pelo menos 80% dos pixels nas duas comparações. Intervalo sazonal máximo de 60 dias. Esses limiares não pertencem à metodologia oficial do INPE e não têm acurácia medida. Os índices medem resposta espectral e não classificam origem nativa da vegetação.</p>"
    body += "<p>As regras de triagem deste plugin são próprias, conservadoras e não homologadas. Faltas de observação produzem resultado inconclusivo. Tolerância cartográfica, quando ativada para CAR, é diagnóstico separado. Regeneração posterior ou autorização de supressão não demonstram erro no registro histórico.</p>"
    body += "<h2>Resultados por polígono</h2>"
    for row in rows:
        acquisition = row.get("acquisition")
        if acquisition:
            body += "<p><b>Busca automática:</b> ano PRODES {}; referência sazonal {}; datas obtidas: {}.<br>Cenas: {}. Referência pré-marco: {}. A seleção é uma alternativa pública, não necessariamente a imagem original interpretada pelo INPE.</p>".format(
                esc(acquisition["year"]), esc(acquisition["reference_date"]), esc(acquisition["dates"]),
                esc(acquisition["scene_ids"]), esc(acquisition.get("historical_scene") or "Não obtida"))
        contest = row.get("contestability")
        if contest:
            body += "<h3>Triagem de contestação — {}</h3><p><b>{}</b><br>{}<br>Escopo da indicação: {:.4f} ha. Base legal: {}. Base técnica: {}.</p>".format(
                esc(row.get("uuid", "Sem UUID")), esc(contest["status"]), esc(contest["reason"]),
                contest.get("scope_ha", 0), esc(contest["legal_basis"]), esc(contest["technical_basis"]))
            body += "<p><b>Área consolidada:</b> {}. Sobreposição: {:.4f} ha. Não extrapolar essa classificação para o restante do polígono.</p>".format(
                esc(row.get("consolidation_assessment", "Não informada")), row.get("consolidated_ha", 0))
            historical = row.get("historical", {})
            metrics = historical.get("metrics", {})
            body += "<p><b>Corroboração histórica:</b> {}. Data: {}. {}<br>Pixels válidos: {}; cobertura: {:.1f}%; resposta de pouca cobertura verde: {:.1f}% dos pixels válidos.</p>".format(
                esc(historical.get("status", "Não avaliada")), esc(historical.get("date", "Não fornecida")),
                esc(historical.get("reason", "")), metrics.get("common_pixels", 0),
                100 * metrics.get("common_coverage", 0), 100 * metrics.get("low_cover_fraction", 0))
        body += "<h3>{} — {}</h3><p>Classe: {}; ano: {}; imagem de referência: {}.<br>Área original: {:.4f} ha; interseção: {:.4f} ha; núcleo além da borda: {}.</p><p><b>{}</b><br>{}</p>".format(
            esc(row.get("uuid", "Sem UUID")), esc(row.get("status", "Inconclusivo")),
            esc(row.get("class", "")), esc(row.get("year", "")), esc(row.get("image_date", "Não informada")),
            row.get("original_ha", 0), row.get("clip_ha", 0), esc(row.get("core_ha", "não avaliado")),
            esc(row.get("status", "Inconconclusivo")), esc(row.get("reason", "")))
        if row.get("mode") == "automatic":
            stats = row.get("automatic", {})
            body += "<p><b>Sinal calculado:</b> {}. Resolução da grade: {} m; pixels comuns: {}; cobertura comum: {}.</p>".format(
                esc(row.get("spectral_signal", "Não calculado")), esc(stats.get("resolution_m", "—")),
                esc(stats.get("common_pixels", 0)), esc("{:.1f}%".format(100 * stats.get("common_coverage", 0))))
            body += "<table><tr><th>Data</th><th>Pixels válidos</th><th>Cobertura local</th><th>NDVI mediano</th><th>NDMI mediano</th></tr>"
            for when, values in zip(row.get("dates", []), stats.get("per_date", [])):
                fmt = lambda v: "—" if v is None else "{:.3f}".format(v)
                body += "<tr><td>{}</td><td>{}</td><td>{:.1f}%</td><td>{}</td><td>{}</td></tr>".format(
                    esc(when), values["valid_pixels"], 100 * values["coverage"], fmt(values["ndvi_median"]), fmt(values["ndmi_median"]))
            body += "</table><p><b>Opinião do revisor:</b> {}. Notas: {}.</p>".format(esc(row.get("user_review", "A revisar")), esc(row.get("notes", "")))
        else:
            body += "<p>Observações (atual, anterior, dois anos antes): {}. Datas: {}. Revisão declarada: {}. Notas: {}</p>".format(
                esc(", ".join(row.get("observations", []))), esc(", ".join(row.get("dates", []))),
                esc(row.get("reviewed", False)), esc(row.get("notes", "")))
        if row.get("geometry_repaired"):
            body += "<p>Geometria corrigida para o recorte: partes poligonais preservadas; eventuais remanescentes de linhas/pontos não geram área.</p>"
    if not rows:
        body += "<p>Nenhum incremento da classe/ano selecionado interceptou o imóvel na fonte consultada. Isso não certifica ausência de supressão ou conformidade ambiental.</p>"
    for caption, filename in maps:
        body += "<h2>{}</h2><img src='{}'>".format(esc(caption), esc(filename))
    if automatic:
        from .prodes_auto import LAW, AUTO_RULE_VERSION
        body += "<h2>Enquadramento técnico e legal para revisão</h2><p>A orientação INPE (2026) exige comparação do ano analisado e dois anteriores. A data oficial de referência delimita a interpretação; datas alternativas escolhidas no plugin não garantem reproduzir o registro. Regeneração ou supressão autorizada não removem automaticamente um registro PRODES.</p>"
        body += "<p>A camada de consolidada selecionada e identificada como produto de análise técnica é tratada como classificação de entrada do profissional, não como classificação produzida pelos índices. O cruzamento usa união geométrica para evitar contar sobreposições entre feições da mesma camada duas vezes. A indicação de contestação documental vale somente para a parte interceptada e deve ser corroborada antes do pedido.</p>"
        body += "<p>O indicador pré-marco é experimental: NDVI de 0,05 a 0,35, NDMI até 0,10 e NIR ao menos 0,15 em 60% dos pixels válidos; exige aquisição anterior a 22/07/2008, máscaras locais, 9 pixels e cobertura de 80%. Mede pouca cobertura verde/solo relativamente exposto, também possível em ambientes naturais; não identifica autonomamente atividade humana. Pastagem verde ou pousio podem não satisfazer o indicador.</p>"
        body += "<p>Arts. 29 e 61-A da Lei 12.651/2012: CAR é instrumento cadastral; consolidação não dispensa avaliar as condições aplicáveis a APP. APP, Reserva Legal, módulos fiscais e recomposição não foram calculados nesta triagem. O relatório não certifica regularidade ambiental nem conclui dispensa de recuperação.</p>"
        body += "<p>Lei 12.651/2012: o art. 3º, IV, define área rural consolidada mediante ocupação anterior a 22/07/2008 e requisitos de uso; índices espectrais e ano de uma classe não comprovam esses requisitos. O art. 26 trata de CAR e autorização prévia para supressão de vegetação nativa para uso alternativo do solo. Autorização, enquadramento territorial e histórico documental não foram examinados; legalidade permanece não avaliada. <a href='{}'>Texto legal compilado, consultado em 06/10/2026</a>.</p>".format(LAW)
        body += "<p>Referências espectrais: <a href='https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index'>USGS: NDMI</a>; <a href='https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands'>USGS: QA Collection 2</a>; <a href='https://sentiwiki.copernicus.eu/web/s2-processing'>Copernicus: processamento Sentinel-2</a>.</p>"
    body += "<h2>Referência e revisão</h2><p>INPE (2026), O uso dos dados do PRODES para avaliar a conformidade ambiental de propriedades rurais. <a href='{}'>Documento oficial</a>. Divergências podem ser submetidas ao Canal de Atendimento BiomasBR com identificação do imóvel e UUIDs. Esta exportação não envia solicitação.</p><p>Regras: {}. Desenvolvido por Kayky Pessoa de Araujo em colaboração com OpenAI Codex. Dados PRODES: INPE/TerraBrasilis; Landsat: USGS/NASA; Sentinel: ESA/Copernicus.</p></body></html>".format(GUIDANCE, (context.get("Regras", AUTO_RULE_VERSION) + " / " + AUTO_RULE_VERSION) if automatic else RULE_VERSION)
    return body
