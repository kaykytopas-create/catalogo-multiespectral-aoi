# Validação da versão 3.1.0 experimental

06/10/2026. Foram executados **141 testes automatizados**, todos aprovados, sem testes ignorados, no ambiente com QGIS 3.34.4, GDAL e NumPy.

A integração nativa verificou abertura do catálogo pelo botão principal, acesso à investigação, interpretação e execução de comandos em QThread, seleção da composição cor natural, lote com duas datas, registro do manifesto, roteamento de comando à central PRODES, inspeção de pixels sem dados dentro do imóvel, prévia/importação e geração de PDF do relatório técnico. A primeira página do PDF sintético foi renderizada e inspecionada visualmente.

A aquisição desse teste foi **simulada**. Os rasters, máscaras, cálculo de cobertura, interface e PDF usaram QGIS/GDAL reais. A cena sintética tinha 25% de pixels sem dados em uma das bandas; a inspeção identificou 75% de cobertura, mostrou o aviso e conservou os dados originais. Testes adicionais verificaram que lacunas fora do limite não entram no cálculo, amostras externas são insuficientes e a inspeção não modifica o arquivo. Outro teste verificou que NBR não é adquirido para a candidata descartada.

Esta rodada não mediu ganho de tempo em uma rede real, não verificou disponibilidade atual de cenas nas fontes públicas e não validou classificações em casos ambientais independentes. A melhora de velocidade decorre de menos cenas/bandas por tarefa e reutilização do acervo; não há promessa de tempo fixo. Não foi executado modelo multimodal real. Os comandos são um interpretador restrito e não estabelecem conexão com o Codex.

Consulte o registro [VALIDACAO_3.0.md](VALIDACAO_3.0.md) para o ensaio anterior do fluxo completo de investigação histórica e produção das cartas com aquisição sintética. Esses ensaios não constituem homologação temática ou jurídica.
