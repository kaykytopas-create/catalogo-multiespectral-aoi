# Comandos executáveis — versão 3.2 experimental

Selecione a camada do limite do imóvel no catálogo. Se ela contiver vários imóveis, selecione exatamente uma feição. Escreva o pedido e clique em **Executar comando**, ou pressione Enter. **Ver plano (não executa)** serve para conferir; **Executar plano mostrado** inicia esse plano.

## Importar as imagens no projeto aberto

`Baixe e importe no QGIS uma imagem por ano de 2000 a 2008, cor natural, com 0% de nuvens.`

O sistema pesquisa o imóvel, escolhe a cena elegível com menor nebulosidade de cada ano, baixa as bandas e adiciona cada imagem concluída ao projeto. O download permanece no acervo. Cada composição gera um raster por cena; repetir a mesma cena/composição substitui sua camada correspondente. Cor natural e PRODES da mesma data podem coexistir.

## Salvar somente no acervo

`Baixe uma imagem por ano de 2000 a 2008, cor natural, com 0% de nuvens e salve no acervo offline.`

Esse destino permite pesquisar na internet e guardar os resultados sem adicionar camadas. Para usar apenas arquivos já existentes:

`Importe no QGIS imagens cor natural de 2000 a 2008 usando somente o acervo local, sem internet.`

Acervo offline significa destino de armazenamento. Sem internet ou somente acervo local significa fonte de pesquisa local.

## Critérios aceitos

- Dois anos para aquisição: de 1982 ao ano atual, sujeitos à disponibilidade do sensor. Uma imagem por ano é o padrão; escreva **todas as datas** para incluir as datas elegíveis.
- Composições: cor natural, PRODES, infravermelho vegetação, NDVI ou NBR. Se omitida, usa a composição selecionada no catálogo quando compatível.
- Landsat é o padrão; Sentinel pode ser solicitado explicitamente.
- Percentual explícito entre zero e vinte, como **0% de nuvens**, **até 5% de nuvens** ou **menos de 5% de nuvens**. O teto geral continua abaixo de vinte. Sem percentual, usa esse teto.
- O percentual é o metadado de nuvens da cena inteira. Zero no catálogo não garante ausência de nuvens em cada pixel do imóvel.

Não relaxa o filtro quando faltam resultados. Informa os anos sem cena elegível e as falhas parciais. Se o melhor candidato falhar no download, registra a falha; não promete uma imagem por ano em qualquer situação. Cancelar preserva arquivos e camadas já concluídos.

## Investigação PRODES

`Investigue o PRODES de 2020 do meu imóvel e gere relatório aprofundado com 0% de nuvens.`

Abre a central, usa o limite escolhido, configura o ano PRODES, o perfil e o filtro de nuvens e inicia o fluxo. Os demais insumos e parâmetros da central precisam estar válidos. Um único ano no comando filtra o registro PRODES; configure o período histórico de imagens na central. O filtro também vale para as buscas históricas e alternativas. Os relatórios e mapas existentes continuam disponíveis para revisão técnica.

## Qualidade e operação manual

A importação mantém a resolução do produto, sem suavização por padrão. A inspeção de NoData dentro do limite recusa amostras sem pixels válidos e sinaliza resultados incompletos ou inspeção inconclusiva com **conferir qualidade**. Essa amostragem não prova que toda a imagem está íntegra e não mede nuvens locais. Lacunas de origem não são preenchidas artificialmente.

O catálogo manual, prévia com limite, seleção de bandas, índices e importação por data continuam disponíveis. A execução é feita pelo plugin instalado no QGIS; esta conversa não controla o seu QGIS diretamente. O interpretador aceita tarefas e critérios definidos acima, não qualquer instrução livre como um modelo de linguagem.

## Instalação

No QGIS: Complementos > Gerenciar e instalar complementos > Instalar a partir de ZIP. Escolha o ZIP 3.2.0 e reinicie o QGIS para recarregar o código. Versão experimental; confira as mensagens e os mapas antes de usar em laudos.
