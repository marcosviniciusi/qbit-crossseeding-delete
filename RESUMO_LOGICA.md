# Resumo da Logica do qbit-manager - Pontos Importantes

## Arquitetura Atual (monolitica - qbit-manager.py ~1128 linhas)

### Fluxo Principal (main)
1. Inicializa banco SQLite (`init_db`)
2. Conecta ao qBittorrent via API (`qbittorrentapi.Client`)
3. Le ultimo estado do banco (`ler_ultimo_estado`)
4. Coleta estado atual: espacos em disco + checking/moving
5. Cria registro de run no banco
6. Salva snapshot de todos os torrents
7. Logica de decisao baseada no estado anterior (pausado ou ativo)
8. Gerencia trackers (se sistema ativo)
9. Atualiza run e imprime resumo

### Logica de Estado - Maquina de Estados
- **tinha_pausados = True**: Sistema estava pausado
  - Verifica `discos_criticos_registro` (do banco)
  - Se `None`: notifica waiting, aguarda
  - Se `pode_restaurar` (todos_ok AND checking_moving_zero): restaura
  - Senao: analisa tipo de disco que causou pausa:
    - `pausa_por_p2p` + `critico_seed_cleaner`: tenta seed cleaner, reavalia
    - `pausa_por_destino` (sem p2p): aguarda Radarr/Sonarr
    - Disco normalizado mas checking/moving alto: aguarda
- **tinha_pausados = False**: Fluxo normal
  - Se `qualquer_critico`: seed cleaner -> se ainda critico: pausa
  - Senao: force checking + gerenciar trackers

### Condicoes Chave
- `qualquer_critico`: algum disco com `pause_trigger=True` esta <= `limite_min`
- `todos_ok`: todos os discos com `pause_trigger=True` estao >= `limite_max`
- `checking_moving_zero`: nenhum torrent em checking/moving
- `critico_seed_cleaner`: disco com `seed_cleaner=True` esta critico
- `pode_restaurar`: `todos_ok AND checking_moving_zero`

### Banco de Dados - 5 Tabelas
1. **runs**: historico de execucoes (status, checking, moving, disk_spaces, contadores)
2. **torrent_snapshots**: snapshot de todos torrents por run (hash, name, state, speeds, tracker)
3. **pause_events**: historico de pause/restore/waiting (reason, disk_spaces, discos_criticos, hashes)
4. **seed_deletions**: historico de delecoes do seed cleaner (hash, name, tracker, seeding_days, dry_run)
5. **notifications**: log de notificacoes enviadas (event_type, title, message)

### Seed Cleaner - Logica Cross-Seed
- Agrupa torrents por nome (detecta cross-seeds)
- Para cada grupo: verifica se TODOS os trackers satisfazem TRACKER_RULES
- So deleta quando ALL_SATISFIED = True para o grupo inteiro
- Se dry_run: registra no banco mas nao apaga
- Se deleção real: um por um com commit individual, aguarda 2 min no final

### Pausa/Restauracao
- Pausa: desativa force_start, pausa torrent, registra hashes no banco
- Restauracao: resume + reativa force_start, registra evento restore
- Moving torrents: faz recheck quando pausa (evita corrupcao)

### Gerenciamento de Trackers
- Classifica torrents por tracker: ativo, fila, pausado, seeding
- Se ativos < MIN_DOWNLOADS_PER_TRACKER: ativa da fila ou dos pausados
- Trackers pequenos (< MIN_TORRENTS_PER_TRACKER): ignora se tem ativo, ativa se nao tem

### Notificacoes - 3 Tipos de Evento
- `paused`: envia 1x por ocorrencia (nao reenvia se ja enviou sem restore)
- `restored`: sempre envia
- `waiting_paused`: envia a cada 60 minutos

### Importacoes e Configs
- CONFIG_DIR = "/etc/qbit-manager" (adicionado ao sys.path)
- config.py: importado com `from config import *`
- tracker_rules.py: opcional, sobrescreve TRACKER_RULES do config
- notificacao.py: opcional, fallback para Pushover

---

## Nova Arquitetura Modular

```
qbit-manager-python/
├── qbit-manager.py          # Entry point (aceita --tracker-list)
├── config.py                # Template de configuracoes
├── modulos/
│   ├── __init__.py
│   ├── db.py                # Banco de dados (init, CRUD, queries)
│   ├── helpers.py           # Utilitarios compartilhados
│   ├── otel.py              # OpenTelemetry logging (buffer + flush)
│   ├── notificacao.py       # Notificacoes (despacha por tipo do config)
│   ├── limpeza.py           # Seed cleaner (chamado pela checagem)
│   ├── ativacao.py          # Ativacao de downloads + gerenciamento de trackers
│   ├── checagem_disco.py    # Orquestrador: checagem de disco -> limpeza -> ativacao
│   └── tracker_list.py      # Gerador de lista de trackers
```

### Responsabilidades:
- **checagem_disco.py**: verifica espacos, decide estado, chama limpeza e ativacao
- **limpeza.py**: seed cleaner completo (cross-seed, dry_run, delecao)
- **ativacao.py**: restauracao de downloads, gerenciamento de trackers, force start
- **notificacao.py**: le NOTIFICACAO_TIPO do config e despacha (telegram, discord, etc)
- **otel.py**: acumula logs durante o run e envia em bloco unico via OTLP/HTTP
- **tracker_list.py**: varre torrents e gera bloco TRACKER_RULES pro config.py
- **db.py**: todas as operacoes de banco (init, criar_run, salvar_snapshots, etc)
- **helpers.py**: verificar_espacos, extrair_dominio, construir_tracker_map
