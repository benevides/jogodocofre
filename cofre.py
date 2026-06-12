"""
O Cofre V2 — Versão de Exploração.

O agente não recebe nenhuma instrução sobre o que fazer ou onde procurar.
A API não expõe a lista de ações válidas. Observações são mínimas.
O agente deve descobrir os comandos, os objetos relevantes e os dígitos
apenas explorando a casa.

Código do cofre: 319
  1o dígito (3): número de canecas no armário da cozinha
  2o dígito (1): número riscado atrás do quadro no escritório
  3o dígito (9): número no papel da gaveta trancada do escritório

API (mesmo formato do V1, Gymnasium-style):
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step(acao)
"""

from dataclasses import dataclass, field


COMANDOS = ("ir para <sala> | olhar | examinar <obj> | abrir <obj> | "
            "pegar <obj> | usar <obj> em <obj> | digitar <numero> | inventario")


def mundo_inicial():
    """Estado inicial. Objetos falsos em todos os cômodos para forçar exploração."""
    return {
        "sala_atual": "sala",
        "inventario": [],
        "cofre_aberto": False,
        "passos": 0,
        "score": 0,
        "salas": {
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
                        "texto": (
                            "Um bilhete velho e rasgado. Partes ilegíveis, mas da pra ler: "
                            "'...o cofre... tres numeros... conta o que ve... olha por tras... "
                            "abre com a chave... junta os numeros...'"
                        )
                    },
                    "quadro_antigo": {
                        "tipo": "movel",
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
                        "pista": "1"
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
                        "conteudo_item": "chave"
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
                        "atras": "1"
                    },
                    "gaveta": {
                        "tipo": "container",
                        "aberto": False,
                        "trancada": True,
                        "conteudo": "um papel com um numero: 9"
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
        },
    }


