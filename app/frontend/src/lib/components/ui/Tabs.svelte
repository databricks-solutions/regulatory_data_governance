<script>
  let { tabs, active, onchange } = $props();
</script>

<div class="tabs" role="tablist">
  {#each tabs as tab}
    <button
      role="tab"
      class="tab"
      class:active={active === tab.key}
      aria-selected={active === tab.key}
      onclick={() => onchange(tab.key)}
    >
      {tab.label}
      {#if active === tab.key}
        <div class="tab-indicator"></div>
      {/if}
    </button>
  {/each}
</div>

<style>
  .tabs {
    display: flex;
    gap: var(--space-1);
    padding: var(--space-1);
    background: var(--gray-100);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-5);
  }
  .tab {
    position: relative;
    padding: var(--space-2) var(--space-5);
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--gray-500);
    cursor: pointer;
    transition: all var(--transition-fast);
    white-space: nowrap;
  }
  .tab:hover {
    color: var(--gray-700);
  }
  .tab.active {
    color: var(--primary);
    background: var(--white);
    box-shadow: var(--shadow-sm);
  }
  .tab-indicator {
    display: none;
  }
</style>
