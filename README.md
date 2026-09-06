# ROT

Robot Brain / Robot Tablet para um robô social e inteligente, com arquitetura modular
separando cérebro, percepção e hardware físico.

## Visão geral

Este projeto reúne:

- o cérebro do robô (personalidade, emoção, memória, decisão e ações);
- o tablet como corpo provisório de percepção e presença;
- a comunicação por protocolo versionado com WebSocket;
- personalidade consistente, emoção temporária, ações estruturadas e iniciativa
  limitada baseada em propostas seguras;
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

Para hora correta na nuvem e previsão do tempo, configure no `.env`:

```dotenv
ROBOT_LOCATION_NAME=Sua cidade
ROBOT_LATITUDE=-00.0000
ROBOT_LONGITUDE=-00.0000
ROBOT_TIMEZONE=America/Sao_Paulo
```

Sem latitude e longitude, Bob pede que a localização seja configurada em vez
de inventar temperatura. Também é possível dizer “Eu moro em Campinas, SP” ou
responder apenas “Campinas” quando ele perguntar a cidade; a localização
resolvida fica salva para as próximas execuções. A previsão usa Open-Meteo e
não exige chave de API.

## Rodar a CLI do Robot Brain

```bash
python -m app.main
```

## Rodar o cérebro para o tablet

Com `OPENAI_API_KEY` preenchida no arquivo `.env`:

```bash
# Windows
.venv\Scripts\python.exe -m api.server
# Unix
.venv/bin/python -m api.server
```

O tablet se conecta a `ws://IP_DO_COMPUTADOR:8000/ws/device`. Nesta fase, o
Android reconhece a fala, o Robot Brain/OpenAI produz a resposta e o tablet a
exibe em texto junto com a expressão correspondente.

## Rodar na nuvem (Oracle Cloud, grátis)

Pra o cérebro ficar no ar sozinho, acessível de qualquer rede com internet
(sem depender do PC ligado nem de USB — o tablet já se conecta por WiFi
normalmente, USB só é usado pra instalar builds do app), o caminho
recomendado é uma instância **Always Free** da Oracle Cloud (genuinamente
gratuita, não é trial) rodando os containers deste repositório.

1. Crie a instância (shape "Always Free" — Ampere A1 ou o Micro AMD) com
   Ubuntu na Oracle Cloud, e abra as portas 80 e 443 na security list da
   VCN e no firewall da própria instância (`ufw allow 80,443/tcp` ou
   equivalente).
2. Registre um subdomínio grátis apontando pro IP público da instância —
   por exemplo em [duckdns.org](https://www.duckdns.org) — porque emitir
   certificado TLS (obrigatório fora de uma LAN) exige um domínio, não um
   IP nu.
3. Na instância: instale Docker e Docker Compose, clone este repositório,
   copie `.env.example` para `.env` e preencha os valores reais
   (`OPENAI_API_KEY`, `OPENAI_MODEL`, `PIPER_ENABLED=true` + as variáveis
   de tuning de voz que quiser, `ROBOT_API_HOST=0.0.0.0`,
   `ROBOT_API_PORT=8000`) — esse `.env` nunca é commitado.
4. Edite o `Caddyfile` na raiz, trocando `seunome.duckdns.org` pelo
   domínio que você registrou.
5. Suba tudo:

   ```bash
   docker compose up -d --build
   ```

   O serviço `brain` roda o cérebro (`restart: always` — sobrevive a
   reboot da VM e a crash do processo) com `./data/state`,
   `./data/memories` e `./data/people` montados do host, então a memória
   do robô sobrevive a rebuilds. O serviço `caddy` faz proxy reverso e
   emite/renova o certificado TLS sozinho, já resolvendo `wss://`.

6. Confirme de fora da rede de casa: `curl -I
   https://seudominio.duckdns.org/health` deve responder `200`.
7. Na tela de Settings do tablet, troque a URL do cérebro para
   `wss://seudominio.duckdns.org/ws/device`.

Pra atualizar depois de mudanças no código: `git pull && docker compose up
-d --build`.

**Limitação atual:** a integração com Home Assistant (`HOME_ASSISTANT_URL`
em `.env.example`) espera um host só alcançável na LAN de casa
(`homeassistant.local`). Ela não está ativa por padrão, mas se for ligada
com o cérebro fora de casa, vai precisar de acesso remoto ao Home Assistant
(Nabu Casa, ou um túnel tipo Tailscale entre a VPS e a rede de casa).

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

## Personalidade do Bob

Respostas da OpenAI e fallbacks locais compartilham o mesmo contrato verbal:
curioso, afetuoso, compacto, levemente travesso e sem tom de atendimento. O
humor altera a intensidade da fala, mas preserva essa identidade estável.
# Cognition v0.2

Eventos de pessoa, fala, clima, tempo, idle, dispositivos e ações agora podem
alimentar o mesmo pipeline contextual. Para simular em desenvolvimento, defina
`DEBUG_EVENTS_ENABLED=true` e use `POST /debug/events`. Consulte
`COGNITION_V02.md` para eventos, proteções de iniciativa, métricas e exemplos.

## Casa inteligente

O cérebro integra diretamente com um Home Assistant na rede local. Ele descobre
entidades de várias categorias e envia comandos pela API REST, mantendo o token
somente no backend. Não há Google Cloud nem credencial de casa no tablet ou no
ESP32. Consulte `HOME_ASSISTANT_SETUP.md`; sem URL/token, o sistema falha de
forma explícita e nunca informa sucesso falso.
