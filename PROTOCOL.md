# Protocolo Robot Tablet ↔ Robot Brain

## Objetivo

Este documento define a estrutura das mensagens enviadas entre o tablet e o Robot Brain. O protocolo é leve, versionado e pensado para evoluir sem quebrar compatibilidade.

## Convenções gerais

- toda mensagem usa JSON;
- campo `version` obrigatório;
- campo `type` obrigatório;
- campo `device_id` obrigatório;
- campo `timestamp` em epoch milliseconds;
- campo `payload` opcional, quando a mensagem carrega dados;
- mensagens inesperadas devem ser ignoradas com segurança;
- o padrão é manter a comunicação por WebSocket persistente.

## Estrutura base

```json
{
  "version": 1,
  "type": "device_status",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "state": "LISTENING"
  }
}
```

## Mensagens do tablet para o cérebro

### smart_home_devices

Legado v1, mantido apenas para clientes antigos e atualmente ignorado. A
integração ativa é feita diretamente pelo cérebro com o Home Assistant.

```json
{"version":1,"type":"smart_home_devices","device_id":"tablet_antigo","timestamp":1712345678901,"payload":{"provider":"legacy","devices":[]}}
```

### smart_home_result

Legado v1, mantido para compatibilidade e atualmente ignorado.

```json
{"version":1,"type":"smart_home_result","device_id":"tablet_001","timestamp":1712345678901,"payload":{"request_id":"req_123","success":true,"provider_latency_ms":85,"state":{}}}
```

### smart_home_disconnected

Legado v1, mantido para compatibilidade e atualmente ignorado.

```json
{"version":1,"type":"smart_home_disconnected","device_id":"tablet_antigo","timestamp":1712345678901,"payload":{"provider":"legacy"}}
```

### recognized_speech

Resultado do reconhecimento de fala executado na camada de percepção do
tablet. Resultados parciais podem ser usados apenas para feedback visual; o
cérebro processa somente `is_final: true`.

```json
{
  "version": 1,
  "type": "recognized_speech",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "text": "Como você está hoje?",
    "is_final": true,
    "confidence": 0.91,
    "language": "pt-BR",
    "source": "android_speech_recognizer"
  }
}
```

### device_hello

```json
{
  "version": 1,
  "type": "device_hello",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "capabilities": [
      "camera.front",
      "camera.back",
      "microphone",
      "speaker",
      "screen",
      "accelerometer",
      "gyroscope"
    ]
  }
}
```

### device_connected

```json
{
  "version": 1,
  "type": "device_connected",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "online": true
  }
}
```

### device_status

```json
{
  "version": 1,
  "type": "device_status",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "battery": 86,
    "wifi": "connected",
    "state": "LISTENING"
  }
}
```

### speech_started

```json
{
  "version": 1,
  "type": "speech_started",
  "device_id": "tablet_001",
  "timestamp": 1712345678901
}
```

### speech_ended

```json
{
  "version": 1,
  "type": "speech_ended",
  "device_id": "tablet_001",
  "timestamp": 1712345678901
}
```

### audio_chunk

```json
{
  "version": 1,
  "type": "audio_chunk",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "encoding": "pcm16",
    "sample_rate": 16000,
    "channels": 1,
    "chunk_ms": 50,
    "data_base64": "..."
  }
}
```

### camera_frame

```json
{
  "version": 1,
  "type": "camera_frame",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "camera": "front",
    "width": 640,
    "height": 480,
    "format": "jpeg",
    "data_base64": "..."
  }
}
```

### camera_status

```json
{
  "version": 1,
  "type": "camera_status",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "active": true,
    "fps": 5,
    "mode": "observation"
  }
}
```

### motion_update

```json
{
  "version": 1,
  "type": "motion_update",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "accelerometer": [0.12, -0.04, 0.98],
    "gyroscope": [0.01, 0.02, -0.05]
  }
}
```

### touch_event

```json
{
  "version": 1,
  "type": "touch_event",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "x": 320,
    "y": 240,
    "action": "tap"
  }
}
```

### app_error

```json
{
  "version": 1,
  "type": "app_error",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "code": "MIC_PERMISSION_DENIED",
    "message": "Microphone permission not granted"
  }
}
```

### speech_playback_done

Enviada assim que o tablet termina de tocar uma fala do robô (saudação de
wake-word ou resposta) e retoma o microfone. O cérebro usa isso como o sinal
real de que um turno acabou -- em vez de estimar a duração da fala e esperar
um tempo fixo (que na prática varia: rede, decodificação e o próprio atraso
de retomada do microfone do cliente) -- antes de rearmar o timer de
inatividade do wake-word ou de considerar a resposta concluída. Sem payload.

