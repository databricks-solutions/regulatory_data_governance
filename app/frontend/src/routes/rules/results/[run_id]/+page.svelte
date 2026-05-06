<script>
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Pagination from '$lib/components/data/Pagination.svelte';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import { getRuleEngineRunResults, getRuleEngineExceptions } from '$lib/api.js';

  const runId = $derived($page.params.run_id);

  let runData = $state(null);
  let results = $state([]);
  let summary = $state({ total_rules: 0, passed: 0, failed: 0, warnings: 0, pass_rate_pct: 0, total_records: 0, total_exceptions: 0 });
  let expandedResult = $state(null);

  // Exception drill-down
  let showExceptions = $state(false);
  let selectedResultId = $state(null);
  let selectedRuleName = $state('');
  let exceptions = $state([]);
  let excPage = $state(1);
  let excTotalPages = $state(1);

  const resultColumns = [
    { key: 'rule_name', label: 'Regra', sortable: true },
    { key: 'status', label: 'Status', sortable: true, width: '80px', render: (v) => v === 'pass' ? '<span class="st-pass">pass</span>' : v === 'fail' ? '<span class="st-fail">fail</span>' : `<span class="st-warn">${v}</span>` },
    { key: 'total_records', label: 'Total', width: '100px', sortable: true, render: (v) => v?.toLocaleString('pt-BR') || '-' },
    { key: 'failed_records', label: 'Falhas', width: '80px', sortable: true, render: (v) => v > 0 ? `<span class="st-fail">${v.toLocaleString('pt-BR')}</span>` : '0' },
    { key: 'pass_rate_pct', label: 'Taxa', width: '80px', sortable: true, render: (v) => `${v}%` },
    { key: 'severity', label: 'Sev.', width: '70px', render: (v) => `<span class="sev-${v}">${v}</span>` },
    { key: 'dimension_r18', label: 'Dim.', width: '50px', render: (v) => v || '-' },
    { key: 'execution_time_ms', label: 'Tempo', width: '70px', render: (v) => v ? `${v}ms` : '-' }
  ];

  const exceptionColumns = [
    { key: 'row_identifier', label: 'Identificador do Registro', render: (v) => `<span style="font-family:var(--font-mono);font-size:var(--font-size-xs)">${JSON.stringify(v)}</span>` },
    { key: 'failed_columns', label: 'Colunas', width: '120px', render: (v) => (v || []).join(', ') },
    { key: 'failure_reason', label: 'Motivo', render: (v) => v || '-' }
  ];

  let excExpandedRow = $state(null);

  async function loadExceptions(resultId, ruleName) {
    selectedResultId = resultId;
    selectedRuleName = ruleName;
    showExceptions = true;
    try {
      const data = await getRuleEngineExceptions(runId, { result_id: resultId, page: excPage, page_size: 20 });
      if (data?.exceptions) exceptions = data.exceptions;
      excTotalPages = Math.ceil((data?.total || exceptions.length) / 20) || 1;
    } catch {
      // Use results from whatever mock returns
    }
  }

  function backToResults() {
    showExceptions = false;
    selectedResultId = null;
    exceptions = [];
  }

  onMount(async () => {
    try {
      const data = await getRuleEngineRunResults(runId);
      if (data) {
        runData = data;
        results = data.results || [];
        summary = data.summary || summary;
      }
    } catch {}
  });
</script>

