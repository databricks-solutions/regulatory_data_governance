<script>
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { invalidateAll } from '$app/navigation';
  import Sidebar from '$lib/components/layout/Sidebar.svelte';
  import Header from '$lib/components/layout/Header.svelte';
  import BrandSettings from '$lib/components/ui/BrandSettings.svelte';
  import { appState, toggleSidebar, setDataBase, toggleTheme, applyTheme } from '$lib/stores.svelte.js';
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
  });

  function handleBrandUpdate(newConfig) {
    Object.assign(brandConfig, newConfig);
    applyBrandColors(newConfig.primary_color, newConfig.accent_color);
    writeCache(newConfig);
  }

  // --- Page titles ---
  const pageTitles = {
    '/': 'Painel de Conformidade R.18',
    '/quality': 'Qualidade R.18',
    '/validations': 'Críticas SCR',
    '/reconciliation': 'Reconciliação',
    '/lineage': 'Lineage',
    '/xml': 'Visualizador XML',
    '/genie': 'Consulta Natural',
    '/dashboards/conformidade': 'Conformidade R.18',
    '/dashboards/criticas': 'Monitor de Críticas',
    '/dashboards/reconciliacao': 'Reconciliação Executiva',
    '/reference': 'Dados de Referência',
    '/governance': 'Gestão de Incidentes',
    '/rules': 'Motor de Regras'
  };

  let currentTitle = $derived.by(() => {
    const path = $page.url.pathname;
    if (pageTitles[path]) return pageTitles[path];
    if (path.startsWith('/rules/results/')) return 'Resultados da Execucao';
    if (path.startsWith('/rules/datasets/')) return 'Detalhe do Dataset';
    if (path.startsWith('/rules')) return 'Motor de Regras';
    if (path.startsWith('/quality/')) return 'Dimensao R.18';
    if (path.startsWith('/reconciliation/')) return 'Reconciliacao';
    return 'R.18 Compliance';
  });

  function handleDataBaseChange(val) {
    setDataBase(val);
    invalidateAll();
  }
</script>

<div class="app-shell" class:sidebar-collapsed={appState.sidebarCollapsed}>
  <Sidebar collapsed={appState.sidebarCollapsed} {brandConfig} />
  <div class="main-area">
    <Header
      title={currentTitle}
      onToggleSidebar={toggleSidebar}
      dataBase={appState.dataBase}
      onDataBaseChange={handleDataBaseChange}
      alertCount={appState.alertCount}
      onOpenBrandSettings={() => showBrandSettings = true}
      theme={appState.theme}
      onToggleTheme={toggleTheme}
    />
    <main class="content">
      <div class="content-inner">
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
</style>
