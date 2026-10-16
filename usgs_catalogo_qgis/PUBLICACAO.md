# Publicação — 3.5.0 experimental

Atualização preparada para envio; não foi publicada automaticamente.

## Arquivos

- O ZIP instalável contém apenas a pasta `usgs_catalogo_qgis/`, com `metadata.txt` e `__init__.py` diretamente dentro dela. Envie esse ZIP ao repositório de complementos QGIS.
- O ZIP de código-fonte contém essa pasta, README de entrada e licença. Extraia e atualize o repositório GitHub existente; não envie o ZIP de fontes como se fosse o instalador.
- Autoria: Kayky Pessoa de Araujo; contato: kaykytopas@gmail.com. Assistência de desenvolvimento: OpenAI Codex. Licença GPL-2.0-or-later.

## Notas sugeridas da versão

Nova aba de situação ambiental e fundiária, com consulta pública do CAR, embargos IBAMA/ICMBio, processos associados ao cadastro e metadados judiciais por número CNJ. Inclui glebas, assentamentos, SIGEF/SNCI e requerimentos do acervo ITERPA para o Pará. As consultas trabalham em paralelo com orçamento de cinco minutos e produzem relatório breve, evidências JSON/CSV e exportação PDF. Indisponibilidade e consulta parcial são identificadas. Não certifica domínio, regularidade ou ausência de todos os processos.

## Envio

1. Instale o ZIP 3.5 em uma instalação QGIS 3.x e confira uma propriedade da sua área de trabalho. A validação registrada foi feita no QGIS 3.34.4; outras instalações devem ser conferidas.
2. Atualize os arquivos no repositório `https://github.com/kaykytopas-create/catalogo-multiespectral-aoi` e crie uma versão/tag `v3.5.0`, se estiver usando releases do GitHub.
3. Entre em `https://plugins.qgis.org/`, abra a página do seu complemento e envie uma nova versão usando o ZIP instalável. Mantenha a indicação experimental nesta etapa.
4. Informe as mudanças e o alcance regional das fontes fundiárias. A publicação depende do envio e da revisão/aprovação do repositório QGIS; criar o ZIP não o torna disponível automaticamente.

## Verificação já preparada no pacote

Metadados completos, versão numérica 3.5.0, licença e créditos, links públicos existentes do projeto, guias de uso/validação e histórico de versões. O empacotador valida os campos e a interpolação de percentuais, evita caches/arquivos de usuário e testa a integridade do ZIP. A versão continua declarando QGIS 3.22–3.99; não foi declarada compatibilidade com QGIS 4.

Não inclua relatórios de clientes, projetos, recortes de satélite, recibos reais, chaves privadas ou bases locais no repositório público. O pacote gerado não contém esses arquivos. Consulte GUIA_3.5.md e VALIDACAO_3.5.md para comportamento e limitações verificadas.
