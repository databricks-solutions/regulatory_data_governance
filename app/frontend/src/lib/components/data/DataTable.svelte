<script>
  let { columns, data = [], sortable = true, onRowClick = null, emptyMessage = 'Nenhum dado encontrado', expandedRow = null, expandSnippet = null } = $props();

  let sortColumn = $state(null);
  let sortDirection = $state('asc');

  function handleSort(col) {
    if (!sortable || !col.sortable) return;
    if (sortColumn === col.key) {
      sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = col.key;
      sortDirection = 'asc';
    }
  }

  let sortedData = $derived.by(() => {
    if (!sortColumn) return data;
    const col = columns.find(c => c.key === sortColumn);
    if (!col) return data;
    return [...data].sort((a, b) => {
      const va = a[sortColumn];
      const vb = b[sortColumn];
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp = typeof va === 'number' ? va - vb : String(va).localeCompare(String(vb), 'pt-BR');
      return sortDirection === 'asc' ? cmp : -cmp;
    });
  });
</script>

<div class="table-container">
  {#if data.length === 0}
    <div class="table-empty">{emptyMessage}</div>
  {:else}
    <table class="data-table">
      <thead>
        <tr>
          {#each columns as col}
            <th
              class:sortable={sortable && col.sortable}
              style={col.width ? `width: ${col.width}` : ''}
              onclick={() => handleSort(col)}
            >
              {col.label}
              {#if sortColumn === col.key}
                <span class="sort-icon">{sortDirection === 'asc' ? '\u25B2' : '\u25BC'}</span>
              {/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each sortedData as row, i}
          <tr
            class:clickable={!!onRowClick}
            class:expanded={expandedRow === i}
            onclick={() => onRowClick?.(row, i)}
          >
            {#each columns as col}
              <td>
                {#if col.render}
                  {@html col.render(row[col.key], row)}
                {:else}
                  {row[col.key] ?? '-'}
                {/if}
              </td>
            {/each}
          </tr>
          {#if expandedRow === i && expandSnippet}
            <tr class="expand-row">
              <td colspan={columns.length}>
                {@render expandSnippet(row)}
              </td>
            </tr>
          {/if}
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .table-container {
    overflow-x: auto;
  }
  .data-table {
    width: 100%;
    border-collapse: collapse;
  }
  .data-table th {
    background: var(--blue-100);
    color: var(--blue-900);
    font-weight: 600;
    font-size: var(--font-size-sm);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: var(--space-3) var(--space-4);
    border-bottom: 2px solid var(--primary);
    text-align: left;
    white-space: nowrap;
    user-select: none;
  }
  th.sortable {
    cursor: pointer;
  }
  th.sortable:hover {
    background: var(--blue-300);
    color: var(--white);
  }
  .sort-icon {
    font-size: var(--font-size-xs);
    margin-left: var(--space-1);
  }
  .data-table td {
    padding: var(--space-3) var(--space-4);
    border-bottom: var(--border-width) solid var(--border-color);
    font-size: var(--font-size-base);
  }
  .data-table tbody tr:nth-child(even) {
    background: var(--gray-100);
  }
  tr.clickable {
    cursor: pointer;
  }
  tr.clickable:hover {
    background: var(--blue-100) !important;
  }
  tr.expanded {
    background: var(--blue-100) !important;
  }
  .expand-row td {
    padding: var(--space-4) var(--space-5);
    background: var(--blue-100);
    border-bottom: 2px solid var(--primary);
  }
  .table-empty {
    padding: var(--space-10);
    text-align: center;
    color: var(--gray-500);
    font-size: var(--font-size-base);
  }
</style>
