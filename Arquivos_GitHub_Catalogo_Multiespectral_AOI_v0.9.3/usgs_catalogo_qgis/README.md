# Catálogo Multiespectral por Área de Interesse — QGIS 0.9.3

**English summary:** Search anonymous Landsat Collection 2 Level-2 and Sentinel-2 Level-2A scenes by a parcel polygon, filter scene cloud cover below 20%, preview imagery with the parcel boundary, select RGB bands, calculate NDVI and maintain a local offline archive. No account is required. QGIS 3.22–3.99, GDAL Python and NumPy are required. New downloads need internet. Experimental release; see [publication preparation](PUBLICACAO.md).

Pesquisa imagens Landsat USGS Collection 2 Level-2 e Sentinel-2 Level-2A sem conta. Usa o STAC público do Microsoft Planetary Computer, recorta o imóvel com entorno, permite escolher bandas RGB e calcular NDVI. Agora inclui prévia georreferenciada e acervo permanente para uso offline.

## Instalação

No QGIS 3.22 a 3.99: **Complementos → Gerenciar e Instalar Complementos → Instalar a partir de ZIP**. Abra pelo menu **Raster → Catálogo Multiespectral**. O pacote não declara compatibilidade com QGIS 4.

## Conferir a imagem antes de importar

1. Adicione o limite do imóvel como camada poligonal com SRC definido e selecione essa camada no plugin.
2. Escolha Landsat, Sentinel-2 ou ambos e um ano ou período. **Todo o histórico (1982–hoje)** consulta o arquivo histórico disponível para a área.
3. Clique em **Buscar imagens com nuvens < 20%**. As miniaturas são da cena inteira; não use essas miniaturas para verificar alinhamento.
4. Selecione a cena e as bandas R/G/B. **PRODES — INPE** usa SWIR1–NIR–vermelho, na ordem R/G/B (Landsat 4/5/7: 5–4–3; Landsat 8/9: 6–5–4; Sentinel-2: 11–8–4). O botão mostra a combinação correspondente ao satélite da cena selecionada. A seleção manual de bandas continua disponível. **Cor natural** usa vermelho–verde–azul.
5. Clique em **Ver prévia no mapa e importar RGB**. O plugin prepara os recortes locais e abre uma janela ampla com os pixels georreferenciados e o **limite real do imóvel em azul**, sem preenchimento.
6. Use a roda do mouse para zoom, arraste para mover e use **Enquadrar área** para voltar. É possível ocultar o limite. Em **Comparar com**, escolha outra camada raster do projeto e reduza a opacidade da cena para comparar alinhamento. No modo offline, essa lista oferece apenas arquivos raster locais.
7. Clique em **Importar esta composição** para adicionar uma camada ao projeto, ou **Voltar para escolher outra cena**. Voltar não descarta as bandas baixadas; a próxima abertura as reutiliza.

A prévia usa o SRC do raster e transforma o limite do imóvel para esse SRC. Ela permite inspeção visual, mas não detecta nem corrige automaticamente deslocamentos. As bandas preservam os valores dos recortes; o contraste RGB é apenas visual, com corte de 2% a 98%. As cores variam conforme a cena e seu contraste.

