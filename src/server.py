"""
Servidor HTTP do Cofre V2 — porta 5002.

Diferença chave do V1:
  /reset e /step NÃO retornam valid_actions ao agente.
  O agente descobre os comandos por tentativa e erro.

  /current-game AINDA retorna valid_actions para o watch 3D
  poder inferir os estados dos objetos na cena.

Roda (a partir da raiz do projeto): python src/server.py
"""

from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime
from dotenv import load_dotenv
import sys
import os
import re
import time
import json
import threading

sys.path.insert(0, os.path.dirname(__file__))
from cofre import Cofre
import jogos

# Estrutura do projeto: src/ (código), web/ (páginas), logs/ e .env na raiz
RAIZ    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(RAIZ, "web")

load_dotenv(os.path.join(RAIZ, ".env"))
PORT = int(os.getenv("COFRE_PORT", "5002"))

# Modos de jogo:
#   livre  — ações em paralelo permitidas (o "glitch" que as IAs descobrem:
#            mandar trocentas ações ao mesmo tempo)
#   turnos — modo realista: UMA ação por vez. A resposta só é entregue quando
#            a ação "termina de verdade" (andar até outra sala leva o tempo da
#            animação 3D — sem teletransporte). Ações paralelas são recusadas.
MODO_PADRAO = os.getenv("COFRE_MODO", "livre").strip().lower()
TEMPO_MOVER = float(os.getenv("COFRE_TEMPO_MOVER", "3"))    # andar entre salas
TEMPO_ACAO  = float(os.getenv("COFRE_TEMPO_ACAO",  "1.5"))  # demais ações

app = Flask(__name__)
env = None

current_thought     = ""
god_message_pending = ""
god_message_count   = 0

# ── Log da jogada ─────────────────────────────────────────────────────────────

LOGS_DIR = os.path.join(RAIZ, "logs")

run_id            = None   # ex: 20260612_153000_omnikimi
run_model         = ""
run_started_iso   = ""
run_system_prompt = ""
run_modo          = MODO_PADRAO
run_jogo          = None   # metadados do jogo da partida atual (id, nome, fase, ...)
historico         = []    # [{passo, acao, t, reward, resultado, pensamento, conversa}]
conversa_pendente = None  # última troca agente↔LLM, anexada ao próximo /step
acao_em_andamento = False # modo turnos: há uma ação segurando a resposta agora
passo_lock        = threading.Lock()  # serializa ações simultâneas


