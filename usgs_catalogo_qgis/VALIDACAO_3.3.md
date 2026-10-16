# Validação 3.3 experimental

167 testes automatizados passaram, sem testes pulados, no runtime QGIS 3.34.4, GDAL e Qt offscreen. Incluem a detecção de nuvem localizada dentro do limite, ignorar nuvens fora dele, preenchimento e sombra, limites radiométricos comuns na cor natural, filtro zero preservado, tentativas de datas alternativas no mesmo ano e contabilização de anos com falhas.

Integração nativa: transporte e catálogo simulados; rasters e máscaras GeoTIFF reais, GDAL e inserção efetiva no projeto QGIS. Uma cena com nuvens foi rejeitada, outra com 25 por cento de NoData nas bandas foi descartada e uma terceira do mesmo ano foi importada. Verificados limites de contraste dos três canais, duas imagens anuais completas, ano sem candidata e destino somente acervo sem novas camadas.

Não foram realizados downloads online reais nesta atualização. Não foi avaliada acurácia temática, nitidez em imóveis reais, disponibilidade de anos solicitados ou modelos de IA. A QA é classificação fornecida pelo produto e a inspeção usa amostragem; pode haver erros ou detalhes não capturados. As melhorias não aumentam a resolução física do sensor.

Argumentação: testada persistência dos quatro eixos de revisão, preservação do resultado/área, ausência de dados do cliente de referência, condição de revisão temporal e distinção entre falta de evidência e contestação positiva. Avaliador de acurácia testado contra abstenções, classes desbalanceadas, amostra pequena e UUID repetido. Nenhum conjunto ambiental real foi avaliado; a meta de 80 por cento não foi demonstrada. O prompt visual foi ajustado, mas nenhum modelo multimodal real foi executado.
