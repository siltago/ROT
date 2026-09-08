# Casa inteligente local com Home Assistant

O Robot Brain usa o Home Assistant como hub universal local. Não há Google
Cloud, OAuth do Google ou segredo armazenado no tablet/ESP32.

## Onde cada parte roda

- **Home Assistant:** PC, máquina virtual, Raspberry Pi ou mini-PC sempre ligado.
- **Robot Brain:** PC central do robô; chama a API local do Home Assistant.
- **Tablet:** câmera, microfone, rosto e áudio; não recebe o token da casa.
- **ESP32:** hardware do robô ou dispositivo integrado via ESPHome/MQTT. Ele não
  tem recursos para hospedar o Home Assistant completo.

## Configuração sem assinatura

1. Instale o Home Assistant OS em uma VM ou computador da rede.
2. Adicione suas integrações e confirme que os dispositivos aparecem como
   entidades (`light.*`, `switch.*`, `climate.*`, `fan.*`, etc.).
3. No perfil do usuário do Home Assistant, crie um token de longa duração.
4. Copie `.env.example` para `.env` e preencha:

```env
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=cole_o_token_aqui
HOME_ASSISTANT_TIMEOUT=4
```

5. Reinicie o Robot Brain. Na inicialização ele consulta `/api/states` e
   normaliza luzes, interruptores, climatização, mídia, ventiladores, cortinas,
   fechaduras, sensores e aspiradores.

## Segurança e funcionamento

O token deve pertencer a um usuário dedicado com o menor acesso possível. Não
o versione, não o coloque no Flutter e não o grave no firmware do ESP32.
Comandos continuam obrigados a passar por DecisionEngine, Planner,
PermissionPolicy e ActionExecutor. O provider só executa uma ação já validada.

O funcionamento totalmente offline depende da integração do aparelho. Matter,
Zigbee, ESPHome e integrações LAN podem ser locais; alguns fabricantes ainda
dependem da nuvem própria, mesmo sem Google Cloud.

