# qbit-tools

Scripts para gerenciamento de torrents no qBittorrent via API.

---

## Pré-requisitos

**Python 3.6+**
```bash
python3 --version
```

**Biblioteca requests:**
```bash
pip install requests
```

**qBittorrent:**
- Versão 4.1 ou superior
- Web UI habilitada em Ferramentas → Preferências → Web UI
- Usuário e senha configurados

---

## qbit-traker-list.py

Lista todos os trackers presentes nos torrents do qBittorrent, mostrando quantos torrents cada tracker possui. Ao final, gera automaticamente o bloco `TRACKER_RULES` pronto para copiar e colar no script de deleção, com `X` nos lugares dos dias para você preencher conforme a regra de cada tracker.

**Uso:**
```bash
python qbit-traker-list.py
```

**Exemplo de output gerado:**
```python
TRACKER_RULES = {
    "XPTo.com":                        X,  # 169 torrents
    "trackerx.cc":                        X,  # 159 torrents
    "trackerY.com":                       X,  # 150 torrents
    ...
}
```

Copie o bloco acima, cole no script de deleção substituindo o `TRACKER_RULES` existente, e troque os `X` pelos dias mínimos de seedtime de cada tracker.

---

## qbit-cross-delete.py

Apaga torrents que cumpriram o seedtime mínimo definido por tracker. Suporta **cross-seeding**: se o mesmo torrent estiver em múltiplos trackers, só apaga quando **todos** os trackers do grupo cumpriram seus respectivos tempos mínimos.

**Configurações importantes no script:**

- `DRY_RUN = True` — apenas simula, não apaga nada. Mude para `False` para apagar de verdade.
- `deleteFiles = True` — apaga os arquivos do disco junto com o torrent. Mude para `False` para remover só da fila.
- `TRACKER_RULES` — cole aqui o bloco gerado pelo `qbit-traker-list.py` e substitua os `X` pelos dias.

**Uso:**
```bash
python qbit-cross-delete.py
```

---

## qbit-cross-delete-with-check-filesystem.py

Versão do script de deleção com verificação de espaço em disco. Funciona igual ao `qbit-cross-delete.py`, porém **só executa a limpeza se o espaço livre em disco estiver abaixo do threshold configurado**, evitando deleções desnecessárias quando o disco ainda tem espaço suficiente.

**Configurações adicionais em relação ao qbit-cross-delete.py:**

- `MIN_FREE_SPACE_GB` — threshold de espaço livre em GB. O script só age se o espaço livre estiver **abaixo** deste valor.
- `MONITOR_PATH` — caminho do disco a monitorar (ex: `/` ou `/mnt/media`).

**Uso:**
```bash
python qbit-cross-delete-with-check-filesystem.py
```

---

## Fluxo recomendado

1. Rode o `qbit-traker-list.py`
2. Copie o bloco `TRACKER_RULES` do output
3. Cole no script de deleção desejado substituindo o `TRACKER_RULES` existente
4. Substitua os `X` pelos dias mínimos de cada tracker
5. Se usar o `with-check-filesystem`, ajuste `MIN_FREE_SPACE_GB` e `MONITOR_PATH`
6. Rode com `DRY_RUN = True` para conferir
7. Mude para `DRY_RUN = False` e rode de verdade

---

## Crontab

Para rodar o script automaticamente, adicione ao crontab:
```bash
crontab -e
```

**Exemplos de agendamento:**

A cada hora:
```
0 * * * * /usr/bin/python3 /caminho/para/qbit-cross-delete.py >> /var/log/qbit-cross-delete.log 2>&1
```

A cada 6 horas:
```
0 */6 * * * /usr/bin/python3 /caminho/para/qbit-cross-delete.py >> /var/log/qbit-cross-delete.log 2>&1
```

Uma vez por dia à meia-noite:
```
0 0 * * * /usr/bin/python3 /caminho/para/qbit-cross-delete.py >> /var/log/qbit-cross-delete.log 2>&1
```

Para verificar o log:
```bash
tail -f /var/log/qbit-cross-delete.log
```

> **Nota:** Confirme o caminho do Python com `which python3` antes de adicionar ao crontab.

---

## Configuração (todos os scripts)
```python
QB_URL  = "https://seu-qbittorrent:porta"
QB_USER = "usuario"
QB_PASS = "senha"
```