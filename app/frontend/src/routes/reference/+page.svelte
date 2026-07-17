<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import { getReferenceDominios, getReferenceCalendar, getReferenceEquivalence, getReferenceLayoutVersions } from '$lib/api.js';
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';

  let activeTab = $state('dominios');
  let selectedField = $state('modalidade');
  let loading = $state(false);

  const tabs = $derived.by(() => [
    { key: 'dominios', label: $_('reference.tabDominios') },
    { key: 'calendario', label: $_('reference.tabCalendario') },
    { key: 'equivalencia', label: $_('reference.tabEquivalencia') },
    { key: 'versoes', label: $_('reference.tabVersoes') }
  ]);

  const fieldOptions = [
    'modalidade', 'tipo_cliente', 'natureza_operacao', 'tipo_garantia',
    'classificacao_risco', 'origem_recurso', 'indexador', 'periodicidade'
  ];

  let dominios = $state([]);
  let calendario = $state([]);
  let equivalencia = $state([]);
  let versoes = $state([]);

  const domCols = $derived.by(() => [
    { key: 'codigo', label: $_('reference.colCodigo'), sortable: true, width: '100px' },
    { key: 'descricao', label: $_('reference.colDescricao'), sortable: true }
  ]);

  const calCols = $derived.by(() => [
    { key: 'data', label: $_('reference.colData'), sortable: true, width: '120px' },
    { key: 'tipo', label: $_('reference.colTipo'), sortable: true, width: '80px' },
    { key: 'ultimo_du_semana', label: $_('reference.colUltDuSemana'), width: '120px', render: (v) => v ? $_('reference.sim') : '-' },
    { key: 'ultimo_du_mes', label: $_('reference.colUltDuMes'), width: '120px', render: (v) => v ? `<strong style="color: var(--accent)">${$_('reference.sim')}</strong>` : '-' }
  ]);

  const equivCols = $derived.by(() => [
    { key: 'mod_3040', label: $_('reference.colMod3040'), sortable: true, width: '100px' },
    { key: 'desc_3040', label: $_('reference.colDesc3040'), sortable: true },
    { key: 'cat_3050', label: $_('reference.colCat3050'), sortable: true, width: '150px' },
    { key: 'notas', label: $_('reference.colNotas'), width: '100px' }
  ]);

  const verCols = $derived.by(() => [
    { key: 'doc', label: $_('reference.colDocumento'), sortable: true, width: '100px' },
    { key: 'versao', label: $_('reference.colVersao'), sortable: true, width: '80px' },
    { key: 'vigencia_inicio', label: $_('reference.colVigenciaInicio'), sortable: true, width: '140px' },
    { key: 'vigencia_fim', label: $_('reference.colVigenciaFim'), sortable: true, width: '140px' },
    { key: 'status', label: $_('reference.colStatus'), sortable: true, width: '100px', render: (v) => v === 'atual' ? `<span style="color: var(--success); font-weight: 600">${$_('reference.statusAtual')}</span>` : `<span style="color: var(--gray-500)">${$_('reference.statusHistorico')}</span>` }
  ]);

  onMount(async () => {
    try {
      const data = await getReferenceDominios(selectedField);
      if (data) dominios = data;
    } catch {}
  });
</script>

<div class="reference-page">
  <Tabs {tabs} active={activeTab} onchange={(k) => activeTab = k} />

  {#if activeTab === 'dominios'}
    <div class="card">
      <div class="filter-row">
        <label class="field-label">{$_('reference.campoLabel')}</label>
        <select class="field-select" bind:value={selectedField}>
          {#each fieldOptions as f}
            <option value={f}>{f}</option>
          {/each}
        </select>
      </div>
      <DataTable columns={domCols} data={dominios} emptyMessage={$_('reference.emptyDominios')} />
    </div>
  {:else if activeTab === 'calendario'}
    <div class="card">
      <DataTable columns={calCols} data={calendario} emptyMessage={$_('reference.emptyCalendario')} />
    </div>
  {:else if activeTab === 'equivalencia'}
    <div class="card">
      <DataTable columns={equivCols} data={equivalencia} emptyMessage={$_('reference.emptyEquivalencia')} />
    </div>
  {:else if activeTab === 'versoes'}
    <div class="card">
      <DataTable columns={verCols} data={versoes} emptyMessage={$_('reference.emptyVersoes')} />
    </div>
  {/if}
</div>

<style>
  .reference-page { display: flex; flex-direction: column; gap: var(--space-4); }
  .filter-row {
    display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-4);
  }
  .field-label { font-size: var(--font-size-sm); font-weight: 600; color: var(--gray-500); }
  .field-select {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-family: var(--font-primary);
    font-size: var(--font-size-sm);
  }
</style>
