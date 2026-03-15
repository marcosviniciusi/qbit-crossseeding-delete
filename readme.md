# qBittorrent Manager Python

Gerenciamento automatizado do qBittorrent via cron: monitoramento de espaço em disco, pausa/restauração de downloads, seed cleaner com suporte a cross-seed e gerenciamento de downloads por tracker.

---

## Funcionalidades

- **Monitoramento de disco** — pausa downloads quando o espaço cai abaixo do limite mínimo e restaura quando normaliza
- **Seed cleaner** — remove torrents que já cumpriram o tempo mínimo de seeding por tracker, respeitando cross-seeds
- **Force start em checking** — aplica `force_start` automaticamente em torrents em estado `checkingDL/UP/ResumeData`
- **Gerenciamento por tracker** — garante um mínimo de downloads ativos por tracker
- **Histórico em SQLite** — todas as execuções, snapshots de torrents, pausas e deleções registradas no banco
- **Notificações configuráveis** — Telegram, Discord, Slack, Ntfy, Gotify ou Pushover (tudo via `config.py`)
- **OpenTelemetry (OTEL)** — logs estruturados enviados via OTLP/HTTP para qualquer collector

---

## Uso

```bash
# Execução normal (cron)
python3 qbit-manager.py

# Verificar espaço em disco (sem executar ações)
python3 qbit-manager.py --check-disk

# Listar torrents elegíveis para remoção (dry run)
python3 qbit-manager.py --check-torrent

# Executar seed cleaner (respeita tempo de seed e cross-seed)
python3 qbit-manager.py --erase-torrent

# Gerar bloco TRACKER_RULES a partir dos torrents atuais
python3 qbit-manager.py --tracker-list

# Testar envio de notificação
python3 qbit-manager.py --test-notification

# Testar envio de log ao OTEL Collector
python3 qbit-manager.py --check-send-log

# Validar se a configuração está correta
python3 qbit-manager.py --check-config
```

### Flags globais

```bash
# Usar diretório de configuração diferente do padrão
python3 qbit-manager.py --config /caminho/para/config

# Usar diretório de módulos diferente do INSTALL_DIR
python3 qbit-manager.py --modules /caminho/para/modulos

# Combinar: config custom + verificar disco
python3 qbit-manager.py --config /home/user/meu-config --check-disk
```

| Flag | Padrão | O que faz |
|---|---|---|
| `--config PATH` | `/etc/qbit-manager` | Diretório onde fica o `config.py` |
| `--modules PATH` | `INSTALL_DIR` do config | Diretório onde ficam os scripts + `modulos/` |

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

## Diretórios — onde cada coisa fica

O sistema usa **3 diretórios** separados, cada um com uma função. Todos são configuráveis via `config.py`:

| Variável | Caminho padrão | O que fica aqui |
|---|---|---|
| `INSTALL_DIR` | `/usr/local/lib/qbit-manager` | Scripts + pasta `modulos/` (código do programa) |
| `CONFIG_DIR`* | `/etc/qbit-manager` | `config.py`, `tracker_rules.py` (suas configs) |
| `DB_DIR` | `/var/lib/qbit-manager` | `qbit.db` (banco SQLite, criado automaticamente) |

> *`CONFIG_DIR` é definido no topo do `qbit-manager.py` (não no config.py, pois o config.py fica dentro dele).

```
INSTALL_DIR (/usr/local/lib/qbit-manager/)    ← código do programa
├── qbit-manager.py                            ← entry point (o que o cron executa)
├── modulos/                                   ← módulos internos (DEVEM estar junto do script)
│   ├── __init__.py
│   ├── checagem_disco.py                      ← orquestrador (disco → limpeza → ativação)
│   ├── limpeza.py                             ← seed cleaner
│   ├── ativacao.py                            ← pausa/restauração + gerenciamento de trackers
│   ├── db.py                                  ← operações SQLite
│   ├── helpers.py                             ← utilitários compartilhados
│   ├── notificacao.py                         ← sistema de notificações (despacha por tipo do config)
│   ├── otel.py                                ← integração OpenTelemetry (buffer + flush)
│   └── tracker_list.py                        ← gerador de lista de trackers

CONFIG_DIR (/etc/qbit-manager/)               ← configuração do usuário
├── config.py                                  ← credenciais, discos, notificações, INSTALL_DIR
└── tracker_rules.py                           ← regras de seeding por tracker (opcional)

DB_DIR (/var/lib/qbit-manager/)               ← dados persistentes
└── qbit.db                                    ← banco SQLite (criado automaticamente)
```

