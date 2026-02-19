# qBittorrent Manager Python

Gerenciamento automatizado do qBittorrent via cron: monitoramento de espaço em disco, pausa/restauração de downloads, seed cleaner com suporte a cross-seed e gerenciamento de downloads por tracker.

---

## Funcionalidades

- **Monitoramento de disco** — pausa downloads quando o espaço cai abaixo do limite mínimo e restaura quando normaliza
- **Seed cleaner** — remove torrents que já cumpriram o tempo mínimo de seeding por tracker, respeitando cross-seeds
- **Force start em checking** — aplica `force_start` automaticamente em torrents em estado `checkingDL/UP/ResumeData`
- **Gerenciamento por tracker** — garante um mínimo de downloads ativos por tracker
- **Histórico em SQLite** — todas as execuções, snapshots de torrents, pausas e deleções registradas no banco
- **Sistema de notificações plugável** — implemente `enviar_notificacao()` com o canal de sua preferência

---

## Requisitos

### Python

```
Python 3.8+
qbittorrent-api
```

### Linux

```bash
# Ubuntu/Debian
sudo apt install python3 python3-pip

pip install qbittorrent-api
```

### Windows

1. Instale o Python em [python.org/downloads](https://www.python.org/downloads/)
   - Marque **"Add Python to PATH"** durante a instalação
2. Abra o terminal (cmd ou PowerShell) e instale a dependência:

```powershell
pip install qbittorrent-api
```

> O SQLite já vem embutido no Python — nenhuma instalação adicional necessária.

---

## Configuração do qBittorrent

Antes de usar o script, ajuste as opções do qBittorrent em **Tools → Options → BitTorrent**:

| Opção | Valor | Motivo |
|---|---|---|
| **Maximum active downloads** | `0` | Desabilita o limite interno — o script assume o controle total dos downloads |

Com `Maximum active downloads > 0`, o qBittorrent pode bloquear ou liberar downloads independentemente do script, causando comportamento inesperado.

> **Tools → Options → BitTorrent → Torrent Queueing → Maximum active downloads → `0`**

---

## Instalação

### Linux

```bash
# 1. Criar diretórios
sudo mkdir -p /etc/qbit-manager
sudo mkdir -p /var/lib/qbit-manager

# 2. Copiar os scripts
sudo cp qbit-manager.py         /usr/local/bin/qbit-manager.py
sudo cp qbit-tracker-list.py    /usr/local/bin/qbit-tracker-list.py
sudo chmod +x /usr/local/bin/qbit-manager.py
sudo chmod +x /usr/local/bin/qbit-tracker-list.py

# 3. Configurar
sudo cp config.py /etc/qbit-manager/config.py
sudo chmod 600 /etc/qbit-manager/config.py   # proteger credenciais

# 4. Editar configurações
sudo nano /etc/qbit-manager/config.py
```

### Windows

```powershell
# 1. Criar diretórios
mkdir C:\qbit-manager\config
mkdir C:\qbit-manager\db

# 2. Copiar arquivos
copy qbit-manager.py         C:\qbit-manager\
copy qbit-tracker-list.py    C:\qbit-manager\
copy config.py               C:\qbit-manager\config\config.py
```

Edite o `config.py` e ajuste o `CONFIG_DIR` no topo de cada script:

```python
CONFIG_DIR = r"C:\qbit-manager\config"
```

---

## Configuração

Edite o `config.py` no diretório de configuração e preencha os valores:

### Conexão com o qBittorrent

```python
QB_URL  = "http://localhost:8080"   # URL do qBittorrent Web UI
QB_USER = "admin"
QB_PASS = "senha"
```

### Banco de dados

```python
DB_DIR  = "/var/lib/qbit-manager"       # Linux
DB_PATH = f"{DB_DIR}/qbit.db"

# Windows:
# DB_DIR  = r"C:\qbit-manager\db"
# DB_PATH = f"{DB_DIR}\\qbit.db"
```

### Discos monitorados

Cada entrada define um grupo de discos com seus limites e papel no sistema:

```python
PATHS = {
    "p2p": {
        "path":          "/mnt/p2p/",   # string única ou lista de paths
        "limite_min":    100,            # GB — pausa downloads abaixo deste valor
        "limite_max":    150,            # GB — retoma downloads acima deste valor
        "seed_cleaner":  True,           # seed cleaner monitora este disco
        "pause_trigger": True            # disco crítico aqui pausa os downloads
    },
    "videos": {
        "path": [                        # múltiplos discos de destino
            "/mnt/videos-1/",
            "/mnt/videos-2/",
        ],
        "limite_min":    200,
        "limite_max":    250,
        "seed_cleaner":  False,          # seed cleaner NÃO monitora (destino Radarr/Sonarr)
        "pause_trigger": True
    },
}
```

**`seed_cleaner: True`** — disco onde os torrents ficam fisicamente (diretório de download do qBittorrent). O seed cleaner só limpa quando este disco estiver crítico.

**`seed_cleaner: False`** — disco de destino (onde o Radarr/Sonarr importa os arquivos). O seed cleaner não age aqui — quando este disco fica crítico o script apenas aguarda o Radarr/Sonarr liberar espaço.

**`pause_trigger: True`** — qualquer disco com esta flag crítico pausa os downloads.

**`path` como lista** — quando há múltiplos discos num grupo, usa o menor espaço livre entre eles (pior caso).

### Gerenciamento de trackers

```python
MIN_DOWNLOADS_PER_TRACKER = 4   # mínimo de downloads ativos simultâneos por tracker
MIN_TORRENTS_PER_TRACKER  = 4   # ignorar tracker com menos torrents que isso
                                 # (exceto se não houver nenhum ativo)
```

### Seed cleaner

```python
SEED_CLEANER_DRY_RUN = True   # True = simula, não apaga nada
                               # False = apaga de verdade
```

As regras de seeding por tracker podem ficar no próprio `config.py` ou num arquivo separado `tracker_rules.py` (tem prioridade):

```python
# config.py ou tracker_rules.py
TRACKER_RULES = {
    "tracker1.example.com":  30,    # deleta após 30 dias de seeding
    "tracker2.example.com":  45,
    "privatehd.example.com": 90,
}
```

**Cross-seed**: se o mesmo torrent existir em múltiplos trackers, só será deletado quando **todos** satisfizerem seu respectivo mínimo de dias.

---

## Gerando a lista de trackers

O script `qbit-tracker-list.py` conecta ao qBittorrent, varre todos os torrents e gera automaticamente o bloco `TRACKER_RULES` pronto para colar no `tracker_rules.py`.

```bash
python3 qbit-tracker-list.py
```

O script lê as credenciais do mesmo `config.py` usado pelo gerenciador principal. Ajuste o `CONFIG_DIR` no topo do arquivo se necessário:

```python
CONFIG_DIR = "/etc/qbit-manager"          # Linux (padrão)
# CONFIG_DIR = r"C:\qbit-manager\config"  # Windows
```

### Saída

```
✅ Configurações carregadas de /etc/qbit-manager/config.py
✅ Conectado ao qBittorrent

📦 Total de torrents: 843

TRACKER                                            TORRENTS
------------------------------------------------------------
tracker1.example.com                                    312
tracker2.example.com                                    289
privatehd.example.com                                   150

============================================================
# Cole em /etc/qbit-manager/tracker_rules.py:
============================================================
TRACKER_RULES = {
    "tracker1.example.com":                      0,  # 312 torrents
    "tracker2.example.com":                      0,  # 289 torrents
    "privatehd.example.com":                     0,  # 150 torrents
}
============================================================

⚠️  Substitua os 0 pelo número de dias mínimos de seeding de cada tracker.
```

Após gerar, edite o `tracker_rules.py` substituindo os `0` pelos dias reais e salve em `/etc/qbit-manager/tracker_rules.py`.

---

## Agendamento

### Linux (cron)

```bash
sudo crontab -e
```

```cron
# Executa a cada 5 em 5 Minutos
*/5 * * * *  root  python3 /usr/local/bin/qbit-manager.py >/dev/null 2>&1
```

### Windows (Agendador de Tarefas)

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **Criar Tarefa Básica**
3. Defina o gatilho como **Diário** e configure a repetição a cada 5 minutos
4. Na ação, configure:
   - **Programa**: `python`
   - **Argumentos**: `C:\qbit-manager\qbit-manager.py`

---

## Notificações

As notificações são implementadas num arquivo separado `notificacao.py`, mantendo o script principal intacto. Copie o arquivo para o diretório de configuração e descomente o canal desejado:

```bash
sudo cp notificacao.py /etc/qbit-manager/notificacao.py
sudo nano /etc/qbit-manager/notificacao.py
```

Se o arquivo não existir, o script imprime as notificações apenas no log (sem envio externo).

A função deve se chamar `enviar_notificacao()` e aceitar os parâmetros:
- `titulo` (str) — título da notificação
- `mensagem` (str) — corpo da mensagem
- `priority` (int) — `0` = informativo, `1` = crítico
- `event_type` (str) — tipo do evento, útil para rotear ou formatar por canal

***O Script principal já possui mensagens criadas para cada tipo de situação***

### Mensagens enviadas

| `event_type` | Título | Mensagem |
|---|---|---|
| `paused` | `Torrents Status` | `Downloads Pausados` |
| `restored` | `Torrents Status` | `Download em andamento` |
| `waiting_paused` | `Downloads Ainda Pausados` | `Verificar sistema.` |

### Eventos notificados

| Evento | Quando |
|---|---|
| `paused` | Downloads pausados por disco crítico — enviado 1x por ocorrência |
| `restored` | Downloads restaurados — sempre enviado |
| `waiting_paused` | Sistema continua pausado — enviado a cada 60 minutos |

---

### Telegram

Crie um bot via [@BotFather](https://t.me/BotFather) e obtenha o `BOT_TOKEN`. Para obter o `CHAT_ID`, envie uma mensagem ao bot e acesse `https://api.telegram.org/bot<TOKEN>/getUpdates`.

```python
def enviar_notificacao(titulo, mensagem, priority=0):
    import requests
    BOT_TOKEN = "123456:ABC-seu-token-aqui"
    CHAT_ID   = "123456789"

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id":    CHAT_ID,
            "text":       f"*{titulo}*\n\n{mensagem}",
            "parse_mode": "Markdown"
        }
    )
```

---

### Discord

Crie um Webhook em **Configurações do Servidor → Integrações → Webhooks**.

```python
def enviar_notificacao(titulo, mensagem, priority=0):
    import requests
    WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"

    # Cor: vermelho para crítico, amarelo para aviso, verde para ok
    cor = {0: 0x2ecc71, 1: 0xe74c3c}.get(priority, 0xf39c12)

    requests.post(WEBHOOK_URL, json={
        "embeds": [{
            "title":       titulo,
            "description": mensagem,
            "color":       cor
        }]
    })
```

---

### Slack

Crie um app em [api.slack.com/apps](https://api.slack.com/apps), ative **Incoming Webhooks** e copie a URL gerada.

```python
def enviar_notificacao(titulo, mensagem, priority=0):
    import requests
    WEBHOOK_URL = "https://hooks.slack.com/services/SEU/WEBHOOK/AQUI"

    requests.post(WEBHOOK_URL, json={
        "text": f"*{titulo}*\n{mensagem}"
    })
```

---

### Ntfy

[Ntfy](https://ntfy.sh) é uma solução self-hosted ou pública, sem necessidade de criar conta para uso básico.

```python
def enviar_notificacao(titulo, mensagem, priority=0):
    import requests
    NTFY_URL   = "https://ntfy.sh/seu-topico-aqui"  # ou seu servidor self-hosted
    PRIORIDADE = {0: "default", 1: "high"}.get(priority, "default")

    requests.post(NTFY_URL, data=mensagem.encode("utf-8"), headers={
        "Title":    titulo,
        "Priority": PRIORIDADE
    })
```

---

### Gotify

[Gotify](https://gotify.net) é uma alternativa self-hosted popular em homelabs.

```python
def enviar_notificacao(titulo, mensagem, priority=0):
    import requests
    GOTIFY_URL   = "https://gotify.seu-servidor.com"
    GOTIFY_TOKEN = "seu-app-token-aqui"

    requests.post(f"{GOTIFY_URL}/message", json={
        "title":    titulo,
        "message":  mensagem,
        "priority": priority
    }, headers={"X-Gotify-Key": GOTIFY_TOKEN})
```

---

### Pushover

```python
def enviar_notificacao(titulo, mensagem, priority=0):
    import requests
    requests.post("https://api.pushover.net/1/messages.json", data={
        "token":    "seu-app-token",
        "user":     "sua-user-key",
        "title":    titulo,
        "message":  mensagem,
        "priority": priority
    })
```

---

## Banco de dados

O banco SQLite é criado automaticamente em `DB_PATH`. Tabelas disponíveis:

```sql
-- Histórico de execuções
SELECT id, started_at, status, checking, moving, paused_count
FROM runs ORDER BY id DESC LIMIT 20;

-- Histórico de pausas e restaurações
SELECT event_at, event_type, reason, discos_criticos, torrents_count
FROM pause_events ORDER BY id DESC LIMIT 20;

-- Estado de um torrent ao longo do tempo
SELECT r.started_at, s.state, s.progress, s.dlspeed
FROM torrent_snapshots s
JOIN runs r ON r.id = s.run_id
WHERE s.hash = 'abc123'
ORDER BY s.id DESC LIMIT 20;

-- Histórico de deleções do seed cleaner
SELECT deleted_at, name, tracker, seeding_days, rule_days,
       round(size_bytes/1073741824.0, 2) as size_gb, dry_run
FROM seed_deletions ORDER BY id DESC LIMIT 20;

-- Histórico de notificações
SELECT sent_at, event_type, title
FROM notifications ORDER BY id DESC LIMIT 20;
```

---

## Estrutura de arquivos

```
/etc/qbit-manager/
├── config.py             # credenciais e configurações
├── notificacao.py        # implementação do canal de notificação
└── tracker_rules.py      # regras de seeding por tracker (opcional)

/var/lib/qbit-manager/
└── qbit.db               # banco SQLite (criado automaticamente)

/usr/local/bin/
├── qbit-manager.py       # script principal
└── qbit-tracker-list.py  # gerador da lista de trackers
```

