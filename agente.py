"""
Agente Autônomo do Cofre V2 — Modo Exploração

Diferenças do V1:
  - Nenhuma lista de ações válidas é recebida da API
  - O agente descobre os comandos por tentativa e erro
  - System prompt mínimo: só o objetivo, sem guia de como jogar
  - Qualquer ação é enviada ao servidor; respostas inválidas ensinam o agente

Configuração via .env:
    API_URL      = URL OpenAI-compatible (ex: http://localhost:8000/v1/chat/completions)
    API_KEY      = chave (deixar vazio para APIs locais)
    API_MODEL    = nome do modelo
    COFRE_SERVER = URL do server.py (default: http://localhost:5002)
    VERBOSE      = true/false

Uso:
    python server.py           (em terminal separado)
    python agente.py
"""

import os
import re
import requests
import json
import time
from dotenv import load_dotenv

load_dotenv()

API_URL      = os.getenv("API_URL",      "http://localhost:8000/v1/chat/completions")
API_KEY      = os.getenv("API_KEY",      "").strip()
API_MODEL    = os.getenv("API_MODEL",    "model")
COFRE_SERVER = os.getenv("COFRE_SERVER", "http://localhost:5002")
VERBOSE      = os.getenv("VERBOSE",      "true").lower() == "true"

# ── System prompt mínimo — sem guia, sem lista de comandos ──────────────────

SYSTEM_PROMPT = """\
Você está em uma casa desconhecida. Em algum lugar há um cofre trancado.
Seu objetivo: abrir o cofre.

Ninguém vai te dizer o que fazer. Explore e descubra por conta própria.

Você pode tentar qualquer ação em linguagem natural. O ambiente vai responder.
Se uma ação não funcionar, tente algo diferente.

Responda sempre neste formato:
PENSAMENTO: [o que você sabe, o que ainda falta descobrir, e por que vai fazer essa ação]
ACAO: [a ação que você vai executar]
"""

# ── LLM ─────────────────────────────────────────────────────────────────────

def call_llm(obs, historico=None, god_message=None):
    """
    Chama a LLM sem fornecer lista de ações válidas.
    O agente aprende com as respostas do ambiente.
    """
    if historico is None:
        historico = []

    historico_str = ""
    if historico:
        linhas = []
        for i, e in enumerate(historico[-15:]):
            resultado = e["resultado"][:100]
            linhas.append(f"  {i+1:>2}. {e['acao']}\n      → {resultado}")
        historico_str = "\n\nHistórico (ação → resultado):\n" + "\n".join(linhas)

    god_str = ""
    if god_message:
        god_str = f"\n\n⚡ DICA DO OPERADOR: {god_message}\n"

    user_message = f"""Estado atual:
{obs}{historico_str}{god_str}

PENSAMENTO: [analise o que você descobriu até agora e o que vai tentar]
ACAO: [sua próxima ação]"""

    payload = {
        "model":    API_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message}
        ],
        "stream":      False,
        "temperature": 0.5,
    }

    headers = {"Content-Type": "application/json"}
    if API_KEY and API_KEY.lower() not in ("", "local"):
        headers["Authorization"] = f"Bearer {API_KEY}"

    for tentativa in range(1, 4):
        try:
            if VERBOSE:
                sufixo = f" (tentativa {tentativa}/3)" if tentativa > 1 else ""
                print(f"  [LLM] Consultando {API_MODEL}...{sufixo}")

            r = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()

            pensamento, acao = "", ""
            if "PENSAMENTO:" in texto and "ACAO:" in texto:
                partes    = texto.split("ACAO:")
                pensamento = partes[0].replace("PENSAMENTO:", "").strip()
                acao       = partes[1].strip().split("\n")[0].strip()
            else:
                acao = texto.strip()
                pensamento = "(sem pensamento)"

            acao = acao.strip('"\'').strip()

            if VERBOSE:
                print(f"  [PENSA] {pensamento[:90]}...")
                print(f"  [ACAO]  '{acao}'")

            return pensamento, acao

        except requests.exceptions.Timeout:
            print(f"  ⚠  Timeout (tentativa {tentativa}/3)")
            if tentativa < 3:
                time.sleep(tentativa * 3)
            else:
                return None, None

        except requests.exceptions.ConnectionError:
            print(f"  ⚠  Sem conexão (tentativa {tentativa}/3)")
            if tentativa < 3:
                time.sleep(tentativa * 2)
            else:
                return None, None

        except requests.exceptions.HTTPError as e:
            print(f"  ✗  HTTP {e.response.status_code}")
            return None, None

        except (KeyError, json.JSONDecodeError):
            print(f"  ⚠  Resposta fora do padrão (tentativa {tentativa}/3)")
            if tentativa < 3:
                time.sleep(2)
            else:
                return None, None

        except Exception as e:
            print(f"  ⚠  Erro: {e} (tentativa {tentativa}/3)")
            if tentativa < 3:
                time.sleep(2)
            else:
                return None, None

    return None, None


