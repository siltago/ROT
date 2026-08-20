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

## Mensagens do cérebro para o tablet

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
    "intensity": 0.8
  }
}
```

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
