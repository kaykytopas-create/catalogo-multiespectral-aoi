# Validação 3.2.0 experimental

150 testes automatizados passaram, sem testes pulados, no runtime QGIS 3.34.4 com GDAL e Qt em modo offscreen. Compilação dos módulos e validação do pacote também realizadas.

Integração nativa testou o botão Executar comando, sinais Qt, criação real de raster no projeto QGIS, aplicação de bandas, importação progressiva, destino somente acervo, limite de nuvens zero sem relaxamento, ano sem imagem elegível, coexistência de composições e substituição da assinatura repetida, feição selecionada e sinalização de NoData. O raster de teste tinha 25 por cento de NoData. Roteamento de ano/perfil/nuvens para a central PRODES foi verificado; a chamada de início da investigação foi simulada. A geração PDF existente foi exercitada na integração.

Catálogo e transporte da aquisição foram simulados. Não houve validação desta versão com downloads online reais, execução de modelos treinados, acurácia temática ou interpretação ambiental independente. A cobertura de testes não garante disponibilidade dos serviços nem correção de conclusões para imóveis reais. O relatório continua dependente de revisão profissional e evidência adequada.
