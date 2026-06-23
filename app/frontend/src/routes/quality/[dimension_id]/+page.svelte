<script>
  import { page } from '$app/stores';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import LineChart from '$lib/components/charts/LineChart.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import { getQualityDimension } from '$lib/api.js';
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';

  let dimId = $derived(parseInt($page.params.dimension_id));

  // Measured width of the chart container — fed into the SVG viewBox so the
  // trend chart fills the full card width at a fixed height (no empty margins,
  // no distortion since viewBox maps 1:1 to rendered pixels).
  let chartW = $state(0);

  let data = $state({
    dimension: { id: 1, name: '', article: '', description: '' },
    score: 0,
    target: 0,
    status: 'pendente',
    metrics: {},
    violations: [],
    trend: []
  });

  // Name comes from the API response (locale-aware in mock mode) instead of a
  // hardcoded pt-BR list, so it follows the active language.
  let dimName = $derived(data.dimension?.name || $_('quality.dimensionFallback', { values: { id: dimId } }));

  // Known metric keys → i18n labels; unknown keys fall back to a prettified key.
  // Only `*_pct`/`taxa*` metrics are rendered as percentages.
  const METRIC_LABEL_KEYS = {
    taxa_conformidade_pct: 'quality.metricComplianceRate',
    registros_nao_conformes: 'quality.metricNonCompliantRecords'
  };
  function metricLabel(key) {
    return METRIC_LABEL_KEYS[key] ? $_(METRIC_LABEL_KEYS[key]) : key.replace(/_/g, ' ');
  }
  function metricValue(key, value) {
    if (typeof value !== 'number') return value;
    const isPct = key.includes('pct') || key.includes('taxa');
    return isPct ? value.toFixed(1) + '%' : Math.round(value).toLocaleString();
  }

  // At-a-glance trend summary shown next to the chart (fills the right side of
  // the wide trend card so it reads as a designed layout, not empty space).
  let trendStats = $derived.by(() => {
    const t = data.trend || [];
    if (t.length < 2) return null;
    const scores = t.map((x) => x.score);
    const latest = scores[scores.length - 1];
    return {
      latest,
      change: latest - scores[0],
      best: Math.max(...scores),
      vsTarget: latest - (data.target || 0)
    };
  });

  // Metrics other than the compliance rate (which is already shown as the big
  // headline score), rendered as secondary stats in the unified header card.
  let extraMetrics = $derived(
    Object.entries(data.metrics || {}).filter(([k]) => !(k.includes('pct') || k.includes('taxa')))
  );

  const violationColumns = $derived.by(() => [
    { key: 'rule_id', label: $_('quality.colRule'), sortable: true, width: '100px' },
    { key: 'rule_description', label: $_('quality.colDescription'), sortable: true },
    { key: 'severity', label: $_('quality.colSeverity'), sortable: true, width: '100px', render: (v) => `<span class="sev-${v}">${v}</span>` },
    { key: 'count', label: $_('quality.colRecords'), sortable: true, width: '100px' },
    { key: 'status', label: $_('common.status'), sortable: true, width: '80px' }
  ]);

  onMount(async () => {
    try {
      const resp = await getQualityDimension(dimId, appState.dataBase);
      if (resp) data = resp;
    } catch {}
  });

  let statusVariant = $derived(data.status === 'conforme' ? 'success' : data.status === 'atencao' ? 'warning' : 'error');
  let statusLabel = $derived(data.status === 'conforme' ? $_('quality.statusConforme') : data.status === 'atencao' ? $_('quality.statusAtencao') : $_('quality.statusNaoConforme'));
</script>

