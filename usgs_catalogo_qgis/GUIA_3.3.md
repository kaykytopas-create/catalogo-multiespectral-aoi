# Qualidade e seleção anual — 3.3 experimental

Instale o novo ZIP pelo gerenciador de complementos e reinicie o QGIS. As camadas já abertas mantêm o estilo anterior; execute novamente o comando para importar com o novo processamento. Arquivos válidos do acervo são reaproveitados. Catálogo manual, bandas, prévia e relatório PRODES continuam disponíveis.

## O que mudou

Cor natural é montada com vermelho, verde e azul e apresentada com intervalo comum de reflectância de zero a 0,30, usando a calibração de cada produto. O contraste independente por canal não é aplicado a essa composição. Isso reduz a distorção cromática, mas não remove nuvens reais. Dados espectrais originais, bandas e resolução são preservados. Sem suavização por padrão e sem preenchimento de lacunas ou criação de pixels artificiais. Essa mudança também vale para importação manual de RGB natural.

Na execução por comandos, todas as candidatas que respeitam a taxa de nuvens da cena, sensor, período e opção de ocultar SLC-off permanecem disponíveis. Antes das bandas, o sistema baixa/reutiliza QA_PIXEL (Landsat) ou SCL (Sentinel), inspeciona o limite do imóvel e ordena por fração local de pixels limpos, cobertura e nuvens da cena. Baixa uma composição por grupo anual ou data. Se uma candidata falhar ou tiver bandas incompletas, tenta a próxima do mesmo grupo.

Exige pelo menos 99 por cento de cobertura válida na amostra do imóvel e 98 por cento de pixels limpos segundo QA. Também aplica o limite de nuvens solicitado à amostra local. Nuvens, sombra e neve não são consideradas limpas. A ausência de QA ou amostra válida impede a seleção automática dessa candidata. O catálogo manual permite a avaliação individual de cenas que não passaram na seleção automática. A inspeção é limitada a 1024 pixels por dimensão; é uma estimativa amostral, não uma certificação de ausência absoluta de nuvens, nitidez ou precisão geométrica. Nuvens não são apagadas das bandas.

## Comando de exemplo

`Baixe e importe no QGIS uma imagem por ano de 2000 a 2008, cor natural, com menos de 20% de nuvens.`

Além da taxa da cena, a seleção automática prioriza imagens limpas no imóvel. Se você exigir **0% de nuvens**, o filtro da cena inteira continua zero e a amostra local também deve indicar zero. Isso pode excluir anos inteiros; o plugin não muda o critério silenciosamente. Nenhum software consegue gerar uma cena histórica que não exista na fonte ou recuperar terreno coberto por nuvens sem outra observação.

Para salvar sem adicionar camadas, use **salve no acervo offline** e omita **importe no QGIS**. Consulte GUIA_3.2.md para os destinos e outros comandos. O interpretador continua limitado às tarefas implementadas; a seleção é baseada em medidas de qualidade, não em uma IA capaz de entender qualquer pedido.

## Resultado do lote

Informa imagens efetivamente preparadas/importadas, anos sem resultado, quantidade de rejeições e falhas. O manifesto no acervo registra as candidatas rejeitadas por QA e as tentativas de download. Um ano só conta como atendido depois de uma composição preparada; uma falha não conta como imagem entregue.

A avaliação de todas as máscaras adiciona uma etapa ao lote, que pode demorar em períodos longos. Apenas máscaras são adquiridas durante a classificação das candidatas; bandas completas são baixadas conforme a tentativa escolhida e o acervo evita trabalho repetido. É uma troca deliberada em favor de qualidade para vetorização.

## Argumentação PRODES para o responsável técnico

A estrutura foi adaptada do relatório fornecido como referência de linguagem e organização, sem incluir dados, mapas, nomes ou conclusões daquele cliente. O motor agora registra objeto, evidência, interpretação temporal, temática e espacial, encaminhamento por UUID e roteiro de síntese. Datas anteriores são pistas condicionadas à correspondência com o mesmo evento; sobreposição não transfere automaticamente o argumento ao polígono inteiro. Realocação espacial depende de evento comprovado no setor de destino. Regeneração, autorização ou consolidação declarada não bastam para excluir registros.

A análise preserva o resultado das regras e a área indicada. Pode orientar complementação de evidências, investigação da divergência ou manutenção provisória como referência de trabalho. Não é solicitação pronta nem modelo homologado pelo INPE. A estrutura de argumentação não torna o sistema um classificador automático de floresta primária ou pastagem. O assistente visual local já existente recebe a mesma orientação de comparar observações datadas e hipóteses concorrentes; depende de modelo multimodal instalado no Ollama, não incluído no ZIP e sem acurácia temática validada.

## Como medir a meta de 80 por cento

A meta ainda não é um resultado comprovado. Testes de software verificam execução; não medem acerto ambiental. O código inclui `tools/validate_accuracy.py` para avaliar um conjunto independente revisado. Prepare CSV com `uuid,reference,prediction`. Referência usa `revisar_data`, `contestar` ou `manter`; previsão também admite `inconclusivo`. O protocolo deve definir essas classes antes de avaliar. Uma pista ou recomendação condicionada não deve ser rotulada como decisão conclusiva; use inconclusivo quando faltar fundamento.

Escolha casos representativos, com diferentes anos, imóveis, sensores, qualidade e classes. Separe imóveis usados para ajuste dos usados para avaliação; faça a referência por técnicos sem acesso à previsão, idealmente com segundo revisor e resolução de divergências. Nenhum dado sintético fornecido com os testes vale como validação temática.

Execute no diretório do projeto: `python tools/validate_accuracy.py casos_revisados.csv --output avaliacao.json`. A ferramenta conta erros e inconclusivos, matriz de confusão, precisão e recuperação por classe, acurácia global, acurácia balanceada e limite inferior de Wilson de 95 por cento. Inconclusivos não contam como acerto global. Exige no mínimo 50 casos e 10 em cada classe para seu indicador de suporte, além da meta na acurácia balanceada e no limite inferior. Esses mínimos são controles do projeto, não requisito oficial nem garantia estatística de generalização: casos correlacionados, viés da referência e representatividade continuam exigindo avaliação.
