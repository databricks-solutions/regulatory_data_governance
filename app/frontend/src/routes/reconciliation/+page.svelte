<script>
  import ReconciliationCard from '$lib/components/domain/ReconciliationCard.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import { goto } from '$app/navigation';
  import { appState } from '$lib/stores.svelte.js';
  import { getReconciliationSummary } from '$lib/api.js';
  import { onMount } from 'svelte';

  let reconciliations = $state([
    {
      type: '3040_vs_cosif', name: 'SCR 3040 vs COSIF 4010', status: 'passed',
      executed_at: '2026-03-29T08:00:00Z',
      checks: { total: 18, passed: 17, failed: 0, warning: 1 },
      max_divergence_pct: 0.08, tolerance_pct: 0.1
    },
    {
      type: '3040_vs_3050', name: 'SCR 3040 vs SCR 3050', status: 'passed',
      executed_at: '2026-03-31T10:00:00Z',
      checks: { total: 35, passed: 33, failed: 0, warning: 2 },
      max_divergence_pct: 0.32, tolerance_pct: 0.5
    },
    {
      type: '3040_vs_internal', name: 'SCR 3040 vs Sistemas Internos', status: 'passed',
      executed_at: '2026-03-28T22:00:00Z',
      checks: { total: 12, passed: 12, failed: 0, warning: 0 },
      max_divergence_pct: 0.0, tolerance_pct: 0.0
    },
    {
      type: '3050_vs_internal', name: 'SCR 3050 vs Sistemas Internos', status: 'warning',
      executed_at: '2026-03-28T22:30:00Z',
      checks: { total: 10, passed: 9, failed: 0, warning: 1 },
      max_divergence_pct: 0.45, tolerance_pct: 0.5
    }
  ]);

  let totalChecks = $derived(reconciliations.reduce((s, r) => s + r.checks.total, 0));
  let passedChecks = $derived(reconciliations.reduce((s, r) => s + r.checks.passed, 0));
  let warningChecks = $derived(reconciliations.reduce((s, r) => s + r.checks.warning, 0));
  let blockedCount = $derived(reconciliations.filter(r => r.status === 'blocked' || r.status === 'failed').length);

  onMount(async () => {
    try {
      const data = await getReconciliationSummary(appState.dataBase);
      if (data?.reconciliations) reconciliations = data.reconciliations;
    } catch { /* use mock */ }
  });
</script>

<div class="recon-page">
  <!-- Overview Bar -->
  <div class="card overview-bar">
    <span class="overview-title">Reconciliação — Data-Base: {appState.dataBase}</span>
    <span class="overview-stats">
      {reconciliations.length} cruzamentos
      <span class="sep">|</span>
      {reconciliations.filter(r => r.status === 'passed').length} aprovados
      <span class="sep">|</span>
      {reconciliations.filter(r => r.status === 'warning').length} com alerta
      <span class="sep">|</span>
      {blockedCount} bloqueados
    </span>
  </div>

  <!-- Cards Grid -->
  <div class="recon-grid">
    {#each reconciliations as recon}
      <ReconciliationCard {recon} onclick={() => goto(`/reconciliation/${recon.type}`)} />
    {/each}
  </div>
</div>

<style>
  .recon-page { display: flex; flex-direction: column; gap: var(--space-5); }
  .overview-bar {
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
  }
  .overview-title { font-size: var(--font-size-md); font-weight: 700; }
  .overview-stats { font-size: var(--font-size-sm); color: var(--gray-500); }
  .sep { color: var(--gray-300); margin: 0 var(--space-2); }
  .recon-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-4); }

  @media (max-width: 800px) {
    .recon-grid { grid-template-columns: 1fr; }
  }
</style>
