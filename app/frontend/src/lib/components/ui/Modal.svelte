<script>
  import { fade, scale } from 'svelte/transition';
  import { _ } from 'svelte-i18n';

  let { open = false, title = '', onclose, children } = $props();
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="modal-backdrop" transition:fade={{ duration: 150 }} onclick={onclose}>
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="modal-content" transition:scale={{ duration: 200, start: 0.96 }} onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>{title}</h3>
        <button class="modal-close" onclick={onclose} aria-label={$_('common.close')}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </div>
      <div class="modal-body">
        {@render children()}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 17, 23, 0.5);
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: var(--space-6);
  }
  .modal-content {
    background: var(--white);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-xl);
    width: 100%;
    max-width: 560px;
    max-height: 80vh;
    overflow-y: auto;
    border: 1px solid var(--border-color);
  }
  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--border-color);
  }
  .modal-header h3 {
    margin: 0;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .modal-close {
    background: none;
    border: none;
    color: var(--gray-400);
    padding: var(--space-2);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-fast);
  }
  .modal-close:hover {
    color: var(--gray-700);
    background: var(--gray-100);
  }
  .modal-body {
    padding: var(--space-6);
  }
</style>
