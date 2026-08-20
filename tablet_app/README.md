# Robot Tablet App

Este diretório contém a base do app para tablet Android que atua como presença e interface do Robot Brain.

## Objetivo

O tablet não é o cérebro. Ele é o cliente responsável por:

- câmera;
- microfone;
- alto-falante;
- tela de rosto;
- sensores de movimento;
- conexão persistente com o Robot Brain.

## Stack inicial

- Flutter
- WebSocket
- camera plugin
- microphone plugin
- flutter_tts
- sensors_plus

## Como rodar

1. Instale o Flutter SDK.
2. Entre nesta pasta.
3. Execute:

```bash
flutter pub get
flutter run
```

## Estrutura

```text
lib/
├── app/
├── core/
├── devices/
├── robot/
├── ui/
├── main.dart
└──
```

## Observação

A estrutura foi pensada para evoluir para hardware real no futuro sem alterar o protocolo do cérebro.
