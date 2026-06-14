"""
Registro de jogos — descoberta automática.

══════════════════════════════════════════════════════════════════════════════
COMO ADICIONAR UM JOGO NOVO
══════════════════════════════════════════════════════════════════════════════
Crie um arquivo .py nesta pasta (src/jogos/) que defina, no nível do módulo,
um dicionário chamado JOGO. Pronto: ele é descoberto sozinho e passa a aparecer
no servidor, no MCP (a IA pode escolher jogá-lo) e nas páginas web. Não é preciso
mexer em mais nada. Use cofre_fase1.py como modelo.

Contrato de um JOGO
───────────────────
Obrigatórios:
    "nome":       str   — nome exibido (ex: "Jogo do Cofre - Fase 1")
    "mundo":      callable() -> dict   — retorna o estado inicial (use _base.estado_base)
    "milestones": dict {id: rótulo}    — marcos do jogo (registrados pelo motor)

Opcionais (têm default):
    "id":         str   — identificador único        (default: nome do arquivo)
    "fase":       int   — número da fase              (default: 0)
    "ordem":      int   — ordem de exibição/listagem  (default: igual a "fase")
    "cenario":    str   — qual cena 3D o /watch usa   (default: "cofre")
    "descricao":  str   — descrição curta             (default: "")
    "max_passos": int   — limite de passos da partida (default: 200)
    "cena":       dict  — parâmetros visuais p/ o watch (ex: nº de canecas, dígitos)
    "solucao":    callable() -> list[str]  — sequência que vence (usada nos testes)

Arquivos com prefixo "_" (ex: _base.py) são ignorados pelo registro.
"""

import importlib
import pkgutil

_CACHE = None

# Chaves obrigatórias num JOGO bem-formado.
_OBRIGATORIAS = ("nome", "mundo", "milestones")


def _descobrir():
    """Varre a pasta e carrega todo módulo que exponha um dict JOGO válido."""
    jogos = {}
    for info in pkgutil.iter_modules(__path__):
        nome = info.name
        if nome.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{nome}")
        except Exception as e:  # um jogo quebrado não derruba os outros
            print(f"  [jogos] '{nome}' falhou ao importar: {e}")
            continue
        jogo = getattr(mod, "JOGO", None)
        if not isinstance(jogo, dict):
            continue
        faltando = [k for k in _OBRIGATORIAS if k not in jogo]
        if faltando:
            print(f"  [jogos] '{nome}' ignorado: faltam chaves {faltando}")
            continue

        jogo = dict(jogo)  # cópia rasa para preencher defaults sem mutar o módulo
        jogo.setdefault("id", nome)
        jogo.setdefault("fase", 0)
        jogo.setdefault("ordem", jogo.get("fase", 0))
        jogo.setdefault("cenario", "cofre")
        jogo.setdefault("descricao", "")
        jogo.setdefault("max_passos", 200)
        jogo.setdefault("cena", {})
        jogos[jogo["id"]] = jogo
    return jogos


def _todos(forcar=False):
    global _CACHE
    if _CACHE is None or forcar:
        _CACHE = _descobrir()
    return _CACHE


def recarregar():
    """Redescobre os jogos (útil ao soltar um arquivo novo sem reiniciar)."""
    return _todos(forcar=True)


def listar_jogos():
    """Metadados (sem os callables) de todos os jogos, na ordem de exibição."""
    out = []
    for j in sorted(_todos().values(), key=lambda x: (x["ordem"], x["id"])):
        out.append({
            "id":            j["id"],
            "nome":          j["nome"],
            "fase":          j.get("fase"),
            "ordem":         j["ordem"],
            "cenario":       j["cenario"],
            "descricao":     j["descricao"],
            "max_passos":    j["max_passos"],
            "cena":          j.get("cena", {}),
            "n_milestones":  len(j.get("milestones", {})),
        })
    return out


def carregar_jogo(jogo_id):
    """Retorna o JOGO completo (com callables) pelo id, ou None se não existir."""
    return _todos().get(jogo_id)


def jogo_padrao():
    """ID do primeiro jogo na ordem (normalmente a Fase 1)."""
    lst = listar_jogos()
    return lst[0]["id"] if lst else None
