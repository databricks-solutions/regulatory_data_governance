<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Pagination from '$lib/components/data/Pagination.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import { getValidationResults } from '$lib/api.js';
  import { onMount } from 'svelte';

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
  let activeNivel = $state(null); // null = all levels

  let filterValues = $state({});
  let currentPage = $state(1);
  let totalPages = $state(1);
  let expandedRow = $state(null);

  const filterDefs = [
    { key: 'severity', label: 'Severidade', type: 'select', options: [{ value: 'error', label: 'Error' }, { value: 'warning', label: 'Warning' }, { value: 'info', label: 'Info' }] },
    { key: 'rule_type', label: 'Tipo', type: 'select', options: [{ value: 'syntactic', label: 'Sintática' }, { value: 'semantic', label: 'Semântica' }, { value: 'inter_document', label: 'Inter-documento' }, { value: 'business', label: 'Regra Negocial' }] },
    { key: 'dimension_r18', label: 'Dimensão R.18', type: 'select', options: Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `${i + 1}` })) },
    { key: 'modality', label: 'Modalidade', type: 'text', placeholder: 'Ex: 0201' }
  ];

  const columns = [
    { key: 'rule_id', label: 'Regra', sortable: true, width: '100px' },
    { key: 'rule_name', label: 'Descrição', sortable: true },
    { key: 'nivel_verificacao', label: 'Nível', sortable: true, width: '80px', render: (v) => `<span class="nivel-badge nivel-${v}">N${v}</span>` },
    { key: 'rule_type', label: 'Tipo', sortable: true, width: '110px', render: (v) => v === 'business' ? 'Negocial' : v === 'inter_document' ? 'Inter-doc' : v === 'syntactic' ? 'Sintática' : 'Semântica' },
    { key: 'dimension_name', label: 'Dimensão R.18', sortable: true, width: '120px' },
    { key: 'severity', label: 'Sev.', sortable: true, width: '80px', render: (v) => `<span class="sev-${v}">${v}</span>` },
    { key: 'status', label: 'Status', sortable: true, width: '80px', render: (v) => v === 'fail' ? '<span class="sev-error">fail</span>' : v === 'warning' || v === 'warn' ? '<span class="sev-warning">warn</span>' : '<span class="sev-success">pass</span>' },
    { key: 'affected_records', label: 'Registros', sortable: true, width: '90px' }
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

  async function loadResults() {
    try {
      const data = await getValidationResults(activeTab, appState.dataBase, filterValues);
      if (data?.results) results = data.results;
      if (data?.summary) runSummary = { ...runSummary, ...data.summary };
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
      <span class="run-source">Resultados da pipeline DLT</span>
      <span class="run-sep">|</span>
      <span class="run-id">Run: {runSummary.run_id}</span>
      <span class="run-sep">|</span>
      <span>Concluído: {runSummary.run_completed_at?.slice(0, 16).replace('T', ' ')}</span>
    </div>
    <div class="run-stats">
      Total: {runSummary.total_rules} regras
      <span class="run-sep">|</span>
      <span class="stat-pass">{runSummary.passed} pass</span>
      <span class="run-sep">|</span>
      <span class="stat-warn">{runSummary.warnings ?? 0} warning</span>
      <span class="run-sep">|</span>
      <span class="stat-fail">{runSummary.failed} fail</span>
      <span class="run-sep">|</span>
      Pass Rate: <strong>{runSummary.pass_rate_pct}%</strong>
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
          {#if counts.fail > 0}<span class="stat-fail">{counts.fail} fail</span>{/if}
          {#if counts.warn > 0}<span class="stat-warn">{counts.warn} warn</span>{/if}
          <span class="stat-pass">{counts.pass} pass</span>
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
          <p><strong>{row.rule_id}</strong> — {row.rule_name}</p>
          <p class="expand-desc">{row.description}</p>
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

  .expand-detail { padding: var(--space-2) 0; }
  .expand-desc { font-size: var(--font-size-sm); color: var(--gray-700); margin: var(--space-2) 0; }
  .expand-meta { font-size: var(--font-size-xs); color: var(--gray-500); display: flex; align-items: center; gap: var(--space-2); }

  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-success) { color: var(--success); font-weight: 600; }
</style>
