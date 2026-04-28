<script>
  let { title = '', breadcrumbs = [] } = $props();
</script>

<div class="page-header">
  {#if breadcrumbs.length > 0}
    <nav class="breadcrumbs" aria-label="Breadcrumbs">
      {#each breadcrumbs as crumb, i}
        {#if i > 0}
          <svg class="bc-sep" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 18l6-6-6-6"/></svg>
        {/if}
        {#if crumb.href}
          <a href={crumb.href} class="bc-link">{crumb.label}</a>
        {:else}
          <span class="bc-current">{crumb.label}</span>
        {/if}
      {/each}
    </nav>
  {/if}
</div>

<style>
  .page-header {
    margin-bottom: var(--space-5);
  }
  .breadcrumbs {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--font-size-sm);
  }
  .bc-link {
    color: var(--gray-500);
    font-weight: 500;
    text-decoration: none;
    padding: 2px var(--space-2);
    border-radius: var(--radius-xs);
    transition: all var(--transition-fast);
  }
  .bc-link:hover {
    color: var(--primary);
    background: var(--blue-50);
    text-decoration: none;
  }
  .bc-sep { color: var(--gray-300); flex-shrink: 0; }
  .bc-current {
    color: var(--gray-800);
    font-weight: 600;
    padding: 2px var(--space-2);
  }
</style>
