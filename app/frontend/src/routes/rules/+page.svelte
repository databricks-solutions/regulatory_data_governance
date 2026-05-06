<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import RuleBuilder from '$lib/components/domain/RuleBuilder.svelte';
  import { getRuleEngineDatasets, getRuleEngineRules, createRuleEngineDataset, createRuleEngineRule } from '$lib/api.js';
  import { appState } from '$lib/stores.svelte.js';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';

  let activeTab = $state('dados');
  const tabs = [
    { key: 'dados', label: 'Dados' },
    { key: 'regras', label: 'Regras' }
  ];

  const NIVEL_LABELS = {
    1: { label: 'Nível 1', subtitle: 'Verificações básicas', color: 'var(--primary)' },
    2: { label: 'Nível 2', subtitle: 'Coerência temporal', color: 'var(--warning)' },
    3: { label: 'Nível 3', subtitle: 'Regras negociais', color: 'var(--error)' },
  };

  const dimensionNames = ['Acessibilidade','Acurácia','Adaptabilidade','Clareza','Comparabilidade','Completude','Confiabilidade','Consistência','Integridade','Rastreabilidade','Relevância','Tempestividade'];

  // Data-Base options (6 months back)
  const dataBaseOptions = Array.from({ length: 6 }, (_, i) => {
    const d = new Date();
    d.setMonth(d.getMonth() - i);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    return `${y}-${m}`;
  });

  // --- Dados state ---
  let datasets = $state([]);
  let showAddDataset = $state(false);
  let newDataset = $state({ name: '', source_path: '', tipo: 'table', data_base: appState.dataBase || '2026-03' });

  // --- Regras state ---
  let rules = $state([]);

  let ruleFilters = $state({});
  let expandedRule = $state(null);
  let showRuleBuilder = $state(false);

  const ruleFilterDefs = [
    { key: 'nivel_verificacao', label: 'Nível', type: 'select', options: [
      { value: '1', label: 'N1 — Básico' },
      { value: '2', label: 'N2 — Temporal' },
      { value: '3', label: 'N3 — Negocial' }
    ]},
    { key: 'rule_type', label: 'Tipo', type: 'select', options: [
      { value: 'syntactic', label: 'Sintática' },
      { value: 'semantic', label: 'Semântica' },
      { value: 'inter_document', label: 'Inter-documento' },
      { value: 'business', label: 'Regra Negocial' }
    ]},
    { key: 'severity', label: 'Severidade', type: 'select', options: [
      { value: 'error', label: 'Error' },
      { value: 'warning', label: 'Warning' },
      { value: 'info', label: 'Info' }
    ]},
    { key: 'search', label: 'Buscar', type: 'text', placeholder: 'Nome da regra...' }
  ];

  const RULE_TYPE_LABELS = { syntactic: 'Sintática', semantic: 'Semântica', inter_document: 'Inter-doc', business: 'Negocial' };

  const ruleColumns = [
    { key: 'rule_id', label: 'Regra', sortable: true, width: '80px', render: (v) => `<span style="font-family:var(--font-mono);font-size:var(--font-size-xs)">${v}</span>` },
    { key: 'name', label: 'Descrição', sortable: true },
    { key: 'nivel_verificacao', label: 'Nível', sortable: true, width: '70px', render: (v) => `<span class="nivel-badge nivel-${v}">N${v}</span>` },
    { key: 'rule_type', label: 'Tipo', sortable: true, width: '100px', render: (v) => RULE_TYPE_LABELS[v] || v },
    { key: 'dimension_r18', label: 'Dim. R.18', sortable: true, width: '130px', render: (v) => v ? `${v} - ${dimensionNames[v-1] || ''}` : '-' },
    { key: 'severity', label: 'Sev.', sortable: true, width: '70px', render: (v) => `<span class="sev-${v}">${v}</span>` },
    { key: 'is_seeded', label: '', width: '80px', render: (v) => v ? '<span class="seeded-badge">Semeada</span>' : '' }
  ];

  let filteredRules = $derived.by(() => {
    let r = rules;
    if (ruleFilters.nivel_verificacao) r = r.filter(x => String(x.nivel_verificacao) === ruleFilters.nivel_verificacao);
    if (ruleFilters.rule_type) r = r.filter(x => x.rule_type === ruleFilters.rule_type);
    if (ruleFilters.severity) r = r.filter(x => x.severity === ruleFilters.severity);
    if (ruleFilters.search) r = r.filter(x => x.name.toLowerCase().includes(ruleFilters.search.toLowerCase()));
    return r;
  });

  function handleRuleFilter(key, value) {
    ruleFilters = { ...ruleFilters, [key]: value };
  }
  function resetRuleFilters() {
    ruleFilters = {};
  }

  function tipoVariant(tipo) {
    return tipo === 'table' ? 'info' : 'warning';
  }
  function tipoLabel(tipo) {
    return tipo === 'table' ? 'Tabela' : 'Arquivo';
  }

  function statusVariant(status) {
    if (status === 'completed') return 'success';
    if (status === 'failed') return 'error';
    if (status === 'running') return 'info';
    return 'neutral';
  }

  async function handleRuleSave(rule) {
    try {
      const created = await createRuleEngineRule(rule);
      if (created) rules = [...rules, created];
    } catch {}
    showRuleBuilder = false;
  }

  async function handleAddDataset() {
    try {
      const created = await createRuleEngineDataset(newDataset);
      if (created) datasets = [...datasets, { ...created, bindings_count: 0, last_run_status: null }];
    } catch {}
    showAddDataset = false;
    newDataset = { name: '', source_path: '', tipo: 'table', data_base: appState.dataBase || '2026-03' };
  }

  onMount(async () => {
    try {
      const [dsData, rulesData] = await Promise.all([
        getRuleEngineDatasets(),
        getRuleEngineRules()
      ]);
      if (dsData?.datasets) datasets = dsData.datasets;
      if (rulesData?.rules) rules = rulesData.rules;
    } catch {}
  });
