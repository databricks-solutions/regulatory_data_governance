<script>
  import { page } from '$app/stores';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import LineChart from '$lib/components/charts/LineChart.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import { getQualityDimension } from '$lib/api.js';
  import { dimensionNames } from '$lib/theme.js';
  import { onMount } from 'svelte';

  let dimId = $derived(parseInt($page.params.dimension_id));
  let dimName = $derived(dimensionNames[dimId - 1] || `Dimensão ${dimId}`);

  let data = $state({
    dimension: { id: 1, name: '', article: '', description: '' },
    score: 0,
    target: 0,
    status: 'pendente',
    metrics: {},
    violations: [],
    trend: []
  });

  const violationColumns = [
    { key: 'rule_id', label: 'Regra', sortable: true, width: '100px' },
    { key: 'rule_description', label: 'Descrição', sortable: true },
    { key: 'severity', label: 'Severidade', sortable: true, width: '100px', render: (v) => `<span class="sev-${v}">${v}</span>` },
    { key: 'count', label: 'Registros', sortable: true, width: '100px' },
    { key: 'status', label: 'Status', sortable: true, width: '80px' }
  ];

  onMount(async () => {
    // Mock data
    data = {
      dimension: { id: dimId, code: dimensionNames[dimId - 1]?.toLowerCase() || '', name: dimName, article: `Art. 2, par. 2, ${dimId}`, description: 'Medida de qualidade conforme R.18' },
      score: 92.5,
      target: 95.0,
      status: 'atencao',
      metrics: { taxa_rejeicao_bcb_pct: 2.1, reconciliacao_pre_envio_pct: 99.8, validacao_fonte_primaria_pct: 97.5 },
      violations: [
        { rule_id: 'SEM_014', rule_description: 'IPOC componentes divergentes dos campos da operação', severity: 'error', count: 127, status: 'fail' },
        { rule_id: 'SEM_008', rule_description: 'Taxa efetiva implausível para modalidade', severity: 'warning', count: 43, status: 'warn' },
        { rule_id: 'S10_001', rule_description: 'Campos obrigatórios - Operação', severity: 'error', count: 42, status: 'fail' }
      ],
      trend: [
        { month: '2025-10', score: 85.0 }, { month: '2025-11', score: 87.0 },
        { month: '2025-12', score: 89.0 }, { month: '2026-01', score: 90.0 },
        { month: '2026-02', score: 91.0 }, { month: '2026-03', score: 92.5 }
      ]
    };

    try {
      const resp = await getQualityDimension(dimId, appState.dataBase);
      if (resp) data = resp;
    } catch { /* use mock */ }
  });

  let statusVariant = $derived(data.status === 'conforme' ? 'success' : data.status === 'atencao' ? 'warning' : 'error');
  let statusLabel = $derived(data.status === 'conforme' ? 'Conforme' : data.status === 'atencao' ? 'Atenção' : 'Não Conforme');
</script>

<div class="dim-detail">
  <PageHeader breadcrumbs={[{ label: 'Qualidade R.18', href: '/quality' }, { label: dimName }]} />

  <!-- Dimension Header -->
  <div class="card dim-header-card">
    <div class="dim-info">
      <h2>{dimId}. {dimName}</h2>
      <p class="dim-desc">{data.dimension.description}</p>
      <p class="dim-article">{data.dimension.article}</p>
    </div>
    <div class="dim-score-area">
      <div class="score-big">{data.score?.toFixed(1)}%</div>
      <div class="score-target">Meta: {data.target?.toFixed(1)}%</div>
      <Badge label={statusLabel} variant={statusVariant} />
    </div>
  </div>

  <!-- Sub-metrics -->
  <div class="metrics-row">
    {#each Object.entries(data.metrics) as [key, value]}
      <div class="card metric-card">
        <div class="metric-label">{key.replace(/_/g, ' ').replace('pct', '%')}</div>
        <div class="metric-value">{typeof value === 'number' ? value.toFixed(1) + '%' : value}</div>
      </div>
    {/each}
  </div>

  <!-- Trend Chart -->
  <div class="card">
    <div class="card-header">Tendência (6 meses)</div>
    <LineChart data={data.trend} targetValue={data.target} />
  </div>

  <!-- Violations Table -->
  <div class="card">
    <div class="card-header">Violações Associadas</div>
    <DataTable columns={violationColumns} data={data.violations} emptyMessage="Nenhuma violação encontrada" />
  </div>
</div>

<style>
  .dim-detail { display: flex; flex-direction: column; gap: var(--space-5); }
  .dim-header-card {
    display: flex; justify-content: space-between; align-items: flex-start;
  }
  .dim-info { flex: 1; }
  .dim-info h2 { margin-bottom: var(--space-2); }
  .dim-desc { font-size: var(--font-size-base); color: var(--gray-700); }
  .dim-article { font-size: var(--font-size-sm); color: var(--gray-500); margin-top: var(--space-1); }
  .dim-score-area { text-align: right; }
  .score-big { font-size: var(--font-size-2xl); font-weight: 700; }
  .score-target { font-size: var(--font-size-sm); color: var(--gray-500); margin-bottom: var(--space-2); }
  .metrics-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }
  .metric-card { text-align: center; }
  .metric-label { font-size: var(--font-size-xs); text-transform: uppercase; color: var(--gray-500); margin-bottom: var(--space-2); }
  .metric-value { font-size: var(--font-size-xl); font-weight: 700; color: var(--gray-900); }

  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-info) { color: var(--info); font-weight: 600; }
</style>
