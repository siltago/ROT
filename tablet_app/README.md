# Robot Tablet App

Cliente Flutter/Android que fornece câmera, microfone, alto-falante e rosto
visual ao Robot Brain. Personalidade, memória, decisões e ações continuam no
backend.

## Recursos da v0.1

- preview da câmera frontal e captura manual de frame JPEG;
- microfone PCM16 mono a 16 kHz, nível RMS e VAD básico;
- eventos `speech_started`, `audio_chunk` e `speech_ended`;
- WebSocket, reconexão automática com backoff e URL configurável;
- comandos `set_state`, `set_expression`, `speak`, `stop_speaking` e `ping`;
- rastreamento local de rosto pela câmera frontal para orientar a face animada;
- resposta em texto e voz usando o TTS do Android;
- TTS `pt-BR`, rosto minimalista animado e painel de diagnóstico;
- Android landscape, fullscreen e tela sempre ligada.

## Preparar e rodar

Instale Flutter 3.22 ou mais recente e o Android Studio/SDK. Na primeira vez,
gere/atualize os arquivos auxiliares Android, incluindo o Gradle wrapper:

```bash
cd tablet_app
flutter create --platforms=android .
flutter pub get
flutter doctor
flutter devices
flutter run
```

Para gerar um APK:

```bash
flutter build apk --release
```

O APK fica em `build/app/outputs/flutter-apk/app-release.apk`.

## Configurar a conexão

Abra o painel pelo ícone de diagnóstico ou pressionando o rosto. Toque na
engrenagem e informe, por exemplo:

```text
ws://192.168.1.10:8000/ws/device
```

Use o IP LAN do computador que executa o Robot Brain. `10.0.2.2` é o padrão
para acessar o host a partir do emulador Android. A URL é persistida localmente.
O Android permite `ws://` nesta versão para desenvolvimento local; em produção,
use `wss://` e autenticação.

## Validar

```bash
flutter analyze
flutter test
```

Antes de abrir o app, inicie o gateway na raiz do repositório:

```powershell
.venv\Scripts\python.exe -m api.server
```

O app reconhece fala em português no Android e envia a transcrição final ao
Robot Brain. A tela principal mostra a expressão recebida sem exibir a prévia
da câmera ou a caixa de transcrição. O serviço de
reconhecimento disponível no tablet pode depender dos componentes de voz do
Google/Samsung e, conforme a configuração do Android, de internet.
