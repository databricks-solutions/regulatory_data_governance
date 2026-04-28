<script>
  let { message = 'Nenhum dado encontrado', icon = '' } = $props();
</script>

<div class="empty-state">
  <div class="empty-icon-wrap">
    {#if icon}{icon}{:else}
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    {/if}
  </div>
  <p class="empty-msg">{message}</p>
</div>

<style>
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--space-16);
    gap: var(--space-4);
    color: var(--gray-500);
  }
  .empty-icon-wrap {
    width: 72px;
    height: 72px;
    border-radius: var(--radius-xl);
    background: var(--gray-100);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--gray-400);
  }
  .empty-msg {
    font-size: var(--font-size-base);
    font-weight: 500;
    color: var(--gray-500);
  }
</style>
