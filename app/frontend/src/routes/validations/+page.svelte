<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Pagination from '$lib/components/data/Pagination.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import { getValidationResults, createIncident, ApiError } from '$lib/api.js';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  let activeTab = $state('3040');
  const tabs = [
    { key: '3040', label: 'SCR 3040' },
    { key: '3050', label: 'SCR 3050' }
  ];

  const NIVEL_LABELS = {
    1: { label: 'Nível 1', subtitle: 'Verificações genéricas básicas', desc: 'Completude, Unicidade, Formatos, Privacidade', color: 'var(--primary)' },
    2: { label: 'Nível 2', subtitle: 'Coerência com meses anteriores', desc: 'Comparação temporal entre arquivos consecutivos', color: 'var(--warning)' },
    3: { label: 'Nível 3', subtitle: 'Regras negociais', desc: 'Definidas pelo Curador de Dados / Gestor da Informação', color: 'var(--error)' },
  };

  let runSummary = $state({ run_id: '', run_completed_at: '', total_rules: 0, passed: 0, failed: 0, warnings: 0, pass_rate_pct: 0 });
  let results = $state([]);
  let studioUrl = $state(null);
  let activeNivel = $state(null); // null = all levels

  let filterValues = $state({});
  let currentPage = $state(1);
  let totalPages = $state(1);
  let expandedRow = $state(null);

  // Per-row inflight tracking so the button can show a spinner and prevent
  // double-submits without forcing a full results refetch.
  let incidentPending = $state({}); // { [rule_id]: true }
  // Toast UI state. We don't depend on a global toast lib — small inline
  // component below renders a single transient message.
  let toast = $state(null); // { kind: 'success' | 'error' | 'info', message, href, hrefLabel } | null
  let toastTimer = null;

  const filterDefs = [
    { key: 'severity', label: 'Bloqueio', type: 'select', options: [{ value: 'error', label: 'Bloqueante' }, { value: 'warning', label: 'Alerta' }, { value: 'info', label: 'Info' }] },
    { key: 'rule_type', label: 'Tipo', type: 'select', options: [{ value: 'syntactic', label: 'Sintática' }, { value: 'semantic', label: 'Semântica' }, { value: 'inter_document', label: 'Inter-documento' }, { value: 'business', label: 'Regra Negocial' }] },
    { key: 'dimension_r18', label: 'Dimensão R.18', type: 'select', options: Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `${i + 1}` })) },
    { key: 'modality', label: 'Modalidade', type: 'text', placeholder: 'Ex: 0201' }
  ];

  // Two distinct visual concepts:
  //   • Severidade — PROPERTY of the rule (Bloqueante/Alerta) → neutral chip.
  //   • Status     — RESULT of last run (Aprovado/Reprovado/Atenção) → colored
  //     status badge with icon. Status drives the row's emphasis; severity is
  //     informational and only matters when reading "WHY does it block?".
  const columns = [
    { key: 'rule_id', label: 'Regra', sortable: true, width: '100px' },
    { key: 'rule_name', label: 'Descrição', sortable: true },
    { key: 'nivel_verificacao', label: 'Nível', sortable: true, width: '80px', render: (v) => `<span class="nivel-badge nivel-${v}">N${v}</span>` },
    { key: 'dimension_name', label: 'Dimensão R.18', sortable: true, width: '120px' },
    { key: 'severity', label: 'Bloqueio', sortable: true, width: '100px',
      render: (v) => {
        const label = v === 'error' ? 'Bloqueante' : v === 'warning' ? 'Alerta' : 'Info';
        return `<span class="severity-chip">${label}</span>`;
      }
    },
    { key: 'status', label: 'Status', sortable: true, width: '140px',
      render: (v) => {
        if (v === 'fail') return '<span class="status-badge status-fail">✗ Reprovado</span>';
        if (v === 'warning' || v === 'warn') return '<span class="status-badge status-warn">⚠ Atenção</span>';
        return '<span class="status-badge status-pass">✓ Aprovado</span>';
      }
    },
    // Execução: mostra "inconsistencias / registros checados" — torna explícito
    // que houve uma run e quantas linhas foram avaliadas.
    // O número de "inconsistências" é SEMPRE vermelho (mais escuro quando >0,
    // mais leve quando =0) — afinal a coluna conta problemas, não acertos.
    // A leitura "tudo OK" vem do badge ✓ Aprovado da coluna Status, não daqui.
    { key: 'affected_records', label: 'Inconsistências / Total', sortable: true, width: '160px',
      render: (v, row) => {
        const total = row?.total_records ?? 0;
        const affected = v ?? 0;
        const cls = affected > 0 ? 'inc-strong' : 'inc-muted';
        return `<span class="${cls}">${affected.toLocaleString('pt-BR')}</span> <span class="run-sep-inline">/</span> <span class="run-total">${total.toLocaleString('pt-BR')}</span>`;
      }
    }
  ];

  let filteredResults = $derived.by(() => {
    let data = results;
    if (activeNivel !== null) {
      data = data.filter(r => r.nivel_verificacao === activeNivel);
    }
    if (filterValues.severity) data = data.filter(r => r.severity === filterValues.severity);
    if (filterValues.rule_type) data = data.filter(r => r.rule_type === filterValues.rule_type);
    if (filterValues.dimension_r18) data = data.filter(r => String(r.dimension_r18) === filterValues.dimension_r18);
    return data;
  });

  let nivelCounts = $derived.by(() => {
    const counts = { 1: { total: 0, fail: 0, pass: 0, warn: 0 }, 2: { total: 0, fail: 0, pass: 0, warn: 0 }, 3: { total: 0, fail: 0, pass: 0, warn: 0 } };
    for (const r of results) {
      const nv = r.nivel_verificacao || 1;
      if (counts[nv]) {
        counts[nv].total++;
        if (r.status === 'fail') counts[nv].fail++;
        else if (r.status === 'warning' || r.status === 'warn') counts[nv].warn++;
        else counts[nv].pass++;
      }
    }
    return counts;
  });

  function handleFilter(key, value) {
    filterValues = { ...filterValues, [key]: value };
  }
  function resetFilters() {
    filterValues = {};
  }

  function showToast(t, durationMs = 5500) {
    toast = t;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast = null; }, durationMs);
  }

  function canCreateIncident(row) {
    // Botão sempre visível quando temos run_config_name e identificador da regra.
    // Quando status=pass (sem inconsistências), o caller renderiza o botão
    // disabled com tooltip para que o usuário entenda que a feature existe.
    return !!row?.run_config_name && !!(row?.critica_id || row?.rule_id);
  }

  function shouldDisableIncident(row) {
    return !(row?.affected_records > 0);
  }

  async function handleCreateIncident(row, e) {
    // Stop the row's expand toggle (button lives inside the table row).
    e?.stopPropagation?.();
    const key = row.rule_id || row.critica_id;
    if (!key || incidentPending[key]) return;
    incidentPending = { ...incidentPending, [key]: true };
    try {
      const payload = {
        critica_id: row.critica_id || row.rule_id,
        run_config_name: row.run_config_name,
        data_base: appState.dataBase,
        severity: row.severity,
        description: row.description || row.rule_name,
        check_name: row.check_name || null,
        source: 'manual'
      };
      const inc = await createIncident(payload);
      const id = inc?.id || inc?.incident_id || '';
      showToast({
        kind: 'success',
        message: id ? `Incidente ${id} criado` : 'Incidente criado',
        href: id ? `/governance?incident=${encodeURIComponent(id)}` : null,
        hrefLabel: 'Abrir'
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const existing = err.body?.existing_incident_id || err.body?.incident_id || '';
        showToast({
          kind: 'info',
          message: 'Incidente já existe para esta crítica',
          href: existing ? `/governance?incident=${encodeURIComponent(existing)}` : null,
          hrefLabel: existing ? `Ver ${existing}` : null
        });
      } else {
        showToast({ kind: 'error', message: err?.message || 'Falha ao criar incidente' });
      }
    } finally {
      const { [key]: _drop, ...rest } = incidentPending;
      incidentPending = rest;
    }
  }

  async function loadResults() {
    try {
      const data = await getValidationResults(activeTab, appState.dataBase, filterValues);
      if (data?.results) results = data.results;
      if (data?.summary) runSummary = { ...runSummary, ...data.summary, run_id: data.run_id, run_completed_at: data.run_completed_at };
      studioUrl = data?.studio_url || null;
    } catch {}
  }

  onMount(loadResults);

  $effect(() => {
    activeTab;
    loadResults();
  });
</script>

<div class="validations-page">
  <Tabs {tabs} active={activeTab} onchange={(k) => { activeTab = k; activeNivel = null; }} />

  <!-- Run Summary -->
  <div class="card run-summary">
    <div class="run-info">
      <span class="run-source">Resultados DQX Studio (última execução por tabela)</span>
      <span class="run-sep">|</span>
      <span class="run-id">Run: {runSummary.run_id ? runSummary.run_id.slice(0, 12) + '…' : '—'}</span>
      <span class="run-sep">|</span>
      <span>Concluído: {runSummary.run_completed_at?.slice(0, 16).replace('T', ' ') || '—'}</span>
      {#if studioUrl}
        <span class="run-sep">|</span>
        <a class="studio-link" href={studioUrl} target="_blank" rel="noopener noreferrer">Ver no DQX Studio ↗</a>
      {/if}
    </div>
    <div class="run-stats">
      Total: {runSummary.total_rules} regras
      <span class="run-sep">|</span>
      <span class="stat-pass">✓ {runSummary.passed} aprovadas</span>
      <span class="run-sep">|</span>
      <span class="stat-warn">⚠ {runSummary.warnings ?? 0} em atenção</span>
      <span class="run-sep">|</span>
      <span class="stat-fail">✗ {runSummary.failed} reprovadas</span>
      <span class="run-sep">|</span>
      Taxa de aprovação: <strong>{runSummary.pass_rate_pct}%</strong>
    </div>
  </div>

  <!-- Verification Levels Pyramid -->
  <div class="nivel-cards">
    {#each [3, 2, 1] as nv}
      {@const info = NIVEL_LABELS[nv]}
      {@const counts = nivelCounts[nv]}
      <button
        class="nivel-card"
        class:nivel-active={activeNivel === nv}
        style="--nivel-color: {info.color}"
        onclick={() => activeNivel = activeNivel === nv ? null : nv}
      >
        <div class="nivel-header">
          <span class="nivel-tag" style="background: {info.color}">{info.label}</span>
          <span class="nivel-subtitle">{info.subtitle}</span>
        </div>
        <div class="nivel-desc">{info.desc}</div>
        <div class="nivel-stats">
          <span>{counts.total} regras</span>
          <span class="run-sep">|</span>
          {#if counts.fail > 0}<span class="stat-fail">✗ {counts.fail} reprov.</span>{/if}
          {#if counts.warn > 0}<span class="stat-warn">⚠ {counts.warn} atenção</span>{/if}
          <span class="stat-pass">✓ {counts.pass} aprov.</span>
        </div>
      </button>
    {/each}
  </div>

  {#if activeNivel !== null}
    <div class="active-nivel-banner" style="border-left-color: {NIVEL_LABELS[activeNivel].color}">
      Mostrando: <strong>{NIVEL_LABELS[activeNivel].label} — {NIVEL_LABELS[activeNivel].subtitle}</strong>
      <button class="clear-nivel" onclick={() => activeNivel = null}>Mostrar todos</button>
    </div>
  {/if}

  <!-- Filters -->
  <FilterBar filters={filterDefs} values={filterValues} onchange={handleFilter} onreset={resetFilters} />

  <!-- Results Table -->
  <div class="card">
    <DataTable
      {columns}
      data={filteredResults}
      {expandedRow}
      onRowClick={(row, i) => expandedRow = expandedRow === i ? null : i}
      emptyMessage="Nenhum resultado de validação"
    >
      {#snippet expandSnippet(row)}
        <div class="expand-detail">
          <div class="expand-header">
            <div class="expand-title">
              <strong>{row.rule_id}</strong> — {row.rule_name}
            </div>
            {#if canCreateIncident(row)}
              {@const disabled = incidentPending[row.rule_id || row.critica_id] || shouldDisableIncident(row)}
              <button
                type="button"
                class="btn-incident"
                {disabled}
                onclick={(e) => handleCreateIncident(row, e)}
                title={shouldDisableIncident(row) ? 'Sem inconsistências nesta execução — nada a registrar' : 'Criar incidente em Gestão de Incidentes'}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                {incidentPending[row.rule_id || row.critica_id] ? 'Criando…' : 'Criar Incidente'}
              </button>
            {/if}
          </div>
          <p class="expand-desc">{row.description}</p>
          <div class="expand-dqx">
            {#if row.check_name}
              <span class="dqx-chip" title="DQX check name (expectation_name)">
                <span class="dqx-chip-label">DQX check</span>
                <code>{row.check_name}</code>
              </span>
            {/if}
            {#if row.dqx_check_function}
              <span class="dqx-chip" title="DQX check function">
                <span class="dqx-chip-label">função</span>
                <code>{row.dqx_check_function}</code>
              </span>
            {/if}
            {#if row.run_config_name}
              <span class="dqx-chip" title="DQX run_config_name (dataset binding)">
                <span class="dqx-chip-label">dataset</span>
                <code>{row.run_config_name}</code>
              </span>
            {/if}
            {#if row.dqx_check_url}
              <a class="studio-link" href={row.dqx_check_url} target="_blank" rel="noopener noreferrer">Editar regra no DQX Studio ↗</a>
            {/if}
          </div>
          <p class="expand-meta">
            <span class="nivel-badge nivel-{row.nivel_verificacao}">Nível {row.nivel_verificacao}</span>
            Dimensão R.18: {row.dimension_r18} ({row.dimension_name}) | Registros afetados: {row.affected_records?.toLocaleString('pt-BR')}
          </p>
        </div>
      {/snippet}
    </DataTable>
    <Pagination page={currentPage} {totalPages} onchange={(p) => currentPage = p} />
  </div>
</div>

{#if toast}
  <div class="toast toast-{toast.kind}" role="status" aria-live="polite">
    <span class="toast-msg">{toast.message}</span>
    {#if toast.href}
      <button type="button" class="toast-link" onclick={() => { const h = toast.href; toast = null; goto(h); }}>
        {toast.hrefLabel || 'Abrir'}
      </button>
    {/if}
    <button type="button" class="toast-close" aria-label="Fechar" onclick={() => toast = null}>×</button>
  </div>
{/if}

<style>
  .validations-page { display: flex; flex-direction: column; gap: var(--space-4); }
  .run-summary {
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: var(--space-3);
  }
  .run-info { font-size: var(--font-size-sm); color: var(--gray-500); display: flex; align-items: center; flex-wrap: wrap; }
  .run-source { color: var(--primary); font-weight: 600; }
  .run-id { font-family: var(--font-mono); }
  .run-sep { color: var(--gray-300); margin: 0 var(--space-2); }
  .run-stats { font-size: var(--font-size-sm); color: var(--gray-700); }
  .stat-pass { color: var(--success); font-weight: 600; }
  .stat-warn { color: var(--warning); font-weight: 600; }
  .stat-fail { color: var(--error); font-weight: 600; }
  .studio-link {
    color: var(--primary);
    font-weight: 600;
    text-decoration: none;
    font-size: var(--font-size-sm);
  }
  .studio-link:hover { text-decoration: underline; }

  /* Nivel Cards (Pyramid layout - N3 on top, N1 on bottom) */
  .nivel-cards {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: var(--space-3);
  }
  .nivel-card {
    background: var(--white);
    border: 2px solid var(--gray-200);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    cursor: pointer;
    transition: all 0.2s ease;
    text-align: left;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .nivel-card:hover {
    border-color: var(--nivel-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  }
  .nivel-card.nivel-active {
    border-color: var(--nivel-color);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--nivel-color) 20%, transparent);
  }
  .nivel-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .nivel-tag {
    color: white;
    font-size: var(--font-size-xs);
    font-weight: 700;
    padding: 2px 8px;
    border-radius: var(--radius-sm);
  }
  .nivel-subtitle {
    font-weight: 600;
    font-size: var(--font-size-sm);
    color: var(--gray-800);
  }
  .nivel-desc {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    line-height: 1.4;
  }
  .nivel-stats {
    font-size: var(--font-size-xs);
    color: var(--gray-600);
    display: flex;
    align-items: center;
    gap: var(--space-1);
    flex-wrap: wrap;
  }

  .active-nivel-banner {
    background: var(--gray-50);
    border-left: 4px solid;
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .clear-nivel {
    background: none;
    border: none;
    color: var(--primary);
    font-weight: 600;
    font-size: var(--font-size-sm);
    cursor: pointer;
    text-decoration: underline;
  }

  /* Nivel badges in table */
  :global(.nivel-badge) {
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 3px;
    color: white;
    margin-right: var(--space-1);
  }
  :global(.nivel-1) { background: var(--primary, #1E3A5F); }
  :global(.nivel-2) { background: var(--warning, #F59E0B); }
  :global(.nivel-3) { background: var(--error, #EF4444); }

  .expand-detail { padding: var(--space-2) 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .expand-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    flex-wrap: wrap;
  }
  .expand-title { font-size: var(--font-size-sm); color: var(--gray-800); }
  .expand-desc { font-size: var(--font-size-sm); color: var(--gray-700); margin: 0; }
  .expand-dqx {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--font-size-xs);
  }
  .dqx-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--gray-50);
    border: 1px solid var(--gray-200);
    border-radius: var(--radius-sm);
    padding: 2px var(--space-2);
    color: var(--gray-700);
  }
  .dqx-chip-label { color: var(--gray-500); text-transform: uppercase; font-size: 10px; letter-spacing: 0.04em; }
  .dqx-chip code { font-family: var(--font-mono); color: var(--gray-800); }

  .expand-meta {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin: 0;
  }

  .btn-incident {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--primary);
    color: var(--white);
    border: none;
    border-radius: var(--radius-sm);
    padding: 6px var(--space-3);
    font-size: var(--font-size-sm);
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.15s ease, opacity 0.15s ease;
  }
  .btn-incident:hover:not(:disabled) { background: var(--blue-900, #163559); }
  .btn-incident:disabled { opacity: 0.6; cursor: progress; }

  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-success) { color: var(--success); font-weight: 600; }

  /* Coluna "Inconsistências / Total" — número de inconsistências sempre em
   * tom vermelho (o nome da coluna conta problemas). >0 = vermelho forte;
   * =0 = vermelho dessaturado para sinalizar que tem dado mas sem violações. */
  :global(.inc-strong) { color: var(--error, #dc2626); font-weight: 700; }
  :global(.inc-muted)  { color: rgba(220, 38, 38, 0.45); font-weight: 600; }
  :global(.run-sep-inline) { color: var(--gray-400, #9ca3af); margin: 0 2px; }
  :global(.run-total) { color: var(--gray-600, #4b5563); font-weight: 500; }

  /* "Bloqueio" — propriedade da regra. Cinza neutro pra NÃO competir com o status. */
  :global(.severity-chip) {
    display: inline-block;
    padding: 2px 8px;
    background: var(--gray-100, #f1f3f5);
    color: var(--gray-700, #495057);
    border-radius: var(--radius-sm, 4px);
    font-size: var(--font-size-xs);
    font-weight: 600;
    border: 1px solid var(--gray-200, #e9ecef);
  }

  /* "Status" — resultado da última execução. Cor dominante (verde/vermelho/amarelo). */
  :global(.status-badge) {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: var(--font-size-xs);
    font-weight: 700;
    white-space: nowrap;
    border: 1px solid transparent;
  }
  :global(.status-badge.status-pass) {
    background: rgba(34, 197, 94, 0.12);
    color: var(--success, #16a34a);
    border-color: rgba(34, 197, 94, 0.3);
  }
  :global(.status-badge.status-fail) {
    background: rgba(220, 38, 38, 0.12);
    color: var(--error, #dc2626);
    border-color: rgba(220, 38, 38, 0.3);
  }
  :global(.status-badge.status-warn) {
    background: rgba(234, 179, 8, 0.15);
    color: var(--warning, #ca8a04);
    border-color: rgba(234, 179, 8, 0.35);
  }

  /* Toast */
  .toast {
    position: fixed;
    bottom: var(--space-5);
    right: var(--space-5);
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    background: var(--white);
    border-left: 4px solid var(--primary);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
    border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    min-width: 280px;
    max-width: 420px;
    font-size: var(--font-size-sm);
  }
  .toast-success { border-left-color: var(--success); }
  .toast-error { border-left-color: var(--error); }
  .toast-info { border-left-color: var(--warning); }
  .toast-msg { flex: 1; color: var(--gray-800); }
  .toast-link {
    background: none;
    border: none;
    color: var(--primary);
    font-weight: 600;
    cursor: pointer;
    text-decoration: underline;
    font-size: var(--font-size-sm);
    padding: 0;
  }
  .toast-close {
    background: none;
    border: none;
    color: var(--gray-500);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
    padding: 0 var(--space-1);
  }
</style>
