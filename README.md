# ROT

Robot Brain / Robot Tablet para um robô social e inteligente, com arquitetura modular
separando cérebro, percepção e hardware físico.

## Visão geral

Este projeto reúne:

- o cérebro do robô (personalidade, emoção, memória, decisão e ações);
- o tablet como corpo provisório de percepção e presença;
- a comunicação por protocolo versionado com WebSocket;
- a preparação para futuramente trocar o tablet por câmera, microfone, speaker,
  ESP32 e outros hardwares sem quebrar a lógica do cérebro.

## Requisitos

- Python 3.11+
- Flutter SDK para a app de tablet Android

## Instalação do cérebro

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Unix
source .venv/bin/activate

pip install -e ".[dev]"
```

Copie `.env.example` para `.env` se quiser customizar configurações.

## Rodar a CLI do Robot Brain

```bash
python -m app.main
```

## Rodar o cérebro para o tablet

Com o Ollama aberto e o modelo configurado disponível:

```bash
# Windows
.venv\Scripts\python.exe -m api.server
# Unix
.venv/bin/python -m api.server
```

O tablet se conecta a `ws://IP_DO_COMPUTADOR:8000/ws/device`. Nesta fase, o
Android reconhece a fala, o Robot Brain/Ollama produz a resposta e o tablet a
exibe em texto junto com a expressão correspondente.

## Rodar os testes

```bash
python -m pytest -q
```

## Tablet do robô

A base da app Android/Flutter está em [tablet_app/README.md](tablet_app/README.md).
A arquitetura do corpo do robô foi documentada em [ARCHITECTURE.md](ARCHITECTURE.md)
e o protocolo foi documentado em [PROTOCOL.md](PROTOCOL.md).

A ideia principal é manter o tablet como cliente do Robot Brain e não como o cérebro em si.

## Estrutura principal

```
app/            configuração e ponto de entrada (CLI)
brain/          modelos, decision engine, planner, context builder,
                response engine, orquestrador (agent.py)
personality/    traços de personalidade estáveis
emotions/       estado emocional, eventos, decaimento
memory/         memória de curto/longo prazo e perfis de pessoas
perception/     interfaces de voz/visão/identidade
actions/        ações e execução controlada
hardware/       abstração de hardware + simulador
integrations/   integrações e LLMs
api/            API e comunicação externa
tablet_app/     app Android/Flutter para câmera, microfone, fala e display
data/           dados persistidos localmente
tests/          testes automatizados
```

Detalhes maiores estão em [PROJECT.md](PROJECT.md) e [AGENTS.md](AGENTS.md).
