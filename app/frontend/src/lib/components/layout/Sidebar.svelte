<script>
  import { page } from '$app/stores';
  import DefaultLogo from '$lib/components/ui/DefaultLogo.svelte';

  let { collapsed = false, brandConfig = { name: 'RC18 StarterKit', logo_url: null } } = $props();

  const sections = [
    {
      title: null,
      items: [
        { label: 'Dashboard', href: '/', icon: 'grid' }
      ]
    },
    {
      title: 'Monitoramento',
      items: [
        { label: 'Qualidade R.18', href: '/quality', icon: 'shield' },
        { label: 'Críticas SCR', href: '/validations', icon: 'check' }
      ]
    },
    {
      title: 'Gestão de Regras',
      items: [
        { label: 'Motor de Regras', href: '/rules', icon: 'engine' }
      ]
    },
    {
      title: 'Governança',
      items: [
        { label: 'Gestão de Incidentes', href: '/governance', icon: 'alert' }
      ]
    },
    {
      title: 'Exploração',
      items: [
        { label: 'Lineage', href: '/lineage', icon: 'flow' },
        { label: 'Visualizador XML', href: '/xml', icon: 'code' },
        { label: 'Consulta Natural', href: '/genie', icon: 'sparkle' }
      ]
    },
    {
      title: 'Painéis',
      items: [
        { label: 'Conformidade R.18', href: '/dashboards/conformidade', icon: 'chart' },
        { label: 'Monitor de Críticas', href: '/dashboards/criticas', icon: 'chart' }
      ]
    },
    {
      title: 'Referência',
      items: [
        { label: 'Dados de Referência', href: '/reference', icon: 'book' }
      ]
    }
  ];

  function isActive(href, currentPath) {
    if (href === '/') return currentPath === '/';
    return currentPath.startsWith(href);
  }

  const icons = {
    grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
    shield: 'M12 2l7 4v6c0 5.25-3.5 9.74-7 11-3.5-1.26-7-5.75-7-11V6l7-4z',
    check: 'M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11',
    layers: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
    flow: 'M5 3v4M3 5h4M5 9a4 4 0 006 3.5M19 21v-4M17 19h4M19 15a4 4 0 00-6-3.5M12 12a3 3 0 100-6 3 3 0 000 6z',
    code: 'M16 18l6-6-6-6M8 6l-6 6 6 6',
    sparkle: 'M12 3v2m0 14v2m9-9h-2M5 12H3m15.364-6.364l-1.414 1.414M7.05 16.95l-1.414 1.414m12.728 0l-1.414-1.414M7.05 7.05L5.636 5.636M12 8a4 4 0 100 8 4 4 0 000-8z',
    chart: 'M3 3v18h18M7 16V8m4 8v-5m4 5V5m4 11V9',
    alert: 'M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4m0 4h.01',
    book: 'M4 19.5A2.5 2.5 0 016.5 17H20M4 4.5A2.5 2.5 0 016.5 2H20v20H6.5a2.5 2.5 0 010-5',
    engine: 'M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 0V6m6 10v2m0-2a2 2 0 100-4m0 4a2 2 0 110-4'
  };
</script>

