#!/usr/bin/env python3
"""Gera um Doc 3040 sintético de tamanho ARBITRÁRIO (dezenas de GiB) para teste
de escala da ingestão bronze.

Por que existe: o gerador do demo (`demo/notebooks/scr3040_generator/`) monta a
árvore inteira com `lxml.etree` em memória, o que é exatamente o modo de falha
que queremos reproduzir. Este aqui **emite texto em streaming**, com memória
constante (~alguns MB), independente do tamanho do arquivo.

## Para que serve

1. **Reproduzir** o `OutOfMemoryError: Java heap space` em
   `XmlTokenizer.readUntilEndElement` que o bronze 3040 dá com arquivo grande —
   `rowTag="Doc3040"` bufferiza o documento todo como UMA String Java, e o
   `char[]` do Java satura em 2.147.483.647 elementos (~2 GiB de texto ASCII).
   Acima disso não existe heap nem instância que resolva.
2. **Provar a correção** (`rowTag="Cli"`, memória O(maior cliente)) no mesmo
   arquivo que quebrava.
3. **Exercitar o particionamento** que o leiaute exige acima de 4.000 MB:
   `--max-part-mib` corta em partes com `Parte` sequencial, `TpArq="F"` só na
   última e sem cliente repetido entre partes.

⚠️ O monolito gerado com `--max-part-mib 0` **viola de propósito** a regra de
particionamento do BACEN (>4.000 MB). É um reprodutor de falha, não uma remessa.

## Dados

Sintético e determinista (seed fixa). CNPJ default `99999999`, o mesmo dos
samples do repo — nunca um CNPJ de cliente. Todos os valores de domínio foram
colhidos de `sample/Doc3040_99999999_2026-03_R1_P1.xml`, então os checks DQX de
domínio passam limpos: o arquivo estressa o parser, não as regras.

Só clientes PJ (`Tp="2"`, `PorteCli` 0–4), como o sample canônico limpo, para
não gerar violação acidental de `porte_cli_in_dominio_por_tipo`.

A variedade dos atributos vem de um pool de N blocos `<Cli>` pré-renderizados
que ciclam; o que é único por cliente é a IDENTIDADE (`Cd` e, por consequência,
o `IPOC`). Suficiente para teste de parser e volumetria, não para realismo
estatístico.

## Uso

    # monolito de ~20 GiB (reprodutor da falha) — fora do repo, git é público
    python scripts/gen_doc3040_scale_sample.py --target-gib 20

    # a MESMA volumetria, particionada como o leiaute manda (~40 partes)
    python scripts/gen_doc3040_scale_sample.py --target-gib 20 --max-part-mib 500

    # smoke test com validação XML completa
    python scripts/gen_doc3040_scale_sample.py --target-gib 0.02 --validate

Rodando DENTRO do workspace (evita subir 20 GiB pela rede — recomendado),
aponte a saída direto para o Volume de landing:

    --out-dir /Volumes/rc18_catalog/landing/scr_xml/3040
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

try:
    REPO_ROOT = Path(__file__).resolve().parents[1]
except NameError:
    # Executado inline (notebook / exec) — sem `__file__`, e portanto sem repo
    # a proteger; o guarda-corpo de `--out-dir` vira no-op.
    REPO_ROOT = None

# Marcador do código do cliente: 8 bytes, EXATAMENTE a largura de `Cd`. Como o
# `bytes.replace` não muda o tamanho do bloco, o tamanho de cada `<Cli>` é
# conhecido ANTES de escrever — é isso que permite planejar o corte em partes e
# o `TotalCli` de cada uma sem uma segunda passada.
CD_MARK = b"#CLICODE"

XML_DECL = b"<?xml version='1.0' encoding='UTF-8'?>\n"
FOOTER = b"</Doc3040>\n"

# Domínios colhidos do sample canônico (500 clientes / 1.271 operações).
AUTORZC = ("S", "N")
PORTE_CLI = ("0", "1", "2", "3", "4")
TP_CTRL = ("01", "02", "03", "04")
MOD = "0101"
NATU_OP = "01"
ORIGEM_REC = ("0101", "0102", "0199", "0201", "0299")
INDX = ("11", "24", "25", "29", "31", "32", "39", "41", "42", "43", "49", "51",
        "52", "53", "54", "91", "99")
VAR_CAMB = "790"
CARAC_ESPECIAL = (
    "01", "01;02", "01;03", "01;05", "01;07", "02", "02;03", "02;04", "02;05",
    "02;06", "02;07", "03", "03;04", "03;05", "03;06", "04", "04;05", "04;06",
    "04;07", "05", "05;06", "05;07", "06", "06;07", "07",
)
GAR_TP = ("0101", "0102", "0201", "0205", "0321", "0424", "0901", "0902")
# Vértices de vencimento observados, com o peso do sample (1 vértice por Op).
VENC_VERTICES = ("v110", "v120", "v130", "v140", "v150", "v150", "v160", "v160",
                 "v160", "v165", "v170", "v175")
# Distribuição do sample: 522 Ops sem garantia, 495 com 1, 254 com 2.
GAR_COUNT = (0, 0, 0, 0, 1, 1, 1, 1, 2, 2)
# 1.271 Ops / 500 clientes = 2,54 — média 2,5 aqui.
OPS_PER_CLI = (1, 2, 2, 3, 3, 4)


def _date(rng: random.Random, y0: int, y1: int) -> str:
    return f"{rng.randint(y0, y1)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def _money(rng: random.Random, lo: int, hi: int) -> str:
    return f"{rng.randint(lo * 100, hi * 100) / 100:.2f}"


def build_templates(cnpj: str, dt_base: str, n: int, seed: int) -> list[bytes]:
    """Pré-renderiza `n` blocos `<Cli>` com o código do cliente como marcador."""
    rng = random.Random(seed)
    cd = CD_MARK.decode()
    out: list[bytes] = []

    for _ in range(n):
        porte = rng.choice(PORTE_CLI)
        rows = [
            f'  <Cli Tp="2" Cd="{cd}" Autorzc="{rng.choice(AUTORZC)}"'
            f' PorteCli="{porte}" TpCtrl="{rng.choice(TP_CTRL)}"'
            f' IniRelactCli="{_date(rng, 2016, 2025)}"'
            f' FatAnual="{_money(rng, 10_000, 90_000_000)}">'
        ]

        for op_seq in range(rng.choice(OPS_PER_CLI)):
            contrt = f"{rng.randint(1, 999):03d}{op_seq:03d}{rng.randint(0, 999):03d}"
            vlr = _money(rng, 500, 900_000)
            tje = f"{rng.randint(155, 6500) / 100:.2f}"
            rows.append(
                f'    <Op DetCli="{rng.randrange(10 ** 14):014d}" Contrt="{contrt}"'
                f' NatuOp="{NATU_OP}" Mod="{MOD}"'
                f' OrigemRec="{rng.choice(ORIGEM_REC)}" Indx="{rng.choice(INDX)}"'
                f' PercIndx="{rng.randint(10_000, 13_000) / 100:.2f}"'
                f' VarCamb="{VAR_CAMB}" DtVencOp="{_date(rng, 2026, 2031)}"'
                f' CEP="{rng.randrange(10 ** 8):08d}"'
                f' TaxEft="{tje}" DtContr="{_date(rng, 2021, 2026)}"'
                f' ProvConsttd="{_money(rng, 100, 50_000)}"'
                f' CaracEspecial="{rng.choice(CARAC_ESPECIAL)}" DiaAtraso="0"'
                f' IPOC="{cnpj}{MOD}2{cd}{contrt}">'
            )
            rows.append(f'      <Venc {rng.choice(VENC_VERTICES)}="{vlr}"/>')
            for _ in range(rng.choice(GAR_COUNT)):
                orig = _money(rng, 1_000, 1_200_000)
                rows.append(
                    f'      <Gar Tp="{rng.choice(GAR_TP)}"'
                    f' Ident="{rng.randrange(10 ** 11):011d}"'
                    f' PercGar="{rng.randint(2000, 9900) / 100:.2f}"'
                    f' VlrOrig="{orig}" VlrData="{orig}"'
                    f' DtReav="{_date(rng, 2025, 2026)}"/>'
                )
            rows.append(
                f'      <ContInstFinRes4966 ClasAtFin="1" EstInstFin="1"'
                f' CartProvMin="C1" VlrContBr="{vlr}" TJE="{tje}" RendMes="0.00">'
            )
            rows.append(f'        <Estagio Motivo="101" DtAlocacao="{dt_base}"/>')
            rows.append("      </ContInstFinRes4966>")
            rows.append("    </Op>")

        rows.append("  </Cli>")
        out.append(("\n".join(rows) + "\n").encode("ascii"))

    return out


def header(cnpj: str, dt_base: str, remessa: int, parte: int, tp_arq: str,
           total_cli: int) -> bytes:
    """Cabeçalho da parte. `TotalCli` conta os `<Cli>` DESTA parte."""
    return (
        f'<Doc3040 DtBase="{dt_base}" CNPJ="{cnpj}" Remessa="{remessa}"'
        f' Parte="{parte}" TpArq="{tp_arq}" NomeResp="Equipe Governanca SCR"'
        f' EmailResp="scr.governanca@exemplo.com.br" TelResp="1133000000"'
        f' TotalCli="{total_cli}" MetodApPE="C" MetodDifTJE="N">\n'
    ).encode("ascii")


def clients_fitting(lens: list[int], offset: int, budget: int) -> tuple[int, int]:
    """Quantos clientes, a partir de `offset` no ciclo, cabem em `budget` bytes.

    Um ciclo completo soma sempre o mesmo total, qualquer que seja a rotação —
    então os ciclos inteiros saem por divisão e só o resto precisa de laço.
    """
    period, cycle = len(lens), sum(lens)
    full = budget // cycle
    n, used = full * period, full * cycle
    while used + lens[(offset + n) % period] <= budget:
        used += lens[(offset + n) % period]
        n += 1
    return n, used


def write_part(path: Path, templates: list[bytes], first_cd: int, n_cli: int,
               cnpj: str, dt_base: str, remessa: int, parte: int, tp_arq: str,
               chunk_clients: int = 4096) -> int:
    """Escreve uma parte em streaming e devolve os bytes gravados."""
    period = len(templates)
    written = 0
    with open(path, "wb", buffering=1 << 20) as fh:
        written += fh.write(XML_DECL)
        written += fh.write(header(cnpj, dt_base, remessa, parte, tp_arq, n_cli))
        buf: list[bytes] = []
        for i in range(n_cli):
            cd = first_cd + i
            buf.append(templates[(first_cd - 1 + i) % period]
                       .replace(CD_MARK, b"%08d" % cd))
            if len(buf) >= chunk_clients:
                written += fh.write(b"".join(buf))
                buf.clear()
        if buf:
            written += fh.write(b"".join(buf))
        written += fh.write(FOOTER)
    return written


def validate(path: Path) -> tuple[int, int, int]:
    """Parse incremental (expat) — well-formedness + contagens, memória constante."""
    from xml.parsers import expat

    counts = {"Cli": 0, "Op": 0}
    declared = {"total": -1}

    def start(name: str, attrs: dict) -> None:
        if name in counts:
            counts[name] += 1
        elif name == "Doc3040":
            declared["total"] = int(attrs["TotalCli"])

    parser = expat.ParserCreate()
    parser.StartElementHandler = start
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 22):
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    return counts["Cli"], counts["Op"], declared["total"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target-gib", type=float, default=20.0,
                    help="tamanho total do documento em GiB (default: 20)")
    ap.add_argument("--max-part-mib", type=int, default=0,
                    help="corta em partes deste tamanho; 0 = monolito (default)")
    ap.add_argument("--out-dir", type=Path, default=Path("/tmp/rc18_scale_3040"))
    ap.add_argument("--cnpj", default="99999999", help="8 dígitos, sintético")
    ap.add_argument("--dt-base", default="2026-08", help="AAAA-MM")
    ap.add_argument("--remessa", type=int, default=1)
    ap.add_argument("--templates", type=int, default=512,
                    help="tamanho do pool de blocos <Cli> pré-renderizados")
    ap.add_argument("--seed", type=int, default=18)
    ap.add_argument("--validate", action="store_true",
                    help="parse incremental do resultado (lento em arquivo grande)")
    args = ap.parse_args()

    out_dir = args.out_dir.resolve()
    # Guarda-corpo: o repo é PÚBLICO e `sample/` é versionado — 20 GiB ali seria
    # um acidente irreversível no histórico.
    if REPO_ROOT and (out_dir == REPO_ROOT or REPO_ROOT in out_dir.parents):
        print(f"ERRO: --out-dir dentro do repo ({out_dir}).\n"
              f"      Use /tmp/... ou /Volumes/<catalog>/landing/scr_xml/3040.",
              file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    target = int(args.target_gib * (1 << 30))
    print(f"pool de templates ......... {args.templates}", file=sys.stderr)
    templates = build_templates(args.cnpj, args.dt_base, args.templates, args.seed)
    lens = [len(t) for t in templates]
    avg = sum(lens) / len(lens)
    print(f"tamanho médio por <Cli> ... {avg:,.0f} bytes", file=sys.stderr)

    # Reserva o cabeçalho na sua largura MÁXIMA para planejar; o arquivo sai
    # alguns bytes abaixo do orçamento, nunca acima.
    overhead = len(XML_DECL) + len(FOOTER) + len(
        header(args.cnpj, args.dt_base, args.remessa, 9999, "F", 99_999_999))
    part_budget = (args.max_part_mib << 20) if args.max_part_mib else target

    plan: list[int] = []
    offset, remaining = 0, target
    while remaining > overhead:
        n, used = clients_fitting(lens, offset, min(part_budget, remaining) - overhead)
        if n == 0:
            break
        plan.append(n)
        offset = (offset + n) % len(templates)
        remaining -= used + overhead

    total_cli = sum(plan)
    if total_cli > 99_999_999:
        print(f"ERRO: {total_cli:,} clientes excede a largura de 8 dígitos de `Cd`.",
              file=sys.stderr)
        return 2
    print(f"plano .................... {len(plan)} parte(s), "
          f"{total_cli:,} clientes\n", file=sys.stderr)

    t0 = time.monotonic()
    written = 0
    first_cd = 1
    for idx, n_cli in enumerate(plan, start=1):
        tp_arq = "F" if idx == len(plan) else "P"
        name = f"Doc3040_{args.cnpj}_{args.dt_base}_R{args.remessa}_P{idx}.xml"
        path = out_dir / name
        got = write_part(path, templates, first_cd, n_cli, args.cnpj, args.dt_base,
                         args.remessa, idx, tp_arq)
        written += got
        first_cd += n_cli
        el = time.monotonic() - t0
        print(f"[{idx:>4}/{len(plan)}] {name}  {got / (1 << 20):>9,.1f} MiB  "
              f"{n_cli:>10,} cli  TpArq={tp_arq}  "
              f"({written / (1 << 30):>6.2f} GiB total, "
              f"{written / (1 << 20) / max(el, 1e-9):>6,.0f} MiB/s)", file=sys.stderr)

    el = time.monotonic() - t0
    print(f"\nOK — {written / (1 << 30):.2f} GiB em {len(plan)} arquivo(s), "
          f"{total_cli:,} clientes, {el:,.1f}s "
          f"({written / (1 << 20) / max(el, 1e-9):,.0f} MiB/s)", file=sys.stderr)
    print(f"     {out_dir}", file=sys.stderr)

    if args.validate:
        print("\nvalidando (parse incremental)...", file=sys.stderr)
        for idx, n_cli in enumerate(plan, start=1):
            path = out_dir / f"Doc3040_{args.cnpj}_{args.dt_base}_R{args.remessa}_P{idx}.xml"
            cli, ops, declared = validate(path)
            assert cli == n_cli == declared, (
                f"{path.name}: <Cli>={cli} plano={n_cli} TotalCli={declared}")
            print(f"  P{idx}: well-formed, {cli:,} <Cli> == TotalCli, {ops:,} <Op>",
                  file=sys.stderr)
        print("OK — todas as partes íntegras.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
