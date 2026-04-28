<script>
  let { size = 'full', name = 'BankCorp' } = $props();
</script>

{#if size === 'icon'}
  <svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36" fill="none" aria-label={name}>
    <rect width="36" height="36" rx="8" fill="var(--primary)"/>
    <path d="M23 36 L36 23 L36 36 Z" fill="var(--accent)" opacity="0.55"/>
    <text x="18" y="15.5" text-anchor="middle" font-family="Inter,system-ui,sans-serif" font-weight="800" font-size="10.5" fill="white" letter-spacing="0.5">BC</text>
    <text x="18" y="28.5" text-anchor="middle" font-family="Inter,system-ui,sans-serif" font-weight="700" font-size="7.5" fill="var(--accent)" letter-spacing="0.5">BANK</text>
  </svg>
{:else}
  <svg xmlns="http://www.w3.org/2000/svg" width="176" height="36" viewBox="0 0 176 36" fill="none" aria-label={name}>
    <!-- Icon block -->
    <rect width="36" height="36" rx="8" fill="var(--primary)"/>
    <path d="M23 36 L36 23 L36 36 Z" fill="var(--accent)" opacity="0.55"/>
    <text x="18" y="15.5" text-anchor="middle" font-family="Inter,system-ui,sans-serif" font-weight="800" font-size="10.5" fill="white" letter-spacing="0.5">BC</text>
    <text x="18" y="28.5" text-anchor="middle" font-family="Inter,system-ui,sans-serif" font-weight="700" font-size="7.5" fill="var(--accent)" letter-spacing="0.5">BANK</text>
    <!-- Text -->
    <text x="48" y="21" font-family="Inter,system-ui,sans-serif" font-weight="800" font-size="16" fill="var(--primary)" letter-spacing="-0.5">BankCorp</text>
    <text x="48" y="32" font-family="Inter,system-ui,sans-serif" font-weight="500" font-size="8" fill="#9CA3AF" letter-spacing="2.2">R.18 COMPLIANCE</text>
  </svg>
{/if}