<div class="results-page">
  <PageHeader breadcrumbs={[
    { label: 'Motor de Regras', href: '/rules' },
    { label: runData?.dataset_name || 'Dataset', href: '/rules' },
    { label: `Execucao ${runId}` }
  ]} />

  {#if !showExceptions}
    <!-- Run Summary -->
    <div class="card run-summary">
      <div class="run-info">
        <span class="run-id">Run: {runId}</span>
        <span class="sep">|</span>
        <Badge label={runData?.status || 'completed'} variant={runData?.status === 'completed' ? 'success' : 'error'} />
        <span class="sep">|</span>
        <span>{runData?.dataset_name || 'Dataset'}</span>
      </div>
    </div>

    <!-- KPIs -->
    <div class="kpi-row">
      <KpiCard title="Total Regras" value={summary.total_rules} status="info" />
      <KpiCard title="Pass Rate" value={`${summary.pass_rate_pct}%`} status={summary.pass_rate_pct >= 90 ? 'success' : summary.pass_rate_pct >= 70 ? 'warning' : 'error'} />
      <KpiCard title="Excecoes" value={summary.total_exceptions} status={summary.total_exceptions > 0 ? 'error' : 'success'} />
      <KpiCard title="Registros" value={summary.total_records ? (summary.total_records / 1000000).toFixed(1) + 'M' : '-'} status="info" />
    </div>

    <!-- Results stats bar -->
    <div class="stats-bar">
      <span class="st-pass">{summary.passed} pass</span>
      <span class="sep">|</span>
      <span class="st-fail">{summary.failed} fail</span>
      <span class="sep">|</span>
      <span class="st-warn">{summary.warnings} warning</span>
    </div>

    <!-- Results Table -->
    <div class="card">
      <DataTable
        columns={resultColumns}
        data={results}
        expandedRow={expandedResult}
        onRowClick={(row, i) => expandedResult = expandedResult === i ? null : i}
        emptyMessage="Nenhum resultado"
      >
        {#snippet expandSnippet(row)}
          <div class="expand-detail">
            {#if row.expression_used}
              <div class="expr-preview">
                <span class="expr-label">Expressao:</span>
                <code>{row.expression_used}</code>
              </div>
            {/if}
            <div class="expand-stats">
              Total: {row.total_records?.toLocaleString('pt-BR')} |
              Passou: {row.passed_records?.toLocaleString('pt-BR')} |
              Falhou: {row.failed_records?.toLocaleString('pt-BR')}
            </div>
            {#if row.failed_records > 0}
              <button class="exceptions-btn" onclick={() => loadExceptions(row.result_id, row.rule_name)}>
                Ver {row.failed_records} Excecoes
              </button>
            {/if}
          </div>
        {/snippet}
      </DataTable>
    </div>

  {:else}
    <!-- Exception Drill-Down -->
    <div class="section-header">
      <button class="back-btn" onclick={backToResults}>&larr; Voltar aos Resultados</button>
      <span class="section-count">Excecoes: {selectedRuleName}</span>
    </div>

    <div class="card">
      <DataTable
        columns={exceptionColumns}
        data={exceptions}
        expandedRow={excExpandedRow}
        onRowClick={(row, i) => excExpandedRow = excExpandedRow === i ? null : i}
        emptyMessage="Nenhuma excecao"
      >
        {#snippet expandSnippet(row)}
          <div class="expand-detail">
            <div class="snapshot-label">Snapshot do Registro:</div>
            <pre class="snapshot">{JSON.stringify(row.row_snapshot, null, 2)}</pre>
          </div>
        {/snippet}
      </DataTable>
      <Pagination page={excPage} totalPages={excTotalPages} onchange={(p) => { excPage = p; loadExceptions(selectedResultId, selectedRuleName); }} />
    </div>
  {/if}
</div>

<style>
  .results-page { display: flex; flex-direction: column; gap: var(--space-4); }

  .run-summary { display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-3); }
  .run-info { display: flex; align-items: center; gap: var(--space-3); font-size: var(--font-size-sm); }
  .run-id { font-family: var(--font-mono); color: var(--gray-700); }
  .sep { color: var(--gray-300); }

  .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); }

  .stats-bar {
    font-size: var(--font-size-sm); color: var(--gray-700);
    display: flex; gap: var(--space-3); align-items: center;
  }

  :global(.st-pass) { color: var(--success); font-weight: 600; }
  :global(.st-fail) { color: var(--error); font-weight: 600; }
  :global(.st-warn) { color: var(--warning); font-weight: 600; }
  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }

  .expand-detail { padding: var(--space-2) 0; }
  .expr-preview { margin-bottom: var(--space-2); }
  .expr-label { font-size: var(--font-size-xs); color: var(--gray-500); font-weight: 600; }
  .expr-preview code { font-family: var(--font-mono); font-size: var(--font-size-sm); color: var(--blue-900); }
  .expand-stats { font-size: var(--font-size-sm); color: var(--gray-500); margin-bottom: var(--space-2); }

  .exceptions-btn {
    padding: var(--space-1) var(--space-4);
    background: var(--error-light); color: var(--error);
    border: 1px solid var(--error); border-radius: var(--radius-sm);
    font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }
  .exceptions-btn:hover { background: var(--error); color: white; }

  .section-header { display: flex; align-items: center; gap: var(--space-4); }
  .section-count { font-size: var(--font-size-sm); color: var(--gray-500); }
  .back-btn {
    padding: var(--space-2) var(--space-4);
    background: var(--gray-100); color: var(--gray-700);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm);
    font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }
  .back-btn:hover { background: var(--gray-300); }

  .snapshot-label { font-size: var(--font-size-xs); color: var(--gray-500); font-weight: 600; margin-bottom: var(--space-1); }
  .snapshot {
    background: var(--gray-100); padding: var(--space-3);
    border-radius: var(--radius-sm); font-family: var(--font-mono);
    font-size: var(--font-size-xs); overflow-x: auto; white-space: pre-wrap;
  }

  @media (max-width: 900px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
