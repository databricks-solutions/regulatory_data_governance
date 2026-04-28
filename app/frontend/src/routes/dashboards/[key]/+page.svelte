<script>
  import { page } from '$app/stores';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import DashboardEmbed from '$lib/components/ui/DashboardEmbed.svelte';

  let dashboardKey = $derived($page.params.key);

  const dashboardMeta = {
    conformidade: { title: 'Conformidade R.18', breadcrumb: 'Conformidade R.18' },
    criticas: { title: 'Monitor de Críticas', breadcrumb: 'Monitor de Críticas' },
    reconciliacao: { title: 'Reconciliação Executiva', breadcrumb: 'Reconciliação Executiva' }
  };

  let meta = $derived(dashboardMeta[dashboardKey] || { title: dashboardKey, breadcrumb: dashboardKey });
</script>

{#key dashboardKey}
<div class="dashboard-embed-page">
  <PageHeader breadcrumbs={[{ label: 'Painéis', href: `/dashboards/${dashboardKey}` }, { label: meta.breadcrumb }]} />
  <DashboardEmbed {dashboardKey} title={meta.title} />
</div>
{/key}

<style>
  .dashboard-embed-page { display: flex; flex-direction: column; gap: var(--space-4); }
</style>
