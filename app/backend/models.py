"""Pydantic v2 models for the R.18 Compliance Accelerator API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Pagination ---

class Pagination(BaseModel):
    page: int = 1
    page_size: int = 50
    total_results: int = 0
    total_pages: int = 0


# --- Dashboard / KPI ---

class DimensionScore(BaseModel):
    id: int
    name: str
    score: float
    status: str  # conforme | atencao | nao_conforme


class PendingValidations(BaseModel):
    scr3040: int = 0
    scr3050: int = 0


class LastSubmission(BaseModel):
    document: str
    data_base: str
    status: str
    submitted_at: str


class Alert(BaseModel):
    severity: str
    message: str
    created_at: str


class Deadline(BaseModel):
    date: str
    days_remaining: int
    phase: str


class DashboardKPIs(BaseModel):
    data_base: str
    compliance_score: float
    dimensions: list[DimensionScore]
    pending_validations: PendingValidations
    last_submission: LastSubmission
    alerts: list[Alert]
    deadline: Deadline


class DashboardInfo(BaseModel):
    id: str
    name: str
    description: str
    type: str
    last_published: str | None = None


class DashboardListResponse(BaseModel):
    dashboards: list[DashboardInfo]


class DashboardEmbed(BaseModel):
    dashboard_id: str
    dashboard_name: str
    embed_url: str
    embed_token: str
    token_expires_at: str
    width: str = "100%"
    height: str = "800px"


# --- Quality Dimensions ---

class TrendPoint(BaseModel):
    month: str
    score: float


class DimensionMetrics(BaseModel):
    sla_atendimento_pct: float | None = None
    catalogo_cobertura_pct: float | None = None
    taxa_rejeicao_bcb_pct: float | None = None
    validacao_fonte_primaria_pct: float | None = None


class DimensionDetail(BaseModel):
    id: int
    code: str
    name: str
    description: str
    score: float
    target: float
    status: str
    metrics: dict[str, float] = {}
    trend: list[TrendPoint] = []


class QualityDimensionsResponse(BaseModel):
    data_base: str
    overall_score: float
    dimensions: list[DimensionDetail]


class Violation(BaseModel):
    rule_id: str
    rule_description: str
    severity: str
    count: int
    sample_records: list[str] = []


class DimensionDetailResponse(BaseModel):
    dimension: dict[str, Any]
    score: float
    target: float
    status: str
    metrics: dict[str, float] = {}
    violations: list[Violation] = []
    trend: list[TrendPoint] = []


# --- Validation Results ---

class ValidationSummary(BaseModel):
    total_rules: int
    passed: int
    failed: int
    warnings: int
    pass_rate_pct: float


class ValidationResult(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: str
    severity: str
    dimension_r18: int
    dimension_name: str
    status: str
    affected_records: int
    total_records: int
    affected_pct: float
    description: str
    sample_ipocs: list[str] = []
    nivel_verificacao: int = 1  # 1=Básico, 2=Coerência temporal, 3=Regras negociais


class ValidationResultsResponse(BaseModel):
    data_base: str
    run_id: str
    run_status: str
    run_completed_at: str | None = None
    summary: ValidationSummary
    results: list[ValidationResult]
    pagination: Pagination


# --- Validation Trigger / Run ---

class TriggerValidationRequest(BaseModel):
    document: str
    data_base: str
    scope: str = "full"
    rule_ids: list[str] | None = None


class TriggerValidationResponse(BaseModel):
    run_id: str
    job_run_id: int
    status: str
    document: str
    data_base: str
    scope: str
    triggered_by: str
    triggered_at: str
    estimated_duration_minutes: int = 45


class RunProgress(BaseModel):
    current_step: str
    steps_completed: int
    total_steps: int
    records_processed: int
    total_records: int
    elapsed_seconds: int


class ValidationRunStatus(BaseModel):
    run_id: str
    job_run_id: int
    status: str
    document: str
    data_base: str
    progress: RunProgress | None = None
    triggered_by: str
    triggered_at: str
    started_at: str | None = None
    completed_at: str | None = None


class RunSummary(BaseModel):
    run_id: str
    document: str
    data_base: str
    status: str
    scope: str
    summary: ValidationSummary | None = None
    triggered_by: str
    triggered_at: str
    completed_at: str | None = None
    duration_seconds: int | None = None


class ValidationRunsResponse(BaseModel):
    runs: list[RunSummary]


# --- Lineage ---

class LineageNodeMetadata(BaseModel):
    connection: str | None = None
    update_frequency: str | None = None
    row_count: int | None = None
    last_updated: str | None = None
    expectations_pass_rate: float | None = None
    file_size_mb: float | None = None
    parts: int | None = None
    validated: bool | None = None


class LineageNode(BaseModel):
    id: str
    label: str
    type: str
    layer: str
    system: str | None = None
    catalog: str | None = None
    schema_name: str | None = Field(None, alias="schema")
    metadata: LineageNodeMetadata | None = None

    model_config = {"populate_by_name": True}


class ColumnMapping(BaseModel):
    source: str
    target: str


class LineageEdge(BaseModel):
    source: str
    target: str
    type: str
    pipeline: str | None = None
    audit_ref: str | None = None
    column_mappings: list[ColumnMapping] | None = None


class LineageGraphResponse(BaseModel):
    nodes: list[LineageNode]
    edges: list[LineageEdge]


class UpstreamColumn(BaseModel):
    table: str
    column: str
    transformation: str


class ExternalSource(BaseModel):
    system: str
    table: str
    columns: list[str]
    source_type: str


class ColumnLineageResponse(BaseModel):
    target_column: str
    upstream_columns: list[UpstreamColumn]
    external_sources: list[ExternalSource] = []


# --- XML Processing ---

class XmlUploadResponse(BaseModel):
    file_id: str
    filename: str
    document_type: str
    file_size_bytes: int
    encoding: str = "ISO-8859-1"
    uploaded_at: str
    status: str


class XmlTreeNode(BaseModel):
    tag: str
    attributes: dict[str, str] = {}
    children_count: int = 0
    children: list[XmlTreeNode] = []


class XmlTreeStatistics(BaseModel):
    total_elements: int
    total_clients: int
    total_operations: int
    total_aggregated: int


class XmlTreeResponse(BaseModel):
    file_id: str
    document_type: str
    root: XmlTreeNode
    statistics: XmlTreeStatistics


class XmlValidateRequest(BaseModel):
    xsd_version: str = "V11"
    max_errors: int = 100


class XmlValidationError(BaseModel):
    line: int
    column: int
    path: str
    error_type: str
    field: str
    value: str
    message: str
    xsd_constraint: str


class XmlValidateResponse(BaseModel):
    file_id: str
    valid: bool
    xsd_version: str
    errors_found: int
    max_errors: int
    errors: list[XmlValidationError]
    warnings: list[XmlValidationError] = []
    validated_at: str


class FieldValidation(BaseModel):
    rule: str
    passed: bool
    detail: str


class XmlField(BaseModel):
    name: str
    value: str
    status: str
    validations: list[FieldValidation]


class XmlFieldsResponse(BaseModel):
    xpath: str
    element: str
    fields: list[XmlField]


# --- Reference Data ---

class DominioValue(BaseModel):
    code: str
    description: str
    active: bool = True


class DominioField(BaseModel):
    field: str
    description: str
    values: list[DominioValue]


class DominiosResponse(BaseModel):
    document: str | None = None
    version: str = "V11"
    fields: list[DominioField]


class CriticaRule(BaseModel):
    rule_id: str
    document: str
    rule_type: str
    severity: str
    dimension_r18: int
    dimension_name: str
    expression: str
    description: str
    bcb_reference: str
    layout_version: str
    active: bool = True


class CriticasResponse(BaseModel):
    total: int
    rules: list[CriticaRule]


class CalendarioDay(BaseModel):
    date: str
    is_dia_util: bool
    is_ultimo_du_semana: bool
    is_ultimo_du_mes: bool
    feriado: str | None = None


class CalendarioWeek(BaseModel):
    data_base: str
    dias_uteis: list[str]


class CalendarioSummary(BaseModel):
    total_dias_uteis: int
    total_feriados: int
    ultimo_du_mes: str
    semanas: list[CalendarioWeek]


class CalendarioResponse(BaseModel):
    year: int
    month: int | None = None
    days: list[CalendarioDay]
    summary: CalendarioSummary


class EquivalenciaMapping(BaseModel):
    modality_3040: str
    modality_3040_description: str
    category_3050: str
    category_3050_description: str
    segment: str
    credit_type: str
    periodicity: str
    special_rules: str | None = None


class EquivalenciaResponse(BaseModel):
    version: str
    mappings: list[EquivalenciaMapping]


class DimensionMetricDef(BaseModel):
    code: str
    name: str
    target: float
    unit: str


class DimensionDefinition(BaseModel):
    id: int
    code: str
    name: str
    article: str
    definition: str
    implementation: str
    databricks_capability: str
    metrics: list[DimensionMetricDef]


class DimensionsResponse(BaseModel):
    dimensions: list[DimensionDefinition]


# --- Submissions ---

class SubmissionRecord(BaseModel):
    id: str
    document: str
    data_base: str
    remessa: int
    parts: int
    status: str
    submitted_at: str
    accepted_at: str | None = None
    rejected_at: str | None = None
    rejection_reasons: list[str] = []
    file_size_mb: float
    validator_result: str
    validator_errors: int
    validator_warnings: int
    channel: str
    submitted_by: str
    approved_by: str | None = None
    quality_gate_passed: bool
    quality_gate_score: float


class SubmissionSummary(BaseModel):
    total_submissions: int
    accepted: int
    rejected: int
    acceptance_rate_pct: float
    avg_days_before_deadline: float


class SubmissionsResponse(BaseModel):
    submissions: list[SubmissionRecord]
    summary: SubmissionSummary


class QualityGateCheck(BaseModel):
    category: str
    name: str
    status: str
    pass_rate_pct: float
    details: str | None = None
    last_run: str
    blocking: bool = True


class QualityGateBlocker(BaseModel):
    category: str
    message: str
    action_required: str


class QualityGateResponse(BaseModel):
    document: str
    data_base: str
    gate_status: str
    overall_score: float
    checks: list[QualityGateCheck]
    blockers: list[QualityGateBlocker]
    submission_allowed: bool
    evaluated_at: str


# --- Governance ---

class IrregularityDimensionSummary(BaseModel):
    dimension_id: int
    name: str
    count: int


class IrregularitySummary(BaseModel):
    total_open: int
    total_in_progress: int
    total_resolved: int
    avg_resolution_days: float
    by_dimension: list[IrregularityDimensionSummary]


class IncidentEvent(BaseModel):
    timestamp: str
    event_type: str  # detected, assigned, responded, escalated, resolved, validated, reopened, comment
    actor: str
    description: str


class Irregularity(BaseModel):
    id: str
    detected_at: str
    data_base: str
    document: str
    dimension_r18: int
    dimension_name: str
    severity: str
    status: str
    description: str
    root_cause: str | None = None
    impact: str | None = None
    remedial_action: str | None = None
    owner: str | None = None
    resolved_at: str | None = None
    resolution_days: int | None = None
    detected_by: str | None = None
    responded_by: str | None = None
    responded_at: str | None = None
    validated_by: str | None = None
    validated_at: str | None = None
    escalated_by: str | None = None
    escalated_at: str | None = None
    escalated_to: str | None = None
    timeline: list[IncidentEvent] = []
    bcb_communication_required: bool = False
    included_in_report: str | None = None


class IrregularitiesResponse(BaseModel):
    total: int
    irregularities: list[Irregularity]
    summary: IrregularitySummary
    pagination: Pagination


class GovernanceReport(BaseModel):
    id: str
    period: str
    period_start: str
    period_end: str
    status: str
    generated_at: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None
    distributed_to: list[str] = []
    irregularities_count: int
    resolved_count: int
    pending_count: int
    dimensions_covered: int
    pdf_url: str | None = None


class GovernanceReportsResponse(BaseModel):
    reports: list[GovernanceReport]


class ActionPlanUpdate(BaseModel):
    date: str
    author: str
    note: str


class ActionPlan(BaseModel):
    id: str
    irregularity_id: str
    title: str
    description: str
    owner: str
    created_at: str
    deadline: str
    status: str  # pending, in_progress, completed, overdue
    progress_pct: float
    dimension_r18: int
    dimension_name: str
    auditor_caveat: str | None = None
    updates: list[ActionPlanUpdate] = []


class ActionPlansResponse(BaseModel):
    total: int
    action_plans: list[ActionPlan]
    pagination: Pagination


class IrregularityDetailResponse(BaseModel):
    irregularity: Irregularity
    action_plans: list[ActionPlan]


# --- Health / System ---

class DependencyStatus(BaseModel):
    status: str
    warehouse_id: str | None = None
    warehouse_name: str | None = None
    state: str | None = None
    host: str | None = None
    response_time_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    dependencies: dict[str, DependencyStatus]


class UserContext(BaseModel):
    email: str
    username: str
    display_name: str | None = None
    workspace: str = ""
    roles: list[str] = ["viewer"]
    preferences: dict[str, Any] = {}


class AppConfig(BaseModel):
    app_name: str = "R.18 Compliance Accelerator"
    app_version: str = "1.0.0"
    workspace: str = ""
    catalog: str = "rc18_catalog"
    schemas: dict[str, str] = {}
    documents: list[str] = ["3040", "3050"]
    current_layout_versions: dict[str, str] = {}
    dashboards: dict[str, str] = {}
    genie_space_id: str | None = None
    features: dict[str, bool] = {}
    deadline: str = "2026-12-31"
    language: str = "pt-BR"


# --- Rule Engine ---

class RECondition(BaseModel):
    column: str
    operator: str
    value: Any = None
    value_is_column: bool = False


class REStructuredDefinition(BaseModel):
    version: int = 1
    operator: str = "AND"
    conditions: list[RECondition] = []


class REParameter(BaseModel):
    name: str
    type: str = "any"
    description: str = ""


class RERuleCreate(BaseModel):
    name: str
    description: str | None = None
    nivel_verificacao: int = 1  # 1=Básico, 2=Coerência temporal, 3=Regras negociais
    rule_type: str = "syntactic"  # syntactic | semantic | inter_document | business
    dimension_r18: int | None = None
    severity: str = "error"  # error | warning | info
    authoring_mode: str = "structured"  # "structured" or "expression"
    structured_definition: REStructuredDefinition | None = None
    expression: str | None = None
    parameters: list[REParameter] | None = None
    tags: list[str] | None = None


class RERule(BaseModel):
    rule_id: str
    name: str
    description: str | None = None
    nivel_verificacao: int = 1
    rule_type: str = "syntactic"
    dimension_r18: int | None = None
    severity: str = "error"
    authoring_mode: str = "structured"
    structured_definition: dict | None = None
    expression: str | None = None
    parameters: list[REParameter] | None = None
    tags: list[str] | None = None
    is_seeded: bool = False
    source_critica_id: str | None = None
    created_by: str
    created_at: str
    updated_at: str
    is_active: bool = True


class RERuleListResponse(BaseModel):
    total: int
    rules: list[RERule]


class REDataset(BaseModel):
    dataset_id: str
    name: str
    source_path: str  # UC table name or volume path
    tipo: str  # "table" or "file"
    data_base: str | None = None  # YYYY-MM reference month
    description: str | None = None
    row_count_approx: int | None = None
    last_profiled_at: str | None = None
    registered_by: str
    registered_at: str


class REDatasetListResponse(BaseModel):
    total: int
    datasets: list[REDataset]


class REColumn(BaseModel):
    name: str
    type: str
    nullable: bool = True
    description: str | None = None


class REColumnListResponse(BaseModel):
    dataset_id: str
    table_name: str
    columns: list[REColumn]


class REDatasetDetail(BaseModel):
    dataset: REDataset
    columns: list[REColumn]
    bindings_count: int = 0
    last_run: str | None = None


class REBindingCreate(BaseModel):
    rule_id: str
    column_bindings: dict[str, str]
    override_name: str | None = None
    override_severity: str | None = None


class REBinding(BaseModel):
    binding_id: str
    rule_id: str
    dataset_id: str
    rule_name: str
    column_bindings: dict[str, str]
    override_name: str | None = None
    override_severity: str | None = None
    is_active: bool = True
    created_by: str
    created_at: str


class REBindingListResponse(BaseModel):
    total: int
    bindings: list[REBinding]


class RETriggerRunResponse(BaseModel):
    run_id: str
    job_run_id: int | None = None
    status: str
    dataset_id: str
    total_bindings: int
    triggered_by: str
    triggered_at: str


class RERunStatus(BaseModel):
    run_id: str
    dataset_id: str
    dataset_name: str
    job_run_id: int | None = None
    status: str
    total_rules: int | None = None
    total_records: int | None = None
    triggered_by: str
    triggered_at: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: int | None = None
    error_message: str | None = None


class RERunResult(BaseModel):
    result_id: str
    binding_id: str
    rule_id: str
    rule_name: str
    status: str
    total_records: int
    passed_records: int
    failed_records: int
    pass_rate_pct: float
    severity: str
    dimension_r18: int | None = None
    execution_time_ms: int | None = None
    expression_used: str | None = None


class RERunResultsSummary(BaseModel):
    total_rules: int
    passed: int
    failed: int
    warnings: int
    pass_rate_pct: float
    total_records: int
    total_exceptions: int


class RERunResultsResponse(BaseModel):
    run_id: str
    dataset_name: str
    status: str
    summary: RERunResultsSummary
    results: list[RERunResult]


class REException(BaseModel):
    exception_id: str
    result_id: str
    binding_id: str
    rule_name: str
    row_identifier: dict[str, Any]
    failed_columns: list[str] | None = None
    row_snapshot: dict[str, Any] | None = None
    failure_reason: str | None = None


class REExceptionsResponse(BaseModel):
    run_id: str
    result_id: str | None = None
    total: int = 0
    exceptions: list[REException]
    pagination: Pagination


class RERunListResponse(BaseModel):
    total: int
    runs: list[RERunStatus]


class RESeedResponse(BaseModel):
    rules_created: int
    bindings_created: int
    rule_ids: list[str]


class REExpressionValidation(BaseModel):
    expression: str
    is_valid: bool
    error_message: str | None = None
    resolved_expression: str | None = None
