<script>
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import BindingModal from '$lib/components/domain/BindingModal.svelte';
  import {
    getRuleEngineDataset, getRuleEngineDatasetColumns,
    getDatasetBindings, createBinding, deleteBinding,
    getRuleEngineRules, triggerRuleEngineRun, getRuleEngineRuns
  } from '$lib/api.js';
  import { resolveExpression, structuredToExpression } from '$lib/ruleEngine.js';

  const datasetId = $derived($page.params.id);

  let activeTab = $state('colunas');
  const tabs = [
    { key: 'colunas', label: 'Colunas' },
    { key: 'bindings', label: 'Regras Vinculadas' },
    { key: 'execucoes', label: 'Execucoes' }
  ];

  // Dataset info
  let dataset = $state({ dataset_id: '', name: 'Carregando...', source_path: '', layer: '', row_count_approx: 0 });
  let columns = $state([]);
  let bindings = $state([]);
  let allRules = $state([]);
  let runs = $state([]);

  // Modals
  let showBindingModal = $state(false);
  let showRunModal = $state(false);
  let runInProgress = $state(false);
  let lastTriggeredRunId = $state(null);

  // KPIs
  let totalColumns = $derived(columns.length);
  let totalBindings = $derived(bindings.length);
  let lastRun = $derived(runs.length > 0 ? runs[0] : null);
  let passRate = $derived.by(() => {
    if (!lastRun || lastRun.status !== 'completed') return null;
    return lastRun.total_rules > 0 ? Math.round((lastRun.total_rules - (lastRun.total_rules - (lastRun.total_records || 0))) / lastRun.total_rules * 100) : null;
  });

  // Column table
  const columnDefs = [
    { key: 'name', label: 'Nome', sortable: true, render: (v) => `<span style="font-family:var(--font-mono);font-size:var(--font-size-sm)">${v}</span>` },
    { key: 'type', label: 'Tipo', sortable: true, width: '120px' },
    { key: 'nullable', label: 'Nulavel', width: '80px', render: (v) => v ? 'Sim' : 'Nao' },
    { key: 'description', label: 'Descricao', render: (v) => v || '<span style="color:var(--gray-400)">-</span>' }
  ];

  // Binding table
  const bindingDefs = [
    { key: 'rule_name', label: 'Regra', sortable: true },
    { key: 'column_bindings', label: 'Colunas Vinculadas', render: (v) => Object.entries(v || {}).map(([k, c]) => `${k} → ${c}`).join(', ') },
    { key: 'override_severity', label: 'Sev.', width: '80px', render: (v, row) => {
      const sev = v || allRules.find(r => r.rule_id === row.rule_id)?.severity || '-';
      return `<span class="sev-${sev}">${sev}</span>`;
    }},
    { key: 'is_active', label: 'Status', width: '80px', render: (v) => v ? '<span style="color:var(--success)">Ativa</span>' : '<span style="color:var(--gray-400)">Inativa</span>' },
    { key: 'binding_id', label: '', width: '60px', render: () => '<span class="delete-hint">Remover</span>' }
  ];

  // Runs table
  const runDefs = [
    { key: 'run_id', label: 'Run ID', width: '110px', render: (v) => `<span style="font-family:var(--font-mono);font-size:var(--font-size-xs)">${v}</span>` },
    { key: 'triggered_at', label: 'Data', sortable: true, width: '140px', render: (v) => v ? v.slice(0, 16).replace('T', ' ') : '-' },
    { key: 'status', label: 'Status', width: '100px', render: (v) => {
      const cls = v === 'completed' ? 'success' : v === 'failed' ? 'error' : v === 'running' ? 'info' : 'neutral';
      return `<span class="sev-${cls === 'success' ? 'success' : cls === 'error' ? 'error' : 'info'}">${v}</span>`;
    }},
    { key: 'total_rules', label: 'Regras', width: '70px' },
    { key: 'total_records', label: 'Registros', width: '100px', render: (v) => v ? v.toLocaleString('pt-BR') : '-' },
    { key: 'duration_seconds', label: 'Duracao', width: '80px', render: (v) => v ? `${v}s` : '-' }
  ];

  async function handleBindingSave(binding) {
    try {
      const created = await createBinding(datasetId, binding);
      if (created) bindings = [...bindings, created];
    } catch { /* mock */ }
    showBindingModal = false;
  }

  async function handleDeleteBinding(row) {
    try {
      await deleteBinding(datasetId, row.binding_id);
    } catch { /* mock */ }
    bindings = bindings.filter(b => b.binding_id !== row.binding_id);
  }

  async function handleTriggerRun() {
    showRunModal = true;
    runInProgress = true;
    try {
      const result = await triggerRuleEngineRun(datasetId);
      await loadRuns();
      // Store the new run_id so the "Ver Resultados" button works
      lastTriggeredRunId = result?.run_id || (runs.length ? runs[0].run_id : null);
    } catch { /* mock */ }
    runInProgress = false;
  }

  async function loadBindings() {
    try {
      const data = await getDatasetBindings(datasetId);
      if (data?.bindings) bindings = data.bindings;
    } catch { /* mock */ }
  }

  async function loadRuns() {
    try {
      const data = await getRuleEngineRuns({ dataset_id: datasetId });
      if (data?.runs) runs = data.runs;
    } catch { /* mock */ }
  }

  onMount(async () => {
    // Fetch each independently so one failure doesn't block the rest
    const results = await Promise.allSettled([
      getRuleEngineDataset(datasetId),
      getRuleEngineDatasetColumns(datasetId),
      getDatasetBindings(datasetId),
      getRuleEngineRules(),
      getRuleEngineRuns({ dataset_id: datasetId })
    ]);
    const [dsDetail, colData, bindData, rulesData, runsData] = results.map(r => r.status === 'fulfilled' ? r.value : null);
    if (dsDetail?.dataset) dataset = dsDetail.dataset;
    if (colData?.columns) columns = colData.columns;
    if (bindData?.bindings) bindings = bindData.bindings;
    if (rulesData?.rules) allRules = rulesData.rules;
    if (runsData?.runs) runs = runsData.runs;
  });
