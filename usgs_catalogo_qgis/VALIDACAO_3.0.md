# Registro de validação — 3.0.0 experimental

Data: 06/10/2026. Este registro descreve testes de funcionamento, não uma validação de precisão temática ou jurídica.

## Verificações concluídas

- 125 testes automatizados passaram no ambiente com QGIS 3.34.4, GDAL e NumPy, sem testes ignorados. Incluem seleção local por polígono, integridade dos eventos, compatibilidade temporal, aquisição offline, estrutura das respostas visuais e regras anteriores.
- O fluxo completo foi executado no QGIS: camadas de entrada, investigação em segundo plano, leitura de rasters, índices, hipóteses, argumentação, cartas, PDF, HTML, GeoPackage e exportação automática.
- Essa integração usou dois polígonos PRODES simulados e 41 cenas sintéticas calibradas. Somente os transportes de consulta/aquisição foram substituídos por respostas de teste; os cálculos e a produção dos mapas e documentos usaram o QGIS/GDAL reais.
- Foram verificadas reutilização offline sem consulta STAC, conservação da data do cache PRODES, cancelamento entre cartas, revisão do usuário separada do parecer calculado e incorporação dos mapas no relatório. As cartas foram produzidas em A4 paisagem, 300 DPI.
- O transporte HTTP local do adaptador visual foi exercitado com servidor simulado no formato da API Ollama. A etapa visual na interface também usou resposta simulada. IDs, estrutura, limites e preservação do parecer calculado foram verificados.
- A compilação dos módulos Python passou. O empacotamento verifica os metadados, a integridade do ZIP e a ausência de caches de execução.

## O que estes testes não demonstram

Não foi executada inferência com um modelo multimodal real, não há pesos de modelo incluídos e não foi medido um índice de acerto. A investigação usa regras técnicas explícitas; a interpretação visual opcional depende de modelo instalado pelo usuário. Resposta bem formada não comprova interpretação correta.

Esta rodada não verificou aquisição ao vivo nas fontes públicas, homologação pelo INPE ou precisão em uma amostra independente de imóveis. Disponibilidade dos serviços, compatibilidade com outras versões do QGIS e conclusões ambientais precisam de verificação adicional em condições reais.

## Protocolo recomendado para validação temática

Separar casos independentes com abertura antiga, alteração recente, incêndio com recuperação, nuvens, pixels ausentes e amostras pequenas. Comparar as datas e hipóteses produzidas com interpretação de técnicos, imagens oficiais e documentos de referência. Registrar divergências, resultados inconclusivos e tempos de execução, sem ajustar as regras aos mesmos casos usados para medir desempenho. Revisar os fundamentos normativos antes de utilizar uma conclusão em procedimento administrativo.

Os dados de teste e relatórios sintéticos não são incluídos no pacote público.
