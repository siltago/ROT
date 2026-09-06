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

## Restrição de implantação final

O produto final deve funcionar com **apenas um ESP32 no corpo do Bob**. O
ESP32 é responsável por sensores, atuadores e comunicação, mas não hospeda o
cérebro, o modelo de IA nem o banco de dados. Cérebro, inferência, memória e
persistência ficam em serviços de nuvem acessados por uma conexão segura.

Consequências desta restrição:

- o banco de produção deve ser remoto e gerenciado; PostgreSQL é o padrão;
- Supabase é a opção inicial preferida por oferecer PostgreSQL gerenciado,
  autenticação e API, sem criar dependência no código de domínio;
- SQLite pode ser usado somente em desenvolvimento, testes ou cache local de
  um gateway, nunca como fonte principal de memória no produto final;
- o ESP32 nunca recebe credenciais administrativas do banco e não acessa suas
  tabelas diretamente: comunica-se com a API/WebSocket do cérebro;
- pesos de modelos e datasets de treinamento ficam em armazenamento de
  objetos, enquanto o banco guarda metadados, memórias, relações e embeddings;
- toda persistência continua atrás da interface `Repository`, permitindo
  trocar o provedor de nuvem sem alterar a lógica cognitiva.

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
                abstrato + OpenAIProvider) está implementado; o resto
                (Alexa, Spotify) é reservado para o futuro; Home Assistant local
                está implementado como provider de casa inteligente
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
  indisponível. Implementação atual: `OpenAIProvider` via Responses API,
  configurável por `LLM_PROVIDER`/`OPENAI_API_KEY`/`OPENAI_MODEL` no
  `.env`. Trocar para outro provider no futuro é uma
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
- Geração de resposta de diálogo/pergunta via OpenAI API, com
  fallback automático para resposta template se o LLM estiver indisponível.
- Testes automatizados para `DecisionEngine`, `ActionExecutor` e o loop
  completo do `RobotAgent`.
- Cliente Flutter v0.1 com câmera frontal, captura manual de frame, microfone
  PCM16/16 kHz preparado para streaming futuro, reconhecimento de fala local,
  TTS opcional, rosto animado, painel de debug e WebSocket configurável com
  reconexão automática.
- Gateway FastAPI/WebSocket em `api/server.py` integrado ao `RobotAgent` e à
  OpenAI Responses API. O tablet usa reconhecimento de fala Android como percepção local,
  envia a transcrição final e recebe resposta textual, estado e expressão. O
  LLM continua sem acesso direto a hardware ou integrações.

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

## Áudio conversacional do tablet

A evolução do áudio passa a usar módulos independentes do fornecedor de IA:
noise floor adaptativo, VAD com probabilidade, máquina de turno e pre/post-roll.
O baseline e a estratégia incremental estão em `tablet_app/AUDIO_PIPELINE.md`.
O PCM só substituirá o reconhecedor Android no fluxo principal quando o backend
tiver STT de streaming compatível, preservando a conversa funcional durante a
migração.

O protocolo agora também suporta sessões PCM incrementais com frames WebSocket
binários, sequência, fila limitada e cancelamento. A transcrição é representada
por contratos genéricos em `perception/speech/streaming.py`; integrações de STT
não podem vazar tipos do fornecedor para o `RobotAgent`. Transcripts parciais
são exclusivamente observacionais e apenas um final idempotente por stream pode
entrar no pipeline de decisão.

## Comportamento e iniciativa limitada

O estado efêmero da sessão vive em `brain/world_state.py`. Eventos internos são
publicados por `brain/events.py`; `brain/behaviors.py` transforma eventos apenas
em `BehaviorProposal`, sujeitas a prioridade, cooldown, estado ocupado e limite
por hora. Comportamentos nunca executam handlers. Ações locais de hora, data e
status usam o mesmo `ActionRegistry`/`ActionExecutor` das demais capacidades.
O relatório e as fronteiras para futura persistência estão em
`BEHAVIOR_MILESTONE.md`.

## Cognition v0.2 orientada a eventos

O caminho proativo agora usa `RobotEvent`/`EventType`, fontes desacopladas,
`WorldStateReducer`, `ContextEvaluator`, drives independentes de emoção,
behaviors contextuais, `ProposalArbiter` e iniciativa limitada. Nenhum desses
componentes executa ações; uma ação sugerida continua obrigada a passar por
Planner, PermissionPolicy e ActionExecutor. Estado, cooldowns e métricas desta
fase permanecem em RAM. O desenho, configuração, simulação e validação estão em
`COGNITION_V02.md`.

## Smart Home v0.1

Casa inteligente usa `SmartHomeService` e `SmartHomeProvider`; o provider
inicial é `HomeAssistantProvider`, conectado por REST ao Home Assistant na rede
local. Targets são resolvidos localmente contra um registry normalizado em RAM.
URL e token vêm do ambiente do cérebro e nunca chegam ao tablet ou ESP32. Todos
os comandos continuam passando por Planner, PermissionPolicy e ActionExecutor,
possuem `request_id` e timeout e nunca usam LLM. O desenho e a configuração
estão em `PROTOCOL.md`, `ARCHITECTURE.md` e `HOME_ASSISTANT_SETUP.md`.

## Identidade verbal do Bob

O contrato estável de voz vive em `personality/voice.py` e é aplicado tanto ao
prompt do LLM quanto às respostas determinísticas. Bob fala em português
brasileiro natural, geralmente em uma ou duas frases, com curiosidade, afeto
discreto e humor ocasional; evita linguagem corporativa, servilismo, markdown e
bordões repetitivos. Emoção e relacionamento modulam o tom, mas não substituem
a identidade. O contrato é exclusivamente de apresentação e nunca propõe,
confirma ou executa ações.

## Linguagem visual do Bob

O fundo da interface é sempre preto. Em conversa social e respostas breves, a
face com olhos continua sendo a apresentação padrão. Quando um resultado tem
valor visual (hora, data, clima, música, timer e casos futuros), o
`PresentationPlanner` pode selecionar uma `SceneSpec` em tela cheia; durante a
cena os olhos desaparecem completamente. O cliente desenha animações
procedurais de um catálogo local e retorna à face ao expirar ou receber
`dismiss_scene`. A decisão é semântica e determinística, baseada em resultados
de ações validadas; nenhum texto de LLM vira código de interface.

O relógio segue uma identidade de painel digital: dígitos de sete segmentos,
segundos, data e ambiente procedural. A implementação atual usa verde luminoso
e cenário em pixel art, com zonas reservadas para impedir que
texto, temperatura e elementos ambientais se sobreponham. Amanhecer mostra um sol baixo,
dia mostra o sol alto e noite mostra lua e estrelas, sempre sobre preto. O fuso
vem de `ROBOT_TIMEZONE`, não do servidor cloud. Clima usa coordenadas explícitas
do robô e o provider gratuito Open-Meteo; sem localização, Bob informa que ela
precisa ser configurada e nunca inventa uma temperatura.

Perguntas sobre o momento atual usam `weather.get`; perguntas com “amanhã”
usam `weather.forecast`. A previsão fala mínima, máxima, condição e chance de
chuva e a cena é escolhida pelo código meteorológico, nunca pela temperatura
isolada. Céu limpo à noite usa lua/estrelas, não sol.
