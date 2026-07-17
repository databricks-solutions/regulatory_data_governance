<script>
  import { _ } from 'svelte-i18n';
  import DashboardEmbed from '$lib/components/ui/DashboardEmbed.svelte';
</script>

<div class="genie-page">
  <div class="genie-header">
    <h2>{$_('genie.title')}</h2>
    <p class="genie-sub">{$_('genie.subtitle')}</p>
  </div>
  <DashboardEmbed dashboardKey="genie" title={$_('genie.embedTitle')} />
</div>

<style>
  .genie-page { display: flex; flex-direction: column; gap: var(--space-4); }
  .genie-header { margin-bottom: var(--space-2); }
  .genie-sub { font-size: var(--font-size-sm); color: var(--gray-500); }
</style>
