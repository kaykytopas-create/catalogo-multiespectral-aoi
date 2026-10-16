# Catálogo Multiespectral AOI 3.1 — dois modos e comandos de tarefa

Versão experimental. Instale o ZIP em Complementos → Gerenciar e instalar complementos → Instalar a partir de ZIP e reinicie o QGIS.

## 1. Catálogo: baixar imagens e escolher bandas

O botão principal abre novamente o catálogo. Escolha o limite, o período e a cena. As opções PRODES, cor natural, infravermelho vegetação, outras composições, bandas personalizadas, NDVI e NBR continuam disponíveis. Clique em Ver prévia no mapa e importar para conferir a imagem real com o contorno do imóvel antes de adicioná-la ao projeto. Miniaturas não são a imagem usada para classificar.

Por padrão, a suavização está desmarcada: a tela mostra os pixels originais. O download usa reamostragem por vizinho mais próximo, sem reduzir deliberadamente a resolução para ganhar velocidade. O RGB é um VRT multibanda que referencia as bandas baixadas, sem compressão JPEG ou reconstrução de detalhes. Não mova as bandas para fora do acervo, pois o VRT depende delas.

Cenas Landsat 7 SLC-off ficam inicialmente ocultas por terem lacunas do sensor. É possível desmarcar o filtro, mas as lacunas permanecem. Há também pixels sem dados nas bordas, recortes ou arquivos incompletos. Antes da importação, uma inspeção amostral verifica máscaras/NoData nas bandas dentro do imóvel e informa a fração com dados. Abaixo de 98% há aviso. Essa inspeção não certifica nitidez, ausência de nuvens ou precisão posicional; em áreas pequenas a amostra pode ser insuficiente. Confira o recorte que pretende classificar. Se os arquivos locais estiverem inválidos, a validação do acervo permite recuperação online; a opção de baixar novamente continua disponível.

Landsat Collection 2 Surface Reflectance tem resolução espacial de 30 m. Nenhum aumento de DPI ou zoom cria detalhes menores que o sensor. Para detalhe recente, o catálogo também oferece Sentinel-2, conforme as bandas e datas disponíveis. Histórico antigo continua sujeito ao sensor daquela época.

Fontes: [USGS — resolução da reflectância Landsat](https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-reflectance) e [USGS — lacunas Landsat 7](https://www.usgs.gov/landsat-missions/landsat-7).

## Comandos aceitos

Escreva no campo superior, clique em Interpretar comando, leia o plano e clique em Executar plano mostrado.

- `Buscar imagens cor natural de 1985 até 2008`
- `Baixar imagens cor natural de 1985 até 2008`
- `Baixar imagens PRODES de 2000 até 2008`
- `Baixar imagens infravermelho vegetação de 2015 até 2024`
- `Baixar NDVI de 2018 até 2024`
- `Baixar NBR de 2018 até 2024`
- `Baixar imagens cor natural de 2020 até 2022 todas as datas`
- `Baixar imagens cor natural de 2020 até 2022 offline`
- `Baixar imagens cor natural Sentinel de 2020 até 2022`
- `Analisar PRODES e gerar relatório aprofundado`
- `Analisar PRODES e gerar relatório rápido offline`

O interpretador é um conjunto restrito de comandos, não um chat de IA ou conexão com o Codex. Não executa código arbitrário. Comandos ambíguos, anos invertidos/futuros, 1885 e pedidos de classificação temática são recusados com orientação. Use 1985 se esse for o ano desejado; a interface nunca o substitui silenciosamente.

O padrão do download por comando é Landsat e uma cena por ano, escolhida pela menor nebulosidade da cena, estritamente abaixo de 20%, com as bandas da composição disponível. Não significa a melhor imagem para cada ponto do imóvel, nem comparabilidade sazonal de toda a sequência. A seleção PRODES por polígono usa outros critérios locais na investigação. Para várias datas, escreva todas as datas: seleciona uma cena por dia, até 200; a busca é limitada a 100 páginas, e exige período menor ao exceder esse limite. Anos sem cenas elegíveis são informados. Falhas individuais ficam no manifesto `lote_*.json` no acervo da área. Não há preenchimento nem substituição silenciosa por outra composição.

Baixar salva no acervo; não adiciona dezenas de camadas automaticamente. Ao concluir, selecione a cena, escolha a composição desejada, confira a prévia e importe. A primeira cena do lote fica com a composição do comando selecionada; ao mudar de cena, confira novamente as bandas. Os arquivos concluídos podem ser reutilizados após cancelamento ou em nova execução.

## 2. Investigação PRODES e relatório técnico

Abra pelo botão superior do catálogo ou Raster → Catálogo Multiespectral → Investigação PRODES. Configure o limite, consolidada e origem da delimitação. Use o fluxo explicado no [GUIA_3.0.md](GUIA_3.0.md). A composição das cartas investigativas permanece SWIR1/NIR/vermelho, independentemente da composição do catálogo.

O comando de investigação reaproveita o limite escolhido no catálogo e as demais entradas da central, define o perfil e inicia a consulta. Preencha e confira a consolidada, responsável, fonte e ano(s) antes de executá-lo. No modo offline do botão principal, é necessário cache PRODES correspondente ao limite/base; para fonte PRODES local, use o caminho da camada local e o botão de recorte na central.

O relatório acrescenta matriz dos pares comparáveis, método e alcance, explicações alternativas e síntese condicionada às evidências para o revisor adaptar. A argumentação não é fortalecida atribuindo certeza a dados insuficientes. Não há classificação automática de floresta primária, homologação de consolidada ou comprovação de causa de incêndio.

## Velocidade

Bandas e composições existentes são reutilizadas. O lote baixa somente a composição solicitada e máscaras de qualidade disponíveis, em vez de todas as bandas de todas as cenas. O NBR da investigação passa a ser preparado apenas depois de uma candidata ser escolhida, poupando aquisição/cálculo para candidatas descartadas. A aquisição de bandas já usa paralelismo controlado; cenas são processadas em sequência para não saturar memória e corromper o índice do acervo. Rápido reduz o orçamento investigativo; Aprofundado o amplia. Não há promessa de um tempo fixo: internet, servidor, tamanho da área e disponibilidade das cenas continuam determinantes.

O comando de download prepara imagens; não realiza K-means, classificação supervisionada ou relatório de classes. Uma classificação temática exige ferramenta e validação específicas. O relatório automático disponível é o de investigação PRODES.
