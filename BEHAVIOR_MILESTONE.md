# Milestone: personalidade, ações e iniciativa limitada

## Baseline

Antes deste milestone havia 27 testes aprovados. Já existiam decisões tipadas,
roteamento determinístico, `Planner`, `ActionRegistry`, `PermissionPolicy`,
`ActionExecutor`, personalidade estável, emoção com clamp/decay, contexto curto,
memória por repositório e observabilidade estruturada.

## Arquitetura adicionada

```text
user text
  -> DecisionEngine
  -> ContextBuilder (personality + emotion + recent dialogue)
  -> Planner
  -> PermissionPolicy
  -> ActionExecutor
  -> ResponseEngine

BrainEvent -> EventBus -> BehaviorEngine -> BehaviorProposal
                                      -> InitiativeEngine -> proposta aceita
```

`BehaviorProposal` nunca executa ações. Uma proposta futura que contenha
`proposed_action` ainda deverá passar pelo planner, permissões e executor.

## Componentes

- `WorldState`: estado efêmero da conversa, pessoa, fala e processamento.
- `EventBus`: eventos internos síncronos e assinaturas removíveis.
- `BehaviorEngine`: greeting, curiosidade, idle e comentário de clima.
- `InitiativeEngine`: enabled, prioridade mínima, cooldown, bloqueio enquanto
  usuário/robô fala ou processa e limite por hora.
- `InMemoryRepository`: implementação sem disco do contrato existente.
- ações locais: `time.get`, `date.get` e `system.status`.
- personalidade: curiosity, humor, sarcasm, affection, initiative, verbosity,
  confidence e formality, separada do estado emocional.

## Segurança

O LLM continua sendo usado somente para texto de conversa. A decisão de ação é
estruturada e nenhuma personalidade, emoção, evento ou comportamento chama
handlers. Toda capacidade executável é registrada e passa por validação,
política e `ActionExecutor`.

## Persistência

Nenhum banco foi adicionado. `InMemoryRepository` serve a testes e sessões RAM;
`JsonFileRepository` continua disponível para configuração local compatível.
Áudio, comportamento e iniciativa não dependem de persistência.

## PRONTO PARA SUPABASE?

Sim, no nível de contratos, mas não há integração agora. Uma futura
`SupabaseRepository` implementará `memory.repository.Repository` (`add`, `get`,
`all`, `query`, `update`, `delete`). `PeopleDirectory` e `LongTermMemory`
recebem esse contrato por injeção; personalidade, emoção, BehaviorEngine,
Planner e ActionExecutor não precisam mudar. Preferências pessoais continuam no
modelo `PersonProfile` e podem usar a mesma implementação de repositório ou um
adapter especializado sem vazar Supabase para o cérebro.

## Limitações atuais

- ações de luz, clima e música ainda são mocks;
- clima externo não foi integrado;
- propostas de iniciativa não são enviadas sozinhas ao tablet nesta fase;
- entendimento semântico aberto ainda cai no LLM apenas para gerar resposta;
  ações comuns usam regras determinísticas e sinônimos explícitos;
- histórico curto é RAM; JSON local permanece opcional para dados existentes.
