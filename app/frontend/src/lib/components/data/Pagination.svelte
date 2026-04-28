<script>
  let { page = 1, totalPages = 1, onchange } = $props();
</script>

{#if totalPages > 1}
  <div class="pagination">
    <button class="pg-btn" disabled={page <= 1} onclick={() => onchange(page - 1)}>&laquo; Anterior</button>
    <span class="pg-info">Página {page} de {totalPages}</span>
    <button class="pg-btn" disabled={page >= totalPages} onclick={() => onchange(page + 1)}>Próximo &raquo;</button>
  </div>
{/if}

<style>
  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-4);
    padding: var(--space-4) 0;
  }
  .pg-btn {
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--white);
    color: var(--primary);
    font-size: var(--font-size-sm);
    font-weight: 600;
    transition: background 0.15s;
  }
  .pg-btn:hover:not(:disabled) {
    background: var(--blue-100);
  }
  .pg-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .pg-info {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
  }
</style>
