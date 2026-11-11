# 3.3.0 — experimental

- Cor natural manual e por comandos com intervalo físico comum R/G/B, preservando DN e resolução.
- QA local no imóvel antes da seleção de bandas: cobertura, nuvens, sombra e neve.
- Mantém candidatas alternativas e tenta outras datas do mesmo ano em caso de falha ou lacunas.
- Anos atendidos contam somente imagens preparadas; tentativas e rejeições no manifesto.
- Preserva percentual pedido, destino do comando e interface de investigação PRODES.
- Argumentação por UUID com objeto, observações, interpretação temporal/temática/espacial, encaminhamento e síntese para o técnico; prompt visual alinhado à mesma estrutura.
- Avaliador offline de acurácia para casos independentemente revisados, sem promessa de 80 por cento de acerto.
- 167 testes e integração nativa com transporte simulado; sem validação online ou temática.

# 3.2.0 — experimental

- Botão Executar comando e Enter iniciam interpretação e execução; Ver plano apenas confere.
- Destinos independentes: importação progressiva no QGIS ou somente acervo. Acervo offline não ativa automaticamente pesquisa sem internet.
- Percentual de nuvens explícito respeitado, inclusive zero; anos sem cena elegível e erros parciais informados.
- Importação na thread principal, composição preservada, inspeção NoData, coexistência de bandas distintas e substituição apenas da assinatura repetida.
- Limite da feição selecionada e proteção contra alteração do imóvel durante o lote.
- Comandos PRODES configuram ano, perfil, nuvens e início do fluxo da central.
- 150 testes passaram e integração QGIS com aquisição simulada. Sem validação online ou temática nesta versão.

# 3.1.0 — experimental

- Entrada principal restaurada para catálogo e prévia; investigação PRODES disponível no mesmo plugin.
- Comandos de tarefa em português com plano explícito, validação de anos e composição, busca paginada e download por ano ou por data, manifesto e falhas individuais.
- Visualização sem suavização como padrão, cenas SLC-off ocultas inicialmente e inspeção amostral de pixels sem dados dentro do imóvel antes de importar.
- NBR adquirido apenas após seleção da candidata na investigação, reutilizando cache.
- Relatório técnico com matriz de pares, explicações concorrentes, alcance do método e síntese condicional para o revisor adaptar.

## 3.0.0 — Central de investigação ambiental experimental

- Entrada principal passa a coordenar a investigação; catálogo/bandas permanecem em ferramentas avançadas.
- Planejamento por polígono, QA local, escolha de candidatas e refinamento temporal limitado por perfil.
- Comparações compatíveis são preservadas após inserir outra época/sensor.
- Hipóteses, evidências, perguntas abertas e orientação oficial curada/versionada.
- Assistente multimodal local opcional, com referências/IDs validados e opiniões separadas do parecer.
- Cartas UTM com foco, entorno, localização, norte da grade, escala, fonte e contraste físico comparável.
- Produção de cartas em fila cancelável e exportação automática com reaproveitamento dos PNGs.
- Acervo offline, cache PRODES com data original, auditoria encadeada, manifesto e CSV de seleção.
- Snapshots de entrada descartam resultados antigos antes de uma nova análise.

## 2.3.2 — Argumentação por evidência

- Integra a argumentação ao motor de análise, à aquisição histórica e ao manifesto; amplia a justificativa individual sem alterar a classificação ou a área calculadas.
- Explica alcance da consolidada, amostra, datas úteis e lacunas, com critérios INPE e art. 3º, IV.
- Distingue indicação documental, investigação de data e perturbação por fogo.
- Expõe contrapontos e quais evidências são necessárias para um pedido verificável.

# 2.3.1 experimental

- Corrige o botão de análise para buscar o histórico anterior e posterior automaticamente.
- Separa a comparação manual de três imagens em uma opção avançada explícita.
- Informa quando a pesquisa histórica não foi executada e elimina resultados históricos antigos ao alterar entradas.
- Mantém a proporção dos mapas no PDF e evita reutilizar mapas de anos incompatíveis por polígono.

## 2.3.0 — Experimental

