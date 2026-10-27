<script>
  import DimensionCard from '$lib/components/domain/DimensionCard.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import PrereqAlert from '$lib/components/ui/PrereqAlert.svelte';
  import DocumentDataBases from '$lib/components/domain/DocumentDataBases.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import { goto } from '$app/navigation';
  import { appState } from '$lib/stores.svelte.js';
  import { getQualityDimensions } from '$lib/api.js';
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

  let dimensionsLoaded = $state(false);

  // As 12 dimensões vêm sempre: "nada avaliado" = TODAS sem regra vinculada.
  let nothingScored = $derived(
    dimensionsLoaded && dimensions.length > 0 && dimensions.every((d) => d.status === 'sem_regras')
  );

  // Enquanto busca, skeletons no lugar dos cards; falha vira aviso com
  // "Tentar novamente", nunca grade vazia.
  let loading = $state(true);
  let loadFailed = $state(false);
  // Só a resposta da busca mais recente é aplicada (troca rápida de mês).
  let loadSeq = 0;

  async function load() {
    const seq = ++loadSeq;
    loading = true;
    loadFailed = false;
    try {
      const data = await getQualityDimensions(appState.dataBase);
      if (seq !== loadSeq) return;
      if (data?.dimensions) dimensions = data.dimensions;
    } catch {
      if (seq === loadSeq) loadFailed = true;
    } finally {
      if (seq === loadSeq) {
        dimensionsLoaded = true;
        loading = false;
      }
    }
  }

  // Espera o layout resolver o mês de referência e recarrega quando ele muda.
  $effect(() => {
    if (!appState.dataBaseReady) return;
    appState.dataBase;
    load();
  });
</script>

<div class="quality-page">
  <Tabs {tabs} active={activeTab} onchange={(k) => activeTab = k} />

  <PrereqAlert active={nothingScored} />
  <DocumentDataBases />

  {#if loadFailed}
    <div class="card load-error" role="alert">
      <span>{$_('common.requestFailed')}</span>
      <button type="button" class="btn-secondary" onclick={load}>{$_('common.retry')}</button>
    </div>
  {:else if loading}
    <div class="dim-grid" aria-busy="true">
      {#each Array(12) as _, i (i)}
        <div class="card dim-skeleton">
          <Skeleton width="55%" />
          <Skeleton width="40%" height="1.8em" />
          <Skeleton width="70%" />
        </div>
      {/each}
    </div>
  {:else if activeTab === 'por_dimensao'}
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
  .dim-skeleton { display: flex; flex-direction: column; gap: var(--space-3); }
  .load-error { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); color: var(--error); font-size: var(--font-size-sm); }
  .btn-secondary { background: var(--white); color: var(--gray-700); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: var(--space-2) var(--space-4); font-weight: 500; font-size: var(--font-size-sm); cursor: pointer; }
  .status-group { margin-bottom: var(--space-5); }
  .status-group-header { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
  .sg-count { font-size: var(--font-size-sm); color: var(--gray-500); }

  @media (max-width: 900px) {
    .dim-grid { grid-template-columns: repeat(2, 1fr); }
  }
</style>
