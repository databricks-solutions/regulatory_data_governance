<script>
  let { title = '', onToggleSidebar, dataBase = '2026-03', onDataBaseChange, alertCount = 0, onOpenBrandSettings, theme = 'light', onToggleTheme } = $props();

  const dataBaseOptions = [
    '2026-03', '2026-02', '2026-01', '2025-12', '2025-11', '2025-10'
  ];

  function formatDataBaseLabel(db) {
    const [year, month] = db.split('-');
    const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
    return `${months[parseInt(month) - 1]} ${year}`;
  }
</script>

<header class="header">
  <div class="header-left">
    <button class="hamburger" onclick={onToggleSidebar} aria-label="Toggle menu">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M3 12h18M3 6h18M3 18h18" />
      </svg>
    </button>
    <div class="header-title-area">
      <h1 class="header-title">{title}</h1>
    </div>
  </div>

  <div class="header-right">
    <div class="db-selector">
      <svg class="db-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
      </svg>
      <span class="db-label">Data-Base</span>
      <select
        class="db-select"
        value={dataBase}
        onchange={(e) => onDataBaseChange(e.target.value)}
      >
        {#each dataBaseOptions as opt}
          <option value={opt}>{formatDataBaseLabel(opt)}</option>
        {/each}
      </select>
    </div>

    <div class="header-divider"></div>

    <button class="icon-btn" aria-label="Alertas">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />
      </svg>
      {#if alertCount > 0}
        <span class="alert-badge">{alertCount}</span>
      {/if}
    </button>

    <button class="icon-btn" onclick={onToggleTheme} aria-label={theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro'} title={theme === 'dark' ? 'Modo claro' : 'Modo escuro'}>
      {#if theme === 'dark'}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
        </svg>
      {:else}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      {/if}
    </button>

    <button class="icon-btn" onclick={onOpenBrandSettings} aria-label="Configurações de marca" title="Configurações de marca">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
      </svg>
    </button>
  </div>
</header>

<style>
  .header {
    height: var(--header-height);
    background: var(--white);
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--space-6);
    position: sticky;
    top: 0;
    z-index: 50;
  }
  .header-left { display: flex; align-items: center; gap: var(--space-4); }
  .hamburger {
    background: none;
    border: none;
    padding: var(--space-2);
    color: var(--gray-500);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all var(--transition-fast);
    width: 36px;
    height: 36px;
  }
  .hamburger:hover { background: var(--gray-100); color: var(--gray-700); }
  .header-title-area { display: flex; flex-direction: column; }
  .header-title {
    font-size: var(--font-size-lg);
    font-weight: 700;
    color: var(--gray-900);
    letter-spacing: -0.02em;
  }
  .header-right { display: flex; align-items: center; gap: var(--space-3); }
  .header-divider { width: 1px; height: 24px; background: var(--gray-200); }

  .db-selector {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    background: var(--gray-50);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    transition: all var(--transition-fast);
  }
  .db-selector:hover { border-color: var(--blue-300); background: var(--blue-50); }
  .db-icon { color: var(--gray-500); flex-shrink: 0; }
  .db-label { font-size: var(--font-size-xs); font-weight: 600; color: var(--gray-500); white-space: nowrap; }
  .db-select {
    padding: 0;
    border: none;
    font-size: var(--font-size-sm);
    font-family: var(--font-primary);
    font-weight: 600;
    color: var(--primary);
    background: transparent;
    cursor: pointer;
    appearance: auto;
    outline: none;
  }

  .icon-btn {
    position: relative;
    background: none;
    border: none;
    padding: var(--space-2);
    color: var(--gray-500);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    transition: all var(--transition-fast);
  }
  .icon-btn:hover { background: var(--gray-100); color: var(--gray-700); }
  .alert-badge {
    position: absolute;
    top: 2px;
    right: 2px;
    background: var(--error);
    color: white;
    font-size: 9px;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    padding: 0 4px;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px solid var(--white);
    line-height: 1;
  }
</style>
