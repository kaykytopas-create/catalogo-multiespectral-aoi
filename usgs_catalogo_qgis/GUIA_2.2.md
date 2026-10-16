# 2.2.0 experimental — evidências e triagem automáticas

## Instalação

No QGIS 3.22–3.99, use **Complementos → Gerenciar e instalar complementos → Instalar a partir de ZIP**. Se a versão anterior estiver carregada, feche e reabra o QGIS após a atualização. O pacote depende de GDAL Python e NumPy, normalmente presentes no QGIS. Integração verificada em QGIS 3.34.4; QGIS 4 não está validado.

## Fluxo na etapa 1

1. Abra o módulo PRODES do plugin. Adicione ao projeto o limite do imóvel e, se disponível, a camada consolidada produzida pelo técnico.
2. Na aba **1 · Imóvel e PRODES**, selecione o imóvel, a consolidada e informe a origem/evidências técnicas. A caixa de classificação técnica significa que você fornece essa classificação, não que o plugin a homologou. `id_tema=consolidada` reconhece esse papel automaticamente.
3. Consulte o WFS TerraBrasilis ou selecione uma camada local de incrementos anuais por bioma. Confirme a fonte anual. Escolha todos os anos ou filtre um ano.
4. Mantenha **Buscar imagens, analisar e gerar relatório automaticamente** marcado e clique em **Recortar no imóvel e executar análise**.
5. Aguarde. O plugin consulta Landsat sem conta, obtém as bandas PRODES e máscaras de qualidade, analisa e abre o relatório com mapas. Não é necessário baixar nem selecionar os rasters manualmente.
6. Revise cada polígono: **Concordo/Discordo** e notas não alteram os resultados calculados. Use **Exportar** para salvar PDF, HTML, mapas PNG, evidências vetoriais e manifesto.

A aba 2 mantém a análise manual disponível: desmarque a busca automática na etapa 1, prepare os recortes e selecione três imagens locais do catálogo. Uma aquisição incompleta deve ser refeita ou complementada manualmente.

## Imagens e qualidade

Para cada ano/data de referência PRODES, o sistema procura imagens do ano do registro e dos dois anos anteriores. Usa o mês/dia de `image_date` quando válido; a ausência desse dado adota explicitamente 31 de julho. Procura ±30 dias, dentro de cada ano, até cinco páginas do catálogo e três candidatas por data. Isso é um limite operacional; não demonstra ausência de outras imagens úteis fora da janela.

Coleção automática: Landsat Collection 2 Level-2 do catálogo Microsoft Planetary Computer, com acesso anônimo e nuvens de cena estritamente abaixo de 20%. A comparação prioriza a mesma plataforma nas três datas. A preferência de candidata considera proximidade de data, nuvens de cena e, depois de baixar o recorte, qualidade QA e cobertura válida no imóvel. A avaliação por polígono aplica filtros adicionais e pode permanecer inconclusiva.

A imagem selecionada não é necessariamente a mesma interpretada originalmente pelo INPE. Cenas e datas constam no relatório e manifesto para conferência. O RGB PRODES é SWIR1/NIR/vermelho: Landsat 4/5/7 = 5/4/3; Landsat 8/9 = 6/5/4. O contraste melhora a visualização, preservando dados e resolução nativa de aproximadamente 30 m. Sem inventar pixels, preencher falhas ou transformar resolução visual em evidência adicional.

Os arquivos permanecem no acervo configurado pelo catálogo, na mesma identidade de área/SRC. Downloads concluídos são reutilizados. Uma consulta online indisponível permite recorrer às cenas já indexadas. Novas imagens e bandas ausentes exigem internet; a primeira análise pode demorar. Este fluxo baixa evidências selecionadas, não todo o histórico global.

## Consolidada e conclusão

A união da camada consolidada é recortada no imóvel e cruzada com cada polígono PRODES; feições repetidas não duplicam a área. Quando há sobreposição técnica, o sistema procura também uma referência de 2007 na época sazonal equivalente, se a sequência já não contiver uma data anterior a 22/07/2008. Ausência de imagem ou amostra insuficiente aparece explicitamente no relatório.

A classificação fornecida pelo técnico entra como insumo documental. Ela pode gerar uma indicação preliminar de contestação apenas na sobreposição, sujeita à conferência de imagens, documentos e registro. NDVI/NDMI são regras experimentais próprias: pouca cobertura verde não prova uso antrópico; vegetação verde não exclui pastagem ou pousio. A conclusão pode ser:

- **Passível de contestação (triagem):** indício temporal ou classificação técnica sobreposta que exige confirmação e revisão do registro.
- **Sem indícios suficientes para contestação:** evidência avaliada compatível com a perda registrada, sem fundamento adicional detectado.
- **Evidências insuficientes:** sequência incompleta, qualidade insuficiente, respostas ambíguas ou elementos conflitantes.

Não se conclui que o PRODES é falso, que a supressão foi autorizada ou que o imóvel está juridicamente regular. Consolidação não dispensa automaticamente obrigações de APP ou Reserva Legal. PRODES registra supressão e não decide legalidade.

## Referências e validação

- [Lei 12.651/2012 compilada — especialmente art. 3º, IV](https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12651.htm): marco de 22/07/2008 e usos definidos na lei.
- [INPE — Uso de dados PRODES para avaliar conformidade ambiental, 2026](https://data.inpe.br/wp-content/uploads/sites/3/2026/03/Uso-de-dados-Prodes-para-avaliar-conformidade-ambiental.pdf): confronto temporal, fonte e natureza dos registros, sem determinação de legalidade. Usar incremento anual por bioma; resíduos/reclassificações não bastam para datar uma ocorrência.

85 testes passaram. Em QGIS 3.34.4, foram verificados vetores reais fornecidos, união, recortes, thread de aquisição com cliente simulado, rasters sintéticos calibrados, QA, triagem, mapas no relatório, revisão independente e exportação PDF/PNG/GeoPackage. Consulta pública GET confirmou cenas de julho de 2022 na área. A rede do ambiente impediu a consulta nativa online; o download real ainda deve ser verificado no QGIS do usuário. Os limiares não são critérios oficiais INPE nem um modelo treinado. A precisão temática precisa de validação com casos independentes antes de uso como conclusão técnica de laudo.
