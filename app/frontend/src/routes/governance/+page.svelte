<script>
  import Badge from '$lib/components/ui/Badge.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import {
    getIrregularities,
    getIrregularityDetail,
    updateIncidentStatus,
  } from '$lib/api.js';
  import { formatDateTime, formatDate } from '$lib/format.js';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { _ } from 'svelte-i18n';

  // --- Incidentes state ---
  // Esta página tem APENAS incidentes — as abas "Planos de Ação" e "Relatórios"
  // foram removidas porque os fluxos não estão implementados (entidades vivem
  // fora do RC18 — JIRA/Confluence/etc).
  let irregularities = $state([]);
  let summary = $state({ total_open: 0, total_in_progress: 0, total_resolved: 0, avg_resolution_days: 0 });
  let loading = $state(false);
  let filterValues = $state({});
  let expandedRow = $state(null);
  let showDetailModal = $state(false);
  let selectedIncident = $state(null);

  const STATUS_MAP = $derived.by(() => ({
    open: { label: $_('governance.statusOpen'), variant: 'error' },
    in_progress: { label: $_('governance.statusInProgress'), variant: 'warning' },
    resolved: { label: $_('governance.statusResolved'), variant: 'success' },
    reopened: { label: $_('governance.statusReopened'), variant: 'error' },
  }));

  const SEVERITY_MAP = $derived.by(() => ({
    high: { label: $_('governance.severityHigh'), variant: 'error' },
    medium: { label: $_('governance.severityMedium'), variant: 'warning' },
    low: { label: $_('governance.severityLow'), variant: 'success' },
  }));

  const EVENT_TYPE_MAP = $derived.by(() => ({
    detected: { label: $_('governance.eventDetected'), color: 'var(--primary)' },
    in_progress: { label: $_('governance.statusInProgress'), color: 'var(--warning)' },
    resolved: { label: $_('governance.statusResolved'), color: 'var(--success)' },
    reopened: { label: $_('governance.statusReopened'), color: 'var(--error)' },
    comment: { label: $_('governance.eventComment'), color: 'var(--gray-400)' },
  }));

  const filterDefs = $derived.by(() => [
    { key: 'status', label: $_('common.status'), type: 'select', options: [
      { value: 'open', label: $_('governance.statusOpen') }, { value: 'in_progress', label: $_('governance.statusInProgress') },
      { value: 'resolved', label: $_('governance.statusResolved') }, { value: 'reopened', label: $_('governance.statusReopened') }
    ]},
    { key: 'severity', label: $_('governance.severity'), type: 'select', options: [
      { value: 'high', label: $_('governance.severityHigh') }, { value: 'medium', label: $_('governance.severityMedium') }, { value: 'low', label: $_('governance.severityLow') }
    ]},
    { key: 'dimension_r18', label: $_('governance.dimensionR18'), type: 'select', options: Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `${i + 1}` })) },
  ]);

  // "Detectado por" renders as a compact badge that distinguishes auto-emitted
  // incidents (post-silver DQX job) from incidents created manually from
  // Críticas SCR. See docs/spec/08_dqx_app_integration.md §4.1 / §4.2.
  function renderDetectedBy(v) {
    if (!v) return '<span class="inline-badge badge-neutral">-</span>';
    if (v === 'dqx:auto-emit' || v === 'system@dqx-pipeline' || v === 'dlt-pipeline') {
      return `<span class="inline-badge badge-info" title="${$_('governance.detectedByAutoTitle')}">DQX auto</span>`;
    }
    if (v.startsWith('manual:')) {
      const email = v.slice('manual:'.length);
      return `<span class="inline-badge badge-neutral" title="${$_('governance.detectedByManualTitle', { values: { email } })}">${$_('governance.detectedByManualLabel')} · ${email}</span>`;
    }
    return `<span class="inline-badge badge-neutral">${v}</span>`;
  }

  // "Regra DQX" links to DQX Studio when the row carries a check_name + studio_url.
  function renderDqxCheck(_v, row) {
    const name = row?.dqx_check_name;
    if (!name) return '<span class="muted-cell">-</span>';
    const safeName = String(name).replace(/</g, '&lt;');
    if (row?.studio_url) {
      const safeUrl = String(row.studio_url).replace(/"/g, '&quot;');
      return `<a class="dqx-link" href="${safeUrl}" target="_blank" rel="noopener noreferrer" title="${$_('governance.openInDqxStudio')}">${safeName} <span class="dqx-arrow">&#8599;</span></a>`;
    }
    return `<span class="muted-cell">${safeName}</span>`;
  }

  const incidentColumns = $derived.by(() => [
    { key: 'id', label: $_('governance.colId'), sortable: true, width: '160px' },
    { key: 'detected_at', label: $_('governance.colDetected'), sortable: true, width: '160px', render: (v) => formatDateTime(v) },
    { key: 'detected_by', label: $_('governance.colDetectedBy'), sortable: true, width: '180px', render: renderDetectedBy },
    { key: 'dqx_check_name', label: $_('governance.colDqxRule'), sortable: true, width: '220px', render: renderDqxCheck },
    { key: 'document', label: $_('governance.colDoc'), sortable: true, width: '60px' },
    { key: 'dimension_name', label: $_('governance.dimension'), sortable: true, width: '120px' },
    { key: 'severity', label: $_('governance.severity'), sortable: true, width: '100px', render: (v) => {
      const s = SEVERITY_MAP[v] || { label: v, variant: 'neutral' };
      return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`;
    }},
    { key: 'status', label: $_('common.status'), sortable: true, width: '120px', render: (v) => {
      const s = STATUS_MAP[v] || { label: v, variant: 'neutral' };
      return `<span class="inline-badge badge-${s.variant}">${s.label}</span>`;
    }},
    { key: 'owner', label: $_('governance.responsible'), sortable: true },
  ]);

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

  async function openDetail(row) {
    try {
      const data = await getIrregularityDetail(row.id);
      selectedIncident = data.irregularity;
    } catch {
      selectedIncident = row;
    }
    showDetailModal = true;
  }

  async function openDetailById(id) {
    try {
      const data = await getIrregularityDetail(id);
      selectedIncident = data.irregularity;
      showDetailModal = true;
    } catch { /* swallow — bad ID just leaves modal closed */ }
  }

  // --- FSM transitions (simplificada) ---
  // 4 estados: Aberto → Em Andamento → Resolvido (+ Reaberto como escape).
  // Removidos: assigned, escalated, validated — o fluxo ficou confuso com
  // tantas opções; melhor um ciclo linear claro com reabertura possível.
  const FSM_TRANSITIONS = {
    open:        ['in_progress', 'resolved'],
    in_progress: ['resolved'],
    resolved:    ['reopened'],
    reopened:    ['in_progress', 'resolved'],
  };
  // Metadata para cada ação: rótulo PT-BR, ícone (SVG path) e variante de cor.
  // Usado pra renderizar os botões coloridos do action panel.
  const TRANSITION_META = $derived.by(() => ({
    in_progress: {
      label: $_('governance.transitionTakeLabel'),
      hint:  $_('governance.transitionTakeHint'),
      // Person/check icon
      icon:  'M16 11c1.66 0 3-1.34 3-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 3-1.34 3-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z',
      variant: 'primary',
    },
    resolved: {
      label: $_('governance.transitionResolveLabel'),
      hint:  $_('governance.transitionResolveHint'),
      // Check-circle
      icon:  'M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z',
      variant: 'success',
    },
    reopened: {
      label: $_('governance.transitionReopenLabel'),
      hint:  $_('governance.transitionReopenHint'),
      // Refresh arrows
      icon:  'M17.65 6.35A7.958 7.958 0 0012 4a8 8 0 00-7.93 7H2l3.89 3.89.07.14L10 11H7c0-2.76 2.24-5 5-5s5 2.24 5 5-2.24 5-5 5c-1.92 0-3.58-1.09-4.43-2.67l-1.46 1.49C7.16 17.32 9.39 19 12 19a8 8 0 000-16c-2.21 0-4.21.9-5.65 2.35z',
      variant: 'warning',
    },
  }));
  let transitionLoading = $state(false);
  let transitionError = $state('');
  // Comentário compartilhado entre os botões — capturado quando o usuário
  // clica em qualquer ação. Limpa após sucesso.
  let actionComment = $state('');

  function availableTransitions(status) {
    return FSM_TRANSITIONS[status] || [];
  }

  async function transitionIncident(target) {
    if (!selectedIncident) return;
    transitionLoading = true;
    transitionError = '';
    try {
      const payload = { status: target };
      const trimmed = (actionComment || '').trim();
      if (trimmed) payload.comment = trimmed;
      const updated = await updateIncidentStatus(selectedIncident.id, payload);
      selectedIncident = updated;
      // Refresh the row in the table so the list reflects the new status.
      irregularities = irregularities.map(r => r.id === updated.id ? updated : r);
      actionComment = '';
    } catch (err) {
      transitionError = err?.message || $_('governance.transitionError');
    } finally {
      transitionLoading = false;
    }
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
    // Deep-link: when Críticas SCR teammate redirects here after creating an
    // incident, auto-open the detail modal for that ID (spec 08 §4.4 linkback).
    try {
      const url = new URL(window.location.href);
      const deepLink = url.searchParams.get('incident');
      if (deepLink) openDetailById(deepLink);
    } catch { /* SSR / no window — ignore */ }
  });

  $effect(() => {
    void filterValues;
    loadIrregularities();
  });
</script>

<div class="governance-page">
    <!-- KPI Cards -->
    <div class="kpi-grid">
      <KpiCard title={$_('governance.kpiOpen')} value={summary.total_open} status="error" />
      <KpiCard title={$_('governance.kpiInProgress')} value={summary.total_in_progress} status="warning" />
      <KpiCard title={$_('governance.kpiResolved')} value={summary.total_resolved} status="success" />
      <KpiCard title={$_('governance.kpiAvgResolution')} value={summary.avg_resolution_days} unit={$_('governance.daysUnit')} status="info" />
    </div>

    <FilterBar filters={filterDefs} values={filterValues} onchange={handleFilter} onreset={resetFilters} />

    {#if loading}
      <Spinner message={$_('governance.loadingIncidents')} />
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
                <p><strong>{$_('governance.descriptionLabel')}</strong> {row.description}</p>
                {#if row.root_cause}<p><strong>{$_('governance.rootCauseLabel')}</strong> {row.root_cause}</p>{/if}
                {#if row.remedial_action}<p><strong>{$_('governance.remedialActionLabel')}</strong> {row.remedial_action}</p>{/if}
                {#if row.impact}<p><strong>{$_('governance.impactLabel')}</strong> {row.impact}</p>{/if}
              </div>
              <div class="expand-lifecycle">
                <strong>{$_('governance.lifecycleLabel')}</strong>
                <div class="lifecycle-grid">
                  <div class="lifecycle-item">
                    <span class="lifecycle-label">{$_('governance.colDetectedBy')}</span>
                    <span class="lifecycle-value">{row.detected_by || '-'}</span>
                  </div>
                  <div class="lifecycle-item">
                    <span class="lifecycle-label">{$_('governance.respondedBy')}</span>
                    <span class="lifecycle-value">{row.responded_by || '-'}</span>
                  </div>
                  <div class="lifecycle-item">
                    <span class="lifecycle-label">{$_('governance.validatedBy')}</span>
                    <span class="lifecycle-value">{row.validated_by || '-'}</span>
                  </div>
                  {#if row.escalated_by}
                    <div class="lifecycle-item">
                      <span class="lifecycle-label">{$_('governance.escalatedBy')}</span>
                      <span class="lifecycle-value">{row.escalated_by}</span>
                    </div>
                  {/if}
                </div>
              </div>
              <button class="btn-detail" onclick={() => openDetail(row)}>{$_('governance.viewFullTimeline')}</button>
            </div>
          {/snippet}
        </DataTable>
      </div>
    {/if}

    <!-- Detail Modal -->
    <Modal open={showDetailModal} title={selectedIncident?.id || ''} onclose={() => { showDetailModal = false; transitionError = ''; }}>
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

          {#if selectedIncident.dqx_check_name || selectedIncident.critica_id}
            <div class="detail-dqx">
              {#if selectedIncident.critica_id}
                <span class="dqx-chip"><strong>{$_('governance.criticaLabel')}</strong> {selectedIncident.critica_id}</span>
              {/if}
              {#if selectedIncident.run_config_name}
                <span class="dqx-chip"><strong>{$_('governance.runConfigLabel')}</strong> {selectedIncident.run_config_name}</span>
              {/if}
              {#if selectedIncident.dqx_check_name}
                {#if selectedIncident.studio_url}
                  <a class="dqx-chip-link" href={selectedIncident.studio_url} target="_blank" rel="noopener noreferrer">
                    <strong>{$_('governance.dqxRuleLabel')}</strong> {selectedIncident.dqx_check_name} <span class="dqx-arrow">↗</span>
                  </a>
                {:else}
                  <span class="dqx-chip"><strong>{$_('governance.dqxRuleLabel')}</strong> {selectedIncident.dqx_check_name}</span>
                {/if}
              {/if}
              {#if selectedIncident.affected_records != null}
                <span class="dqx-chip"><strong>{$_('governance.affectedRecordsLabel')}</strong> {selectedIncident.affected_records}</span>
              {/if}
            </div>
          {/if}

          <p class="detail-desc">{selectedIncident.description}</p>

          <!-- Action panel: comentário + botões de transição com ícones -->
          {#if availableTransitions(selectedIncident.status).length}
            <div class="action-panel">
              <label class="action-panel-header" for="incident-comment">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>
                </svg>
                <span>{$_('governance.commentLabel')} <span class="optional-tag">{$_('governance.optionalTag')}</span></span>
              </label>
              <textarea
                id="incident-comment"
                class="action-comment"
                placeholder={$_('governance.commentPlaceholder')}
                rows="2"
                bind:value={actionComment}
                disabled={transitionLoading}
              ></textarea>
              <div class="action-buttons">
                {#each availableTransitions(selectedIncident.status) as target}
                  {@const meta = TRANSITION_META[target] || { label: target, hint: '', icon: '', variant: 'primary' }}
                  <button
                    type="button"
                    class="btn-action btn-action-{meta.variant}"
                    disabled={transitionLoading}
                    title={meta.hint}
                    onclick={() => transitionIncident(target)}
                  >
                    {#if meta.icon}
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d={meta.icon} />
                      </svg>
                    {/if}
                    <span class="btn-action-label">{meta.label}</span>
                  </button>
                {/each}
              </div>
              {#if transitionLoading}
                <div class="action-status">{$_('governance.updatingIncident')}</div>
              {/if}
              {#if transitionError}
                <div class="action-error">{transitionError}</div>
              {/if}
            </div>
          {/if}

          {#if selectedIncident.timeline?.length}
            <h4 class="timeline-title">{$_('governance.incidentTimeline')}</h4>
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

        </div>
      {/if}
    </Modal>
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
  .timeline-title {
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

  @media (max-width: 900px) {
    .kpi-grid {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  /* DQX / transition UI (post Phase-7) */
  :global(.dqx-link) {
    color: var(--primary);
    font-weight: 600;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: var(--font-size-xs);
  }
  :global(.dqx-link:hover) { text-decoration: underline; }
  :global(.dqx-arrow) {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
  }
  :global(.muted-cell) {
    color: var(--gray-400);
    font-size: var(--font-size-xs);
  }

  .detail-dqx {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    padding: var(--space-2);
    background: var(--gray-50);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-color);
  }
  .dqx-chip, .dqx-chip-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px var(--space-2);
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    color: var(--gray-700);
  }
  .dqx-chip-link {
    color: var(--primary);
    text-decoration: none;
  }
  .dqx-chip-link:hover { text-decoration: underline; }
  .dqx-chip strong, .dqx-chip-link strong {
    color: var(--gray-500);
    font-weight: 600;
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.04em;
  }

  /* Action panel — input de comentário + botões coloridos de transição */
  .action-panel {
    margin-top: var(--space-3);
    padding: var(--space-4);
    background: var(--gray-50, #f8f9fa);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .action-panel-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--gray-700);
  }
  .action-panel-header svg { color: var(--gray-500); }
  .optional-tag {
    font-weight: 400;
    color: var(--gray-500);
    font-size: var(--font-size-xs);
  }
  .action-comment {
    width: 100%;
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-family: inherit;
    font-size: var(--font-size-sm);
    color: var(--gray-900);
    resize: vertical;
    min-height: 60px;
    background: var(--white);
    transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  }
  .action-comment:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(255, 51, 102, 0.08);
  }
  .action-comment:disabled { opacity: 0.6; cursor: not-allowed; }

  .action-buttons {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .btn-action {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    border: none;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    font-weight: 700;
    cursor: pointer;
    color: white;
    transition: filter var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
  }
  .btn-action:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); box-shadow: 0 3px 6px rgba(0,0,0,0.12); }
  .btn-action:active:not(:disabled) { transform: translateY(0); }
  .btn-action:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-action svg { flex-shrink: 0; }
  .btn-action-label { line-height: 1; }

  /* Variantes de cor — cada ação tem semântica clara */
  .btn-action-primary  { background: var(--primary, #2563eb); }
  .btn-action-success  { background: var(--success, #16a34a); }
  .btn-action-warning  { background: var(--warning, #d97706); color: white; }
  .btn-action-danger   { background: var(--error, #dc2626); }

  .action-status {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    font-style: italic;
  }
  .action-error {
    padding: var(--space-2) var(--space-3);
    background: var(--error-light);
    color: var(--error);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    border-left: 3px solid var(--error);
  }
</style>
