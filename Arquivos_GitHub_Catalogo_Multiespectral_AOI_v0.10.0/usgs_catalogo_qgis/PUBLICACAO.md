# Preparação para publicar no QGIS

## Estado da versão 0.10.0

O pacote instala localmente e contém a licença, os créditos, o ícone PNG, descrição curta em inglês, instruções, código-fonte e uma geometria sintética para testar. Está marcado como **experimental**.

**Metadados configurados:** contato `kaykytopas@gmail.com`; repositório `https://github.com/kaykytopas-create/catalogo-multiespectral-aoi`; apresentação no README do repositório; suporte em `/issues`. É necessário colocar o código-fonte nesse repositório e confirmar que os links estão públicos antes do envio. Os testes de execução/renderização dentro do QGIS e de downloads reais também permanecem pendentes. Esta versão não foi enviada ao QGIS nem a um repositório externo.

## 1. Criar o repositório público

Sugestão de nome: `catalogo-multiespectral-aoi`.

No GitHub, GitLab ou equivalente, crie um repositório público na sua conta. Coloque a pasta `usgs_catalogo_qgis` descompactada, incluindo LICENSE, NOTICE, README, testes e ferramentas. Use o README como apresentação do projeto; pode acrescentar um README na raiz apontando para ele. O conteúdo deve coincidir com o ZIP submetido. Não coloque os ZIPs de versões, pastas de acervo, arquivos de clientes ou credenciais no código público. Habilite o rastreador de problemas (Issues).

## 2. Preencher os metadados e gerar o ZIP

O e-mail será um contato do autor e ficará visível nos metadados instalados. Use um contato que possa divulgar. Para um repositório GitHub, a ferramenta calcula a página de apresentação e o link de Issues a partir do endereço real fornecido.

Execute no terminal Python do seu ambiente de desenvolvimento, a partir da pasta que contém `usgs_catalogo_qgis` (não no console de comandos Python do QGIS):

```sh
python usgs_catalogo_qgis/tools/prepare_release.py --check
```

Com os metadados atuais, o comando deve concluir a validação local. Se forem removidos links obrigatórios, ele lista as pendências e retorna código 1. Para configurar e empacotar, substitua as duas expressões entre aspas pelos seus dados verdadeiros:

```sh
python usgs_catalogo_qgis/tools/prepare_release.py --configure --email "SEU_EMAIL_REAL" --repository "URL_REAL_DO_REPOSITORIO_GITHUB" --output Catalogo_Multiespectral_AOI_QGIS_v0.10.0.zip
```

Para outro provedor, acrescente `--homepage` e `--tracker` com os links verdadeiros. A ferramenta não entra em contas, não envia mensagens e não publica arquivos. Ela valida campos e estrutura, mas não verifica se as URLs existem ou se são públicas: abra os links sem estar logado para conferir. Atualize os metadados no repositório depois de configurá-los; a versão do código público deve corresponder à do ZIP.

## 3. Conferir no QGIS antes de enviar

Use um perfil limpo do QGIS 3 com GDAL Python e NumPy. Registre as versões de QGIS, GDAL e sistema operacional efetivamente testadas. O pacote não declara suporte ao QGIS 4. O intervalo 3.22–3.99 é uma compatibilidade declarada, não uma certificação de testes em todas as versões.

1. Instale pelo gerenciador de complementos e confira ativação, desativação e reabertura sem erros.
2. Abra `examples/imovel_sintetico.geojson`, uma geometria fictícia em EPSG:4326, e selecione-a no plugin. Faça também um teste em uma área de sua escolha em SIRGAS 2000 / UTM.
3. Pesquise Landsat em período anterior a 2005 e recente; pesquise Sentinel-2 em período recente. Confirme datas, filtro estritamente menor que 20% e tratamento de cenas sem dados.
4. Abra a prévia e confira recorte horizontal, limite do imóvel, zoom, deslocamento e suavização ativada/desativada.
5. Importe cor natural e PRODES da mesma cena: confira duas composições distintas, uma camada por composição e três bandas internas.
6. Confira NDVI, NoData e bandas NIR/vermelha. Para comparação numérica, aplique os mesmos fatores de escala, offset e máscara na ferramenta de referência.
7. Reinicie o QGIS e teste a cena baixada sem internet. Faça atualização incremental, cancelamento e retomada; confira o reaproveitamento das bandas.
8. Confirme que o pacote não cria telemetria ou envia o polígono completo: a consulta STAC transmite a caixa geográfica e os filtros à Microsoft; pedidos raster usam URLs de acesso temporário. Não registre nem publique tokens SAS.
9. Registre também eventuais limitações de proxy: consultas STAC e SAS usam a rede nativa do QGIS; leituras raster usam GDAL, cuja integração com proxies configurados apenas no QGIS ainda precisa ser conferida.

Não retire `experimental=True` antes de validar a execução real. Capturas de tela para a apresentação devem usar a área sintética ou dados que você possa divulgar.

## 4. Enviar para revisão

Entre com sua conta em https://plugins.qgis.org/ e use **Upload a plugin** para enviar o ZIP final, configurado e testado. Não precisa incluir conta USGS no plugin. A conta do publicador no QGIS é separada do acesso anônimo às imagens.

O envio passa por validações do repositório e processo de aprovação; gerar o ZIP localmente não garante aprovação. Consulte:

- Requisitos: https://plugins.qgis.org/docs/publish
- Aprovação: https://plugins.qgis.org/docs/approval
- Metadados e estrutura: https://docs.qgis.org/3.44/en/docs/pyqgis_developer_cookbook/plugins/plugins.html

## Autor e licença

Autor: **Kayky Pessoa de Araujo**. Colaboração no desenvolvimento: **OpenAI Codex**. Fontes de imagens: **USGS/NASA** e **ESA/Copernicus**. Catálogo/hospedagem: **Microsoft Planetary Computer**. INPE é referência para as composições espectrais; o plugin é independente e não tem aprovação institucional implícita.

GPL-2.0-or-later permite distribuir e modificar o software nos termos da licença, preservando os avisos aplicáveis. A licença do código não substitui os termos dos serviços e imagens externos. Veja LICENSE e NOTICE.
