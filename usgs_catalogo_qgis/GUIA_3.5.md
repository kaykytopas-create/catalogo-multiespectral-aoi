# 3.5 experimental — situação ambiental e fundiária

A nova aba **Situação ambiental e fundiária** faz a consulta documental/espacial sem baixar imagens. A página de imagens, as composições de bandas, os comandos, o acervo offline e a investigação PRODES continuam na primeira aba.

## Uso

1. Instale o ZIP 3.5 em Complementos → Gerenciar e Instalar Complementos → Instalar a partir de ZIP. Reinicie o QGIS para recarregar os módulos Python.
2. Abra Raster → Catálogo Multiespectral e escolha a nova aba.
3. Selecione a camada poligonal do imóvel e a UF. Se a camada contiver vários imóveis, selecione somente as partes do imóvel e marque **Usar somente feições selecionadas**. O sistema não reúne propriedades distintas silenciosamente.
4. Informe o recibo federal do CAR, se o tiver. Isso reduz ambiguidades e permite consultar diretamente a SEMAS/LDI do Pará. Sem recibo, o SICAR é pesquisado pelo polígono; até cinco CARs candidatos podem ser consultados na LDI, identificados como candidatos, sem escolher automaticamente um titular ou cadastro exclusivo.
5. Se quiser consultar metadados judiciais, informe até vinte números CNJ completos, separados por ponto e vírgula. A numeração é validada e direcionada ao tribunal de origem. A chave pública do CNJ vem incluída; existe campo para substituí-la caso o CNJ a altere. Não é necessário inserir conta pessoal.
6. Clique **Consultar e gerar relatório · até 5 min**. As fontes são consultadas em paralelo. A tela exibe tempo decorrido e permite cancelar preservando as respostas concluídas.
7. O relatório aparece na própria aba e é salvo automaticamente em HTML, com evidências JSON e planilha CSV. Use **Exportar PDF breve** para gerar o PDF. **Pasta dos relatórios** permite mudar o destino.

## Consultas incluídas

| Tema | Base e alcance |
|---|---|
| CAR | SICAR/SFB, camada da UF selecionada: situação, condição de análise e data de atualização quando publicadas. |
| Embargos IBAMA | Pamgia, camada pública de embargos, cruzamento com o polígono real. Inclui números de termos, autos e processos disponibilizados no registro. |
| Embargos ICMBio | WFS oficial na INDE: registro, processo, descrição e interseção quando disponíveis. |
| Autos de infração ICMBio | Camada WFS oficial; caso o serviço falhe, o relatório registra a indisponibilidade. |
| Embargos e processos punitivos SEMAS/PA | Portal LDI, consulta pelo recibo CAR; não representa todos os processos do SIMLAM/SEI. |
| Processos judiciais | CNJ/DataJud, números informados pelo usuário e tribunal de origem. Informa classe, órgão e último movimento disponível. O vínculo do número com a propriedade é fornecido pelo usuário. |
| Glebas estaduais e federais | Acervo público ITERPA, recorte Pará: denominação, situação original na base e referências publicadas. |
| Assentamentos estaduais e federais | Acervo público ITERPA, recorte Pará: nome, código SIPRA quando disponível e identificação da interseção. |
| Parcelas SIGEF e SNCI | Camadas publicadas pelo ITERPA para o Pará: parcela, situação original, certificação e referências cadastrais. Não é consulta direta nacional ao INCRA/SIGEF. |
| Requerimentos fundiários | SICARF/ITERPA, recorte Pará: nome, processo/ano e situação publicada. Requerimento não equivale a título. |

Para os temas fundiários, o plugin consulta o serviço do ITERPA com o polígono real do imóvel e a relação espacial dos interiores (DE-9IM T********), que exclui apenas contato na borda. Recebe os atributos sem baixar os enormes polígonos de glebas/assentamentos. A fração de área fundiária não é calculada nessa modalidade. Embargos e CAR usam interseção local das geometrias, com área elipsoidal quando poligonais; um registro pontual não produz área fictícia.

## O que o relatório significa

- **Registros encontrados:** há dados que atendem ao vínculo espacial ou cadastral informado. A vigência e o alcance jurídico do ato devem ser conferidos no órgão.
- **Sem registro no recorte consultado:** a fonte respondeu e a consulta desse recorte terminou. Não é certidão negativa geral.
- **Parcial/indisponível/prazo atingido:** existem pendências. Nunca são transformadas em ausência de embargo, de processo ou de assentamento.
- **Fora da cobertura:** o tema fundiário/LDI integrado cobre o Pará, não os outros estados. Nesses estados a conclusão fundiária fica pendente.
- **Outros processos públicos:** permanece explicitamente pendente. Não existe, nesta integração, descoberta de todos os processos por polígono, proprietário, CPF/CNPJ, CAR ou nome da fazenda.

Um CAR ativo não equivale à análise aprovada. Uma parcela certificada SIGEF/SNCI não comprova domínio. Uma gleba ou assentamento sobreposto não determina, isoladamente, a situação jurídica individual do imóvel. O relatório orienta conferir matrícula atualizada, cadeia dominial e instrumentos fundiários cabíveis; não emite uma decisão de regularidade.

## Tempo e dados

O orçamento máximo da consulta é de cinco minutos: até 295 segundos para requisições/processamento, reservando tempo para a gravação do resumo. Requisições individuais têm limite de 25 segundos e 8 MB. Falhas temporárias/timeout podem ser repetidas uma única vez, com pausa curta, somente se ainda houver orçamento global; respostas 400/403 não são repetidas. Há até oito páginas de 250 registros por camada, até quatro consultas simultâneas (no máximo duas ao mesmo tempo no ITERPA), até cinco CARs na LDI e até vinte números judiciais. Se faltar tempo ou volume, o relatório identifica a consulta parcial. A gravação em disco e a exportação PDF podem acrescentar tempo; não é promessa de conclusão integral em todos os servidores.

Novas consultas requerem internet. Resultados anteriores continuam disponíveis nos arquivos salvos; não são reapresentados como consulta online atualizada. São registrados horários, parâmetros, fontes, resumo dos atributos públicos e identificadores de integridade das respostas. A chave CNJ não é incluída no relatório nem persistida pelo complemento. CPF e nome de autuados não são usados como filtro nem publicados nas evidências resumidas. Não há envio para serviços de IA nesta aba.

Fontes oficiais: SICAR/SFB; IBAMA/Pamgia; ICMBio/INDE; SEMAS/LDI; Acervo Fundiário ITERPA; Conselho Nacional de Justiça — Base Nacional de Dados do Poder Judiciário (DataJud). As páginas de cada fonte são acessíveis no relatório. O uso dos dados deve observar as condições publicadas pelos órgãos. O complemento é independente dessas instituições.
