# Catálogo Multiespectral AOI 3.0 — Central de investigação ambiental

Esta versão experimental reorganiza o plugin em torno de uma investigação automatizada. A central coordena a consulta PRODES, seleção de imagens por polígono, comparação temporal, hipóteses, argumentação, cartas-imagem e pacote de revisão. O catálogo e as ferramentas de bandas continuam disponíveis no menu Raster para conferência manual.

## Executar a investigação

1. Instale o ZIP em **Complementos → Gerenciar e instalar complementos → Instalar a partir de ZIP**. Reinicie o QGIS.
2. Carregue o limite do imóvel e, quando disponível, a consolidada delimitada pelo técnico. Abra o plugin pela barra de ferramentas: a entrada principal agora é a central de investigação.
3. Selecione as camadas, identifique o imóvel, CAR e revisor. Informe a origem da consolidação e confirme a classificação técnica somente quando corresponder ao trabalho realizado.
4. Escolha o início histórico e o perfil. O padrão é **1985 / Equilibrado**. A base automática padrão é Amazônia florestal; para outro bioma, consulte e selecione a camada anual correta.
5. Clique em **Iniciar investigação: imóvel + consolidada → relatório**. Não precisa importar manualmente imagens de cada ano.
6. Acompanhe as mensagens de progresso. É possível cancelar aquisição/análise e interromper a fila de cartas entre mapas.
7. Ao concluir, o pacote é salvo automaticamente na pasta `relatorios` do acervo configurado, em uma subpasta nova. A mensagem informa o caminho; na aba Relatório, use **Abrir pasta do último pacote exportado**. Desmarque a exportação automática para revisar antes de escolher a pasta.
8. Examine as hipóteses e mapas, marque **Concordo/Discordo** por polígono e acrescente notas. Exporte novamente para incluir sua revisão. O parecer calculado e as evidências permanecem separados da sua opinião.

## O que o sistema investiga

- Planeja o período de cada polígono, até dois anos após o ano registrado, limitado ao ano atual.
- Avalia QA, cobertura e número de pixels **no polígono PRODES**, e não somente no imóvel inteiro.
- Ordena as candidatas pela adequação local e registra os motivos. Uma cena selecionada pode continuar insuficiente: serve de referência, não de prova.
- Quando a seleção inicial não é adequada, amplia a janela de busca, preservando os testes de compatibilidade sazonal e plataforma.
- Busca observações intermediárias em intervalos elegíveis, dentro de um orçamento explícito. Se não encontrar uma imagem melhor, conserva a lacuna.
- Examina perda antiga, evento próximo ao registro, alteração posterior, perturbação compatível com fogo e ocupação técnica pré-marco.
- Mantém comparações adequadas de época/plataforma quando uma observação adicional tem outra condição. Não faz comparação numérica livre entre sensores.
- Separa indicação documental de divergência temporal demonstrada. Uma consolidada pequena não fundamenta automaticamente todo o polígono.

| Perfil | Candidatas por seleção | Tentativas adicionais por polígono | Janela de recuperação |
|---|---:|---:|---:|
| Rápido | 3 | 1 | ±45 dias |
| Equilibrado | 5 | 3 | ±60 dias |
| Aprofundado | 8 | 6 | ±60 dias |

A janela inicial é ±30 dias. A recuperação não dispensa compatibilidade de época/sensor para comparar pixels. O número de tentativas não equivale a imagens efetivamente encontradas. O filtro de nuvens da cena permanece estritamente abaixo de 20%; a QA local controla a amostra válida.

## Interpretação visual com IA local

O sistema de investigação e os relatórios funcionam **sem IA generativa**. Para acrescentar interpretação visual:

