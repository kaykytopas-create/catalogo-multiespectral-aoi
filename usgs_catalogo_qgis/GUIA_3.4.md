# Versão 3.4 experimental — acervo público INPE

O catálogo busca Landsat USGS Collection 2 Level-2 em duas plataformas: Microsoft Planetary Computer e INPE/Brazil Data Cube. A nova fonte usa a coleção de cenas `landsat-2`, com arquivos públicos, sem chave de API ou conta. Sentinel-2 continua na fonte anterior. Não utiliza LandViewer, imagens comerciais, cubos temporais ou mosaicos como se fossem cenas de uma data.

## Como usar

1. Instale o ZIP 3.4 pelo gerenciador de complementos do QGIS e reinicie o QGIS para recarregar os módulos Python.
2. Abra Raster → Catálogo Multiespectral, selecione a camada de limite e escolha o período.
3. Mantenha Landsat marcado. A busca online consulta automaticamente as duas fontes; a identificação da cena mostra sua origem. Use mais resultados para continuar a paginação.
4. Escolha uma cena, a composição e a prévia georreferenciada com o limite. As miniaturas servem somente à seleção; a importação utiliza as bandas GeoTIFF, nunca o JPEG.
5. Também pode executar: `Baixar uma imagem por ano de 2000 a 2008 em cor natural com até 10% de nuvens e importar no QGIS`. Os critérios permanecem iguais; não são relaxados para preencher um ano.
6. Para guardar sem importar, use o destino acervo offline no comando. A análise PRODES também consulta a nova fonte automaticamente quando a aquisição online estiver habilitada.

## O que mudou

- Cenas do mesmo produto Collection 2 e mesmo identificador são unificadas; os endereços alternativos de cada banda são preservados.
- Se a abertura ou validação de uma banda falhar, o sistema tenta o outro endereço conhecido desse mesmo produto. Não substitui silenciosamente a data ou o sensor. A seleção anual continua tentando outras cenas daquele ano quando a qualidade local não atende ao critério.
- Origem das cenas e servidor efetivo por banda ficam nos metadados do acervo e nos registros dos lotes. As propriedades das camadas e os metadados espectrais preservam as fontes.
- Indisponibilidade de uma fonte é informada. Uma busca parcial não é apresentada como cobertura completa.
- O INPE atualmente rejeita a extensão STAC `query` nesse endpoint. O plugin percorre suas páginas e aplica localmente o limite estrito de menos de 20% de nuvens; o critério adicional do comando continua preservado, inclusive zero.

## Qualidade e cobertura

Mantidas escala e offset oficiais da reflectância Landsat, bandas por sensor, contraste comum da cor natural, recorte com entorno e inspeção QA no imóvel. A nova hospedagem não aumenta a resolução física (30 m nas bandas multiespectrais Landsat), não reconstrói pixels perdidos nem assegura uma cena utilizável em cada ano. Buracos reais, nuvens e SLC-off continuam sendo problemas do produto; não são preenchidos com informação inventada.

O acervo INPE pode ter as mesmas aquisições da fonte anterior, disponibilizadas por outro servidor. Produtos com identificadores diferentes não são tratados como cópias intercambiáveis. O arquivo local de cada imóvel continua separado por área e sistema de coordenadas. Uso offline exige baixar os recortes primeiro.

Fontes oficiais: https://data.inpe.br/dados/landsat/ e https://data.inpe.br/bdc/stac/v1/collections . Este complemento é independente do INPE e do USGS.
