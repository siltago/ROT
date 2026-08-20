# Robot Brain -- PROJECT.md

Fonte de verdade do projeto. Qualquer decisão arquitetural relevante deve
ser refletida aqui antes (ou junto) da implementação.

## Visão

Construir a "mente" de um robô social/inteligente como um sistema de
software modular, independente de hardware físico. Nesta fase não há
locomoção nem corpo real -- o objetivo é validar toda a arquitetura de
decisão, personalidade, emoção e memória via uma CLI de texto, de forma que
câmeras, ESP32, servos e sensores possam ser plugados depois sem reescrever
o cérebro.

## Objetivos

- Conversa natural, com personalidade consistente e estado emocional que
  flutua dentro de limites.
- Memória de curto prazo (conversa corrente), longo prazo (fatos/
  preferências duráveis) e por pessoa (relacionamento, confiança).
- Diferenciação explícita entre diálogo, intenção e comando -- nem toda
  frase vira ação.
- Planejamento e validação antes de qualquer execução.
- Registro central de ações (capacidades) com metadados de risco e
  confirmação.
- Preparação (interfaces, sem implementação real) para reconhecimento de
  pessoas por voz/câmera, corpo físico via ESP32, e integrações externas
  (Alexa, casa inteligente, música).
- Baixa latência: roteamento determinístico local para o caminho comum,
  reservando modelos maiores para conversa livre.

## Princípio arquitetural central

**O cérebro nunca depende diretamente de hardware físico.** Toda interação
com o corpo do robô passa pela interface abstrata `hardware.base.RobotHardware`.
Hoje existe apenas `SimulatorHardware` (imprime/loga ações). No futuro,
`ESP32Hardware` implementará a mesma interface enviando comandos via
`hardware.protocol.Command`/`CommandResult`. Nenhum código acima da camada
`hardware/` deve saber qual implementação está em uso.

O mesmo princípio se aplica a identidade (voz/câmera): o resto do sistema
só conhece `IdentityResult(person_id, confidence, source)`, nunca como a
identidade foi resolvida.

## Fluxo obrigatório de uma interação

```
input (texto hoje; voz/câmera no futuro)
  -> perception (identity resolver)
  -> brain.context (ContextBuilder: personalidade + emoção + pessoa + memórias)
  -> brain.decision_engine (classifica intenção + extrai ações propostas)
  -> brain.planner (valida ações propostas contra o ActionRegistry)
  -> actions.permissions (decide se precisa confirmação)
  -> actions.executor (único ponto que de fato executa um handler)
  -> brain.response_engine (gera texto de resposta)
  -> saída (texto hoje; TTS no futuro)
```

Texto gerado por um modelo de linguagem **nunca** aciona hardware ou
integrações diretamente. Toda ação passa por `ActionExecutor`, que é o
único componente autorizado a invocar um handler registrado no
`ActionRegistry`.

## Arquitetura de módulos

```
app/            configuração (app/config.py) e composição/CLI (app/main.py)
brain/          modelos centrais, decision engine, planner, context builder,
                response engine e o orquestrador (agent.py)
personality/    traços estáveis (PersonalityTraits) e derivação de estilo de resposta
emotions/       estado emocional flutuante, eventos e decaimento no tempo
memory/         short-term (RAM), long-term (Repository), perfis de pessoas
perception/     interfaces de voz, visão, identidade e reconhecimento facial
                (só a resolução manual está implementada; o resto é interface)
actions/        registry, executor, política de permissões, e as ações
                concretas (robot, smart_home, music, alexa)
hardware/       RobotHardware (abstrato), SimulatorHardware (implementado),
                ESP32Hardware (placeholder), protocolo de comando
integrations/   clientes de serviços externos -- integrations/llm/ (LLMProvider
                abstrato + OllamaProvider) está implementado; o resto
                (Alexa, Home Assistant, Spotify) é reservado para o futuro
api/            reservado para uma futura API HTTP/WebSocket
data/           persistência local em JSON (people, memories, state)
tablet_app/     app Android/Flutter para tablet como corpo provisório do robô:
                câmera, microfone, fala, rosto, debug e WebSocket com o cérebro
tests/          testes automatizados (pytest + pytest-asyncio)
```

## Tablet Android / corpo provisório do robô

A arquitetura do tablet foi desenhada para seguir o mesmo princípio do resto
do sistema: o cérebro continua desacoplado do hardware. O tablet é um cliente
de percepção e presença, não uma inteligência autônoma.

### Princípios do tablet

- o tablet expõe uma interface uniforme para câmera, microfone, alto-falante,
  sensores e tela;
- o Robot Brain decide intenção, emoção, memória e ações;
- o app de tablet apenas executa o que o cérebro ordena;
- o protocolo é versionado e permanece compatível com hardware futuro;
- o código do Android/Flutter não deve carregar lógica de personalidade,
  planejamento ou tomada de decisão.

### Tecnologia recomendada

Para a v0.1, a recomendação é **Flutter**.

Motivos:

- melhor produtividade para UI de rosto/expressão e painel de debug;
- fácil integração com CAMERA, mic, TTS, sensores e WebSocket;
- abstração mais simples para um app de tablet Android sem acoplar a lógica
  do cérebro ao Android SDK;
- a camada do app pode evoluir para um futuro hardware externo sem mudar o
  contrato do cérebro.

### Contrato de comunicação

O tablet e o Robot Brain se comunicam por mensagens padronizadas usando
WebSocket persistente e um payload JSON, com campos de `version`, `type`,
`device_id`, `timestamp` e `payload`. O protocolo completo está em
`PROTOCOL.md` e o desenho da arquitetura em `ARCHITECTURE.md`.

