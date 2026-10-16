# SPDX-License-Identifier: GPL-2.0-or-later
"""Curated, versioned official guidance. Summaries, not automatic legal advice."""
KNOWLEDGE_VERSION = '2026-10-06.1'
INPE = 'https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf'
RULES = [
 {'id':'LAW_CONSOLIDATED','title':'Área rural consolidada','locator':'Lei 12.651/2012, art. 3º, IV',
  'url':'https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm',
  'tags':['consolidada'], 'summary':'O enquadramento depende de ocupação antrópica anterior a 22/07/2008 e dos usos definidos na lei. A camada técnica e os índices não homologam esse enquadramento.'},
 {'id':'INPE_PRODUCT','title':'Escolha do produto','locator':'INPE 2026, quadro síntese e seção 7','url':INPE,
  'tags':['fonte'],'summary':'Para avaliar propriedades, verificar incrementos anuais por bioma e a classe do registro. Máscaras acumuladas e resíduos têm limitações distintas.'},
 {'id':'INPE_REVIEW','title':'Revisão e legalidade','locator':'INPE 2026, seções 8–9','url':INPE,
  'tags':['data','consolidada','fogo'],'summary':'Revisão exige demonstrar divergência do mapa em relação à imagem de referência. O PRODES não avalia legalidade. Regeneração ou autorização não retiram automaticamente o registro.'},
 {'id':'INPE_SMALL','title':'Polígonos pequenos na Amazônia','locator':'INPE 2026, quadro síntese e seção 7','url':INPE,
  'tags':['amostra'],'summary':'Na Amazônia, polígonos originais menores que 6,25 ha não devem fundamentar avaliação de conformidade segundo essa orientação. Isso não comprova erro do mapa e não é um limiar aplicado à parte recortada do imóvel.'},
 {'id':'INPE_BORDER','title':'Tolerância de sobreposição CAR','locator':'INPE 2026, seção 10','url':INPE,
  'tags':['borda'],'summary':'Conferir a sobreposição considerando faixa interna de dois pixels Landsat, de 60 m, nos limites CAR. O diagnóstico espacial não determina a classificação temática.'},
 {'id':'USGS_QA','title':'Qualidade local das imagens','locator':'USGS, Landsat Collection 2 Quality Assessment Bands',
  'url':'https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands',
  'tags':['amostra'],'summary':'As bandas QA identificam condições como nuvens, sombras e saturação. A porcentagem de nuvens da cena não substitui a avaliação dos pixels dentro da área analisada.'},
 {'id':'USGS_NBR','title':'Indicador de perturbação','locator':'USGS, Landsat Normalized Burn Ratio',
  'url':'https://www.usgs.gov/landsat-missions/landsat-normalized-burn-ratio',
  'tags':['fogo'],'summary':'NBR usa infravermelho próximo e SWIR2. A interpretação causal e a autoria de um evento exigem evidências adicionais; o índice não é uma decisão jurídica.'}]


def retrieve(tags):
    wanted = set(tags) | {'fonte','data','amostra'}
    return [dict(rule, checked_on='2026-10-06', knowledge_version=KNOWLEDGE_VERSION)
            for rule in RULES if wanted.intersection(rule['tags'])]
