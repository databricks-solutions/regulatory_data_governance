#!/usr/bin/env python3
"""Gera docker/.env.bundle: a configuração do app derivada do bundle.

Lê o bloco `apps.config.env` de resources/app/app.yml — o mesmo que o bundle
injeta no Databricks App — e resolve cada `${...}` contra o `bundle summary -o json`.
Assim a lista de variáveis tem uma fonte só: variável nova no app.yml chega ao
container sem tocar aqui. Sem PyYAML de propósito (só stdlib no host).

Uso: render_env.py --summary summary.json --host https://... [--app-yml ...] [--out ...]
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REF = re.compile(r"\$\{([^}]+)\}")
# DATABRICKS_HOST vem do perfil: no Databricks Apps é a plataforma que o injeta.
HEADER = "# GERADO por docker/setup.sh a partir do bundle — não edite. Mude o target.yml e rode o setup de novo.\n"


def parse_env_block(text: str) -> list[tuple[str, str]]:
    """Pares (name, value) do primeiro bloco `env:` do app.yml."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "env:")
    except StopIteration:
        sys.exit("ERRO: bloco `env:` não encontrado no app.yml.")
    indent = len(lines[start]) - len(lines[start].lstrip())
    pairs, name = [], None
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break  # saiu do bloco env
        if m := re.match(r"-\s*name:\s*(\S+)$", stripped):
            name = m.group(1)
        elif (m := re.match(r"value:\s*(.+)$", stripped)) and name:
            pairs.append((name, m.group(1).strip().strip("\"'")))
            name = None
    if not pairs:
        sys.exit("ERRO: nenhuma variável lida do bloco `env:` do app.yml.")
    return pairs


def lookup(path: str, summary: dict):
    head, _, rest = path.partition(".")
    if head == "var":
        var = summary.get("variables", {}).get(rest)
        if var is None:
            raise KeyError(path)
        return var.get("value", var.get("default"))
    node = summary.get(head)
    for part in rest.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def resolve(value: str, summary: dict, depth: int = 0) -> str:
    if depth > 10:
        raise KeyError(f"referência circular em {value!r}")
    if not REF.search(value):
        return value
    out = REF.sub(lambda m: str(lookup(m.group(1), summary)), value)
    return resolve(out, summary, depth + 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True, help="saída de `databricks bundle summary -o json`")
    ap.add_argument("--host", required=True)
    ap.add_argument("--app-yml", default=str(REPO / "resources/app/app.yml"))
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    summary = json.loads(Path(args.summary).read_text())
    env, missing = [("DATABRICKS_HOST", args.host.rstrip("/"))], []
    for name, raw in parse_env_block(Path(args.app_yml).read_text()):
        try:
            value = resolve(raw, summary)
        except KeyError as e:
            missing.append(f"{name} ({raw} → {e})")
            continue
        if value == "":
            missing.append(f"{name} (vazio)")
            continue
        env.append((name, value))
    if missing:
        sys.exit("ERRO: não resolvidas — o bundle já foi deployado?\n  " + "\n  ".join(missing))

    body = HEADER + "".join(f"{k}={v}\n" for k, v in env)
    if args.out == "-":
        sys.stdout.write(body)
    else:
        Path(args.out).write_text(body)


if __name__ == "__main__":
    main()
