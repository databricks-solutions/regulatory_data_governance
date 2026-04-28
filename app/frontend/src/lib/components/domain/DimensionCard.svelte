<script>
  import Badge from '../ui/Badge.svelte';
  import SparkLine from '../charts/SparkLine.svelte';
  import { statusColors } from '$lib/theme.js';

  let { dimension, onclick = null } = $props();

  let statusInfo = $derived(statusColors[dimension.status] || statusColors.pendente);
  let trendValues = $derived((dimension.trend || []).map(t => t.score));
</script>

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="dim-card" style="border-left-color: {statusInfo.color}" class:clickable={!!onclick} onclick={onclick}>
  <div class="dim-header">
    <span class="dim-number">{dimension.id}.</span>
    <span class="dim-name">{dimension.name}</span>
  </div>
  <div class="dim-score">{dimension.score?.toFixed(1)}<span class="dim-unit">%</span></div>
  <div class="dim-target">Meta: {dimension.target?.toFixed(1)}%</div>
  <div class="dim-footer">
    <Badge label={statusInfo.label} variant={dimension.status === 'conforme' ? 'success' : dimension.status === 'atencao' ? 'warning' : 'error'} />
    {#if trendValues.length > 1}
      <SparkLine values={trendValues} color={statusInfo.color} />
    {/if}
  </div>
</div>

<style>
  .dim-card {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-left: 4px solid var(--gray-300);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    box-shadow: var(--shadow-sm);
    transition: box-shadow 0.15s, transform 0.15s;
  }
  .dim-card.clickable { cursor: pointer; }
  .dim-card.clickable:hover {
    box-shadow: var(--shadow-md);
    transform: translateY(-1px);
  }
  .dim-header {
    display: flex;
    align-items: baseline;
    gap: var(--space-1);
    margin-bottom: var(--space-2);
  }
  .dim-number {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
    font-weight: 600;
  }
  .dim-name {
    font-size: var(--font-size-base);
    font-weight: 700;
    color: var(--gray-900);
  }
  .dim-score {
    font-size: var(--font-size-2xl);
    font-weight: 700;
    color: var(--gray-900);
    line-height: 1.1;
  }
  .dim-unit {
    font-size: var(--font-size-md);
  }
  .dim-target {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
    margin-top: var(--space-1);
  }
  .dim-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: var(--space-3);
  }
</style>
