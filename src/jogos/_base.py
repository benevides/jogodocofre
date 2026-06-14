"""
Utilitários compartilhados pelos jogos.

Arquivos com prefixo "_" NÃO são tratados como jogos pelo registro
(veja jogos/__init__.py). Coloque aqui código reusável entre fases/jogos.
"""

import time


def estado_base(salas, sala_inicial="sala"):
    """Monta o dicionário de estado padrão que o motor (Cofre) consome.

    Um jogo só precisa descrever as `salas` (e em qual sala o agente começa);
    o resto da estrutura — inventário, passos, score, milestones, cronômetro —
    é igual para todos e fica centralizado aqui.
    """
    return {
        "sala_atual":  sala_inicial,
        "inventario":  [],
        "cofre_aberto": False,
        "passos":      0,
        "score":       0,
        "milestones":  [],
        "t0":          time.time(),
        "salas":       salas,
    }