- Novo botão executa tudo a partir do imóvel e consolidada: consulta catálogo WFS oficial, obtém polígonos, confirma automaticamente a fonte anual verificada, recorta e adquire evidências. Base padrão: Amazônia florestal; escolha outra base para outro bioma.
- Série anual da época sazonal de referência, de 1985 por padrão (início ajustável) até Y+2, limitada ao ano atual. Pesquisa sem conta, filtro de nuvens abaixo de 20, calibração e QA locais; acervo e consultas repetidas reutilizados.
- Intervalos de alteração anterior/posterior para investigação de revisão de data. Primeira observação já alterada não recebe ano de abertura inventado. Lacunas ficam explícitas; não se reatribui automaticamente uma nova perda à primeira queda espectral.
- NBR/dNBR exploratórios com banda SWIR2 e recuperação nos mesmos pixels. Não inferir causa/autoria, estrutura florestal ou falso PRODES pelo fogo ou regeneração. Perturbação antiga com recuperação rápida não é automaticamente tratada como data de primeira abertura.
- Relatório simples: resultado, motivo, próximo passo, linha do tempo, mapas por polígono e limitações. Sem dicionários Python ou QDate na apresentação.
- Corrigidos mapas ausentes no PDF: recursos incorporados explicitamente. HTML autocontido com PNG embutido; mapas destacam o polígono analisado. Todas as cenas escolhidas ficam disponíveis no QGIS/acervo.
- Escopo de indicação zero quando inconclusivo; diagnóstico Amazônia florestal de mínimo de 6,25 ha usa área ORIGINAL, não o recorte do imóvel.
- 98 testes passaram. Fluxo completo QGIS 3.34.4, com cliente WFS/STAC simulado, vetores reais e imagens sintéticas: busca histórica, índices, revisão, mapas >500 pixels incorporados no PDF, HTML e GeoPackage. Aquisição nativa online e precisão temática continuam pendentes de validação independente.

## 2.2.0 — Experimental

- Etapa 1 executa recorte, busca anônima Landsat, aquisição no acervo, análise, mapas e relatório sem selecionar imagens manualmente.
- Cada data de referência/ano PRODES gera a própria sequência Y, Y−1 e Y−2. Janela sazonal de ±30 dias; fallback explícito em 31 de julho se a data da fonte estiver ausente. Preferência por plataforma comum; rejeição de comparação espectral entre sensores diferentes.
- Filtro estrito de nuvens de cena abaixo de 20; até três candidatas por data, priorizando cobertura local válida com máscaras QA. Pixels sem dados permanecem sem dados.
- União dos polígonos consolidados evita duplicação de área. Campo id_tema=consolidada identifica o papel técnico declarado; não certifica datas, uso ou regularidade jurídica.
- Sobreposição técnica, referência pré-marco 2007 quando aplicável, justificativa de contestabilidade preliminar e limites por polígono. NDVI/NDMI não comprovam por si sós uso antrópico ou consolidação legal.
- Mapas RGB SWIR1/NIR/vermelho no relatório, revisão Concordo/Discordo independente e exportação PDF/PNG/GeoPackage/manifesto.
- 85 testes e fluxo completo em QGIS 3.34.4 com vetores reais e rasters sintéticos. Precisão temática não validada com casos independentes. Consulta nativa online impedida pela rede do ambiente de teste; validar aquisição real no QGIS do usuário.

# Changelog

## 2.1.0 — 2026-10-06 — experimental

- Automatic per-polygon raw-pixel screening with calibrated NDVI/NDMI, common-pixel comparison and numerical evidence in the report.
- Fixed Sentinel processing-baseline offsets before spectral indices; calibration now participates in derived-index cache identity.
- Best-effort QA_PIXEL, QA_RADSAT and Sentinel SCL downloads stored locally, without adding visible raster layers.
- Conservative guards for local coverage, tiny slivers, missing QA, mixed sensors and seasonal/date incompatibility; no interpolation across missing pixels.
- Separate reviewer agreement/disagreement and notes preserve automatic calculations in HTML/PDF and the manifest.
- Verified INPE technical guidance and conditional references to Law 12.651/2012; no automated legality or native-cover verdict.
- Real QGIS 3.34.4 worker, cloud masking, parcel clipping, independent review, three PNG maps, PDF, GeoPackage and manifest export verified with synthetic rasters.
- 69 automated tests passed including real GDAL pixel processing. Rules remain unvalidated against independent reference cases; experimental status retained.

## 2.0.2 — 2026-10-06 — experimental

- Fixed PRODES preparation aborting when GEOS repairs an invalid polygon into a geometry collection containing polygon and collapsed line components.
- Preserve existing polygon components, validate them and refuse empty/nonpolygonal results without buffering lines into artificial area.
- Identify the processing stage, class, UUID and feature ID in geometry errors.
- Record geometry repairs per result in the report/manifest.
- Reproduced the reported failure using the supplied parcel and the official annual biome WFS: 14 envelope candidates, six positive-area overlaps across 2008, 2012, 2019 and 2022. The parcel itself is valid.
- 54 tests passed with real PyQGIS 3.34.4; the actual dialog prepared six valid parcel clips, three with the 2022 filter. Full imagery and export integration remains pending.

## 2.0.1 — 2026-10-06 — experimental

