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

// =============================================================================
// Branding + embed config
//
// Returns brand-related fields plus runtime URLs for embedded external apps
// (currently `dqx_studio_url` — empty string when not configured).
// =============================================================================

export function getBrandConfig() {
  return apiFetch('/brand/config');
}
