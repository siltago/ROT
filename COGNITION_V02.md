# Cognition v0.2 — contexto e iniciativa orientados a eventos

## Baseline

Antes deste milestone, a suíte tinha **39 testes aprovados em 1,83 s**. A
compilação dos módulos Python também passou; Ruff não estava instalado no
ambiente, portanto não houve resultado de lint por Ruff.

## Arquitetura

O caminho reativo seguro continua inalterado:

```text
Intent -> Planner -> PermissionPolicy -> ActionExecutor -> resposta
```

O novo caminho proativo é local, determinístico e apenas produz propostas:

```text
EventSource -> EventBus -> WorldStateReducer -> ContextEvaluator
            -> DriveEngine -> BehaviorEngine -> ProposalArbiter
            -> InitiativeEngine -> resposta sugerida / ActionRequest sugerida
```

Uma `suggested_action` nunca é executada por behavior ou drive. Se for aceita
futuramente, deverá entrar no Planner, política de permissão e executor.

## Contratos e estado

- `RobotEvent`: ID UUID, `EventType`, timestamp UTC, source e data.
- `EventBus`: subscriptions tipadas/wildcard, handlers sync/async,
  unsubscribe e isolamento de erro.
- `WorldState`: conversa, atividade, pessoas presentes, ambiente e horário;
  permanece somente em RAM e é atualizado pelo `WorldStateReducer`.
- `DerivedContext`: disponibilidade/ocupação do usuário, recência, calor,
  frio, escuridão, oportunidade social, período silencioso e permissão de
  iniciativa.
- `DriveState`: curiosity, social, helpfulness, playfulness e rest, todos com
  clamp 0..1, alterações graduais e decay. Drives não são emoções.

Todos os thresholds ficam em `CognitionConfig`: temperaturas, delta
significativo, recência, idle social, TTL, quiet period, prioridade mínima,
cooldown global, cooldown por behavior e limite por hora.

## Behaviors e arbitragem

- `GreetingBehavior`: `person_detected` e `user_returned`.
- `WeatherBehavior`: mudança climática/temperatura relevante, sem controlar ar.
- `IdleBehavior`: pessoa presente e idle suficiente.
- `CuriosityBehavior`: pessoa desconhecida, objeto novo ou evento incomum.
- `SocialBehavior`: encerramento de conversa sem inferir emoção humana.
- `HelpfulnessBehavior`: sugere ajuda em oportunidade clara; nunca executa.

Cada proposta possui ID, tipo, prioridade, confiança, motivo, resposta/ação
sugeridas, indicador de LLM e expiração. A prioridade é determinística e
inclui contexto, confiança e drive relevante. O arbiter permite no máximo uma
proposta vencedora. O `InitiativeEngine` aplica expiração, prioridade mínima,
quiet period, estados ocupado/falando/processando, cooldown global e por
behavior, além do limite horário.

Estados de iniciativa: `idle`, `evaluating`, `proposal_ready`, `suppressed`,
`executing` e `cooldown`. Eventos internos observáveis cobrem proposed,
suppressed, started e completed.

## Sources, simulação e integrações

`EventSource`, `SimulatedEventSource` e `ClockEventSource` ficam na percepção;
eles só emitem eventos. O relógio emite no máximo por minuto e registra mudança
de hora/período. `WeatherProvider` é abstrato e possui `MockWeatherProvider`.
Eventos de pessoa recebem apenas `person_id` e `confidence`, mantendo câmera e
ML Kit fora da cognição.

`POST /debug/events` injeta eventos reais no motor cognitivo quando
`DEBUG_EVENTS_ENABLED=true`. O padrão é desabilitado. Se houver tablet
conectado, uma resposta local selecionada é enviada como mensagem e fala. O
endpoint nunca executa a ação sugerida.

Exemplo:

```powershell
$env:DEBUG_EVENTS_ENABLED="true"
Invoke-RestMethod -Method Post http://localhost:8000/debug/events `
  -ContentType "application/json" `
  -Body '{"type":"temperature_changed","data":{"previous":25,"temperature":33}}'
```

## Observabilidade, métricas e custo

São expostas latências de evento, contexto, behaviors, arbitragem, decisão de
iniciativa e total proativo. Contadores: propostas criadas/suprimidas,
iniciativas executadas/por hora e chamadas LLM por iniciativa. Nenhum
chain-of-thought é armazenado.

Todos os behaviors iniciais usam templates locais (`requires_llm=false`). Logo,
o custo esperado desta versão para pessoa, clima, idle, curiosidade e sugestão
de luz é **zero chamadas de LLM**. `ContextSerializer` já limita o payload caso
um behavior futuro realmente precise de geração de linguagem.

## Validação e limitações

Resultado final: **49 testes aprovados**. Foram adicionados testes de EventBus,
reducers, contexto, drives, behaviors, arbitragem, suppression, cooldown,
limite horário e quatro fluxos ponta a ponta. A compilação Python e
`git diff --check` passaram. Ruff não está instalado.

Limitações atuais:

- clima e sensores ainda são mocks/injeção debug;
- o relógio oferece polling, mas seu scheduler de produção ainda não é iniciado;
- identificação persistente e consolidação evento -> memória ficam fora;
- uma ação sugerida aguarda um futuro fluxo explícito de confirmação;
- métricas permanecem em RAM.

## Próximo milestone recomendado

Antes de banco, recomendo uma integração curta **Cognition v0.2.1**: ligar os
eventos reais de presença/fala do tablet ao backend, iniciar o ClockEventSource
no lifecycle do servidor e validar spam/cooldowns por alguns dias. Depois disso,
**Memory v0.1** é o passo certo para persistir people, preferences, memories e
somente eventos importantes — nunca o EventBus inteiro nem o WorldState.
