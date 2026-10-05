# Catálogo Multiespectral por Área de Interesse

QGIS plugin by **Kayky Pessoa de Araujo**, developed with assistance from **OpenAI Codex**.

Search anonymous Landsat Collection 2 Level-2 and Sentinel-2 Level-2A scenes by a parcel polygon, preview imagery with the parcel boundary, select RGB bands, calculate NDVI and maintain a local offline archive. Scene cloud cover is filtered strictly below 20%. No USGS account is required.

## Recursos

- Consulta de imagens históricas por imóvel e período.
- Prévia georreferenciada com contorno do imóvel e recorte horizontal com entorno.
- Composições de cor natural e PRODES — INPE, com escolha manual de bandas.
- Composições distintas da mesma data e NDVI.
- Downloads de recortes em paralelo e reaproveitamento dos arquivos locais.
- Acervo offline e atualização incremental de cenas.

## Instalação e uso

Versão experimental 0.10.0 para QGIS 3.22–3.99, com GDAL Python e NumPy. O suporte ao QGIS 4 não é declarado. A execução/renderização em diferentes instalações ainda precisa ser validada.

Veja o [manual](usgs_catalogo_qgis/README.md) e o [guia de publicação](usgs_catalogo_qgis/PUBLICACAO.md). O código-fonte do complemento está na pasta `usgs_catalogo_qgis`. Para gerar o ZIP localmente, execute, a partir da raiz deste repositório:

```sh
python usgs_catalogo_qgis/tools/prepare_release.py --output Catalogo_Multiespectral_AOI_QGIS_v0.10.0.zip
```

Instale o ZIP no QGIS em **Complementos → Gerenciar e Instalar Complementos → Instalar a partir de ZIP**. Novas buscas e downloads requerem internet e disponibilidade do Microsoft Planetary Computer. Dados já baixados podem ser usados offline. A disponibilidade histórica e o detalhe dependem do satélite e da área.

## Desenvolvimento

```sh
python -m unittest discover -s usgs_catalogo_qgis/tests -v
```

Os testes de download simulam o GDAL; não substituem testes de execução no QGIS. Consulte [CONTRIBUTING](usgs_catalogo_qgis/CONTRIBUTING.md) e [CHANGELOG](usgs_catalogo_qgis/CHANGELOG.md).

## Contato e créditos

Contato do autor: kaykytopas@gmail.com.

Relate problemas em [Issues](https://github.com/kaykytopas-create/catalogo-multiespectral-aoi/issues).

Landsat: USGS/NASA. Sentinel-2: ESA/Copernicus. Catálogo e hospedagem: Microsoft Planetary Computer. INPE: referência para as composições espectrais do PRODES Amazônia. Este é um projeto independente.

## Licença

Copyright (C) 2026 Kayky Pessoa de Araujo. **GPL-2.0-or-later** — consulte [LICENSE](LICENSE) e [NOTICE](NOTICE). Nenhuma imagem de satélite ou área de cliente é incluída no código.

## Atualização 0.10.0

Menu de composições espectrais, infravermelho de vegetação, SWIR, NBR, validação integral dos blocos raster, reparo de cache e aviso Landsat 7 SLC-off. Veja o manual completo em usgs_catalogo_qgis/README.md.
