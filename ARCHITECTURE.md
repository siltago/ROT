# Arquitetura do Robot Tablet

## Visão geral

Este projeto define a camada de presença do robô: câmera, microfone, alto-falante, tela e sensores do tablet. O tablet não é o cérebro. Ele é um cliente de percepção e interface para o Robot Brain.

A intenção é manter a separação entre:

- cérebro: personalidade, emoções, memória, decisões, planejamento;
- percepção e presença: câmera, áudio, display, sensores, comunicação.

Essa separação evita acoplamento e facilita substituir o tablet por hardware físico no futuro.

## Escolha tecnológica

### Flutter

A opção recomendada para a v0.1 é Flutter.

Motivos:

- desenvolvimento rápido para Android com UI consistente;
- boa API para câmera, microfone e WebSocket via plugins;
- excelente evolução para uma interface de rosto robótico e painel de debug;
- arquitetura de widgets e serviços facilita a separação de responsabilidades;
- a camada nativa pode ser encapsulada em serviços, preservando o cérebro desacoplado da plataforma Android.

### Kotlin nativo

Kotlin nativo é interessante quando a exigência é máxima performance nativa e acesso direto a recursos muito específicos do Android. No entanto, para a primeira fase, a curva de desenvolvimento e a manutenção são mais altas, e a criação de interfaces complexas como rosto animado e painel de diagnóstico fica mais pesada.

Conclusão:

- usar Flutter para o primeiro tablet;
- encapsular acesso a câmera/audio em services;
- manter o protocolo em formato independente das APIs do Android.

## Princípios arquiteturais

1. O tablet expõe capacidades padronizadas.
2. O cérebro fala com o tablet via protocolo de mensagens.
3. O app não toma decisões sobre intenção, emoção ou ação.
4. Mudanças de hardware devem ser transparentes ao cérebro.
5. A latência importa mais do que a qualidade máxima de imagem.
6. O código de sensores, câmera e áudio deve ficar em serviços isolados.

## Estrutura proposta

```text
lib/
├── app/
│   ├── robot_app.dart
│   └── config.dart
├── core/
│   ├── connection/
│   │   └── robot_connection.dart
│   ├── permissions/
│   │   └── permission_manager.dart
│   ├── protocol/
│   │   └── protocol.dart
│   └── logging/
│       └── app_logger.dart
├── devices/
│   ├── camera/
│   │   └── camera_service.dart
│   ├── microphone/
│   │   └── microphone_service.dart
│   ├── audio/
│   │   └── audio_output_service.dart
│   ├── sensors/
│   │   └── sensor_service.dart
│   └── screen/
│       └── screen_service.dart
├── robot/
│   ├── robot_display_state.dart
│   ├── device_capabilities.dart
│   └── robot_face.dart
├── ui/
│   ├── robot_face_widget.dart
│   ├── debug_panel.dart
│   └── settings_screen.dart
├── main.dart
└── services/
    └── app_state.dart
```

## Responsabilidades por camada

### Camada de aplicação

- inicializa os serviços;
- gerencia estado global do app;
- decide quando mostrar painel de debug;
- lida com reconexão e estado offline.

### Camada de conexão

- WebSocket persistente;
- serialização de mensagens;
- reconexão automática;
- retry exponencial;
- tratamento de timeout e desconexão.

### Camada de dispositivos

- câmera: preview, switch camera, FPS e resolução;
- microfone: stream, volume, VAD, speech_started, speech_ended;
- áudio: TTS e reprodução de streaming;
- sensores: acelerômetro, giroscópio, bateria e orientação.

### Camada de apresentação

- rosto mínimo do robô;
- expressões visuais em estados como idle, listening, thinking, speaking;
- detecção facial local no tablet para deslocar suavemente o rosto virtual em
  direção à pessoa; essa presença visual não identifica pessoas nem toma decisões;
- debug overlay com conexão e estatísticas;
- estado offline e erro.

### Apresentação semântica em tela cheia

O rosto é o fallback para conversa social e respostas curtas. Resultados com
valor visual passam por um `PresentationPlanner` determinístico no cérebro,
que transforma apenas resultados de ações já validadas em uma `SceneSpec`.
O tablet recebe `show_scene`, oculta os olhos e renderiza a receita sobre fundo
preto usando um catálogo local. `dismiss_scene` ou o tempo de vida da cena
restaura a face.

```text
ActionOutcome -> PresentationPlanner -> SceneSpec -> WebSocket
                                                -> SceneRegistry/Renderer local
```

O catálogo inicial possui relógio, data, clima procedural e reprodução de
música. Animações e primitivas ficam no cliente como a cobrinha ociosa; o
cérebro escolhe quando e com quais dados apresentá-las, sem gerar Flutter,
JavaScript ou outro código executável em tempo real.

O relógio recebe hora, segundos, data, dia da semana e período calculados no
fuso configurado do Bob. Opcionalmente recebe a leitura climática em cache. A
integração meteorológica usa `WeatherProvider`; `OpenMeteoWeatherProvider` é a
implementação inicial e requer nome, latitude e longitude na configuração do
cérebro.

