"""Validation endpoints: results, trigger, status, runs.

Post-Phase-7 DQX wire-up: results are read from ``silver.criticas_results``
(a VIEW over ``silver.<tabela>_quarantine`` ∪ ``quality.dqx_checks`` — see
``docs/spec/08_dqx_app_integration.md`` §1.5 and §3). Each row surfaces:

- ``expectation_name`` (the DQX check name) → ``ValidationResult.check_name``
- ``nivel_verificacao`` from ``user_metadata`` (no longer hard-coded)
- a linkback URL to DQX Studio so the SA can jump straight to the rule editor.

Warning/fail rows also carry ``critica_id`` + ``run_config_name`` + ``dqx_run_id``
so the front-end can POST to ``/governance/incidents`` with the canonical
dedup key from §4.1.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from db import CATALOG, DQX_CHECKS_TABLE, SCHEMA_SILVER, USE_MOCK
from i18n import get_locale
# Tolerant variant aliased as `execute_query` so handlers degrade to empty
# results when silver tables haven't been populated yet (pipeline not run).
from db import execute_query_or_empty as execute_query
from rc18_rule_meta import meta_for
from models import (
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

# silver.criticas_results emits Portuguese vocabulary; normalize to the UI-facing one.
_DIM_ROMAN_TO_INT = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6,
                     "VII": 7, "VIII": 8, "IX": 9, "X": 10, "XI": 11, "XII": 12}
_SEVERITY_MAP = {"BLOQUEANTE": "error", "ALERTA": "warning", "INFO": "info"}
_STATUS_MAP = {"APROVADO": "pass", "REPROVADO": "fail", "ALERTA": "warning"}

# Default run_config_name when the view doesn't surface one (legacy data).
_RUN_CONFIG_DEFAULTS = {
    "3040": "silver_3040_operacoes",
    "3050": "silver_3050",
}


def _dqx_studio_configured_base() -> str | None:
    """Base URL do DQX Studio quando configurado de verdade.

    Trata como "desativado" três casos: env ausente, string vazia, e a
    sentinela `about:blank` (default do bundle quando o customer não
    setou a URL real). Retorna None nesses casos pra UI esconder
    deep-links e a aba Motor de Regras renderizar estado vazio.
    """
    base = os.getenv("DQX_STUDIO_URL", "").rstrip("/")
    if not base or base in ("about:blank",):
        return None
    return base


def dqx_check_url(run_config_name: str | None, check_name: str | None) -> str | None:
    """Linkback to DQX Studio para edição da regra.

    A Studio (`databrickslabs/dqx`) não tem um deep-link por
    `run_config_name`/`check_name` que mostre a regra direto no editor — as
    rotas internas do app são todas client-side. Por isso apontamos para
    `/rules/active`, que lista todas as regras ativas (incluindo as 4 do RC18
    + qualquer regra criada via UI da Studio). O usuário acha a regra na
    lista e clica para abrir o editor.
    """
    base = _dqx_studio_configured_base()
    if not base or not check_name:
        return None
    return f"{base}/rules/active"


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


def _normalize_critica_row(r: dict, documento: str) -> ValidationResult:
    """Map a silver.criticas_results row to the UI ValidationResult shape."""
    sev_raw = r.get("severidade") or ""
    status_raw = r.get("status") or ""
    dim_raw = r.get("dimension_r18")
    dim_int = (
        dim_raw if isinstance(dim_raw, int)
        else _DIM_ROMAN_TO_INT.get(str(dim_raw), 0)
    )
    total = int(r.get("registros_avaliados") or 0)
    nc = int(r.get("registros_nao_conformes") or 0)
    pct = float(r.get("taxa_conformidade_pct") or 0)
    nivel_raw = r.get("nivel_verificacao")
    try:
        nivel = int(nivel_raw) if nivel_raw is not None else 1
    except (TypeError, ValueError):
        nivel = 1
    critica_id = r.get("critica_id") or ""
    check_name = r.get("check_name") or r.get("expectation_name")
    run_cfg = r.get("run_config_name") or _RUN_CONFIG_DEFAULTS.get(documento)
    return ValidationResult(
        rule_id=critica_id,
        rule_name=r.get("critica_descricao") or "",
        rule_type=r.get("grupo") or "",
        severity=_SEVERITY_MAP.get(sev_raw, sev_raw.lower() if sev_raw else "info"),
        dimension_r18=dim_int,
        dimension_name=r.get("dimension_name") or "",
        status=_STATUS_MAP.get(status_raw, status_raw.lower() if status_raw else "pass"),
        affected_records=nc,
        total_records=total,
        affected_pct=round(100 - pct, 4) if total else 0.0,
        description=r.get("critica_descricao") or r.get("mensagem_erro") or "",
        sample_ipocs=list(r.get("sample_falhas") or []),
        nivel_verificacao=nivel,
        check_name=check_name,
        dqx_check_function=r.get("dqx_check_function"),
        dqx_check_url=dqx_check_url(run_cfg, check_name),
        run_config_name=run_cfg,
        dqx_run_id=r.get("dqx_run_id"),
        critica_id=critica_id or None,
    )


def _mock_vr(*, rule_id, run_config_name, check_name, dqx_check_function,
             rule_name, rule_type, severity, dimension_r18, dimension_name,
             status, affected_records, total_records, description, nivel,
             sample_ipocs=None):
    """Build a ValidationResult mock row with DQX-flavored fields wired up.

    Keeps the call sites readable and forces every mock entry to carry the
    same shape as a real row coming out of ``silver.criticas_results``.
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
    )


