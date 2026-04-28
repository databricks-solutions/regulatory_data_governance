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

  // Mock data
  let dominios = $state([
    { codigo: '0101', descricao: 'Empréstimos - Cheque especial' },
    { codigo: '0201', descricao: 'Capital de giro com prazo até 365 dias' },
    { codigo: '0202', descricao: 'Capital de giro com prazo superior a 365 dias' },
    { codigo: '0301', descricao: 'Investimento com prazo até 365 dias' },
    { codigo: '0401', descricao: 'Desconto de duplicatas' },
    { codigo: '0501', descricao: 'Financiamento rural - Custeio' },
    { codigo: '0601', descricao: 'Financiamento imobiliário - SFH' },
    { codigo: '0901', descricao: 'Cartão de crédito - Compra à vista' },
    { codigo: '1101', descricao: 'Crédito consignado - INSS' },
    { codigo: '1511', descricao: 'Microcrédito produtivo orientado' }
  ]);

  let calendario = $state([
    { data: '2026-03-02', tipo: 'util', ultimo_du_semana: false, ultimo_du_mes: false },
    { data: '2026-03-06', tipo: 'util', ultimo_du_semana: true, ultimo_du_mes: false },
    { data: '2026-03-13', tipo: 'util', ultimo_du_semana: true, ultimo_du_mes: false },
    { data: '2026-03-20', tipo: 'util', ultimo_du_semana: true, ultimo_du_mes: false },
    { data: '2026-03-27', tipo: 'util', ultimo_du_semana: true, ultimo_du_mes: false },
    { data: '2026-03-31', tipo: 'util', ultimo_du_semana: false, ultimo_du_mes: true }
  ]);

  let equivalencia = $state([
    { mod_3040: '0201', desc_3040: 'Capital de giro até 365 dias', cat_3050: 'capitalDeGiro', notas: 'PJ only' },
    { mod_3040: '0202', desc_3040: 'Capital de giro > 365 dias', cat_3050: 'capitalDeGiro', notas: 'PF excl' },
    { mod_3040: '0301', desc_3040: 'Investimento até 365 dias', cat_3050: 'investimento', notas: '' },
    { mod_3040: '0401', desc_3040: 'Desconto de duplicatas', cat_3050: 'descontos', notas: '' },
    { mod_3040: '0601', desc_3040: 'Financiamento imobiliário SFH', cat_3050: 'imobiliario', notas: 'SFH only' },
    { mod_3040: '0901', desc_3040: 'Cartão de crédito', cat_3050: 'cartaoCredito', notas: '' }
  ]);

  let versoes = $state([
    { doc: '3040', versao: '-', vigencia_inicio: '-', vigencia_fim: '-', status: 'atual' },
    { doc: '3050', versao: 'V11', vigencia_inicio: '07/11/2025', vigencia_fim: '-', status: 'atual' },
    { doc: '3050', versao: 'V10', vigencia_inicio: '04/03/2022', vigencia_fim: '31/10/2025', status: 'historico' },
    { doc: '3050', versao: 'V9', vigencia_inicio: '01/08/2021', vigencia_fim: '03/03/2022', status: 'historico' },
    { doc: '3050', versao: 'V8', vigencia_inicio: '05/02/2021', vigencia_fim: '31/07/2021', status: 'historico' }
  ]);

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
    } catch { /* use mock */ }
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
