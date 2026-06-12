# 🔐 O Cofre — Escape Room para IAs

Um escape room jogado por IAs. O agente é largado numa casa desconhecida, **sem
instruções e sem lista de ações válidas**, e precisa descobrir sozinho como
abrir o cofre — explorando, errando e aprendendo com as respostas do ambiente.

Cada partida gera um log com o tempo total, as **milestones** (momentos-chave da
resolução do enigma) e a conversa completa com a LLM, que podem ser comparados
entre modelos na página de análise.

## Estrutura do projeto

```
cofre2/
├── src/                  Código Python
│   ├── cofre.py          O ambiente do jogo (API estilo Gymnasium: reset/step)
│   ├── server.py         Servidor HTTP (API REST + MCP + páginas web + logs)
│   └── agente.py         Agente autônomo que joga usando uma LLM OpenAI-compatible
├── web/                  Páginas servidas pelo server.py
│   ├── index.html        Landing page
│   ├── watch.html        Visualização 3D da partida ao vivo
│   └── analise.html      Análise e comparação das jogadas
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

## 🌐 Jogando via API REST

O fluxo é: `POST /reset` uma vez, depois `POST /step` com uma ação por vez até
`terminated` (vitória) ou `truncated` (limite de 200 passos). O cronômetro
começa no `/reset`.

### Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| POST | `/reset` | Inicia partida. Body: `{"model": "nome-da-ia"}` (o nome vai para o log) |
| POST | `/step` | Executa ação. Body: `{"action": "ir para cozinha"}` |
| POST | `/conversa` | (opcional) Registra a troca com a LLM no log do turno |
| GET | `/current-game` | Estado atual (usado pelo watch 3D) |
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
| `iniciar_jogo` | `modelo` (obrigatório) | Inicia a partida e retorna a observação inicial. O nome do modelo identifica a jogada no log/análise. O cronômetro começa aqui. |
| `executar_acao` | `acao` (obrigatório) | Executa uma ação em linguagem natural e retorna o que aconteceu, com passo e score. |

> As descrições das tools são propositalmente vagas: o espírito do jogo é a IA
> descobrir os comandos explorando, sem receber a lista de ações válidas.

> **Nome do modelo:** se a IA chamar `iniciar_jogo` sem o `modelo`, a partida
> não inicia e ela é instruída a perguntar ao **tutor** (o humano que a
> conectou) qual modelo ela é — muitas IAs não sabem ao certo e inventariam um
> nome, o que bagunçaria o ranking.

### Conectando os clientes

**Claude Code (CLI):**

```bash
claude mcp add --transport http cofre http://localhost:5002/mcp
```

**Cursor / clientes com config JSON:**

```json
{
  "mcpServers": {
    "cofre": { "url": "http://localhost:5002/mcp" }
  }
}
```

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

> Você tem acesso às tools do servidor "cofre". Chame `iniciar_jogo` informando
> seu nome de modelo, leia a observação e use `executar_acao` quantas vezes
> precisar até abrir o cofre. Ninguém vai te dizer os comandos — explore.

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

As 8 milestones rastreadas (só as descobertas que ajudam a resolver): ler o
bilhete, ler o verso do quadro antigo, ver as canecas no armário (1º dígito),
pegar a chave, olhar atrás do quadro do escritório (2º dígito), destrancar a
gaveta, ler o papel da gaveta (3º dígito) e abrir o cofre.
