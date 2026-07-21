import { get } from 'svelte/store';
import { locale } from 'svelte-i18n';

const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Current UI locale (e.g. 'pt', 'en'). Sent on every request so the backend
// can serve locale-matched mock data in demo mode (USE_MOCK_BACKEND=true).
function currentLocale() {
  try { return get(locale) || 'pt'; } catch (_) { return 'pt'; }
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Accept': 'application/json', 'X-Locale': currentLocale(), ...options.headers },
    ...options
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new ApiError(res.status, body.detail || 'Falha na requisicao');
    // Surface the parsed body so callers can read e.g. the `existing_incident_id`
    // returned with HTTP 409 conflicts (incident dedup) per spec 08 §4.2.
    err.body = body;
    throw err;
  }
  return res.json();
}

// Dashboard
export function getDashboardKpis(dataBase) {
  const params = dataBase ? `?data_base=${dataBase}` : '';
  return apiFetch(`/dashboard/kpis${params}`);
}

// Data-bases disponíveis + a corrente (último CADOC processado). Alimenta o
// seletor de Data-Base no header — substitui a lista antes hardcoded.
export function getDataBases() {
  return apiFetch('/dashboard/data-bases');
}

// Quality
export function getQualityDimensions(dataBase, trendMonths = 6) {
  const params = new URLSearchParams();
  if (dataBase) params.set('data_base', dataBase);
  params.set('trend_months', trendMonths);
  return apiFetch(`/quality/dimensions?${params}`);
}

export function getQualityTrend(dataBase, months = 6) {
  const params = new URLSearchParams();
  if (dataBase) params.set('data_base', dataBase);
  params.set('months', months);
  return apiFetch(`/quality/trend?${params}`);
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

// Create an incident from a DQX validation row (Críticas SCR "Criar Incidente" button).
// Dedup key per docs/spec/08_dqx_app_integration.md §4.1:
//   (critica_id, run_config_name, dt_base) WHERE status NOT IN ('resolved','validated')
// On dedup hit the backend returns HTTP 409 with body { existing_incident_id, detail }.
export function createIncident(payload) {
  return apiFetch('/governance/incidents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

// Transition an incident through the FSM (spec 08 §4.3 / spec 07 §12.4).
// Body shape: { status, owner?, comment?, root_cause?, remedial_action?, escalated_to? }
// Allowed target statuses: 'assigned' | 'in_progress' | 'resolved' | 'validated'
// | 'escalated' | 'reopened' | 'open'. Rejects illegal transitions with HTTP 400.
export function updateIncidentStatus(incidentId, payload) {
  return apiFetch(`/governance/incidents/${encodeURIComponent(incidentId)}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
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