@dataclass
class Cofre:
    max_passos: int = 200
    estado: dict = field(default_factory=mundo_inicial)

    # ── API Gymnasium ────────────────────────────────────────────────────────

    def reset(self):
        self.estado = mundo_inicial()
        return "Ha um cofre nesta casa. Explore.\n" + self._descricao_sala(), \
               {"acoes_validas": self._acoes_validas()}

    def step(self, acao: str):
        self.estado["passos"] += 1
        resultado = self._aplicar(acao)
        terminated = self.estado["cofre_aberto"]
        truncated = self.estado["passos"] >= self.max_passos and not terminated
        reward = 100.0 if terminated else -1.0
        self.estado["score"] += reward
        obs = resultado
        if not terminated:
            obs += "\n" + self._descricao_sala()
        return obs, reward, terminated, truncated, {"acoes_validas": self._acoes_validas()}

    # ── Texto que o agente enxerga ───────────────────────────────────────────

    def _descricao_sala(self):
        """Versão V2: mínima, sem dicas de interação."""
        s = self.estado["salas"][self.estado["sala_atual"]]
        items = []
        for o, d in s["objetos"].items():
            if d.get("pego"):
                continue
            estado = ""
            if d["tipo"] == "container":
                if d.get("aberto"):
                    estado = "(aberto)"
                elif d.get("trancada"):
                    estado = "(trancado)"
                else:
                    estado = "(fechado)"
            elif d["tipo"] == "cofre":
                estado = "(trancado)" if not d.get("aberto") else "(aberto)"
            items.append(f"{o} {estado}".strip())
        vis = ", ".join(items) if items else "nada"
        return (f"Voce esta na {s['nome']}. Ha aqui: {vis}. "
                f"Saidas: {', '.join(s['saidas'])}.")

    # ── Ações válidas (uso interno do servidor — não exposto ao agente) ──────

    def _acoes_validas(self):
        s = self.estado["salas"][self.estado["sala_atual"]]
        acoes = ["olhar", "inventario"]
        acoes += [f"ir para {x}" for x in s["saidas"]]
        for o, d in s["objetos"].items():
            if d.get("pego"):
                continue
            acoes.append(f"examinar {o}")
            if d["tipo"] == "container":
                if not d.get("aberto"):
                    acoes.append(f"abrir {o}")
                elif d.get("conteudo_item"):
                    acoes.append(f"pegar {d['conteudo_item']}")
            if d["tipo"] == "nota":
                acoes.append(f"pegar {o}")
            if d["tipo"] == "cofre":
                acoes.append("digitar <numero>")
        if "chave" in self.estado["inventario"]:
            acoes.append("usar chave em gaveta")
        return acoes

    # ── Lógica das ações ─────────────────────────────────────────────────────

    def _objs(self):
        return self.estado["salas"][self.estado["sala_atual"]]["objetos"]

    def _aplicar(self, acao: str) -> str:
        a = acao.lower().strip()

        if a in ("inventario", "inventory", "i"):
            inv = ", ".join(self.estado["inventario"]) or "vazio"
            return f"Inventario: {inv}."

        if a in ("olhar", "look", "l"):
            return "Voce olha ao redor."

        if a.startswith(("ir para ", "ir ", "go to ", "go ")):
            for prefixo in ("ir para ", "ir ", "go to ", "go "):
                if a.startswith(prefixo):
                    destino = a[len(prefixo):].strip()
                    break
            saidas = self.estado["salas"][self.estado["sala_atual"]]["saidas"]
            if destino in saidas:
                self.estado["sala_atual"] = destino
                return f"Voce vai para {self.estado['salas'][destino]['nome']}."
            return f"Nao da pra ir para '{destino}' daqui. Saidas: {', '.join(saidas)}."

        for prefixo in ("examinar ", "ver ", "examine ", "look at ", "olhar ",
                        "investigar ", "inspecionar "):
            if a.startswith(prefixo):
                alvo = a[len(prefixo):].strip()
                return self._examinar(alvo)

        for prefixo in ("abrir ", "open ", "abre "):
            if a.startswith(prefixo):
                alvo = a[len(prefixo):].strip()
                return self._abrir(alvo)

        for prefixo in ("pegar ", "take ", "pega ", "get ", "apanhar "):
            if a.startswith(prefixo):
                alvo = a[len(prefixo):].strip()
                return self._pegar(alvo)

        for prefixo in ("usar ", "use ", "usa ", "utilizar "):
            if a.startswith(prefixo):
                return self._usar(a)

        for prefixo in ("digitar ", "enter ", "inserir ", "codigo ", "digito ",
                        "digitar codigo ", "colocar codigo "):
            if a.startswith(prefixo):
                num = "".join(c for c in a if c.isdigit())
                return self._digitar(num)

        return (f"Nao entendi '{acao}'. "
                "Tente: examinar, abrir, pegar, usar, ir para, digitar, olhar, inventario.")

    def _examinar(self, alvo):
        objs = self._objs()
        if alvo not in objs:
            return f"Nao ha '{alvo}' aqui."
        d = objs[alvo]

        if d["tipo"] == "nota":
            return d["texto"]

        if d["tipo"] == "quadro":
            return f"Voce olha atras do quadro. Ha um numero riscado na madeira: {d['atras']}."

        if d["tipo"] == "container":
            if d.get("aberto"):
                conteudo = d.get("conteudo") or d.get("conteudo_item") or "vazio"
                return f"Dentro do {alvo} ha: {conteudo}."
            if d.get("trancada"):
                return f"O {alvo} esta trancado."
            return f"O {alvo} esta fechado."

        if d["tipo"] == "cofre":
            if d.get("aberto"):
                return "O cofre esta aberto."
            return "Um cofre de aco pesado. Na frente, um painel com botoes numerados."

        if d["tipo"] == "movel":
            return d.get("desc", f"Voce examina o(a) {alvo}. Nada de especial.")

        return f"Voce examina o(a) {alvo}."

    def _abrir(self, alvo):
        objs = self._objs()
        if alvo not in objs or objs[alvo]["tipo"] != "container":
            return f"Nao da pra abrir '{alvo}'."
        d = objs[alvo]
        if d.get("aberto"):
            conteudo = d.get("conteudo") or d.get("conteudo_item") or "vazio"
            return f"O {alvo} ja esta aberto. Dentro ha: {conteudo}."
        if d.get("trancada"):
            return f"O {alvo} esta trancado. Precisa de alguma coisa para abrir."
        d["aberto"] = True
        if d.get("conteudo_item"):
            return f"Voce abre o {alvo}. Ha algo dentro."
        return f"Voce abre o {alvo}. Dentro ha: {d['conteudo']}."

    def _pegar(self, alvo):
        objs = self._objs()
        for nome, d in objs.items():
            if d["tipo"] == "container" and d.get("aberto") and d.get("conteudo_item") == alvo:
                self.estado["inventario"].append(alvo)
                d["conteudo_item"] = None
                return f"Voce pega: {alvo}."
        if alvo in objs and objs[alvo]["tipo"] == "nota":
            objs[alvo]["pego"] = True
            self.estado["inventario"].append(alvo)
            return f"Voce pega: {alvo}."
        return f"Nao da pra pegar '{alvo}'."

    def _usar(self, a):
        for sep in (" em ", " na ", " no ", " on ", " with "):
            if sep in a:
                item, alvo = a.split(sep, 1)
                for prefixo in ("usar ", "use ", "usa ", "utilizar "):
                    if item.startswith(prefixo):
                        item = item[len(prefixo):]
                        break
                item = item.strip()
                alvo = alvo.strip()
                break
        else:
            return "Formato: usar <item> em <objeto>."
        if item not in self.estado["inventario"]:
            return f"Voce nao tem '{item}'."
        objs = self._objs()
        if alvo in objs and objs[alvo].get("trancada"):
            objs[alvo]["trancada"] = False
            return f"Voce usa a {item} e destranca o {alvo}. Agora da pra abrir."
        return f"Nao ha como usar {item} em {alvo} aqui."

    def _digitar(self, num):
        objs = self._objs()
        if "cofre" not in objs:
            return "Nao ha cofre aqui para digitar."
        cofre = objs["cofre"]
        if cofre.get("aberto"):
            return "O cofre ja esta aberto."
        if not num:
            return "Digite um numero. Ex: digitar 123"
        if num == cofre["codigo"]:
            cofre["aberto"] = True
            self.estado["cofre_aberto"] = True
            return f"Voce digita {num}... CLICK. O cofre abre! VOCE VENCEU."
        return f"Voce digita {num}... nada acontece. Codigo errado."