O renderer de relógio e clima usa pixel art procedural, com coordenadas
responsivas e áreas seguras separadas para informação e cenário. O fundo-base
permanece preto; estrelas, lua, sol, nuvens e chuva são desenhados em blocos sem
antialiasing, enquanto os dígitos usam segmentos sólidos e nítidos.

## Fluxo principal

```text
Tablet
  -> CameraService.start()
  -> MicrophoneService.start()
  -> RobotConnection.connect()
  -> envia device_hello + capabilities
  -> escuta mensagens do cérebro
  -> recebe set_expression / set_state / speak
  -> atualiza face e áudio
```

### Conversa por voz com resposta textual

```text
Android SpeechRecognizer (percepção)
  -> recognized_speech
  -> API WebSocket /ws/device
  -> RobotAgent (decision -> planner -> permissions -> executor -> response)
  -> OpenAIProvider (Responses API)
  -> show_message + set_expression + set_state
  -> tablet exibe texto e anima o rosto
```

O reconhecedor Android apenas propõe a transcrição. Ele não contém
personalidade, memória, decisão ou regras de ação. Ações sensíveis recebidas
por esse canal usam confirmação não interativa e são negadas por padrão.

## Compatibilidade futura

A arquitetura foi desenhada para permitir evoluir sem quebrar o cérebro:

- `CameraService` pode virar USB camera, webcam ou sensor local;
- `MicrophoneService` pode virar microfone externo;
- `AudioOutputService` pode virar TTS local, speaker físico, ou ESP32;
- `RobotConnection` pode ser um WebSocket, MQTT ou bridge local;
- `RobotDisplayState` continua válido independentemente do hardware real.

## Regras de segurança

- só solicitar permissões necessárias;
- manter IP do cérebro em configuração e não hardcoded;
- não enviar logs com áudio ou dados sensíveis em excesso;
- tratar reconexão sem bloquear UI;
- manter o protocolo versionado;
- nunca acoplar o cérebro ao hardware real ou ao Android SDK.

## Milestones

### v0.1

- app abre;
- permissões de câmera e microfone;
- preview frontal;
- indicador de volume;
- detecção básica de fala;
- WebSocket configurável;
- mensagens `speech_started` e `speech_ended`;
- `set_state`, `set_expression`, `speak` e reconexão.

### v0.2

- streaming de áudio real;
- streaming de câmera com modos observation/live;
- barge-in;
- métricas de latência.

### v0.3

- integração com Robot Brain;
- contexto visual;
- reconhecimento de pessoas;
- cadastro de identidade.

### v0.4

- wake word;
- sempre ativo;
- otimização de bateria;
- background/foreground.

## Estado da implementação v0.1

O cliente Flutter captura PCM16/16 kHz diretamente do microfone, calcula RMS
localmente, aplica VAD simples e envia envelopes versionados pelo WebSocket.
A URL do cérebro é configuração persistente do dispositivo. `RobotConnection`
controla a conexão e o backoff; áudio e câmera continuam sendo apenas entradas
de percepção e nunca executam ações diretamente.

## Fundação de áudio conversacional

O tablet agora possui uma camada modular em
`devices/microphone/audio_pipeline.dart`, com configuração centralizada,
noise floor adaptativo, VAD probabilístico, máquina explícita de turn-taking e
pre/post-roll. O reconhecedor Android permanece temporariamente como caminho
principal até existir STT streaming no backend. Baseline e ativação incremental
estão descritos em `tablet_app/AUDIO_PIPELINE.md`.

O modo experimental `pcmStreaming` conecta essa fundação a um transporte
binário WebSocket com sequência e backpressure. No backend,
`SpeechToTextProvider` cria sessões incrementais desacopladas do Robot Brain;
somente `SpeechTranscript.is_final` atravessa o `TabletBrainBridge`. O provider
inicial usa OpenAI Realtime no diretório `integrations/stt/`, mas pode ser
substituído sem mudanças no tablet, no bridge ou no cérebro. O modo legado
continua sendo o padrão até o comparativo real no dispositivo ser concluído.
# Cognição orientada a eventos

```text
tablet/sensor/clock/weather -> EventSource -> EventBus
                                      -> WorldStateReducer
                                      -> ContextEvaluator + DriveEngine
                                      -> BehaviorEngine -> ProposalArbiter
                                      -> InitiativeEngine -> response sink
```

O sink pode apresentar/falar uma resposta local. `suggested_action` é somente
uma proposta e não contorna o pipeline seguro de ações. O backend não conhece a
implementação concreta de câmera, clima ou hardware.

## Casa inteligente local

```text
fala -> DecisionEngine -> Planner -> PermissionPolicy -> ActionExecutor
     -> SmartHomeService -> HomeAssistantProvider -> REST na rede local
     -> Home Assistant -> integração do fabricante/Matter/Zigbee -> dispositivo
```

O backend mantém dispositivos normalizados em RAM e guarda URL/token somente no
processo do cérebro. O tablet não participa dos comandos de casa. O ESP32 pode
ser uma entidade do Home Assistant ou hardware do robô, mas não hospeda o Home
Assistant. Outro provider pode substituir o Home Assistant sem alterar o cérebro.
