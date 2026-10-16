> Atualização: a versão 2.1.0 acrescenta análise automática. Consulte [GUIA_2.1.md](GUIA_2.1.md). O restante deste documento descreve o modo assistido 2.0, ainda disponível.

# Versão 2.0.2 experimental — guia de uso

Esta atualização inclui um módulo novo funcionando ao lado do catálogo de imagens. A análise é **assistida**: o usuário interpreta as imagens e o sistema aplica regras conservadoras, calcula interseções e organiza as evidências. Não existe nesta versão um classificador automático de falsos PRODES.

## Instalar

QGIS 3.22–3.99: Complementos → Gerenciar e instalar complementos → Instalar a partir de ZIP. Escolha o ZIP inteiro, sem descompactar. Reinicie o QGIS se uma versão anterior estava carregada. O nome e a pasta do plugin foram mantidos para atualizar o complemento existente. O acervo anterior continua utilizável.

Abra Raster → Catálogo Multiespectral → Análise PRODES por imóvel — 2.0 experimental. Também há um botão no catálogo de imagens.

## Preparar o imóvel e os incrementos

1. Adicione uma camada poligonal com SRC correto e selecione uma única feição do imóvel. Se a camada contém somente um imóvel, ele é usado automaticamente quando não há seleção. Partes do mesmo imóvel devem ser dissolvidas explicitamente.
2. Informe nome, CAR e responsável pela revisão. A opção de tolerância de 60 m é específica para limite CAR; para outros limites, deixe desativada.
3. Consulte as camadas TerraBrasilis e selecione os incrementos anuais do **bioma correto**. A lista agora exclui mapas acumulados e referências auxiliares. Para Amazônia, use `prodes-amazon-nb:yearly_deforestation_biome`. Confirme a origem nos metadados.
4. Baixe os polígonos. “Mostrar todos os anos encontrados no imóvel” vem marcado. Para analisar um ano específico, desmarque e escolha o ano PRODES. A consulta WFS não exige conta. Respostas incompletas, repetidas ou inválidas são recusadas. Quando o serviço estiver indisponível, adicione o arquivo oficial local ao QGIS, atualize a lista e use “Usar camada PRODES local / offline”.
5. Clique em “Recortar no imóvel e preparar análise”. São usados apenas registros cujo class_name/classname é dAAAA, para todos os anos da base consultada ou apenas o ano escolhido. O painel informa os anos que intersectam o imóvel e suas contagens. Resíduos rAAAA não entram nessa avaliação. UUID ausente gera resultado inconclusivo.

A interseção usa a geometria real do imóvel e preserva os atributos originais. O sistema calcula áreas geodésicas em hectares e mostra a área do polígono completo separadamente da parcela dentro do imóvel. Falhas de geometria interrompem a preparação; correções automáticas realizadas são registradas.

O diagnóstico opcional de borda usa núcleo interno com recuo de 60 m, projetado em UTM local. Se não existir núcleo interno, exige revisão manual. Uma interseção somente na borda não significa que o PRODES seja falso.

## Quando o recorte fica vazio

O diagnóstico informa a fonte usada, o número de feições recebidas, candidatas na caixa do imóvel, anos com interseção, classes não reconhecidas e coordenadas longitude/latitude. Envie esse diagnóstico e o limite do imóvel para reproduzir o problema. Trocar a fonte exige novo download ou nova seleção local; mudar o limite depois do download exige nova consulta. Camadas vazias não são adicionadas ao projeto.

A base anual pode começar em 2008: registros anteriores podem constar de um produto acumulado. Esses produtos não são incrementos anuais e não entram na avaliação desta versão. Resultado vazio não comprova ausência de desmatamento.

## Correção de coleções geométricas (2.0.2)

Alguns polígonos oficiais inválidos retornam uma coleção com polígonos e linhas após `makeValid`. O plugin agora preserva as superfícies poligonais, elimina os remanescentes sem área e valida o resultado. Não aplica buffer em linhas nem cria área artificial. Correções são registradas por polígono no relatório e no manifesto; a geometria de origem não é sobrescrita. Se não restar superfície válida, a operação continua bloqueada e o aviso identifica a etapa e o UUID.

## Comparar imagens

