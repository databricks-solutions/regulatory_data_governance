<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import { getReferenceDominios, getReferenceCalendar, getReferenceEquivalence, getReferenceLayoutVersions } from '$lib/api.js';
  import { onMount } from 'svelte';

  let activeTab = $state('dominios');
  let selectedField = $state('modalidade');
  let loading = $state(false);

  const tabs = [
    { key: 'dominios', label: 'Domínios' },
    { key: 'calendario', label: 'Calendário BACEN' },
    { key: 'equivalencia', label: 'Equivalência' },
    { key: 'versoes', label: 'Versões de Leiaute' }
  ];

  const fieldOptions = [
    'modalidade', 'tipo_cliente', 'natureza_operacao', 'tipo_garantia',
    'classificacao_risco', 'origem_recurso', 'indexador', 'periodicidade'
  ];

  let dominios = $state([]);
  let calendario = $state([]);
  let equivalencia = $state([]);
  let versoes = $state([]);

  const domCols = [
    { key: 'codigo', label: 'Código', sortable: true, width: '100px' },
    { key: 'descricao', label: 'Descrição', sortable: true }
  ];

  const calCols = [
    { key: 'data', label: 'Data', sortable: true, width: '120px' },
    { key: 'tipo', label: 'Tipo', sortable: true, width: '80px' },
    { key: 'ultimo_du_semana', label: 'Ult. DU Semana', width: '120px', render: (v) => v ? 'Sim' : '-' },
    { key: 'ultimo_du_mes', label: 'Ult. DU Mês', width: '120px', render: (v) => v ? '<strong style="color: var(--accent)">Sim</strong>' : '-' }
  ];

  const equivCols = [
    { key: 'mod_3040', label: 'Mod 3040', sortable: true, width: '100px' },
    { key: 'desc_3040', label: 'Descrição 3040', sortable: true },
    { key: 'cat_3050', label: 'Categoria 3050', sortable: true, width: '150px' },
    { key: 'notas', label: 'Notas', width: '100px' }
  ];

  const verCols = [
    { key: 'doc', label: 'Documento', sortable: true, width: '100px' },
    { key: 'versao', label: 'Versão', sortable: true, width: '80px' },
    { key: 'vigencia_inicio', label: 'Vigência Início', sortable: true, width: '140px' },
    { key: 'vigencia_fim', label: 'Vigência Fim', sortable: true, width: '140px' },
    { key: 'status', label: 'Status', sortable: true, width: '100px', render: (v) => v === 'atual' ? '<span style="color: var(--success); font-weight: 600">Atual</span>' : '<span style="color: var(--gray-500)">Histórico</span>' }
  ];

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
        <label class="field-label">Campo:</label>
        <select class="field-select" bind:value={selectedField}>
          {#each fieldOptions as f}
            <option value={f}>{f}</option>
          {/each}
        </select>
      </div>
      <DataTable columns={domCols} data={dominios} emptyMessage="Nenhum domínio encontrado" />
    </div>
  {:else if activeTab === 'calendario'}
    <div class="card">
      <DataTable columns={calCols} data={calendario} emptyMessage="Nenhuma data encontrada" />
    </div>
  {:else if activeTab === 'equivalencia'}
    <div class="card">
      <DataTable columns={equivCols} data={equivalencia} emptyMessage="Nenhuma equivalência encontrada" />
    </div>
  {:else if activeTab === 'versoes'}
    <div class="card">
      <DataTable columns={verCols} data={versoes} emptyMessage="Nenhuma versão encontrada" />
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
