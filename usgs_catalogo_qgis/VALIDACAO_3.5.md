# Validação 3.5 experimental — 16 de outubro de 2026

## Automatizada e interface

203 testes passaram, sem testes pulados, em QGIS 3.34.4, GDAL 3.8.4 e Qt 5.15.13, com interface offscreen. São os 177 testes anteriores e 26 novos testes do módulo ambiental/fundiário. Incluem:

- Validação de recibo CAR, UF e dígitos verificadores CNJ; seleção de imóvel único ou feições selecionadas.
- Interseção geométrica real: buraco do polígono e contato apenas na borda não viram sobreposição. Área elipsoidal e registros pontuais sem área inventada.
- Identificação de vários CARs candidatos sem escolher um cadastro exclusivo; campos públicos resumidos sem CPF/nome de autuado.
- WFS com paginação, eixo explícito longitude/latitude, página repetida e CRS nulo em resposta vazia (caso encontrado durante integração e corrigido).
- Correspondência de camadas/campos fundiários ITERPA; consulta espacial de interiores pelo serviço, sem baixar as grandes geometrias; cobertura fora do Pará identificada.
- LDI negativa e positiva, processos punitivos, alerta oculto não interpretado como embargo, página alterada e recibo divergente.
- DataJud por número exato, tribunal, resultado divergente e registro com indicação de sigilo excluído. Chave não persistida no relatório.
- Erros HTTP, XML/HTML inesperado, geometria ausente e fonte sem resposta não viram consulta negativa.
- Transporte Qt nativo com timeout, cancelamento e aborto da resposta, rejeição de redirecionamento e de resposta grande; POST restrito a consultas de leitura autorizadas.
- Repetição única apenas de falha temporária e sob orçamento; espera por vaga no servidor fundiário também é interrompida pelo prazo global.
- HTML escapado, proteção contra fórmulas no CSV, gravação atômica e evidências em JSON.

A interface principal foi aberta e fechada no QGIS, com duas abas e os controles de imagens preservados. A nova aba também executou consultas em QThread, recebeu resultados na interface e salvou os arquivos. PDF A4 exportado e inspecionado visualmente: o exemplo breve passou a ter três páginas, com quadro de resultados, situação fundiária, registros, fontes e pendências legíveis.

## Integração online real

Confirmados durante a implementação, com requisições públicas reais:

- SICAR/SFB: situação e condição do CAR, com a geometria pública do cadastro.
- IBAMA/Pamgia: consulta espacial à camada oficial e resposta sem registro para o recorte de teste.
- ICMBio: capabilities/schema, consulta de embargos e resposta espacial vazia válida; o tratamento de CRS nulo foi corrigido e verificado.
- SEMAS/LDI: identificação do recibo consultado, resposta explícita de ausência de embargo e seção de processos punitivos para o exemplo público.
- CNJ/DataJud: metadados do número de exemplo publicado na documentação oficial, sem associação automática com a propriedade de teste.
- ITERPA: metadados das sete camadas e consultas reais com polígono; respostas com assentamento federal, denominação da gleba federal e parcelas SIGEF/SNCI no recorte. A relação DE-9IM de interiores é suportada pelo serviço e foi utilizada.

Durante a integração, duas execuções pela interface finalizaram em aproximadamente 28 e 47 segundos. Esses números não constituem SLA: o ITERPA oscilou e chegou a ultrapassar o timeout nas consultas seguintes. Isso foi exposto como fonte indisponível/inconclusiva, sem transformar a falta de resposta em inexistência de assentamento/gleba. A política final limita o servidor fundiário a duas requisições simultâneas e repete uma vez falhas temporárias, se houver tempo global.

A camada de autos de infração do ICMBio respondeu HTTP 400 em diferentes consultas, inclusive sem filtro espacial. O módulo registra a indisponibilidade e mantém o link oficial; não apresenta consulta negativa. Essa indisponibilidade externa não foi resolvida pelo complemento.

Não houve validação jurídica de um imóvel, conferência de matrículas ou análise da completude de todos os processos públicos. Não foi testado acesso a processos sigilosos ou a documentos restritos, nem existe mecanismo para contornar bloqueios. Fora do Pará, as fontes fundiárias integradas ficam explicitamente fora da cobertura. O recebimento de respostas hoje não garante que as bases estejam atualizadas hoje.

## Publicação

Metadados versão 3.5.0, autoria/licença/contato, guias, créditos das fontes e instruções de publicação atualizados. Compilação Python, metadados com leitor QGIS/ConfigParser e estrutura/integridade do ZIP verificados. Sem projetos, relatórios de clientes, imagens baixadas ou bases locais no pacote. Preparado como experimental; não enviado nem aprovado no repositório público nesta etapa.
