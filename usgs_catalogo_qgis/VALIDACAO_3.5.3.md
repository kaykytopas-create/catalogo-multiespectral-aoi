# Ajuste de interface 3.5.3

- O botão principal fica no rodapé fixo da aba de imagens, fora da área de rolagem.
- Área mínima do botão: 280 × 48 pixels lógicos, com texto, destaque azul, foco visível e atalho Alt+I.
- A prévia continua sendo aberta pelo mesmo fluxo de importação; o botão de confirmação também foi ampliado.
- Os filtros, a tabela e as bandas ficam em uma área com rolagem. A tabela preserva uma altura mínima de 160 pixels.
- A janela usa o espaço disponível da tela para definir o tamanho inicial.
- O botão continua desabilitado quando não há cena/bandas válidas ou há tarefa em execução.

Compilação Python, metadados e perfil Flake8 F,E711,E712,E713,E714,E721,E722,E731,E741,E742,E743,E9 verificados sem apontamentos. Este perfil não declara conformidade com todas as regras de formatação PEP 8.

Verificação na interface real do QGIS 3.34.4, com Qt em modo offscreen: janelas de 1180 × 850, 1024 × 700 e 900 × 600; botão inteiramente visível com a rolagem no início e no fim. Clique e Alt+I acionaram o manipulador existente de prévia/importação. O atalho é reaplicado ao trocar o texto da composição. A aba ambiental também recebe rolagem, evitando impor seu tamanho mínimo à janela inteira.

205 testes existentes passaram no QGIS/GDAL, sem testes pulados. O teste de interface verificou a acessibilidade do acionamento; não realizou download real de imagens. ZIPs e metadados foram validados localmente. Publicação externa não realizada.