**Importante:** a pasta `modulos/` **deve estar dentro do `INSTALL_DIR`**, no mesmo diretório do `qbit-manager.py`. O script usa `INSTALL_DIR` do `config.py` para encontrar os módulos. Se você instalar em outro lugar que não o padrão, basta alterar `INSTALL_DIR` no `config.py`.

### Fluxo de chamadas entre módulos

```
qbit-manager.py (entry point)
  └── checagem_disco.executar_checagem()         ← orquestrador
        ├── helpers.verificar_espacos()           ← checa disco
        ├── limpeza.executar_seed_cleaner()        ← chamado quando disco crítico
        ├── ativacao.executar_pausa()              ← chamado quando precisa pausar
        ├── ativacao.executar_restauracao()         ← chamado quando pode restaurar
        ├── ativacao.gerenciar_trackers()           ← chamado quando sistema ativo
        ├── otel.log_*()                           ← acumula logs no buffer
        └── otel.flush()                           ← envia tudo pro OTEL em bloco unico
```

---

## Requisitos

```
Python 3.8+
qbittorrent-api
```

> O SQLite e o `requests` já vêm incluídos no Python.

---

## Configuração do qBittorrent

Antes de usar o script, ajuste as opções do qBittorrent em **Tools → Options → BitTorrent**:

| Opção | Valor | Motivo |
|---|---|---|
| **Maximum active downloads** | `0` | Desabilita o limite interno — o script assume o controle total dos downloads |

> **Tools → Options → BitTorrent → Torrent Queueing → Maximum active downloads → `0`**

---

## Instalação — Linux

### 1. Instalar dependências

```bash
sudo apt install python3 python3-pip    # Ubuntu/Debian
pip install qbittorrent-api
```

### 2. Criar os 3 diretórios

```bash
# INSTALL_DIR — onde ficam os scripts e módulos
sudo mkdir -p /usr/local/lib/qbit-manager/modulos

# CONFIG_DIR — onde fica a configuração do usuário
sudo mkdir -p /etc/qbit-manager

# DB_DIR — onde fica o banco de dados (criado automaticamente, mas garantir permissão)
sudo mkdir -p /var/lib/qbit-manager
```

### 3. Copiar scripts + módulos para INSTALL_DIR

```bash
# Script principal
sudo cp qbit-manager.py /usr/local/lib/qbit-manager/
sudo chmod +x /usr/local/lib/qbit-manager/qbit-manager.py

# Módulos internos (DEVEM ficar dentro de INSTALL_DIR/modulos/)
sudo cp modulos/*.py /usr/local/lib/qbit-manager/modulos/
```

### 4. Copiar configuração para CONFIG_DIR

```bash
# Template de configuração — edite com seus dados reais
sudo cp config.py /etc/qbit-manager/config.py
sudo chmod 600 /etc/qbit-manager/config.py    # proteger credenciais
sudo nano /etc/qbit-manager/config.py
```

### 5. Verificar o INSTALL_DIR no config.py

Abra `/etc/qbit-manager/config.py` e confirme que `INSTALL_DIR` aponta para onde você colocou os scripts:

```python
# Se instalou no local padrão, não precisa mudar nada:
INSTALL_DIR = "/usr/local/lib/qbit-manager"

# Se instalou em outro lugar, ajuste:
# INSTALL_DIR = "/opt/qbit-manager"
# INSTALL_DIR = "/home/usuario/qbit-manager"
```

### 6. (Opcional) Criar atalho

```bash
sudo ln -sf /usr/local/lib/qbit-manager/qbit-manager.py /usr/local/bin/qbit-manager
```

### 7. Agendar no cron

```bash
sudo crontab -e
```

```cron
# Executa a cada 5 minutos
*/5 * * * * python3 /usr/local/lib/qbit-manager/qbit-manager.py >/dev/null 2>&1
```

### Instalou em outro local?

Duas opções:

**Opção 1** — Alterar `INSTALL_DIR` no `config.py`:
```python
INSTALL_DIR = "/opt/qbit-manager"
```

**Opção 2** — Usar flags na linha de comando (sem alterar nenhum arquivo):
```bash
python3 /opt/qbit-manager/qbit-manager.py --config /meu/config --modules /opt/qbit-manager
```

---

## Instalação — Windows

