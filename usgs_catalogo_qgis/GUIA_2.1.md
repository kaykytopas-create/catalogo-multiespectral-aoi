# Versão 2.1.0 experimental — análise automática e revisão

O plugin agora calcula uma **triagem espectral automática**, sem exigir que você classifique visualmente cada polígono antes. Ele examina os pixels, compara três datas e redige um relatório preliminar com indicadores, limitações e contexto técnico/legal. É um motor de regras explicáveis; não há modelo de IA treinado nem validação de acurácia em casos independentes.

## Instalar e preparar

1. No QGIS 3, use **Complementos → Gerenciar e instalar complementos → Instalar a partir de ZIP**, selecione o ZIP inteiro e reinicie o QGIS após substituir a versão anterior.
2. Importe pelo catálogo três composições **PRODES (SWIR1/NIR/vermelho)**: ano do registro e dois anos anteriores, preferindo o mesmo sensor e período do ano. O filtro de nuvens global continua abaixo de 20 por cento.
3. Para imagens antigas já baixadas, reimporte a mesma cena pelo catálogo com internet e a opção offline desmarcada: as bandas espectrais válidas são reutilizadas e as máscaras de qualidade faltantes são acrescentadas. O recorte RGB continua sendo uma camada por composição/data. Falha no download da máscara não impede visualizar o RGB, mas limita a análise automática.
4. Abra **Análise PRODES por imóvel**, atualize a lista de camadas e selecione o imóvel e os incrementos anuais oficiais do bioma. Confirme os metadados da origem. Para analisar 2022, por exemplo, desmarque “Mostrar todos os anos” e escolha 2022.
5. Clique em **Recortar no imóvel e preparar análise**. Na aba 2, escolha imagens de 2022, 2021 e 2020. Datas são preenchidas com a aquisição registrada. Os RGB compostos do catálogo usam posições **R=1, G=2, B=3**, correspondentes a SWIR1, NIR e vermelho.

Imagens externas sem procedência/calibração registrada não são aceitas no modo automático. O modo de avaliação visual assistida continua disponível para outros arquivos. Antes da comparação, as três imagens devem estar no projeto; apenas baixar arquivos ou abrir polígonos não produz evidência raster no mapa.

## Analisar automaticamente

Clique em **Analisar pixels e gerar relatório automaticamente**. Os campos “Visual atual/anterior/dois anos antes” e “Conferência visual” pertencem ao modo assistido e podem permanecer vazios.

O processamento roda em segundo plano e pode ser cancelado. O relatório abre na aba 4. Para comparar imagens e limites, use o botão de comparação da aba 2 e alterne as datas na aba 3.

O relatório apresenta, por polígono:

- UUID, classe, ano, referência oficial, áreas e correções geométricas;
- NDVI e NDMI medianos, cobertura válida e quantidade de pixels por data;
- diferença temporal nos mesmos pixels, proporção de queda conjunta e resolução real;
- hipótese espectral, critérios que impediram concluir e checagens sugeridas;
- referências técnicas e contexto legal, separados da opinião do revisor.

Resultados possíveis incluem sinal compatível com perda de cobertura, indício espectral de divergência temporal, resposta majoritariamente estável e inconclusivo. **Nenhum desses resultados comprova sozinho que um PRODES é falso ou verdadeiro.** Índices altos não distinguem floresta nativa, pasto e regeneração. Datas alternativas não garantem reproduzir a imagem de referência oficial.

## Regras e qualidade

As bandas são convertidas em reflectância antes dos índices. Landsat C2 usa escala 0,0000275 e deslocamento −0,2; Sentinel usa escala/metadados e baseline de processamento, inclusive deslocamento −0,1 quando aplicável.

NDVI usa NIR/vermelho; NDMI usa NIR/SWIR1. NDMI não é NBR. As imagens são reprojetadas em grade UTM comum na resolução mais grossa, com vizinho mais próximo. SWIR Sentinel tem resolução nativa de 20 m, mesmo em VRT visual de 10 m; Landsat tem 30 m. Não há criação de detalhe nem preenchimento de lacunas.

Os centros dos pixels precisam estar dentro do recorte. NoData, reflectâncias fora de [0,1], denominadores inválidos, nuvens, sombras, neve e saturação identificadas pelas máscaras são excluídos. Falhas reais Landsat 7 permanecem excluídas. A comparação usa a interseção dos pixels válidos nas três datas.

Limiares próprios, experimentais e publicados no relatório/código: ao menos 9 pixels comuns, cobertura de 80%; queda conjunta de NDVI ≤−0,20 e NDMI ≤−0,15 em 60% dos pixels; estabilidade até 0,05 em ambos os índices em 80% dos pixels nas duas comparações. Limite sazonal de 60 dias. **Não são limiares oficiais do INPE nem têm probabilidade de acerto medida.**

Máscaras ausentes, cobertura insuficiente, sensores diferentes sem harmonização validada, amostra pequena ou histórico incompatível produzem inconclusivo. Métricas exploratórias disponíveis continuam apresentadas. Não há detecção automática de deslocamento residual; confira o mapa. Diferentes anos encontrados no imóvel precisam de conjuntos de imagens próprios.

## Concordar ou discordar

Na aba 2, use **Minha revisão automática → Concordo / Discordo** e acrescente Notas. O relatório se atualiza imediatamente e mantém o resultado automático original. “A revisar” permanece registrado quando ninguém se manifestou. Discordância não transforma o resultado calculado em outro parecer.

Mudanças de imagem, bandas, data, limite, ano ou origem invalidam a análise; execute novamente. Atualizar a lista de camadas também exige preparar o recorte novamente. Alterar nome/CAR/revisor ou notas atualiza a revisão sem recalcular os pixels.

## Exportar

Na aba 4, exporte o pacote: PDF, HTML, três mapas PNG quando as imagens estão disponíveis, GeoPackage e manifesto com resultados, parâmetros, fontes radiométricas, caminhos de evidências e hashes dos arquivos exportados. Os rasters e máscaras ficam no acervo; conserve-os para reproduzir a análise offline. O pacote não inclui as imagens originais e não é enviado a terceiros.

## Referências e interpretação legal

O relatório cita a orientação INPE de 2026 sobre uso de PRODES para conformidade ambiental, as fontes USGS/Copernicus dos índices e máscaras e o texto compilado da Lei 12.651/2012, consultado em 06/10/2026.

O art. 3º, IV, demanda histórico de ocupação e requisitos de uso para área rural consolidada; o plugin não presume esse enquadramento pela imagem. O art. 26 trata de CAR e autorização prévia para supressão para uso alternativo do solo. Autorizações e demais documentos não são analisados automaticamente. PRODES registra supressão e não decide legalidade. Regeneração recente ou autorização não demonstram erro histórico de mapeamento.

Referências:

- [INPE — orientação PRODES, 2026](https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf)
- [Lei 12.651/2012 — texto compilado](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm)
- [USGS — NDMI](https://www.usgs.gov/landsat-missions/normalized-difference-moisture-index)
- [USGS — qualidade Collection 2](https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands)
- [Copernicus — processamento Sentinel-2](https://sentiwiki.copernicus.eu/web/s2-processing)

Validação desta entrega: 69 testes automatizados, incluindo GDAL real; fluxo completo com QGIS 3.34.4, imagens sintéticas, processamento em segundo plano, máscaras, revisão independente, mapas/PDF/GeoPackage. As geometrias reais anteriormente problemáticas também foram verificadas. Isso valida funcionamento, **não acurácia em contestação PRODES**. Outras versões/instalações QGIS e casos de campo precisam de validação.
