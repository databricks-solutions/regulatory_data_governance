<script>
  import Spinner from './Spinner.svelte';
  import { getDashboardEmbed } from '$lib/api.js';
  import { _ } from 'svelte-i18n';

  let { dashboardKey, title = 'Painel' } = $props();
  let embedUrl = $state('');
  let publishedUrl = $state('');
  let dashboardId = $state('');
  let loading = $state(true);
  let error = $state('');
  let isDatabricksHost = $state(false);
  let iframeError = $state(false);

  const DASHBOARD_KEYS = ['conformidade', 'criticas', 'genie'];
  function dashboardTitle(key) {
    return DASHBOARD_KEYS.includes(key) ? $_(`dashboardEmbed.title_${key}`) : title;
  }
  function dashboardDescription(key) {
    return DASHBOARD_KEYS.includes(key) ? $_(`dashboardEmbed.desc_${key}`) : '';
  }

  /**
   * Derive the Databricks workspace URL and workspace ID from the app URL.
   * App URL pattern: {app-name}-{workspace-id}.{region}.azure.databricksapps.com
   * Workspace URL:   adb-{workspace-id}.{region}.azuredatabricks.net
   */
  function getWorkspaceInfo() {
    if (typeof window === 'undefined') return { url: '', workspaceId: '' };
    const hostname = window.location.hostname;

    // Match Databricks Apps host: <app-name>-<workspace-id>.<region>.azure.databricksapps.com
    const match = hostname.match(/\w+-(\d+)\.(\d+)\.azure\.databricksapps\.com/);
    if (match) {
      return {
        url: `https://adb-${match[1]}.${match[2]}.azuredatabricks.net`,
        workspaceId: match[1]
      };
    }

    // Already on workspace URL: adb-<workspace-id>.<region>.azuredatabricks.net
    const wsMatch = hostname.match(/adb-(\d+)\.\d+\.azuredatabricks\.net/);
    if (wsMatch) {
      return { url: window.location.origin, workspaceId: wsMatch[1] };
    }

    // Local dev or unknown host
    return { url: '', workspaceId: '' };
  }

  function buildPublishedFromEmbed(key, embed) {
    if (!embed) return '';
    const { url: wsUrl, workspaceId } = getWorkspaceInfo();
    if (key === 'genie') return embed;
    // Convert /embed/dashboardsv3/<id>?o=<ws> → /dashboardsv3/<id>/published?o=<ws>
    const m = embed.match(/dashboardsv3\/([^?]+)/);
    if (m && wsUrl) {
      return `${wsUrl}/dashboardsv3/${m[1]}/published?o=${workspaceId}`;
    }
    return embed;
  }

  function checkDatabricksHost() {
    if (typeof window === 'undefined') return false;
    const h = window.location.hostname;
    return h.includes('databricksapps') || h.includes('azuredatabricks') || h.includes('.cloud.');
  }

  // Use onMount pattern to avoid effect loop
  import { onMount } from 'svelte';
  onMount(() => {
    isDatabricksHost = checkDatabricksHost();

    if (!isDatabricksHost) {
      loading = false;
      error = 'local';
      return;
    }

    getDashboardEmbed(dashboardKey)
      .then(data => {
        embedUrl = data.embed_url;
        dashboardId = data.dashboard_id || '';
        publishedUrl = buildPublishedFromEmbed(dashboardKey, data.embed_url);
        loading = false;
      })
      .catch(() => {
        error = $_('dashboardEmbed.loadError');
        loading = false;
      });
  });
</script>

<div class="embed-wrap">
  {#if loading}
    <Spinner message={$_('dashboardEmbed.loading')} />
  {:else if error === 'local'}
    <div class="embed-placeholder local-preview">
      <div class="placeholder-icon">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="1.2">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
          <circle cx="7" cy="6" r="0.8" fill="var(--accent)" />
          <circle cx="10" cy="6" r="0.8" fill="var(--accent)" />
          <circle cx="13" cy="6" r="0.8" fill="var(--accent)" />
          <rect x="11" y="12" width="8" height="3" rx="0.5" fill="var(--primary)" opacity="0.2" />
          <rect x="11" y="16.5" width="5" height="2" rx="0.5" fill="var(--primary)" opacity="0.15" />
        </svg>
      </div>
      <p class="placeholder-title">{dashboardTitle(dashboardKey)}</p>
      <p class="placeholder-desc">{dashboardDescription(dashboardKey)}</p>
      <div class="placeholder-badge">
        <span class="badge-dot"></span>
        {$_('dashboardEmbed.availableAfterDeploy')}
      </div>
      <p class="placeholder-id">
        {dashboardKey === 'genie' ? $_('dashboardEmbed.genieAfterDeploy') : `Dashboard: ${dashboardId || '—'}`}
      </p>
    </div>
  {:else if error}
    <div class="embed-placeholder">
      <div class="placeholder-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
        </svg>
      </div>
      <p class="placeholder-title">{title}</p>
      <p class="placeholder-msg">{error}</p>
    </div>
  {:else}
    <div class="embed-with-link">
      <div class="embed-topbar">
        <span class="embed-topbar-title">{dashboardTitle(dashboardKey)}</span>
        <a href={publishedUrl || embedUrl} target="_blank" rel="noopener noreferrer" class="open-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
          {$_('dashboardEmbed.openInDatabricks')}
        </a>
      </div>
      <iframe
        src={embedUrl}
        title={dashboardTitle(dashboardKey)}
        width="100%"
        height="100%"
        frameborder="0"
        allow="fullscreen"
      ></iframe>
    </div>
  {/if}
</div>

<style>
  .embed-wrap {
    width: 100%;
    height: calc(100vh - var(--header-height) - 100px);
    min-height: 400px;
    border-radius: var(--radius-md);
    overflow: hidden;
    background: var(--white);
    border: 1px solid var(--border-color);
  }
  iframe {
    display: block;
  }
  .embed-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: var(--space-4);
    color: var(--gray-500);
  }
  .placeholder-icon { opacity: 0.3; }
  .placeholder-title {
    font-size: var(--font-size-lg);
    font-weight: 700;
    color: var(--gray-700);
  }
  .placeholder-msg {
    font-size: var(--font-size-sm);
  }
  .local-preview {
    background: linear-gradient(135deg, var(--gray-50), var(--white));
  }
  .placeholder-desc {
    font-size: var(--font-size-sm);
    color: var(--gray-500);
    max-width: 400px;
    text-align: center;
    line-height: 1.5;
  }
  .placeholder-badge {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--font-size-xs);
    color: var(--primary);
    background: color-mix(in srgb, var(--primary) 8%, transparent);
    padding: 6px 14px;
    border-radius: 999px;
    font-weight: 600;
  }
  .badge-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
  }
  .placeholder-id {
    font-size: 11px;
    color: var(--gray-400);
    font-family: var(--font-mono);
  }
  .embed-with-link {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .embed-with-link iframe {
    display: block;
    flex: 1;
    width: 100%;
    border: none;
  }
  .embed-topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    background: var(--gray-50);
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }
  .embed-topbar-title {
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--gray-700);
  }
  .open-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    background: var(--primary);
    color: white;
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-decoration: none;
    transition: background 0.15s;
  }
  .open-btn:hover {
    background: color-mix(in srgb, var(--primary) 85%, black);
  }
</style>