<div class="dim-detail">
  <PageHeader breadcrumbs={[{ label: $_('quality.breadcrumbRoot'), href: '/quality' }, { label: dimName }]} />

  <!-- Dimension header + key stats, unified into one cohesive card -->
  <div class="card dim-header-card">
    <div class="dim-info">
      <h2>{dimId}. {dimName}</h2>
      <p class="dim-desc">{data.dimension.description}</p>
      <p class="dim-article">{data.dimension.article}</p>
    </div>
    <div class="dim-stats">
      <div class="dim-stat dim-stat-main">
        <div class="dim-stat-label">{$_('quality.metricComplianceRate')}</div>
        <div class="score-big">{data.score?.toFixed(1)}%</div>
        <Badge label={statusLabel} variant={statusVariant} />
      </div>
      <div class="dim-stat">
        <div class="dim-stat-label">{$_('quality.target')}</div>
        <div class="dim-stat-value">{data.target?.toFixed(1)}%</div>
      </div>
      {#each extraMetrics as [key, value]}
        <div class="dim-stat">
          <div class="dim-stat-label">{metricLabel(key)}</div>
          <div class="dim-stat-value">{metricValue(key, value)}</div>
        </div>
      {/each}
    </div>
  </div>

  <!-- Trend Chart -->
  <div class="card">
    <div class="card-header">{$_('quality.trend6Months')}</div>
    <div class="trend-body">
      <div class="trend-chart" bind:clientWidth={chartW}>
        {#if chartW > 0}
          <LineChart data={data.trend} targetValue={data.target} width={chartW} height={280} />
        {/if}
      </div>
      {#if trendStats}
        <div class="trend-stats">
          <div class="tstat">
            <div class="tstat-label">{$_('quality.trendLatestLabel')}</div>
            <div class="tstat-value">{trendStats.latest.toFixed(1)}%</div>
          </div>
          <div class="tstat">
            <div class="tstat-label">{$_('quality.trendChangeLabel')}</div>
            <div class="tstat-value" class:pos={trendStats.change >= 0} class:neg={trendStats.change < 0}>
              {trendStats.change >= 0 ? '+' : ''}{trendStats.change.toFixed(1)} pts
            </div>
          </div>
          <div class="tstat">
            <div class="tstat-label">{$_('quality.trendBestLabel')}</div>
            <div class="tstat-value">{trendStats.best.toFixed(1)}%</div>
          </div>
          <div class="tstat">
            <div class="tstat-label">{$_('quality.trendVsTargetLabel')}</div>
            <div class="tstat-value" class:pos={trendStats.vsTarget >= 0} class:neg={trendStats.vsTarget < 0}>
              {trendStats.vsTarget >= 0 ? '+' : ''}{trendStats.vsTarget.toFixed(1)} pts
            </div>
          </div>
        </div>
      {/if}
    </div>
  </div>

  <!-- Violations Table -->
  <div class="card">
    <div class="card-header">{$_('quality.associatedViolations')}</div>
    <DataTable columns={violationColumns} data={data.violations} emptyMessage={$_('quality.noViolations')} />
  </div>
</div>

<style>
  .dim-detail { display: flex; flex-direction: column; gap: var(--space-5); }
  /* Two-column trend card: chart fills the left (its measured width feeds the
     SVG viewBox 1:1, so no distortion / dead margins), a compact summary fills
     the right so the wide card reads as designed rather than empty. */
  .trend-body { display: flex; gap: var(--space-6); align-items: stretch; }
  .trend-chart { flex: 1; min-width: 0; }
  .trend-stats {
    width: 200px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-4);
    border-left: 1px solid var(--border-color);
    padding-left: var(--space-6);
  }
  .tstat-label {
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--gray-500);
    margin-bottom: 2px;
  }
  .tstat-value { font-size: var(--font-size-xl); font-weight: 700; color: var(--gray-900); }
  .tstat-value.pos { color: var(--success); }
  .tstat-value.neg { color: var(--error); }

  @media (max-width: 900px) {
    .trend-body { flex-direction: column; }
    .trend-stats {
      width: auto;
      border-left: none;
      border-top: 1px solid var(--border-color);
      padding-left: 0;
      padding-top: var(--space-4);
      flex-direction: row;
      flex-wrap: wrap;
      gap: var(--space-5);
    }
  }
  /* Unified header: dimension identity on the left, the key stats (compliance
     rate, target, non-compliant records) grouped on the right — one cohesive
     card instead of a big header + two sparse metric cards. */
  .dim-header-card {
    display: flex; justify-content: space-between; align-items: center; gap: var(--space-8);
  }
  .dim-info { flex: 1; min-width: 0; }
  .dim-info h2 { margin-bottom: var(--space-2); }
  .dim-desc { font-size: var(--font-size-base); color: var(--gray-700); }
  .dim-article { font-size: var(--font-size-sm); color: var(--gray-500); margin-top: var(--space-1); }

  .dim-stats { display: flex; align-items: stretch; gap: var(--space-6); flex-shrink: 0; }
  .dim-stat {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: center;
    gap: var(--space-1);
    text-align: right;
  }
  .dim-stat:not(:first-child) {
    border-left: 1px solid var(--border-color);
    padding-left: var(--space-6);
  }
  .dim-stat-label {
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--gray-500);
  }
  .dim-stat-value { font-size: var(--font-size-xl); font-weight: 700; color: var(--gray-900); }
  .dim-stat-main { gap: var(--space-2); }
  .score-big { font-size: var(--font-size-2xl); font-weight: 700; color: var(--gray-900); line-height: 1.1; }

  @media (max-width: 900px) {
    .dim-header-card { flex-direction: column; align-items: stretch; gap: var(--space-5); }
    .dim-stats { justify-content: space-between; gap: var(--space-4); }
    .dim-stat:not(:first-child) { padding-left: var(--space-4); }
  }

  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-info) { color: var(--info); font-weight: 600; }
</style>
