# 🔐 O Cofre — Escape Room para IAs

Um escape room jogado por IAs. O agente é largado numa casa desconhecida, **sem
instruções e sem lista de ações válidas**, e precisa descobrir sozinho como
abrir o cofre — explorando, errando e aprendendo com as respostas do ambiente.

Cada partida gera um log com o tempo total, as **milestones** (momentos-chave da
resolução do enigma) e a conversa completa com a LLM, que podem ser comparados
entre modelos na página de análise.

O jogo tem **várias fases**, com dificuldade crescente (a Fase 2 é a mesma casa
da Fase 1, mas com pistas mais cruéis, números-chamariz e um código que exige
raciocínio). A IA escolhe qual fase jogar, e o catálogo é montado sozinho a
partir dos arquivos em `src/jogos/` — **basta soltar um arquivo novo no padrão
que ele aparece em tudo** (servidor, MCP e páginas web). Veja
[Fases e jogos](#-fases-e-jogos-srcjogos).

## Estrutura do projeto

```
cofre2/
├── src/                  Código Python
│   ├── cofre.py          O motor do jogo, genérico (API estilo Gymnasium: reset/step)
│   ├── server.py         Servidor HTTP (API REST + MCP + páginas web + logs)
│   ├── agente.py         Agente autônomo que joga usando uma LLM OpenAI-compatible
│   └── jogos/            ★ Um arquivo por fase/jogo — descobertos automaticamente
│       ├── __init__.py   Registro: varre a pasta e carrega cada JOGO
│       ├── _base.py      Utilitários compartilhados (arquivos "_" não são jogos)
│       ├── cofre_fase1.py  Fase 1 (fácil)
│       └── cofre_fase2.py  Fase 2 (difícil)
├── web/                  Páginas servidas pelo server.py
│   ├── index.html        Landing page
│   ├── watch.html        Visualização 3D da partida ao vivo
│   ├── analise.html      Análise e comparação das jogadas
│   └── configurar.html   Como conectar um cliente MCP
├── logs/                 Um arquivo JSON por partida
├── .env                  Sua configuração (não versionado — crie a partir do env.example)
├── env.example           Modelo de configuração
└── requirements.txt
```

## Instalação e uso

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy env.example .env           # e edite com sua API/modelo
```

Em um terminal: `python src/server.py` — depois abra **http://localhost:5002/**.

> A porta padrão é **5002**; mude com `COFRE_PORT` no `.env` (e ajuste
> `COFRE_SERVER`, usado pelo `agente.py`). Os exemplos abaixo assumem a padrão.

Para a IA jogar, há três caminhos:

1. **Agente pronto:** `python src/agente.py` (configurado pelo `.env`)
2. **API REST:** qualquer código que chame `/reset` e `/step`
3. **MCP:** qualquer cliente MCP (Claude Code, Claude Desktop, claude.ai, Cursor…) conectado em `/mcp`

---

## 🎮 Fases e jogos (`src/jogos/`)

Cada fase/jogo é um arquivo Python em `src/jogos/`. O registro
(`src/jogos/__init__.py`) varre a pasta na inicialização e carrega **todo
arquivo que exponha um dicionário `JOGO`** — sem mexer no motor, no servidor nem
nas páginas. O motor (`cofre.py`) é genérico: ele só consome a definição do jogo.

Fases que já vêm prontas:

| id | Nome | Dificuldade |
|---|---|---|
| `cofre_fase1` | Jogo do Cofre - Fase 1 | Fácil — três dígitos viram o código na ordem em que se encontra |
| `cofre_fase2` | Jogo do Cofre - Fase 2 | Difícil — mesma casa, mas com números-chamariz e um código que exige reordenar os dígitos e somar 1 a cada |

### Como adicionar um jogo novo

Crie `src/jogos/meu_jogo.py` com um dicionário `JOGO`. Assim que o arquivo
estiver na pasta (no padrão abaixo), ele aparece sozinho no servidor, vira opção
no MCP (`iniciar_jogo`/`listar_jogos`) e entra nos filtros da análise.

```python
from ._base import estado_base   # monta o estado padrão a partir das salas

MILESTONES = {"cofre_aberto": "Abriu o cofre"}  # marcos {id: rótulo}

def mundo():
    return estado_base({ ... salas e objetos ... }, sala_inicial="sala")

def solucao():
    return ["...", "digitar 000"]   # opcional, usado no autoteste

JOGO = {
    "nome":       "Meu Jogo",        # obrigatório
    "mundo":      mundo,             # obrigatório (callable -> estado)
    "milestones": MILESTONES,        # obrigatório
    # opcionais (têm default):
    "id":         "meu_jogo",        # default: nome do arquivo
    "fase":       3,
    "cenario":    "cofre",           # qual cena 3D o /watch usa
    "descricao":  "...",
    "max_passos": 200,
    "cena":       {"mugs": 3, "digito_quadro": "1", "digito_papel": "9"},
    "solucao":    solucao,
}
```

O contrato completo está documentado no topo de `src/jogos/__init__.py`. Para
validar a sua fase, rode `python src/cofre.py` — ele joga a `solucao()` de cada
jogo descoberto e diz se vence.

> **Cena 3D:** o `/watch` reaproveita o cenário do `cenario` (hoje, `"cofre"`) e
> lê os números variáveis (`cena`) do servidor — por isso a Fase 2, com 4
> canecas e outros dígitos, é renderizada corretamente sem tocar no 3D. Um jogo
> com mapa totalmente diferente precisaria de uma cena nova no `watch.html`.

---

## 🌐 Jogando via API REST

O fluxo é: `POST /reset` uma vez, depois `POST /step` com uma ação por vez até
`terminated` (vitória) ou `truncated` (limite de passos da fase — 200 na Fase 1).
O cronômetro começa no `/reset`.

### Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/reset` | Inicia partida. Body: `{"model": "nome-da-ia", "jogo": "cofre_fase2"}` (`jogo` é opcional — padrão Fase 1) |
| POST | `/step` | Executa ação. Body: `{"action": "ir para cozinha"}` |
| POST | `/conversa` | (opcional) Registra a troca com a LLM no log do turno |
| GET | `/current-game` | Estado atual (usado pelo watch 3D) — inclui o jogo e os parâmetros de cena |
| GET | `/jogos` | Lista as fases/jogos disponíveis (descobertos em `src/jogos/`) |
| GET | `/runs` | Todos os logs de jogadas (usado pela análise) |
| GET/POST | `/god-message` | Dica do operador humano para a IA |
| GET | `/health` | Status do servidor |

### Exemplo (curl)

```bash
# Iniciar partida
curl -X POST http://localhost:5002/reset \
     -H "Content-Type: application/json" \
     -d '{"model": "minha-ia"}'
# → {"obs": "Ha um cofre nesta casa. Explore. ...", "run_id": "...", "success": true}

# Executar uma ação
curl -X POST http://localhost:5002/step \
     -H "Content-Type: application/json" \
     -d '{"action": "olhar"}'
# → {"obs": "...", "reward": -1.0, "terminated": false, "truncated": false,
#    "steps": 1, "score": -1.0, "success": true}
```

Resposta do `/step`:

- `obs` — o que o ambiente respondeu (é tudo que a IA "enxerga")
- `reward` — −1 por passo, +100 ao abrir o cofre
- `terminated` — `true` quando o cofre abriu (vitória)
- `truncated` — `true` quando estourou o limite de passos

### Registrando a conversa no log (opcional)

Antes de cada `/step`, envie a troca com a LLM para ela aparecer na análise:

```bash
curl -X POST http://localhost:5002/conversa \
     -H "Content-Type: application/json" \
     -d '{"enviado": "<prompt enviado à LLM>", "resposta": "<resposta completa>",
          "pensamento": "<raciocínio extraído>", "acao": "<ação extraída>"}'
```

---

## 🔌 Jogando via MCP (Model Context Protocol)

O servidor expõe um endpoint MCP no **transporte Streamable HTTP** — o formato
atual do protocolo (endpoint único recebendo JSON-RPC 2.0 via POST, que
substituiu o transporte antigo HTTP+SSE de duas rotas). Com isso, **a IA enxerga
o ambiente e manda ações diretamente pelas tools, sem precisar de código de
API**. O servidor é stateless (não exige sessão) e negocia a versão do
protocolo com o cliente (`2024-11-05` até `2025-11-25`).

```
URL do servidor MCP:  http://localhost:5002/mcp
```

### Tools disponíveis

| Tool | Parâmetros | O que faz |
|---|---|---|
| `listar_jogos` | — | Lista as fases/jogos disponíveis (id, nome, dificuldade) para a IA escolher. Não inicia partida nem gasta passos. |
| `iniciar_jogo` | `modelo` (obrigatório), `jogo` (opcional), `modo` (opcional: `livre`/`turnos`) | Inicia a partida e retorna a observação inicial. `jogo` escolhe a fase (padrão: Fase 1). O nome do modelo identifica a jogada no log/análise. O cronômetro começa aqui. |
| `executar_acao` | `acao` (obrigatório), `pensamento` (obrigatório) | Executa uma ação em linguagem natural e retorna o que aconteceu, com passo e score. O `pensamento` aparece no balão da visualização 3D e no log — sem ele a ação não executa. |

> As descrições das tools são propositalmente vagas: o espírito do jogo é a IA
> descobrir os comandos explorando, sem receber a lista de ações válidas.

> **Nome do modelo:** se a IA chamar `iniciar_jogo` sem o `modelo`, a partida
> não inicia e ela é instruída a perguntar ao **tutor** (o humano que a
> conectou) qual modelo ela é — muitas IAs não sabem ao certo e inventariam um
> nome, o que bagunçaria o ranking.

### Conectando os clientes

**Claude Code (CLI):**

```bash
claude mcp add --transport http jogo-do-cofre http://127.0.0.1:5002/mcp
```

**Cursor / Claude Code / clientes com config JSON:**

Use a mesma forma em todos — no Claude Code é o arquivo `.mcp.json` na raiz do
projeto:

```json
{
  "mcpServers": {
    "jogo-do-cofre": {
      "type": "http",
      "url": "http://127.0.0.1:5002/mcp"
    }
  }
}
```

Dois detalhes que deixam essa config compatível com o Claude Code (e não
atrapalham os outros, que ignoram chaves extras):

- **`"type": "http"`** — o Claude Code precisa dele pra escolher o transporte
  Streamable HTTP; Cursor e afins inferem pela URL.
- **nome sem espaços** (`jogo-do-cofre`, não `jogo do cofre`) — o Claude Code
  deriva o nome das tools daí (`mcp__jogo-do-cofre__iniciar_jogo`), e só aceita
  letras, números, `_` e `-`.

> Use `127.0.0.1` em vez de `localhost`: em alguns sistemas o `localhost`
> resolve IPv6 (`::1`) antes do IPv4, e o cliente pode não achar o servidor.

**Claude Desktop / claude.ai (conectores web):** esses clientes exigem uma URL
pública HTTPS. Exponha o servidor local com um túnel e cadastre o conector em
*Settings → Connectors → Add custom connector*:

```bash
ngrok http 5002
# use a URL gerada: https://xxxx.ngrok.app/mcp
```

⚠️ Ao expor publicamente, lembre que o servidor não tem autenticação — qualquer
pessoa com a URL pode jogar e ler os logs. Use o túnel só durante a partida.

### Exemplo de prompt para a IA jogar

> Você tem acesso às tools do servidor "cofre". Chame `listar_jogos` para ver as
> fases, depois `iniciar_jogo` informando seu nome de modelo e a fase escolhida
> (campo `jogo`). Leia a observação e use `executar_acao` quantas vezes precisar
> até abrir o cofre. Ninguém vai te dizer os comandos — explore.

A partida via MCP entra nos logs e na página de análise normalmente (o tempo
inclui o raciocínio da IA entre uma tool call e outra, como nos outros modos).

### Por baixo dos panos

O endpoint implementa os métodos JSON-RPC `initialize`, `tools/list`,
`tools/call` e `ping` (além de aceitar as notificações com `202 Accepted`).
Exemplo de chamada crua:

```bash
curl -X POST http://localhost:5002/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "executar_acao", "arguments": {"acao": "olhar"}}}'
```

---

## ⏱️ Modos de jogo: `livre` × `turnos`

IAs jogando via MCP descobriram um "glitch" divertido: mandar **várias ações em
paralelo**, resolvendo missões simultaneamente — a animação 3D fica pulando
etapas, mas demonstra bem o poder de paralelismo delas. Por isso existem dois
modos:

| Modo | Comportamento |
|---|---|
| `livre` (padrão) | Como está: ações em paralelo são permitidas (apenas serializadas internamente, nunca recusadas) |
| `turnos` | Realista, "sem teletransporte": **uma ação por vez**. A resposta da ação só é entregue quando ela termina no mundo — andar até outra sala leva `COFRE_TEMPO_MOVER` (padrão 3s, o tempo do boneco chegar lá na animação 3D) e as demais ações levam `COFRE_TEMPO_ACAO` (padrão 1.5s). Qualquer ação enviada enquanto outra está em andamento é recusada na hora — não conta passo nem entra no histórico — e a IA é avisada: nada de "abre a gaveta, olha o quadro, faz isso, faz aquilo" tudo de uma vez |

Onde configurar:

- **Padrão do servidor:** `COFRE_MODO=livre|turnos` no `.env`
- **Por partida (REST):** `POST /reset` com `{"model": "...", "modo": "turnos"}`
  — no `/step`, ações recusadas voltam com `"rejeitada": true`
- **Por partida (MCP):** argumento `modo` da tool `iniciar_jogo`

O modo da partida fica registrado no log (`"modo"`) e aparece na página de
análise — dá para comparar o tempo da mesma IA com e sem paralelismo.

---

## 📊 Páginas web

| URL | O que mostra |
|---|---|
| `http://localhost:5002/` | Landing page |
| `http://localhost:5002/watch` | Partida ao vivo em 3D, com pensamentos e dicas divinas |
| `http://localhost:5002/analise` | Comparação de jogadas: filtros por modelo/tempo, gráfico de evolução das milestones e conversas completas |

## 📝 Formato do log (`logs/*.json`)

```json
{
  "run_id": "20260612_153000_omnikimi",
  "model": "omnikimi",
  "started_at": "2026-06-12T15:30:00",
  "modo": "livre",
  "jogo": "cofre_fase1",
  "jogo_nome": "Jogo do Cofre - Fase 1",
  "fase": 1,
  "cenario": "cofre",
  "total_milestones": 8,
  "venceu": true,
  "tempo_total": 84.3,
  "passos": 17,
  "score": 84,
  "system_prompt": "...",
  "milestones": [
    {"id": "digito1_canecas", "label": "Viu as canecas no armario da cozinha (1o digito)",
     "passo": 3, "t": 12.4}
  ],
  "historico": [
    {"passo": 1, "acao": "olhar", "t": 3.1, "reward": -1.0,
     "resultado": "...", "pensamento": "...",
     "conversa": {"enviado": "<prompt>", "resposta": "<resposta da LLM>"}}
  ]
}
```

Os campos `jogo`/`jogo_nome`/`fase` identificam **qual fase foi jogada** (logs
antigos, anteriores às fases, são tratados como `Jogo do Cofre - Fase 1`). A
página de análise filtra por jogo e descobre as milestones de cada partida
automaticamente, então funciona para qualquer jogo novo.

As 8 milestones rastreadas na família Cofre (só as descobertas que ajudam a
resolver): ler o bilhete, ler o verso do quadro antigo, ver as canecas no
armário (1º dígito), pegar a chave, olhar atrás do quadro do escritório (2º
dígito), destrancar a gaveta, ler o papel da gaveta (3º dígito) e abrir o cofre.
