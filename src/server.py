"""
Servidor HTTP do Cofre V2 — porta 5002.

Diferença chave do V1:
  /reset e /step NÃO retornam valid_actions ao agente.
  O agente descobre os comandos por tentativa e erro.

  /current-game AINDA retorna valid_actions para o watch 3D
  poder inferir os estados dos objetos na cena.

Roda: python server.py
"""

from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime
import sys
import os
import re
import time
import json

sys.path.insert(0, os.path.dirname(__file__))
from cofre import Cofre

app = Flask(__name__)
env = None

current_thought     = ""
god_message_pending = ""
god_message_count   = 0

# ── Log da jogada ─────────────────────────────────────────────────────────────

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

run_id            = None   # ex: 20260612_153000_omnikimi
run_model         = ""
run_started_iso   = ""
run_system_prompt = ""
historico         = []    # [{passo, acao, t, reward, resultado, pensamento, conversa}]
conversa_pendente = None  # última troca agente↔LLM, anexada ao próximo /step


def _salvar_log(venceu):
    """Grava o log da jogada atual em logs/<run_id>.json (uma única vez)."""
    global run_id
    if run_id is None or env is None:
        return None
    log = {
        "run_id":        run_id,
        "model":         run_model,
        "started_at":    run_started_iso,
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

BASE_DIR = os.path.dirname(__file__)


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/analise')
def pagina_analise():
    return send_from_directory(BASE_DIR, 'analise.html')


@app.route('/watch')
def pagina_watch():
    return send_from_directory(BASE_DIR, 'watch.html')


# ── Endpoints do agente (sem valid_actions) ──────────────────────────────────

@app.route('/reset', methods=['GET', 'POST', 'OPTIONS'])
def reset():
    """Inicia partida nova. NÃO retorna valid_actions — o agente explora.

    Aceita ?model=<nome> (ou JSON {"model": ...}) para identificar a IA no log.
    """
    global env, current_thought, god_message_pending, god_message_count
    global run_id, run_model, run_started_iso, run_system_prompt
    global historico, conversa_pendente
    if request.method == 'OPTIONS':
        return '', 204

    model = request.args.get('model', '')
    system_prompt = ''
    if request.is_json:
        dados = request.json or {}
        model = model or dados.get('model', '')
        system_prompt = dados.get('system_prompt', '')
    model = model.strip() or "desconhecido"

    env = Cofre()
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
    print(f"  [log] Nova jogada: {run_id} (modelo: {model})")

    return jsonify({
        "obs": obs,
        "steps": 0,
        "score": 0,
        "run_id": run_id,
        "success": True
    })


@app.route('/step', methods=['POST', 'OPTIONS'])
def step():
    """Executa ação. NÃO retorna valid_actions ao agente."""
    global conversa_pendente
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data   = request.json or {}
        action = data.get('action', '').strip()
        if not action:
            return jsonify({"success": False, "error": "Acao vazia"}), 400

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

        return jsonify({
            "obs":        obs,
            "reward":     reward,
            "terminated": terminated,
            "truncated":  truncated,
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
    return jsonify({
        "status":           "playing",
        "room":             env.estado["sala_atual"],
        "room_name":        s["nome"],
        "obs":              env._descricao_sala(),
        "inventory":        env.estado["inventario"],
        "steps":            env.estado["passos"],
        "score":            env.estado.get("score", 0),
        "terminated":       env.estado["cofre_aberto"],
        "valid_actions":    env._acoes_validas(),   # só para o watch
        "milestones":       env.estado["milestones"],
        "thought":          current_thought,
        "god_message_count": god_message_count
    })


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


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("COFRE SERVER V2 — Modo Exploração")
    print("=" * 60)
    print("HTTP:  http://localhost:5002")
    print("Endpoints: /reset  /step  /current-game  /runs  /health")
    print("\nPAGINAS NO NAVEGADOR:")
    print("  Analise das jogadas:  http://localhost:5002/analise")
    print("  Assistir em 3D:       http://localhost:5002/watch")
    print("\nDiferença do V1:")
    print("  /reset e /step NÃO retornam valid_actions ao agente.")
    print("  O agente descobre os comandos por tentativa e erro.")
    print("\nLogs das jogadas (tempo + milestones) salvos em logs/*.json")
    print("=" * 60 + "\n")
    app.run(host='localhost', port=5002, debug=False, use_reloader=False)
