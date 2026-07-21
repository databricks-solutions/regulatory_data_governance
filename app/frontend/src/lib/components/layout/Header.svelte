<script>
  import { _, locale } from 'svelte-i18n';
  import { SUPPORTED_LOCALES, setLocale } from '$lib/i18n';

  let { title = '', onToggleSidebar, dataBase = '', dataBaseOptions = [], onDataBaseChange, alertCount = 0, onOpenBrandSettings, theme = 'light', onToggleTheme, action = null } = $props();

  function formatDataBaseLabel(db) {
    if (!db) return '—';
    const [year, month] = db.split('-');
    const idx = parseInt(month) - 1;
    const months = $_('header.months').split(',');
    if (Number.isNaN(idx) || !months[idx]) return db;
    return `${months[idx]} ${year}`;
  }

  let langOpen = $state(false);
  const currentLang = $derived(SUPPORTED_LOCALES.find((l) => l.code === $locale) ?? SUPPORTED_LOCALES[0]);

  function chooseLang(code) {
    setLocale(code);
    langOpen = false;
  }
</script>

<svelte:window onclick={() => (langOpen = false)} />

<header class="header">
  <div class="header-left">
    <button class="hamburger" onclick={onToggleSidebar} aria-label={$_('header.toggleMenu')}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M3 12h18M3 6h18M3 18h18" />
      </svg>
    </button>
    <div class="header-title-area">
      <h1 class="header-title">{title}</h1>
    </div>
  </div>

  <div class="header-right">
    {#if action}
      <button
        type="button"
        class="header-action"
        onclick={action.onClick}
        title={action.title ?? action.label}
      >
        {action.label}
      </button>
      <div class="header-divider"></div>
    {/if}

    <div class="db-selector">
      <svg class="db-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
      </svg>
      <span class="db-label">{$_('header.dataBase')}</span>
      {#if dataBaseOptions.length > 0}
        <select
          class="db-select"
          value={dataBase}
          onchange={(e) => onDataBaseChange(e.target.value)}
        >
          {#each dataBaseOptions as opt}
            <option value={opt}>{formatDataBaseLabel(opt)}</option>
          {/each}
        </select>
      {:else}
        <span class="db-empty">{dataBase ? formatDataBaseLabel(dataBase) : '—'}</span>
      {/if}
    </div>

    <div class="header-divider"></div>

    <div class="lang-selector">
      <button
        class="icon-btn lang-btn"
        onclick={(e) => { e.stopPropagation(); langOpen = !langOpen; }}
        aria-label={$_('header.language')}
        title={$_('header.language')}
      >
        <span class="lang-code">{currentLang.code.toUpperCase()}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
      </button>
      {#if langOpen}
        <div class="lang-menu" role="menu">
          {#each SUPPORTED_LOCALES as lang}
            <button
              type="button"
              class="lang-option"
              class:active={lang.code === $locale}
              role="menuitemradio"
              aria-checked={lang.code === $locale}
              onclick={(e) => { e.stopPropagation(); chooseLang(lang.code); }}
            >
              <span class="lang-tag">{lang.code.toUpperCase()}</span>
              <span class="lang-name">{lang.label}</span>
              {#if lang.code === $locale}
                <svg class="lang-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
              {/if}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <div class="header-divider"></div>

    <button class="icon-btn" aria-label={$_('header.alerts')}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" />
      </svg>
      {#if alertCount > 0}
        <span class="alert-badge">{alertCount}</span>
      {/if}
    </button>

    <button class="icon-btn" onclick={onToggleTheme} aria-label={theme === 'dark' ? $_('header.activateLight') : $_('header.activateDark')} title={theme === 'dark' ? $_('header.lightMode') : $_('header.darkMode')}>
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

    <button class="icon-btn" onclick={onOpenBrandSettings} aria-label={$_('header.brandSettings')} title={$_('header.brandSettings')}>
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

  .lang-selector { position: relative; }
  .lang-btn {
    width: auto;
    gap: var(--space-1);
    padding: var(--space-2) var(--space-2);
  }
  .lang-code { font-size: var(--font-size-xs); font-weight: 700; color: var(--gray-600); }
  .lang-tag {
    font-size: 10px;
    font-weight: 700;
    color: var(--gray-500);
    width: 22px;
    flex-shrink: 0;
    letter-spacing: 0.02em;
  }
  .lang-menu {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    min-width: 168px;
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg, 0 10px 24px rgba(0,0,0,0.12));
    padding: var(--space-1);
    z-index: 60;
  }
  .lang-option {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    padding: var(--space-2) var(--space-3);
    background: none;
    border: none;
    border-radius: var(--radius-sm);
    font-family: var(--font-primary);
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    cursor: pointer;
    text-align: left;
    transition: background var(--transition-fast);
  }
  .lang-option:hover { background: var(--gray-100); }
  .lang-option.active { color: var(--primary); font-weight: 600; }
  .lang-name { flex: 1; }
  .lang-check { color: var(--primary); flex-shrink: 0; }
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

  .header-action {
    padding: var(--space-2) var(--space-3);
    background: transparent;
    color: var(--primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-family: var(--font-primary);
    font-size: var(--font-size-sm);
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: all var(--transition-fast);
  }
  .header-action:hover { background: var(--blue-50); border-color: var(--primary); }

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
  .db-empty { font-size: var(--font-size-sm); font-weight: 600; color: var(--primary); white-space: nowrap; }

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
