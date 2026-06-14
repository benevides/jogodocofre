"""
Jogo do Cofre — Fase 1 (Fácil).

O agente não recebe nenhuma instrução sobre o que fazer ou onde procurar.
A API não expõe a lista de ações válidas. Observações são mínimas.
O agente deve descobrir os comandos, os objetos relevantes e os dígitos
apenas explorando a casa.

Código do cofre: 319
  1o dígito (3): número de canecas no armário da cozinha
  2o dígito (1): número riscado atrás do quadro no escritório
  3o dígito (9): número no papel da gaveta trancada do escritório

Este arquivo é um JOGO no padrão de src/jogos/ — é descoberto automaticamente.
"""

from ._base import estado_base


# Marcos que ajudam a resolver o enigma. Registrados com tempo e passo na
# primeira vez que o agente realiza cada descoberta.
MILESTONES = {
    "dica_bilhete":       "Leu o bilhete (dica geral)",
    "dica_quadro_antigo": "Leu o verso do quadro antigo (dica dos guardioes)",
    "digito1_canecas":    "Viu as canecas no armario da cozinha (1o digito)",
    "pegou_chave":        "Pegou a chave no quarto",
    "digito2_quadro":     "Olhou atras do quadro do escritorio (2o digito)",
    "destrancou_gaveta":  "Destrancou a gaveta do escritorio",
    "digito3_papel":      "Leu o papel da gaveta trancada (3o digito)",
    "cofre_aberto":       "Abriu o cofre",
}


def _salas():
    """Objetos falsos em todos os cômodos para forçar exploração."""
    return {
        "sala": {
            "nome": "Sala de Estar",
            "saidas": ["cozinha", "quarto", "escritorio"],
            "objetos": {
                "mesa": {
                    "tipo": "movel",
                    "desc": "Uma mesa de madeira escura. Superficie limpa."
                },
                "bilhete": {
                    "tipo": "nota",
                    "pego": False,
                    "milestone_examinar": "dica_bilhete",
                    "texto": (
                        "Um bilhete velho e rasgado. Partes ilegíveis, mas da pra ler: "
                        "'...o cofre... tres numeros... conta o que ve... olha por tras... "
                        "abre com a chave... junta os numeros...'"
                    )
                },
                "quadro_antigo": {
                    "tipo": "movel",
                    "milestone_examinar": "dica_quadro_antigo",
                    "desc": (
                        "Um quadro de paisagem desbotado. Voce o inclina para ver o verso. "
                        "Ha um papel colado atras, escrito a mao:\n"
                        "'Tres guardioes guardam os digitos:\n"
                        " O que sacia a sede revela o primeiro.\n"
                        " O que decora as paredes revela o segundo.\n"
                        " O que a chave almeja revela o terceiro.'"
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
                    "conteudo": "tres canecas",
                    "pista": "1",
                    "milestone_conteudo": "digito1_canecas"
                },
                "prateleira": {
                    "tipo": "movel",
                    "desc": "Uma prateleira de madeira. Esta vazia."
                },
                "fogao": {
                    "tipo": "movel",
                    "desc": "Um fogao velho. Frio. Nada em cima."
                },
            },
        },
        "quarto": {
            "nome": "Quarto",
            "saidas": ["sala"],
            "objetos": {
                "cama": {
                    "tipo": "movel",
                    "desc": "Uma cama arrumada. Voce verifica embaixo: nada."
                },
                "guarda_roupa": {
                    "tipo": "movel",
                    "desc": "Um guarda-roupa. Roupas velhas penduradas. Nada util."
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
                    "codigo": "319",
                    "aberto": False
                },
                "quadro": {
                    "tipo": "quadro",
                    "atras": "1",
                    "milestone_examinar": "digito2_quadro"
                },
                "gaveta": {
                    "tipo": "container",
                    "aberto": False,
                    "trancada": True,
                    "conteudo": "um papel com um numero: 9",
                    "milestone_destrancar": "destrancou_gaveta",
                    "milestone_conteudo": "digito3_papel"
                },
                "escrivaninha": {
                    "tipo": "movel",
                    "desc": "Uma escrivaninha coberta de poeira. Gavetas vazias."
                },
                "livro": {
                    "tipo": "movel",
                    "desc": "Um livro velho. Paginas em branco. Nada escrito."
                },
            },
        },
    }


def mundo():
    return estado_base(_salas(), sala_inicial="sala")


def solucao():
    """Solução de referência (sem ler o bilhete: 13 passos)."""
    return [
        "ir para cozinha", "abrir armario",            # tres canecas → 3
        "ir para sala", "ir para quarto",
        "abrir gaveta", "examinar gaveta", "pegar chave",
        "ir para sala", "ir para escritorio",
        "examinar quadro",                             # 1
        "usar chave em gaveta", "abrir gaveta",        # 9
        "digitar 319",
    ]


JOGO = {
    "id":          "cofre_fase1",
    "nome":        "Jogo do Cofre - Fase 1",
    "fase":        1,
    "ordem":       1,
    "cenario":     "cofre",
    "descricao":   "Escape room introdutório: três dígitos espalhados pela casa "
                   "formam o código do cofre, na ordem em que você os encontra.",
    "max_passos":  200,
    "milestones":  MILESTONES,
    "mundo":       mundo,
    "solucao":     solucao,
    # Parâmetros visuais que o /watch usa para desenhar a cena corretamente.
    "cena": {
        "mugs":          3,    # quantas canecas desenhar no armário
        "digito_quadro": "1",  # número riscado atrás do quadro do escritório
        "digito_papel":  "9",  # número no papel da gaveta trancada
    },
}
