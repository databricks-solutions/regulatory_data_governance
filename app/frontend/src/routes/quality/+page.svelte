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

  let dimensions = $state([
    { id: 1, name: 'Acessibilidade', score: 95.0, target: 90, status: 'conforme', trend: [{month:'2025-10',score:80},{month:'2025-11',score:85},{month:'2025-12',score:88},{month:'2026-01',score:90},{month:'2026-02',score:92},{month:'2026-03',score:95}] },
    { id: 2, name: 'Acurácia', score: 92.5, target: 95, status: 'atencao', trend: [{month:'2025-10',score:85},{month:'2025-11',score:87},{month:'2025-12',score:89},{month:'2026-01',score:90},{month:'2026-02',score:91},{month:'2026-03',score:92.5}] },
    { id: 3, name: 'Adaptabilidade', score: 88.0, target: 85, status: 'conforme', trend: [{month:'2025-10',score:75},{month:'2025-11',score:78},{month:'2025-12',score:80},{month:'2026-01',score:83},{month:'2026-02',score:85},{month:'2026-03',score:88}] },
    { id: 4, name: 'Atualidade', score: 91.0, target: 90, status: 'conforme', trend: [{month:'2025-10',score:82},{month:'2025-11',score:84},{month:'2025-12',score:86},{month:'2026-01',score:88},{month:'2026-02',score:90},{month:'2026-03',score:91}] },
    { id: 5, name: 'Completude', score: 94.0, target: 90, status: 'conforme', trend: [{month:'2025-10',score:88},{month:'2025-11',score:89},{month:'2025-12',score:90},{month:'2026-01',score:91},{month:'2026-02',score:93},{month:'2026-03',score:94}] },
    { id: 6, name: 'Consistência', score: 89.5, target: 90, status: 'atencao', trend: [{month:'2025-10',score:78},{month:'2025-11',score:80},{month:'2025-12',score:83},{month:'2026-01',score:85},{month:'2026-02',score:87},{month:'2026-03',score:89.5}] },
    { id: 7, name: 'Confidencialidade', score: 97.0, target: 95, status: 'conforme', trend: [{month:'2025-10',score:93},{month:'2025-11',score:94},{month:'2025-12',score:95},{month:'2026-01',score:96},{month:'2026-02',score:96.5},{month:'2026-03',score:97}] },
    { id: 8, name: 'Disponibilidade', score: 96.0, target: 95, status: 'conforme', trend: [{month:'2025-10',score:90},{month:'2025-11',score:91},{month:'2025-12',score:93},{month:'2026-01',score:94},{month:'2026-02',score:95},{month:'2026-03',score:96}] },
    { id: 9, name: 'Granularidade', score: 85.0, target: 85, status: 'conforme', trend: [{month:'2025-10',score:70},{month:'2025-11',score:73},{month:'2025-12',score:76},{month:'2026-01',score:79},{month:'2026-02',score:82},{month:'2026-03',score:85}] },
    { id: 10, name: 'Rastreabilidade', score: 78.0, target: 85, status: 'nao_conforme', trend: [{month:'2025-10',score:60},{month:'2025-11',score:63},{month:'2025-12',score:67},{month:'2026-01',score:70},{month:'2026-02',score:74},{month:'2026-03',score:78}] },
    { id: 11, name: 'Relevância', score: 90.0, target: 85, status: 'conforme', trend: [{month:'2025-10',score:82},{month:'2025-11',score:84},{month:'2025-12',score:86},{month:'2026-01',score:87},{month:'2026-02',score:88},{month:'2026-03',score:90}] },
    { id: 12, name: 'Conformidade', score: 86.0, target: 90, status: 'atencao', trend: [{month:'2025-10',score:72},{month:'2025-11',score:75},{month:'2025-12',score:78},{month:'2026-01',score:81},{month:'2026-02',score:84},{month:'2026-03',score:86}] }
  ]);

  let grouped = $derived({
    conforme: dimensions.filter(d => d.status === 'conforme'),
    atencao: dimensions.filter(d => d.status === 'atencao'),
    nao_conforme: dimensions.filter(d => d.status === 'nao_conforme')
  });

  onMount(async () => {
    try {
      const data = await getQualityDimensions(appState.dataBase);
      if (data?.dimensions) dimensions = data.dimensions;
    } catch { /* use mock */ }
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