```json
{"version":1,"type":"speech_playback_done","device_id":"tablet_001","timestamp":1712345678901,"payload":{}}
```

## Mensagens do cérebro para o tablet

### wake_state

O microfone (streaming) fica sempre ligado — é o pipeline confiável. O que
muda é se um trecho reconhecido chega a virar um turno de verdade (com
custo de LLM) ou não: o cérebro escaneia toda transcrição final procurando
"ei Bob" (`perception/speech/wake_word.py`) antes de decidir. Enquanto
`awake` for falso, nada do que for dito chega a `process_turn`/LLM — só a
palavra-chave é checada, de graça, na mesma transcrição que já ia ser feita
de qualquer forma. Ao reconhecer a palavra-chave, o cérebro manda essa
mensagem com `awake: true`, uma saudação fixa (sem LLM) e `set_state:
LISTENING`; depois de alguns segundos sem nova fala, manda `awake: false`
de novo sozinho. O tablet só usa isso pra cor do olho (azul em stand by,
verde claro quando acordado) — não liga/desliga nada no microfone.

```json
{
  "version": 1,
  "type": "wake_state",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {"awake": true}
}
```

### smart_home_action

Legado v1, mantido para que clientes antigos não quebrem. O cérebro atual não
emite esta mensagem: ele chama o Home Assistant local depois do pipeline seguro.

```json
{"version":1,"type":"smart_home_action","device_id":"tablet_antigo","timestamp":1712345678901,"payload":{"request_id":"req_123","action":"turn_on","device_id":"legacy-id","value":null}}
```

### show_transcript

Confirma na interface o texto reconhecido que entrou no cérebro.

```json
{
  "version": 1,
  "type": "show_transcript",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {"text": "Como você está hoje?", "final": true}
}
```

### ping

```json
{
  "version": 1,
  "type": "ping",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "server_time": 1712345678901
  }
}
```

### set_state

```json
{
  "version": 1,
  "type": "set_state",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "state": "LISTENING"
  }
}
```

### set_expression

```json
{
  "version": 1,
  "type": "set_expression",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "expression": "curious",
    "intensity": 0.8,
    "mood": "curious",
    "valence": 0.62,
    "energy": 0.58,
    "irritation": 0.05,
    "curiosity": 0.81
  }
}
```

`expression` e `mood` são rótulos discretos, mantidos por compatibilidade (ex.:
`debug_panel`). `valence`/`energy`/`irritation`/`curiosity` (0.0–1.0) são o vetor
emocional contínuo bruto do `EmotionalState` do backend — o cliente deve preferir
esses campos para desenhar a face (forma/cor do olho variando continuamente) em
vez de mapear `expression` para um template fixo. Clientes antigos podem ignorar
os campos numéricos e continuar usando só `expression`.

### speak

```json
{
  "version": 1,
  "type": "speak",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "mode": "text",
    "text": "Oi João, tudo bem?"
  }
}
```

### stop_speaking

```json
{
  "version": 1,
  "type": "stop_speaking",
  "device_id": "tablet_001",
  "timestamp": 1712345678901
}
```

### camera_config

```json
{
  "version": 1,
  "type": "camera_config",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "mode": "observation",
    "fps": 5,
    "width": 640,
    "height": 480,
    "compression": "jpeg"
  }
}
```

### start_camera

```json
{
  "version": 1,
  "type": "start_camera",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "camera": "front"
  }
}
```

### stop_camera

```json
{
  "version": 1,
  "type": "stop_camera",
  "device_id": "tablet_001",
  "timestamp": 1712345678901
}
```

### capture_image

```json
{
  "version": 1,
  "type": "capture_image",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "camera": "front",
    "count": 1
  }
}
```

### show_message

```json
{
  "version": 1,
  "type": "show_message",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "title": "Robot Online",
    "message": "Conectado ao cérebro"
  }
}
```

### show_scene

Solicita uma cena semântica em tela cheia. Enquanto a cena estiver ativa, o
cliente oculta completamente os olhos e os elementos normais da face. O fundo
é sempre preto e o cliente desenha a animação localmente a partir de seu
catálogo; o cérebro nunca envia código executável ou frames de vídeo.

```json
{
  "version": 1,
  "type": "show_scene",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "kind": "weather",
    "variant": "rain",
    "duration_ms": 10000,
    "persistent": false,
    "data": {"condition": "rain", "temperature": 21}
  }
}
```

