# Versão 2.3.2 experimental — histórico e relatório simples

## Como executar com os dois shapes

1. Instale o ZIP 2.3.2 em **Complementos → Gerenciar e instalar complementos → Instalar a partir de ZIP**. Reinicie o QGIS se a versão anterior estava carregada.
2. Abra o módulo PRODES. Adicione ao projeto o limite do imóvel e a consolidada delimitada pelo técnico. Selecione essas camadas na aba **1 · Imóvel e PRODES** e informe sua identificação e a origem/evidências técnicas da consolidada.
3. O início histórico padrão é **1985**; ajuste se necessário. A pesquisa termina até dois anos depois de cada ano PRODES, sem ultrapassar o ano atual.
4. Clique em **Analisar tudo automaticamente: imóvel + consolidada**. A base padrão é **Amazônia florestal**, adequada à região do projeto atual. Para outro bioma, primeiro consulte e selecione sua base WFS. O botão verifica a base oficial e confirma essa origem; fonte local continua exigindo confirmação do usuário.
5. Na aba **2 · Evidências e avaliação**, o botão **Buscar histórico e analisar antes/depois automaticamente** também executa a pesquisa histórica. A opção **Comparar somente as 3 imagens escolhidas (avançado)** é limitada às imagens selecionadas e não busca o histórico.
6. Aguarde a consulta PRODES, recorte, busca/download das imagens, índices e mapas. Não é necessário importar manualmente imagens de cada ano.
7. Leia o resumo e cada conclusão. Na aba de revisão, marque **Concordo/Discordo** e deixe notas. Exporte o pacote para salvar o PDF, HTML autocontido, mapas PNG, GeoPackage e manifesto.

As imagens escolhidas também ficam disponíveis como camadas PRODES no projeto e nos arquivos do acervo. Imagens históricas adicionais são inseridas com visibilidade desativada para facilitar a organização. Cada cena pode ser reaberta sem novo download, desde que seus arquivos e área/SRC sejam os mesmos.

## O que muda no relatório

Primeiro aparece uma tabela com **ano registrado, resultado e próximo passo**. Depois, cada polígono recebe:

- Área interceptada e sobreposição com a consolidada técnica.
- Explicação do resultado e do tipo de revisão que pode ser investigado.
- Primeiro intervalo de perda espectral observado na série consultada, ou a data em que a alteração já era visível.
- Possível perturbação compatível com fogo, recuperação espectral e limitações.
- Linha do tempo, lacunas e mapas destacando o polígono, com imagens anteriores e posteriores.

Os mapas agora são incorporados ao PDF. O HTML contém as imagens e pode ser aberto sem depender da pasta de PNGs. Os metadados técnicos completos permanecem no manifesto, evitando dicionários e termos de programação no texto principal.

## Buscar a abertura ou revisar a data

Exemplo de lógica, não conclusão sobre um imóvel: se um PRODES de 2020 estiver sobre uma consolidada técnica, o sistema buscará o passado da mesma área. Uma queda observada entre imagens de 2004 e 2005 pode gerar um **intervalo candidato para investigar revisão**, acompanhado dos mapas. Se a primeira imagem disponível já mostrar pouca cobertura verde, o relatório dirá que esse padrão já era visível naquela data; não inventará o ano da abertura.

Se houver perda antiga e nova perda próxima do registro, o relatório pede revisão do histórico antes de propor transferência de data. Recuperação rápida de uma perturbação antiga compatível com fogo não é automaticamente atribuída à primeira abertura. Uma mudança posterior só recebe indicação temporal quando a observação anterior à perda é da data oficial de referência ou posterior; intervalos que atravessam essa data podem continuar inconclusivos.

NDVI/NDMI medem resposta espectral. Eles não identificam sozinhos floresta primária, pastagem, regeneração ou uso legal. O resultado exige conferir a imagem oficial, estrutura/textura, documentos e histórico de máscaras antes de solicitar correção.

## Investigar incêndios

O sistema adquire também SWIR2 e calcula NBR=(NIR−SWIR2)/(NIR+SWIR2). dNBR é a diferença entre a observação anterior e posterior. A regra exploratória usa dNBR ≥0,27 em 60% dos pixels comuns válidos; exige QA local, 9 pixels, 80% de cobertura e mesma plataforma/época sazonal. Não é um limiar oficial do INPE nem prova da causa ou autoria.

