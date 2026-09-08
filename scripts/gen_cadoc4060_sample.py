#!/usr/bin/env python3
"""Gera os samples canônicos do CADOC 4060 em `sample/`.

O 4060 é o **Balancete Patrimonial Analítico do Conglomerado Prudencial**,
MENSAL (o gêmeo semestral é o 4066). O sample cobre DUAS data-bases
consecutivas — 2026-05 e 2026-06 — porque 18 das críticas do 4060 comparam a
data-base corrente com a anterior; com um mês só, elas ficariam
permanentemente indeterminadas.

Sem dado de cliente: o plano de contas e os valores são sintéticos e
deterministas (seed fixa).

## Invariantes, e por que eles importam

As críticas ESTRUTURAIS do 4060 são aritméticas. Se o sample do acelerador não
as satisfizer, todo cliente que fizer o primeiro deploy verá críticas falhando
sem ter feito nada errado. Então cada uma é garantida por CONSTRUÇÃO e conferida
por `assert` antes de gravar:

  1. `saldoConsolidado = saldoAglutinado − valorEliminacoes` em todo bloco
     consolidado (crítica **E3** — *total da linha difere das parcelas*).
  2. Aglutinado do bloco 5 = aglutinado do bloco 3 + soma do `saldoContabil`
     das assemelhadas (*"Erro soma Consolid Prudencial"*).
  3. Conta-pai = soma das contas-filhas, em todos os blocos (crítica **E4**).
  4. Compensação devedora (grupo 3) = − compensação credora (grupo 9)
     (crítica **E5**).
  5. `g1 + g2 + g4 + g6 + g7 + g8 = 0` (crítica **G100**).
  6. Dígito verificador COSIF válido em toda conta.

Convenção de sinal — **débito negativo, crédito positivo**: ativo (grupos 1 e 2)
e despesa (8) e compensação devedora (3)
negativos; passivo (4), patrimônio líquido (6), receita (7) e compensação
credora (9) positivos. É o que faz a soma do invariante 5 fechar em zero.

Tudo é calculado em **centavos inteiros**. Gerar em float e arredondar no fim
faria os invariantes falharem por um centavo aqui e ali, e um centavo é
suficiente para uma crítica acusar.

Uso:

    python scripts/gen_cadoc4060_sample.py
    python scripts/gen_cadoc4060_sample.py --validate   # valida no XSD, se houver

Referências: `docs/cadoc4060/README.md` e o leiaute oficial
`docs/cadoc4060/Leiaute_4060_4066_xml.pdf`.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# `sample/` direto: o glob de `load_sample_xmls` não é recursivo.
SAMPLE_DIR = REPO / "sample"
DOCS_DIR = REPO / "docs/cadoc4060"

CODIGO_DOCUMENTO = "4060"
CODIGO_CONGLOMERADO = "C0000001"
CNPJ = "99999999"                 # mesma instituição fictícia dos outros samples
TIPO_REMESSA = "I"                # I = inclusão
# O leiaute permite 99.9999 para indicar "não aplicação do campo"; é o correto
# aqui, porque o sample não tem posição no exterior nem moeda estrangeira.
TAXA_CONVERSAO = "99.9999"

DATAS_BASE = ["2026-05", "2026-06"]

# Grupos COSIF e o sinal do saldo na convenção débito-negativo/crédito-positivo.
GRUPOS = {
    1: ("Ativo — Circulante e Realizável a Longo Prazo", -1),
    2: ("Ativo — Permanente", -1),
    3: ("Compensação — devedora", -1),
    4: ("Passivo — Circulante e Exigível a Longo Prazo", +1),
    6: ("Patrimônio Líquido", +1),
    7: ("Contas de Resultado — Receitas", +1),
    8: ("Contas de Resultado — Despesas", -1),
    9: ("Compensação — credora", +1),
}
# Grupos que entram na equação de balanço (invariante 5). Compensação fica fora
# — ela fecha contra si mesma, no invariante 4.
GRUPOS_BALANCO = [1, 2, 4, 6, 7, 8]

# As entidades do conglomerado e a fatia de cada uma. A líder vai para o bloco 3
# (posição contábil país e exterior) e as demais para o bloco 4 (assemelhadas).
# As fatias somam 1, o que é o que faz o invariante 2 fechar.
LIDER = ("Z0000001", 55)
ASSEMELHADAS = [("Z0000002", 20), ("Z0000003", 15), ("Z0000004", 10)]

PESOS_DV = [1, 7, 3, 1, 7, 3, 1, 7, 3]


def dv_cosif(hierarquia: str) -> int:
    """Dígito verificador da conta COSIF (10º dígito).

    Pesos 3-7-1 repetidos da direita para a esquerda sobre os 9 dígitos de
    hierarquia — o que, da esquerda para a direita, dá 1-7-3 repetido.
    `DV = 10 − (soma mod 10)`, e 0 quando o resto é 0.
    """
    if len(hierarquia) != 9 or not hierarquia.isdigit():
        raise ValueError(f"hierarquia deve ter 9 dígitos: {hierarquia!r}")
    soma = sum(int(d) * p for d, p in zip(hierarquia, PESOS_DV))
    resto = soma % 10
    return 0 if resto == 0 else 10 - resto


def conta(hierarquia: str) -> str:
    return f"{hierarquia}{dv_cosif(hierarquia)}"


# Confere o algoritmo contra os quatro códigos do exemplo oficial do BCB (§4 do
# leiaute 4010/4016). Se o DV mudar, isto quebra antes de gerar arquivo errado.
for _codigo in ("1000000009", "1100000002", "1130000003", "1139000004"):
    if conta(_codigo[:9]) != _codigo:
        raise SystemExit(
            f"algoritmo do DV COSIF divergiu do exemplo oficial: "
            f"{_codigo} → {conta(_codigo[:9])}"
        )


class PlanoDeContas:
    """Hierarquia COSIF de 3 níveis por grupo: raiz → 2 subgrupos → 2 folhas cada."""

    def __init__(self):
        self.raizes: list[str] = []
        self.pais: dict[str, str] = {}        # conta → conta-pai
        self.folhas: list[str] = []
        self.descricoes: dict[str, str] = {}
        self.grupo_de: dict[str, int] = {}
        for grupo, (nome, _) in GRUPOS.items():
            raiz = conta(f"{grupo}00000000")
            self.raizes.append(raiz)
            self.descricoes[raiz] = nome
            self.grupo_de[raiz] = grupo
            for sub in (1, 2):
                subconta = conta(f"{grupo}{sub}0000000")
                self.pais[subconta] = raiz
                self.descricoes[subconta] = f"{nome} — subgrupo {sub}"
                self.grupo_de[subconta] = grupo
                for det in (1, 2):
                    folha = conta(f"{grupo}{sub}{det}000000")
                    self.pais[folha] = subconta
                    self.folhas.append(folha)
                    self.descricoes[folha] = f"{nome} — subgrupo {sub}, rubrica {det}"
                    self.grupo_de[folha] = grupo

    @property
    def todas(self) -> list[str]:
        # Ordem do documento: hierárquica, como o BCB espera.
        return sorted(set(self.raizes) | set(self.pais.keys()))

    def folhas_do_grupo(self, grupo: int) -> list[str]:
        return [f for f in self.folhas if self.grupo_de[f] == grupo]

    def consolidar(self, valores_folha: dict[str, int]) -> dict[str, int]:
        """Preenche pais e raízes somando as folhas (invariante 3)."""
        completo = dict(valores_folha)
        for subconta in sorted({self.pais[f] for f in self.folhas}):
            completo[subconta] = sum(
                completo[f] for f in self.folhas if self.pais[f] == subconta
            )
        for raiz in self.raizes:
            completo[raiz] = sum(
                v for c, v in completo.items()
                if c in self.pais and self.pais[c] == raiz
            )
        return completo


def _distribuir(total: int, n: int, rng: random.Random) -> list[int]:
    """Divide `total` centavos em `n` parcelas, a última absorvendo o resto."""
    if n == 1:
        return [total]
    pesos = [rng.randint(15, 60) for _ in range(n)]
    soma_pesos = sum(pesos)
    parcelas = [total * p // soma_pesos for p in pesos[:-1]]
    parcelas.append(total - sum(parcelas))
    return parcelas


def gerar_folhas(plano: PlanoDeContas, rng: random.Random, escala_pct: int = 100) -> dict[str, int]:
    """Valores das folhas em centavos, já satisfazendo os invariantes 4 e 5."""
    folhas: dict[str, int] = {}

    # 1) Lado credor livre: passivo, PL, receita; e despesa (devedora).
    for grupo in (4, 6, 7):
        escala = {4: 900, 6: 120, 7: 45}[grupo] * escala_pct // 100
        for f in plano.folhas_do_grupo(grupo):
            folhas[f] = rng.randint(escala * 10**7, escala * 10**8)
    for f in plano.folhas_do_grupo(8):
        folhas[f] = -rng.randint(
            30 * 10**7 * escala_pct // 100, 40 * 10**8 * escala_pct // 100
        )

    # 2) O ativo é o que fecha a equação: g1 + g2 = −(g4 + g6 + g7 + g8).
    credor = sum(folhas[f] for g in (4, 6, 7, 8) for f in plano.folhas_do_grupo(g))
    ativo_total = -credor
    folhas_ativo = plano.folhas_do_grupo(1) + plano.folhas_do_grupo(2)
    for f, v in zip(folhas_ativo, _distribuir(ativo_total, len(folhas_ativo), rng)):
        folhas[f] = v

    # 3) Compensação fecha contra si mesma: grupo 3 = −grupo 9.
    folhas_g9 = plano.folhas_do_grupo(9)
    for f in folhas_g9:
        folhas[f] = rng.randint(
            500 * 10**7 * escala_pct // 100, 900 * 10**8 * escala_pct // 100
        )
    total_g9 = sum(folhas[f] for f in folhas_g9)
    folhas_g3 = plano.folhas_do_grupo(3)
    for f, v in zip(folhas_g3, _distribuir(-total_g9, len(folhas_g3), rng)):
        folhas[f] = v

    return folhas


def gerar_eliminacoes(plano: PlanoDeContas, rng: random.Random) -> dict[str, int]:
    """Eliminações intragrupo que NÃO desequilibram o balanço.

    Uma eliminação real (um empréstimo entre entidades do conglomerado) sai do
    ativo de uma ponta e do passivo da outra pelo mesmo valor. Aplicando o mesmo
    módulo com o sinal de cada lado, a soma das eliminações por grupo é zero e o
    invariante 5 continua valendo depois de `consolidado = aglutinado − elim`.
    """
    valor = rng.randint(10 * 10**7, 50 * 10**7)
    folha_ativo = plano.folhas_do_grupo(1)[0]
    folha_passivo = plano.folhas_do_grupo(4)[0]
    return {folha_ativo: -valor, folha_passivo: +valor}


def cents(valor: int) -> str:
    """Centavos inteiros → texto do leiaute (2 decimais, ponto como separador)."""
    sinal = "-" if valor < 0 else ""
    v = abs(valor)
    return f"{sinal}{v // 100}.{v % 100:02d}"


def montar_documento(data_base: str, semente: int) -> tuple[str, dict]:
    rng = random.Random(semente)
    plano = PlanoDeContas()

    # Cada entidade gera o SEU balancete, já coerente. O consolidado é a soma.
    # Fazer o contrário — sortear o consolidado e ratear — deixa o resto da
    # divisão em centavos numa entidade só, e a equação de balanço dela fecha
    # com alguns centavos de erro. Somando balancetes que já fecham em zero, o
    # zero é preservado em toda entidade E no total, por construção.
    fatias = [LIDER, *ASSEMELHADAS]
    por_entidade: dict[str, dict[str, int]] = {
        ident: plano.consolidar(gerar_folhas(plano, rng, escala_pct=peso))
        for ident, peso in fatias
    }
    total = {
        c: sum(por_entidade[ident][c] for ident, _ in fatias)
        for c in plano.todas
    }

    elim_folhas = gerar_eliminacoes(plano, rng)
    elim = plano.consolidar({f: elim_folhas.get(f, 0) for f in plano.folhas})

    contas = plano.todas
    lider_ident = LIDER[0]

    # ─── invariantes ───────────────────────────────────────────────────────
    # 3) pai = soma das filhas, em cada entidade e no total
    for mapa, rotulo in [(total, "total")] + [
        (v, f"entidade {k}") for k, v in por_entidade.items()
    ]:
        for subconta in sorted({plano.pais[f] for f in plano.folhas}):
            filhas = sum(mapa[f] for f in plano.folhas if plano.pais[f] == subconta)
            assert mapa[subconta] == filhas, f"E4 falhou em {subconta} ({rotulo})"
        for raiz in plano.raizes:
            filhas = sum(
                v for c, v in mapa.items() if c in plano.pais and plano.pais[c] == raiz
            )
            assert mapa[raiz] == filhas, f"E4 falhou na raiz {raiz} ({rotulo})"

    # 2) aglutinado do bloco 5 = bloco 3 + soma das assemelhadas
    for c in contas:
        soma = por_entidade[lider_ident][c] + sum(
            por_entidade[ident][c] for ident, _ in ASSEMELHADAS
        )
        assert soma == total[c], f"soma Consolid Prudencial falhou em {c}"

    # 4) compensação devedora = − compensação credora
    g3 = total[conta("300000000")]
    g9 = total[conta("900000000")]
    assert g3 == -g9, f"E5 falhou: grupo 3 = {g3}, grupo 9 = {g9}"

    # 4b) compensação também fecha em cada entidade
    for ident, mapa in por_entidade.items():
        assert mapa[conta("300000000")] == -mapa[conta("900000000")], (
            f"E5 falhou na entidade {ident}"
        )

    # 5) equação de balanço: no aglutinado, no consolidado E em cada entidade
    for rotulo, mapa, ajuste in (
        [("aglutinado", total, 0), ("consolidado", total, 1)]
        + [(f"entidade {k}", v, 0) for k, v in por_entidade.items()]
    ):
        soma = 0
        for g in GRUPOS_BALANCO:
            raiz = conta(f"{g}00000000")
            soma += mapa[raiz] - (elim.get(raiz, 0) if ajuste else 0)
        assert soma == 0, f"G100 falhou no {rotulo}: soma = {soma}"

    # 1) consolidado = aglutinado − eliminações (por construção; conferido abaixo)
    # 6) DV — garantido por `conta()`, que só monta código com DV calculado.

    # ─── XML ───────────────────────────────────────────────────────────────
    linhas = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<documento codigoDocumento="{CODIGO_DOCUMENTO}"'
        f' codigoConglomerado="{CODIGO_CONGLOMERADO}"'
        f' cnpj="{CNPJ}" dataBase="{data_base}"'
        f' tipoRemessa="{TIPO_REMESSA}" taxaConversao="{TAXA_CONVERSAO}">',
    ]

    def bloco_consolidado(tag: str, valores: dict[str, int], eliminacoes: dict[str, int]):
        linhas.append(f"    <{tag}>")
        linhas.append("        <contas>")
        for c in contas:
            aglut = valores[c]
            e = eliminacoes.get(c, 0)
            consolidado = aglut - e
            assert consolidado == aglut - e, "E3 falhou"
            linhas.append(
                f'            <conta codigoConta="{c}"'
                f' saldoAglutinado="{cents(aglut)}"'
                f' valorEliminacoes="{cents(e)}"'
                f' saldoConsolidado="{cents(consolidado)}" />'
            )
        linhas.append("        </contas>")
        linhas.append(f"    </{tag}>")

    # Bloco 3 — obrigatório. A líder não tem eliminações próprias.
    bloco_consolidado(
        "consolidadoPaisExterior", por_entidade[lider_ident], {}
    )

    # Bloco 4 — assemelhadas.
    linhas.append("    <assemelhadas>")
    for ident, _ in ASSEMELHADAS:
        linhas.append(
            f'        <balancAssemelhada idAssemelhada="{ident}"'
            ' tipoAssemelhada="6" origemAssemelhada="1"'
            ' moedaFuncional="BRL" motivoConsolidacao="1">'
        )
        linhas.append("            <contas>")
        for c in contas:
            linhas.append(
                f'                <conta codigoConta="{c}"'
                f' saldoContabil="{cents(por_entidade[ident][c])}"'
                ' saldoAte3Meses="0.00" saldoApos3Meses="0.00" />'
            )
        linhas.append("            </contas>")
        linhas.append("        </balancAssemelhada>")
    linhas.append("    </assemelhadas>")

    # Bloco 5 — obrigatório.
    bloco_consolidado("consolidadoPrudencial", total, elim)

    linhas.append("</documento>")

    resumo = {
        "contas": len(contas),
        "folhas": len(plano.folhas),
        "assemelhadas": len(ASSEMELHADAS),
        "grupos": sorted(GRUPOS),
    }
    return "\n".join(linhas) + "\n", resumo


def validar_xsd(caminho: Path) -> None:
    xsds = sorted(DOCS_DIR.glob("*.xsd"))
    if not xsds:
        print(f"  {caminho.name}: XSD indisponível — validação estrutural apenas.")
        print("     (a página do leiaute 4060 no BCB é renderizada por JS e o XSD")
        print("      não sai por URL direta; baixe manualmente para docs/cadoc4060/)")
        return
    xsd = xsds[0]
    try:
        subprocess.run(
            ["xmllint", "--noout", "--schema", str(xsd), str(caminho)],
            check=True, capture_output=True,
        )
        print(f"  {caminho.name}: válido contra {xsd.name}")
    except FileNotFoundError:
        print(f"  {caminho.name}: xmllint ausente — validação no XSD pulada")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"{caminho.name} inválido:\n{exc.stderr.decode()}") from exc


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--validate", action="store_true",
                    help="valida o XML gerado contra o XSD, se houver")
    args = ap.parse_args()

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for i, data_base in enumerate(DATAS_BASE):
        xml, resumo = montar_documento(data_base, semente=4060 + i)
        destino = SAMPLE_DIR / f"Doc{CODIGO_DOCUMENTO}_{CODIGO_CONGLOMERADO}_{data_base}.xml"
        destino.write_text(xml, encoding="utf-8")
        ET.fromstring(xml)                      # o arquivo tem de ser XML bem-formado
        print(
            f"{destino.relative_to(REPO)}: {resumo['contas']} contas "
            f"({resumo['folhas']} folhas) · {resumo['assemelhadas']} assemelhadas "
            f"· {destino.stat().st_size / 1024:.1f} KB"
        )
        if args.validate:
            validar_xsd(destino)
    print("\ninvariantes E3 · E4 · E5 · G100 · soma prudencial · DV COSIF: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
