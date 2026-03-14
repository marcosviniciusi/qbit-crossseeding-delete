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
- **OpenTelemetry (OTEL)** — logs estruturados enviados via OTLP/HTTP para qualquer collector

---

## Como funciona

```
Disco crítico? (espaço livre <= limite_min)
  │
  ├── SIM → executa seed cleaner (limpeza)
  │          ├── Resolveu? → sistema ativo → gerenciar trackers
  │          └── Não resolveu? → pausa downloads → notifica
  │
  └── NÃO → sistema ativo → gerenciar trackers

Se já estava pausado na execução anterior:
  │
  ├── Todos discos OK (>= limite_max) E checking/moving = 0?
  │     → restaura downloads → notifica → gerenciar trackers
  │
  └── Ainda não OK?
        ├── Disco p2p crítico? → tenta seed cleaner → reavalia
        ├── Disco destino crítico? → aguarda Radarr/Sonarr
        └── Disco OK mas checking/moving ativo? → aguarda
```

---

## Estrutura do projeto

O script é dividido em módulos independentes:

```
qbit-manager-python/            ← repositório (código fonte)
├── qbit-manager.py              ← entry point (config + conexão + chamada ao orquestrador)
├── modulos/
│   ├── __init__.py
│   ├── checagem_disco.py        ← orquestrador: verifica disco → chama limpeza → chama ativação
│   ├── limpeza.py               ← seed cleaner (cross-seed aware, dry_run)
│   ├── ativacao.py              ← pausa/restauração de downloads + gerenciamento de trackers
│   ├── db.py                    ← operações SQLite (init, CRUD, queries de estado)
│   ├── helpers.py               ← utilitários (verificar espaço, extrair tracker, notificações)
│   └── otel.py                  ← integração OpenTelemetry (logs via OTLP/HTTP)
├── config.py                    ← template de configuração
├── notificacao.py               ← template de notificações (6 canais de exemplo)
├── qbit-traker-list.py          ← utilitário: gera lista de trackers do qBittorrent
└── readme.md
```

### Fluxo de chamadas entre módulos

```
qbit-manager.py (entry point)
  └── checagem_disco.executar_checagem()         ← orquestrador
        ├── helpers.verificar_espacos()           ← checa disco
        ├── limpeza.executar_seed_cleaner()        ← chamado quando disco crítico
        ├── ativacao.executar_pausa()              ← chamado quando precisa pausar
        ├── ativacao.executar_restauracao()         ← chamado quando pode restaurar
        ├── ativacao.gerenciar_trackers()           ← chamado quando sistema ativo
        └── otel.log_*()                           ← logs enviados ao OTEL em cada etapa
```

---

## Requisitos

```
Python 3.8+
qbittorrent-api
requests
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
2. Instale a dependência:

```powershell
pip install qbittorrent-api
```

> O SQLite e o `requests` já vêm embutidos/instalados com o Python.

---

## Configuração do qBittorrent

Antes de usar o script, ajuste as opções do qBittorrent em **Tools → Options → BitTorrent**:

| Opção | Valor | Motivo |
|---|---|---|
| **Maximum active downloads** | `0` | Desabilita o limite interno — o script assume o controle total dos downloads |

> **Tools → Options → BitTorrent → Torrent Queueing → Maximum active downloads → `0`**

---

## Instalação

### Linux — Passo a passo

O sistema usa dois diretórios separados: um para os **scripts** e outro para a **configuração**.

#### 1. Instalar dependências

```bash
sudo apt install python3 python3-pip
pip install qbittorrent-api
```

#### 2. Criar diretórios

```bash
# Diretório de configuração (credenciais, regras, notificações)
sudo mkdir -p /etc/qbit-manager

# Diretório do banco de dados (criado automaticamente, mas bom garantir)
sudo mkdir -p /var/lib/qbit-manager

# Diretório dos scripts + módulos
sudo mkdir -p /usr/local/lib/qbit-manager/modulos
```

#### 3. Copiar os scripts e módulos

```bash
# Script principal (entry point)
sudo cp qbit-manager.py /usr/local/lib/qbit-manager/qbit-manager.py

# Módulos internos
sudo cp modulos/__init__.py        /usr/local/lib/qbit-manager/modulos/__init__.py
sudo cp modulos/db.py              /usr/local/lib/qbit-manager/modulos/db.py
sudo cp modulos/helpers.py         /usr/local/lib/qbit-manager/modulos/helpers.py
sudo cp modulos/otel.py            /usr/local/lib/qbit-manager/modulos/otel.py
sudo cp modulos/limpeza.py         /usr/local/lib/qbit-manager/modulos/limpeza.py
sudo cp modulos/ativacao.py        /usr/local/lib/qbit-manager/modulos/ativacao.py
sudo cp modulos/checagem_disco.py  /usr/local/lib/qbit-manager/modulos/checagem_disco.py

# Utilitário de lista de trackers
sudo cp qbit-traker-list.py /usr/local/lib/qbit-manager/qbit-traker-list.py

