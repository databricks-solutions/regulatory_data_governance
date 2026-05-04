<script>
  import LineChart from '$lib/components/charts/LineChart.svelte';
  import DimensionCard from '$lib/components/domain/DimensionCard.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import { goto } from '$app/navigation';
  import { appState } from '$lib/stores.svelte.js';
  import { getQualityDimensions } from '$lib/api.js';
  import { onMount } from 'svelte';

  let activeTab = $state('por_dimensao');
  const tabs = [
    { key: 'por_dimensao', label: 'Por Dimensão' },
    { key: 'por_status', label: 'Por Status' },
    { key: 'tendencia', label: 'Tendência' }
  ];

  let dimensions = $state([]);

  let grouped = $derived({
    conforme: dimensions.filter(d => d.status === 'conforme'),
    atencao: dimensions.filter(d => d.status === 'atencao'),
    nao_conforme: dimensions.filter(d => d.status === 'nao_conforme')
  });

  onMount(async () => {
    try {
      const data = await getQualityDimensions(appState.dataBase);
      if (data?.dimensions) dimensions = data.dimensions;
    } catch {}
  });
</script>

<div class="quality-page">
  <Tabs {tabs} active={activeTab} onchange={(k) => activeTab = k} />

  {#if activeTab === 'por_dimensao'}
    <div class="dim-grid">
      {#each dimensions as dim}
        <DimensionCard dimension={dim} onclick={() => goto(`/quality/${dim.id}`)} />
      {/each}
    </div>
  {:else if activeTab === 'por_status'}
    {#each [['conforme','Conforme','success'], ['atencao','Atenção','warning'], ['nao_conforme','Não Conforme','error']] as [key, label, variant]}
      {#if grouped[key].length > 0}
        <div class="status-group">
          <div class="status-group-header">
            <Badge {label} {variant} /> <span class="sg-count">({grouped[key].length})</span>
          </div>
          <div class="dim-grid">
            {#each grouped[key] as dim}
              <DimensionCard dimension={dim} onclick={() => goto(`/quality/${dim.id}`)} />
            {/each}
          </div>
        </div>
      {/if}
    {/each}
  {:else}
    <div class="card trend-section">
      <div class="card-header">Tendência — Todas as Dimensões (6 meses)</div>
      {#each dimensions as dim}
        <div class="trend-row">
          <span class="trend-dim-name">{dim.id}. {dim.name}</span>
          <div class="trend-chart-small">
            <LineChart data={dim.trend} showArea={false} height={36} width={300} color={dim.status === 'nao_conforme' ? 'var(--error)' : dim.status === 'atencao' ? 'var(--warning)' : 'var(--success)'} />
          </div>
          <span class="trend-score">{dim.score.toFixed(1)}%</span>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .quality-page { display: flex; flex-direction: column; gap: var(--space-5); }
.dim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }
  .status-group { margin-bottom: var(--space-5); }
  .status-group-header { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
  .sg-count { font-size: var(--font-size-sm); color: var(--gray-500); }
  .trend-section { padding: var(--space-5); }
  .trend-row {
    display: flex; align-items: center; gap: var(--space-4);
    padding: var(--space-1) 0; border-bottom: 1px solid var(--gray-100);
  }
  .trend-dim-name { width: 160px; font-size: var(--font-size-sm); font-weight: 600; color: var(--gray-700); flex-shrink: 0; }
  .trend-chart-small { flex: 1; }
  .trend-score { width: 60px; text-align: right; font-size: var(--font-size-sm); font-weight: 700; color: var(--gray-900); }

  @media (max-width: 900px) {
    .dim-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
