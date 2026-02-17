# qbit-cross-delete

Scripts para gerenciamento na remoção de torrents no qBittorrent via API.

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
    "trake1.example.com":                        X,  # 169 torrents
    "tracker.cc":                                X,  # 159 torrents
    "anothertracker.com":                        X,  # 150 torrents
    ...
}
```

Copie o bloco acima, cole no `qbit-cross-delete.py` substituindo o `TRACKER_RULES` existente, e troque os `X` pelos dias mínimos de seedtime de cada tracker.

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

## Fluxo recomendado

1. Rode o `qbit-traker-list.py`
2. Copie o bloco `TRACKER_RULES` do output
3. Cole no `qbit-cross-delete.py` substituindo o `TRACKER_RULES` existente
4. Substitua os `X` pelos dias mínimos de cada tracker
5. Rode o `qbit-cross-delete.py` com `DRY_RUN = True` para conferir
6. Mude para `DRY_RUN = False` e rode de verdade

---

## Configuração (ambos os scripts)
```python
QB_URL  = "https://seu-qbittorrent:porta"
QB_USER = "usuario"
QB_PASS = "senha"
```