- Default to all annual increment years, listing years that intersect the parcel.
- Offer annual biome sources only; exclude reference, accumulated, legal-Amazon and small-increment products from discovery.
- Clear the active source when changing source selection and refuse WFS data fetched for a different parcel.
- Normalise class whitespace/case before year selection; remove provider-specific year filtering.
- Accept the only parcel automatically when its layer has one feature.
- Diagnose empty results with source, counts, years, classes and geographic bounds; refuse empty layer additions and empty assessments.
- 48 unit tests and Qt5 UI/PDF smoke passed. A real official WFS query returned three annual records (2010, 2012, 2015) for a known control area. Full QGIS geometry/rendering and the user parcel remain unverified.

## 2.0.0 — 2026-10-06 — experimental

- Added a dedicated PRODES parcel analysis module, available from the raster menu and imagery dialog.
- Added TerraBrasilis WFS capabilities discovery and paginated CRS84 feature queries, refusing repeated and incomplete responses.
- Added a local vector source option for offline use, a single-feature parcel snapshot and exact intersection retaining official attributes/UUIDs.
- Added geodesic hectare areas and a separate optional CAR 60-m border diagnostic.
- Added three-date RGB comparison and conservative rules based on user-declared visual evidence; missing or unreviewed evidence remains inconclusive.
- Added temporary project layers, map PNGs with scale, PDF/HTML report, GeoPackage and hash manifest export.
- Preserved all 0.10 imagery presets, download integrity checks, NDVI/NBR and archive behavior.
- No automatic false-PRODES classifier, per-pixel cloud masking or new machine-learning model is implemented in this release.
- Local tests and Qt UI/PDF smoke checks passed; real QGIS/GDAL/WFS integration validation is still pending.


## 0.10.0 — 2026-10-05

- Added a spectral preset dropdown with vegetation infrared, vegetation analysis, SWIR, agriculture, land/water, natural color and the PRODES default.
- Added scaled NBR calculation and retained NDVI/manual RGB selection.
- Read all raster blocks before accepting downloads or unvalidated cache files; validation receipts avoid repeat scans of unchanged bands.
- Added HTTP retries, exact warp transformation, explicit output NoData and lossless compressed TIFF crops.
- Added a manual cache repair option; rebuilt RGB composites and indices when source bands change.
- Increased display contrast sampling to 262144 pixels and kept source resolution and optional display smoothing.
- Marked affected Landsat 7 SLC-off scenes and added an optional filter without synthesizing missing observations.
- 36 tests passed; Qt5/Qt6 controls checked with mocked PyQGIS. Full QGIS/GDAL runtime validation remains pending.

## 0.9.3 — 2026-10-01

- Fixed all 22 Qt6 compatibility findings in the submitted 0.9.2 package.
- Used scoped Qt and PyQGIS enums and QDialog.exec().
- Imported QAction from QtGui with a Qt5 fallback to QtWidgets.
- Checked Qt references with PyQt5 5.15.11 and PyQt6 6.11.0; 30 core tests passed.
- Compatibility remains declared for QGIS 3.22–3.99. QGIS runtime and full QGIS 4 validation are still pending.

## 0.9.2 — 2026-10-01

- Replaced urllib requests with native QGIS networking for STAC and temporary SAS signing.
- Restricted catalog requests to authorized HTTPS endpoints and refused redirects.
- Removed unused full-scene download code and reported cache errors instead of ignoring them.
- Replaced hardcoded credential-like test fixtures with ephemeral synthetic values.
- Added network validation and error-handling tests; 30 tests passed locally.
- Bandit 1.9.4 and detect-secrets 1.5.0 reported no findings.

## 0.9.1 — 2026-09-30

- Fixed literal percent sign in metadata that caused public QGIS upload parsing to fail.
- Added validation with ConfigParser BasicInterpolation and regression tests.
- Imagery retrieval and rendering are unchanged.

## 0.9.0 — 2026-09-30

- Prepared experimental publication metadata with an English description.
- Added GPL-2.0-or-later license, author notice and PNG icon.
- Added publication guide, release builder, contribution guide and synthetic test parcel.
- Configured author email and public GitHub project links supplied by the author. Source upload and runtime validation remain pending.
- No change to imagery retrieval, RGB processing, NDVI or archive format.

## 0.8.0

- Wider landscape crop and preview window.
- Optional RGB display smoothing and highest-resolution composite grid.
- Offline fallback to older local archives.

## 0.7.0

- INPE/PRODES spectral preset labels by sensor.
- Up to three independent band download workers.
- Cached contrast limits and VRT reuse.

## 0.6.0

- Georeferenced preview with parcel boundary.
- Incremental local imagery archive and offline mode.
