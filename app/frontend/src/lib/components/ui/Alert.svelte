<script>
  let { message, severity = 'info' } = $props();
</script>

<div class="alert alert-{severity}" role="alert">
  <div class="alert-icon-box">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      {#if severity === 'error'}
        <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/>
      {:else if severity === 'warning'}
        <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/>
      {:else if severity === 'success'}
        <path d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0Z"/>
      {:else}
        <path d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0Zm-9-3.75h.008v.008H12V8.25Z"/>
      {/if}
    </svg>
  </div>
  <span class="alert-msg">{message}</span>
</div>

<style>
  .alert {
    display: flex;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
    font-size: var(--font-size-sm);
    font-weight: 500;
  }
  .alert-icon-box {
    width: 24px;
    height: 24px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .alert-info    { background: var(--info-light); color: var(--primary); }
  .alert-info .alert-icon-box { background: rgba(0, 92, 169, 0.1); }
  .alert-warning { background: var(--warning-light); color: var(--orange-900); }
  .alert-warning .alert-icon-box { background: rgba(243, 112, 33, 0.1); }
  .alert-error   { background: var(--error-light); color: var(--error); }
  .alert-error .alert-icon-box { background: rgba(219, 68, 55, 0.1); }
  .alert-success { background: var(--success-light); color: var(--success); }
  .alert-success .alert-icon-box { background: rgba(15, 157, 88, 0.1); }
  .alert-msg { line-height: 1.5; padding-top: 2px; }
</style>