# Tornar executável
sudo chmod +x /usr/local/lib/qbit-manager/qbit-manager.py
```

#### 4. Criar link simbólico (atalho para rodar de qualquer lugar)

```bash
sudo ln -sf /usr/local/lib/qbit-manager/qbit-manager.py /usr/local/bin/qbit-manager
sudo ln -sf /usr/local/lib/qbit-manager/qbit-traker-list.py /usr/local/bin/qbit-traker-list
```

#### 5. Copiar e editar configuração

```bash
# Copiar template de configuração
sudo cp config.py /etc/qbit-manager/config.py

# Proteger credenciais
sudo chmod 600 /etc/qbit-manager/config.py

# Editar com seus dados reais
sudo nano /etc/qbit-manager/config.py
```

#### 6. (Opcional) Configurar notificações

```bash
sudo cp notificacao.py /etc/qbit-manager/notificacao.py
sudo nano /etc/qbit-manager/notificacao.py
# Descomente o canal desejado (Telegram, Discord, etc.)
```

#### 7. Agendar no cron

```bash
sudo crontab -e
```

Adicione:

```cron
# Executa a cada 5 minutos
*/5 * * * * python3 /usr/local/lib/qbit-manager/qbit-manager.py >/dev/null 2>&1
```

#### Resultado final no Linux

```
/usr/local/lib/qbit-manager/         ← scripts + módulos
├── qbit-manager.py                   ← entry point (executado pelo cron)
├── modulos/
│   ├── __init__.py
│   ├── checagem_disco.py
│   ├── limpeza.py
│   ├── ativacao.py
│   ├── db.py
│   ├── helpers.py
│   └── otel.py
└── qbit-traker-list.py

/etc/qbit-manager/                   ← configuração (editável pelo usuário)
├── config.py                         ← credenciais, discos, regras
├── notificacao.py                    ← canal de notificação (opcional)
└── tracker_rules.py                  ← regras de seeding por tracker (opcional)

/var/lib/qbit-manager/               ← dados (criado automaticamente)
└── qbit.db                           ← banco SQLite

/usr/local/bin/                      ← atalhos (links simbólicos)
├── qbit-manager → /usr/local/lib/qbit-manager/qbit-manager.py
└── qbit-traker-list → /usr/local/lib/qbit-manager/qbit-traker-list.py
```

### Windows

```powershell
# 1. Criar diretórios
mkdir C:\qbit-manager
mkdir C:\qbit-manager\modulos
mkdir C:\qbit-manager\config
mkdir C:\qbit-manager\db

# 2. Copiar scripts e módulos
copy qbit-manager.py           C:\qbit-manager\
copy modulos\*.py               C:\qbit-manager\modulos\

# 3. Copiar configuração
copy config.py                  C:\qbit-manager\config\config.py
copy notificacao.py             C:\qbit-manager\config\notificacao.py
```

Edite o `CONFIG_DIR` no topo do `qbit-manager.py`:

```python
CONFIG_DIR = r"C:\qbit-manager\config"
```

E no `config.py`:

```python
DB_DIR  = r"C:\qbit-manager\db"
DB_PATH = f"{DB_DIR}\\qbit.db"
```

#### Agendador de Tarefas (Windows)

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **Criar Tarefa Básica**
3. Defina o gatilho como **Diário** e configure a repetição a cada 5 minutos
4. Na ação, configure:
   - **Programa**: `python`
   - **Argumentos**: `C:\qbit-manager\qbit-manager.py`

---

## Configuração

Edite o `config.py` no diretório de configuração (`/etc/qbit-manager/config.py`).

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

### OpenTelemetry (opcional)

Para enviar logs estruturados a um OTEL Collector, adicione ao `config.py`:

```python
OTEL_ENDPOINT     = "http://localhost:4318"   # endpoint OTLP/HTTP do collector
OTEL_SERVICE_NAME = "qbit-manager"            # nome do serviço nos logs
OTEL_ENABLED      = True                      # ativar envio
```

Se não configurar, o sistema funciona normalmente sem OTEL — os logs vão apenas para o console.

---

## Gerando a lista de trackers

O script `qbit-traker-list.py` conecta ao qBittorrent, varre todos os torrents e gera automaticamente o bloco `TRACKER_RULES` pronto para colar no `tracker_rules.py`.

```bash
python3 /usr/local/lib/qbit-manager/qbit-traker-list.py
# ou, se criou o link simbólico:
qbit-traker-list
```

O script lê as credenciais do mesmo `config.py` usado pelo gerenciador principal.

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

### Mensagens enviadas

| `event_type` | Título | Mensagem | Quando |
|---|---|---|---|
| `paused` | `Torrents Status` | `Downloads Pausados` | 1x por ocorrência |
| `restored` | `Torrents Status` | `Download em andamento` | Sempre |
| `waiting_paused` | `Downloads Ainda Pausados` | `Verificar sistema.` | A cada 60 min |

---

### Telegram

Crie um bot via [@BotFather](https://t.me/BotFather) e obtenha o `BOT_TOKEN`. Para obter o `CHAT_ID`, envie uma mensagem ao bot e acesse `https://api.telegram.org/bot<TOKEN>/getUpdates`.

```python
def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
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
def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
    import requests
    WEBHOOK_URL = "https://discord.com/api/webhooks/SEU_WEBHOOK_AQUI"

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
def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
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
def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
    import requests
    NTFY_URL   = "https://ntfy.sh/seu-topico-aqui"
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
def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
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
def enviar_notificacao(titulo, mensagem, priority=0, event_type=None):
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
