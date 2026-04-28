<script>
  import DashboardEmbed from '$lib/components/ui/DashboardEmbed.svelte';
</script>

<div class="genie-page">
  <div class="genie-header">
    <h2>Consulta Natural — SCR R.18</h2>
    <p class="genie-sub">Pergunte sobre dados do SCR em linguagem natural</p>
  </div>
  <DashboardEmbed dashboardKey="genie" title="Genie Space — Consulta Natural" />
</div>

<style>
  .genie-page { display: flex; flex-direction: column; gap: var(--space-4); }
  .genie-header { margin-bottom: var(--space-2); }
  .genie-sub { font-size: var(--font-size-sm); color: var(--gray-500); }
</style>
