"""
Jogo do Cofre — Fase 2 (Difícil).

Mesma casa da Fase 1 (mesmos cômodos, móveis e marcos — então a cena 3D do
/watch é reaproveitada), mas o enigma foi endurecido a partir do que se viu
nos logs das IAs jogando a Fase 1 (todas venciam, em 14–49 passos):

  • Os números mudaram e o código NÃO é a simples concatenação na ordem em que
    se encontra os dígitos. O bilhete/quadro agora exigem reordenar os dígitos
    e somar 1 a cada um antes de discar — um passo de raciocínio a mais.
  • Há NÚMEROS-CHAMARIZ espalhados em móveis irrelevantes (livro, escrivaninha,
    fogão, cama...). Quem não ler as pistas com atenção disca o código errado.
  • As dicas são mais vagas e avisam (de propósito) que a casa "mente".

Dígitos dos guardiões (valores crus, visíveis na cena 3D):
  sacia a sede    → 4 canecas no armário da cozinha
  decora paredes  → 7 riscado atrás do quadro do escritório
  a chave almeja  → 2 no papel da gaveta trancada

Regra do disco: ordem [paredes, chave, sede] = 7,2,4  →  +1 em cada  →  8,3,5
Código do cofre: 835
"""

from ._base import estado_base


# Marcos IDÊNTICOS aos da Fase 1: isso mantém a cena 3D e a página de análise
# funcionando sem mudanças (os efeitos do /watch são acionados por esses ids).
MILESTONES = {
    "dica_bilhete":       "Leu o bilhete (dica geral)",
    "dica_quadro_antigo": "Leu o verso do quadro antigo (regra do disco)",
    "digito1_canecas":    "Contou as canecas no armario (guardiao da sede)",
    "pegou_chave":        "Pegou a chave no quarto",
    "digito2_quadro":     "Olhou atras do quadro do escritorio (guardiao das paredes)",
    "destrancou_gaveta":  "Destrancou a gaveta do escritorio",
    "digito3_papel":      "Leu o papel da gaveta trancada (guardiao da chave)",
    "cofre_aberto":       "Abriu o cofre",
}


def _salas():
    return {
        "sala": {
            "nome": "Sala de Estar",
            "saidas": ["cozinha", "quarto", "escritorio"],
            "objetos": {
                "mesa": {
                    "tipo": "movel",
                    # chamariz: um número que NÃO entra no código
                    "desc": "Uma mesa escura. Grudado nela, um post-it desbotado: '0 0 0'."
                },
                "bilhete": {
                    "tipo": "nota",
                    "pego": False,
                    "milestone_examinar": "dica_bilhete",
                    "texto": (
                        "Um bilhete rasgado, quase ilegível: "
                        "'...o cofre quer tres digitos... mas esta casa MENTE: "
                        "ha numeros espalhados que nao servem pra nada. "
                        "Confie so nos tres guardioes do quadro... "
                        "e lembre que o cofre e velhaco com a ordem e com a conta...'"
                    )
                },
                "quadro_antigo": {
                    "tipo": "movel",
                    "milestone_examinar": "dica_quadro_antigo",
                    "desc": (
                        "Um quadro de paisagem desbotado. Atras, um papel escrito a mao:\n"
                        "'Tres guardioes guardam os digitos:\n"
                        " - o que sacia a sede;\n"
                        " - o que decora as paredes;\n"
                        " - o que a chave almeja.\n"
                        "Mas o disco do cofre e velhaco:\n"
                        " 1) some 1 ao numero de CADA guardiao;\n"
                        " 2) disque na ordem: PAREDES, depois CHAVE, depois SEDE.'"
                    )
                },
            },
        },
        "cozinha": {
            "nome": "Cozinha",
            "saidas": ["sala"],
            "objetos": {
                "armario": {
                    "tipo": "container",
                    "aberto": False,
                    "conteudo": "quatro canecas",   # guardiao da sede → 4
                    "pista": "4",
                    "milestone_conteudo": "digito1_canecas"
                },
                "prateleira": {
                    "tipo": "movel",
                    "desc": "Uma prateleira com um calendario velho aberto no dia 6."  # chamariz
                },
                "fogao": {
                    "tipo": "movel",
                    "desc": "Um fogao velho. O timer quebrado travou marcando 5."  # chamariz
                },
            },
        },
        "quarto": {
            "nome": "Quarto",
            "saidas": ["sala"],
            "objetos": {
                "cama": {
                    "tipo": "movel",
                    "desc": "Cama arrumada. Embaixo, so um chinelo tamanho 8. Nada util."  # chamariz
                },
                "guarda_roupa": {
                    "tipo": "movel",
                    "desc": "Guarda-roupa com roupas velhas. Etiqueta de lavanderia: n 3."  # chamariz
                },
                "gaveta": {
                    "tipo": "container",
                    "aberto": False,
                    "conteudo_item": "chave",
                    "milestone_pegar": "pegou_chave"
                },
            },
        },
        "escritorio": {
            "nome": "Escritorio",
            "saidas": ["sala"],
            "objetos": {
                "cofre": {
                    "tipo": "cofre",
                    "codigo": "835",   # = (paredes 7, chave 2, sede 4) +1 cada
                    "aberto": False
                },
                "quadro": {
                    "tipo": "quadro",
                    "atras": "7",      # guardiao das paredes → 7
                    "milestone_examinar": "digito2_quadro"
                },
                "gaveta": {
                    "tipo": "container",
                    "aberto": False,
                    "trancada": True,
                    "conteudo": "um papel com um numero: 2",   # guardiao da chave → 2
                    "milestone_destrancar": "destrancou_gaveta",
                    "milestone_conteudo": "digito3_papel"
                },
                "escrivaninha": {
                    "tipo": "movel",
                    "desc": "Escrivaninha empoeirada. Um recibo rasgado: 'total 49'."  # chamariz
                },
                "livro": {
                    "tipo": "movel",
                    # chamariz forte: parece um código pronto (127)
                    "desc": "Um livro velho aberto. So da pra ler, a lapis na margem: '1 2 7'."
                },
            },
        },
    }


def mundo():
    return estado_base(_salas(), sala_inicial="sala")


def solucao():
    """Solução de referência da Fase 2 (lê as pistas e aplica a regra)."""
    return [
        "examinar quadro_antigo",                      # regra: +1 e ordem paredes/chave/sede
        "ir para cozinha", "abrir armario",            # sede = 4
        "ir para sala", "ir para quarto",
        "abrir gaveta", "pegar chave",
        "ir para sala", "ir para escritorio",
        "examinar quadro",                             # paredes = 7
        "usar chave em gaveta", "abrir gaveta",        # chave = 2
        "digitar 835",                                 # (7,2,4) +1 = (8,3,5)
    ]


JOGO = {
    "id":          "cofre_fase2",
    "nome":        "Jogo do Cofre - Fase 2",
    "fase":        2,
    "ordem":       2,
    "cenario":     "cofre",
    "descricao":   "Mesma casa, enigma cruel: números-chamariz por toda parte, e "
                   "o código exige reordenar os dígitos dos guardiões e somar 1 a cada.",
    "max_passos":  250,
    "milestones":  MILESTONES,
    "mundo":       mundo,
    "solucao":     solucao,
    "cena": {
        "mugs":          4,    # quatro canecas agora
        "digito_quadro": "7",
        "digito_papel":  "2",
    },
}