# ── Chamadas ao servidor ─────────────────────────────────────────────────────

def reset_cofre():
    try:
        r = requests.get(f"{COFRE_SERVER}/reset", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"✗ Erro no reset: {e}")
        return {"success": False}


def step_cofre(action):
    try:
        r = requests.post(f"{COFRE_SERVER}/step",
                          json={"action": action}, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"✗ Erro no step: {e}")
        return {"success": False}


def get_god_message():
    try:
        r = requests.get(f"{COFRE_SERVER}/god-message", timeout=3)
        d = r.json()
        return d.get("message", ""), d.get("count", 0)
    except Exception:
        return "", 0


def send_thought(pensamento):
    try:
        requests.post(f"{COFRE_SERVER}/thought",
                      json={"thought": pensamento}, timeout=3)
    except Exception:
        pass


# ── Loop principal ───────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("AGENTE COFRE V2 — Modo Exploração Autônoma")
    print("=" * 70)
    print(f"LLM:      {API_URL}")
    print(f"Modelo:   {API_MODEL}")
    print(f"Servidor: {COFRE_SERVER}")
    print("─" * 70)
    print("Diferença do V1: o agente NÃO recebe lista de ações válidas.")
    print("Ele descobre o que pode fazer tentando e errando.")
    print("=" * 70 + "\n")

    print("🔄 Iniciando partida...")
    res = reset_cofre()
    if not res.get("success"):
        print("✗ Não foi possível conectar ao servidor.")
        print(f"  Certifique-se de que server.py está rodando em {COFRE_SERVER}")
        return

    obs      = res["obs"]
    steps    = 0
    score    = 0.0
    historico = []
    god_count = 0

    print("✓ Partida iniciada!\n")
    print("OBSERVAÇÃO INICIAL:")
    print("─" * 70)
    print(obs)
    print("─" * 70 + "\n")

    while True:
        turno = steps + 1

        print(f"\n{'#' * 70}")
        print(f"# TURNO {turno:>3}  |  passos={steps}  score={int(score):+d}  god={god_count}⚡")
        print(f"{'#' * 70}")
        print("\nOBSERVAÇÃO:")
        print("=" * 70)
        print(obs)
        print("=" * 70 + "\n")

        # Dica divina
        god_msg, god_count = get_god_message()
        if god_msg:
            print(f"  ⚡ MENSAGEM DIVINA: {god_msg}\n")

        # Consulta LLM
        pensamento, acao = call_llm(obs, historico, god_msg or None)

        if acao is None:
            print("  ⏳ LLM não respondeu. Aguardando 5s...\n")
            time.sleep(5)
            continue

        if pensamento and pensamento != "(sem pensamento)":
            print(f"\n  💭 {pensamento}")
            send_thought(pensamento)

        print(f"\n  ✅ AÇÃO → '{acao}'")
        print(f"{'─' * 70}\n")
        time.sleep(0.3)

        # Executa — sem validação prévia; o jogo responde ao que for inválido
        res = step_cofre(acao)
        if not res.get("success"):
            print(f"\n✗ Erro no servidor: {res.get('error')}")
            break

        obs        = res["obs"]
        steps      = res["steps"]
        score      = res["score"]
        terminated = res["terminated"]

        resultado = obs.split("\n")[0][:120]
        historico.append({"acao": acao, "resultado": resultado})

        if terminated:
            print(f"\n{'#' * 70}")
            print(f"# FIM DE JOGO — turno {steps}")
            print(f"{'#' * 70}")
            print("\nOBSERVAÇÃO FINAL:")
            print("=" * 70)
            print(obs)
            print("=" * 70)
            print(f"\n{'=' * 70}")
            print("🎉  VITÓRIA!")
            print(f"{'=' * 70}")
            print(f"  Passos    : {steps}")
            print(f"  Score     : {int(score):+d}")
            print(f"  God Msgs  : {god_count} {'⚡' * god_count if god_count else '(nenhuma)'}")
            print(f"  Caminho   : {' → '.join(e['acao'] for e in historico)}")
            print(f"{'=' * 70}\n")
            break

        if res.get("truncated"):
            print(f"\n⏱ Limite de passos atingido. Partida encerrada.")
            break

    print("Agente finalizado.\n")


if __name__ == "__main__":
    main()
