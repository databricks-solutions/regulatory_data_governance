<script>
  // "Novo relacionamento de linhagem" — mirrors the native "Add lineage
  // relationship": pick a source and a target (each either an external metadata
  // object OR a Unity Catalog table), an optional column mapping, and free-form
  // properties (mechanism/ingestion). Writes to the UC External Lineage API.
  import { _ } from 'svelte-i18n';
  import Modal from '$lib/components/ui/Modal.svelte';
  import SystemTypeIcon from './SystemTypeIcon.svelte';
  import { createExternalLineage } from '$lib/api.js';

  let { open = false, externalObjects = [], ucTables = [], onclose, onsaved } = $props();

  // Each endpoint is { kind: 'external'|'table', value: <name|fqn> }.
  let source = $state({ kind: 'external', value: '' });
  let target = $state({ kind: 'table', value: '' });
  let mappings = $state([]);          // [{source, target}]
  let mechanism = $state('');
  let saving = $state(false);
  let error = $state('');

  $effect(() => {
    if (open) {
      source = { kind: 'external', value: externalObjects[0]?.name || '' };
      target = { kind: 'table', value: ucTables[0]?.full_name || '' };
      mappings = [];
      mechanism = '';
      error = '';
    }
  });

  function iconFor(name) {
    return externalObjects.find(o => o.name === name)?.system_type_icon || 'custom';
  }

  function endpointBody(ep) {
    return ep.kind === 'external'
      ? { external_metadata_name: ep.value }
      : { table_name: ep.value };
  }

  const payload = $derived({
    source: endpointBody(source),
    target: endpointBody(target),
    columns: mappings.filter(m => m.source && m.target),
    properties: mechanism.trim() ? { mechanism: mechanism.trim() } : {}
  });

  function addMapping() { mappings = [...mappings, { source: '', target: '' }]; }
  function removeMapping(i) { mappings = mappings.filter((_, idx) => idx !== i); }

  async function submit() {
    if (!source.value || !target.value) { error = $_('lineageMgmt.errEndpointsRequired'); return; }
    if (source.kind === source.kind && source.value === target.value && source.kind === target.kind) {
      error = $_('lineageMgmt.errSameEndpoint'); return;
    }
    saving = true; error = '';
    try {
      await createExternalLineage(payload);
      onsaved?.();
    } catch (e) {
      error = e?.message || String(e);
    } finally {
      saving = false;
    }
  }
</script>

