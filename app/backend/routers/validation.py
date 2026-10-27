"""Validation endpoints: results, trigger, status, runs.

Results come from DQX Studio's approved runs (`dq_validation_runs` +
`dq_metrics.check_metrics`): the latest run per table, plus the data-base each
run evaluated (`data_base.py`). `GET /documents` lists the CADOCs with runs —
the document picker of the Críticas page.

Warning/fail rows carry ``critica_id`` + ``run_config_name`` + ``dqx_run_id``
so the front-end can POST to ``/governance/incidents`` with the canonical
dedup key.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from data_base import RunSelection, reference_month, select_runs
from db import CATALOG, DQX_METRICS_TABLE, SCHEMA_SILVER, USE_MOCK
from dqx_config import dqx_studio_base_url, dqx_studio_entry_url
from i18n import get_locale
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when silver tables haven't been populated yet (pipeline not run).
from db import execute_query_or_empty as execute_query
from rc18_rule_meta import meta_for, resolve_meta
from dqx_rules import RuleIndex, build_index, load_executed_rules
from rc18_links import load_cadoc_documents, load_cadoc_tables, load_vinculos
from models import (
    CadocRef,
    DocumentSummary,
    DocumentsResponse,
    TableDataBase,
    Pagination,
    RunProgress,
    RunSummary,
    TriggerValidationRequest,
    TriggerValidationResponse,
    ValidationResult,
    ValidationResultsResponse,
    ValidationRunsResponse,
    ValidationRunStatus,
    ValidationSummary,
)

router = APIRouter()


def _dqx_studio_configured_base() -> str | None:
    """Base URL do DQX Studio quando configurado de verdade.

    Trata como "desativado" três casos: env ausente, string vazia, e a
    sentinela `about:blank` (default do bundle quando o customer não
    setou a URL real). Retorna None nesses casos pra UI esconder
    deep-links e a aba Motor de Regras renderizar estado vazio.
    """
    return dqx_studio_base_url()


def dqx_check_url(run_config_name: str | None, check_name: str | None) -> str | None:
    """Linkback to DQX Studio para edição da regra.

    A Studio (`databrickslabs/dqx`) não tem um deep-link por
    `run_config_name`/`check_name` que mostre a regra direto no editor — as
    rotas internas do app são todas client-side. Por isso apontamos para a tela
    de entrada configurada (`dqx_studio_entry_url`, default `/registry-rules`),
    que lista as regras; o usuário acha a dele e clica para abrir o editor.
    """
    if not check_name:
        return None
    return dqx_studio_entry_url()


def _studio_base_url() -> str | None:
    """URL do botão 'Ver no DQX Studio' do header de Críticas SCR.

    Aponta direto para a aba **Histórico de Execuções** (`/runs-history`) ao
    invés da home — o usuário vem da Críticas SCR querendo investigar as
    execuções recentes, então é a destination certa.
    """
    base = _dqx_studio_configured_base()
    if not base:
        return None
    return f"{base}/runs-history"


def _mock_vr(*, rule_id, run_config_name, check_name, dqx_check_function,
             rule_name, rule_type, severity, dimension_r18, dimension_name,
             status, affected_records, total_records, description, nivel,
             sample_ipocs=None):
    """Build a ValidationResult mock row with DQX-flavored fields wired up.

    Keeps the call sites readable and forces every mock entry to carry the
    same shape as a real row built by ``_fetch_studio_results``.
    """
    pct = round(100 * affected_records / total_records, 6) if total_records else 0.0
    return ValidationResult(
        rule_id=rule_id,
        rule_name=rule_name,
        rule_type=rule_type,
        severity=severity,
        dimension_r18=dimension_r18,
        dimension_name=dimension_name,
        status=status,
        affected_records=affected_records,
        total_records=total_records,
        affected_pct=pct,
        description=description,
        sample_ipocs=sample_ipocs or [],
        nivel_verificacao=nivel,
        check_name=check_name,
        dqx_check_function=dqx_check_function,
        dqx_check_url=dqx_check_url(run_config_name, check_name),
        run_config_name=run_config_name,
        # Mock rows fake a stable run_id per (rule_id) so the dedup key is
        # deterministic across reloads of the page.
        dqx_run_id=f"mockrun_{rule_id}",
        critica_id=rule_id,
        # Deriva a tabela-alvo do run_config_name (silver_3040_operacoes →
        # {CATALOG}.silver.scr3040_operacoes) para o mock refletir a coluna real.
        table_fqn=_table_fqn_from_run_config(run_config_name),
    )


def _table_fqn_from_run_config(run_config_name: str | None) -> str | None:
    """Mapeia o run_config mock (silver_3040_operacoes) para a table_fqn real
    ({CATALOG}.silver.scr3040_operacoes). Só usado nas linhas mock — no caminho
    real a table_fqn vem direto do source_table_fqn do run DQX."""
    if not run_config_name:
        return None
    tbl = run_config_name.replace("silver_3040_", "scr3040_").replace("silver_3050", "scr3050")
    return f"{CATALOG}.{SCHEMA_SILVER}.{tbl}"


_RC_3040_OPER = "silver_3040_operacoes"
_RC_3040_CLI = "silver_3040_clientes"
_RC_3040_GAR = "silver_3040_garantias"
_RC_3040_VEN = "silver_3040_vencimentos"
_RC_3050 = "silver_3050"

# As 4 regras iniciais do acelerador — referência canônica usada para o mapping
# de dimensões R.18. As regras autoritativas são criadas via DQX Studio e lidas
# dos runs dela (`dqx_rules`); o RC18 não semeia mais regras.
# Mapping uses the spec-canonical 12 R.18 dimensions per docs/spec/01_requirements.md §1.2:
# 1 Acessibilidade, 2 Acurácia, 3 Adaptabilidade, 4 Clareza, 5 Comparabilidade,
# 6 Completude, 7 Confiabilidade, 8 Consistência, 9 Integridade, 10 Rastreabilidade,
# 11 Relevância, 12 Tempestividade.
_MOCK_RULES_3040 = [
    _mock_vr(rule_id="S20_001", run_config_name=_RC_3040_CLI,
             check_name="autorzc_in_dominio", dqx_check_function="sql_expression",
             rule_name="Autorzc fora do domínio {S,N}", rule_type="syntactic",
             severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="fail",
             affected_records=12, total_records=50000000, nivel=1,
             description="12 clientes com Autorzc fora do domínio {S,N} do leiaute SCR 3040."),
    _mock_vr(rule_id="S20_002", run_config_name=_RC_3040_CLI,
             check_name="porte_cli_in_dominio_por_tipo", dqx_check_function="sql_expression",
             rule_name="PorteCli inválido para o tipo de cliente", rule_type="syntactic",
             severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="fail",
             affected_records=7, total_records=50000000, nivel=1,
             description="7 clientes com PorteCli fora do domínio condicional ao tipo (PF: 0-8; PJ: 0-4)."),
    _mock_vr(rule_id="S20_003", run_config_name=_RC_3040_CLI,
             check_name="tp_ctrl_in_dominio", dqx_check_function="sql_expression",
             rule_name="TpCtrl fora do domínio {01..04}", rule_type="syntactic",
             severity="error", dimension_r18=3, dimension_name="Adaptabilidade", status="fail",
             affected_records=5, total_records=50000000, nivel=1,
             description="5 clientes com TpCtrl fora do domínio oficial {'01','02','03','04'} do leiaute SCR 3040."),
    _mock_vr(rule_id="S10_004", run_config_name=_RC_3040_OPER,
             check_name="dia_atraso_nao_negativo", dqx_check_function="sql_expression",
             rule_name="DiaAtraso negativo", rule_type="syntactic",
             severity="error", dimension_r18=2, dimension_name="Acurácia", status="fail",
             affected_records=23, total_records=50000000, nivel=1,
             description="23 operações com DiaAtraso negativo — valor inválido (esperado inteiro não-negativo)."),
]

# English (en-US) fixture set — same structure/codes as _MOCK_RULES_3040, only
# human-readable text (rule_name/description/dimension_name) translated. Selected
# in mock mode when the request locale is `en` (see i18n.get_locale).
_MOCK_RULES_3040_EN = [
    _mock_vr(rule_id="S20_001", run_config_name=_RC_3040_CLI,
             check_name="autorzc_in_dominio", dqx_check_function="sql_expression",
             rule_name="Authorization flag (Autorzc) outside the {S,N} domain", rule_type="syntactic",
             severity="error", dimension_r18=3, dimension_name="Adaptability", status="fail",
             affected_records=12, total_records=50000000, nivel=1,
             description="12 customers whose authorization flag (Autorzc) falls outside the allowed {S,N} domain of the SCR 3040 layout."),
    _mock_vr(rule_id="S20_002", run_config_name=_RC_3040_CLI,
             check_name="porte_cli_in_dominio_por_tipo", dqx_check_function="sql_expression",
             rule_name="Customer size (PorteCli) invalid for the customer type", rule_type="syntactic",
             severity="error", dimension_r18=3, dimension_name="Adaptability", status="fail",
             affected_records=7, total_records=50000000, nivel=1,
             description="7 customers whose customer size (PorteCli) is outside the range allowed for their type (individuals PF: 0-8; companies PJ: 0-4)."),
    _mock_vr(rule_id="S20_003", run_config_name=_RC_3040_CLI,
             check_name="tp_ctrl_in_dominio", dqx_check_function="sql_expression",
             rule_name="Control type (TpCtrl) outside the {01..04} domain", rule_type="syntactic",
             severity="error", dimension_r18=3, dimension_name="Adaptability", status="fail",
             affected_records=5, total_records=50000000, nivel=1,
             description="5 customers whose control type (TpCtrl) falls outside the official domain {'01','02','03','04'} of the SCR 3040 layout."),
    _mock_vr(rule_id="S10_004", run_config_name=_RC_3040_OPER,
             check_name="dia_atraso_nao_negativo", dqx_check_function="sql_expression",
             rule_name="Negative days past due (DiaAtraso)", rule_type="syntactic",
             severity="error", dimension_r18=2, dimension_name="Accuracy", status="fail",
             affected_records=23, total_records=50000000, nivel=1,
             description="23 operations with negative days past due (DiaAtraso) — invalid value (expected a non-negative integer)."),
]


def _mock_rules_3040(locale: str) -> list[ValidationResult]:
    """Pick the locale-matched 3040 mock fixture set (en-US, else pt-BR default)."""
    return _MOCK_RULES_3040_EN if locale == "en" else _MOCK_RULES_3040


# 3050: ainda sem regras iniciais. O usuário pode autorizar regras adicionais
# via DQX Studio (run_config_name='silver_3050') que aparecerão aqui assim que
# o pipeline silver as executar.
_MOCK_RULES_3050: list[ValidationResult] = []
# English (en-US) fixture set for 3050 — empty like the pt-BR default until
# initial 3050 rules exist; kept as an explicit home for translated rows.
_MOCK_RULES_3050_EN: list[ValidationResult] = []


def _mock_rules_3050(locale: str) -> list[ValidationResult]:
    """Pick the locale-matched 3050 mock fixture set (en-US, else pt-BR default)."""
    return _MOCK_RULES_3050_EN if locale == "en" else _MOCK_RULES_3050


def _apply_mock_filters(results, *, severity, status, rule_type, dimension_r18,
                       nivel_verificacao):
    if severity:
        results = [r for r in results if r.severity == severity]
    if status:
        results = [r for r in results if r.status == status]
    if rule_type:
        results = [r for r in results if r.rule_type == rule_type]
    if dimension_r18:
        results = [r for r in results if r.dimension_r18 == dimension_r18]
    if nivel_verificacao:
        results = [r for r in results if r.nivel_verificacao == nivel_verificacao]
    return results


def _summary_from_results(results) -> ValidationSummary:
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    warnings = sum(1 for r in results if r.status == "warning")
    pass_rate = round(passed / total * 100, 1) if total else 0.0
    return ValidationSummary(total_rules=total, passed=passed, failed=failed,
                             warnings=warnings, pass_rate_pct=pass_rate)


# ── DQX Studio run-results integration ──────────────────────────────────────
#
# Reads ONE approved run per source_table_fqn (`data_base.select_runs`: the
# latest, or the latest whose data-base falls in the reference month)
# joined with `${DQX_METRICS_TABLE}` (`check_metrics` = JSON array of per-check
# counts), and the rule definitions from the runs' own `checks_json`
# (`dqx_rules.load_executed_rules`). check_metrics entries that don't match a
# rule in force are dropped silently. Each table also gets the data-base its run
# evaluated.

_DOC_TO_TABLE_PREFIX = {
    "3040": "rc18_catalog.silver.scr3040_",
    "3050": "rc18_catalog.silver.scr3050",
}


async def _load_active_rules() -> RuleIndex:
    """Definições das regras em vigor (executadas), indexadas por (tabela, check).

    O valor é a definição DQX acrescida de `_row_table_fqn`. Escopado ao catálogo
    do deployment e indexado pelo PAR — `check_name` sozinho não é único entre
    tabelas. Ver `dqx_rules`.
    """
    rows = await load_executed_rules()
    return build_index(
        rows,
        value_of=lambda row, chk: {**chk, "_row_table_fqn": row.get("table_fqn") or ""},
    )


def _doc_scope(doc_tables: dict[str, list[str]]):
    """(predicado de `source_table_fqn`, params, tabela → documento) para os documentos.

    Tabelas de `cadoc_tabelas` entram pela lista; documento sem tabela registrada
    cai no prefixo legado (3040/3050), como antes de o `cadoc_tabelas` existir.
    Nomes de tabela vão como parâmetro, nunca interpolados. None = nada a buscar.
    """
    table_to_doc = {t: doc for doc, tables in doc_tables.items() for t in tables}
    prefixes = {
        doc: _DOC_TO_TABLE_PREFIX[doc]
        for doc, tables in doc_tables.items() if not tables and doc in _DOC_TO_TABLE_PREFIX
    }
    preds: list[str] = []
    params: dict = {}
    if table_to_doc:
        keys = [f"t{i}" for i in range(len(table_to_doc))]
        params.update(zip(keys, table_to_doc))
        preds.append(f"source_table_fqn IN ({','.join(f':{k}' for k in keys)})")
    for i, prefix in enumerate(prefixes.values()):
        params[f"prefix{i}"] = f"{prefix}%"
        preds.append(f"source_table_fqn LIKE :prefix{i}")
    if not preds:
        return None

    def doc_of(table_fqn: str) -> str | None:
        return table_to_doc.get(table_fqn) or next(
            (d for d, p in prefixes.items() if table_fqn.startswith(p)), None,
        )

    return f"({' OR '.join(preds)})", params, doc_of


def _created_at_str(run: dict) -> str:
    # O connector devolve datetime (prod) ou string (alguns ambientes locais);
    # run_completed_at é str, e comparar datetime com "" quebra.
    created_at = run.get("created_at")
    return created_at.isoformat() if hasattr(created_at, "isoformat") else (str(created_at) if created_at is not None else "")


def _results_for_run(
    r: dict, check_metrics: list, rules_index: RuleIndex, vinc_by_pair: dict, vinc_by_rule: dict,
) -> list[ValidationResult]:
    """Um ValidationResult por check do run que casa com regra em vigor (ou vínculo)."""
    run_id = r["run_id"]
    source_table = r.get("source_table_fqn") or ""
    total = int(r.get("total_rows") or 0)
    out: list[ValidationResult] = []
    for cmrow in check_metrics:
        check_name = cmrow.get("check_name")
        if not check_name:
            continue
        rule = rules_index.get(source_table, check_name)
        # Link-aware recovery: a rule authored without an explicit `name`
        # produces a runtime check_name (e.g. `parte_not_in_range`) that has
        # no matching definition in `rules_index`. If the /linking screen
        # linked (source_table, check_name), surface it anyway using the
        # link's metadata instead of dropping it silently.
        link = vinc_by_pair.get((source_table, check_name))
        if not rule and not link:
            # Truly stale (deleted definition, never linked); drop.
            continue
        err = int(cmrow.get("error_count") or 0)
        warn = int(cmrow.get("warning_count") or 0)
        affected = err + warn
        um = (rule or {}).get("user_metadata") or {}
        criticality = (rule or {}).get("criticality") or "error"
        sev = "error" if criticality == "error" else "warning"
        status = "pass" if affected == 0 else ("fail" if sev == "error" else "warning")
        run_cfg = (rule or {}).get("run_config_name") or ""
        check_fn = ((rule or {}).get("check") or {}).get("function", "")
        rule_id = (rule or {}).get("rule_id") or (link or {}).get("rule_id")
        # Structural metadata: link table wins, else tag/hard-coded fallback.
        meta = resolve_meta(
            check_name,
            table_fqn=(rule or {}).get("_row_table_fqn", "") or source_table,
            user_metadata=um,
            vinculos_by_pair=vinc_by_pair,
            vinculos_by_rule_id=vinc_by_rule,
            rule_id=rule_id,
        )
        description = (
            um.get("descricao") or um.get("mensagem_erro")
            or (link or {}).get("descricao") or check_name
        )
        rule_name = description if len(description) < 80 else check_name
        out.append(ValidationResult(
            rule_id=meta["critica_id"] or check_name,
            rule_name=rule_name,
            rule_type=meta["rule_type"],
            severity=sev,
            dimension_r18=meta["dimension_r18"],
            dimension_name=meta["dimension_name"],
            status=status,
            affected_records=affected,
            total_records=total,
            affected_pct=round(100 * affected / total, 4) if total else 0.0,
            description=description,
            sample_ipocs=[],
            nivel_verificacao=meta["nivel_verificacao"],
            check_name=check_name,
            dqx_check_function=check_fn,
            dqx_check_url=dqx_check_url(run_cfg, check_name),
            run_config_name=run_cfg,
            dqx_run_id=run_id,
            critica_id=meta["critica_id"] or check_name,
            table_fqn=source_table or None,
        ))
    return out


async def _studio_results(doc_tables: dict[str, list[str]], month: str | None):
    """({documento: (resultados, runs)}, seleção, tabela → documento).

    Um run aprovado por tabela (`data_base.select_runs`: o último, ou o último
    com data-base no `month`). Uma consulta de runs e uma de métricas para todos
    os documentos pedidos — a rota de documentos chama com todos os CADOCs de
    uma vez. Run sem `check_metrics` legível fica de fora, como antes.
    """
    scope = _doc_scope(doc_tables)
    if scope is None:
        return {}, RunSelection(runs=[], tables={}), (lambda _t: None)
    pred, params, doc_of = scope
    selection = await select_runs(pred, params, month)
    runs = selection.runs
    if not runs:
        return {}, selection, doc_of

    # run_ids vêm do banco, mas ainda assim vão como parâmetro.
    rk = [f"r{i}" for i in range(len(runs))]
    metrics_rows = await execute_query(
        "SELECT run_id, metric_value AS check_metrics_json "
        f"FROM {DQX_METRICS_TABLE} "
        f"WHERE metric_name = 'check_metrics' AND run_id IN ({','.join(f':{k}' for k in rk)})",
        {k: r["run_id"] for k, r in zip(rk, runs)},
        cache_ns="dqx",
    )
    metrics_by_run = {m["run_id"]: m for m in metrics_rows}
    rules_index = await _load_active_rules()
    vinc_by_pair, vinc_by_rule = await load_vinculos()

    out: dict[str, tuple[list[ValidationResult], list[dict]]] = {}
    for r in runs:
        doc = doc_of(r.get("source_table_fqn") or "")
        cm = metrics_by_run.get(r["run_id"])
        if not doc or not cm:
            continue
        try:
            check_metrics = json.loads(cm["check_metrics_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(check_metrics, list):
            continue
        results, doc_runs = out.setdefault(doc, ([], []))
        doc_runs.append(r)
        results.extend(_results_for_run(r, check_metrics, rules_index, vinc_by_pair, vinc_by_rule))
    return out, selection, doc_of


def _summaries(
    by_doc: dict[str, tuple[list[ValidationResult], list[dict]]],
    docs_meta: dict[str, dict],
    per_table: dict[str, TableDataBase],
) -> dict[str, DocumentSummary]:
    """Resumo por documento: a data-base do processamento exibido e as reprovações."""
    out: dict[str, DocumentSummary] = {}
    for doc, (results, runs) in by_doc.items():
        meta = docs_meta.get(doc) or {}
        tables = sorted(
            (per_table[r.get("source_table_fqn") or ""] for r in runs),
            key=lambda t: t.table_fqn,
        )
        known = [t.data_base for t in tables if t.data_base]
        out[doc] = DocumentSummary(
            documento=doc,
            nome=meta.get("nome"),
            grupo=meta.get("grupo"),
            periodicidade=meta.get("periodicidade"),
            data_base=max(known) if known else None,
            mixed=len({t.data_base for t in tables}) > 1,
            last_run_at=max((_created_at_str(r) for r in runs), default=None),
            total_rules=len(results),
            # Mesma conta do card de resumo das Críticas: reprovadas + alertas.
            failed_rules=sum(1 for v in results if v.status in ("fail", "warning")),
            tables=tables,
        )
    return out


async def _fetch_studio_results(
    document: str, month: str | None = None,
) -> tuple[list[ValidationResult], str | None, str | None, DocumentSummary | None]:
    """Compose ValidationResult rows from DQX Studio's run history.

    For each source_table_fqn that matches `document`'s silver tables, pick the
    LATEST SUCCESS run — or, with `month`, the latest whose evaluated data-base
    falls in it. Parse its `check_metrics` and emit one ValidationResult
    per check that maps to a rule in force (via the link table, then
    check_name → the runs' `checks_json`). Also returns the document summary
    (data-base evaluated by each table's run).

    Table selection is driven by `governance.cadoc_tabelas` (the CADOC↔table
    map maintained on the /linking screen); when that table is empty (fresh
    workspace, pre-seed) it falls back to the legacy hard-coded prefix so
    nothing regresses.
    """
    tables_by_doc, _doc_by_table = await load_cadoc_tables()
    by_doc, selection, _doc_of = await _studio_results({document: tables_by_doc.get(document, [])}, month)
    if document not in by_doc:
        return [], None, None, None
    results, runs = by_doc[document]
    latest = max(runs, key=_created_at_str)
    summary = _summaries({document: by_doc[document]}, await load_cadoc_documents(), selection.tables)[document]
    return results, latest["run_id"], _created_at_str(latest), summary


_DIM_NAME_BY_INT = {
    1: "Acessibilidade", 2: "Acurácia", 3: "Adaptabilidade", 4: "Clareza",
    5: "Comparabilidade", 6: "Completude", 7: "Confiabilidade", 8: "Consistência",
    9: "Integridade", 10: "Rastreabilidade", 11: "Relevância", 12: "Tempestividade",
}


# Documentos do mock: espelham os CADOCs de demonstração (ver routers/linking.py).
_MOCK_DOCS = {
    "3040": ("SCR 3040 - Operações de crédito individualizadas", _mock_rules_3040),
    "3050": ("SCR 3050 - Estoque mensal agregado", _mock_rules_3050),
}


def _mock_document(documento: str, rules: list[ValidationResult]) -> DocumentSummary:
    nome, _fixtures = _MOCK_DOCS[documento]
    return DocumentSummary(
        documento=documento, nome=nome, grupo="SCR", periodicidade="mensal",
        data_base="2026-03-31", last_run_at="2026-03-30T14:45:00Z",
        total_rules=len(rules), failed_rules=sum(1 for r in rules if r.status in ("fail", "warning")),
    )


@router.get("/documents", response_model=DocumentsResponse)
async def list_documents(
    data_base: str | None = Query(None, description="Mês de referência (AAAA-MM); sem ele, o último processamento"),
    locale: str = Depends(get_locale),
):
    """CADOCs com execução aprovada na DQX, cada um com a data-base do processamento exibido.

    Alimenta o seletor de documentos das Críticas e o card "Data-bases
    avaliadas". Os demais cadastrados vêm em `unprocessed`, com
    `ever_processed` distinguindo "sem execução no mês" de "nunca executado".
    """
    month = reference_month(data_base)
    if USE_MOCK:
        # O mock tem uma data-base só (31/03/2026): outro mês = nada processado.
        if month not in (None, "2026-03"):
            return DocumentsResponse(unprocessed=[
                CadocRef(documento=doc, nome=nome, grupo="SCR", periodicidade="mensal", ever_processed=True)
                for doc, (nome, _fixtures) in _MOCK_DOCS.items()
            ])
        return DocumentsResponse(documents=[
            _mock_document(doc, fixtures(locale)) for doc, (_nome, fixtures) in _MOCK_DOCS.items()
        ])

    tables_by_doc, _doc_by_table = await load_cadoc_tables()
    docs_meta = await load_cadoc_documents()
    # Sem cadastro nenhum (workspace novo), os dois documentos do prefixo legado.
    doc_tables = {d: tables_by_doc.get(d, []) for d in sorted(set(docs_meta) | set(tables_by_doc))}
    by_doc, selection, doc_of = await _studio_results(doc_tables or {d: [] for d in _DOC_TO_TABLE_PREFIX}, month)
    summaries = _summaries(by_doc, docs_meta, selection.tables)
    documents = sorted(summaries.values(), key=_group_order)
    ever_docs = {doc_of(t) for t in selection.ever}
    unprocessed = sorted((
        CadocRef(
            documento=d, nome=meta.get("nome"), grupo=meta.get("grupo"),
            periodicidade=meta.get("periodicidade"), ever_processed=d in ever_docs,
        )
        for d, meta in docs_meta.items() if d not in summaries
    ), key=_group_order)
    return DocumentsResponse(documents=documents, unprocessed=unprocessed)


def _group_order(d) -> tuple:
    # Com grupo primeiro (em ordem alfabética), sem grupo por último.
    return (d.grupo is None, d.grupo or "", d.documento)


@router.get("/scr3040/results", response_model=ValidationResultsResponse)
async def get_validation_results_3040(
    data_base: str | None = Query(None, description="Mês de referência (AAAA-MM); sem ele, o último processamento"),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    modality: str | None = Query(None),
    rule_type: str | None = Query(None),
    dimension_r18: int | None = Query(None),
    nivel_verificacao: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    locale: str = Depends(get_locale),
):
    """Return validation results for SCR 3040 criticas."""
    if USE_MOCK:
        mock_rules = _mock_rules_3040(locale)
        filtered = _apply_mock_filters(
            list(mock_rules),
            severity=severity, status=status, rule_type=rule_type,
            dimension_r18=dimension_r18, nivel_verificacao=nivel_verificacao,
        )
        total = len(filtered)
        start = (page - 1) * page_size
        paged = filtered[start : start + page_size]
        doc = _mock_document("3040", mock_rules)
        return ValidationResultsResponse(
            data_base=doc.data_base,
            run_id="run_20260330_142200",
            run_status="completed",
            run_completed_at="2026-03-30T14:45:00Z",
            summary=_summary_from_results(mock_rules),
            results=paged,
            pagination=Pagination(
                page=page, page_size=page_size, total_results=total,
                total_pages=max(1, (total + page_size - 1) // page_size),
            ),
            studio_url=_studio_base_url(),
            document=doc,
        )

    # Real-mode: read DQX Studio's latest run + check_metrics + active rules.
    all_results, latest_run_id, latest_run_time, summary = await _fetch_studio_results("3040", reference_month(data_base))
    filtered = _apply_mock_filters(
        all_results,
        severity=severity, status=status, rule_type=rule_type,
        dimension_r18=dimension_r18, nivel_verificacao=nivel_verificacao,
    )
    total = len(filtered)
    start = (page - 1) * page_size
    paged = filtered[start : start + page_size]
    return ValidationResultsResponse(
        data_base=(summary.data_base if summary else None) or data_base or "",
        run_id=latest_run_id or "",
        run_status="completed",
        run_completed_at=latest_run_time,
        summary=_summary_from_results(all_results),
        results=paged,
        pagination=Pagination(
            page=page, page_size=page_size, total_results=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
        studio_url=_studio_base_url(),
        document=summary,
    )


@router.get("/scr3050/results", response_model=ValidationResultsResponse)
async def get_validation_results_3050(
    data_base: str | None = Query(None, description="Mês de referência (AAAA-MM); sem ele, o último processamento"),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    critica_group: int | None = Query(None),
    layout_version: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    locale: str = Depends(get_locale),
):
    """Return validation results for SCR 3050 criticas."""
    if USE_MOCK:
        mock_rules = _mock_rules_3050(locale)
        total = len(mock_rules)
        doc = _mock_document("3050", mock_rules)
        return ValidationResultsResponse(
            data_base=doc.data_base, run_id="run_20260331_100000", run_status="completed",
            run_completed_at="2026-03-31T10:30:00Z",
            summary=_summary_from_results(mock_rules),
            results=mock_rules,
            pagination=Pagination(page=1, page_size=page_size,
                                  total_results=total, total_pages=1),
            studio_url=_studio_base_url(),
            document=doc,
        )

    all_results, latest_run_id, latest_run_time, summary = await _fetch_studio_results("3050", reference_month(data_base))
    filtered = _apply_mock_filters(
        all_results,
        severity=severity, status=status, rule_type=None,
        dimension_r18=None, nivel_verificacao=None,
    )
    total = len(filtered)
    start = (page - 1) * page_size
    paged = filtered[start : start + page_size]
    return ValidationResultsResponse(
        data_base=(summary.data_base if summary else None) or data_base or "",
        run_id=latest_run_id or "",
        run_status="completed",
        run_completed_at=latest_run_time,
        summary=_summary_from_results(all_results),
        results=paged,
        pagination=Pagination(
            page=page, page_size=page_size, total_results=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
        studio_url=_studio_base_url(),
        document=summary,
    )


@router.get("/{document}/results", response_model=ValidationResultsResponse)
async def get_validation_results_generic(
    document: str,
    data_base: str | None = Query(None, description="Mês de referência (AAAA-MM); sem ele, o último processamento"),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    modality: str | None = Query(None),
    rule_type: str | None = Query(None),
    dimension_r18: int | None = Query(None),
    nivel_verificacao: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    locale: str = Depends(get_locale),
):
    """Return validation results for ANY CADOC document, driven by its
    `cadoc_tabelas` associations.

    This is the extensible path: customers register a new CADOC on the
    /linking screen, associate silver/gold tables to it, and its DQX runs
    surface here without any hard-coded 3040/3050 wiring. The legacy
    `/scr3040/results` and `/scr3050/results` routes remain for back-compat
    (and carry the pt-BR mock fixtures); this route serves everything else and
    returns empty results in mock mode (a custom CADOC has no fixtures).

    NOTE: this catch-all is declared AFTER `/scr3040/results` and
    `/scr3050/results` so those explicit paths win; `/trigger`, `/runs` etc.
    live under different prefixes and are unaffected.
    """
    document = (document or "").strip()
    if USE_MOCK:
        # No fixtures for a customer-defined CADOC; keep the two canonical demos
        # answering through their own routes and return empty for the rest.
        return ValidationResultsResponse(
            data_base=data_base or "", run_id="", run_status="completed",
            run_completed_at=None,
            summary=_summary_from_results([]),
            results=[],
            pagination=Pagination(page=page, page_size=page_size, total_results=0, total_pages=1),
            studio_url=_studio_base_url(),
        )

    all_results, latest_run_id, latest_run_time, summary = await _fetch_studio_results(document, reference_month(data_base))
    filtered = _apply_mock_filters(
        all_results,
        severity=severity, status=status, rule_type=rule_type,
        dimension_r18=dimension_r18, nivel_verificacao=nivel_verificacao,
    )
    total = len(filtered)
    start = (page - 1) * page_size
    paged = filtered[start : start + page_size]
    return ValidationResultsResponse(
        data_base=(summary.data_base if summary else None) or data_base or "",
        run_id=latest_run_id or "",
        run_status="completed",
        run_completed_at=latest_run_time,
        summary=_summary_from_results(all_results),
        results=paged,
        pagination=Pagination(
            page=page, page_size=page_size, total_results=total,
            total_pages=max(1, (total + page_size - 1) // page_size),
        ),
        studio_url=_studio_base_url(),
        document=summary,
    )


@router.post("/trigger", response_model=TriggerValidationResponse, status_code=202)
async def trigger_validation(
    req: TriggerValidationRequest,
    locale: str = Depends(get_locale),
):
    """Trigger an on-demand validation run."""
    if req.document not in ("3040", "3050"):
        raise HTTPException(status_code=400, detail="Document must be 3040 or 3050")

    now = datetime.now(timezone.utc)
    run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}"

    if USE_MOCK:
        # Mock payload carries only codes/ids/dates/numbers — no locale-sensitive
        # free text — so `locale` selects the same response for every locale.
        return TriggerValidationResponse(
            run_id=run_id,
            job_run_id=12345678,
            status="pending",
            document=req.document,
            data_base=req.data_base,
            scope=req.scope,
            triggered_by="analyst@bankcorp.com",
            triggered_at=now.isoformat(),
            estimated_duration_minutes=45,
        )

    from databricks.sdk import WorkspaceClient
    import os, json
    w = WorkspaceClient()
    job_id = int(os.getenv(f"VALIDATION_JOB_{req.document}_ID", "0"))
    run = w.jobs.run_now(
        job_id=job_id,
        notebook_params={
            "document": req.document,
            "data_base": req.data_base,
            "scope": req.scope,
            "rule_ids": json.dumps(req.rule_ids) if req.rule_ids else "",
        },
    )
    return TriggerValidationResponse(
        run_id=run_id, job_run_id=run.run_id, status="pending",
        document=req.document, data_base=req.data_base, scope=req.scope,
        triggered_by="service-principal", triggered_at=now.isoformat(),
    )


@router.get("/runs/{run_id}", response_model=ValidationRunStatus)
async def get_validation_run_status(
    run_id: str,
    locale: str = Depends(get_locale),
):
    """Get status of a validation run."""
    if USE_MOCK:
        # Run status is all codes/ids/dates/numbers — no locale-sensitive free
        # text — so `locale` resolves to the same payload for every locale.
        return ValidationRunStatus(
            run_id=run_id, job_run_id=12345678, status="completed",
            document="3040", data_base="2026-03",
            progress=RunProgress(
                current_step="completed", steps_completed=4, total_steps=4,
                records_processed=50000000, total_records=50000000, elapsed_seconds=2520,
            ),
            triggered_by="analyst@bankcorp.com",
            triggered_at="2026-04-02T10:00:00Z",
            started_at="2026-04-02T10:00:15Z",
            completed_at="2026-04-02T10:42:00Z",
        )
    raise HTTPException(status_code=404, detail="Run not found")


@router.get("/runs", response_model=ValidationRunsResponse)
async def list_validation_runs(
    document: str | None = Query(None),
    status: str | None = Query(None),
    data_base: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    locale: str = Depends(get_locale),
):
    """Return history of validation runs."""
    if USE_MOCK:
        # Run summaries are all codes/ids/dates/numbers — no locale-sensitive
        # free text — so `locale` resolves to the same payload for every locale.
        runs = [
            RunSummary(
                run_id="run_20260402_100000", document="3040", data_base="2026-03",
                status="completed", scope="full",
                summary=ValidationSummary(total_rules=145, passed=140, failed=3, warnings=2, pass_rate_pct=96.5),
                triggered_by="analyst@bankcorp.com", triggered_at="2026-04-02T10:00:00Z",
                completed_at="2026-04-02T10:42:00Z", duration_seconds=2520,
            ),
            RunSummary(
                run_id="run_20260331_100000", document="3050", data_base="2026-03-28",
                status="completed", scope="full",
                summary=ValidationSummary(total_rules=85, passed=83, failed=1, warnings=1, pass_rate_pct=97.6),
                triggered_by="analyst@bankcorp.com", triggered_at="2026-03-31T10:00:00Z",
                completed_at="2026-03-31T10:25:00Z", duration_seconds=1500,
            ),
        ]
        if document:
            runs = [r for r in runs if r.document == document]
        return ValidationRunsResponse(runs=runs[:limit])
    return ValidationRunsResponse(runs=[])
