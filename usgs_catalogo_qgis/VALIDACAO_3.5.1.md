# Correção 3.5.1 — verificador de publicação

Correções dos apontamentos enviados pelo usuário:

- prodes_ui.py: QFont.Weight.Bold nos dois títulos e QgsUnitTypes.DistanceUnit.DistanceMeters na barra de escala. Enumerações conferidas no QGIS 3.34.4.
- tests/test_prodes.py: importação exclusivamente de qgis.PyQt; não usa mais fallback de importação direta de PyQt5.
- plugin.py: as duas exceções opcionais de metadados espectrais e enquadramento do mapa passam a ser registradas no log e no resultado da importação. A importação concluída é mantida; erros não são mais ignorados silenciosamente.
- environmental.py: retirada a chave pública DataJud literal do código. Se houver números judiciais, o módulo consulta a página oficial de acesso CNJ para obter o valor vigente. Se o portal estiver bloqueado, a consulta judicial fica pendente, com orientação para informar a chave pública no campo existente. Não esconde nem fragmenta a chave para contornar o detector, e não persiste o valor no relatório/configuração.

Validação local: 205 testes passaram, sem testes pulados, no QGIS 3.34.4 / GDAL 3.8.4 / Qt 5.15.13. Dois testes novos conferem a obtenção da chave a partir de HTML simulado da documentação oficial e o estado pendente quando esse portal é bloqueado. A página oficial pode bloquear acesso automatizado; não se promete consulta judicial sem esse campo em qualquer instalação.

Bandit 1.9.4, varredura recursiva de todo o código, incluindo testes: zero apontamentos. Detect-secrets 1.5.0, todos os arquivos do complemento: zero achados. Os padrões exatos de enumeração/importação apresentados no print também foram conferidos e removidos. Compilação Python, validação dos metadados e integridade do ZIP verificadas.

Esta é uma validação local. A plataforma de publicação pode usar versões e regras diferentes; é necessário reenviar o ZIP 3.5.1 para obter o resultado oficial. Não foi realizada publicação externa. Mantido o caráter experimental e as limitações de cobertura documentadas em GUIA_3.5.md.