</script>

<div class="rules-page">
  <div class="page-intro">
    <h2>Motor de Regras</h2>
    <p class="intro-text">Gerencie regras de validação de dados e execute verificações contra seus datasets registrados.</p>
  </div>

  <Tabs {tabs} active={activeTab} onchange={(k) => activeTab = k} />

  {#if activeTab === 'dados'}
    <!-- Datasets Tab -->
    <div class="section-header">
      <span class="section-count">{datasets.length} datasets registrados</span>
      <button class="btn-primary" onclick={() => showAddDataset = true}>+ Registrar Dataset</button>
    </div>

    <div class="dataset-grid">
      {#each datasets as ds}
        <button class="card dataset-card" onclick={() => goto(`/rules/datasets/${ds.dataset_id}`)}>
          <div class="ds-header">
            <span class="ds-name">{ds.name}</span>
            <div class="ds-badges">
              <Badge label={tipoLabel(ds.tipo)} variant={tipoVariant(ds.tipo)} />
              {#if ds.data_base}
                <Badge label={ds.data_base} variant="neutral" />
              {/if}
            </div>
          </div>
          <div class="ds-source-path">{ds.source_path}</div>
          <div class="ds-stats">
            <div class="ds-stat">
              <span class="ds-stat-value">{ds.row_count_approx ? (ds.row_count_approx / 1000000).toFixed(1) + 'M' : '-'}</span>
              <span class="ds-stat-label">registros</span>
            </div>
            <div class="ds-stat">
              <span class="ds-stat-value">{ds.bindings_count ?? 0}</span>
              <span class="ds-stat-label">regras vinculadas</span>
            </div>
            <div class="ds-stat">
              {#if ds.last_run_status}
                <Badge label={ds.last_run_status} variant={statusVariant(ds.last_run_status)} />
              {:else}
                <span class="ds-stat-value">-</span>
              {/if}
              <span class="ds-stat-label">última execução</span>
            </div>
          </div>
        </button>
      {/each}
    </div>

    <Modal open={showAddDataset} title="Registrar Dataset" onclose={() => showAddDataset = false}>
      <div class="form-group">
        <label for="ds-name">Nome</label>
        <input id="ds-name" type="text" bind:value={newDataset.name} placeholder="Ex: Operações Validadas" />
      </div>
      <div class="form-group">
        <label for="ds-tipo">Tipo</label>
        <select id="ds-tipo" bind:value={newDataset.tipo}>
          <option value="table">Tabela (Unity Catalog)</option>
          <option value="file">Arquivo (Volume)</option>
        </select>
      </div>
      <div class="form-group">
        <label for="ds-source">{newDataset.tipo === 'table' ? 'Tabela (Unity Catalog)' : 'Caminho do Volume'}</label>
        <input id="ds-source" type="text" bind:value={newDataset.source_path}
          placeholder={newDataset.tipo === 'table' ? 'Ex: rc18_catalog.silver.operacoes_validadas' : 'Ex: /Volumes/rc18_catalog/bronze/xmls/'} />
      </div>
      <div class="form-group">
        <label for="ds-database">Data-Base</label>
        <select id="ds-database" bind:value={newDataset.data_base}>
          {#each dataBaseOptions as db}
            <option value={db}>{db}</option>
          {/each}
        </select>
      </div>
      <div class="form-actions">
        <button class="btn-secondary" onclick={() => showAddDataset = false}>Cancelar</button>
        <button class="btn-primary" onclick={handleAddDataset} disabled={!newDataset.name || !newDataset.source_path}>Registrar</button>
      </div>
    </Modal>

  {:else}
    <!-- Regras Tab -->
    <div class="section-header">
      <span class="section-count">{filteredRules.length} regras</span>
      <button class="btn-primary" onclick={() => showRuleBuilder = true}>+ Criar Regra</button>
    </div>

    <FilterBar filters={ruleFilterDefs} values={ruleFilters} onchange={handleRuleFilter} onreset={resetRuleFilters} />

    <div class="card">
      <DataTable
        columns={ruleColumns}
        data={filteredRules}
        expandedRow={expandedRule}
        onRowClick={(row, i) => expandedRule = expandedRule === i ? null : i}
        emptyMessage="Nenhuma regra encontrada"
      >
        {#snippet expandSnippet(row)}
          <div class="expand-detail">
            <p><strong>{row.rule_id}</strong> — {row.name}</p>
            <p class="expand-meta">
              Nível: N{row.nivel_verificacao} |
              Tipo: {RULE_TYPE_LABELS[row.rule_type] || row.rule_type} |
              Modo: {row.authoring_mode === 'structured' ? 'Estruturada' : 'Expressão'} |
              Dimensão R.18: {row.dimension_r18 ? `${row.dimension_r18} (${dimensionNames[row.dimension_r18 - 1]})` : 'N/A'}
            </p>
            {#if row.tags?.length}
              <p class="expand-tags">
                {#each row.tags as tag}
                  <span class="tag">{tag}</span>
                {/each}
              </p>
            {/if}
          </div>
        {/snippet}
      </DataTable>
    </div>
  {/if}

  <RuleBuilder open={showRuleBuilder} onclose={() => showRuleBuilder = false} onsave={handleRuleSave} />
</div>

<style>
  .rules-page { display: flex; flex-direction: column; gap: var(--space-4); }

  .page-intro { margin-bottom: var(--space-2); }
  .page-intro h2 { font-size: var(--font-size-2xl); font-weight: 700; color: var(--gray-900); margin: 0; }
  .intro-text { font-size: var(--font-size-base); color: var(--gray-500); margin-top: var(--space-1); }

  .section-header { display: flex; align-items: center; justify-content: space-between; }
  .section-count { font-size: var(--font-size-sm); color: var(--gray-500); }

  .btn-primary {
    padding: var(--space-2) var(--space-5); background: var(--primary);
    color: white; border: none; border-radius: var(--radius-sm);
    font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }
  .btn-primary:hover { background: var(--blue-500); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary {
    padding: var(--space-2) var(--space-5); background: var(--gray-100);
    color: var(--gray-700); border: 1px solid var(--gray-300);
    border-radius: var(--radius-sm); font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }

  /* Dataset grid */
  .dataset-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: var(--space-4); }
  .dataset-card {
    text-align: left; cursor: pointer;
    border: var(--border-width) solid var(--border-color);
    transition: box-shadow 0.15s, border-color 0.15s;
  }
  .dataset-card:hover { box-shadow: var(--shadow-md); border-color: var(--primary); }
  .ds-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-2); }
  .ds-badges { display: flex; gap: var(--space-2); }
  .ds-name { font-weight: 700; font-size: var(--font-size-md); color: var(--gray-900); }
  .ds-source-path { font-family: var(--font-mono); font-size: var(--font-size-xs); color: var(--gray-500); margin-bottom: var(--space-4); }
  .ds-stats { display: flex; gap: var(--space-5); border-top: 1px solid var(--gray-100); padding-top: var(--space-3); }
  .ds-stat { display: flex; flex-direction: column; gap: 2px; }
  .ds-stat-value { font-weight: 700; font-size: var(--font-size-md); color: var(--gray-900); }
  .ds-stat-label { font-size: var(--font-size-xs); color: var(--gray-500); }

  /* Regras */
  .expand-detail { padding: var(--space-2) 0; }
  .expand-meta { font-size: var(--font-size-sm); color: var(--gray-500); margin-top: var(--space-2); }
  .expand-tags { margin-top: var(--space-2); display: flex; gap: var(--space-2); }
  .tag { font-family: var(--font-mono); font-size: var(--font-size-xs); background: var(--blue-100); color: var(--primary); padding: 2px 8px; border-radius: var(--radius-full); }

  :global(.seeded-badge) { font-size: var(--font-size-xs); background: var(--orange-100); color: var(--orange-900); padding: 2px 8px; border-radius: var(--radius-full); font-weight: 600; }
  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-info) { color: var(--info); font-weight: 600; }
  :global(.nivel-badge) { display: inline-block; padding: 2px 8px; border-radius: var(--radius-full); color: white; font-size: var(--font-size-xs); font-weight: 700; }
  :global(.nivel-1) { background: var(--primary); }
  :global(.nivel-2) { background: var(--warning); }
  :global(.nivel-3) { background: var(--error); }

  /* Modal form */
  .form-group { margin-bottom: var(--space-4); }
  .form-group label { display: block; font-size: var(--font-size-sm); font-weight: 600; color: var(--gray-700); margin-bottom: var(--space-1); }
  .form-group input, .form-group select { width: 100%; padding: var(--space-2) var(--space-3); border: 1px solid var(--gray-300); border-radius: var(--radius-sm); font-size: var(--font-size-base); font-family: var(--font-primary); }
  .form-group input:focus, .form-group select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px var(--blue-100); }
  .form-actions { display: flex; gap: var(--space-3); justify-content: flex-end; margin-top: var(--space-5); }
</style>