_RC_3040_OPER = "silver_3040_operacoes"
_RC_3040_CLI = "silver_3040_clientes"
_RC_3040_GAR = "silver_3040_garantias"
_RC_3040_VEN = "silver_3040_vencimentos"
_RC_3050 = "silver_3050"

# As 4 regras iniciais do acelerador — mesmo conjunto canônico semeado no
# deploy em `${var.catalog}.quality.dqx_checks` a partir de
# `pipelines/silver/dqx_checks/scr3040.yml`. Novas regras serão adicionadas via
# DQX Studio e aparecerão automaticamente assim que o pipeline silver as
# executar e popular `silver.criticas_results`.
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


# Canonical SQL columns selected from silver.criticas_results. ``expectation_name``
# and ``nivel_verificacao`` are the new fields surfaced by the post-Phase-7 view
# (see docs/spec/08_dqx_app_integration.md §1.5 / §3.1).
_CRITICAS_SQL = (
    "SELECT critica_id, "
    "       expectation_name AS check_name, "
    "       critica_descricao, "
    "       grupo, "
    "       severidade, "
    "       dimension_r18, "
    "       nivel_verificacao, "
    "       status, "
    "       registros_avaliados, "
    "       registros_conformes, "
    "       registros_nao_conformes, "
    "       taxa_conformidade_pct, "
    "       sample_falhas, "
    "       run_config_name, "
    "       dqx_run_id "
    f"FROM {{catalog}}.{{schema}}.criticas_results "
    "WHERE dt_base = :data_base AND documento = :documento "
    "  AND (:severidade IS NULL OR severidade = :severidade) "
    "  AND (:dim_roman  IS NULL OR dimension_r18 = :dim_roman) "
    "  AND (:nivel      IS NULL OR nivel_verificacao = :nivel) "
    "ORDER BY severidade DESC, registros_nao_conformes DESC "
    "LIMIT :page_size OFFSET :offset"
)

_SUMMARY_SQL = (
    "SELECT status, COUNT(*) AS n "
    f"FROM {{catalog}}.{{schema}}.criticas_results "
    "WHERE dt_base = :data_base AND documento = :documento "
    "GROUP BY status"
)


def _dim_int_to_roman(d: int | None) -> str | None:
    if not d:
        return None
    for roman, val in _DIM_ROMAN_TO_INT.items():
        if val == d:
            return roman
    return None