</script>

<div class="dataset-detail">
  <PageHeader breadcrumbs={[
    { label: 'Motor de Regras', href: '/rules' },
    { label: dataset.name }
  ]} />

  <!-- Dataset Header -->
  <div class="card ds-header-card">
    <div class="ds-title-row">
      <div>
        <h2>{dataset.name}</h2>
        <span class="ds-table">{dataset.source_path}</span>
      </div>
      <Badge label={dataset.tipo === 'table' ? 'Tabela' : 'Arquivo'} variant={dataset.tipo === 'table' ? 'info' : 'warning'} />
    </div>
  </div>

  <!-- KPIs -->
  <div class="kpi-row">
    <KpiCard title="Colunas" value={totalColumns} status="info" />
    <KpiCard title="Regras Vinculadas" value={totalBindings} status={totalBindings > 0 ? 'success' : 'neutral'} />
    <KpiCard title="Registros" value={dataset.row_count_approx ? (dataset.row_count_approx / 1000000).toFixed(1) + 'M' : '-'} status="info" />
    <KpiCard title="Ultima Execucao" value={lastRun ? lastRun.status : 'N/A'} status={lastRun?.status === 'completed' ? 'success' : lastRun?.status === 'failed' ? 'error' : 'neutral'} />
  </div>

  <Tabs {tabs} active={activeTab} onchange={(k) => activeTab = k} />

  {#if activeTab === 'colunas'}
    <div class="card">
      <DataTable columns={columnDefs} data={columns} emptyMessage="Nenhuma coluna encontrada" />
    </div>

  {:else if activeTab === 'bindings'}
    <div class="section-header">
      <span class="section-count">{bindings.length} regras vinculadas</span>
      <button class="btn-primary" onclick={() => showBindingModal = true}>+ Vincular Regra</button>
    </div>
    <div class="card">
      <DataTable
        columns={bindingDefs}
        data={bindings}
        onRowClick={(row) => {
          if (confirm(`Remover vinculacao "${row.rule_name}"?`)) handleDeleteBinding(row);
        }}
        emptyMessage="Nenhuma regra vinculada. Clique em '+ Vincular Regra' para comecar."
      />
    </div>

    <BindingModal
      open={showBindingModal}
      rules={allRules}
      {columns}
      onclose={() => showBindingModal = false}
      onsave={handleBindingSave}
    />

  {:else}
    <div class="section-header">
      <span class="section-count">{runs.length} execucoes</span>
      <button class="btn-primary" onclick={handleTriggerRun} disabled={totalBindings === 0}>
        Executar Validacao
      </button>
    </div>
    <div class="card">
      <DataTable
        columns={runDefs}
        data={runs}
        onRowClick={(row) => goto(`/rules/results/${row.run_id}`)}
        emptyMessage="Nenhuma execucao registrada. Vincule regras e clique em 'Executar Validacao'."
      />
    </div>

    <Modal open={showRunModal} title="Executar Validacao" onclose={() => showRunModal = false}>
      {#if runInProgress}
        <Spinner message="Executando validacao no dataset..." />
      {:else}
        <div class="run-done">
          <p>Validacao concluida.</p>
          <button class="btn-primary" onclick={() => { showRunModal = false; const rid = lastTriggeredRunId || (runs.length ? runs[0].run_id : null); if (rid) goto(`/rules/results/${rid}`); }}>Ver Resultados</button>
        </div>
      {/if}
    </Modal>
  {/if}
</div>

<style>
  .dataset-detail { display: flex; flex-direction: column; gap: var(--space-4); }

  .ds-header-card { padding: var(--space-5); }
  .ds-title-row { display: flex; align-items: flex-start; justify-content: space-between; }
  .ds-title-row h2 { margin: 0; font-size: var(--font-size-xl); }
  .ds-table { font-family: var(--font-mono); font-size: var(--font-size-sm); color: var(--gray-500); }

  .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-4); }

  .section-header { display: flex; align-items: center; justify-content: space-between; }
  .section-count { font-size: var(--font-size-sm); color: var(--gray-500); }

  .btn-primary {
    padding: var(--space-2) var(--space-5); background: var(--primary);
    color: white; border: none; border-radius: var(--radius-sm);
    font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }
  .btn-primary:hover { background: var(--blue-500); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

  .run-done { text-align: center; padding: var(--space-4); }

  :global(.delete-hint) { color: var(--error); font-size: var(--font-size-xs); cursor: pointer; }
  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-success) { color: var(--success); font-weight: 600; }
  :global(.sev-info) { color: var(--info); font-weight: 600; }

  @media (max-width: 900px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
  }
</style>
