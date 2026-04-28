<script>
  let { label, variant = 'info' } = $props();
</script>

<span class="badge badge-{variant}">
  <span class="badge-dot"></span>
  {label}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px 3px 8px;
    border-radius: var(--radius-full);
    font-size: var(--font-size-xs);
    font-weight: 600;
    letter-spacing: 0.01em;
    white-space: nowrap;
  }
  .badge-dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .badge-success { background: var(--success-light); color: var(--success); }
  .badge-success .badge-dot { background: var(--success); }
  .badge-warning { background: var(--warning-light); color: var(--orange-900); }
  .badge-warning .badge-dot { background: var(--warning); }
  .badge-error   { background: var(--error-light); color: var(--error); }
  .badge-error .badge-dot   { background: var(--error); }
  .badge-info    { background: var(--info-light); color: var(--primary); }
  .badge-info .badge-dot    { background: var(--primary); }
  .badge-neutral { background: var(--gray-100); color: var(--gray-600); }
  .badge-neutral .badge-dot { background: var(--gray-400); }
</style>