A composição principal segue as bandas documentadas na [nota técnica do INPE para o PRODES Amazônia](https://www.terrabrasilis.dpi.inpe.br/download/terrabrasilis/technicalnotes/nota_tecnica_nao_floresta.pdf). O preset anterior já usava essas bandas; esta versão explicita o nome e a combinação de cada sensor. O preset não reproduz toda a metodologia de classificação do PRODES nem garante cores idênticas às de outra cena.

## Recorte mais largo e qualidade visual

O entorno tem largura mínima de quatro vezes a largura da caixa do imóvel e altura de 2,4 vezes. Para imóveis estreitos e compridos, a largura aumenta até uma proporção aproximada de pelo menos 1,6:1 em distância no terreno. O imóvel continua centralizado e inteiro; o raster passa a ter formato horizontal. A janela da prévia também ficou mais larga, respeitando o espaço da tela.

**Suavizar pixels na visualização RGB** vem ativado: usa interpolação cúbica ao aproximar e bilinear ao afastar. O efeito acompanha a camada RGB importada e melhora a aparência no mapa; desmarque para inspecionar os pixels sem suavização. Isso não cria detalhes novos, não altera os arquivos das bandas e não muda o cálculo do NDVI. O contorno do imóvel continua georreferenciado.

As composições usam a melhor resolução de grade entre as bandas selecionadas, evitando uma grade de resolução média quando as bandas têm resoluções diferentes. Bandas mais grossas continuam com seu limite de detalhe original. Os GeoTIFFs locais são recortes das bandas, e não imagens JPEG de prévia.

Para obter o **novo recorte horizontal**, baixe a composição ou atualize a área novamente com internet. O cache é separado pelo perfil de recorte para não reutilizar uma imagem estreita como se fosse a nova. Os arquivos anteriores ficam preservados. Em modo offline, se ainda não existir catálogo do novo recorte, o plugin abre o acervo anterior e informa que o enquadramento largo exige atualização. Se já existir um catálogo novo, as cenas dele são usadas e as bandas ausentes precisam ser baixadas com internet.

## Melhorias de velocidade

- Até três bandas são recortadas em paralelo, com datasets e configurações GDAL separados por tarefa. Em versões do GDAL sem configuração por thread, o download continua sequencial.
- Bandas locais, composições VRT e limites de contraste já calculados são reutilizados. O contraste é recalculado se os arquivos do recorte mudarem.
- O corte visual de 2% a 98% usa uma amostra de 65.536 pixels, reduzindo o trabalho para abrir a prévia. Isso não reduz a resolução nem altera os valores das bandas; pode mudar ligeiramente o contraste exibido.
- Requisições HTTP usam leitura de intervalos e multiplexação quando suportadas. As tarefas compartilham o token de acesso anônimo, evitando pedidos repetidos.
- A remoção de cenas repetidas na busca usa um índice por identificador.

O ganho depende da conexão, do servidor, do tamanho da área e da versão do GDAL. Não foi medido em uma instalação real do QGIS neste ambiente.

## Acervo offline e atualização de novas cenas

1. Escolha uma pasta em **Acervo permanente → Escolher pasta**. Por padrão, usa `Catalogo_Multiespectral_Acervo` na pasta Documentos. A escolha fica salva nas configurações do QGIS.
2. Com internet, escolha a área, os satélites e o período. Para baixar o arquivo histórico completo da área, escolha **Todo o histórico (1982–hoje)**.
3. Clique em **Baixar / atualizar todas as cenas do período**. A rotina percorre todas as páginas do catálogo e salva os recortes de todas as bandas espectrais de cada cena elegível, para permitir mudar composições e calcular NDVI depois, sem rede. Não adiciona automaticamente todas essas cenas ao projeto.
4. O painel mostra **Completo**, **Parcial** ou **Não baixado**. Cenas só pesquisadas podem constar no catálogo sem bandas baixadas. Para uma cena individual, basta abrir sua prévia: só as bandas da composição escolhida são baixadas.
5. Depois, marque **Modo offline — usar apenas o acervo local** e clique em **Buscar no acervo local**. Use a mesma área, SRC e pasta, selecionando o período que deseja consultar. Prévia, RGB e NDVI usam os arquivos já baixados. Bandas ausentes geram um aviso; o modo offline não faz download automaticamente.
6. Para novas imagens, desmarque offline, selecione novamente o período a atualizar e clique em **Baixar / atualizar todas as cenas do período**. A rotina consulta o catálogo novamente, incorpora novas cenas e tenta completar bandas que falharam. Arquivos completos são reutilizados, sem baixar tudo outra vez. Para incluir datas recentes, o período deve chegar até hoje.

**O acervo é da área selecionada e de seu entorno, não de todo o planeta nem de cenas inteiras.** Continua valendo o filtro de nuvens **estritamente menor que 20%** no metadado da cena inteira. Isso não garante ausência de nuvens dentro do imóvel. Cenas sem o metadado ficam fora da busca. A primeira sincronização pode demorar e ocupar bastante espaço, especialmente com décadas de imagens; é possível trabalhar por ano e cancelar a tarefa.

Downloads interrompidos não contam como completos. Os arquivos concluídos permanecem, e uma nova atualização pode retomar as bandas faltantes. A pasta externa de acervo não é apagada ao atualizar ou reinstalar o plugin. Não mova ou exclua essa pasta se um projeto do QGIS depender dela; faça cópia de segurança quando necessário. Imóveis com caixa envolvente ou SRC diferentes recebem acervos separados para evitar reutilizar um recorte errado.

As miniaturas online que foram vistas também são guardadas quando possível. Uma cena recém-sincronizada pode não ter miniatura, mas suas bandas completas permitem abrir a prévia georreferenciada offline. Referências XYZ/WMS não são oferecidas dentro da prévia offline; camadas online já presentes no projeto principal são gerenciadas pelo próprio QGIS.

## Composições da mesma data e NDVI

Falsa cor e cor natural da mesma data podem coexistir, cada uma como **uma camada RGB com três bandas internas**. Reimportar a mesma cena, área e combinação de bandas substitui apenas aquela composição. As bandas de apoio não viram camadas separadas no painel.

**Calcular NDVI da cena** usa NIR e vermelho: Landsat 4/5/7, bandas 4 e 3; Landsat 8/9, bandas 5 e 4; Sentinel-2, B08 e B04. O índice aplica `(NIR − vermelho) / (NIR + vermelho)` e é aberto em prévia com uma rampa de −1 a +1 antes da importação.

Para Landsat Collection 2, aplica escala 0,0000275 e deslocamento −0,2 antes do cálculo; para Sentinel-2, lê `raster:bands` quando disponível, com escala padrão 0,0001. Pixels sem dados ou índices fora do intervalo físico são tratados como NoData. O NDVI é salvo como GeoTIFF Float32 no acervo. Os recortes Landsat/Sentinel preservam os valores originais; as composições RGB usam VRT local. O NDVI complementa a interpretação e não classifica automaticamente desmatamento, nuvens ou sombras.

## Armazenamento e dependências

A imagem só é adicionada ao projeto após confirmação na prévia. Os dados são permanentes no acervo local e podem sustentar o projeto após reiniciar o QGIS. Para um arquivo independente, exporte a composição RGB em GeoTIFF. Remover uma camada do painel não remove as bandas do acervo.

Requer GDAL Python e NumPy, presentes nas instalações usuais do QGIS. A busca e os novos downloads dependem do Microsoft Planetary Computer e de internet. Landsat provém da USGS/NASA; Sentinel-2, ESA/Copernicus. A disponibilidade histórica depende da área e do catálogo.

## Validação desta versão

30 testes locais passaram, incluindo: persistência do catálogo, separação de áreas/SRC, filtro de nuvens/datas, paginação completa, atualização incremental, reaproveitamento entre composições, recusa de rede em modo offline, retomada de downloads com falha cálculo numérico de NDVI com NoData, bandas PRODES por sensor, recortes em três tarefas com configurações isoladas e compartilhamento do token entre tarefas, recorte horizontal para imóveis estreitos e compatibilidade offline com acervos anteriores e validação dos metadados/pacote de publicação e transporte de rede (HTTPS, redirecionamentos, erros e cancelamento). Os testes de recorte simulam o GDAL; este ambiente não tem QGIS/GDAL instalado. A aparência da janela, a sobreposição de geometrias e a importação de cenas reais ainda precisam ser conferidas no QGIS.

**Créditos:** Kayky Pessoa de Araujo (autor); OpenAI Codex (colaboração no desenvolvimento); USGS/NASA (Landsat); ESA/Copernicus (Sentinel-2); Microsoft Planetary Computer (catálogo, prévias e hospedagem).

## Licença e contribuição

Copyright (C) 2026 Kayky Pessoa de Araujo. Código e ícone distribuídos sob **GPL-2.0-or-later**: veja [LICENSE](LICENSE) e [NOTICE](NOTICE). A colaboração de OpenAI Codex e as fontes de dados estão creditadas; o plugin é independente das instituições mencionadas.

Esta versão prepara a publicação. O e-mail do autor e os links do projeto estão configurados. O código precisa ser colocado no repositório público e a execução real no QGIS conferida antes da submissão. Consulte [PUBLICACAO.md](PUBLICACAO.md), [CONTRIBUTING.md](CONTRIBUTING.md) e [CHANGELOG.md](CHANGELOG.md). O ZIP não contém dados de clientes, imagens baixadas ou credenciais.

Projeto público: https://github.com/kaykytopas-create/catalogo-multiespectral-aoi

Relatos de problemas: https://github.com/kaykytopas-create/catalogo-multiespectral-aoi/issues

## Segurança (desde a versão 0.9.2)

Consultas STAC e assinaturas temporárias usam QgsNetworkAccessManager, respeitando a configuração de rede do QGIS. Endereços externos ao serviço autorizado e redirecionamentos são recusados. Erros de cache são registrados sem incluir URLs assinadas. Bandit 1.9.4 e detect-secrets 1.5.0 foram executados no pacote completo, sem ocorrências. Essa verificação local não substitui a avaliação do repositório QGIS.

## Ajustes Qt6 da versão 0.9.3

As 22 ocorrências de enumerações e execução de diálogo apontadas pelo repositório foram corrigidas; QAction usa uma importação compatível com Qt5 e Qt6. As referências Qt foram conferidas com PyQt5 5.15.11 e PyQt6 6.11.0. Os testes de transporte usam objetos simulados com enumerações apenas no formato novo. O plugin continua declarado para QGIS 3.22–3.99; a interface e o processamento completo precisam de validação no QGIS antes de declarar suporte ao QGIS 4.
