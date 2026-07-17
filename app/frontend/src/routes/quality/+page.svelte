<script>
  import DimensionCard from '$lib/components/domain/DimensionCard.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import { goto } from '$app/navigation';
  import { appState } from '$lib/stores.svelte.js';
  import { getQualityDimensions } from '$lib/api.js';
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';

  let activeTab = $state('por_dimensao');
  const tabs = $derived.by(() => [
    { key: 'por_dimensao', label: $_('quality.tabByDimension') },
    { key: 'por_status', label: $_('quality.tabByStatus') }
  ]);

  let statusGroups = $derived.by(() => [
    ['conforme', $_('quality.statusConforme'), 'success'],
    ['atencao', $_('quality.statusAtencao'), 'warning'],
    ['nao_conforme', $_('quality.statusNaoConforme'), 'error'],
    ['sem_regras', $_('quality.statusSemRegras'), 'default']
  ]);

  let dimensions = $state([]);

  let grouped = $derived({
    conforme: dimensions.filter(d => d.status === 'conforme'),
    atencao: dimensions.filter(d => d.status === 'atencao'),
    nao_conforme: dimensions.filter(d => d.status === 'nao_conforme'),
    sem_regras: dimensions.filter(d => d.status === 'sem_regras')
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
    {#each statusGroups as [key, label, variant]}
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
  {/if}
</div>

<style>
  .quality-page { display: flex; flex-direction: column; gap: var(--space-5); }
  .dim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }
  .status-group { margin-bottom: var(--space-5); }
  .status-group-header { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
  .sg-count { font-size: var(--font-size-sm); color: var(--gray-500); }

  @media (max-width: 900px) {
    .dim-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
