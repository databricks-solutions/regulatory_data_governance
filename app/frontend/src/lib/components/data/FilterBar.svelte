<script>
  import { _ } from 'svelte-i18n';

  let { filters = [], values = {}, onchange, onreset } = $props();
</script>

<div class="filter-bar">
  {#each filters as f}
    <div class="filter-group">
      <label class="filter-label">{f.label}</label>
      {#if f.type === 'select'}
        <select
          class="filter-select"
          value={values[f.key] || ''}
          onchange={(e) => onchange(f.key, e.target.value || null)}
        >
          <option value="">{$_('ui.filterAll')}</option>
          {#each f.options as opt}
            <option value={opt.value}>{opt.label}</option>
          {/each}
        </select>
      {:else}
        <input
          class="filter-input"
          type="text"
          placeholder={f.placeholder || ''}
          value={values[f.key] || ''}
          oninput={(e) => onchange(f.key, e.target.value || null)}
        />
      {/if}
    </div>
  {/each}
  {#if onreset}
    <button class="filter-reset" onclick={onreset}>{$_('ui.clearFilters')}</button>
  {/if}
</div>

<style>
  .filter-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-4);
    padding: var(--space-4);
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    margin-bottom: var(--space-4);
  }
  .filter-group {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .filter-label {
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--gray-500);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .filter-select, .filter-input {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-sm);
    font-family: var(--font-primary);
    background: var(--white);
    color: var(--gray-900);
    min-width: 140px;
  }
  .filter-select:focus, .filter-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 2px var(--blue-100);
  }
  .filter-reset {
    padding: var(--space-2) var(--space-4);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--white);
    color: var(--gray-700);
    font-size: var(--font-size-sm);
    font-weight: 600;
  }
  .filter-reset:hover {
    background: var(--gray-100);
  }
</style>
