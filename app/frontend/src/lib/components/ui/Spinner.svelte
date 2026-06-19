<script>
  import { _ } from 'svelte-i18n';

  let { message = null } = $props();

  let displayMessage = $derived(message ?? $_('common.loading'));
</script>

<div class="spinner-wrap">
  <div class="spinner">
    <div class="spinner-ring"></div>
  </div>
  {#if displayMessage}<p class="spinner-msg">{displayMessage}</p>{/if}
</div>

<style>
  .spinner-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--space-12);
    gap: var(--space-4);
  }
  .spinner {
    position: relative;
    width: 36px;
    height: 36px;
  }
  .spinner-ring {
    width: 36px;
    height: 36px;
    border: 3px solid var(--gray-200);
    border-top-color: var(--primary);
    border-right-color: var(--primary);
    border-radius: 50%;
    animation: spin 0.8s cubic-bezier(0.5, 0, 0.5, 1) infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  .spinner-msg {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
    font-weight: 500;
  }
</style>