### Fluxo esperável

```text
tablet_app (câmera/mic/voz/tela)
  -> RobotConnection (WebSocket)
  -> mensagens de status, fala e sensor
  -> Robot Brain
  -> comandos: set_state, set_expression, speak, camera_config, stop_speaking
  -> tablet_app atualiza display, fala e câmera
```

A interface do tablet deve manter o contrato do cérebro estável para permitir
uma futura substituição por um hardware real (USB camera, microfone externo,
ESP32, servos, LEDs, etc.) sem mudar a lógica de decisão central.

## Decisões técnicas

- **Pydantic** para todos os modelos que cruzam fronteiras de módulo
  (`brain/models.py`, `EmotionalState`, `PersonalityTraits`, `PersonProfile`,
  `MemoryRecord`, protocolo ESP32) -- validação e serialização de graça.
- **Repository abstrato** (`memory/repository.py`) com uma implementação
  `JsonFileRepository`. Trocar por SQLite/Postgres/vector DB no futuro não
  deve exigir mudança em `memory/long_term.py` ou `memory/people.py`.
- **Roteador determinístico primeiro** no `DecisionEngine`: regex/regras
  locais classificam comandos estruturados comuns (luz, ar-condicionado,
  música, destravar porta) sem chamar um LLM. Isso mantém a ação simples
  rápida e barata. A classificação de intenção em si continua determinística;
  só a *geração da resposta* de diálogo/pergunta usa um LLM (ver abaixo).
- **LLM só para gerar texto de resposta, nunca para decidir ações.**
  `brain/response_engine.py` recebe um `LLMProvider` opcional
  (`integrations/llm/base.py`) e o usa apenas para turnos `DIALOGUE`/
  `QUESTION`/`DIALOGUE_AND_ACTION` -- a parte de ação já foi decidida e
  executada antes disso pelo pipeline determinístico. Se o provider falhar
  ou não estiver configurado, cai automaticamente para uma resposta template
  local; um turno nunca fica sem resposta por causa de rede/modelo local
  indisponível. Implementação atual: `OllamaProvider` (local, gratuito,
  configurável via `LLM_PROVIDER`/`OLLAMA_MODEL`/`OLLAMA_BASE_URL` no
  `.env`). Trocar para outro provider (ex.: Claude API) no futuro é uma
  nova classe em `integrations/llm/` + uma linha de wiring em
  `app/main.py::build_llm_provider` -- nada em `brain/` muda.
- **Personalidade vs. emoção são sistemas separados.** `PersonalityTraits`
  é estável e persiste via `Personality`. `EmotionalState` flutua turno a
  turno, decai no tempo (`EmotionalEngine.decay`) e nunca bloqueia ou altera
  a execução de uma ação validada -- só influencia o *tom* da resposta
  (`personality/style.py`).
- **Nem toda frase vira memória.** `memory/long_term.score_candidate` aplica
  uma heurística local (sem LLM) para decidir se algo é candidato a memória
  de longo prazo, com uma barra mínima de importância antes de persistir.
- **Confirmação de ações sensíveis** é decidida por metadados no
  `ActionSpec` (`risk_level`, `requires_confirmation`), aplicada pelo
  `PermissionPolicy`. Sem canal interativo, o padrão é negar (`auto_deny`) --
  nunca executar silenciosamente uma ação de alto risco.
- **Observabilidade estruturada**: `RobotAgent` emite um `BrainEvent` por
  turno com campos como person/intent/confidence/mood/plan/confirmation/
  execution/latency. Nunca expõe raciocínio bruto do modelo, só decisões
  estruturadas.

## Funcionalidades atuais

- Classificação de intenção determinística (DIALOGUE, ACTION,
  DIALOGUE_AND_ACTION, QUESTION, MEMORY-candidate via DIALOGUE, AMBIGUOUS).
- Registro e execução de ações simuladas: luzes, clima, música, destravar
  porta (alto risco, requer confirmação), e ações de corpo do robô
  (`robot.look_at`, `robot.set_expression`, `robot.move_head`) via
  `SimulatorHardware`.
- Estado emocional persistente com decaimento e eventos.
- Personalidade persistente configurável.
- Memória de curto prazo (conversa), longo prazo (JSON) e por pessoa.
- CLI de texto (`app/main.py`) funcional ponta a ponta, com confirmação
  interativa no terminal para ações de alto risco.
- Geração de resposta de diálogo/pergunta via LLM local (Ollama), com
  fallback automático para resposta template se o LLM estiver indisponível.
- Testes automatizados para `DecisionEngine`, `ActionExecutor` e o loop
  completo do `RobotAgent`.

## Funcionalidades futuras (fora de escopo nesta fase)

- Reconhecimento facial real (`perception/faces/recognizer.py` é placeholder).
- Pipeline de voz streaming real (mic -> VAD -> ASR -> cérebro -> TTS
  streaming); interfaces já definidas em `perception/speech/interfaces.py`.
- `ESP32Hardware` real, com transporte Wi-Fi/serial sobre o protocolo já
  definido em `hardware/protocol.py`.
- Integrações reais: Alexa/Smart Home API, Home Assistant, Spotify, etc.
- Fallback via LLM no `DecisionEngine` para entradas ambíguas.
- API HTTP/WebSocket (`api/`) para clientes externos.
- Substituição do `JsonFileRepository` por um banco real / vector DB.