1. Use o catálogo de imagens para importar três composições **PRODES SWIR1/NIR/vermelho**: uma do ano analisado e duas dos anos anteriores. Faça um conjunto por ano PRODES.
2. No módulo PRODES, atualize as camadas. Atualizar a lista elimina a preparação anterior; refaça o recorte para manter a análise coerente.
3. Selecione as imagens na aba de evidências. Datas de imagens importadas pelo catálogo são preenchidas automaticamente. A análise rejeita datas alteradas em conflito com seus metadados e rejeita reutilização da mesma cena quando identificável.
4. Nos rasters RGB produzidos pelo plugin, os índices são **R=1, G=2, B=3**. São posições no raster composto, não números das bandas do satélite. Em arquivos multibandas externos, indique os índices correspondentes a SWIR1, NIR e vermelho. Confira a composição antes de interpretar.
5. Abra a comparação. O seletor alterna as três imagens no mesmo enquadramento, com imóvel azul, polígonos completos laranja e recortes vermelhos.

| Satélite | Composição SWIR1/NIR/vermelho |
|---|---|
| Landsat 4/5/7 | 5–4–3 |
| Landsat 8/9 | 6–5–4 |
| Sentinel-2 | 11–8–4 |

O plugin não verifica automaticamente nuvem/sombra, resolução ou alinhamento dentro do polígono nesta versão. Essa conferência é obrigatória para marcar uma revisão como concluída. O filtro global inferior a 20 por cento do catálogo permanece disponível, mas não garante ausência de nuvens localmente. Não usar regeneração recente como evidência isolada contra um desmatamento histórico.

## Avaliar e exportar

Para cada polígono, declare se a imagem mostra vegetação nativa, supressão observável ou observação insuficiente. Marque Revisão somente após conferir as três datas, bandas, sazonalidade, nuvens, sombras, lacunas e registro espacial. Acrescente justificativa nas notas.

O botão “Avaliar evidências declaradas” produz compatibilidade preliminar, indícios de divergência temporal/temática ou resultado inconclusivo. A sequência atual suprimida e anteriores nativas é compatível; supressão declarada em anos anteriores aponta divergência temporal; nativa nas três datas aponta possível divergência temática. Não há determinação autônoma da verdade nem probabilidade de acerto calculada. Os resultados se referem ao recorte analisado.

“Adicionar recortes como camadas temporárias” leva imóvel, polígonos completos e recortes para o projeto QGIS. Para conservar os vetores, exporte o pacote.

Na aba Relatório, exporte para uma pasta. Será criada uma subpasta nova contendo:

- relatorio.pdf e relatorio.html;
- até três mapas PNG com enquadramento comparável, indicação de norte, escala, data, SRC e bandas;
- evidencias.gpkg com imóvel, polígonos originais correspondentes e recortes;
- manifesto.json com resultados, regras, contexto e hashes dos arquivos.

Os rasters ficam no acervo/projeto e **não são copiados** para esse pacote. Para processamento offline posterior, conserve o acervo e os arquivos externos. O HTML usa mapas com caminhos relativos. Uma falha na exportação é informada como pacote incompleto; não utilizar arquivos parciais como relatório final.

## Teste com geometria fictícia

Adicione examples/imovel_sintetico.geojson e examples/prodes_sintetico.geojson ao projeto, selecione o imóvel e use a fonte PRODES local com ano 2022. O exemplo serve somente para testar a interseção; não é dado INPE e não deve fundamentar um relatório real. Sem imagens e revisão, a avaliação permanece inconclusiva.

## Metodologia e validação

Referência: INPE (2026), *O uso dos dados do PRODES para avaliar a conformidade ambiental de propriedades rurais*: https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf

O procedimento do plugin é uma adaptação de apoio à revisão visual, com regras próprias explicitadas no código e relatório. Não é homologado pelo INPE. Uma eventual revisão oficial deve ser solicitada no Canal de Atendimento BiomasBR; o plugin não envia solicitações.

Nesta preparação, 54 testes passaram com PyQGIS 3.34.4 real, incluindo coleções geométricas aninhadas, partes multipartes, superfícies preservadas e recusa de linhas sem área. A consulta oficial do imóvel fornecido retornou 14 candidatas; o fluxo real do diálogo criou seis recortes válidos (2008: 1; 2012: 1; 2019: 1; 2022: 3), e o filtro 2022 exibiu três. O limite original é válido e não foi alterado. A emissão de PDF também foi verificada com Qt real. Ainda falta validar o fluxo completo de imagens, mapas e exportação em diferentes instalações QGIS/GDAL. Esta é uma versão experimental para teste, não uma versão estável validada.

Próximas entregas: máscaras de qualidade por pixel, métricas espectrotemporais calibradas, estatísticas de validação com casos independentes e empacotamento portátil das imagens. Essas funções não estão anunciadas como implementadas neste ZIP.
