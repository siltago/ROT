# Pipeline de áudio conversacional

## Baseline auditado

O fluxo usado pela tela principal ainda é `speech_to_text`/Android
`SpeechRecognizer`: ele fornece transcrição parcial/final e um nível de som
normalizado. Um resultado parcial sem mudanças é confirmado por um timer de
2,8 s. Durante o TTS, o reconhecedor é desligado. Esse caminho não fornece PCM
ao backend e, portanto, não oferece pre-roll, barge-in ou AEC verificável.

Existe também `MicrophoneService`, até agora não conectado ao controlador da
conversa. Ele captura PCM16, mono, 16 kHz em memória com `record`, solicitando
AGC, AEC e NS ao Android. O plugin não expõe disponibilidade, estado efetivo ou
audio session id. O VAD anterior comparava somente RMS com o threshold fixo
0,08 e encerrava após 650 ms.

Não há WAV temporário. `audio_chunk` v1 usa PCM em base64/JSON, mas não é usado
pelo fluxo principal. O WebSocket aceita apenas JSON e o backend processa hoje
`recognized_speech` final. O TTS atual recebe texto completo.

## Fundação implementada

`audio_pipeline.dart` centraliza formato, janelas e limites. Ele contém:

- estimador adaptativo de noise floor, com subida lenta e congelamento em fala;
- VAD híbrido inicial baseado em energia relativa ao ambiente e probabilidade;
- estados `silence`, `maybeSpeech` e `speech`;
- máquina explícita `idle -> preSpeech -> listening -> maybeEnd -> endOfTurn`;
- confirmação de início, tolerância a pausas e post-roll;
- buffer circular de pre-roll;
- métricas RMS, dBFS, threshold dinâmico, probabilidade e estado de turno.

Essa camada não depende de OpenAI nem do backend. O VAD de energia adaptativa é
uma fundação/fallback, não é apresentado como substituto definitivo de WebRTC
VAD. Testes com gravações reais devem decidir entre VAD WebRTC e uma ponte
nativa mais simples.

## Configuração recomendada para teste

| Parâmetro | Valor |
|---|---:|
| Sample rate | 16 kHz |
| Formato | PCM16 mono |
| Chunk | 50 ms / 1600 bytes |
| Probabilidade de fala | 0,68 |
| Margem sobre noise floor | 8 dB |
| Confirmação de início | 100 ms |
| Silêncio de fim | 800 ms |
| Pre-roll | 500 ms |
| Post-roll | 200 ms |
| Confirmação de barge-in | 200 ms |

## Próximas etapas sem quebrar o protótipo

## Milestone PCM para STT streaming

O caminho novo é ativado no build com:

```text
--dart-define=AUDIO_INPUT_MODE=pcmStreaming
```

Sem a flag, o padrão seguro continua `androidSpeechRecognizer`. O PCM streaming
usa 24 kHz, mono, signed 16-bit little-endian e chunks de 50 ms. A alteração de
16 para 24 kHz é necessária porque a transcrição Realtime escolhida aceita PCM
nesse sample rate; o caminho Android permanece independente.

O tablet aplica VAD/turn detection local, inclui 500 ms de pre-roll, mantém
200 ms de post-roll e envia binários com sequência e fila limitada a 80 chunks
(4 segundos). Ao exceder o limite, descarta o chunk mais antigo e incrementa a
métrica de dropped chunks.

O backend usa `SpeechToTextProvider`/`SttSession`. A implementação inicial
`OpenAIRealtimeSttProvider` usa `gpt-live-transcribe`; API key e modelo existem
somente no backend. Transcripts parciais atualizam UI/debug e nunca acionam o
cérebro. O primeiro final por stream é idempotente e entra no mesmo
`TabletBrainBridge` usado pelo caminho legado.

Erros de início/finalização retornam `audio_stream_error` e provocam fallback
explícito no tablet, com a causa visível no painel. O timer legado de 2,8 s só
existe no modo Android e não participa do modo PCM.

1. Conectar uma única captura PCM ao controlador da conversa e remover a disputa
   potencial entre `AudioRecord` e `SpeechRecognizer`.
2. Adicionar STT de streaming no backend antes de tornar PCM o caminho padrão.
3. Evoluir o WebSocket retrocompatível para frames binários com `stream_id` e
   sequência, mantendo `audio_chunk` v1 como fallback.
4. Expor AEC/AGC/NS e session id por Kotlin; validar no SM-P615.
5. Implementar fila/cancelamento de saída, IDs de resposta e barge-in.
6. Habilitar microfone durante TTS e medir eco, falsos positivos e latência.

WebRTC Audio Processing não será introduzido antes dessas medições. APIs nativas
têm menor complexidade e consumo; WebRTC é candidato caso o DSP do dispositivo
não entregue AEC suficiente para barge-in.
