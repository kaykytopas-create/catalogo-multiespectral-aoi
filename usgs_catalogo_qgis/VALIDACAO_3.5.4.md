# Validação 3.5.4 — 11/11/2026

- 205 testes automatizados aprovados no Python do QGIS 3.44.7, após corrigir a abertura de arquivo temporário no teste de relatório para Windows.
- Renderizador PyQGIS real testado com GeoTIFF Float32 sintético: escala fixa −1/+1, valores 0,8/0,86/1 em verde, cores esperadas e persistência da simbologia em QML.
- Hash SHA-256 e valores do GeoTIFF idênticos antes/depois da aplicação da simbologia; NoData preservado.
- Prévia, importação manual e importação por comandos usam CatalogDialog.configure_ndvi. Produto do acervo recebe a escala quando reaberto pelo plugin. Projetos antigos preservam seus estilos salvos.
- Alteração visual; não revalida a acurácia temática das análises ambientais. Não foram realizados downloads novos nesta atualização.
- Faixa declarada QGIS 3.22–3.99 mantida. Verificação desta atualização no QGIS 3.44.7.
