<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import { getIrregularities, getIrregularityDetail, getActionPlans, getGovernanceReports } from '$lib/api.js';
  import { formatDateTime, formatDate } from '$lib/format.js';
  import { onMount } from 'svelte';

  // --- Tabs ---
  let activeTab = $state('incidentes');
  const tabs = [
    { key: 'incidentes', label: 'Incidentes' },
    { key: 'planos', label: 'Planos de Ação' },
    { key: 'relatorios', label: 'Relatórios' }
  ];

  // --- Incidentes state ---
  let irregularities = $state([]);
  let summary = $state({ total_open: 0, total_in_progress: 0, total_resolved: 0, avg_resolution_days: 0 });
  let loading = $state(false);
  let filterValues = $state({});
  let expandedRow = $state(null);
  let showDetailModal = $state(false);
  let selectedIncident = $state(null);
  let selectedPlans = $state([]);

  const STATUS_MAP = {
    open: { label: 'Aberto', variant: 'error' },
    in_progress: { label: 'Em Andamento', variant: 'warning' },
    resolved: { label: 'Resolvido', variant: 'success' },
    escalated: { label: 'Escalado', variant: 'error' },
    validated: { label: 'Validado', variant: 'info' },
  };

  const SEVERITY_MAP = {
    high: { label: 'Alta', variant: 'error' },
    medium: { label: 'Média', variant: 'warning' },
    low: { label: 'Baixa', variant: 'success' },
  };

  const EVENT_TYPE_MAP = {
    detected: { label: 'Detectado', color: 'var(--primary)' },
    assigned: { label: 'Atribuído', color: 'var(--gray-500)' },
    responded: { label: 'Respondido', color: 'var(--warning)' },
    escalated: { label: 'Escalado', color: 'var(--error)' },
    resolved: { label: 'Resolvido', color: 'var(--success)' },
    validated: { label: 'Validado', color: 'var(--success-dark, var(--success))' },
    reopened: { label: 'Reaberto', color: 'var(--error)' },
    comment: { label: 'Comentário', color: 'var(--gray-400)' },
  };

  const filterDefs = [
    { key: 'status', label: 'Status', type: 'select', options: [
      { value: 'open', label: 'Aberto' }, { value: 'in_progress', label: 'Em Andamento' },
      { value: 'resolved', label: 'Resolvido' }, { value: 'escalated', label: 'Escalado' }
    ]},
    { key: 'severity', label: 'Severidade', type: 'select', options: [
      { value: 'high', label: 'Alta' }, { value: 'medium', label: 'Média' }, { value: 'low', label: 'Baixa' }
    ]},
    { key: 'dimension_r18', label: 'Dimensão R.18', type: 'select', options: Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `${i + 1}` })) },
  ];

  const incidentColumns = [
    { key: 'id', label: 'ID', sortable: true, width: '140px' },
    { key: 'detected_at', label: 'Detectado', sortable: true, width: '180px', render: (v) => formatDateTime(v) },
    { key: 'document', label: 'Doc', sortable: true, width: '60px' },
    { key: 'dimension_name', label: 'Dimensão', sortable: true, width: '120px' },
    { key: 'severity', label: 'Severidade', sortable: true, width: '100px', render: (v) => {
      const s = SEVERITY_MAP[v] || { label: v, variant: 'neutral' };
      return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`;
    }},
    { key: 'status', label: 'Status', sortable: true, width: '120px', render: (v) => {
      const s = STATUS_MAP[v] || { label: v, variant: 'neutral' };
      return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`;
    }},
    { key: 'owner', label: 'Responsável', sortable: true },
    { key: 'resolution_days', label: 'Dias', sortable: true, width: '60px' },
  ];

  // --- Planos state ---
  let actionPlans = $state([]);
  let plansLoading = $state(false);
  let planExpandedRow = $state(null);

  const PLAN_STATUS_MAP = {
    pending: { label: 'Pendente', variant: 'neutral' },
    in_progress: { label: 'Em Andamento', variant: 'warning' },
    completed: { label: 'Concluído', variant: 'success' },
    overdue: { label: 'Atrasado', variant: 'error' },
  };

  const planColumns = [
    { key: 'id', label: 'ID', sortable: true, width: '120px' },
    { key: 'title', label: 'Título', sortable: true },
    { key: 'owner', label: 'Responsável', sortable: true, width: '180px' },
    { key: 'status', label: 'Status', sortable: true, width: '120px', render: (v) => {
      const s = PLAN_STATUS_MAP[v] || { label: v, variant: 'neutral' };
      return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`;
    }},
    { key: 'progress_pct', label: 'Progresso', sortable: true, width: '150px', render: (v) =>
      `<div class="progress-bar"><div class="progress-fill" style="width:${v}%"></div><span class="progress-text">${v}%</span></div>`
    },
    { key: 'deadline', label: 'Prazo', sortable: true, width: '110px', render: (v) => formatDate(v) },
    { key: 'dimension_name', label: 'Dimensão', sortable: true, width: '120px' },
  ];

  // --- Relatórios state ---
  let reports = $state([]);
  let reportsLoading = $state(false);

  const REPORT_STATUS_MAP = {
    draft: { label: 'Rascunho', variant: 'neutral' },
    in_progress: { label: 'Em Elaboração', variant: 'warning' },
    approved: { label: 'Aprovado', variant: 'success' },
    distributed: { label: 'Distribuído', variant: 'info' },
  };

  // --- Data loading ---
  async function loadIrregularities() {
    loading = true;
    try {
      const data = await getIrregularities(filterValues);
      if (data?.irregularities) irregularities = data.irregularities;
      if (data?.summary) summary = { ...summary, ...data.summary };
    } catch { /* keep current state */ }
    loading = false;
  }

  async function loadActionPlans() {
    plansLoading = true;
    try {
      const data = await getActionPlans();
      if (data?.action_plans) actionPlans = data.action_plans;
    } catch { /* keep current state */ }
    plansLoading = false;
  }

  async function loadReports() {
    reportsLoading = true;
    try {
      const data = await getGovernanceReports();
      if (data?.reports) reports = data.reports;
    } catch { /* keep current state */ }
    reportsLoading = false;
  }

  async function openDetail(row) {
    try {
      const data = await getIrregularityDetail(row.id);
      selectedIncident = data.irregularity;
      selectedPlans = data.action_plans || [];
    } catch {
      selectedIncident = row;
      selectedPlans = [];
    }
    showDetailModal = true;
  }

  function handleFilter(key, value) {
    filterValues = { ...filterValues, [key]: value };
  }

  function resetFilters() {
    filterValues = {};
  }

  let filteredIrregularities = $derived.by(() => {
    let data = irregularities;
    if (filterValues.status) data = data.filter(r => r.status === filterValues.status);
    if (filterValues.severity) data = data.filter(r => r.severity === filterValues.severity);
    if (filterValues.dimension_r18) data = data.filter(r => r.dimension_r18 === Number(filterValues.dimension_r18));
    return data;
  });

  onMount(() => {
    loadIrregularities();
    loadActionPlans();
    loadReports();
  });

  $effect(() => {
    if (activeTab === 'incidentes') {
      void filterValues;
      loadIrregularities();
    }
  });
</script>

<div class="governance-page">
  <Tabs {tabs} active={activeTab} onchange={(key) => { activeTab = key; expandedRow = null; planExpandedRow = null; }} />

  {#if activeTab === 'incidentes'}
    <!-- KPI Cards -->
    <div class="kpi-grid">
      <KpiCard title="Abertos" value={summary.total_open} status="error" />
      <KpiCard title="Em Andamento" value={summary.total_in_progress} status="warning" />
      <KpiCard title="Resolvidos" value={summary.total_resolved} status="success" />
      <KpiCard title="Tempo Médio Resolução" value={summary.avg_resolution_days} unit=" dias" status="info" />
    </div>

    <FilterBar filters={filterDefs} values={filterValues} onchange={handleFilter} onreset={resetFilters} />

    {#if loading}
      <Spinner message="Carregando incidentes..." />
    {:else}
      <div class="card">
        <DataTable
          columns={incidentColumns}
          data={filteredIrregularities}
          {expandedRow}
          onRowClick={(row, i) => expandedRow = expandedRow === i ? null : i}
        >
          {#snippet expandSnippet(row)}
            <div class="incident-expand">
              <div class="expand-info">
                <p><strong>Descrição:</strong> {row.description}</p>
                {#if row.root_cause}<p><strong>Causa Raiz:</strong> {row.root_cause}</p>{/if}
                {#if row.remedial_action}<p><strong>Ação Corretiva:</strong> {row.remedial_action}</p>{/if}
                {#if row.impact}<p><strong>Impacto:</strong> {row.impact}</p>{/if}
              </div>
              <div class="expand-lifecycle">
                <strong>Ciclo de Vida:</strong>
                <div class="lifecycle-grid">
                  <div class="lifecycle-item">
                    <span class="lifecycle-label">Detectado por</span>
                    <span class="lifecycle-value">{row.detected_by || '-'}</span>
                  </div>
                  <div class="lifecycle-item">
                    <span class="lifecycle-label">Respondido por</span>
                    <span class="lifecycle-value">{row.responded_by || '-'}</span>
                  </div>
                  <div class="lifecycle-item">
                    <span class="lifecycle-label">Validado por</span>
                    <span class="lifecycle-value">{row.validated_by || '-'}</span>
                  </div>
                  {#if row.escalated_by}
                    <div class="lifecycle-item">
                      <span class="lifecycle-label">Escalado por</span>
                      <span class="lifecycle-value">{row.escalated_by}</span>
                    </div>
                  {/if}
                </div>
              </div>
              <button class="btn-detail" onclick={() => openDetail(row)}>Ver Timeline Completa</button>
            </div>
          {/snippet}
        </DataTable>
      </div>
    {/if}

    <!-- Detail Modal -->
    <Modal open={showDetailModal} title={selectedIncident?.id || ''} onclose={() => showDetailModal = false}>
      {#if selectedIncident}
        <div class="incident-detail">
          <div class="detail-header">
            <div class="detail-meta">
              <span class="detail-doc">Doc {selectedIncident.document}</span>
              <span class="detail-dim">{selectedIncident.dimension_name}</span>
              {@html (() => { const s = SEVERITY_MAP[selectedIncident.severity] || { label: selectedIncident.severity, variant: 'neutral' }; return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`; })()}
              {@html (() => { const s = STATUS_MAP[selectedIncident.status] || { label: selectedIncident.status, variant: 'neutral' }; return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`; })()}
            </div>
          </div>
          <p class="detail-desc">{selectedIncident.description}</p>

          {#if selectedIncident.timeline?.length}
            <h4 class="timeline-title">Timeline do Incidente</h4>
            <div class="timeline">
              {#each selectedIncident.timeline as event}
                {@const evtInfo = EVENT_TYPE_MAP[event.event_type] || { label: event.event_type, color: 'var(--gray-400)' }}
                <div class="timeline-item">
                  <div class="timeline-line-area">
                    <div class="timeline-dot" style="background: {evtInfo.color}"></div>
                    <div class="timeline-line"></div>
                  </div>
                  <div class="timeline-content">
                    <div class="timeline-header">
                      <span class="timeline-type" style="color: {evtInfo.color}">{evtInfo.label}</span>
                      <span class="timeline-time">{formatDateTime(event.timestamp)}</span>
                    </div>
                    <p class="timeline-actor">{event.actor}</p>
                    <p class="timeline-desc">{event.description}</p>
                  </div>
                </div>
              {/each}
            </div>
          {/if}

          {#if selectedPlans.length}
            <h4 class="plans-title">Planos de Ação Vinculados</h4>
            {#each selectedPlans as plan}
              <div class="linked-plan">
                <div class="linked-plan-header">
                  <strong>{plan.id}</strong> - {plan.title}
                  {@html (() => { const s = PLAN_STATUS_MAP[plan.status] || { label: plan.status, variant: 'neutral' }; return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`; })()}
                </div>
                <div class="progress-bar"><div class="progress-fill" style="width:{plan.progress_pct}%"></div><span class="progress-text">{plan.progress_pct}%</span></div>
              </div>
            {/each}
          {/if}
        </div>
      {/if}
    </Modal>

  {:else if activeTab === 'planos'}
    {#if plansLoading}
      <Spinner message="Carregando planos de ação..." />
    {:else}
      <div class="card">
        <DataTable
          columns={planColumns}
          data={actionPlans}
          expandedRow={planExpandedRow}
          onRowClick={(row, i) => planExpandedRow = planExpandedRow === i ? null : i}
        >
          {#snippet expandSnippet(row)}
            <div class="plan-expand">
              <p><strong>Descrição:</strong> {row.description}</p>
              <p><strong>Irregularidade:</strong> {row.irregularity_id}</p>
              {#if row.auditor_caveat}<p><strong>Ressalva de Auditoria:</strong> {row.auditor_caveat}</p>{/if}
              {#if row.updates?.length}
                <div class="plan-updates">
                  <strong>Histórico de Atualizações:</strong>
                  {#each row.updates as upd}
                    <div class="plan-update-item">
                      <span class="update-date">{formatDate(upd.date)}</span>
                      <span class="update-author">{upd.author}</span>
                      <span class="update-note">{upd.note}</span>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/snippet}
        </DataTable>
      </div>
    {/if}

  {:else}
    <!-- Relatórios -->
    {#if reportsLoading}
      <Spinner message="Carregando relatórios..." />
    {:else if reports.length === 0}
      <div class="empty-state">Nenhum relatório semestral encontrado.</div>
    {:else}
      <div class="reports-grid">
        {#each reports as report}
          {@const rs = REPORT_STATUS_MAP[report.status] || { label: report.status, variant: 'neutral' }}
          <div class="card report-card">
            <div class="report-header">
              <h3>{report.period}</h3>
              <Badge label={rs.label} variant={rs.variant} />
            </div>
            <div class="report-period">{formatDate(report.period_start)} - {formatDate(report.period_end)}</div>
            <div class="report-stats">
              <div class="report-stat">
                <span class="report-stat-value">{report.irregularities_count}</span>
                <span class="report-stat-label">Irregularidades</span>
              </div>
              <div class="report-stat">
                <span class="report-stat-value report-stat-success">{report.resolved_count}</span>
                <span class="report-stat-label">Resolvidas</span>
              </div>
              <div class="report-stat">
                <span class="report-stat-value report-stat-warning">{report.pending_count}</span>
                <span class="report-stat-label">Pendentes</span>
              </div>
              <div class="report-stat">
                <span class="report-stat-value">{report.dimensions_covered}</span>
                <span class="report-stat-label">Dimensões</span>
              </div>
            </div>
            {#if report.approved_at}
              <div class="report-approval">Aprovado em {formatDateTime(report.approved_at)} por {report.approved_by || '-'}</div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .governance-page {
    display: flex;
    flex-direction: column;
  }

  /* KPI Grid */
  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-4);
    margin-bottom: var(--space-5);
  }

  /* Card */
  .card {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--space-4);
    box-shadow: var(--shadow-sm);
  }

  /* Inline badges (used by DataTable render functions via @html) */
  :global(.inline-badge) {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    font-size: var(--font-size-xs);
    font-weight: 600;
    white-space: nowrap;
  }
  :global(.badge-success) { background: var(--success-light); color: var(--success); }
  :global(.badge-warning) { background: var(--warning-light); color: var(--orange-900); }
  :global(.badge-error)   { background: var(--error-light); color: var(--error); }
  :global(.badge-info)    { background: var(--info-light); color: var(--primary); }
  :global(.badge-neutral) { background: var(--gray-100); color: var(--gray-600); }

  /* Progress bar (used by DataTable render functions via @html) */
  :global(.progress-bar) {
    position: relative;
    height: 20px;
    background: var(--gray-100);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }
  :global(.progress-fill) {
    height: 100%;
    background: linear-gradient(90deg, var(--primary), var(--blue-600));
    border-radius: var(--radius-sm);
    transition: width 0.3s ease;
  }
  :global(.progress-text) {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--font-size-xs);
    font-weight: 700;
    color: var(--gray-800);
  }

  /* Incident expand */
  .incident-expand {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .expand-info p {
    margin: 0 0 var(--space-1);
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    line-height: 1.5;
  }
  .expand-lifecycle {
    margin-top: var(--space-2);
  }
  .expand-lifecycle strong {
    font-size: var(--font-size-sm);
    color: var(--gray-800);
  }
  .lifecycle-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .lifecycle-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-2) var(--space-3);
    background: var(--white);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
  }
  .lifecycle-label {
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--gray-500);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .lifecycle-value {
    font-size: var(--font-size-sm);
    color: var(--gray-800);
    font-weight: 500;
  }
  .btn-detail {
    align-self: flex-start;
    margin-top: var(--space-2);
    padding: var(--space-2) var(--space-4);
    background: var(--primary);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background var(--transition-fast);
  }
  .btn-detail:hover {
    background: var(--blue-600);
  }

  /* Detail modal */
  .incident-detail {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
  .detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .detail-meta {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .detail-doc, .detail-dim {
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--gray-600);
    padding: 2px 8px;
    background: var(--gray-100);
    border-radius: var(--radius-sm);
  }
  .detail-desc {
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    line-height: 1.6;
    margin: 0;
  }

  /* Timeline */
  .timeline-title, .plans-title {
    font-size: var(--font-size-base);
    font-weight: 700;
    color: var(--gray-800);
    margin: var(--space-2) 0 0;
  }
  .timeline {
    display: flex;
    flex-direction: column;
  }
  .timeline-item {
    display: flex;
    gap: var(--space-3);
    min-height: 60px;
  }
  .timeline-line-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 20px;
    flex-shrink: 0;
  }
  .timeline-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 4px;
  }
  .timeline-line {
    width: 2px;
    flex: 1;
    background: var(--gray-200);
  }
  .timeline-item:last-child .timeline-line {
    display: none;
  }
  .timeline-content {
    flex: 1;
    padding-bottom: var(--space-3);
  }
  .timeline-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: 2px;
  }
  .timeline-type {
    font-size: var(--font-size-sm);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .timeline-time {
    font-size: var(--font-size-xs);
    color: var(--gray-400);
  }
  .timeline-actor {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    font-weight: 600;
    margin: 0;
  }
  .timeline-desc {
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    margin: 2px 0 0;
    line-height: 1.4;
  }

  /* Linked plans in modal */
  .linked-plan {
    padding: var(--space-3);
    background: var(--gray-50);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
  }
  .linked-plan-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
    font-size: var(--font-size-sm);
    flex-wrap: wrap;
  }

  /* Plan expand */
  .plan-expand {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .plan-expand p {
    margin: 0;
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    line-height: 1.5;
  }
  .plan-updates {
    margin-top: var(--space-2);
  }
  .plan-updates strong {
    font-size: var(--font-size-sm);
    color: var(--gray-800);
  }
  .plan-update-item {
    display: flex;
    gap: var(--space-3);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--border-color);
    font-size: var(--font-size-sm);
  }
  .plan-update-item:last-child {
    border-bottom: none;
  }
  .update-date {
    color: var(--gray-500);
    font-weight: 600;
    white-space: nowrap;
    min-width: 80px;
  }
  .update-author {
    color: var(--primary);
    font-weight: 600;
    white-space: nowrap;
  }
  .update-note {
    color: var(--gray-700);
  }

  /* Reports grid */
  .reports-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: var(--space-4);
  }
  .report-card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .report-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .report-header h3 {
    margin: 0;
    font-size: var(--font-size-lg);
    font-weight: 700;
    color: var(--gray-900);
  }
  .report-period {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
  }
  .report-stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-2);
  }
  .report-stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
  .report-stat-value {
    font-size: var(--font-size-xl);
    font-weight: 800;
    color: var(--gray-900);
  }
  .report-stat-success { color: var(--success); }
  .report-stat-warning { color: var(--warning); }
  .report-stat-label {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    font-weight: 600;
    text-align: center;
  }
  .report-approval {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    padding-top: var(--space-2);
    border-top: 1px solid var(--border-color);
  }
  .empty-state {
    padding: var(--space-10);
    text-align: center;
    color: var(--gray-500);
    font-size: var(--font-size-base);
  }

  @media (max-width: 900px) {
    .kpi-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }
</style>
