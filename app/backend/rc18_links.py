"""Loaders for the RC18-owned rule↔CADOC↔dimension link tables.

These read `${CATALOG}.governance.cadoc_tabelas` and `regra_vinculos` — the
source of truth for how a DQX rule maps to a CADOC document and an R.18
dimension. They are consulted by the read paths (validation.py, quality.py,
reference.py) BEFORE the legacy tag/hard-coded fallback, so a rule linked via
the `/linking` screen surfaces in Críticas even when it was authored without an
explicit `name` (the bug that dropped `parte_not_in_range`).

All loaders use the tolerant `execute_query_or_empty`, so a fresh workspace
(tables not created yet) degrades to empty maps and the callers fall back to
their existing behavior — no regression pre-seed.
"""

from __future__ import annotations

from db import CATALOG
from db import execute_query_or_empty as execute_query

_TBLS = f"{CATALOG}.governance.cadoc_tabelas"
_LINKS = f"{CATALOG}.governance.regra_vinculos"


async def load_cadoc_tables() -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return (tables_by_doc, doc_by_table) for active CADOC↔table associations.

    - tables_by_doc: {'3040': ['rc18_catalog.silver.scr3040_clientes', ...]}
    - doc_by_table:  {'rc18_catalog.silver.scr3040_clientes': '3040', ...}

    Empty maps when `cadoc_tabelas` doesn't exist yet — callers must fall back
    to their hard-coded prefix logic in that case.
    """
    rows = await execute_query(
        f"SELECT documento, table_fqn FROM {_TBLS} WHERE is_ativo", {},
    )
    tables_by_doc: dict[str, list[str]] = {}
    doc_by_table: dict[str, str] = {}
    for r in rows:
        doc = r.get("documento")
        tfqn = r.get("table_fqn")
        if not doc or not tfqn:
            continue
        tables_by_doc.setdefault(doc, []).append(tfqn)
        doc_by_table[tfqn] = doc
    return tables_by_doc, doc_by_table


async def load_vinculos() -> tuple[dict[tuple[str, str], dict], dict[str, dict]]:
    """Return (by_pair, by_rule_id) for active rule links.

    - by_pair:    {(table_fqn, check_name): vinculo_dict}
    - by_rule_id: {rule_id: vinculo_dict}

    `by_pair` is the primary join key (matches the grain at which DQX
    `check_metrics` are consumed). `by_rule_id` is the fallback for rules whose
    definition has no `name` (so the parsed check_name is empty) but whose
    stable `rule_id` is known.
    """
    rows = await execute_query(
        "SELECT vinculo_id, check_name, rule_id, table_fqn, documento, dimensao_r18, "
        f"critica_id, nivel_verificacao, descricao FROM {_LINKS} WHERE is_ativo",
        {},
    )
    by_pair: dict[tuple[str, str], dict] = {}
    by_rule_id: dict[str, dict] = {}
    for r in rows:
        tfqn = r.get("table_fqn") or ""
        cname = r.get("check_name") or ""
        if tfqn and cname:
            by_pair[(tfqn, cname)] = r
        rid = r.get("rule_id")
        if rid:
            by_rule_id[rid] = r
    return by_pair, by_rule_id