1. Instale o [Ollama](https://docs.ollama.com/capabilities/vision) e disponibilize um modelo com capacidade de visão, adequado à capacidade do seu computador. O plugin não instala nem baixa modelos.
2. Com o serviço local em execução, clique em **Verificar modelos na IA local**. Escolha o nome do modelo multimodal instalado.
3. Marque **Interpretar cartas com IA visual local** e execute a investigação.
4. O plugin verifica a capacidade de visão e recusa modelos que anunciam encaminhamento remoto. Envia até quatro cartas reduzidas por polígono somente a `127.0.0.1:11434`, sem proxy ou redirecionamento externo. Prioriza pares de alteração/perturbação e cenas úteis próximas à referência.
5. Leia o complemento visual separado no relatório. As descrições são hipóteses não validadas, vinculadas aos IDs das cenas. O modelo não pode substituir a classificação ou a área calculadas.

O plugin valida a estrutura da resposta, IDs de cenas e referências, mas **não comprova a correção semântica das afirmações do modelo**. Se o serviço estiver indisponível, o modelo não tiver visão ou a resposta for inválida, isso aparece no resultado; a investigação espectral não é apresentada como interpretação visual executada. Hardware e modelo influenciam tempo e qualidade. Não há modelo treinado especialmente para PRODES neste pacote.

## Argumentação e base de orientação

O resultado contém explicação por polígono: questão investigada, alcance da sobreposição, qualidade/amostra, datas anteriores e posteriores, intervalo de mudança, possíveis perturbações, contrapontos e evidências necessárias para revisão. A justificativa original da regra permanece registrada.

A base de orientação é um conjunto de **resumos curados e versionados**, com links e localizadores dos documentos oficiais, consultados em 06/10/2026. Não é o texto completo da legislação nem um sistema de atualização jurídica automática:

- Lei 12.651/2012, art. 3º, IV: definição de área rural consolidada.
- INPE 2026: uso dos produtos PRODES, limites de avaliação, revisão e tolerância cartográfica.
- USGS: QA Landsat Collection 2 e NBR.

A correspondência com uma regra não é uma homologação jurídica. O plugin não avalia automaticamente APP, Reserva Legal, autorização, autoria de incêndio, multas, crédito rural ou obrigações de regularização. Índices e textura não comprovam sozinhos floresta primária ou primeira abertura.

## Cartas-imagem e entrega

As cartas focam o polígono com entorno e mostram um mapa de localização no imóvel, norte da grade, escala em metros, data, fonte, cena, SRC UTM e limites. A investigação usa composição SWIR1/NIR/vermelho e limites físicos de reflectância 0,02–0,45 em todas as datas, sem suavização. Isso evita comparar cores derivadas de contrastes independentes. Não é um classificador temático.

A saída padrão é 300 DPI. Aumentar DPI melhora a impressão, **não a resolução espacial do Landsat**. Não há preenchimento artificial de pixels ausentes nem reconstrução de evidências.

O pacote contém:

- `relatorio.pdf` e `relatorio.html` com imagens incorporadas;
- cartas PNG e `evidencias.gpkg` com vetores;
- `selecao_imagens.csv`, com candidatas, qualidade e motivos;
- `investigacao.json`, com hipóteses, evidências, referências e resultado visual quando solicitado;
- `events.jsonl` e `session.json`, com eventos encadeados por SHA-256 e estado;
- `manifesto.json`, com resultados, caminhos de origem e hashes dos arquivos.

A cadeia permite verificar consistência local e detectar alterações sem atualização dos hashes; não é assinatura digital ou prova de autenticidade do INPE. As imagens completas permanecem no acervo, fora do pacote. Os arquivos de investigação pertencem ao caso e não devem ser incluídos no ZIP público do plugin.

## Uso offline e persistência

Uma consulta online guarda a resposta PRODES para aquele limite e base. Com **Usar somente acervo local e PRODES em cache**, o sistema reutiliza esse cache, preserva a data da consulta anterior e procura somente cenas/arquivos locais. Se não houver cache PRODES, use uma camada local na etapa 1 ou realize uma consulta online primeiro. Dados ausentes continuam ausentes; não há download no modo offline. A IA local, se configurada, pode trabalhar sem servidor externo.

Os eventos e estado ficam em `investigacoes` dentro do acervo. Uma execução nova pode reutilizar cenas/bandas concluídas, mas não retoma automaticamente o mesmo estado intermediário de uma sessão cancelada. Os downloads dependem da disponibilidade das fontes públicas; não existe cópia local de todas as imagens do planeta.

## Recursos e limites

QGIS 3.22–3.99 declarado; GDAL e NumPy necessários. Integração efetivamente testada em QGIS 3.34.4. O limite de oito milhões de pixels-data por polígono permanece para proteger a memória. Grandes áreas/períodos precisam ser divididos, sem reduzir artificialmente a resolução. Não há precisão temática ou índice de acerto validado em casos independentes. Quanto menor o recorte, maior a possibilidade de amostra Landsat insuficiente.

Antes de usar uma conclusão em um pedido, conferir a imagem oficial, as datas, a geometria e o fundamento com responsável técnico. O motor organiza a investigação; não substitui essa revisão.
