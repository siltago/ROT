# AGENTS.md

Orientações para qualquer agente de IA (ou humano) que for trabalhar neste
repositório.

1. **Leia `PROJECT.md` antes de alterar arquitetura.** Ele é a fonte de
   verdade sobre visão, decisões técnicas e estrutura de módulos. Se uma
   mudança contradiz algo lá descrito, atualize o `PROJECT.md` como parte
   da mesma mudança -- não deixe a documentação divergir do código.

2. **Preserve a separação cérebro/hardware.** Nada acima de `hardware/`
   (brain, personality, emotions, memory, actions/robot) pode importar
   `SimulatorHardware` ou `ESP32Hardware` diretamente. Sempre dependa da
   interface abstrata `hardware.base.RobotHardware`, injetada por quem monta
   o sistema (`app/main.py`).

3. **Não crie dependência direta entre LLM e hardware/integrações.** Texto
   produzido por um modelo de linguagem nunca deve acionar uma ação
   diretamente. O fluxo obrigatório é: decision engine -> planner
   (validação) -> permissions -> executor. Um LLM pode *propor* ações
   (como `ActionRequest`), nunca executá-las.

4. **Use `ActionRegistry`/`ActionExecutor` para qualquer nova capacidade.**
   Não adicione um jeito paralelo de "fazer o robô fazer algo". Toda nova
   ação: (a) ganha um handler assíncrono que retorna `ActionOutcome`, (b) é
   registrada com `ActionSpec` (incluindo `risk_level` e
   `requires_confirmation` corretos), (c) fica em `actions/<categoria>/`.

5. **Atualize a documentação quando decisões importantes mudarem.**
   Mudanças de arquitetura, novos módulos, ou trocas de decisão técnica
   (ex.: trocar `JsonFileRepository` por outro backend) devem atualizar
   `PROJECT.md`. Mudanças de comportamento observável pelo usuário (novos
   comandos de CLI, etc.) devem atualizar `README.md`.

6. **Evite grandes refatorações sem necessidade.** A estrutura modular já
   existe e foi pensada para separação de responsabilidades. Prefira
   adicionar/estender em vez de reorganizar. Se uma refatoração grande
   parecer necessária, explique o motivo no `PROJECT.md` antes de fazer.

7. **Preserve compatibilidade com o ESP32 futuro.** Qualquer mudança na
   interface `RobotHardware` (`hardware/base.py`) ou no protocolo
   (`hardware/protocol.py`) deve ser cuidadosamente considerada, pois
   afeta o contrato que o firmware real usará. Não implemente firmware ou
   transporte real ainda -- isso é trabalho futuro deliberadamente adiado.

8. **Priorize baixa latência.** Prefira lógica local/determinística
   (regras, heurísticas) para o caminho comum (comandos estruturados,
   atualização de estado emocional, memória). Reserve chamadas a modelos
   grandes para conversa livre genuína. Não bloqueie o loop principal
   esperando I/O desnecessário.

9. **Mantenha o tablet como cliente do cérebro.** O app de tablet nunca deve
  assumir personalidade, memória ou decisão do robô. O papel dele é
  percepção, presença, interface e condução de sensores/áudio/vídeo.

10. **Preserve o protocolo do tablet.** Qualquer mudança em mensagens,
   capacidades ou estados visuais deve ser refletida em `PROTOCOL.md` e
   `ARCHITECTURE.md` no mesmo PR.

11. **Evite breaking changes no canal de comunicação.** Sempre mantenha
    compatibilidade com versões anteriores do protocolo e with a WebSocket
    persistente antes de adicionar formas paralelas de transporte.

12. **Não exponha segredos no app Android.** Endereços, tokens e chaves
    devem vir de configuração local segura e não hardcoded.

- Rode `pytest` antes de considerar uma mudança pronta:
  `.venv/Scripts/python.exe -m pytest -q` (Windows) ou
  `.venv/bin/python -m pytest -q` (Unix).
- Novos testes para `DecisionEngine` e `ActionExecutor` são obrigatórios
  sempre que seu comportamento mudar; são os dois componentes mais críticos
  para segurança e correção do sistema.
