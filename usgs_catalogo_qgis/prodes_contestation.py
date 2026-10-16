# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 Kayky Pessoa de Araujo
"""Preliminary contestability rules, distinguishing land use from PRODES truth."""
from datetime import date
from .prodes_auto import THRESHOLDS

CONTEST_RULE_VERSION = "2.3.1-contestation-1"
CUTOFF = date(2008, 7, 22)
HISTORICAL_LIMITS = {"ndvi_max": 0.35, "ndvi_min": 0.05, "ndmi_max": 0.10,
                     "nir_min": 0.15, "low_cover_fraction": 0.60}


def historical_assessment(stats, acquired):
    result = {"date": acquired, "metrics": stats, "status": "Não identificada",
              "usable": False, "low_cover": False, "reason": ""}
    try:
        when = date.fromisoformat(acquired)
    except (ValueError, TypeError):
        result["reason"] = "Data histórica não identificada nos metadados."
        return result
    if when >= CUTOFF:
        result["reason"] = "Imagem não é anterior a 22/07/2008; não demonstra ocupação preexistente ao marco."
    elif stats.get("error"):
        result["reason"] = stats["error"]
    elif not stats.get("qa_complete"):
        result["reason"] = "Qualidade local histórica incompleta; não assumir nuvens/sombras como uso do solo."
    elif stats.get("common_pixels", 0) < THRESHOLDS["min_pixels"] or stats.get("common_coverage", 0) < THRESHOLDS["min_coverage"]:
        result["reason"] = "Histórico sem amostra/cobertura suficiente na sobreposição com a consolidada."
    else:
        result["usable"] = True
        result["low_cover"] = stats.get("low_cover_fraction", 0) >= HISTORICAL_LIMITS["low_cover_fraction"]
        if result["low_cover"]:
            result["status"] = "Área candidata à consolidação; uso antrópico não comprovado"
            result["reason"] = "Antes do marco, {:.1f}% dos pixels válidos apresentavam pouca cobertura verde/solo relativamente exposto. Esse padrão também pode ocorrer naturalmente; identificar uso agrossilvipastoril, pousio, edificações ou benfeitorias com evidência independente (art. 3º, IV).".format(100 * stats["low_cover_fraction"])
        else:
            result["status"] = "Consolidação não identificada pelo indicador"
            result["reason"] = "Não foi detectado o padrão experimental de pouca cobertura verde. Isso não exclui pastagem verde, pousio ou benfeitorias; a origem da vegetação não é classificada pelo índice."
    return result


def contestability(item, spectral, historical=None, annual=False, tolerance=False, technical=False):
    overlap = max(0.0, float(item.get("consolidated_ha", 0)))
    result = {"status": "Evidências insuficientes", "reason": "", "rule_version": CONTEST_RULE_VERSION,
              "consolidated_ha": overlap, "scope_ha": 0,
              "legal_basis": "Lei 12.651/2012, art. 3º, IV; classificação técnica fornecida" if technical else "Lei 12.651/2012, art. 3º, IV; enquadramento não informado",
              "technical_basis": "INPE 2026, comparação espectrotemporal e revisão por UUID"}
    if not annual or not item.get("year") or not item.get("uuid"):
        result["reason"] = "É preciso confirmar a base de incrementos anuais por bioma, o ano e o UUID oficial."
    elif tolerance and item.get("core_ha") is not None and item["core_ha"] <= 0.000001:
        result["reason"] = "Sobreposição restrita à faixa CAR de 60 m: avaliar vínculo espacial, sem concluir divergência de mapeamento."
        result["technical_basis"] = "INPE 2026, seção 10: tolerância cartográfica PRODES/CAR"
    elif spectral.get("status") == "Indício espectral de divergência temporal":
        result.update(status="Passível de contestação (triagem)",
            scope_ha=item.get("clip_ha", 0),
            reason="Foi detectada queda conjunta dos índices já no ano anterior ao registro, com qualidade suficiente. Priorizar revisão temporal do recorte; conferir imagem oficial, resíduos, expansão e textura antes de solicitar correção. Não determina a primeira supressão nem a nova data correta.")
    elif spectral.get("status") == "Sinal compatível com perda de cobertura":
        if overlap > 0 and (technical or (historical and historical.get("usable") and historical.get("low_cover"))):
            result["reason"] = "Evidências conflitantes: área rural consolidada informada pelo técnico ou pista pré-marco e perda posterior detectada. Verificar regeneração, uso histórico e floresta primária; não presumir erro do PRODES."
        else:
            result.update(status="Sem indícios suficientes para contestação",
                reason="A sequência espectral apresenta perda no ano registrado. A sobreposição com uma área nomeada consolidada, isoladamente, não demonstra divergência do PRODES. Este resultado não impede novas evidências ou revisão técnica.")
    elif technical and overlap > 0:
        result.update(status="Passível de contestação (triagem)", scope_ha=overlap,
            reason="Existe sobreposição do incremento com área rural consolidada delimitada por análise técnica nos termos do art. 3º, IV. Essa informação de ocupação preexistente ao marco constitui fundamento para investigar divergência temporal/temática, limitado à área sobreposta. A indicação se baseia na classificação técnica fornecida, não em reconhecimento autônomo de uso pelo NDVI. Confirmar documentos e imagens oficiais antes de protocolar; não indica exclusão automática.")
        if not historical or not historical.get("usable"):
            result["reason"] += " A classificação técnica não foi corroborada por imagem pré-marco utilizável neste processamento."
        elif not historical.get("low_cover"):
            result["reason"] += " A imagem histórica não apresenta o indicador de pouca cobertura verde; isso não refuta pastagem verde/pousio, mas exige conferir o uso descrito pelo técnico."
    elif overlap > 0 and historical and historical.get("usable") and historical.get("low_cover"):
        # A pre-2008 bare/low-green-cover indicator alone is not a native-cover
        # classifier. It is a lead for investigation, never a positive verdict.
        result["reason"] = "Há pista histórica pré-marco em {:.4f} ha sobrepostos, mas pouca cobertura verde não comprova ocupação antrópica ou erro de incremento. Confirmar o tipo de uso e a cobertura nativa na imagem oficial; ainda não há base suficiente para indicar contestação.".format(overlap)
    elif spectral.get("status") == "Resposta espectral majoritariamente estável":
        result["reason"] = "Índices majoritariamente estáveis não demonstram preservação de vegetação nativa: pastagem, regeneração ou perda estrutural podem ter resposta semelhante. Conferir textura e contexto na imagem oficial."
    else:
        result["reason"] = "O conjunto não sustenta indicação de contestação. " + spectral.get("reason", "Histórico/qualidade insuficiente.")
    if overlap > 0:
        result["reason"] += " Sobreposição consolidada/PRODES: {:.4f} ha ({:.1f}% do recorte); fonte técnica informada, sem homologação automática pelo plugin.".format(overlap, 100 * overlap / item["clip_ha"] if item.get("clip_ha", 0) > 0 else 0)
    return result
