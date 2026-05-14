"""Seed Lakebase with schema and demo data for Sentinel DQ - RC 18 Compliance."""

import json
import logging
import random
from datetime import datetime, timedelta, date

from backend.db import get_conn, query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS dq_rc18;
SET search_path TO dq_rc18, public;

CREATE TABLE IF NOT EXISTS dq_data_domains (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  description TEXT,
  owner_email VARCHAR(200),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dq_quality_rules (
  id SERIAL PRIMARY KEY,
  domain_id INT REFERENCES dq_data_domains(id),
  name VARCHAR(200) NOT NULL,
  description TEXT,
  rule_type VARCHAR(50) NOT NULL,
  target_table VARCHAR(500) NOT NULL,
  target_column VARCHAR(200),
  parameters JSONB DEFAULT '{}',
  threshold DECIMAL(5,2) DEFAULT 95.00,
  severity VARCHAR(20) DEFAULT 'error',
  owner_email VARCHAR(200),
  status VARCHAR(20) DEFAULT 'approved',
  version INT DEFAULT 1,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dq_quality_executions (
  id SERIAL PRIMARY KEY,
  rule_id INT REFERENCES dq_quality_rules(id),
  domain_id INT REFERENCES dq_data_domains(id),
  executed_at TIMESTAMP DEFAULT NOW(),
  total_records INT DEFAULT 0,
  passed_records INT DEFAULT 0,
  failed_records INT DEFAULT 0,
  score DECIMAL(5,2),
  status VARCHAR(50),
  execution_details JSONB DEFAULT '{}',
  duration_seconds DECIMAL(8,2) DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dq_quality_results (
  id SERIAL PRIMARY KEY,
  domain_id INT REFERENCES dq_data_domains(id),
  kpi_type VARCHAR(50) NOT NULL,
  score DECIMAL(5,2) NOT NULL,
  result_date DATE NOT NULL,
  rules_evaluated INT DEFAULT 0,
  rules_passed INT DEFAULT 0,
  rules_failed INT DEFAULT 0,
  details JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dq_quality_incidents (
  id SERIAL PRIMARY KEY,
  domain_id INT REFERENCES dq_data_domains(id),
  rule_id INT REFERENCES dq_quality_rules(id),
  title VARCHAR(300) NOT NULL,
  description TEXT,
  severity VARCHAR(20) NOT NULL,
  status VARCHAR(30) DEFAULT 'open',
  assigned_to VARCHAR(200),
  source_table VARCHAR(500),
  root_cause TEXT,
  resolution TEXT,
  lineage_path JSONB DEFAULT '[]',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  resolved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dq_quality_actions (
  id SERIAL PRIMARY KEY,
  incident_id INT REFERENCES dq_quality_incidents(id) ON DELETE CASCADE,
  action_type VARCHAR(30) NOT NULL,
  description TEXT NOT NULL,
  owner_email VARCHAR(200),
  deadline DATE,
  status VARCHAR(20) DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dq_bdr_conciliation (
  id SERIAL PRIMARY KEY,
  domain_id INT REFERENCES dq_data_domains(id),
  conciliation_date DATE NOT NULL,
  accounting_source VARCHAR(500) NOT NULL,
  regulatory_source VARCHAR(500) NOT NULL,
  metric_name VARCHAR(200) NOT NULL,
  accounting_value DECIMAL(18,2),
  regulatory_value DECIMAL(18,2),
  divergence DECIMAL(18,2),
  divergence_pct DECIMAL(8,4),
  threshold_pct DECIMAL(5,2) DEFAULT 0.01,
  status VARCHAR(30) DEFAULT 'pending',
  resolution_notes TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);
"""


def create_schema():
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
    logger.info("DQ schema created/verified.")


def tables_exist() -> bool:
    """Check if the seed data already exists."""
    try:
        rows = query("SELECT COUNT(*) AS cnt FROM dq_data_domains")
        return rows[0]["cnt"] > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def seed_all():
    """Insert all demo data."""
    now = datetime.utcnow()

    with get_conn() as conn:
        cur = conn.cursor()

        # Clean existing data
        for table in [
            "dq_bdr_conciliation", "dq_quality_actions", "dq_quality_incidents",
            "dq_quality_results", "dq_quality_executions", "dq_quality_rules",
            "dq_data_domains",
        ]:
            cur.execute(f"DELETE FROM {table}")

        # ---- Domains ----
        domains = [
            ("Credito", "Dominio de dados de credito - carteiras, contratos, scores e provisoes", "risco.credito@santander.com.br"),
            ("Risco", "Dominio de dados de risco de mercado e operacional - VaR, stress testing, limites", "risco.mercado@santander.com.br"),
            ("Contabil", "Dominio de dados contabeis - balancetes, razao, conciliacoes COSIF", "contabilidade@santander.com.br"),
            ("Regulatorio", "Dominio de dados regulatorios - BACEN, CVM, SUSEP, reporte obrigatorio", "regulatorio@santander.com.br"),
        ]
        domain_ids = {}
        for name, desc, email in domains:
            cur.execute(
                "INSERT INTO dq_data_domains (name, description, owner_email) VALUES (%s, %s, %s) RETURNING id",
                (name, desc, email),
            )
            domain_ids[name] = cur.fetchone()[0]

        # ---- Quality Rules (16 rules, 4 per domain) ----
        kpi_types = ["completude", "acuracia", "consistencia", "tempestividade", "unicidade", "validade"]

        rules_data = [
            # Credito domain
            (domain_ids["Credito"], "Completude CPF/CNPJ", "CPF ou CNPJ do tomador deve estar preenchido em 100% dos contratos",
             "completude", "santander_credito_app_catalog.credito.contratos", "cpf_cnpj",
             json.dumps({"check": "not_null"}), 99.0, "error", "risco.credito@santander.com.br", "approved"),
            (domain_ids["Credito"], "Acuracia Score de Credito", "Score de credito deve estar entre 0 e 1000 e compativel com bureau",
             "acuracia", "santander_credito_app_catalog.credito.contratos", "score_credito",
             json.dumps({"min": 0, "max": 1000, "cross_ref": "bureau_scores"}), 95.0, "error", "risco.credito@santander.com.br", "approved"),
            (domain_ids["Credito"], "Consistencia Saldo vs Limite", "Saldo utilizado nao pode exceder o limite aprovado",
             "consistencia", "santander_credito_app_catalog.credito.contratos", "saldo_devedor",
             json.dumps({"compare_col": "limite_aprovado", "operator": "<="}), 98.0, "error", "risco.credito@santander.com.br", "approved"),
            (domain_ids["Credito"], "Tempestividade Atualizacao", "Contratos devem ser atualizados no maximo em D+1",
             "tempestividade", "santander_credito_app_catalog.credito.contratos", "data_atualizacao",
             json.dumps({"max_delay_hours": 24}), 97.0, "warning", "risco.credito@santander.com.br", "approved"),

            # Risco domain
            (domain_ids["Risco"], "Completude Exposicao", "Exposicao ao risco deve estar preenchida para todos os ativos",
             "completude", "santander_credito_app_catalog.risco.exposicoes", "valor_exposicao",
             json.dumps({"check": "not_null"}), 99.5, "error", "risco.mercado@santander.com.br", "approved"),
            (domain_ids["Risco"], "Unicidade ID Operacao", "Cada operacao deve ter um identificador unico no sistema de risco",
             "unicidade", "santander_credito_app_catalog.risco.exposicoes", "id_operacao",
             json.dumps({"check": "unique"}), 100.0, "error", "risco.mercado@santander.com.br", "approved"),
            (domain_ids["Risco"], "Validade Rating Interno", "Rating interno deve seguir a escala aprovada (AAA a D)",
             "validade", "santander_credito_app_catalog.risco.exposicoes", "rating_interno",
             json.dumps({"valid_values": ["AAA", "AA", "A", "BBB", "BB", "B", "CCC", "CC", "C", "D"]}), 98.0, "error", "risco.mercado@santander.com.br", "approved"),
            (domain_ids["Risco"], "Consistencia VaR vs Limite", "VaR calculado nao deve exceder o limite regulatorio aprovado",
             "consistencia", "santander_credito_app_catalog.risco.var_diario", "var_99",
             json.dumps({"compare_col": "limite_var", "operator": "<="}), 99.0, "error", "risco.mercado@santander.com.br", "approved"),

            # Contabil domain
            (domain_ids["Contabil"], "Completude Conta COSIF", "Codigo COSIF deve estar preenchido em todos os lancamentos",
             "completude", "santander_credito_app_catalog.contabil.balancete", "conta_cosif",
             json.dumps({"check": "not_null"}), 100.0, "error", "contabilidade@santander.com.br", "approved"),
            (domain_ids["Contabil"], "Acuracia Saldo Contabil", "Saldos contabeis devem bater com o razao analitico",
             "acuracia", "santander_credito_app_catalog.contabil.balancete", "saldo_final",
             json.dumps({"cross_ref": "razao_analitico", "tolerance": 0.01}), 99.9, "error", "contabilidade@santander.com.br", "approved"),
            (domain_ids["Contabil"], "Consistencia Debito-Credito", "Total de debitos deve igualar total de creditos por periodo",
             "consistencia", "santander_credito_app_catalog.contabil.balancete", "saldo_final",
             json.dumps({"balance_check": True}), 100.0, "error", "contabilidade@santander.com.br", "approved"),
            (domain_ids["Contabil"], "Tempestividade Fechamento", "Fechamento contabil deve ocorrer ate D+2 do periodo",
             "tempestividade", "santander_credito_app_catalog.contabil.balancete", "data_fechamento",
             json.dumps({"max_delay_hours": 48}), 95.0, "warning", "contabilidade@santander.com.br", "approved"),

            # Regulatorio domain
            (domain_ids["Regulatorio"], "Completude Campos BACEN", "Todos os campos obrigatorios do reporte 3040 devem estar preenchidos",
             "completude", "santander_credito_app_catalog.regulatorio.reporte_3040", None,
             json.dumps({"mandatory_fields": ["cnpj", "modalidade", "valor", "data_ref"]}), 100.0, "error", "regulatorio@santander.com.br", "approved"),
            (domain_ids["Regulatorio"], "Validade Formato CNPJ", "CNPJ deve ter formato valido com digito verificador correto",
             "validade", "santander_credito_app_catalog.regulatorio.reporte_3040", "cnpj",
             json.dumps({"format": "cnpj", "validate_check_digit": True}), 100.0, "error", "regulatorio@santander.com.br", "approved"),
            (domain_ids["Regulatorio"], "Unicidade Reporte", "Nao deve haver duplicatas no envio regulatorio por periodo",
             "unicidade", "santander_credito_app_catalog.regulatorio.reporte_3040", "id_reporte",
             json.dumps({"check": "unique", "partition_by": "data_referencia"}), 100.0, "error", "regulatorio@santander.com.br", "approved"),
            (domain_ids["Regulatorio"], "Tempestividade Envio BACEN", "Reporte deve ser enviado dentro do prazo regulatorio",
             "tempestividade", "santander_credito_app_catalog.regulatorio.reporte_3040", "data_envio",
             json.dumps({"deadline_business_days": 5}), 100.0, "error", "regulatorio@santander.com.br", "approved"),
        ]

        rule_ids = []
        for r in rules_data:
            cur.execute(
                """INSERT INTO dq_quality_rules
                   (domain_id, name, description, rule_type, target_table, target_column,
                    parameters, threshold, severity, owner_email, status)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                r,
            )
            rule_ids.append(cur.fetchone()[0])

        # ---- Quality Results (90 days, 6 KPI types x 4 domains) ----
        # Define score profiles per domain/kpi (tells a story)
        # Credito: generally good but tempestividade declining
        # Risco: excellent across the board
        # Contabil: acuracia issues recently (critical incident)
        # Regulatorio: completude drop last 2 weeks

        def gen_score(base, volatility, trend=0.0, day_idx=0):
            s = base + random.uniform(-volatility, volatility) + (trend * day_idx)
            return round(max(50, min(100, s)), 2)

        profiles = {
            # (domain, kpi): (base_score, volatility, daily_trend)
            ("Credito", "completude"): (97.5, 1.0, 0.0),
            ("Credito", "acuracia"): (96.0, 1.5, 0.0),
            ("Credito", "consistencia"): (94.5, 2.0, 0.0),
            ("Credito", "tempestividade"): (96.0, 1.5, -0.08),  # declining
            ("Credito", "unicidade"): (99.5, 0.3, 0.0),
            ("Credito", "validade"): (97.0, 1.0, 0.0),

            ("Risco", "completude"): (99.0, 0.5, 0.0),
            ("Risco", "acuracia"): (98.5, 0.8, 0.0),
            ("Risco", "consistencia"): (98.0, 1.0, 0.0),
            ("Risco", "tempestividade"): (97.5, 1.0, 0.0),
            ("Risco", "unicidade"): (99.8, 0.2, 0.0),
            ("Risco", "validade"): (98.0, 1.0, 0.0),

            ("Contabil", "completude"): (99.5, 0.3, 0.0),
            ("Contabil", "acuracia"): (97.0, 1.0, -0.12),  # declining - incident
            ("Contabil", "consistencia"): (95.0, 2.0, -0.05),
            ("Contabil", "tempestividade"): (93.0, 2.5, 0.0),
            ("Contabil", "unicidade"): (99.9, 0.1, 0.0),
            ("Contabil", "validade"): (98.5, 0.8, 0.0),

            ("Regulatorio", "completude"): (98.0, 1.0, -0.10),  # declining
            ("Regulatorio", "acuracia"): (97.5, 1.0, 0.0),
            ("Regulatorio", "consistencia"): (96.0, 1.5, 0.0),
            ("Regulatorio", "tempestividade"): (88.0, 3.0, 0.0),  # chronically low
            ("Regulatorio", "unicidade"): (99.5, 0.3, 0.0),
            ("Regulatorio", "validade"): (96.5, 1.5, 0.0),
        }

        for day_offset in range(90):
            result_date = (now - timedelta(days=89 - day_offset)).date()
            for domain_name, did in domain_ids.items():
                for kpi in kpi_types:
                    base, vol, trend = profiles[(domain_name, kpi)]
                    score = gen_score(base, vol, trend, day_offset)
                    rules_eval = random.randint(3, 6)
                    rules_pass = rules_eval if score >= 95 else rules_eval - random.randint(1, min(2, rules_eval))
                    rules_fail = rules_eval - rules_pass

                    cur.execute(
                        """INSERT INTO dq_quality_results
                           (domain_id, kpi_type, score, result_date, rules_evaluated, rules_passed, rules_failed, details)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (did, kpi, score, result_date, rules_eval, rules_pass, rules_fail,
                         json.dumps({"domain": domain_name, "generated": True})),
                    )

        # ---- Quality Executions (~220 across rules) ----
        for rule_idx, rid in enumerate(rule_ids):
            domain_id = rules_data[rule_idx][0]
            domain_name = [k for k, v in domain_ids.items() if v == domain_id][0]
            rule_type = rules_data[rule_idx][3]

            # Each rule gets ~14 executions over 90 days
            for exec_idx in range(14):
                days_ago = random.randint(0, 89)
                exec_time = now - timedelta(days=days_ago, hours=random.randint(0, 12))
                total = random.randint(10000, 500000)

                base, vol, trend = profiles[(domain_name, rule_type)]
                score = gen_score(base, vol, trend, 90 - days_ago)
                passed = int(total * score / 100)
                failed = total - passed
                duration = round(random.uniform(2.0, 45.0), 2)

                if score >= 95:
                    status = "passed"
                elif score >= 85:
                    status = "warning"
                else:
                    status = "failed"

                cur.execute(
                    """INSERT INTO dq_quality_executions
                       (rule_id, domain_id, executed_at, total_records, passed_records, failed_records,
                        score, status, execution_details, duration_seconds)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (rid, domain_id, exec_time, total, passed, failed, score, status,
                     json.dumps({"rule_name": rules_data[rule_idx][1], "domain": domain_name}), duration),
                )

        # ---- Quality Incidents (8 incidents) ----
        incidents_data = [
            # 2 CRITICAL open
            (domain_ids["Contabil"], rule_ids[9],
             "Divergencia critica no saldo contabil - Provisao PDD",
             "Detectada diferenca de R$ 2.3M entre o saldo contabil de provisao PDD e o razao analitico. "
             "Impacta diretamente o reporte DLO ao BACEN. Divergencia identificada no fechamento de marco/2026.",
             "critical", "open", "carlos.mendes@santander.com.br",
             "santander_credito_app_catalog.contabil.balancete",
             None, None,
             json.dumps(["contabil.balancete", "contabil.razao_analitico", "credito.provisao_pdd"]),
             now - timedelta(days=2), now - timedelta(days=2), None),

            (domain_ids["Regulatorio"], rule_ids[12],
             "Reporte 3040 com dados duplicados - Envio BACEN",
             "Identificados 847 registros duplicados no reporte 3040 referente a mar/2026. "
             "Reporte ja foi enviado ao BACEN com as duplicatas. Necessaria retificacao urgente.",
             "critical", "open", None,
             "santander_credito_app_catalog.regulatorio.reporte_3040",
             None, None,
             json.dumps(["regulatorio.reporte_3040", "credito.contratos"]),
             now - timedelta(hours=8), now - timedelta(hours=8), None),

            # 2 investigating
            (domain_ids["Credito"], rule_ids[3],
             "Atraso sistematico na atualizacao de contratos CDC",
             "Contratos de CDC estao sendo atualizados com atraso medio de 36h, excedendo o SLA de D+1. "
             "Afeta 12.000 contratos diariamente. Possivel problema no pipeline de ingestao.",
             "high", "investigating", "ana.ferreira@santander.com.br",
             "santander_credito_app_catalog.credito.contratos",
             "Pipeline de ingestao CDC com gargalo no step de transformacao",
             None,
             json.dumps(["credito.contratos_raw", "credito.contratos"]),
             now - timedelta(days=5), now - timedelta(days=3), None),

            (domain_ids["Contabil"], rule_ids[10],
             "Desbalanceamento debito-credito no plano de contas",
             "Inconsistencia de R$ 450K no balanceamento debito-credito identificada "
             "em 3 contas COSIF do grupo 1.6 (Operacoes de Credito).",
             "high", "investigating", "patricia.lima@santander.com.br",
             "santander_credito_app_catalog.contabil.balancete",
             None, None,
             json.dumps(["contabil.balancete", "contabil.lancamentos"]),
             now - timedelta(days=7), now - timedelta(days=5), None),

            # 2 assigned
            (domain_ids["Risco"], rule_ids[7],
             "VaR excedendo limite em mesa de derivativos",
             "VaR de 99% da mesa de derivativos excedeu o limite aprovado em 3 dos ultimos 5 dias. "
             "Desvio maximo de 8% acima do limite.",
             "medium", "assigned", "ricardo.santos@santander.com.br",
             "santander_credito_app_catalog.risco.var_diario",
             "Posicoes abertas em opcoes de dolar nao hedgeadas corretamente",
             None,
             json.dumps(["risco.var_diario", "risco.exposicoes", "risco.limites"]),
             now - timedelta(days=10), now - timedelta(days=8), None),

            (domain_ids["Regulatorio"], rule_ids[15],
             "Atraso no envio do reporte mensal ao BACEN",
             "Reporte 4060 de fevereiro/2026 enviado com 2 dias de atraso. "
             "Necessario plano de acao para evitar recorrencia.",
             "medium", "assigned", "juliana.costa@santander.com.br",
             "santander_credito_app_catalog.regulatorio.reporte_3040",
             "Dependencia de dados do sistema legado com falha de integracao",
             None,
             json.dumps(["regulatorio.reporte_3040", "legado.dados_fonte"]),
             now - timedelta(days=15), now - timedelta(days=12), None),

            # 2 resolved
            (domain_ids["Credito"], rule_ids[0],
             "CPFs nulos em lote de migracao do sistema legado",
             "Lote de 3.200 contratos migrados do sistema legado sem CPF preenchido. "
             "Dados recuperados do backup do sistema origem.",
             "high", "resolved", "marcos.silva@santander.com.br",
             "santander_credito_app_catalog.credito.contratos",
             "Erro no mapeamento de campos durante ETL de migracao",
             "Corrigido mapeamento no pipeline ETL e reprocessados os 3.200 registros. "
             "Score de completude retornou a 99.8%.",
             json.dumps(["legado.contratos", "credito.contratos_staging", "credito.contratos"]),
             now - timedelta(days=25), now - timedelta(days=20), now - timedelta(days=20)),

            (domain_ids["Risco"], rule_ids[5],
             "Duplicidade de operacoes no sistema de risco",
             "Detectadas 156 operacoes duplicadas por erro de re-processamento no batch noturno.",
             "medium", "resolved", "fernanda.oliveira@santander.com.br",
             "santander_credito_app_catalog.risco.exposicoes",
             "Job de reconciliacao executado duas vezes por falha no scheduler",
             "Implementado controle de idempotencia no job. Registros duplicados removidos.",
             json.dumps(["risco.exposicoes_raw", "risco.exposicoes"]),
             now - timedelta(days=30), now - timedelta(days=28), now - timedelta(days=28)),
        ]

        incident_ids = []
        for inc in incidents_data:
            cur.execute(
                """INSERT INTO dq_quality_incidents
                   (domain_id, rule_id, title, description, severity, status, assigned_to,
                    source_table, root_cause, resolution, lineage_path, created_at, updated_at, resolved_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                inc,
            )
            incident_ids.append(cur.fetchone()[0])

        # ---- Quality Actions (12 actions) ----
        actions_data = [
            # Incident 0: Divergencia contabil (critical, open)
            (incident_ids[0], "investigation", "Levantar todos os lancamentos de PDD dos ultimos 30 dias e cruzar com razao",
             "carlos.mendes@santander.com.br", (now + timedelta(days=1)).date(), "in_progress"),
            (incident_ids[0], "remediation", "Efetuar lancamento de ajuste para correcao do saldo de provisao",
             "contabilidade@santander.com.br", (now + timedelta(days=3)).date(), "pending"),

            # Incident 1: Reporte duplicado (critical, open)
            (incident_ids[1], "investigation", "Identificar origem das duplicatas no pipeline de geracao do reporte 3040",
             "regulatorio@santander.com.br", (now + timedelta(days=1)).date(), "pending"),
            (incident_ids[1], "remediation", "Preparar e enviar retificacao ao BACEN com dados corretos",
             "regulatorio@santander.com.br", (now + timedelta(days=5)).date(), "pending"),

            # Incident 2: Atraso CDC (investigating)
            (incident_ids[2], "investigation", "Analisar logs do pipeline de ingestao CDC para identificar gargalo",
             "ana.ferreira@santander.com.br", (now - timedelta(days=2)).date(), "completed"),
            (incident_ids[2], "remediation", "Otimizar step de transformacao com particao por modalidade",
             "ana.ferreira@santander.com.br", (now + timedelta(days=2)).date(), "in_progress"),

            # Incident 3: Desbalanceamento (investigating)
            (incident_ids[3], "investigation", "Auditar lancamentos das contas COSIF do grupo 1.6 no periodo",
             "patricia.lima@santander.com.br", (now - timedelta(days=1)).date(), "in_progress"),

            # Incident 4: VaR (assigned)
            (incident_ids[4], "remediation", "Revisar hedge das posicoes em opcoes de dolar",
             "ricardo.santos@santander.com.br", (now + timedelta(days=3)).date(), "pending"),
            (incident_ids[4], "prevention", "Implementar alerta automatico quando VaR atingir 90% do limite",
             "ricardo.santos@santander.com.br", (now + timedelta(days=10)).date(), "pending"),

            # Incident 5: Atraso reporte (assigned)
            (incident_ids[5], "remediation", "Criar redundancia na integracao com sistema legado",
             "juliana.costa@santander.com.br", (now + timedelta(days=7)).date(), "pending"),

            # Incident 6: CPFs nulos (resolved)
            (incident_ids[6], "investigation", "Mapear campos faltantes na ETL de migracao",
             "marcos.silva@santander.com.br", (now - timedelta(days=22)).date(), "completed"),
            (incident_ids[6], "remediation", "Reprocessar lote com mapeamento corrigido",
             "marcos.silva@santander.com.br", (now - timedelta(days=20)).date(), "completed"),
        ]

        for act in actions_data:
            completed = now - timedelta(days=random.randint(1, 5)) if act[5] == "completed" else None
            cur.execute(
                """INSERT INTO dq_quality_actions
                   (incident_id, action_type, description, owner_email, deadline, status, completed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (*act, completed),
            )

        # ---- BDR Conciliation (30 records) ----
        bdr_metrics = [
            ("Saldo Carteira Credito", "contabil.balancete_credito", "regulatorio.reporte_3040"),
            ("Provisao PDD", "contabil.provisao_pdd", "regulatorio.reporte_3050"),
            ("Captacao Total", "contabil.balancete_captacao", "regulatorio.reporte_4060"),
            ("Exposicao Derivativos", "risco.exposicao_derivativos", "regulatorio.reporte_2060"),
            ("Patrimonio Liquido", "contabil.patrimonio", "regulatorio.dlo_bacen"),
        ]

        for day_offset in range(6):
            conc_date = (now - timedelta(days=day_offset * 5)).date()
            for metric_name, acc_src, reg_src in bdr_metrics:
                # Most values match closely, but create some divergences
                base_val = round(random.uniform(500000000, 50000000000), 2)
                is_divergent = random.random() < 0.2  # 20% chance of divergence

                if is_divergent:
                    div_pct = round(random.uniform(0.02, 0.5), 4)
                    reg_val = round(base_val * (1 + div_pct / 100), 2)
                    divergence = round(reg_val - base_val, 2)
                    status = "divergent" if div_pct > 0.1 else "warning"
                else:
                    div_pct = round(random.uniform(0, 0.009), 4)
                    reg_val = round(base_val * (1 + div_pct / 100), 2)
                    divergence = round(reg_val - base_val, 2)
                    status = "ok"

                # Assign to most relevant domain
                if "credito" in metric_name.lower() or "pdd" in metric_name.lower():
                    did = domain_ids["Credito"]
                elif "derivativo" in metric_name.lower():
                    did = domain_ids["Risco"]
                elif "patrimonio" in metric_name.lower() or "captacao" in metric_name.lower():
                    did = domain_ids["Contabil"]
                else:
                    did = domain_ids["Regulatorio"]

                resolution = None
                if status == "ok":
                    resolution = "Valores dentro da tolerancia."
                elif day_offset > 3 and is_divergent:
                    resolution = "Divergencia investigada e justificada - diferenca temporal de processamento."
                    status = "resolved"

                cur.execute(
                    """INSERT INTO dq_bdr_conciliation
                       (domain_id, conciliation_date, accounting_source, regulatory_source,
                        metric_name, accounting_value, regulatory_value, divergence, divergence_pct,
                        threshold_pct, status, resolution_notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (did, conc_date, acc_src, reg_src, metric_name,
                     base_val, reg_val, divergence, div_pct, 0.01, status, resolution),
                )

    logger.info("DQ seed data inserted successfully.")


def init_db():
    """Create schema and seed if empty."""
    create_schema()
    if not tables_exist():
        logger.info("No data found, seeding demo data...")
        seed_all()
        logger.info("Seed complete.")
    else:
        logger.info("Data already exists, skipping seed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
