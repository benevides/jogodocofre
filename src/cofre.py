"""
Motor do Cofre V2 — agora genérico (orientado a dados).

O motor NÃO conhece nenhum jogo específico: ele recebe uma definição de jogo
(um dict no padrão de src/jogos/) e roda em cima do estado que essa definição
produz. Cada jogo descreve as salas, os objetos, os marcos e o código do cofre;
a lógica de explorar/examinar/abrir/usar/digitar é a mesma para todos.

Para adicionar um jogo novo, NÃO mexa aqui: crie um arquivo em src/jogos/
(veja jogos/cofre_fase1.py). Ele é descoberto automaticamente.

API (Gymnasium-style), igual ao V1:
    obs, info = env.reset()
    obs, reward, terminated, truncated, info = env.step(acao)
"""

from dataclasses import dataclass, field
import time


COMANDOS = ("ir para <sala> | olhar | examinar <obj> | abrir <obj> | "
            "pegar <obj> | usar <obj> em <obj> | digitar <numero> | inventario")


@dataclass
class Cofre:
    jogo: dict = None          # definição do jogo (dict de src/jogos/)
    max_passos: int = None
    estado: dict = field(default=None)

    def __post_init__(self):
        # Sem jogo informado → carrega o jogo padrão (Fase 1) do registro.
        if self.jogo is None:
            import jogos
            self.jogo = jogos.carregar_jogo(jogos.jogo_padrao())
            if self.jogo is None:
                raise RuntimeError("Nenhum jogo encontrado em src/jogos/.")
        if self.max_passos is None:
            self.max_passos = self.jogo.get("max_passos", 200)
        if self.estado is None:
            self.estado = self.jogo["mundo"]()

    @property
    def milestones_def(self):
        return self.jogo.get("milestones", {})

    # ── API Gymnasium ────────────────────────────────────────────────────────

    def reset(self):
        self.estado = self.jogo["mundo"]()
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

    def _marcar(self, mid):
        """Registra uma milestone (uma única vez) com tempo e passo."""
        if not mid or any(m["id"] == mid for m in self.estado["milestones"]):
            return
        self.estado["milestones"].append({
            "id": mid,
            "label": self.milestones_def.get(mid, mid),
            "passo": self.estado["passos"],
            "t": round(time.time() - self.estado["t0"], 2),
        })

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
        if d["tipo"] != "container":
            self._marcar(d.get("milestone_examinar"))

        if d["tipo"] == "nota":
            return d["texto"]

        if d["tipo"] == "quadro":
            return f"Voce olha atras do quadro. Ha um numero riscado na madeira: {d['atras']}."

        if d["tipo"] == "container":
            if d.get("aberto"):
                self._marcar(d.get("milestone_conteudo"))
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
            self._marcar(d.get("milestone_conteudo"))
            conteudo = d.get("conteudo") or d.get("conteudo_item") or "vazio"
            return f"O {alvo} ja esta aberto. Dentro ha: {conteudo}."
        if d.get("trancada"):
            return f"O {alvo} esta trancado. Precisa de alguma coisa para abrir."
        d["aberto"] = True
        if d.get("conteudo_item"):
            return f"Voce abre o {alvo}. Ha algo dentro."
        self._marcar(d.get("milestone_conteudo"))
        return f"Voce abre o {alvo}. Dentro ha: {d['conteudo']}."

    def _pegar(self, alvo):
        objs = self._objs()
        for nome, d in objs.items():
            if d["tipo"] == "container" and d.get("aberto") and d.get("conteudo_item") == alvo:
                self.estado["inventario"].append(alvo)
                d["conteudo_item"] = None
                self._marcar(d.get("milestone_pegar"))
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
            self._marcar(objs[alvo].get("milestone_destrancar"))
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
            self._marcar("cofre_aberto")
            return f"Voce digita {num}... CLICK. O cofre abre! VOCE VENCEU."
        return f"Voce digita {num}... nada acontece. Codigo errado."


# ── Loop de demonstração / autoteste ─────────────────────────────────────────

def loop(jogo=None, mostrar=True):
    """Roda a solução de referência de um jogo. Útil para validar uma fase."""
    import jogos
    if jogo is None:
        jogo = jogos.carregar_jogo(jogos.jogo_padrao())
    elif isinstance(jogo, str):
        jogo = jogos.carregar_jogo(jogo)

    env = Cofre(jogo=jogo)
    obs, info = env.reset()
    if mostrar:
        print(f"\n=== {jogo['nome']} ===")
        print(obs + "\n")

    acoes = iter(jogo.get("solucao", lambda: [])())
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
        print("MILESTONES:")
        for m in env.estado["milestones"]:
            print(f"  [{m['t']:>7.2f}s  passo {m['passo']:>3}]  {m['label']}")
    return {"venceu": venceu, "passos": env.estado["passos"], "score": total,
            "milestones": env.estado["milestones"]}


if __name__ == "__main__":
    import jogos
    # Autoteste: roda a solução de referência de cada jogo descoberto.
    for meta in jogos.listar_jogos():
        r = loop(meta["id"], mostrar=True)
        status = "OK" if r["venceu"] else "FALHOU"
        print(f"\n>>> {meta['nome']}: {status} em {r['passos']} passos\n")
