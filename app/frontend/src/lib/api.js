const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Accept': 'application/json', ...options.headers },
    ...options
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || 'Falha na requisicao');
  }
  return res.json();
}

// Dashboard
export function getDashboardKpis(dataBase) {
  const params = dataBase ? `?data_base=${dataBase}` : '';
  return apiFetch(`/dashboard/kpis${params}`);
}

// Quality
export function getQualityDimensions(dataBase, trendMonths = 6) {
  const params = new URLSearchParams();
  if (dataBase) params.set('data_base', dataBase);
  params.set('trend_months', trendMonths);
  return apiFetch(`/quality/dimensions?${params}`);
}

export function getQualityDimension(dimensionId, dataBase) {
  const params = dataBase ? `?data_base=${dataBase}` : '';
  return apiFetch(`/quality/dimensions/${dimensionId}${params}`);
}

// Validations
export function getValidationResults(document, dataBase, filters = {}) {
  const params = new URLSearchParams();
  if (dataBase) params.set('data_base', dataBase);
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  return apiFetch(`/validations/scr${document}/results?${params}`);
}

export function triggerValidation(body) {
  return apiFetch('/validations/trigger', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export function getValidationRun(runId) {
  return apiFetch(`/validations/runs/${runId}`);
}

// Reconciliation
export function getReconciliationSummary(dataBase) {
  const params = dataBase ? `?data_base=${dataBase}` : '';
  return apiFetch(`/reconciliation/summary${params}`);
}

export function getReconciliationDetail(reconType, dataBase, filters = {}) {
  const params = new URLSearchParams();
  if (dataBase) params.set('data_base', dataBase);
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  return apiFetch(`/reconciliation/${reconType}/details?${params}`);
}

// Lineage
export function getLineageGraph(tableName, direction = 'both', depth = 5) {
  const params = new URLSearchParams({ direction, depth });
  if (tableName) params.set('table_name', tableName);
  return apiFetch(`/lineage/graph?${params}`);
}

export function getColumnLineage(tableName, columnName) {
  return apiFetch(`/lineage/column/${encodeURIComponent(tableName)}/${encodeURIComponent(columnName)}`);
}

// XML
export function uploadXml(file, documentType) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('document_type', documentType);
  return apiFetch('/xml/upload', { method: 'POST', body: formData, headers: {} });
}

export function getXmlTree(fileId, maxDepth = 4, maxChildren = 100) {
  return apiFetch(`/xml/${fileId}/tree?max_depth=${maxDepth}&max_children=${maxChildren}`);
}

export function validateXml(fileId) {
  return apiFetch(`/xml/${fileId}/validate`, { method: 'POST' });
}

export function getXmlFields(fileId, xpath) {
  return apiFetch(`/xml/${fileId}/fields?xpath=${encodeURIComponent(xpath)}`);
}

// Reference
export function getReferenceDominios(field) {
  const params = field ? `?field=${field}` : '';
  return apiFetch(`/reference/dominios${params}`);
}

export function getReferenceCalendar(year) {
  const params = year ? `?year=${year}` : '';
  return apiFetch(`/reference/calendar${params}`);
}

export function getReferenceEquivalence() {
  return apiFetch('/reference/modalities/equivalence');
}

export function getReferenceLayoutVersions() {
  return apiFetch('/reference/layout-versions');
}

// Dashboard embed
export function getDashboardEmbed(dashboardKey) {
  return apiFetch(`/dashboard/embed/${dashboardKey}`);
}

// Governance
export function getIrregularities(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  return apiFetch(`/governance/irregularities?${params}`);
}

export function getIrregularityDetail(id) {
  return apiFetch(`/governance/irregularities/${encodeURIComponent(id)}`);
}

export function getActionPlans(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  return apiFetch(`/governance/action-plans?${params}`);
}

export function getGovernanceReports() {
  return apiFetch('/governance/reports');
}

// Rule Engine — Datasets
export function getRuleEngineDatasets(search) {
  const params = search ? `?search=${encodeURIComponent(search)}` : '';
  return apiFetch(`/rules/datasets${params}`);
}

export function createRuleEngineDataset(body) {
  return apiFetch('/rules/datasets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export function getRuleEngineDataset(datasetId) {
  return apiFetch(`/rules/datasets/${datasetId}`);
}

export function getRuleEngineDatasetColumns(datasetId) {
  return apiFetch(`/rules/datasets/${datasetId}/columns`);
}

export function deleteRuleEngineDataset(datasetId) {
  return apiFetch(`/rules/datasets/${datasetId}`, { method: 'DELETE' });
}

// Rule Engine — Rules
export function getRuleEngineRules(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  const qs = params.toString();
  return apiFetch(`/rules/${qs ? '?' + qs : ''}`);
}

export function createRuleEngineRule(body) {
  return apiFetch('/rules/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export function getRuleEngineRule(ruleId) {
  return apiFetch(`/rules/${ruleId}`);
}

export function updateRuleEngineRule(ruleId, body) {
  return apiFetch(`/rules/${ruleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export function deleteRuleEngineRule(ruleId) {
  return apiFetch(`/rules/${ruleId}`, { method: 'DELETE' });
}

export function validateExpression(expression) {
  return apiFetch('/rules/validate-expression', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ expression })
  });
}

// Rule Engine — Bindings
export function getDatasetBindings(datasetId) {
  return apiFetch(`/rules/datasets/${datasetId}/bindings`);
}

export function createBinding(datasetId, body) {
  return apiFetch(`/rules/datasets/${datasetId}/bindings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

export function deleteBinding(datasetId, bindingId) {
  return apiFetch(`/rules/datasets/${datasetId}/bindings/${bindingId}`, { method: 'DELETE' });
}

// Rule Engine — Execution
export function triggerRuleEngineRun(datasetId) {
  return apiFetch(`/rules/datasets/${datasetId}/run`, { method: 'POST' });
}

export function getRuleEngineRunStatus(runId) {
  return apiFetch(`/rules/runs/${runId}`);
}

export function getRuleEngineRunResults(runId) {
  return apiFetch(`/rules/runs/${runId}/results`);
}

export function getRuleEngineExceptions(runId, filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  const qs = params.toString();
  return apiFetch(`/rules/runs/${runId}/exceptions${qs ? '?' + qs : ''}`);
}

export function getRuleEngineRuns(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
  const qs = params.toString();
  return apiFetch(`/rules/runs${qs ? '?' + qs : ''}`);
}

export function seedRuleEngineRules() {
  return apiFetch('/rules/seed', { method: 'POST' });
}
