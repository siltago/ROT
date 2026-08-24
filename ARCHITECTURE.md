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
  -> OllamaProvider
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
