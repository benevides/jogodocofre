"""
Servidor HTTP do Cofre V2 — porta 5002.

Diferença chave do V1:
  /reset e /step NÃO retornam valid_actions ao agente.
  O agente descobre os comandos por tentativa e erro.

  /current-game AINDA retorna valid_actions para o watch 3D
  poder inferir os estados dos objetos na cena.

Roda: python server.py
"""

from flask import Flask, jsonify, request
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from cofre import Cofre

app = Flask(__name__)
env = None

current_thought     = ""
god_message_pending = ""
god_message_count   = 0


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


# ── Endpoints do agente (sem valid_actions) ──────────────────────────────────

@app.route('/reset', methods=['GET'])
def reset():
    """Inicia partida nova. NÃO retorna valid_actions — o agente explora."""
    global env, current_thought, god_message_pending, god_message_count
    env = Cofre()
    obs, info = env.reset()
    current_thought     = ""
    god_message_pending = ""
    god_message_count   = 0
    return jsonify({
        "obs": obs,
        "steps": 0,
        "score": 0,
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

        obs, reward, terminated, truncated, info = env.step(action)
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
        "thought":          current_thought,
        "god_message_count": god_message_count
    })


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


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "version": "v2"})


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("COFRE SERVER V2 — Modo Exploração")
    print("=" * 60)
    print("HTTP:  http://localhost:5002")
    print("Endpoints: /reset  /step  /current-game  /health")
    print("\nDiferença do V1:")
    print("  /reset e /step NÃO retornam valid_actions ao agente.")
    print("  O agente descobre os comandos por tentativa e erro.")
    print("\nAbra watch.html no navegador para assistir.")
    print("=" * 60 + "\n")
    app.run(host='localhost', port=5002, debug=False, use_reloader=False)