def _severity_ui_to_storage(sev: str | None) -> str | None:
    if not sev:
        return None
    for storage, ui in _SEVERITY_MAP.items():
        if ui == sev:
            return storage
    return None


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
# The Críticas SCR module no longer reads from `silver.criticas_results` (a
# view that depended on silver pipelines running DQX inline, which RC18 does
# NOT do yet). Instead it reads ACTIVE/APPROVED rules from
# `${DQX_CHECKS_TABLE}` + the LATEST run per source_table_fqn from
# `dqx_catalog.dqx_app.dq_validation_runs`, joined with `dq_metrics`
# (`metric_name = 'check_metrics'` carries a JSON array of per-check counts).
# Old rule definitions deleted from `dq_quality_rules` produce check_metrics
# entries that don't match any active rule — those are dropped silently.

_DOC_TO_TABLE_PREFIX = {
    "3040": "rc18_catalog.silver.scr3040_",
    "3050": "rc18_catalog.silver.scr3050",
}


async def _load_active_rules() -> dict[str, dict]:
    """Return {check_name: full_check_dict} for every ACTIVE/APPROVED rule.

    `full_check_dict` is the FIRST element of the row's `checks` JSON array
    (DQX Studio stores per-row arrays; RC18 seeds one element per row).
    """
    rows = await execute_query(
        f"SELECT rule_id, table_fqn, checks "
        f"FROM {DQX_CHECKS_TABLE} "
        "WHERE status IN ('active', 'approved')",
        {},
    )
    out: dict[str, dict] = {}
    for r in rows:
        chk_raw = r.get("checks")
        try:
            parsed = json.loads(chk_raw) if isinstance(chk_raw, str) else (chk_raw or [])
        except (json.JSONDecodeError, TypeError):
            continue
        items = parsed if isinstance(parsed, list) else ([parsed] if isinstance(parsed, dict) else [])
        for chk in items:
            if not isinstance(chk, dict):
                continue
            args = (chk.get("check") or {}).get("arguments") or {}
            name = chk.get("name") or (args.get("name") if isinstance(args, dict) else None)
            if name:
                out[name] = {**chk, "_row_table_fqn": r.get("table_fqn") or ""}
    return out


