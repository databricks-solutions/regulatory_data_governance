#!/usr/bin/env python3
"""Gera os samples canônicos do CADOC 2011 (DDR) em `sample/`.

O DDR é **diário**, então o sample cobre alguns dias úteis de dois meses
consecutivos (2026-03 e 2026-04) — o suficiente para exercitar o rollup mensal
do `gold.processing_state` e a flag `is_ultima_do_mes` do `gold.posicao_2011`
sem inflar o repositório.

Os valores são deterministas (seed fixa) e internamente coerentes:

  - `sum(detalhamentoDDR/@valorDetalhe) == conta/@valorConta` em toda conta
    detalhada. ⚠️ Este invariante NÃO é uma regra oficial do leiaute: o próprio
    arquivo de exemplo do BCB o viola na conta 141000. Ele vale no sample porque
    é o comportamento correto esperado, e o check DQX correspondente é `warn`.
  - `161000 >= 181000` — satisfaz a crítica oficial 4693 (tipo E).
  - nenhuma chave (conta, país, moeda, posição) repetida — satisfaz a 4751.
  - 141000/151000 derivadas da diferença entre 111000 e 121000.
  - 710000 (VPRM) = soma das parcelas 310000 + 503000 + 610000.

Uso:

    python scripts/gen_ddr2011_sample.py            # grava em sample/
    python scripts/gen_ddr2011_sample.py --validate # grava e valida contra o XSD

Referências: `docs/ddr2011/README.md`, leiaute oficial v5 e
`docs/ddr2011/DDR_2011_XSD_V01072020.xsd`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.sax.saxutils import quoteattr

REPO = Path(__file__).resolve().parent.parent
SAMPLE_DIR = REPO / "sample"
XSD = REPO / "docs/ddr2011/DDR_2011_XSD_V01072020.xsd"

CNPJ = "99999999"          # mesma instituição fictícia dos outros samples
CODIGO_DOCUMENTO = "2011"
TIPO_ENVIO = "I"           # I = inclusão (Anexo 1)

# Datas-base do sample: últimos dias úteis de março/2026 e primeiros de abril.
# Um mês com 3 remessas e outro com 2 deixa visível que `is_ultima_do_mes`
# marca exatamente uma linha por mês.
DATAS_BASE = [
    dt.date(2026, 3, 27),
    dt.date(2026, 3, 30),
    dt.date(2026, 3, 31),
    dt.date(2026, 4, 1),
    dt.date(2026, 4, 2),
]

# Parâmetros do Anexo 2 — responsável pelo envio do DLO.
PARAMETROS = [
    ("31", "Maria Silva Santos"),
    ("32", "61-3414-1000"),
    ("33", "dlo@bancoexemplo.com.br"),
]

# Moedas da cesta (Anexo 5) e países (Anexo 7) usados nos detalhamentos.
MOEDAS_CESTA = ["USD", "EUR", "JPY", "GBP", "CHF"]
MOEDAS_FORA_CESTA = ["ARS", "CAD", "CNY", "MXN"]
PAISES = ["BR", "US", "GB", "KY", "LU"]

# Códigos de elemento (Anexo 3).
ELEM_PAIS = "81"
ELEM_MOEDA = "83"
ELEM_POSICAO = "84"        # Anexo 6: 1 = País, 2 = Exterior

CENTS = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


class Conta:
    """Uma tag `<conta>`, com detalhamentos opcionais.

    `detalhes` é uma lista de (valor, {codigoElemento: valorElemento}); a soma
    dos valores define o `valorConta` quando a conta é detalhada.
    """

    def __init__(self, codigo: str, valor: Decimal, detalhes=None):
        self.codigo = codigo
        self.detalhes = detalhes or []
        self.valor = _q(sum((d[0] for d in self.detalhes), Decimal(0))) if self.detalhes else _q(valor)

    def to_xml(self, indent: str = "  ") -> str:
        attrs = f'codigoConta="{self.codigo}" valorConta="{self.valor}"'
        if not self.detalhes:
            return f"{indent}<conta {attrs}/>"
        lines = [f"{indent}<conta {attrs}>", f"{indent}  <detalhamentosDDR>"]
        for valor, elementos in self.detalhes:
            lines.append(f'{indent}    <detalhamentoDDR valorDetalhe="{_q(valor)}">')
            # Ordem estável dos elementos: país, moeda, posição (códigos 81, 83, 84).
            for codigo in (ELEM_PAIS, ELEM_MOEDA, ELEM_POSICAO):
                if codigo in elementos:
                    lines.append(
                        f'{indent}      <detalhe codigoElemento="{codigo}" '
                        f'valorElemento="{elementos[codigo]}"/>'
                    )
            lines.append(f"{indent}    </detalhamentoDDR>")
        lines += [f"{indent}  </detalhamentosDDR>", f"{indent}</conta>"]
        return "\n".join(lines)


def _exposicao_por_moeda(rng: random.Random, base: Decimal, posicao: str) -> list:
    """Detalhamentos (moeda × posição país/exterior) de uma exposição cambial.

    Chave = (moeda, posição) — única por construção, o que satisfaz a crítica
    4751 ("chaves duplicadas entre posição e moeda").
    """
    out = []
    for moeda in MOEDAS_CESTA + MOEDAS_FORA_CESTA:
        peso = Decimal(rng.randrange(40, 400)) / Decimal(1000)
        out.append((_q(base * peso), {ELEM_MOEDA: moeda, ELEM_POSICAO: posicao}))
    return out


def _liquidez_por_pais_moeda(rng: random.Random, base: Decimal) -> list:
    """Detalhamentos (país × moeda) dos ativos de alta liquidez."""
    out = []
    for pais in PAISES:
        for moeda in MOEDAS_CESTA[:3]:
            peso = Decimal(rng.randrange(20, 180)) / Decimal(1000)
            out.append((_q(base * peso), {ELEM_PAIS: pais, ELEM_MOEDA: moeda}))
    return out


def build_contas(data_base: dt.date, rng: random.Random) -> list[Conta]:
    """Monta o conjunto de contas de uma data-base.

    Cobre um subconjunto representativo dos 92 códigos do Anexo 4 — os blocos
    que uma instituição com carteira de negociação reporta de fato — em vez dos
    92 indiscriminadamente: o leiaute prevê o envio apenas das contas aplicáveis.
    """
    # Escala diária: pequena variação em torno de R$ 1,5 bi para o dia render uma
    # série temporal visível no dashboard sem virar ruído.
    escala = Decimal(1_500_000_000) * (Decimal(950 + rng.randrange(0, 100)) / Decimal(1000))

    ativa_comprada = _exposicao_por_moeda(rng, escala * Decimal("0.62"), "1")
    passiva_vendida = _exposicao_por_moeda(rng, escala * Decimal("0.41"), "2")

    total_comprada = _q(sum((d[0] for d in ativa_comprada), Decimal(0)))
    total_vendida = _q(sum((d[0] for d in passiva_vendida), Decimal(0)))
    liquida = total_comprada - total_vendida

    # 141000/151000 são mutuamente exclusivas pelo sinal da posição líquida.
    liquida_comprada = _q(liquida) if liquida > 0 else Decimal("0.00")
    liquida_vendida = _q(-liquida) if liquida < 0 else Decimal("0.00")

    # Crítica 4693: 161000 (posições vendidas no PL) NÃO pode ser inferior a
    # 181000 (excesso da posição vendida para hedge no exterior).
    hedge_excesso = _q(escala * Decimal("0.031"))
    vendidas_pl = _q(hedge_excesso * Decimal("1.4"))

    # Parcelas de requerimento de capital.
    rwacam = _q(escala * Decimal("0.081"))
    exposicao_cambial = _q(rwacam / Decimal("1.2"))
    var_normal = _q(escala * Decimal("0.019"))
    var_estressado = _q(var_normal * Decimal("1.6"))
    vprmpad = _q(escala * Decimal("0.043"))
    vprmmi = _q(escala * Decimal("0.036"))
    vprm = _q(rwacam + vprmpad + vprmmi)

    contas = [
        # --- Bloco 1: exposição em ouro, moeda estrangeira e variação cambial ---
        Conta("111000", Decimal(0), ativa_comprada),
        Conta("121000", Decimal(0), passiva_vendida),
        Conta("131000", _q(escala * Decimal("0.055"))),
        Conta("132000", _q(escala * Decimal("0.048"))),
        Conta("141000", liquida_comprada),
        Conta("151000", liquida_vendida),
        Conta("161000", vendidas_pl),
        Conta("171000", _q(escala * Decimal("0.074"))),
        Conta("181000", hedge_excesso),
        # --- Bloco 2: ativos de alta liquidez e entradas de caixa ---
        Conta("210000", Decimal(0), _liquidez_por_pais_moeda(rng, escala * Decimal("0.22"))),
        Conta("220000", _q(escala * Decimal("0.091"))),
        Conta("230000", _q(escala * Decimal("0.130"))),
        Conta("240000", _q(escala * Decimal("0.026"))),
        # --- Bloco 31: RWACAM ---
        Conta("310000", rwacam),
        Conta("310100", exposicao_cambial),
        Conta("310101", _q(exposicao_cambial * Decimal("0.72"))),
        Conta("310102", _q(exposicao_cambial * Decimal("0.28"))),
        Conta("310105", Decimal("1.20")),          # Fator F''
        # --- Bloco 4: RWAJUR / RWACOM / RWAACS (abordagem padronizada) ---
        # 410100: as Instruções mandam "Informar o valor 100" (percentual do fator
        # de incorporação S). 410101: multiplicador MPRE diário, entre 1 e 3,
        # informado EM PERCENTAGEM (Circular 3.634/2013).
        Conta("410100", Decimal("100.00")),
        Conta("410101", Decimal("285.00")),
        Conta("410200", _q(var_normal + var_estressado)),
        Conta("410201", var_normal),
        Conta("410202", var_estressado),
        Conta("410400", _q(escala * Decimal("0.012"))),
        Conta("410500", _q(escala * Decimal("0.009"))),
        Conta("410600", _q(escala * Decimal("0.007"))),
        Conta("410700", _q(escala * Decimal("0.004"))),
        Conta("410800", _q(escala * Decimal("0.006"))),
        Conta("410900", _q(escala * Decimal("0.005"))),
        Conta("411000", _q(escala * Decimal("0.002"))),   # CVA (a partir de 07/2023)
        # --- Bloco 5: RWAMPAD ---
        Conta("501000", _q(escala * Decimal("0.038"))),
        Conta("502000", _q(escala * Decimal("0.033"))),
        Conta("503000", vprmpad),
        Conta("504000", Decimal("100.00")),        # S1 — fator de transição, em %
        Conta("506000", Decimal("100.00")),        # S2 — fator de incorporação, em %
        # --- Bloco 6: RWAMINT (modelo interno) ---
        Conta("610000", vprmmi),
        Conta("620000", _q(vprmmi * Decimal("0.83"))),
        Conta("620200", _q(vprmmi * Decimal("0.21"))),
        Conta("620500", _q(vprmmi * Decimal("0.46"))),
        Conta("630000", _q(vprmmi * Decimal("1.31"))),
        # --- Bloco 7: total ---
        Conta("710000", vprm),
    ]
    return contas


def build_document(data_base: dt.date) -> str:
    # Seed derivada da data-base: regenerar produz exatamente o mesmo arquivo.
    rng = random.Random(int(data_base.strftime("%Y%m%d")))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append(
        f'<documentoDDR cnpj="{CNPJ}" dataBase="{data_base.isoformat()}" '
        f'codigoDocumento="{CODIGO_DOCUMENTO}" tipoEnvio="{TIPO_ENVIO}">'
    )
    lines.append("  <parametros>")
    for codigo, valor in PARAMETROS:
        lines.append(
            f'    <parametro codigoParametro="{codigo}" valorParametro={quoteattr(valor)}/>'
        )
    lines.append("  </parametros>")
    lines.append("  <contas>")
    for conta in build_contas(data_base, rng):
        lines.append(conta.to_xml("    "))
    lines.append("  </contas>")
    lines.append("</documentoDDR>")
    return "\n".join(lines) + "\n"


def validate(paths: list[Path]) -> bool:
    try:
        from lxml import etree
    except ImportError:
        print("  [validate] lxml não instalado — pulando validação XSD.")
        return True

    schema = etree.XMLSchema(etree.parse(str(XSD)))
    ok = True
    for path in paths:
        doc = etree.parse(str(path))
        if schema.validate(doc):
            print(f"  [validate] {path.name}: VÁLIDO contra o XSD oficial")
        else:
            ok = False
            print(f"  [validate] {path.name}: INVÁLIDO")
            for error in schema.error_log:
                print(f"      linha {error.line}: {error.message}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true",
                        help="valida os arquivos gerados contra o XSD oficial do BCB")
    args = parser.parse_args()

    SAMPLE_DIR.mkdir(exist_ok=True)
    written: list[Path] = []
    for data_base in DATAS_BASE:
        path = SAMPLE_DIR / f"Doc2011_{CNPJ}_{data_base.isoformat()}.xml"
        path.write_text(build_document(data_base), encoding="utf-8")
        written.append(path)
        print(f"gerado {path.relative_to(REPO)} ({path.stat().st_size:,} bytes)")

    if args.validate and not validate(written):
        raise SystemExit("algum sample não validou contra o XSD")


if __name__ == "__main__":
    main()
