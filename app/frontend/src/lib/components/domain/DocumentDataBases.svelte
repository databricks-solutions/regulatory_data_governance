<script>
  /**
   * "Data-bases avaliadas": por CADOC, a data-base do processamento que entra nas
   * visões agregadas (home, Qualidade) — o último dentro do mês de referência, ou
   * o último de todos em "Último processamento". Os sem execução na seleção
   * aparecem esmaecidos. Cada item abre o documento nas Críticas.
   */
  import { _ } from 'svelte-i18n';
  import { getValidationDocuments } from '$lib/api.js';
  import { appState } from '$lib/stores.svelte.js';
  import { formatDataBase, formatMonth } from '$lib/format.js';

  const MAX = 8;
  let documents = $state([]);
  let unprocessed = $state([]);
  let loaded = $state(false);
  let loadSeq = 0;

  async function load() {
    const seq = ++loadSeq;
    try {
      const data = await getValidationDocuments(appState.dataBase);
      if (seq !== loadSeq) return;
      documents = data?.documents || [];
      unprocessed = data?.unprocessed || [];
    } catch {} finally {
      if (seq === loadSeq) loaded = true;
    }
  }

  $effect(() => {
    if (!appState.dataBaseReady) return;
    appState.dataBase;
    load();
  });

  let items = $derived([
    ...documents.map((d) => ({ ...d, processed: true })),
    ...unprocessed.map((d) => ({ ...d, processed: false }))
  ]);
  let shown = $derived(items.slice(0, MAX));
</script>

{#if loaded && items.length > 0}
  <div class="card db-card">
    <div class="db-head">
      <span class="card-header">{$_('documentDataBases.title')}</span>
      <span class="db-hint">
        {appState.dataBase
          ? $_('documentDataBases.hintMonth', { values: { month: formatMonth(appState.dataBase, $_('header.months').split(',')) } })
          : $_('documentDataBases.hintLatest')}
      </span>
    </div>
    <div class="db-grid">
      {#each shown as d (d.documento)}
        <a
          class="db-item"
          class:off={!d.processed}
          href={`/validations?doc=${encodeURIComponent(d.documento)}`}
          title={d.nome || ''}
        >
          <span class="code">{d.documento}</span>
          {#if d.processed}
            <span class="date">{formatDataBase(d.data_base)}{d.mixed ? ' ⚠' : ''}</span>
          {:else}
            <span class="date">{$_(d.ever_processed && appState.dataBase ? 'documentPicker.noRunInMonth' : 'documentPicker.noRun')}</span>
          {/if}
          {#if d.periodicidade}<span class="period">{$_(`periodicity.${d.periodicidade}`)}</span>{/if}
        </a>
      {/each}
      {#if items.length > MAX}
        <a class="db-item more" href="/validations">
          {$_('documentDataBases.more', { values: { count: items.length - MAX } })}
        </a>
      {/if}
    </div>
  </div>
{/if}

<style>
  .db-card { padding: var(--space-4); }
  .db-head { display: flex; align-items: baseline; gap: var(--space-3); margin-bottom: var(--space-3); flex-wrap: wrap; }
  .db-hint { font-size: var(--font-size-xs); color: var(--gray-500); }
  .db-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: var(--space-2); }
  .db-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    color: var(--gray-800);
    text-decoration: none;
  }
  .db-item:hover { border-color: var(--blue-300); background: var(--blue-50); }
  .db-item.off { opacity: 0.55; }
  .db-item.off .date { font-weight: 500; font-size: var(--font-size-xs); }
  .code { font-size: var(--font-size-xs); font-weight: 700; color: var(--gray-500); }
  .date { font-size: var(--font-size-sm); font-weight: 600; font-variant-numeric: tabular-nums; }
  .period { font-size: var(--font-size-xs); color: var(--gray-500); }
  .more { justify-content: center; align-items: center; font-size: var(--font-size-xs); color: var(--primary); }
</style>
