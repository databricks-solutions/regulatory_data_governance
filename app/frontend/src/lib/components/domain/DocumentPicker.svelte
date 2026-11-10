<script>
  /**
   * Seletor de documento (CADOC) das Críticas, no lugar da barra de abas.
   *
   * Uma barra horizontal não comporta dezenas de CADOCs; aqui há busca por código
   * ou nome, agrupamento (`grupo` do cadastro) e, por documento, a data-base do
   * processamento exibido e quantas regras reprovaram. Os cadastrados sem
   * execução (no mês de referência, ou nunca) aparecem esmaecidos; selecionados,
   * a tela explica o que falta.
   */
  import { _ } from 'svelte-i18n';
  import { formatDataBase } from '$lib/format.js';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';

  // `monthSelected`: há mês de referência — muda o rótulo de quem não rodou nele.
  let { documents = [], unprocessed = [], value = '', monthSelected = false, loading = false, onchange } = $props();

  let open = $state(false);
  let query = $state('');
  let highlighted = $state(0);
  let root;
  let searchInput = $state(null);

  // Mesma ordem do backend: com grupo primeiro (alfabética), sem grupo por último.
  const order = (d) => `${d.grupo ? 0 : 1}|${d.grupo || ''}|${d.documento}`;
  let all = $derived(
    [
      ...documents.map((d) => ({ ...d, processed: true })),
      ...unprocessed.map((d) => ({ ...d, processed: false }))
    ].sort((a, b) => order(a).localeCompare(order(b)))
  );

  let current = $derived(all.find((d) => d.documento === value) || null);

  let filtered = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter((d) =>
      d.documento.toLowerCase().includes(q) || (d.nome || '').toLowerCase().includes(q)
    );
  });

  let groups = $derived.by(() => {
    const out = [];
    for (const d of filtered) {
      const key = d.grupo || '';
      let g = out.find((x) => x.key === key);
      if (!g) out.push((g = { key, items: [] }));
      g.items.push(d);
    }
    return out;
  });
  let flat = $derived(groups.flatMap((g) => g.items));

  function toggle() {
    open = !open;
    if (open) {
      query = '';
      highlighted = Math.max(0, flat.findIndex((d) => d.documento === value));
      queueMicrotask(() => searchInput?.focus());
    }
  }

  function choose(doc) {
    open = false;
    if (doc && doc.documento !== value) onchange?.(doc.documento);
  }

  function onKeydown(e) {
    if (!open) return;
    if (e.key === 'Escape') { open = false; return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); highlighted = Math.min(flat.length - 1, highlighted + 1); }
    if (e.key === 'ArrowUp') { e.preventDefault(); highlighted = Math.max(0, highlighted - 1); }
    if (e.key === 'Enter') { e.preventDefault(); choose(flat[highlighted]); }
  }

  $effect(() => {
    query;
    highlighted = 0;
  });

  function onWindowClick(e) {
    if (open && root && !root.contains(e.target)) open = false;
  }
</script>

<svelte:window onclick={onWindowClick} />

<div class="picker card" bind:this={root} onkeydown={onKeydown} role="presentation">
  <span class="picker-label">{$_('documentPicker.label')}</span>
  <button class="picker-trigger" type="button" onclick={toggle} aria-haspopup="listbox" aria-expanded={open}>
    {#if current}
      <span class="code">{current.documento}</span>
      <span class="name">{current.nome || ''}</span>
    {:else if loading}
      <Skeleton width="280px" />
    {:else}
      <span class="name muted">{$_('documentPicker.placeholder')}</span>
    {/if}
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6" /></svg>
  </button>

  {#if open}
    <div class="popover">
      <input
        bind:this={searchInput}
        bind:value={query}
        class="search"
        type="text"
        placeholder={$_('documentPicker.search')}
        aria-label={$_('documentPicker.search')}
      />
      <ul class="list" role="listbox">
        {#each groups as g (g.key)}
          <li class="group">{g.key || $_('documentPicker.otherGroup')}</li>
          {#each g.items as d (d.documento)}
            {@const idx = flat.indexOf(d)}
            <li>
              <button
                type="button"
                role="option"
                aria-selected={d.documento === value}
                class="item"
                class:active={idx === highlighted}
                class:selected={d.documento === value}
                class:off={!d.processed}
                onmouseenter={() => (highlighted = idx)}
                onclick={() => choose(d)}
              >
                <span class="code">{d.documento}</span>
                <span class="name">{d.nome || ''}</span>
                {#if d.processed}
                  <span class="db" title={d.mixed ? $_('documentPicker.mixed') : ''}>
                    {formatDataBase(d.data_base)}{d.mixed ? ' ⚠' : ''}
                  </span>
                  <span class="fails">{d.failed_rules > 0 ? `✗ ${d.failed_rules}` : ''}</span>
                {:else}
                  <span class="db norun">
                    {$_(d.ever_processed && monthSelected ? 'documentPicker.noRunInMonth' : 'documentPicker.noRun')}
                  </span>
                  <span class="fails"></span>
                {/if}
              </button>
            </li>
          {/each}
        {:else}
          <li class="empty">{$_('documentPicker.noMatch')}</li>
        {/each}
      </ul>
    </div>
  {/if}
</div>

<style>
  .picker {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    margin-bottom: var(--space-4);
  }
  .picker-label {
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--gray-500);
  }
  .picker-trigger {
    flex: 1;
    max-width: 640px;
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--white);
    color: var(--gray-800);
    font-size: var(--font-size-sm);
    cursor: pointer;
    text-align: left;
  }
  .picker-trigger:hover { border-color: var(--blue-300); }
  .picker-trigger svg { margin-left: auto; color: var(--gray-500); flex-shrink: 0; }
  .code { font-weight: 700; font-variant-numeric: tabular-nums; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .muted { color: var(--gray-500); }

  .popover {
    position: absolute;
    top: calc(100% - var(--space-2));
    left: calc(var(--space-4) + 90px);
    z-index: 20;
    width: min(640px, calc(100% - 2 * var(--space-4)));
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg);
    overflow: hidden;
  }
  .search {
    width: 100%;
    box-sizing: border-box;
    padding: var(--space-3);
    border: none;
    border-bottom: 1px solid var(--border-color);
    background: transparent;
    color: var(--gray-800);
    font-size: var(--font-size-sm);
    outline: none;
  }
  .list { list-style: none; margin: 0; padding: var(--space-1) 0; max-height: 360px; overflow-y: auto; }
  .group {
    padding: var(--space-2) var(--space-3) var(--space-1);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--gray-500);
  }
  .item {
    width: 100%;
    display: grid;
    grid-template-columns: 56px 1fr auto 44px;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3) var(--space-2) var(--space-4);
    border: none;
    background: none;
    color: var(--gray-800);
    font-size: var(--font-size-sm);
    text-align: left;
    cursor: pointer;
  }
  .item.active { background: var(--blue-50); }
  .item.selected .code { color: var(--primary); }
  .db { font-variant-numeric: tabular-nums; color: var(--gray-600); white-space: nowrap; }
  .fails { color: var(--error); font-weight: 600; text-align: right; white-space: nowrap; }
  .empty { padding: var(--space-3); color: var(--gray-500); font-size: var(--font-size-sm); }
  .item.off .code, .item.off .name { color: var(--gray-500); }
  .norun { font-size: var(--font-size-xs); font-style: italic; color: var(--gray-500); }
</style>
