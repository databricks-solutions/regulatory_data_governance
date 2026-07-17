<script>
  import Badge from '../ui/Badge.svelte';
  import { statusColors } from '$lib/theme.js';
  import { formatDateTime, formatPercent } from '$lib/format.js';
  import { _ } from 'svelte-i18n';

  let { recon, onclick = null } = $props();

  let statusInfo = $derived(statusColors[recon.status] || statusColors.pendente);
  let passRate = $derived(
    recon.checks.total > 0 ? ((recon.checks.passed / recon.checks.total) * 100) : 0
  );

  let variantMap = { passed: 'success', warning: 'warning', failed: 'error', blocked: 'error' };
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="recon-card" style="border-left-color: {statusInfo.color}" class:clickable={!!onclick} onclick={onclick}>
  <div class="recon-header">
    <h3 class="recon-name">{recon.name}</h3>
    <Badge label={statusInfo.label} variant={variantMap[recon.status] || 'info'} />
  </div>

  <div class="recon-stats">
    <span>{$_('reconciliation.rules', { values: { count: recon.checks.total } })}</span>
    <span class="sep">|</span>
    <span>{$_('reconciliation.ok', { values: { count: recon.checks.passed } })}</span>
    {#if recon.checks.warning > 0}
      <span class="sep">|</span>
      <span class="warn-text">{$_('reconciliation.warning', { values: { count: recon.checks.warning } })}</span>
    {/if}
    {#if recon.checks.failed > 0}
      <span class="sep">|</span>
      <span class="fail-text">{$_('reconciliation.failure', { values: { count: recon.checks.failed } })}</span>
    {/if}
  </div>

  <div class="recon-detail">
    <span>{$_('reconciliation.maxDiv')}: {formatPercent(recon.max_divergence_pct)}</span>
    <span class="sep">|</span>
    <span>{$_('reconciliation.tolerance')}: {formatPercent(recon.tolerance_pct)}</span>
  </div>

  <div class="recon-meta">
    {$_('reconciliation.exec')}: {formatDateTime(recon.executed_at)}
  </div>

  <div class="progress-bar">
    <div class="progress-fill" style="width: {passRate}%; background: {statusInfo.color}"></div>
  </div>
  <div class="progress-label">{passRate.toFixed(0)}%</div>

  {#if onclick}
    <div class="recon-link">{$_('reconciliation.viewDetails')} &rarr;</div>
  {/if}
</div>

<style>
  .recon-card {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-left: 4px solid var(--gray-300);
    border-radius: var(--radius-md);
    padding: var(--space-4) var(--space-5);
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.15s;
  }
  .recon-card.clickable { cursor: pointer; }
  .recon-card.clickable:hover { box-shadow: var(--shadow-md); }

  .recon-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
  }
  .recon-name {
    font-size: var(--font-size-base);
    font-weight: 700;
  }
  .recon-stats {
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    margin-bottom: var(--space-1);
  }
  .sep { color: var(--gray-300); margin: 0 var(--space-1); }
  .warn-text { color: var(--warning); }
  .fail-text { color: var(--error); }
  .recon-detail {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
    margin-bottom: var(--space-1);
  }
  .recon-meta {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    margin-bottom: var(--space-3);
  }
  .progress-bar {
    width: 100%;
    height: 6px;
    background: var(--gray-100);
    border-radius: var(--radius-full);
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 0.3s;
  }
  .progress-label {
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--gray-500);
    text-align: right;
    margin-top: 2px;
  }
  .recon-link {
    margin-top: var(--space-3);
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--primary);
  }
</style>
