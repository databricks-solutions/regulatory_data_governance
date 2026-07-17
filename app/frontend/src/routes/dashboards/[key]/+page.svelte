<script>
  import { _ } from 'svelte-i18n';
  import { page } from '$app/stores';
  import PageHeader from '$lib/components/layout/PageHeader.svelte';
  import DashboardEmbed from '$lib/components/ui/DashboardEmbed.svelte';

  let dashboardKey = $derived($page.params.key);

  let dashboardMeta = $derived.by(() => ({
    conformidade: { title: $_('dashboards.conformidade'), breadcrumb: $_('dashboards.conformidade') },
    criticas: { title: $_('dashboards.criticas'), breadcrumb: $_('dashboards.criticas') }
  }));

  let meta = $derived(dashboardMeta[dashboardKey] || { title: dashboardKey, breadcrumb: dashboardKey });
</script>

{#key dashboardKey}
<div class="dashboard-embed-page">
  <PageHeader breadcrumbs={[{ label: $_('dashboards.breadcrumb'), href: `/dashboards/${dashboardKey}` }, { label: meta.breadcrumb }]} />
  <DashboardEmbed {dashboardKey} title={meta.title} />
</div>
{/key}

<style>
  .dashboard-embed-page { display: flex; flex-direction: column; gap: var(--space-4); }
</style>
