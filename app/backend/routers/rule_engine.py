"""Rule Engine (Motor de Regras) endpoints: datasets, rules, bindings, execution, exceptions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from db import USE_MOCK as _DB_USE_MOCK, execute_query, fq, CATALOG, SCHEMA_QUALITY, SCHEMA_SILVER, SCHEMA_BRONZE

# re_* tables are not yet provisioned in <catalog>.quality; always serve mock data
USE_MOCK = True
from models import (
    Pagination,
    REBinding,
    REBindingCreate,
    REBindingListResponse,
    REColumn,
    REColumnListResponse,
    REDataset,
    REDatasetDetail,
    REDatasetListResponse,
    REException,
    REExceptionsResponse,
    REExpressionValidation,
    RERule,
    RERuleCreate,
    RERuleListResponse,
    RERunListResponse,
    RERunResult,
    RERunResultsResponse,
    RERunResultsSummary,
    RERunStatus,
    RESeedResponse,
    RETriggerRunResponse,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Mock data: Datasets
# ---------------------------------------------------------------------------

_MOCK_DATASETS = [
    REDataset(
        dataset_id="ds_001",
        name="Operacoes Validadas (Silver)",
        source_path=f"{CATALOG}.{SCHEMA_SILVER}.operacoes_validadas",
        tipo="table",
        data_base="2026-03",
        row_count_approx=1_500_000,
        registered_by="analyst@bankcorp.com",
        registered_at="2026-03-15T10:00:00Z",
    ),
    REDataset(
        dataset_id="ds_002",
        name="SCR 3050 Validated (Silver)",
        source_path=f"{CATALOG}.{SCHEMA_SILVER}.scr3050_validated",
        tipo="table",
        data_base="2026-03",
        row_count_approx=210_000,
        registered_by="analyst@bankcorp.com",
        registered_at="2026-03-15T10:30:00Z",
    ),
    REDataset(
        dataset_id="ds_003",
        name="Operacoes Raw (Bronze)",
        source_path=f"{CATALOG}.{SCHEMA_BRONZE}.operacoes_raw",
        tipo="table",
        data_base="2026-03",
        row_count_approx=1_500_000,
        registered_by="analyst@bankcorp.com",
        registered_at="2026-03-16T09:00:00Z",
    ),
    REDataset(
        dataset_id="ds_004",
        name="Clientes Validados (Silver)",
        source_path=f"{CATALOG}.{SCHEMA_SILVER}.scr3040_clientes",
        tipo="table",
        data_base="2026-03",
        row_count_approx=750_000,
        registered_by="analyst@bankcorp.com",
        registered_at="2026-03-16T11:00:00Z",
    ),
]

# ---------------------------------------------------------------------------
# Mock data: Columns per dataset
# ---------------------------------------------------------------------------

_MOCK_COLUMNS: dict[str, list[REColumn]] = {
    "ds_001": [
        REColumn(name="_pk_hash", type="STRING", nullable=False),
        REColumn(name="cnpj_if", type="STRING", nullable=False, description="CNPJ da IF (8 digitos)"),
        REColumn(name="dt_base", type="STRING", nullable=False, description="Data-base AAAA-MM"),
        REColumn(name="contrt", type="STRING", nullable=False, description="Numero do contrato"),
        REColumn(name="dt_contr", type="DATE", nullable=True, description="Data de contratacao"),
        REColumn(name="dt_venc_op", type="DATE", nullable=True, description="Data de vencimento"),
        REColumn(name="mod", type="STRING", nullable=False, description="Modalidade (4 digitos)"),
        REColumn(name="natu_op", type="STRING", nullable=False, description="Natureza da operacao"),
        REColumn(name="class_op", type="STRING", nullable=True, description="Classificacao de risco"),
        REColumn(name="ipoc", type="STRING", nullable=True, description="IPOC da operacao"),
        REColumn(name="vlr_contr", type="DECIMAL(15,2)", nullable=True, description="Valor do contrato"),
        REColumn(name="tax_eft", type="DECIMAL(10,4)", nullable=True, description="Taxa efetiva"),
        REColumn(name="cep", type="STRING", nullable=True, description="CEP da agencia"),
        REColumn(name="dia_atraso", type="INTEGER", nullable=True, description="Dias de atraso"),
        REColumn(name="cli_tp", type="STRING", nullable=False, description="Tipo de cliente"),
        REColumn(name="cli_cd", type="STRING", nullable=False, description="Codigo do cliente"),
        REColumn(name="prov_consttd", type="DECIMAL(15,2)", nullable=True, description="Provisao constituida"),
        REColumn(name="is_valid", type="BOOLEAN", nullable=False, description="Flag de validacao"),
    ],
    "ds_002": [
        REColumn(name="txb_sk", type="STRING", nullable=False, description="Surrogate key TXB"),
        REColumn(name="cnpj_if", type="STRING", nullable=False, description="CNPJ da IF (8 digitos)"),
        REColumn(name="dt_base_semanal", type="STRING", nullable=False, description="Data-base semanal"),
        REColumn(name="dt_referencia", type="DATE", nullable=False, description="Data de referencia"),
        REColumn(name="modalidade", type="STRING", nullable=False, description="Modalidade 3050"),
        REColumn(name="encargo", type="STRING", nullable=False, description="Tipo de encargo"),
        REColumn(name="segmento", type="STRING", nullable=False, description="Segmento de cliente"),
        REColumn(name="vlr_concessoes", type="DECIMAL(15,2)", nullable=True, description="Valor das concessoes"),
        REColumn(name="tx_med_juros", type="DECIMAL(10,4)", nullable=True, description="Taxa media de juros"),
        REColumn(name="sld_car_ativa", type="DECIMAL(15,2)", nullable=True, description="Saldo carteira ativa"),
        REColumn(name="leiaute_versao", type="STRING", nullable=False, description="Versao do leiaute"),
        REColumn(name="is_valid", type="BOOLEAN", nullable=False, description="Flag de validacao"),
    ],
    "ds_003": [],  # bronze — no detailed columns exposed
    "ds_004": [
        REColumn(name="cli_sk", type="STRING", nullable=False, description="Surrogate key cliente"),
        REColumn(name="cnpj_if", type="STRING", nullable=False, description="CNPJ da IF (8 digitos)"),
        REColumn(name="dt_base", type="STRING", nullable=False, description="Data-base AAAA-MM"),
        REColumn(name="cli_tp", type="STRING", nullable=False, description="Tipo de cliente"),
        REColumn(name="cli_cd", type="STRING", nullable=False, description="Codigo do cliente"),
        REColumn(name="cli_class", type="STRING", nullable=True, description="Classificacao do cliente"),
        REColumn(name="cli_porte", type="STRING", nullable=True, description="Porte do cliente"),
        REColumn(name="cli_fat_anual", type="DECIMAL(15,2)", nullable=True, description="Faturamento anual"),
        REColumn(name="is_valid", type="BOOLEAN", nullable=False, description="Flag de validacao"),
    ],
}

# ---------------------------------------------------------------------------
# Mock data: Rules
# ---------------------------------------------------------------------------

_MOCK_RULES = [
    RERule(
        rule_id="re_001",
        name="Campo obrigatorio (NOT NULL)",
        description="Verifica se o campo especificado nao e nulo.",
        nivel_verificacao=1,
        dimension_r18=6,
        severity="error",
        rule_type="syntactic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [{"column": "{column_1}", "operator": "IS_NOT_NULL"}],
        },
        parameters=[{"name": "column_1", "type": "any", "description": "Campo obrigatorio a validar"}],
        is_seeded=True,
        source_critica_id="S10_001",
        created_by="system",
        created_at="2026-03-15T10:00:00Z",
        updated_at="2026-03-15T10:00:00Z",
    ),
    RERule(
        rule_id="re_002",
        name="Tamanho de campo fixo",
        description="Verifica se o campo possui tamanho exato.",
        nivel_verificacao=1,
        dimension_r18=6,
        severity="error",
        rule_type="syntactic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [{"column": "{column_1}", "operator": "LENGTH_EQUALS", "value": "{value_1}"}],
        },
        parameters=[
            {"name": "column_1", "type": "string", "description": "Campo a validar"},
            {"name": "value_1", "type": "integer", "description": "Tamanho esperado"},
        ],
        is_seeded=True,
        source_critica_id="S10_002",
        created_by="system",
        created_at="2026-03-15T10:00:00Z",
        updated_at="2026-03-15T10:00:00Z",
    ),
    RERule(
        rule_id="re_003",
        name="Componentes IPOC consistentes",
        description="Verifica se os 8 primeiros digitos do IPOC correspondem ao CNPJ da IF.",
        nivel_verificacao=1,
        dimension_r18=2,
        severity="error",
        rule_type="semantic",
        authoring_mode="expression",
        expression="SUBSTRING({ipoc_column}, 1, 8) == {cnpj_column}",
        parameters=[
            {"name": "ipoc_column", "type": "string", "description": "Coluna IPOC"},
            {"name": "cnpj_column", "type": "string", "description": "Coluna CNPJ"},
        ],
        is_seeded=True,
        source_critica_id="SEM_014",
        created_by="system",
        created_at="2026-03-15T10:00:00Z",
        updated_at="2026-03-15T10:00:00Z",
    ),
    RERule(
        rule_id="re_004",
        name="Data vencimento posterior a contratacao",
        description="Verifica se a data de vencimento e igual ou posterior a data de contratacao.",
        nivel_verificacao=2,
        dimension_r18=8,
        severity="error",
        rule_type="semantic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [
                {
                    "column": "{column_1}",
                    "operator": "GREATER_THAN_OR_EQUALS",
                    "value": "{column_2}",
                    "value_is_column": True,
                }
            ],
        },
        parameters=[
            {"name": "column_1", "type": "date", "description": "Data posterior"},
            {"name": "column_2", "type": "date", "description": "Data anterior"},
        ],
        is_seeded=True,
        source_critica_id="SEM_020",
        created_by="system",
        created_at="2026-03-15T10:00:00Z",
        updated_at="2026-03-15T10:00:00Z",
    ),
    RERule(
        rule_id="re_005",
        name="Valor dentro do dominio",
        description="Verifica se o valor pertence a lista de dominio valido.",
        nivel_verificacao=1,
        dimension_r18=6,
        severity="error",
        rule_type="syntactic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [
                {"column": "{column_1}", "operator": "IN", "value": ["AA", "A", "B", "C", "D", "E", "F", "G", "H"]}
            ],
        },
        parameters=[{"name": "column_1", "type": "string", "description": "Campo com dominio"}],
        is_seeded=False,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-17T14:00:00Z",
        updated_at="2026-03-17T14:00:00Z",
    ),
    RERule(
        rule_id="re_006",
        name="Valor positivo",
        description="Verifica se o campo numerico possui valor maior que zero.",
        nivel_verificacao=1,
        dimension_r18=2,
        severity="warning",
        rule_type="syntactic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [{"column": "{column_1}", "operator": "GREATER_THAN", "value": 0}],
        },
        parameters=[{"name": "column_1", "type": "numeric", "description": "Campo numerico a validar"}],
        is_seeded=False,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-17T15:00:00Z",
        updated_at="2026-03-17T15:00:00Z",
    ),
    RERule(
        rule_id="re_007",
        name="Formato CEP valido",
        description="Verifica se o CEP possui exatamente 8 digitos numericos.",
        nivel_verificacao=1,
        dimension_r18=6,
        severity="warning",
        rule_type="syntactic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [{"column": "{column_1}", "operator": "MATCHES_REGEX", "value": "^\\d{8}$"}],
        },
        parameters=[{"name": "column_1", "type": "string", "description": "Coluna de CEP"}],
        is_seeded=False,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-18T09:00:00Z",
        updated_at="2026-03-18T09:00:00Z",
    ),
    RERule(
        rule_id="re_008",
        name="Unicidade de chave",
        description="Verifica se nao existem registros duplicados para a chave especificada.",
        nivel_verificacao=1,
        dimension_r18=12,
        severity="error",
        rule_type="syntactic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [{"column": "{column_1}", "operator": "IS_UNIQUE"}],
        },
        parameters=[{"name": "column_1", "type": "any", "description": "Coluna(s) de chave primaria"}],
        is_seeded=False,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-18T10:00:00Z",
        updated_at="2026-03-18T10:00:00Z",
    ),
    RERule(
        rule_id="re_009",
        name="Faixa de taxa efetiva",
        description="Verifica se a taxa efetiva esta dentro da faixa permitida (0 a 999.99).",
        nivel_verificacao=2,
        dimension_r18=2,
        severity="warning",
        rule_type="semantic",
        authoring_mode="structured",
        structured_definition={
            "version": 1,
            "operator": "AND",
            "conditions": [{"column": "{column_1}", "operator": "BETWEEN", "value": [0, 999.99]}],
        },
        parameters=[{"name": "column_1", "type": "numeric", "description": "Coluna de taxa"}],
        is_seeded=False,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-18T11:00:00Z",
        updated_at="2026-03-18T11:00:00Z",
    ),
    RERule(
        rule_id="re_010",
        name="Valor concessao positivo",
        description="Verifica se o valor de concessao e estritamente positivo.",
        nivel_verificacao=3,
        dimension_r18=2,
        severity="error",
        rule_type="business",
        authoring_mode="expression",
        expression="{valor_column} > 0",
        parameters=[{"name": "valor_column", "type": "numeric", "description": "Coluna de valor"}],
        is_seeded=True,
        source_critica_id="CR4_001",
        created_by="system",
        created_at="2026-03-15T10:00:00Z",
        updated_at="2026-03-15T10:00:00Z",
    ),
]

# ---------------------------------------------------------------------------
# Mock data: Bindings
# ---------------------------------------------------------------------------

_MOCK_BINDINGS = [
    REBinding(
        binding_id="bind_001",
        rule_id="re_001",
        dataset_id="ds_001",
        rule_name="Campo obrigatorio (NOT NULL)",
        column_bindings={"column_1": "dt_contr"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T10:00:00Z",
    ),
    REBinding(
        binding_id="bind_002",
        rule_id="re_001",
        dataset_id="ds_001",
        rule_name="Campo obrigatorio (NOT NULL)",
        column_bindings={"column_1": "mod"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T10:05:00Z",
    ),
    REBinding(
        binding_id="bind_003",
        rule_id="re_002",
        dataset_id="ds_001",
        rule_name="Tamanho de campo fixo",
        column_bindings={"column_1": "cnpj_if", "value_1": "8"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T10:10:00Z",
    ),
    REBinding(
        binding_id="bind_004",
        rule_id="re_004",
        dataset_id="ds_001",
        rule_name="Data vencimento posterior a contratacao",
        column_bindings={"column_1": "dt_venc_op", "column_2": "dt_contr"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T10:15:00Z",
    ),
    REBinding(
        binding_id="bind_005",
        rule_id="re_005",
        dataset_id="ds_001",
        rule_name="Valor dentro do dominio",
        column_bindings={"column_1": "class_op"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T10:20:00Z",
    ),
    REBinding(
        binding_id="bind_006",
        rule_id="re_006",
        dataset_id="ds_002",
        rule_name="Valor positivo",
        column_bindings={"column_1": "vlr_concessoes"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T11:00:00Z",
    ),
    REBinding(
        binding_id="bind_007",
        rule_id="re_009",
        dataset_id="ds_001",
        rule_name="Faixa de taxa efetiva",
        column_bindings={"column_1": "tax_eft"},
        is_active=True,
        created_by="analyst@bankcorp.com",
        created_at="2026-03-20T11:05:00Z",
    ),
]

# ---------------------------------------------------------------------------
# Mock data: Runs, results, and exceptions
# ---------------------------------------------------------------------------

_MOCK_RUNS = [
    RERunStatus(
        run_id="run_re_001",
        dataset_id="ds_001",
        dataset_name="Operacoes Validadas (Silver)",
        status="completed",
        triggered_by="analyst@bankcorp.com",
        triggered_at="2026-03-30T14:00:00Z",
        completed_at="2026-03-30T14:22:00Z",
        total_rules=6,
        passed=4,
        failed=2,
    ),
    RERunStatus(
        run_id="run_re_002",
        dataset_id="ds_002",
        dataset_name="SCR 3050 Diario (Silver)",
        status="completed",
        triggered_by="analyst@bankcorp.com",
        triggered_at="2026-03-30T15:00:00Z",
        completed_at="2026-03-30T15:08:00Z",
        total_rules=1,
        passed=0,
        failed=1,
    ),
    RERunStatus(
        run_id="run_re_003",
        dataset_id="ds_001",
        dataset_name="Operacoes Validadas (Silver)",
        status="completed",
        triggered_by="analyst@bankcorp.com",
        triggered_at="2026-03-31T10:00:00Z",
        completed_at="2026-03-31T10:18:00Z",
        total_rules=5,
        passed=5,
        failed=0,
    ),
]

_MOCK_RUN_RESULTS: dict[str, list[RERunResult]] = {
    "run_re_001": [
        RERunResult(
            result_id="res_001",
            binding_id="bind_001",
            rule_id="re_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            status="fail",
            total_records=1_500_000,
            passed_records=1_499_958,
            failed_records=42,
            pass_rate_pct=99.9972,
            severity="error",
            dimension_r18=6,
            execution_time_ms=4200,
            expression_used="dt_contr IS NOT NULL",
        ),
        RERunResult(
            result_id="res_002",
            binding_id="bind_002",
            rule_id="re_001",
            rule_name="Campo obrigatorio (NOT NULL) — mod",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=3800,
            expression_used="mod IS NOT NULL",
        ),
        RERunResult(
            result_id="res_003",
            binding_id="bind_003",
            rule_id="re_002",
            rule_name="Tamanho de campo fixo — cnpj_if (8)",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=3500,
            expression_used="LENGTH(cnpj_if) = 8",
        ),
        RERunResult(
            result_id="res_004",
            binding_id="bind_004",
            rule_id="re_004",
            rule_name="Data vencimento posterior a contratacao",
            status="fail",
            total_records=1_500_000,
            passed_records=1_499_985,
            failed_records=15,
            pass_rate_pct=99.999,
            severity="error",
            dimension_r18=8,
            execution_time_ms=5100,
            expression_used="dt_venc_op >= dt_contr",
        ),
        RERunResult(
            result_id="res_005",
            binding_id="bind_005",
            rule_id="re_005",
            rule_name="Valor dentro do dominio — class_op",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=4600,
            expression_used="class_op IN ('AA','A','B','C','D','E','F','G','H')",
        ),
        RERunResult(
            result_id="res_007",
            binding_id="bind_007",
            rule_id="re_009",
            rule_name="Faixa de taxa efetiva — tax_eft",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="warning",
            dimension_r18=2,
            execution_time_ms=3200,
            expression_used="tax_eft BETWEEN 0 AND 999.99",
        ),
    ],
    "run_re_002": [
        RERunResult(
            result_id="res_006",
            binding_id="bind_006",
            rule_id="re_006",
            rule_name="Valor positivo — vlr_concessoes",
            status="fail",
            total_records=210_000,
            passed_records=209_995,
            failed_records=5,
            pass_rate_pct=99.9976,
            severity="warning",
            dimension_r18=2,
            execution_time_ms=1800,
            expression_used="vlr_concessoes > 0",
        ),
    ],
    "run_re_003": [
        RERunResult(
            result_id="res_008",
            binding_id="bind_001",
            rule_id="re_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=4100,
            expression_used="dt_contr IS NOT NULL",
        ),
        RERunResult(
            result_id="res_009",
            binding_id="bind_002",
            rule_id="re_001",
            rule_name="Campo obrigatorio (NOT NULL) — mod",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=3700,
            expression_used="mod IS NOT NULL",
        ),
        RERunResult(
            result_id="res_010",
            binding_id="bind_003",
            rule_id="re_002",
            rule_name="Tamanho de campo fixo — cnpj_if (8)",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=3400,
            expression_used="LENGTH(cnpj_if) = 8",
        ),
        RERunResult(
            result_id="res_011",
            binding_id="bind_004",
            rule_id="re_004",
            rule_name="Data vencimento posterior a contratacao",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=8,
            execution_time_ms=5000,
            expression_used="dt_venc_op >= dt_contr",
        ),
        RERunResult(
            result_id="res_012",
            binding_id="bind_005",
            rule_id="re_005",
            rule_name="Valor dentro do dominio — class_op",
            status="pass",
            total_records=1_500_000,
            passed_records=1_500_000,
            failed_records=0,
            pass_rate_pct=100.0,
            severity="error",
            dimension_r18=6,
            execution_time_ms=4500,
            expression_used="class_op IN ('AA','A','B','C','D','E','F','G','H')",
        ),
    ],
}

# Exceptions for run_re_001: bind_001 (42 total, show 5), bind_004 (15 total, show 3)
# Exceptions for run_re_002: bind_006 (5 total, show 3)
_MOCK_EXCEPTIONS: dict[str, list[REException]] = {
    "run_re_001": [
        # bind_001 — dt_contr IS NULL (42 total, 5 samples)
        REException(
            exception_id="exc_001",
            result_id="res_001",
            binding_id="bind_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            row_identifier={"contrt": "OP-2026-00042", "dt_base": "2026-03"},
            failed_columns=["dt_contr"],
            row_snapshot={"contrt": "OP-2026-00042", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": None, "mod": "0201"},
            failure_reason="dt_contr e NULL",
        ),
        REException(
            exception_id="exc_002",
            result_id="res_001",
            binding_id="bind_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            row_identifier={"contrt": "OP-2026-00087", "dt_base": "2026-03"},
            failed_columns=["dt_contr"],
            row_snapshot={"contrt": "OP-2026-00087", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": None, "mod": "0204"},
            failure_reason="dt_contr e NULL",
        ),
        REException(
            exception_id="exc_003",
            result_id="res_001",
            binding_id="bind_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            row_identifier={"contrt": "OP-2026-00153", "dt_base": "2026-03"},
            failed_columns=["dt_contr"],
            row_snapshot={"contrt": "OP-2026-00153", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": None, "mod": "0301"},
            failure_reason="dt_contr e NULL",
        ),
        REException(
            exception_id="exc_004",
            result_id="res_001",
            binding_id="bind_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            row_identifier={"contrt": "OP-2026-00271", "dt_base": "2026-03"},
            failed_columns=["dt_contr"],
            row_snapshot={"contrt": "OP-2026-00271", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": None, "mod": "0401"},
            failure_reason="dt_contr e NULL",
        ),
        REException(
            exception_id="exc_005",
            result_id="res_001",
            binding_id="bind_001",
            rule_name="Campo obrigatorio (NOT NULL) — dt_contr",
            row_identifier={"contrt": "OP-2026-00399", "dt_base": "2026-03"},
            failed_columns=["dt_contr"],
            row_snapshot={"contrt": "OP-2026-00399", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": None, "mod": "0202"},
            failure_reason="dt_contr e NULL",
        ),
        # bind_004 — dt_venc_op < dt_contr (15 total, 3 samples)
        REException(
            exception_id="exc_006",
            result_id="res_004",
            binding_id="bind_004",
            rule_name="Data vencimento posterior a contratacao",
            row_identifier={"contrt": "OP-2026-01020", "dt_base": "2026-03"},
            failed_columns=["dt_venc_op", "dt_contr"],
            row_snapshot={"contrt": "OP-2026-01020", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": "2026-02-15", "dt_venc_op": "2025-11-30", "mod": "0201"},
            failure_reason="dt_venc_op (2025-11-30) e anterior a dt_contr (2026-02-15)",
        ),
        REException(
            exception_id="exc_007",
            result_id="res_004",
            binding_id="bind_004",
            rule_name="Data vencimento posterior a contratacao",
            row_identifier={"contrt": "OP-2026-02450", "dt_base": "2026-03"},
            failed_columns=["dt_venc_op", "dt_contr"],
            row_snapshot={"contrt": "OP-2026-02450", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": "2026-01-10", "dt_venc_op": "2025-12-20", "mod": "0204"},
            failure_reason="dt_venc_op (2025-12-20) e anterior a dt_contr (2026-01-10)",
        ),
        REException(
            exception_id="exc_008",
            result_id="res_004",
            binding_id="bind_004",
            rule_name="Data vencimento posterior a contratacao",
            row_identifier={"contrt": "OP-2026-03888", "dt_base": "2026-03"},
            failed_columns=["dt_venc_op", "dt_contr"],
            row_snapshot={"contrt": "OP-2026-03888", "dt_base": "2026-03", "cnpj_if": "99999999", "dt_contr": "2026-03-01", "dt_venc_op": "2026-02-28", "mod": "0301"},
            failure_reason="dt_venc_op (2026-02-28) e anterior a dt_contr (2026-03-01)",
        ),
    ],
    "run_re_002": [
        REException(
            exception_id="exc_009",
            result_id="res_006",
            binding_id="bind_006",
            rule_name="Valor positivo — vlr_concessoes",
            row_identifier={"txb_sk": "TXB-2026-00101", "dt_base_semanal": "2026-03-27"},
            failed_columns=["vlr_concessoes"],
            row_snapshot={"txb_sk": "TXB-2026-00101", "cnpj_if": "99999999", "dt_base_semanal": "2026-03-27", "modalidade": "capitalDeGiro", "vlr_concessoes": -1500.00},
            failure_reason="vlr_concessoes (-1500.00) nao e positivo",
        ),
        REException(
            exception_id="exc_010",
            result_id="res_006",
            binding_id="bind_006",
            rule_name="Valor positivo — vlr_concessoes",
            row_identifier={"txb_sk": "TXB-2026-00204", "dt_base_semanal": "2026-03-27"},
            failed_columns=["vlr_concessoes"],
            row_snapshot={"txb_sk": "TXB-2026-00204", "cnpj_if": "99999999", "dt_base_semanal": "2026-03-27", "modalidade": "crdPessoal", "vlr_concessoes": 0.00},
            failure_reason="vlr_concessoes (0.00) nao e positivo",
        ),
        REException(
            exception_id="exc_011",
            result_id="res_006",
            binding_id="bind_006",
            rule_name="Valor positivo — vlr_concessoes",
            row_identifier={"txb_sk": "TXB-2026-00317", "dt_base_semanal": "2026-03-27"},
            failed_columns=["vlr_concessoes"],
            row_snapshot={"txb_sk": "TXB-2026-00317", "cnpj_if": "99999999", "dt_base_semanal": "2026-03-27", "modalidade": "descDuplicatas", "vlr_concessoes": -250.75},
            failure_reason="vlr_concessoes (-250.75) nao e positivo",
        ),
    ],
    # run_re_003 has no exceptions (all pass after fixes)
    "run_re_003": [],
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _find_dataset(dataset_id: str) -> REDataset | None:
    return next((d for d in _MOCK_DATASETS if d.dataset_id == dataset_id), None)


def _find_rule(rule_id: str) -> RERule | None:
    return next((r for r in _MOCK_RULES if r.rule_id == rule_id), None)


def _find_run(run_id: str) -> RERunStatus | None:
    return next((r for r in _MOCK_RUNS if r.run_id == run_id), None)


# ===================================================================
# Endpoints: Datasets
# ===================================================================


@router.get("/datasets", response_model=REDatasetListResponse)
async def list_datasets(
    search: str | None = Query(None, description="Filter datasets by name (case-insensitive)"),
):
    """List registered datasets."""
    if USE_MOCK:
        items = _MOCK_DATASETS
        if search:
            search_lower = search.lower()
            items = [d for d in items if search_lower in d.name.lower()]
        return REDatasetListResponse(total=len(items), datasets=items)

    rows = await execute_query(
        f"SELECT dataset_id, name, source_path, tipo, data_base, description, row_count_approx, "
        f"last_profiled_at, registered_by, registered_at "
        f"FROM {fq(SCHEMA_QUALITY, 're_datasets')} "
        f"WHERE is_active = TRUE "
        f"AND (:search IS NULL OR LOWER(name) LIKE CONCAT('%%', LOWER(:search), '%%')) "
        f"ORDER BY registered_at DESC",
        {"search": search},
    )
    datasets = [
        REDataset(
            dataset_id=r["dataset_id"], name=r["name"], source_path=r["source_path"],
            tipo=r["tipo"], data_base=r.get("data_base"), description=r.get("description"),
            row_count_approx=r.get("row_count_approx"),
            last_profiled_at=str(r["last_profiled_at"]) if r.get("last_profiled_at") else None,
            registered_by=r["registered_by"], registered_at=str(r["registered_at"]),
        )
        for r in rows
    ]
    return REDatasetListResponse(total=len(datasets), datasets=datasets)


@router.post("/datasets", response_model=REDataset, status_code=201)
async def create_dataset(req: dict):
    """Register a new dataset for rule evaluation."""
    if USE_MOCK:
        now = datetime.now(timezone.utc).isoformat()
        ds = REDataset(
            dataset_id=f"ds_{uuid.uuid4().hex[:6]}",
            name=req.get("name", "New Dataset"),
            source_path=req.get("source_path", f"{CATALOG}.{SCHEMA_SILVER}.new_table"),
            tipo=req.get("tipo", "table"),
            data_base=req.get("data_base"),
            row_count_approx=req.get("row_count_approx"),
            registered_by="analyst@bankcorp.com",
            registered_at=now,
        )
        _MOCK_DATASETS.append(ds)
        # Generate placeholder columns for new datasets
        _MOCK_COLUMNS[ds.dataset_id] = [
            REColumn(name="id", type="BIGINT", nullable=False, description="Identificador unico"),
            REColumn(name="dt_base", type="STRING", nullable=False, description="Data-base AAAA-MM"),
            REColumn(name="cnpj_if", type="STRING", nullable=False, description="CNPJ da IF (8 digitos)"),
            REColumn(name="valor", type="DECIMAL(15,2)", nullable=True, description="Valor monetario"),
            REColumn(name="status", type="STRING", nullable=True, description="Status do registro"),
            REColumn(name="created_at", type="TIMESTAMP", nullable=False, description="Data de criacao"),
        ]
        return ds

    now = datetime.now(timezone.utc).isoformat()
    ds_id = f"ds_{uuid.uuid4().hex[:6]}"
    await execute_query(
        f"INSERT INTO {fq(SCHEMA_QUALITY, 're_datasets')} "
        f"(dataset_id, name, source_path, tipo, data_base, registered_by, registered_at, is_active) "
        f"VALUES (:dataset_id, :name, :source_path, :tipo, :data_base, :registered_by, :registered_at, TRUE)",
        {
            "dataset_id": ds_id, "name": req.get("name"), "source_path": req.get("source_path"),
            "tipo": req.get("tipo", "table"), "data_base": req.get("data_base"),
            "registered_by": "analyst@bankcorp.com", "registered_at": now,
        },
    )
    return REDataset(
        dataset_id=ds_id, name=req["name"], source_path=req["source_path"],
        tipo=req.get("tipo", "table"), data_base=req.get("data_base"),
        registered_by="analyst@bankcorp.com", registered_at=now,
    )


@router.get("/datasets/{dataset_id}", response_model=REDatasetDetail)
async def get_dataset(dataset_id: str):
    """Return dataset detail including columns, bindings count, and last run."""
    if USE_MOCK:
        ds = _find_dataset(dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        cols = _MOCK_COLUMNS.get(dataset_id, [])
        bindings_count = sum(1 for b in _MOCK_BINDINGS if b.dataset_id == dataset_id)
        last_run = None
        for run in reversed(_MOCK_RUNS):
            if run.dataset_id == dataset_id:
                last_run = run.completed_at
                break
        return REDatasetDetail(dataset=ds, columns=cols, bindings_count=bindings_count, last_run=last_run)

    rows = await execute_query(
        f"SELECT dataset_id, name, source_path, tipo, data_base, description, row_count_approx, "
        f"last_profiled_at, registered_by, registered_at "
        f"FROM {fq(SCHEMA_QUALITY, 're_datasets')} WHERE dataset_id = :dataset_id AND is_active = TRUE",
        {"dataset_id": dataset_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    r = rows[0]
    ds = REDataset(
        dataset_id=r["dataset_id"], name=r["name"], source_path=r["source_path"],
        tipo=r["tipo"], data_base=r.get("data_base"),
        registered_by=r["registered_by"], registered_at=str(r["registered_at"]),
    )
    col_rows = await execute_query(
        f"SELECT column_name, data_type, is_nullable, description "
        f"FROM {fq(SCHEMA_QUALITY, 're_dataset_columns')} WHERE dataset_id = :dataset_id ORDER BY ordinal_position",
        {"dataset_id": dataset_id},
    )
    cols = [
        REColumn(name=c["column_name"], type=c["data_type"], nullable=c["is_nullable"], description=c.get("description"))
        for c in col_rows
    ]
    return REDatasetDetail(dataset=ds, columns=cols, bindings_count=0, last_run=None)


@router.get("/datasets/{dataset_id}/columns", response_model=REColumnListResponse)
async def list_dataset_columns(dataset_id: str):
    """Return column definitions for a dataset."""
    if USE_MOCK:
        ds = _find_dataset(dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        cols = _MOCK_COLUMNS.get(dataset_id, [])
        return REColumnListResponse(dataset_id=dataset_id, table_name=ds.source_path, columns=cols)

    ds_rows = await execute_query(
        f"SELECT source_path FROM {fq(SCHEMA_QUALITY, 're_datasets')} "
        f"WHERE dataset_id = :dataset_id AND is_active = TRUE",
        {"dataset_id": dataset_id},
    )
    if not ds_rows:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    col_rows = await execute_query(
        f"SELECT column_name, data_type, is_nullable, description "
        f"FROM {fq(SCHEMA_QUALITY, 're_dataset_columns')} WHERE dataset_id = :dataset_id ORDER BY ordinal_position",
        {"dataset_id": dataset_id},
    )
    cols = [
        REColumn(name=c["column_name"], type=c["data_type"], nullable=c["is_nullable"], description=c.get("description"))
        for c in col_rows
    ]
    return REColumnListResponse(dataset_id=dataset_id, table_name=ds_rows[0]["source_path"], columns=cols)


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """Soft-delete a dataset."""
    if USE_MOCK:
        ds = _find_dataset(dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        return {"ok": True}

    rows = await execute_query(
        f"SELECT dataset_id FROM {fq(SCHEMA_QUALITY, 're_datasets')} "
        f"WHERE dataset_id = :dataset_id AND is_active = TRUE",
        {"dataset_id": dataset_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    await execute_query(
        f"UPDATE {fq(SCHEMA_QUALITY, 're_datasets')} SET is_active = FALSE WHERE dataset_id = :dataset_id",
        {"dataset_id": dataset_id},
    )
    return {"ok": True}


# ===================================================================
# Endpoints: Rules
# ===================================================================


@router.get("/", response_model=RERuleListResponse)
async def list_rules(
    nivel_verificacao: int | None = Query(None, description="Filter by nivel de verificacao (1, 2, or 3)"),
    rule_type: str | None = Query(None, description="Filter by rule type (syntactic, semantic, inter_document, business)"),
    dimension_r18: int | None = Query(None, description="Filter by R.18 dimension ID"),
    severity: str | None = Query(None, description="Filter by severity (error, warning)"),
    search: str | None = Query(None, description="Full-text search on name and description"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all rules with optional filters and pagination."""
    if USE_MOCK:
        items = list(_MOCK_RULES)
        if nivel_verificacao:
            items = [r for r in items if r.nivel_verificacao == nivel_verificacao]
        if rule_type:
            items = [r for r in items if r.rule_type == rule_type]
        if dimension_r18 is not None:
            items = [r for r in items if r.dimension_r18 == dimension_r18]
        if severity:
            items = [r for r in items if r.severity == severity]
        if search:
            search_lower = search.lower()
            items = [
                r for r in items
                if search_lower in r.name.lower() or (r.description and search_lower in r.description.lower())
            ]
        total = len(items)
        start = (page - 1) * page_size
        paged = items[start : start + page_size]
        return RERuleListResponse(total=total, rules=paged)

    query_parts = [
        f"SELECT rule_id, name, description, nivel_verificacao, dimension_r18, severity, rule_type, "
        f"authoring_mode, structured_definition, expression, parameters, tags, is_seeded, source_critica_id, "
        f"created_by, created_at, updated_at, is_active "
        f"FROM {fq(SCHEMA_QUALITY, 're_rules')} WHERE is_active = TRUE",
    ]
    params: dict = {}
    if nivel_verificacao:
        query_parts.append("AND nivel_verificacao = :nivel_verificacao")
        params["nivel_verificacao"] = nivel_verificacao
    if rule_type:
        query_parts.append("AND rule_type = :rule_type")
        params["rule_type"] = rule_type
    if dimension_r18 is not None:
        query_parts.append("AND dimension_r18 = :dimension_r18")
        params["dimension_r18"] = dimension_r18
    if severity:
        query_parts.append("AND severity = :severity")
        params["severity"] = severity
    if search:
        query_parts.append("AND (LOWER(name) LIKE CONCAT('%%', LOWER(:search), '%%') "
                           "OR LOWER(description) LIKE CONCAT('%%', LOWER(:search), '%%'))")
        params["search"] = search
    query_parts.append("ORDER BY created_at DESC LIMIT :page_size OFFSET :offset")
    params["page_size"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = await execute_query(" ".join(query_parts), params)
    rules = [
        RERule(
            rule_id=r["rule_id"], name=r["name"], description=r.get("description"),
            nivel_verificacao=r["nivel_verificacao"], dimension_r18=r.get("dimension_r18"), severity=r["severity"],
            rule_type=r["rule_type"], authoring_mode=r.get("authoring_mode"),
            structured_definition=r.get("structured_definition"),
            expression=r.get("expression"), parameters=r.get("parameters"),
            tags=r.get("tags"), is_seeded=r.get("is_seeded", False),
            source_critica_id=r.get("source_critica_id"),
            created_by=r["created_by"], created_at=str(r["created_at"]), updated_at=str(r["updated_at"]),
        )
        for r in rows
    ]
    return RERuleListResponse(total=len(rules), rules=rules)


@router.post("/", response_model=RERule, status_code=201)
async def create_rule(req: RERuleCreate):
    """Create a new rule."""
    if USE_MOCK:
        now = datetime.now(timezone.utc).isoformat()
        rule = RERule(
            rule_id=f"re_{uuid.uuid4().hex[:6]}",
            name=req.name,
            description=req.description,
            nivel_verificacao=req.nivel_verificacao,
            dimension_r18=req.dimension_r18,
            severity=req.severity,
            rule_type=req.rule_type,
            authoring_mode=req.authoring_mode,
            structured_definition=req.structured_definition.model_dump() if req.structured_definition else None,
            expression=req.expression,
            parameters=req.parameters,
            tags=req.tags,
            is_seeded=False,
            created_by="analyst@bankcorp.com",
            created_at=now,
            updated_at=now,
        )
        _MOCK_RULES.append(rule)
        return rule

    now = datetime.now(timezone.utc).isoformat()
    rule_id = f"re_{uuid.uuid4().hex[:6]}"
    await execute_query(
        f"INSERT INTO {fq(SCHEMA_QUALITY, 're_rules')} "
        f"(rule_id, name, description, nivel_verificacao, dimension_r18, severity, rule_type, "
        f"authoring_mode, structured_definition, expression, parameters, tags, is_seeded, "
        f"created_by, created_at, updated_at, is_active) "
        f"VALUES (:rule_id, :name, :description, :nivel_verificacao, :dimension_r18, :severity, :rule_type, "
        f":authoring_mode, :structured_definition, :expression, :parameters, :tags, FALSE, "
        f":created_by, :created_at, :updated_at, TRUE)",
        {
            "rule_id": rule_id, "name": req.name, "description": req.description,
            "nivel_verificacao": req.nivel_verificacao, "dimension_r18": req.dimension_r18,
            "severity": req.severity, "rule_type": req.rule_type, "authoring_mode": req.authoring_mode,
            "structured_definition": req.structured_definition,
            "expression": req.expression, "parameters": req.parameters, "tags": req.tags,
            "created_by": "analyst@bankcorp.com", "created_at": now, "updated_at": now,
        },
    )
    return RERule(
        rule_id=rule_id, name=req.name, description=req.description,
        nivel_verificacao=req.nivel_verificacao, dimension_r18=req.dimension_r18, severity=req.severity,
        rule_type=req.rule_type, authoring_mode=req.authoring_mode,
        structured_definition=req.structured_definition,
        expression=req.expression, parameters=req.parameters, tags=req.tags,
        is_seeded=False, created_by="analyst@bankcorp.com", created_at=now, updated_at=now,
    )


@router.get("/runs", response_model=RERunListResponse)
async def list_runs(
    dataset_id: str | None = Query(None, description="Filter by dataset ID"),
    status: str | None = Query(None, description="Filter by status (pending, running, completed, failed)"),
):
    """List all rule-engine runs."""
    if USE_MOCK:
        items = list(_MOCK_RUNS)
        if dataset_id:
            items = [r for r in items if r.dataset_id == dataset_id]
        if status:
            items = [r for r in items if r.status == status]
        return RERunListResponse(total=len(items), runs=items)

    query_parts = [
        f"SELECT run_id, dataset_id, status, triggered_by, triggered_at, "
        f"started_at, completed_at, duration_seconds, error_message "
        f"FROM {fq(SCHEMA_QUALITY, 're_runs')} WHERE 1=1",
    ]
    params: dict = {}
    if dataset_id:
        query_parts.append("AND dataset_id = :dataset_id")
        params["dataset_id"] = dataset_id
    if status:
        query_parts.append("AND status = :status")
        params["status"] = status
    query_parts.append("ORDER BY triggered_at DESC")
    rows = await execute_query(" ".join(query_parts), params)
    runs = [
        RERunStatus(
            run_id=r["run_id"], dataset_id=r["dataset_id"], dataset_name="",
            status=r["status"], triggered_by=r["triggered_by"],
            triggered_at=str(r["triggered_at"]),
            completed_at=str(r["completed_at"]) if r.get("completed_at") else None,
        )
        for r in rows
    ]
    return RERunListResponse(total=len(runs), runs=runs)


@router.get("/{rule_id}", response_model=RERule)
async def get_rule(rule_id: str):
    """Get a single rule by ID."""
    if USE_MOCK:
        rule = _find_rule(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        return rule

    rows = await execute_query(
        f"SELECT rule_id, name, description, nivel_verificacao, dimension_r18, severity, rule_type, "
        f"authoring_mode, structured_definition, expression, parameters, tags, is_seeded, source_critica_id, "
        f"created_by, created_at, updated_at, is_active "
        f"FROM {fq(SCHEMA_QUALITY, 're_rules')} WHERE rule_id = :rule_id AND is_active = TRUE",
        {"rule_id": rule_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    r = rows[0]
    return RERule(
        rule_id=r["rule_id"], name=r["name"], description=r.get("description"),
        nivel_verificacao=r["nivel_verificacao"], dimension_r18=r.get("dimension_r18"), severity=r["severity"],
        rule_type=r["rule_type"], authoring_mode=r.get("authoring_mode"),
        structured_definition=r.get("structured_definition"),
        expression=r.get("expression"), parameters=r.get("parameters"),
        tags=r.get("tags"), is_seeded=r.get("is_seeded", False),
        source_critica_id=r.get("source_critica_id"),
        created_by=r["created_by"], created_at=str(r["created_at"]), updated_at=str(r["updated_at"]),
    )


@router.put("/{rule_id}", response_model=RERule)
async def update_rule(rule_id: str, req: RERuleCreate):
    """Update an existing rule."""
    if USE_MOCK:
        rule = _find_rule(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        now = datetime.now(timezone.utc).isoformat()
        updated = RERule(
            rule_id=rule.rule_id,
            name=req.name,
            description=req.description,
            nivel_verificacao=req.nivel_verificacao,
            dimension_r18=req.dimension_r18,
            severity=req.severity,
            rule_type=req.rule_type,
            authoring_mode=req.authoring_mode,
            structured_definition=req.structured_definition.model_dump() if req.structured_definition else rule.structured_definition,
            expression=req.expression if req.expression is not None else rule.expression,
            parameters=req.parameters if req.parameters is not None else rule.parameters,
            tags=req.tags if req.tags is not None else rule.tags,
            is_seeded=rule.is_seeded,
            source_critica_id=rule.source_critica_id,
            created_by=rule.created_by,
            created_at=rule.created_at,
            updated_at=now,
        )
        return updated

    now = datetime.now(timezone.utc).isoformat()
    rows = await execute_query(
        f"SELECT rule_id FROM {fq(SCHEMA_QUALITY, 're_rules')} WHERE rule_id = :rule_id AND is_active = TRUE",
        {"rule_id": rule_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    await execute_query(
        f"UPDATE {fq(SCHEMA_QUALITY, 're_rules')} SET "
        f"name = :name, description = :description, nivel_verificacao = :nivel_verificacao, "
        f"dimension_r18 = :dimension_r18, severity = :severity, rule_type = :rule_type, "
        f"authoring_mode = :authoring_mode, "
        f"structured_definition = :structured_definition, expression = :expression, "
        f"parameters = :parameters, tags = :tags, updated_at = :updated_at "
        f"WHERE rule_id = :rule_id",
        {
            "rule_id": rule_id, "name": req.name, "description": req.description,
            "nivel_verificacao": req.nivel_verificacao, "dimension_r18": req.dimension_r18,
            "severity": req.severity, "rule_type": req.rule_type, "authoring_mode": req.authoring_mode,
            "structured_definition": req.structured_definition,
            "expression": req.expression, "parameters": req.parameters, "tags": req.tags,
            "updated_at": now,
        },
    )
    return RERule(
        rule_id=rule_id, name=req.name, description=req.description,
        nivel_verificacao=req.nivel_verificacao, dimension_r18=req.dimension_r18, severity=req.severity,
        rule_type=req.rule_type, authoring_mode=req.authoring_mode,
        structured_definition=req.structured_definition,
        expression=req.expression, parameters=req.parameters, tags=req.tags,
        is_seeded=False, created_by="analyst@bankcorp.com", created_at="", updated_at=now,
    )


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    """Soft-delete a rule."""
    if USE_MOCK:
        rule = _find_rule(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
        return {"ok": True}

    rows = await execute_query(
        f"SELECT rule_id FROM {fq(SCHEMA_QUALITY, 're_rules')} WHERE rule_id = :rule_id AND is_active = TRUE",
        {"rule_id": rule_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    await execute_query(
        f"UPDATE {fq(SCHEMA_QUALITY, 're_rules')} SET is_active = FALSE WHERE rule_id = :rule_id",
        {"rule_id": rule_id},
    )
    return {"ok": True}


@router.post("/validate-expression", response_model=REExpressionValidation)
async def validate_expression(req: dict):
    """Validate a rule expression (basic syntax check)."""
    if USE_MOCK:
        expr = req.get("expression", "")
        if not expr.strip():
            return REExpressionValidation(expression=expr, is_valid=False, error_message="Expression is empty")
        return REExpressionValidation(expression=expr, is_valid=True, resolved_expression=expr)

    expr = req.get("expression", "")
    if not expr.strip():
        return REExpressionValidation(expression=expr, is_valid=False, error_message="Expression is empty")
    # In real mode we could parse/compile the expression against the SQL engine
    return REExpressionValidation(expression=expr, is_valid=True, resolved_expression=expr)


# ===================================================================
# Endpoints: Bindings
# ===================================================================


@router.get("/datasets/{dataset_id}/bindings", response_model=REBindingListResponse)
async def list_bindings(dataset_id: str):
    """List rule bindings for a dataset, enriched with rule_name."""
    if USE_MOCK:
        ds = _find_dataset(dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        items = [b for b in _MOCK_BINDINGS if b.dataset_id == dataset_id]
        # Enrich rule_name from _MOCK_RULES
        enriched = []
        for b in items:
            rule = _find_rule(b.rule_id)
            enriched.append(REBinding(
                binding_id=b.binding_id,
                rule_id=b.rule_id,
                dataset_id=b.dataset_id,
                rule_name=rule.name if rule else b.rule_name,
                column_bindings=b.column_bindings,
                override_name=b.override_name,
                override_severity=b.override_severity,
                is_active=b.is_active,
                created_by=b.created_by,
                created_at=b.created_at,
            ))
        return REBindingListResponse(total=len(enriched), bindings=enriched)

    rows = await execute_query(
        f"SELECT b.binding_id, b.rule_id, b.dataset_id, r.name as rule_name, "
        f"b.column_bindings, b.override_name, b.override_severity, b.is_active, "
        f"b.created_by, b.created_at "
        f"FROM {fq(SCHEMA_QUALITY, 're_bindings')} b "
        f"JOIN {fq(SCHEMA_QUALITY, 're_rules')} r ON b.rule_id = r.rule_id "
        f"WHERE b.dataset_id = :dataset_id AND b.is_active = TRUE "
        f"ORDER BY b.created_at",
        {"dataset_id": dataset_id},
    )
    bindings = [
        REBinding(
            binding_id=r["binding_id"], rule_id=r["rule_id"], dataset_id=r["dataset_id"],
            rule_name=r["rule_name"], column_bindings=r["column_bindings"],
            override_name=r.get("override_name"), override_severity=r.get("override_severity"),
            is_active=r["is_active"], created_by=r["created_by"], created_at=str(r["created_at"]),
        )
        for r in rows
    ]
    return REBindingListResponse(total=len(bindings), bindings=bindings)


@router.post("/datasets/{dataset_id}/bindings", response_model=REBinding, status_code=201)
async def create_binding(dataset_id: str, req: REBindingCreate):
    """Create a binding between a rule and a dataset with column mappings."""
    if USE_MOCK:
        ds = _find_dataset(dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        rule = _find_rule(req.rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule {req.rule_id} not found")
        now = datetime.now(timezone.utc).isoformat()
        binding = REBinding(
            binding_id=f"bind_{uuid.uuid4().hex[:6]}",
            rule_id=req.rule_id,
            dataset_id=dataset_id,
            rule_name=rule.name,
            column_bindings=req.column_bindings,
            override_name=req.override_name,
            override_severity=req.override_severity,
            is_active=True,
            created_by="analyst@bankcorp.com",
            created_at=now,
        )
        _MOCK_BINDINGS.append(binding)
        return binding

    ds_rows = await execute_query(
        f"SELECT dataset_id FROM {fq(SCHEMA_QUALITY, 're_datasets')} "
        f"WHERE dataset_id = :dataset_id AND is_active = TRUE",
        {"dataset_id": dataset_id},
    )
    if not ds_rows:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    rule_rows = await execute_query(
        f"SELECT rule_id, name FROM {fq(SCHEMA_QUALITY, 're_rules')} "
        f"WHERE rule_id = :rule_id AND is_active = TRUE",
        {"rule_id": req.rule_id},
    )
    if not rule_rows:
        raise HTTPException(status_code=404, detail=f"Rule {req.rule_id} not found")
    now = datetime.now(timezone.utc).isoformat()
    binding_id = f"bind_{uuid.uuid4().hex[:6]}"
    await execute_query(
        f"INSERT INTO {fq(SCHEMA_QUALITY, 're_bindings')} "
        f"(binding_id, rule_id, dataset_id, column_bindings, override_name, override_severity, "
        f"is_active, created_by, created_at) "
        f"VALUES (:binding_id, :rule_id, :dataset_id, :column_bindings, :override_name, "
        f":override_severity, TRUE, :created_by, :created_at)",
        {
            "binding_id": binding_id, "rule_id": req.rule_id, "dataset_id": dataset_id,
            "column_bindings": req.column_bindings, "override_name": req.override_name,
            "override_severity": req.override_severity,
            "created_by": "analyst@bankcorp.com", "created_at": now,
        },
    )
    return REBinding(
        binding_id=binding_id, rule_id=req.rule_id, dataset_id=dataset_id,
        rule_name=rule_rows[0]["name"], column_bindings=req.column_bindings,
        override_name=req.override_name, override_severity=req.override_severity,
        is_active=True, created_by="analyst@bankcorp.com", created_at=now,
    )


@router.delete("/datasets/{dataset_id}/bindings/{binding_id}")
async def delete_binding(dataset_id: str, binding_id: str):
    """Remove a binding."""
    if USE_MOCK:
        binding = next(
            (b for b in _MOCK_BINDINGS if b.binding_id == binding_id and b.dataset_id == dataset_id),
            None,
        )
        if not binding:
            raise HTTPException(status_code=404, detail=f"Binding {binding_id} not found for dataset {dataset_id}")
        return {"ok": True}

    rows = await execute_query(
        f"SELECT binding_id FROM {fq(SCHEMA_QUALITY, 're_bindings')} "
        f"WHERE binding_id = :binding_id AND dataset_id = :dataset_id AND is_active = TRUE",
        {"binding_id": binding_id, "dataset_id": dataset_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Binding {binding_id} not found for dataset {dataset_id}")
    await execute_query(
        f"UPDATE {fq(SCHEMA_QUALITY, 're_bindings')} SET is_active = FALSE "
        f"WHERE binding_id = :binding_id AND dataset_id = :dataset_id",
        {"binding_id": binding_id, "dataset_id": dataset_id},
    )
    return {"ok": True}


# ===================================================================
# Endpoints: Execution (Runs)
# ===================================================================


@router.post("/datasets/{dataset_id}/run", response_model=RETriggerRunResponse, status_code=202)
async def trigger_run(dataset_id: str):
    """Trigger a rule-engine evaluation run for a dataset."""
    if USE_MOCK:
        import random
        ds = _find_dataset(dataset_id)
        if not ds:
            raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
        now = datetime.now(timezone.utc).isoformat()
        ds_bindings = [b for b in _MOCK_BINDINGS if b.dataset_id == dataset_id and b.is_active]
        run_id = f"run_re_{uuid.uuid4().hex[:6]}"
        total_records = ds.row_count_approx or 500000

        # Generate a run status
        run_status = RERunStatus(
            run_id=run_id, dataset_id=dataset_id, dataset_name=ds.name,
            status="completed", total_rules=len(ds_bindings), total_records=total_records,
            triggered_by="analyst@bankcorp.com", triggered_at=now,
            started_at=now, completed_at=now, duration_seconds=random.randint(5, 60),
        )
        _MOCK_RUNS.append(run_status)

        # Generate results and exceptions per binding
        run_results = []
        run_exceptions = []
        for bind in ds_bindings:
            rule = _find_rule(bind.rule_id)
            result_id = f"res_{uuid.uuid4().hex[:6]}"
            # Simulate: ~80% chance pass, 20% fail with a few exceptions
            fails = random.choice([0, 0, 0, 0, random.randint(3, 50)])
            passed = total_records - fails
            status = "pass" if fails == 0 else "fail"
            col_list = list(bind.column_bindings.values())
            result = RERunResult(
                result_id=result_id, binding_id=bind.binding_id,
                rule_id=bind.rule_id, rule_name=f"{rule.name if rule else bind.rule_id} — {', '.join(col_list)}",
                status=status, total_records=total_records,
                passed_records=passed, failed_records=fails,
                pass_rate_pct=round(passed / total_records * 100, 2),
                severity=rule.severity if rule else "error",
                dimension_r18=rule.dimension_r18 if rule else None,
                execution_time_ms=random.randint(800, 5000),
                expression_used=" AND ".join(f"{c} check" for c in col_list),
            )
            run_results.append(result)

            # Generate exception rows for failures
            for j in range(min(fails, 5)):
                exc = REException(
                    exception_id=f"exc_{uuid.uuid4().hex[:6]}",
                    result_id=result_id, binding_id=bind.binding_id,
                    rule_name=result.rule_name,
                    row_identifier={"_pk_hash": f"hash_{uuid.uuid4().hex[:8]}", "contrt": f"OP-2026-{random.randint(10000,99999)}"},
                    failed_columns=col_list,
                    row_snapshot={c: None if random.random() > 0.5 else f"val_{j}" for c in col_list},
                    failure_reason=f"Violacao na coluna {col_list[0]}" if col_list else "Regra violada",
                )
                run_exceptions.append(exc)

        _MOCK_RUN_RESULTS[run_id] = run_results
        _MOCK_EXCEPTIONS[run_id] = run_exceptions

        return RETriggerRunResponse(
            run_id=run_id,
            status="completed",
            dataset_id=dataset_id,
            total_bindings=len(ds_bindings),
            triggered_by="analyst@bankcorp.com",
            triggered_at=now,
        )

    ds_rows = await execute_query(
        f"SELECT dataset_id FROM {fq(SCHEMA_QUALITY, 're_datasets')} "
        f"WHERE dataset_id = :dataset_id AND is_active = TRUE",
        {"dataset_id": dataset_id},
    )
    if not ds_rows:
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")
    now = datetime.now(timezone.utc).isoformat()
    run_id = f"run_re_{uuid.uuid4().hex[:6]}"
    await execute_query(
        f"INSERT INTO {fq(SCHEMA_QUALITY, 're_runs')} "
        f"(run_id, dataset_id, status, triggered_by, triggered_at) "
        f"VALUES (:run_id, :dataset_id, 'pending', :triggered_by, :triggered_at)",
        {"run_id": run_id, "dataset_id": dataset_id, "triggered_by": "analyst@bankcorp.com", "triggered_at": now},
    )
    return RETriggerRunResponse(
        run_id=run_id, status="pending", dataset_id=dataset_id,
        total_bindings=0, triggered_by="analyst@bankcorp.com", triggered_at=now,
    )


@router.get("/runs/{run_id}", response_model=RERunStatus)
async def get_run_status(run_id: str):
    """Get the status of a rule-engine run."""
    if USE_MOCK:
        run = _find_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return run

    rows = await execute_query(
        f"SELECT run_id, dataset_id, status, triggered_by, triggered_at, "
        f"started_at, completed_at, duration_seconds, error_message "
        f"FROM {fq(SCHEMA_QUALITY, 're_runs')} WHERE run_id = :run_id",
        {"run_id": run_id},
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    r = rows[0]
    return RERunStatus(
        run_id=r["run_id"], dataset_id=r["dataset_id"], dataset_name="",
        status=r["status"], triggered_by=r["triggered_by"],
        triggered_at=str(r["triggered_at"]),
        completed_at=str(r["completed_at"]) if r.get("completed_at") else None,
    )


@router.get("/runs/{run_id}/results", response_model=RERunResultsResponse)
async def get_run_results(run_id: str):
    """Return results with summary for a completed run."""
    if USE_MOCK:
        run = _find_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        results = _MOCK_RUN_RESULTS.get(run_id, [])
        passed = sum(1 for r in results if r.status == "pass")
        failed = sum(1 for r in results if r.status == "fail")
        warnings = 0
        total_records = results[0].total_records if results else 0
        total_exceptions = sum(r.failed_records for r in results)
        summary = RERunResultsSummary(
            total_rules=len(results),
            passed=passed,
            failed=failed,
            warnings=warnings,
            pass_rate_pct=round(passed / max(len(results), 1) * 100, 1),
            total_records=total_records,
            total_exceptions=total_exceptions,
        )
        return RERunResultsResponse(
            run_id=run_id,
            dataset_name=run.dataset_name or "",
            status=run.status,
            summary=summary,
            results=results,
        )

    run_rows = await execute_query(
        f"SELECT run_id, dataset_id, status FROM {fq(SCHEMA_QUALITY, 're_runs')} WHERE run_id = :run_id",
        {"run_id": run_id},
    )
    if not run_rows:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    result_rows = await execute_query(
        f"SELECT result_id, binding_id, rule_id, rule_name, status, "
        f"total_records, passed_records, failed_records, pass_rate_pct, "
        f"severity, dimension_r18, execution_time_ms, expression_used "
        f"FROM {fq(SCHEMA_QUALITY, 're_run_results')} WHERE run_id = :run_id ORDER BY result_id",
        {"run_id": run_id},
    )
    results = [
        RERunResult(
            result_id=r["result_id"], binding_id=r["binding_id"], rule_id=r["rule_id"],
            rule_name=r["rule_name"], status=r["status"],
            total_records=r["total_records"], passed_records=r["passed_records"],
            failed_records=r["failed_records"], pass_rate_pct=r["pass_rate_pct"],
            severity=r["severity"], dimension_r18=r.get("dimension_r18"),
            execution_time_ms=r.get("execution_time_ms"), expression_used=r.get("expression_used"),
        )
        for r in result_rows
    ]
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    total_records = results[0].total_records if results else 0
    total_exceptions = sum(r.failed_records for r in results)
    summary = RERunResultsSummary(
        total_rules=len(results), passed=passed, failed=failed, warnings=0,
        pass_rate_pct=round(passed / max(len(results), 1) * 100, 1),
        total_records=total_records, total_exceptions=total_exceptions,
    )
    return RERunResultsResponse(
        run_id=run_id, dataset_name="", status=run_rows[0]["status"],
        summary=summary, results=results,
    )


@router.get("/runs/{run_id}/exceptions", response_model=REExceptionsResponse)
async def get_run_exceptions(
    run_id: str,
    result_id: str | None = Query(None, description="Filter exceptions by result_id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Return paginated exceptions for a run, optionally filtered by result_id."""
    if USE_MOCK:
        run = _find_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        exceptions = _MOCK_EXCEPTIONS.get(run_id, [])
        if result_id:
            exceptions = [e for e in exceptions if e.result_id == result_id]
        total = len(exceptions)
        start = (page - 1) * page_size
        paged = exceptions[start : start + page_size]
        return REExceptionsResponse(
            run_id=run_id,
            result_id=result_id,
            exceptions=paged,
            total=total,
            pagination=Pagination(
                page=page, page_size=page_size,
                total_results=total, total_pages=max(1, (total + page_size - 1) // page_size),
            ),
        )

    query_parts = [
        f"SELECT exception_id, result_id, binding_id, rule_name, "
        f"row_identifier, failed_columns, row_snapshot, failure_reason "
        f"FROM {fq(SCHEMA_QUALITY, 're_exceptions')} WHERE run_id = :run_id",
    ]
    params: dict = {"run_id": run_id}
    if result_id:
        query_parts.append("AND result_id = :result_id")
        params["result_id"] = result_id
    query_parts.append("ORDER BY exception_id LIMIT :page_size OFFSET :offset")
    params["page_size"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = await execute_query(" ".join(query_parts), params)
    exceptions = [
        REException(
            exception_id=r["exception_id"], result_id=r["result_id"], binding_id=r["binding_id"],
            rule_name=r["rule_name"], row_identifier=r["row_identifier"],
            failed_columns=r.get("failed_columns"), row_snapshot=r.get("row_snapshot"),
            failure_reason=r.get("failure_reason"),
        )
        for r in rows
    ]
    return REExceptionsResponse(
        run_id=run_id, result_id=result_id, exceptions=exceptions,
        total=len(exceptions),
        pagination=Pagination(page=page, page_size=page_size, total_results=len(exceptions), total_pages=1),
    )


# ===================================================================
# Endpoints: Seed
# ===================================================================


@router.post("/seed", response_model=RESeedResponse)
async def seed_rules():
    """Seed the rule engine with BCB critica rules and default bindings."""
    if USE_MOCK:
        seeded = [r for r in _MOCK_RULES if r.is_seeded]
        seeded_bindings = [
            b for b in _MOCK_BINDINGS
            if any(b.rule_id == r.rule_id for r in seeded)
        ]
        return RESeedResponse(
            rules_created=len(seeded),
            bindings_created=len(seeded_bindings),
            rule_ids=[r.rule_id for r in seeded],
        )

    # In real mode, insert seeded rules from validation_rules
    from db import SCHEMA_REFERENCE
    rows = await execute_query(
        f"SELECT critica_id, descricao, grupo, severidade, dimensao_r18, expressao_sql "
        f"FROM {CATALOG}.{SCHEMA_REFERENCE}.validation_rules WHERE is_active = TRUE",
    )
    created = 0
    rule_ids = []
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        rule_id = f"re_{r['critica_id'].lower()}"
        await execute_query(
            f"INSERT INTO {fq(SCHEMA_QUALITY, 're_rules')} "
            f"(rule_id, name, description, nivel_verificacao, dimension_r18, severity, rule_type, "
            f"authoring_mode, expression, is_seeded, source_critica_id, created_by, created_at, updated_at, is_active) "
            f"VALUES (:rule_id, :name, :description, :nivel_verificacao, :dimension_r18, :severity, :rule_type, "
            f"'expression', :expression, TRUE, :source_critica_id, 'system', :created_at, :updated_at, TRUE)",
            {
                "rule_id": rule_id, "name": r["descricao"], "description": r["descricao"],
                "nivel_verificacao": r.get("nivel_verificacao", 1), "dimension_r18": r.get("dimensao_r18", 6),
                "severity": r["severidade"], "rule_type": r.get("tipo_regra", "syntactic"),
                "expression": r.get("expressao_sql", ""),
                "source_critica_id": r["critica_id"], "created_at": now, "updated_at": now,
            },
        )
        rule_ids.append(rule_id)
        created += 1
    return RESeedResponse(rules_created=created, bindings_created=0, rule_ids=rule_ids)
