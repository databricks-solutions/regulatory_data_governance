<script>
  import { page } from '$app/stores';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import BarChart from '$lib/components/charts/BarChart.svelte';
  import DataTable from '$lib/components/data/DataTable.svelte';
  import { appState } from '$lib/stores.svelte.js';
  import { getReconciliationDetail } from '$lib/api.js';
  import { formatCurrency, formatPercent, formatDateTime } from '$lib/format.js';
  import { onMount } from 'svelte';

  let reconType = $derived($page.params.recon_type);

  const reconNames = {
    '3040_vs_cosif': 'SCR 3040 vs COSIF 4010',
    '3040_vs_3050': 'SCR 3040 vs SCR 3050',
    '3040_vs_internal': 'SCR 3040 vs Sistemas Internos',
    '3050_vs_internal': 'SCR 3050 vs Sistemas Internos'
  };

  let summary = $state({
    executed_at: '2026-03-29T08:00:00Z',
    status: 'passed',
    total_rules: 18,
    max_divergence_pct: 0.08,
    tolerance_pct: 0.1
  });

  let checks = $state([
    { rule_id: 'T02', rule_name: 'Total títulos descontados vs COSIF', scr_value: 1234567890.12, cosif_value: 1234567890.12, divergence_pct: 0.0, tolerance_pct: 0.1, status: 'passed', modality: null, cosif_account: '1.6.1.00.00-8' },
    { rule_id: 'M01', rule_name: 'Divergência empréstimos capital de giro', scr_value: 98765432.50, cosif_value: 98845678.20, divergence_pct: 0.08, tolerance_pct: 0.1, status: 'warning', modality: '0201', cosif_account: '1.6.1.10.20-3' },
    { rule_id: 'T03', rule_name: 'Total financiamentos imobiliários', scr_value: 5678901234.00, cosif_value: 5678901234.00, divergence_pct: 0.0, tolerance_pct: 0.1, status: 'passed', modality: null, cosif_account: '1.6.2.00.00-5' },
    { rule_id: 'M05', rule_name: 'Divergência financiamento rural', scr_value: 2345678900.00, cosif_value: 2345680100.00, divergence_pct: 0.00005, tolerance_pct: 0.1, status: 'passed', modality: '0501', cosif_account: '1.6.3.00.00-2' }
  ]);

  let barData = $derived(
    checks.map(c => ({
      label: c.rule_id + ' - ' + c.rule_name.substring(0, 30),
      value: c.divergence_pct,
      tolerance: c.tolerance_pct
    }))
  );

  const columns = [
    { key: 'rule_id', label: 'Regra', sortable: true, width: '70px' },
    { key: 'rule_name', label: 'Descrição', sortable: true },
    { key: 'scr_value', label: 'SCR Valor', sortable: true, width: '120px', render: (v) => formatCurrency(v) },
    { key: 'cosif_value', label: 'COSIF Valor', sortable: true, width: '120px', render: (v) => formatCurrency(v) },
    { key: 'divergence_pct', label: 'Div %', sortable: true, width: '80px', render: (v) => formatPercent(v) },
    { key: 'status', label: 'Status', sortable: true, width: '80px', render: (v) => v === 'passed' ? '<span class="sev-success">pass</span>' : v === 'warning' ? '<span class="sev-warning">warn</span>' : '<span class="sev-error">fail</span>' }
  ];

  onMount(async () => {
    try {
      const data = await getReconciliationDetail(reconType, appState.dataBase);
      if (data?.checks) checks = data.checks;
    } catch { /* use mock */ }
  });
</script>

<div class="recon-detail">
  <PageHeader breadcrumbs={[{ label: 'Reconciliação', href: '/reconciliation' }, { label: reconNames[reconType] || reconType }]} />

  <div class="card summary-header">
    <h2>{reconNames[reconType] || reconType} — {appState.dataBase}</h2>
    <div class="summary-meta">
      Executado: {formatDateTime(summary.executed_at)}
      <span class="sep">|</span>
      Status: <Badge label={summary.status === 'passed' ? 'Aprovado' : 'Alerta'} variant={summary.status === 'passed' ? 'success' : 'warning'} />
      <span class="sep">|</span>
      {summary.total_rules} regras
      <span class="sep">|</span>
      Div. máxima: {formatPercent(summary.max_divergence_pct)}
      <span class="sep">|</span>
      Tolerância: {formatPercent(summary.tolerance_pct)}
    </div>
  </div>

  <div class="card">
    <div class="card-header">Divergência por Regra</div>
    <BarChart data={barData} maxValue={0.2} toleranceKey="tolerance" />
  </div>

  <div class="card">
    <div class="card-header">Detalhes das Regras</div>
    <DataTable {columns} data={checks} emptyMessage="Nenhuma regra de reconciliação" />
  </div>
</div>

<style>
  .recon-detail { display: flex; flex-direction: column; gap: var(--space-5); }
  .summary-header h2 { margin-bottom: var(--space-2); }
  .summary-meta {
    font-size: var(--font-size-sm); color: var(--gray-500);
    display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-1);
  }
  .sep { color: var(--gray-300); margin: 0 var(--space-1); }

  :global(.sev-success) { color: var(--success); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }
  :global(.sev-error) { color: var(--error); font-weight: 600; }
</style>