A recuperação é verificada nos mesmos pixels nas três datas. Retorno dos índices não comprova manutenção da estrutura florestal. Imagens anuais da época sazonal podem não captar queimadas transitórias; ausência de sinal não demonstra ausência de fogo. Não há consulta automática de focos, laudos ou autoria. Esses elementos independentes podem complementar a revisão do técnico.

## Resultados e limites

- **Passível de contestação (triagem):** foi encontrado um fundamento preliminar para conferir data/histórico ou sobreposição documental. Não significa que o pedido será aceito.
- **Sem indícios suficientes para contestação:** a análise não demonstrou divergência; não impede que novas evidências justifiquem revisão.
- **Evidências insuficientes:** não se conseguiu concluir. Faltas de imagem, QA, amostra, comparação entre plataformas ou indícios conflitantes aparecem na justificativa.

Na Amazônia florestal, o diagnóstico de 6,25 ha usa a área do **polígono original**, não a área menor recortada dentro do imóvel. Esse diagnóstico de uso do produto não comprova erro de mapeamento. Consolidada é uma classificação técnica fornecida, sem homologação automática. O art. 3º, IV, da Lei 12.651/2012 exige ocupação anterior a 22/07/2008 e os usos definidos em lei; o plugin não certifica regularidade ou dispensas de APP/RL.

A primeira pesquisa histórica pode demorar: são recortes de muitas datas, máscaras e uma banda adicional. O acervo reutiliza arquivos concluídos. Novas imagens exigem internet e disponibilidade do TerraBrasilis e Microsoft Planetary Computer. A janela sazonal é ±30 dias da referência, até três candidatas por data, com nuvens da cena abaixo de 20%. As lacunas não demonstram inexistência de imagens fora dessa janela. A série tem limite de oito milhões de pixels-data em memória; se excedido, reduza o período ou divida a área, preservando a resolução.

## Referências e validação

- [INPE — uso dos dados PRODES, 2026](https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf).
- [Lei 12.651/2012 compilada](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm).
- [USGS — NBR](https://www.usgs.gov/landsat-missions/landsat-normalized-burn-ratio).

101 testes passaram. Em QGIS 3.34.4, o fluxo inteiro foi verificado com fontes WFS/STAC simuladas, vetores reais e rasters sintéticos calibrados: dois shapes, fonte anual confirmada, histórico, índices, indicação temporal, revisão independente, mapas por polígono incorporados no PDF com dimensões superiores a 500 pixels, HTML e GeoPackage. A precisão temática não foi medida em casos independentes; aquisição nativa online continua a ser conferida no QGIS do usuário. É um motor de regras experimental, não IA treinada, metodologia homologada ou decisão oficial. QGIS 3.22–3.99 declarado; integração efetivamente testada em 3.34.4. GDAL Python e NumPy são necessários.

Na correção 2.3.2, também foi validado o botão da aba 2 com datas manuais incompatíveis: ele voltou a buscar o histórico, incluindo imagens anteriores a 2000 e posteriores ao registro de 2022. Fontes de rede foram simuladas para este teste; ele não mede precisão temática nem comprova disponibilidade online de todas as datas.

## Argumentação do sistema de análise — 2.3.2

O motor grava uma justificativa individual com o resultado da análise. Não é apenas uma alteração no modelo de PDF. Ela considera o recorte, a proporção consolidada, o período pesquisado, a amostra utilizável, as datas anteriores e posteriores, os intervalos de perda e os indicadores de perturbação. A análise separa o que favorece a investigação, os contrapontos e o que ainda precisa ser confirmado.

A conclusão ampliada aparece no relatório e no manifesto. A regra original permanece em `rule_reason`; a argumentação contém versão, fundamento e seções. A classificação, a área indicada e os limiares espectrais foram preservados. Alterar entradas descarta a argumentação antiga. A análise completa deve ser executada novamente para produzir os novos relatórios.

Validação desta edição: 111 testes coletados, 99 aprovados e 12 dependentes de QGIS/GDAL não executados neste ambiente. Os testes cobrem a persistência da argumentação no motor, aquisição histórica simulada, proporção da consolidada, amostra pequena, marco temporal, recuperação, escape HTML e conservação dos resultados. A geração nativa de PDF no QGIS não foi repetida nesta edição.