# ── Demo ─────────────────────────────────────────────────────────────────────

def solucao_otima():
    """Solução de referência (sem ler o bilhete: 13 passos)."""
    return iter([
        "ir para cozinha", "abrir armario",            # tres canecas → 3
        "ir para sala", "ir para quarto",
        "abrir gaveta", "examinar gaveta", "pegar chave",
        "ir para sala", "ir para escritorio",
        "examinar quadro",                             # 1
        "usar chave em gaveta", "abrir gaveta",        # 9
        "digitar 319",
    ])


def loop(agente_fn, mostrar=True):
    env = Cofre()
    obs, info = env.reset()
    if mostrar:
        print(obs + "\n")
    acoes = agente_fn()
    total = 0.0
    while True:
        try:
            acao = next(acoes)
        except StopIteration:
            break
        obs, reward, terminated, truncated, info = env.step(acao)
        total += reward
        if mostrar:
            print(f"> {acao}")
            print(obs)
            print(f"  [reward={reward:+.0f}  total={total:+.0f}  passo={env.estado['passos']}]\n")
        if terminated or truncated:
            break
    venceu = env.estado["cofre_aberto"]
    if mostrar:
        print("=" * 60)
        print(f"RESULTADO: {'VITORIA' if venceu else 'falhou'} | "
              f"passos={env.estado['passos']} | score={total:+.0f}")
    return {"venceu": venceu, "passos": env.estado["passos"], "score": total}


if __name__ == "__main__":
    loop(solucao_otima)