<aside class="sidebar" class:collapsed>
  <div class="sidebar-header">
    {#if !collapsed}
      <a href="/" class="logo-area">
        {#if brandConfig.logo_url}
          <img src={brandConfig.logo_url} alt={brandConfig.name} class="logo-custom" />
        {:else}
          <DefaultLogo size="full" name={brandConfig.name} />
        {/if}
      </a>
    {:else}
      <a href="/" class="logo-collapsed-link">
        {#if brandConfig.logo_url}
          <img src={brandConfig.logo_url} alt={brandConfig.name} class="logo-icon" />
        {:else}
          <DefaultLogo size="icon" name={brandConfig.name} />
        {/if}
      </a>
    {/if}
  </div>

  <nav class="sidebar-nav">
    {#each sections as section}
      {#if section.title && !collapsed}
        <div class="nav-section-title">{section.title}</div>
      {/if}
      {#each section.items as item}
        <a
          href={item.href}
          class="nav-item"
          class:active={isActive(item.href, $page.url.pathname)}
          title={collapsed ? item.label : ''}
        >
          <div class="nav-icon-wrapper" class:active={isActive(item.href, $page.url.pathname)}>
            <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d={icons[item.icon]} />
            </svg>
          </div>
          {#if !collapsed}
            <span class="nav-label">{item.label}</span>
          {/if}
          {#if !collapsed && isActive(item.href, $page.url.pathname)}
            <div class="active-indicator"></div>
          {/if}
        </a>
      {/each}
    {/each}
  </nav>

  <div class="sidebar-footer">
    <div class="env-badge">
      {#if !collapsed}
        <span class="env-dot"></span>
        <span class="env-text">R.18 Compliance</span>
      {:else}
        <span class="env-dot center"></span>
      {/if}
    </div>
    {#if !collapsed}
      <div class="user-info">
        <div class="user-avatar">
          <span>JV</span>
        </div>
        <div class="user-detail">
          <div class="user-name">Analista</div>
          <div class="user-role">Operacional</div>
        </div>
        <svg class="user-menu-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
        </svg>
      </div>
    {:else}
      <div class="user-avatar small">
        <span>JV</span>
      </div>
    {/if}
  </div>
</aside>

<style>
  .sidebar {
    width: var(--sidebar-width);
    height: 100vh;
    background: var(--white);
    border-right: 1px solid var(--border-color);
    color: var(--gray-800);
    display: flex;
    flex-direction: column;
    position: fixed;
    left: 0;
    top: 0;
    z-index: 100;
    transition: width var(--transition-base);
    overflow-x: hidden;
    overflow-y: auto;
  }
  .sidebar.collapsed {
    width: var(--sidebar-collapsed-width);
  }

  .sidebar-header {
    padding: var(--space-5) var(--space-5);
    min-height: 72px;
    display: flex;
    align-items: center;
    border-bottom: 1px solid var(--border-color);
  }
  .logo-area {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    text-decoration: none;
  }
  .logo-custom {
    height: 36px;
    max-width: 160px;
    width: auto;
    object-fit: contain;
    flex-shrink: 0;
  }
  .logo-collapsed-link {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    text-decoration: none;
  }
  .logo-icon {
    width: 34px;
    height: 34px;
    object-fit: contain;
  }

  .sidebar-nav {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-3) var(--space-3);
  }
  .nav-section-title {
    font-size: var(--font-size-xs);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    color: var(--gray-500);
    padding: var(--space-5) var(--space-3) var(--space-2);
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    color: var(--gray-600);
    text-decoration: none;
    font-size: var(--font-size-base);
    font-weight: 500;
    border-radius: var(--radius-md);
    margin: 1px 0;
    transition: all var(--transition-fast);
    white-space: nowrap;
    position: relative;
  }
  .sidebar.collapsed .nav-item {
    justify-content: center;
    padding: var(--space-2) var(--space-2);
  }
  .nav-item:hover {
    background: var(--blue-50);
    color: var(--blue-700);
    text-decoration: none;
  }
  .nav-item.active {
    background: var(--blue-50);
    color: var(--primary);
    font-weight: 600;
  }

  .nav-icon-wrapper {
    width: 32px;
    height: 32px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all var(--transition-fast);
  }
  .nav-icon-wrapper.active {
    background: var(--primary);
    color: white;
    box-shadow: var(--shadow-blue);
  }
  .nav-icon { width: 16px; height: 16px; }
  .nav-label { flex: 1; }

  .active-indicator {
    width: 4px;
    height: 16px;
    background: var(--primary);
    border-radius: var(--radius-full);
    position: absolute;
    right: 0;
  }

  .sidebar-footer {
    padding: var(--space-3) var(--space-3);
    border-top: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .env-badge {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    background: var(--success-light);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--success);
  }
  .env-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--success);
    flex-shrink: 0;
    animation: pulse-dot 2s ease-in-out infinite;
  }
  .env-dot.center { margin: 0 auto; }
  .env-text { white-space: nowrap; }

  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .user-info {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md);
    transition: background var(--transition-fast);
    cursor: pointer;
  }
  .user-info:hover { background: var(--gray-100); }
  .user-avatar {
    width: 34px;
    height: 34px;
    border-radius: var(--radius-md);
    background: linear-gradient(135deg, var(--primary), var(--blue-600));
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--font-size-xs);
    font-weight: 700;
    color: white;
    flex-shrink: 0;
    letter-spacing: 0.02em;
  }
  .user-avatar.small { width: 32px; height: 32px; font-size: 10px; margin: 0 auto; }
  .user-name { font-size: var(--font-size-sm); font-weight: 600; color: var(--gray-800); }
  .user-role { font-size: var(--font-size-xs); color: var(--gray-500); }
  .user-detail { flex: 1; min-width: 0; }
  .user-menu-icon { width: 16px; height: 16px; color: var(--gray-400); flex-shrink: 0; }
</style>
