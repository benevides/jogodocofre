"""
Utilitários compartilhados pelos jogos + REFERÊNCIA do mundo (salas/objetos).

Arquivos com prefixo "_" NÃO são tratados como jogos pelo registro
(veja jogos/__init__.py). Coloque aqui código reusável entre fases/jogos.

══════════════════════════════════════════════════════════════════════════════
COMO DESCREVER AS SALAS E OS OBJETOS (o motor cofre.py interpreta este formato)
══════════════════════════════════════════════════════════════════════════════
`salas` é um dict {id_sala: sala}. Cada sala:

    "<id_sala>": {
        "nome":    "Cozinha",                 # nome exibido
        "saidas":  ["sala", "corredor"],      # ids de salas vizinhas (ir para ...)
        "objetos": { "<id_obj>": {...}, ... } # objetos da sala
    }

Cada objeto tem um "tipo". Os tipos que o motor entende:

  tipo "movel"  — cenário/decoração. Só responde a "examinar".
      {"tipo": "movel", "desc": "texto do que a IA vê ao examinar"}
      Ótimo para CHAMARIZ (decoys): um número falso no texto engana a IA.

  tipo "nota"   — papel/bilhete que dá uma dica e pode ser pego.
      {"tipo": "nota", "texto": "...", "milestone_examinar": "id_milestone"}

  tipo "quadro" — esconde um dígito atrás dele (revelado ao examinar).
      {"tipo": "quadro", "atras": "1", "milestone_examinar": "id_milestone"}

  tipo "container" — armário/gaveta. Abre (e pode estar trancado).
      Com conteúdo de texto (uma pista):
        {"tipo": "container", "aberto": False, "conteudo": "tres canecas",
         "milestone_conteudo": "id"}
      Com um ITEM que pode ser pego (ex: a chave):
        {"tipo": "container", "aberto": False, "conteudo_item": "chave",
         "milestone_pegar": "id"}
      Trancado (precisa de "usar <item> em <obj>" para destrancar):
        {..., "trancada": True, "milestone_destrancar": "id"}

  tipo "cofre"  — o objetivo. Abre com "digitar <numero>".
      {"tipo": "cofre", "codigo": "319", "aberto": False}
      Abrir o cofre dispara automaticamente a milestone "cofre_aberto".

Chaves "milestone_*" são opcionais: registram um marco (com tempo e passo) na
1ª vez que a IA faz aquela descoberta. O id deve existir no dict `milestones`
do JOGO. A milestone "cofre_aberto" é registrada pelo motor ao abrir o cofre.

Veja jogos/cofre_fase1.py (fácil) e cofre_fase2.py (difícil, com chamarizes)
como exemplos completos.
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