async def _fetch_studio_results(document: str) -> tuple[list[ValidationResult], str | None, str | None]:
    """Compose ValidationResult rows from DQX Studio's run history.

    For each source_table_fqn that matches `document`'s silver tables, pick the
    LATEST SUCCESS run. Parse its `check_metrics` and emit one ValidationResult
    per check that maps to an active RC18 rule (check_name → dq_quality_rules).
    """
    prefix = _DOC_TO_TABLE_PREFIX.get(document)
    if not prefix:
        return [], None, None

    # Step 1: latest SUCCESS run per source_table_fqn.
    runs_sql = (
        "WITH ranked AS ("
        "  SELECT run_id, source_table_fqn, total_rows, invalid_rows, created_at, "
        "         ROW_NUMBER() OVER (PARTITION BY source_table_fqn ORDER BY created_at DESC) AS rn "
        "  FROM dqx_catalog.dqx_app.dq_validation_runs "
        "  WHERE status = 'SUCCESS' "
        f"    AND source_table_fqn LIKE '{prefix}%'"
        ") SELECT run_id, source_table_fqn, total_rows, invalid_rows, created_at "
        "FROM ranked WHERE rn = 1"
    )
    runs = await execute_query(runs_sql, {})
    if not runs:
        return [], None, None

    # Step 2: check_metrics for those run_ids.
    quoted = ",".join(f"'{r['run_id']}'" for r in runs)
    metrics_sql = (
        "SELECT run_id, metric_value AS check_metrics_json "
        "FROM dqx_catalog.dqx_app.dq_metrics "
        f"WHERE metric_name = 'check_metrics' AND run_id IN ({quoted})"
    )
    metrics_rows = await execute_query(metrics_sql, {})
    metrics_by_run = {m["run_id"]: m for m in metrics_rows}

    # Step 3: active rules (check_name → check definition).
    rules_by_name = await _load_active_rules()

    results: list[ValidationResult] = []
    latest_run_id: str | None = None
    latest_run_time: str | None = None
    for r in runs:
        run_id = r["run_id"]
        total = int(r.get("total_rows") or 0)
        cm = metrics_by_run.get(run_id)
        if not cm:
            continue
        try:
            check_metrics = json.loads(cm["check_metrics_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(check_metrics, list):
            continue
        if latest_run_id is None or (r.get("created_at") or "") > (latest_run_time or ""):
            latest_run_id = run_id
            latest_run_time = r.get("created_at")
        for cmrow in check_metrics:
            check_name = cmrow.get("check_name")
            if not check_name:
                continue
            rule = rules_by_name.get(check_name)
            if not rule:
                # Stale rule (deleted definition); drop to keep catalog tight.
                continue
            err = int(cmrow.get("error_count") or 0)
            warn = int(cmrow.get("warning_count") or 0)
            affected = err + warn
            um = rule.get("user_metadata") or {}
            criticality = rule.get("criticality") or "error"
            sev = "error" if criticality == "error" else "warning"
            status = "pass" if affected == 0 else ("fail" if sev == "error" else "warning")
            run_cfg = rule.get("run_config_name") or ""
            check_fn = (rule.get("check") or {}).get("function", "")
            # Structural metadata: hard-coded in rc18_rule_meta.py (keeps YAML
            # tags clean — only `projeto` + `descricao`). user_metadata supplies
            # the human-facing description.
            meta = meta_for(
                check_name,
                table_fqn=rule.get("_row_table_fqn", ""),
                user_metadata=um,
            )
            description = um.get("descricao") or um.get("mensagem_erro") or check_name
            rule_name = description if len(description) < 80 else check_name
            results.append(ValidationResult(
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
            ))

    return results, latest_run_id, latest_run_time


_DIM_NAME_BY_INT = {
    1: "Acessibilidade", 2: "Acurácia", 3: "Adaptabilidade", 4: "Clareza",
    5: "Comparabilidade", 6: "Completude", 7: "Confiabilidade", 8: "Consistência",
    9: "Integridade", 10: "Rastreabilidade", 11: "Relevância", 12: "Tempestividade",
}


@router.get("/scr3040/results", response_model=ValidationResultsResponse)
async def get_validation_results_3040(
    data_base: str = Query("2026-03"),
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
        return ValidationResultsResponse(
            data_base=data_base,
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
        )

    # Real-mode: read DQX Studio's latest run + check_metrics + active rules.
    all_results, latest_run_id, latest_run_time = await _fetch_studio_results("3040")
    filtered = _apply_mock_filters(
        all_results,
        severity=severity, status=status, rule_type=rule_type,
        dimension_r18=dimension_r18, nivel_verificacao=nivel_verificacao,
    )
    total = len(filtered)
    start = (page - 1) * page_size
    paged = filtered[start : start + page_size]
    return ValidationResultsResponse(
        data_base=data_base,
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
    )


@router.get("/scr3050/results", response_model=ValidationResultsResponse)
async def get_validation_results_3050(
    data_base: str = Query("2026-03"),
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
        return ValidationResultsResponse(
            data_base=data_base, run_id="run_20260331_100000", run_status="completed",
            run_completed_at="2026-03-31T10:30:00Z",
            summary=_summary_from_results(mock_rules),
            results=mock_rules,
            pagination=Pagination(page=1, page_size=page_size,
                                  total_results=total, total_pages=1),
            studio_url=_studio_base_url(),
        )

    all_results, latest_run_id, latest_run_time = await _fetch_studio_results("3050")
    filtered = _apply_mock_filters(
        all_results,
        severity=severity, status=status, rule_type=None,
        dimension_r18=None, nivel_verificacao=None,
    )
    total = len(filtered)
    start = (page - 1) * page_size
    paged = filtered[start : start + page_size]
    return ValidationResultsResponse(
        data_base=data_base,
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