<Modal {open} title={$_('lineageMgmt.newRelTitle')} {onclose}>
  <div class="form">
    {#if error}<div class="form-error">{error}</div>{/if}
    <div class="info-banner">{$_('lineageMgmt.relBanner')}</div>

    <!-- Source -->
    <div class="endpoint">
      <span class="field-label">{$_('lineageMgmt.source')}</span>
      <div class="kind-toggle">
        <button type="button" class:active={source.kind === 'external'} onclick={() => { source = { kind: 'external', value: externalObjects[0]?.name || '' }; }}>{$_('lineageMgmt.externalObject')}</button>
        <button type="button" class:active={source.kind === 'table'} onclick={() => { source = { kind: 'table', value: ucTables[0]?.full_name || '' }; }}>{$_('lineageMgmt.ucTable')}</button>
      </div>
      {#if source.kind === 'external'}
        <select class="input" bind:value={source.value}>
          {#each externalObjects as o}<option value={o.name}>{o.name}</option>{/each}
        </select>
      {:else}
        <select class="input" bind:value={source.value}>
          {#each ucTables as t}<option value={t.full_name}>{t.full_name}</option>{/each}
        </select>
      {/if}
    </div>

    <div class="arrow">↓</div>

    <!-- Target -->
    <div class="endpoint">
      <span class="field-label">{$_('lineageMgmt.target')}</span>
      <div class="kind-toggle">
        <button type="button" class:active={target.kind === 'external'} onclick={() => { target = { kind: 'external', value: externalObjects[0]?.name || '' }; }}>{$_('lineageMgmt.externalObject')}</button>
        <button type="button" class:active={target.kind === 'table'} onclick={() => { target = { kind: 'table', value: ucTables[0]?.full_name || '' }; }}>{$_('lineageMgmt.ucTable')}</button>
      </div>
      {#if target.kind === 'external'}
        <select class="input" bind:value={target.value}>
          {#each externalObjects as o}<option value={o.name}>{o.name}</option>{/each}
        </select>
      {:else}
        <select class="input" bind:value={target.value}>
          {#each ucTables as t}<option value={t.full_name}>{t.full_name}</option>{/each}
        </select>
      {/if}
    </div>

    <!-- Mechanism -->
    <label class="field">
      <span class="field-label">{$_('lineageMgmt.mechanism')}</span>
      <input class="input" bind:value={mechanism} placeholder={$_('lineageMgmt.mechanismPlaceholder')} spellcheck="false" />
    </label>

    <!-- Column mappings -->
    <div class="field">
      <span class="field-label">{$_('lineageMgmt.columnMappings')}</span>
      {#each mappings as m, i}
        <div class="map-row">
          <input class="input mono" placeholder={$_('lineageMgmt.sourceCol')} bind:value={m.source} spellcheck="false" />
          <span class="map-arrow">→</span>
          <input class="input mono" placeholder={$_('lineageMgmt.targetCol')} bind:value={m.target} spellcheck="false" />
          <button type="button" class="map-del" onclick={() => removeMapping(i)} aria-label="remover">×</button>
        </div>
      {/each}
      <button type="button" class="map-add" onclick={addMapping}>+ {$_('lineageMgmt.addMapping')}</button>
    </div>

    <div class="form-actions">
      <button class="btn btn-secondary" onclick={onclose} disabled={saving}>{$_('common.cancel')}</button>
      <button class="btn btn-primary" onclick={submit} disabled={saving}>
        {saving ? $_('common.saving') : $_('lineageMgmt.create')}
      </button>
    </div>
  </div>
</Modal>

<style>
  .form { display: flex; flex-direction: column; gap: var(--space-3); }
  .info-banner {
    background: var(--blue-50, #E5F0F8); color: var(--blue-800, #003D73);
    border: 1px solid var(--blue-200, #B3D4EA); border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-3); font-size: var(--font-size-xs);
  }
  .form-error { background: #FDECEA; color: #B71C1C; border: 1px solid #F5C6C0;
    border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); font-size: var(--font-size-sm); }
  .field, .endpoint { display: flex; flex-direction: column; gap: 4px; }
  .field-label { font-size: var(--font-size-xs); font-weight: 700; color: var(--gray-700); }
  .input { width: 100%; padding: 8px 10px; border: 1px solid var(--border-color);
    border-radius: var(--radius-md); font-size: var(--font-size-sm); background: var(--white);
    color: var(--gray-900); box-sizing: border-box; }
  .input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(0,92,169,0.12); }
  .input.mono { font-family: var(--font-mono); font-size: 12px; }
  .arrow { text-align: center; font-size: 20px; color: var(--gray-400); }
  .kind-toggle { display: flex; gap: 0; }
  .kind-toggle button {
    flex: 1; padding: 6px 10px; border: 1px solid var(--border-color); background: var(--white);
    font-size: var(--font-size-xs); cursor: pointer; color: var(--gray-600);
  }
  .kind-toggle button:first-child { border-radius: var(--radius-md) 0 0 var(--radius-md); }
  .kind-toggle button:last-child { border-radius: 0 var(--radius-md) var(--radius-md) 0; border-left: none; }
  .kind-toggle button.active { background: var(--primary); color: #fff; border-color: var(--primary); }
  .map-row { display: grid; grid-template-columns: 1fr auto 1fr auto; gap: 6px; align-items: center; margin-bottom: 6px; }
  .map-arrow { color: var(--gray-400); }
  .map-del { background: none; border: 1px solid var(--border-color); border-radius: var(--radius-sm);
    width: 28px; height: 28px; cursor: pointer; color: var(--gray-500); font-size: 16px; }
  .map-del:hover { color: #C62828; border-color: #C62828; }
  .map-add { background: none; border: 1px dashed var(--border-color); border-radius: var(--radius-sm);
    padding: 4px 10px; font-size: var(--font-size-xs); color: var(--gray-600); cursor: pointer; align-self: flex-start; }
  .form-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-2); }
  .btn { padding: 8px 16px; border-radius: var(--radius-md); font-size: var(--font-size-sm); font-weight: 600; cursor: pointer; border: 1px solid transparent; }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover:not(:disabled) { background: var(--blue-700, #004A8A); }
  .btn-secondary { background: var(--white); border-color: var(--border-color); color: var(--gray-700); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
</style>