def _salvar_log(venceu):
    """Grava o log da jogada atual em logs/<run_id>.json (uma única vez)."""
    global run_id
    if run_id is None or env is None:
        return None
    jogo = run_jogo or {}
    log = {
        "run_id":        run_id,
        "model":         run_model,
        "started_at":    run_started_iso,
        "modo":          run_modo,
        # Qual jogo/fase foi jogado (campo novo — partidas antigas eram a Fase 1).
        "jogo":          jogo.get("id", "cofre_fase1"),
        "jogo_nome":     jogo.get("nome", "Jogo do Cofre - Fase 1"),
        "fase":          jogo.get("fase", 1),
        "cenario":       jogo.get("cenario", "cofre"),
        "total_milestones": jogo.get("n_milestones", len(env.estado["milestones"])),
        "venceu":        venceu,
        "tempo_total":   round(time.time() - env.estado["t0"], 2),
        "passos":        env.estado["passos"],
        "score":         env.estado.get("score", 0),
        "system_prompt": run_system_prompt,
        "milestones":    env.estado["milestones"],
        "historico":     historico,
    }
    os.makedirs(LOGS_DIR, exist_ok=True)
    caminho = os.path.join(LOGS_DIR, f"{run_id}.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"  [log] Jogada salva: {caminho}")
    run_id = None  # evita salvar a mesma jogada duas vezes
    return caminho


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ── Páginas (abrir no navegador) ─────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(WEB_DIR, 'index.html')


@app.route('/analise')
def pagina_analise():
    return send_from_directory(WEB_DIR, 'analise.html')


@app.route('/watch')
def pagina_watch():
    return send_from_directory(WEB_DIR, 'watch.html')


@app.route('/configurar')
def pagina_configurar():
    return send_from_directory(WEB_DIR, 'configurar.html')


@app.route('/favicon.svg')
def favicon():
    return send_from_directory(WEB_DIR, 'favicon.svg')


# ── Endpoints do agente (sem valid_actions) ──────────────────────────────────

def _resolver_jogo(jogo_id):
    """Devolve (jogo_def, meta) do jogo pedido; cai no padrão se não existir."""
    jogo_id = (jogo_id or "").strip()
    if not jogo_id:
        jogo_id = jogos.jogo_padrao()
    jogo_def = jogos.carregar_jogo(jogo_id)
    if jogo_def is None:                       # id inválido → padrão (Fase 1)
        jogo_id = jogos.jogo_padrao()
        jogo_def = jogos.carregar_jogo(jogo_id)
    meta = next((m for m in jogos.listar_jogos() if m["id"] == jogo_id), {})
    return jogo_def, meta


def _iniciar_jogada(model, system_prompt="", modo=None, jogo_id=None):
    """Cria uma partida nova com metadados de log. Usado pelo /reset e pelo MCP."""
    global env, current_thought, god_message_pending, god_message_count
    global run_id, run_model, run_started_iso, run_system_prompt, run_modo, run_jogo
    global historico, conversa_pendente, acao_em_andamento

    model = (model or "").strip() or "desconhecido"
    modo = (modo or "").strip().lower()
    run_modo = modo if modo in ("livre", "turnos") else MODO_PADRAO

    jogo_def, run_jogo = _resolver_jogo(jogo_id)
    env = Cofre(jogo=jogo_def)
    obs, info = env.reset()
    current_thought     = ""
    god_message_pending = ""
    god_message_count   = 0

    agora             = datetime.now()
    run_model         = model
    run_started_iso   = agora.isoformat(timespec="seconds")
    run_system_prompt = system_prompt
    modelo_limpo      = re.sub(r"[^A-Za-z0-9._-]+", "_", model)[:40]
    run_id            = f"{agora.strftime('%Y%m%d_%H%M%S')}_{modelo_limpo}"
    historico         = []
    conversa_pendente = None
    acao_em_andamento = False
    print(f"  [log] Nova jogada: {run_id} (modelo: {model}, modo: {run_modo}, "
          f"jogo: {run_jogo.get('nome', '?')})")
    return obs


def _step_e_registra(action):
    """Executa o passo no ambiente e registra histórico/log. Chamar com lock."""
    global conversa_pendente
    obs, reward, terminated, truncated, info = env.step(action)
    entrada = {
        "passo":      env.estado["passos"],
        "acao":       action,
        "t":          round(time.time() - env.estado["t0"], 2),
        "reward":     reward,
        "resultado":  obs.split("\n")[0][:160],
        "pensamento": current_thought,
    }
    if conversa_pendente:
        entrada["conversa"] = conversa_pendente
        conversa_pendente = None
    historico.append(entrada)
    if terminated or truncated:
        _salvar_log(venceu=terminated)
    return obs, reward, terminated, truncated


def _executar_passo(action):
    """Executa um passo. Retorna (obs, reward, terminated, truncated, rejeitada).

    Modo livre: ações simultâneas são apenas serializadas pelo lock (o "glitch"
    de paralelismo é permitido).

    Modo turnos: UMA ação por vez. O passo executa na hora (o watch 3D começa a
    animar), mas a resposta fica RETIDA até a ação terminar no mundo —
    andar entre salas leva TEMPO_MOVER, o resto TEMPO_ACAO. Qualquer ação que
    chegue nesse meio-tempo é recusada sem contar passo: sem missões paralelas.
    """
    global acao_em_andamento
    if run_modo != "turnos":
        with passo_lock:
            obs, reward, terminated, truncated = _step_e_registra(action)
        return obs, reward, terminated, truncated, False

    with passo_lock:
        if acao_em_andamento:
            obs = ("Calma! Uma acao de cada vez — voce ainda esta executando "
                   "a acao anterior. Espere o resultado dela chegar antes de "
                   "mandar a proxima. (modo turnos: sem missoes paralelas)")
            return obs, 0.0, False, False, True
        acao_em_andamento = True
    try:
        with passo_lock:
            obs, reward, terminated, truncated = _step_e_registra(action)
        # Segura a resposta até a animação "chegar lá" (sem teletransporte)
        eh_mover = action.lower().lstrip().startswith(("ir ", "go "))
        time.sleep(TEMPO_MOVER if eh_mover else TEMPO_ACAO)
        return obs, reward, terminated, truncated, False
    finally:
        acao_em_andamento = False


@app.route('/reset', methods=['GET', 'POST', 'OPTIONS'])
def reset():
    """Inicia partida nova. NÃO retorna valid_actions — o agente explora.

    Aceita ?model=<nome> (ou JSON {"model": ...}) para identificar a IA no log.
    """
    if request.method == 'OPTIONS':
        return '', 204

    model = request.args.get('model', '')
    modo  = request.args.get('modo', '')
    jogo_id = request.args.get('jogo', '')
    system_prompt = ''
    if request.is_json:
        dados = request.json or {}
        model = model or dados.get('model', '')
        modo  = modo or dados.get('modo', '')
        jogo_id = jogo_id or dados.get('jogo', '')
        system_prompt = dados.get('system_prompt', '')

    obs = _iniciar_jogada(model, system_prompt, modo, jogo_id)
    return jsonify({
        "obs": obs,
        "steps": 0,
        "score": 0,
        "run_id": run_id,
        "modo": run_modo,
        "jogo": run_jogo.get("id"),
        "jogo_nome": run_jogo.get("nome"),
        "success": True
    })


@app.route('/step', methods=['POST', 'OPTIONS'])
def step():
    """Executa ação. NÃO retorna valid_actions ao agente."""
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data   = request.json or {}
        action = data.get('action', '').strip()
        if not action:
            return jsonify({"success": False, "error": "Acao vazia"}), 400

        obs, reward, terminated, truncated, rejeitada = _executar_passo(action)

        return jsonify({
            "obs":        obs,
            "reward":     reward,
            "terminated": terminated,
            "truncated":  truncated,
            "rejeitada":  rejeitada,   # modo turnos: ação chegou cedo demais
            "steps":      env.estado["passos"],
            "score":      env.estado.get("score", 0),
            "success":    True
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


# ── Endpoints de observação (watch 3D continua recebendo valid_actions) ──────

@app.route('/current-game', methods=['GET'])
def current_game():
    """Estado completo para o watch — inclui valid_actions para animar objetos 3D."""
    if env is None:
        return jsonify({"status": "waiting", "message": "Nenhuma partida em andamento"})

    s = env.estado["salas"][env.estado["sala_atual"]]
    jogo = run_jogo or {}
    return jsonify({
        "status":           "playing",
        "room":             env.estado["sala_atual"],
        "room_name":        s["nome"],
        "obs":              env._descricao_sala(),
        "inventory":        env.estado["inventario"],
        "steps":            env.estado["passos"],
        "time":             round(time.time() - env.estado["t0"], 1) if "t0" in env.estado else 0.0,
        "score":            env.estado.get("score", 0),
        "terminated":       env.estado["cofre_aberto"],
        "valid_actions":    env._acoes_validas(),   # só para o watch
        "milestones":       env.estado["milestones"],
        "last_action":      historico[-1]["acao"] if historico else "",
        "modo":             run_modo,
        # Qual jogo está em andamento + parâmetros visuais para o watch 3D.
        "jogo":             jogo.get("id"),
        "jogo_nome":        jogo.get("nome"),
        "fase":             jogo.get("fase"),
        "cenario":          jogo.get("cenario", "cofre"),
        "cena":             jogo.get("cena", {}),
        "thought":          current_thought,
        "god_message_count": god_message_count
    })


@app.route('/jogos', methods=['GET'])
def listar_jogos_endpoint():
    """Lista os jogos disponíveis (descobertos automaticamente em src/jogos/)."""
    return jsonify({"jogos": jogos.listar_jogos(), "padrao": jogos.jogo_padrao()})


# ── Logs das jogadas (para analise.html) ─────────────────────────────────────

@app.route('/runs', methods=['GET'])
def runs():
    """Retorna todas as jogadas registradas em logs/ (mais recentes primeiro)."""
    lista = []
    if os.path.isdir(LOGS_DIR):
        for nome in os.listdir(LOGS_DIR):
            if not nome.endswith(".json"):
                continue
            try:
                with open(os.path.join(LOGS_DIR, nome), encoding="utf-8") as f:
                    lista.append(json.load(f))
            except Exception:
                continue  # ignora arquivo corrompido
    lista.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return jsonify({"runs": lista})


# ── God Messages e pensamentos ───────────────────────────────────────────────

@app.route('/god-message', methods=['GET', 'POST', 'OPTIONS'])
def god_message():
    global god_message_pending, god_message_count
    if request.method == 'OPTIONS':
        return '', 204
    if request.method == 'POST':
        msg = (request.json or {}).get('message', '').strip()
        if msg:
            god_message_pending  = msg
            god_message_count   += 1
        return jsonify({"ok": True, "count": god_message_count})
    msg = god_message_pending
    god_message_pending = ""
    return jsonify({"message": msg, "count": god_message_count})


@app.route('/thought', methods=['POST'])
def set_thought():
    global current_thought
    current_thought = (request.json or {}).get('thought', '')
    return jsonify({"ok": True})


@app.route('/conversa', methods=['POST', 'OPTIONS'])
def conversa():
    """Recebe a troca completa agente↔LLM do turno; é anexada ao próximo /step."""
    global conversa_pendente, current_thought
    if request.method == 'OPTIONS':
        return '', 204
    d = request.json or {}
    conversa_pendente = {
        "enviado":  d.get("enviado", ""),
        "resposta": d.get("resposta", ""),
    }
    if d.get("pensamento"):
        current_thought = d["pensamento"]   # mantém o watch 3D funcionando
    return jsonify({"ok": True})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": "v2"})


# ── MCP (Model Context Protocol) — transporte Streamable HTTP ────────────────
#
# Endpoint único POST /mcp recebendo JSON-RPC 2.0 (formato atual do protocolo,
# que substituiu o transporte antigo HTTP+SSE). Servidor stateless: não exige
# Mcp-Session-Id. Respostas em application/json (permitido pela spec).
#
# Conectar no Claude Code:
#   claude mcp add --transport http cofre http://localhost:5002/mcp

MCP_VERSOES_SUPORTADAS = {"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"}
MCP_VERSAO_PADRAO = "2025-06-18"

# As descrições são propositalmente vagas: o espírito do V2 é a IA descobrir
# os comandos explorando, sem receber a lista de ações válidas.
#
# As tools são construídas dinamicamente para que jogos novos (soltos em
# src/jogos/) apareçam sozinhos no parâmetro 'jogo' e na tool listar_jogos.

def _construir_tools():
    metas   = jogos.listar_jogos()
    ids     = [m["id"] for m in metas] or [None]
    padrao  = jogos.jogo_padrao()
    catalogo = "; ".join(f"'{m['id']}' = {m['nome']}" for m in metas) or "(nenhum)"
    return [
        {
            "name": "iniciar_jogo",
            "description": (
                "Inicia uma nova partida. Você está numa casa desconhecida e em "
                "algum lugar há um cofre trancado. Seu objetivo: abrir o cofre. "
                "Ninguém vai te dizer o que fazer — explore e descubra por conta "
                "própria. Há mais de uma fase/jogo; escolha em 'jogo' (use a tool "
                "listar_jogos para ver as opções). Retorna a observação inicial. "
                "O cronômetro começa aqui."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "modelo": {
                        "type": "string",
                        "description": (
                            "Nome do modelo de IA que está jogando (aparece no log "
                            "e na página de análise). Se você não tem CERTEZA de "
                            "qual modelo você é, pergunte ao seu tutor — o humano "
                            "que te conectou — antes de jogar. Não invente um nome."
                        )
                    },
                    "jogo": {
                        "type": "string",
                        "enum": ids,
                        "description": (
                            f"Qual fase/jogo jogar (opcional; padrão: '{padrao}'). "
                            f"Opções: {catalogo}. As fases maiores são mais "
                            "difíceis. Use listar_jogos para detalhes."
                        )
                    },
                    "modo": {
                        "type": "string",
                        "enum": ["livre", "turnos"],
                        "description": (
                            "Modo de jogo (opcional; padrão definido pelo servidor). "
                            "'livre': sem restrição de ritmo. 'turnos': modo "
                            "realista — uma ação por vez, com tempo entre elas."
                        )
                    }
                },
                "required": ["modelo"],
            },
        },
        {
            "name": "listar_jogos",
            "description": (
                "Lista as fases/jogos disponíveis (id, nome, dificuldade e "
                "descrição), para você decidir qual jogar em iniciar_jogo. "
                "Não inicia partida nem gasta passos."
            ),
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "executar_acao",
            "description": (
                "Executa uma ação em linguagem natural no ambiente e retorna o que "
                "aconteceu. Se uma ação não funcionar, o ambiente responde e você "
                "pode tentar algo diferente. Sempre envie também o seu pensamento — "
                "ele aparece na visualização 3D para os humanos acompanharem."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "acao": {
                        "type": "string",
                        "description": "A ação a executar, em linguagem natural."
                    },
                    "pensamento": {
                        "type": "string",
                        "description": (
                            "O que você está pensando/planejando com essa ação "
                            "(curto, 1-2 frases). Aparece no balão de pensamento "
                            "da visualização 3D e no log da jogada."
                        )
                    }
                },
                "required": ["acao", "pensamento"],
            },
        },
    ]


def _mcp_resposta(mid, result):
    return jsonify({"jsonrpc": "2.0", "id": mid, "result": result})


def _mcp_erro(mid, codigo, mensagem):
    return jsonify({"jsonrpc": "2.0", "id": mid,
                    "error": {"code": codigo, "message": mensagem}})


def _mcp_tool_iniciar(args):
    modelo = (args.get("modelo") or "").strip()
    if not modelo:
        return (
            "Partida NÃO iniciada: faltou o parâmetro 'modelo'.\n\n"
            "Antes de jogar, pergunte ao seu TUTOR (o humano que te conectou a "
            "este servidor) qual modelo de IA você é, e chame iniciar_jogo de "
            "novo com esse nome. Não invente nem chute um nome — muitas IAs "
            "não sabem ao certo qual modelo são, e esse nome identifica sua "
            "jogada no ranking e na página de análise."
        )
    obs = _iniciar_jogada(modelo, system_prompt="(jogando via MCP)",
                          modo=args.get("modo"), jogo_id=args.get("jogo"))
    extra = ""
    if run_modo == "turnos":
        extra = (" Modo turnos: uma ação por vez — o resultado só chega quando "
                 "a ação termina de verdade (andar leva tempo; sem "
                 "teletransporte). Ações enviadas em paralelo são recusadas.")
    return (f"{obs}\n\n"
            f"Partida iniciada — {run_jogo.get('nome', '?')} "
            f"(id: {run_id}, modo: {run_modo}). "
            f"Use a tool executar_acao para interagir com o ambiente.{extra}")


def _mcp_tool_listar(args):
    linhas = ["Fases/jogos disponíveis (use o 'id' em iniciar_jogo):"]
    padrao = jogos.jogo_padrao()
    for m in jogos.listar_jogos():
        marca = "  ← padrão" if m["id"] == padrao else ""
        linhas.append(
            f"\n• {m['id']} — {m['nome']} (fase {m.get('fase')}){marca}\n"
            f"  {m['descricao']}"
        )
    return "\n".join(linhas)


def _mcp_tool_acao(args):
    global current_thought
    acao       = (args.get("acao") or "").strip()
    pensamento = (args.get("pensamento") or "").strip()
    if not acao:
        return "Ação vazia. Informe uma ação em linguagem natural."
    if not pensamento:
        return ("Ação NÃO executada: faltou o parâmetro 'pensamento'. "
                "Diga em 1-2 frases o que você está pensando/planejando com "
                "essa ação — isso aparece no balão de pensamento da "
                "visualização 3D e no log, e ajuda os humanos a te acompanhar.")
    if env is None:
        return "Nenhuma partida em andamento. Use a tool iniciar_jogo primeiro."
    if env.estado["cofre_aberto"] or env.estado["passos"] >= env.max_passos:
        return ("A partida anterior já terminou. "
                "Use a tool iniciar_jogo para jogar de novo.")

    current_thought = pensamento   # alimenta o balão do watch e o histórico
    obs, reward, terminated, truncated, rejeitada = _executar_passo(acao)
    if rejeitada:
        return f"{obs}\n\n(A ação NÃO foi executada e não contou passo.)"
    rodape = f"[passo {env.estado['passos']} | score {env.estado['score']:+.0f}]"
    if terminated:
        rodape += (f"\n🏆 VITÓRIA! Cofre aberto em {env.estado['passos']} passos "
                   f"e {round(time.time() - env.estado['t0'], 1)}s. "
                   f"Veja a análise em http://localhost:{PORT}/analise")
    elif truncated:
        rodape += "\nLimite de passos atingido. A partida terminou sem vitória."
    return f"{obs}\n\n{rodape}"


@app.route('/mcp', methods=['POST', 'GET', 'DELETE', 'OPTIONS'])
def mcp():
    if request.method == 'OPTIONS':
        return '', 204
    if request.method != 'POST':
        # Não oferecemos stream SSE iniciado pelo servidor nem sessões
        return jsonify({"error": "Use POST com JSON-RPC 2.0"}), 405

    msg = request.get_json(silent=True)
    if msg is None:
        return _mcp_erro(None, -32700, "Parse error: corpo não é JSON"), 400
    if isinstance(msg, list):
        return _mcp_erro(None, -32600,
                         "Batch JSON-RPC não suportado (removido na spec 2025-06-18)"), 400

    metodo = msg.get("method", "")
    params = msg.get("params") or {}

    # Notificações (sem id) não recebem resposta: 202 Accepted
    if "id" not in msg:
        return '', 202
    mid = msg["id"]

    if metodo == "initialize":
        pedida = params.get("protocolVersion", MCP_VERSAO_PADRAO)
        versao = pedida if pedida in MCP_VERSOES_SUPORTADAS else MCP_VERSAO_PADRAO
        return _mcp_resposta(mid, {
            "protocolVersion": versao,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "cofre",
                "title": "O Cofre — Escape Room para IAs",
                "version": "2.0.0",
            },
            "instructions": (
                "Jogo de escape room para IAs. Use listar_jogos para ver as "
                "fases disponíveis (as maiores são mais difíceis), chame "
                "iniciar_jogo (escolhendo o 'jogo') para começar e executar_acao "
                "para interagir. O objetivo é abrir o cofre — explore a casa e "
                "descubra como, ninguém vai te dizer o que fazer."
            ),
        })

    if metodo == "ping":
        return _mcp_resposta(mid, {})

    if metodo == "tools/list":
        return _mcp_resposta(mid, {"tools": _construir_tools()})

    if metodo == "tools/call":
        nome = params.get("name", "")
        args = params.get("arguments") or {}
        try:
            if nome == "iniciar_jogo":
                texto = _mcp_tool_iniciar(args)
            elif nome == "listar_jogos":
                texto = _mcp_tool_listar(args)
            elif nome == "executar_acao":
                texto = _mcp_tool_acao(args)
            else:
                return _mcp_erro(mid, -32602, f"Tool desconhecida: {nome}")
            return _mcp_resposta(mid, {
                "content": [{"type": "text", "text": texto}],
                "isError": False,
            })
        except Exception as e:
            return _mcp_resposta(mid, {
                "content": [{"type": "text", "text": f"Erro ao executar a tool: {e}"}],
                "isError": True,
            })

    # Alguns clientes consultam mesmo sem a capability anunciada
    if metodo == "resources/list":
        return _mcp_resposta(mid, {"resources": []})
    if metodo == "prompts/list":
        return _mcp_resposta(mid, {"prompts": []})

    return _mcp_erro(mid, -32601, f"Método não suportado: {metodo}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("COFRE SERVER V2 — Modo Exploração")
    print("=" * 60)
    print(f"HTTP:  http://localhost:{PORT}   (mude com COFRE_PORT no .env)")
    print("Endpoints: /reset  /step  /current-game  /runs  /jogos  /health")
    print(f"MCP (Streamable HTTP): http://localhost:{PORT}/mcp")
    print("\nJOGOS DISPONIVEIS (src/jogos/ — descobertos automaticamente):")
    for m in jogos.listar_jogos():
        print(f"  - {m['id']:<14} {m['nome']}  (fase {m.get('fase')}, "
              f"{m['n_milestones']} milestones)")
    print("\nPAGINAS NO NAVEGADOR:")
    print(f"  Landing page:         http://localhost:{PORT}/")
    print(f"  Analise das jogadas:  http://localhost:{PORT}/analise")
    print(f"  Assistir em 3D:       http://localhost:{PORT}/watch")
    print("\nDiferença do V1:")
    print("  /reset e /step NÃO retornam valid_actions ao agente.")
    print("  O agente descobre os comandos por tentativa e erro.")
    print("\nLogs das jogadas (tempo + milestones) salvos em logs/*.json")
    print("=" * 60 + "\n")
    app.run(host='localhost', port=PORT, debug=False, use_reloader=False)