```powershell
# 1. Criar diretórios
mkdir C:\qbit-manager              # INSTALL_DIR (scripts + modulos)
mkdir C:\qbit-manager\modulos      # módulos internos
mkdir C:\qbit-manager\config       # CONFIG_DIR (configuração)
mkdir C:\qbit-manager\db           # DB_DIR (banco de dados)

# 2. Copiar scripts + módulos
copy qbit-manager.py           C:\qbit-manager\
copy modulos\*.py               C:\qbit-manager\modulos\

# 3. Copiar configuração
copy config.py                  C:\qbit-manager\config\config.py
```

Edite o `config.py` com os caminhos do Windows:

```python
INSTALL_DIR = r"C:\qbit-manager"
DB_DIR      = r"C:\qbit-manager\db"
DB_PATH     = f"{DB_DIR}\\qbit.db"
```

Para executar, use `--config` apontando para o diretório de configuração:

```powershell
python C:\qbit-manager\qbit-manager.py --config C:\qbit-manager\config
```

#### Agendador de Tarefas (Windows)

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Clique em **Criar Tarefa Básica**
3. Defina o gatilho como **Diário** e configure a repetição a cada 5 minutos
4. Na ação, configure:
   - **Programa**: `python`
   - **Argumentos**: `C:\qbit-manager\qbit-manager.py --config C:\qbit-manager\config`

---

## Configuração

Edite o `config.py` no diretório de configuração (`/etc/qbit-manager/config.py`).

### Diretórios

```python
# Onde estão os scripts e a pasta modulos/ (ajuste se instalou em outro local)
INSTALL_DIR = "/usr/local/lib/qbit-manager"

# Onde o banco de dados será criado
DB_DIR  = "/var/lib/qbit-manager"
DB_PATH = f"{DB_DIR}/qbit.db"
```

### Conexão com o qBittorrent

```python
QB_URL  = "http://localhost:8080"   # URL do qBittorrent Web UI
QB_USER = "admin"
QB_PASS = "senha"
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

Para gerar o `TRACKER_RULES` automaticamente a partir dos seus torrents, use `--tracker-list` — ele lista todos os trackers com contagem de torrents e gera o bloco pronto para colar no `config.py`.

### OpenTelemetry (opcional)

Para enviar logs estruturados a um OTEL Collector, adicione ao `config.py`:

```python
OTEL_ENDPOINT     = "http://localhost:4318"   # endpoint OTLP/HTTP do collector
OTEL_SERVICE_NAME = "qbit-manager"            # nome do serviço nos logs
OTEL_ENVIRONMENT  = "production"              # deployment.environment (ex: production, staging)
OTEL_ENABLED      = True                      # ativar envio
```

Se não configurar, o sistema funciona normalmente sem OTEL — os logs vão apenas para o console.

---

## Notificações

As notificações são configuradas diretamente no `config.py` — basta definir o tipo e as credenciais:

```python
NOTIFICACAO_TIPO = "telegram"    # ou: discord, slack, ntfy, gotify, pushover, nenhum
NOTIFICACAO_CONFIG = {
    "bot_token": "123456:ABC-seu-token-aqui",
    "chat_id":   "123456789",
}
```

O módulo `modulos/notificacao.py` lê essas variáveis e despacha para o canal correto. Não é necessário criar nenhum arquivo separado.

### Tipos e credenciais

| Tipo | Credenciais no `NOTIFICACAO_CONFIG` | Como obter |
|---|---|---|
| `telegram` | `bot_token`, `chat_id` | Crie bot via [@BotFather](https://t.me/BotFather), `chat_id` via `/getUpdates` |
| `discord` | `webhook_url` | Configurações do Servidor → Integrações → Webhooks |
| `slack` | `webhook_url` | [api.slack.com/apps](https://api.slack.com/apps) → Incoming Webhooks |
| `ntfy` | `url`, `token` (opcional) | [ntfy.sh](https://ntfy.sh) ou self-hosted |
| `gotify` | `url`, `token` | [gotify.net](https://gotify.net) — painel → Application → Token |
| `pushover` | `app_token`, `user_key` | [pushover.net](https://pushover.net) |
| `nenhum` | — | Desativa notificações |

Todos os exemplos com credenciais estão comentados no `config.py`.

### Mensagens enviadas

| `event_type` | Título | Mensagem | Quando |
|---|---|---|---|
| `paused` | `Torrents Status` | `Downloads Pausados` | 1x por ocorrência |
| `restored` | `Torrents Status` | `Download em andamento` | Sempre |
| `waiting_paused` | `Downloads Ainda Pausados` | `Verificar sistema.` | A cada 60 min |

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