Tipos iniciais: `clock`, `date`, `weather` e `music`. Variantes desconhecidas
devem usar o fallback seguro do tipo. Cenas temporárias expiram por
`duration_ms` (o relógio usa 3 segundos); cenas persistentes permanecem até `dismiss_scene` ou até uma
nova cena substituí-las.

Em `clock`, `data` pode conter `time`, `seconds`, `date`, `weekday`, `period`
(`dawn`, `day` ou `night`), `timezone` e, quando disponível, `temperature` e
`location`. O cliente anima o relógio localmente a partir desse instante, sem
consultar o relógio ou o clima por conta própria.

Em previsões, `weather.data` pode trazer `minimum_temperature`,
`maximum_temperature`, `condition`, `precipitation_probability`, `location` e
`period_label`. O renderer escolhe sol, nuvens, chuva ou tempestade pela
condição; temperatura mínima ou máxima não determina o ícone.

### dismiss_scene

Encerra a cena atual e retorna à face. É enviada no início de uma nova
interação para que conteúdo persistente ou antigo não cubra a escuta.

```json
{"version":1,"type":"dismiss_scene","device_id":"tablet_001","timestamp":1712345678901,"payload":{"reason":"new_turn"}}
```

### play_idle_animation

```json
{
  "version": 1,
  "type": "play_idle_animation",
  "device_id": "tablet_001",
  "timestamp": 1712345678901
}
```

Enviada sem provocação do tablet, quando o cérebro decide sozinho (via o laço
de cognição periódico) que o robô vai se entreter por estar ocioso há um
tempo. Sem payload de propósito: o cérebro só decide **quando**; o tablet
decide **o quê** fazer localmente (assobiar, animação de "cobrinha" etc.),
sem custo de rede ou IA adicional.

Também vale notar que `set_state` com `{"state": "SLEEPING"}` agora pode
chegar sem o tablet ter pedido nada, quando o robô fica cansado e ocioso por
tempo suficiente. Qualquer interação real do usuário volta a mandar
`set_state` para `THINKING`/`LISTENING` normalmente, "acordando" o robô.

## Estados visuais do robô

```text
OFFLINE
IDLE
LISTENING
THINKING
ACTING
SPEAKING
ERROR
SLEEPING
```

## Estado mínimo de fala

```text
silence
speech_started
speech
speech_ended
```

## Diretrizes de evolução

- nunca remover campos sem versionar;
- manter compatibilidade com futuras plataformas físicas;
- quando uma nova funcionalidade entrar, adicionar tipo e payload sem quebrar leitura antiga;
- mensagens de controle devem ser pequenas e estáveis;
- dados sensíveis devem ser minimizados e eventuais blobs devem ser transmitidos somente quando necessário.

## Compatibilidade da implementação v0.1

## Streaming PCM incremental (compatível com v1)

O modo novo começa com um envelope JSON `audio_stream_start`:

```json
{
  "version": 1,
  "type": "audio_stream_start",
  "device_id": "tablet_001",
  "timestamp": 1712345678901,
  "payload": {
    "stream_id": "audio_01JXYZ",
    "format": {
      "encoding": "pcm_s16le",
      "sample_rate": 24000,
      "channels": 1,
      "bit_depth": 16,
      "chunk_ms": 50
    }
  }
}
```

Só existe uma sessão de entrada ativa por conexão. Depois do start, frames
WebSocket binários usam o seguinte framing:

```text
offset  tamanho  conteúdo
0       4        ASCII "RBA1"
4       4        sequence uint32 big-endian
8       N        PCM signed 16-bit little-endian
```

O backend mede gaps e duplicatas. Um frame atrasado/duplicado é ignorado; um
gap é registrado e o restante continua. O encerramento usa `audio_stream_end`
com `payload.stream_id`. `audio_stream_cancel` cancela e libera a sessão.

O backend responde com `audio_stream_ready`, `transcript_partial`,
`transcript_final`, `audio_stream_closed` ou `audio_stream_error`. Parcial é
somente observabilidade/UI. Apenas o primeiro `transcript_final` de cada
`stream_id` pode entrar no Robot Brain.

O formato legado `audio_chunk` base64 continua aceito/documentado e o modo
Android SpeechRecognizer permanece disponível por feature flag.

- `audio_chunk` usa PCM16 mono a 16 kHz, enviado diretamente do microfone sem
  arquivos temporários. O receptor deve aceitar variação no tamanho dos frames
  e respeitar os metadados do payload.
- Por compatibilidade com o protótipo inicial, o cliente também aceita
  `type: "expression"` com `value` na raiz ou no payload. Emissores novos devem
  usar `set_expression` e `payload.expression`.
