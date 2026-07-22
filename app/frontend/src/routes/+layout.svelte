<script>
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { invalidateAll } from '$app/navigation';
  import { _ } from 'svelte-i18n';
  import Sidebar from '$lib/components/layout/Sidebar.svelte';
  import Header from '$lib/components/layout/Header.svelte';
  import BrandSettings from '$lib/components/ui/BrandSettings.svelte';
  import { appState, toggleSidebar, setDataBase, setDataBaseOptions, toggleTheme, applyTheme } from '$lib/stores.svelte.js';
  import { getDataBases } from '$lib/api.js';
  import '../app.css';

  if (browser) applyTheme(appState.theme);

  let { children } = $props();

  const CACHE_KEY = 'rc18_brand_config';
  const DEFAULT_CONFIG = {
    name: 'BankCorp',
    primary_color: '#1E293B',
    accent_color: '#0EA5E9',
    logo_url: null,
    theme_preset: 'slate'
  };

  // --- Read cache synchronously before first render ---
  let cachedConfig = null;
  if (browser) {
    try { cachedConfig = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null'); }
    catch (_) {}
  }

  let brandConfig = $state(cachedConfig ?? { ...DEFAULT_CONFIG });
  let showBrandSettings = $state(false);

  function applyBrandColors(primary, accent) {
    document.documentElement.style.setProperty('--primary', primary);
    document.documentElement.style.setProperty('--accent', accent);
  }

  function writeCache(config) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(config)); }
    catch (_) {}
  }

  // Apply colors from cache immediately — runs before DOM paint
  if (browser && cachedConfig) {
    applyBrandColors(cachedConfig.primary_color, cachedConfig.accent_color);
  }

  // Fetch latest from API in background; update cache if changed
  onMount(async () => {
    try {
      const res = await fetch('/api/v1/brand/config');
      if (res.ok) {
        const data = await res.json();
        Object.assign(brandConfig, data);
        applyBrandColors(data.primary_color, data.accent_color);
        writeCache(data);
      }
    } catch (_) {}

    // Popula o seletor de Data-Base com o último CADOC processado + as
    // data-bases disponíveis (substitui a lista antes hardcoded no Header).
    try {
      const db = await getDataBases();
      if (db) setDataBaseOptions(db);
    } catch (_) {}
  });

  function handleBrandUpdate(newConfig) {
    Object.assign(brandConfig, newConfig);
    applyBrandColors(newConfig.primary_color, newConfig.accent_color);
    writeCache(newConfig);
  }

  // --- Page titles --- (values are i18n keys under `titles.*`)
  const pageTitles = {
    '/': 'titles.home',
    '/quality': 'titles.quality',
    '/validations': 'titles.validations',
    '/lineage': 'titles.lineage',
    '/xml': 'titles.xml',
    '/genie': 'titles.genie',
    '/dashboards/conformidade': 'titles.dashboardConformidade',
    '/dashboards/criticas': 'titles.dashboardCriticas',
    '/reference': 'titles.reference',
    '/governance': 'titles.governance',
    '/rules': 'titles.rules',
    '/linking': 'titles.linking'
  };

  let currentTitle = $derived.by(() => {
    const path = $page.url.pathname;
    if (pageTitles[path]) return $_(pageTitles[path]);
    if (path.startsWith('/rules/catalogo/') && path.endsWith('/editar')) return $_('titles.rulesEdit');
    if (path.startsWith('/rules/catalogo')) return $_('titles.rulesCatalog');
    if (path.startsWith('/rules/criar/tabela-unica')) return $_('titles.rulesCreate');
    if (path.startsWith('/rules/criar')) return $_('titles.rulesCreate');
    if (path.startsWith('/rules/execucoes/')) return $_('titles.rulesRunDetail');
    if (path.startsWith('/rules/execucoes')) return $_('titles.rulesRuns');
    if (path.startsWith('/rules')) return $_('titles.rules');
    if (path.startsWith('/quality/')) return $_('titles.qualityDimension');
    return $_('titles.fallback');
  });

  function handleDataBaseChange(val) {
    setDataBase(val);
    invalidateAll();
  }

  // The /rules page embeds DQX Studio in an iframe — let it use the full
  // content width instead of the global 1440px cap, so the embedded Studio
  // gets as much horizontal room as possible.
  let isFullWidthPage = $derived(/^\/rules\/?$/.test($page.url.pathname));
</script>

<div class="app-shell" class:sidebar-collapsed={appState.sidebarCollapsed}>
  <Sidebar collapsed={appState.sidebarCollapsed} {brandConfig} />
  <div class="main-area">
    <Header
      title={currentTitle}
      onToggleSidebar={toggleSidebar}
      dataBase={appState.dataBase}
      dataBaseOptions={appState.dataBaseOptions}
      onDataBaseChange={handleDataBaseChange}
      alertCount={appState.alertCount}
      onOpenBrandSettings={() => showBrandSettings = true}
      theme={appState.theme}
      onToggleTheme={toggleTheme}
      action={appState.headerAction}
    />
    <main class="content">
      <div class="content-inner" class:full-width={isFullWidthPage}>
        {@render children()}
      </div>
    </main>
  </div>
</div>

{#if showBrandSettings}
  <BrandSettings
    {brandConfig}
    onUpdate={handleBrandUpdate}
    onClose={() => showBrandSettings = false}
  />
{/if}

<style>
  .app-shell {
    display: flex;
    min-height: 100vh;
    background: var(--gray-50);
  }
  .main-area {
    flex: 1;
    margin-left: var(--sidebar-width);
    display: flex;
    flex-direction: column;
    transition: margin-left var(--transition-base);
    min-height: 100vh;
  }
  .sidebar-collapsed .main-area {
    margin-left: var(--sidebar-collapsed-width);
  }
  .content {
    flex: 1;
    padding: var(--space-6) var(--space-8);
  }
  .content-inner {
    max-width: var(--content-max-width);
    width: 100%;
    margin: 0 auto;
  }
  /* DQX Studio iframe page (/rules): drop the max-width cap so the embedded
     Studio spans the full available content width. */
  .content-inner.full-width {
    max-width: none;
  }
</style>
