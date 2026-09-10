<script>
  /**
   * Motor de Regras (DQX Studio).
   *
   * Embeds the DQX Studio Databricks App via iframe when `DQX_STUDIO_URL` is
   * configured (exposed by `GET /api/v1/brand/config`). When the URL is empty
   * or the destination refuses to be framed (X-Frame-Options/CSP), we fall
   * back to an explanation panel with a "open in new tab" button.
   *
   * Detection of framing failure uses both `onerror` AND a 5s `onload`
   * timeout — most browsers swallow the X-Frame-Options/CSP block silently
   * (no `onerror` event), so the timeout is the primary safety net while the
   * `onerror` covers true network/DNS errors.
   */
  import { onMount, onDestroy } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { getBrandConfig } from '$lib/api.js';
  import { appState, setHeaderAction } from '$lib/stores.svelte.js';

  let studioUrl = $state('');
  let studioEntryUrlFromConfig = $state('');
  let configLoaded = $state(false);
  let iframeLoaded = $state(false);
  let iframeBlocked = $state(false);
  let timeoutHandle = null;

  // O caminho vem do BACKEND, nunca hardcoded aqui: a Studio renomeia rotas
  // entre versões (o `/rules/active` que este arquivo fixava foi aposentado, e o
  // embed passou a mostrar tela deprecada). Fallback para a base cobre backend
  // antigo com frontend novo.
  let studioEntryUrl = $derived(studioEntryUrlFromConfig || studioUrl);

  // Bumped whenever the sidebar toggles, used as a key on the iframe so it
  // remounts at the new width. Cross-origin iframes (DQX Studio) don't always
  // reflow internally on container resize, so a remount is the reliable fix.
  let iframeKey = $state(0);
  let prevSidebarCollapsed = appState.sidebarCollapsed;
  const SIDEBAR_TRANSITION_MS = 250;

  const DOCS_URL = 'https://databrickslabs.github.io/dqx/docs/guide/dqx_studio/';
  const FRAME_TIMEOUT_MS = 5000;

  let showIframe = $derived(configLoaded && studioUrl && !iframeBlocked);
  let showEmptyState = $derived(configLoaded && !studioUrl);
  let showFallback = $derived(configLoaded && studioUrl && iframeBlocked);

  function handleIframeLoad() {
    iframeLoaded = true;
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
  }

  function handleIframeError() {
    iframeBlocked = true;
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
  }

  function openInNewTab() {
    if (studioEntryUrl) {
      window.open(studioEntryUrl, '_blank', 'noopener,noreferrer');
    }
  }

  onMount(async () => {
    try {
      const cfg = await getBrandConfig();
      studioUrl = (cfg?.dqx_studio_url || '').trim();
      studioEntryUrlFromConfig = (cfg?.dqx_studio_entry_url || '').trim();
    } catch {
      studioUrl = '';
      studioEntryUrlFromConfig = '';
    }
    configLoaded = true;

    // Start the framing-failure timeout AFTER the iframe is mounted.
    // Browsers block via X-Frame-Options/CSP without firing `onerror`, so
    // we treat "no onload within 5s" as blocked.
    if (studioUrl) {
      timeoutHandle = setTimeout(() => {
        if (!iframeLoaded) {
          iframeBlocked = true;
        }
      }, FRAME_TIMEOUT_MS);
    }
  });

  // Register the "Abrir em nova aba" button into the global header whenever
  // DQX Studio is actually embeddable. Cleared on route exit.
  $effect(() => {
    if (configLoaded && studioUrl && !iframeBlocked) {
      setHeaderAction({
        label: $_('rules.openInNewTab'),
        title: $_('rules.openStudioInNewTab'),
        onClick: openInNewTab
      });
    } else {
      setHeaderAction(null);
    }
  });

  onDestroy(() => setHeaderAction(null));

  $effect(() => {
    const collapsed = appState.sidebarCollapsed;
    if (collapsed === prevSidebarCollapsed) return;
    prevSidebarCollapsed = collapsed;
    const id = setTimeout(() => { iframeKey++; }, SIDEBAR_TRANSITION_MS);
    return () => clearTimeout(id);
  });
</script>

<div class="rules-page">
  {#if !configLoaded}
    <div class="loading-pane">{$_('common.loading')}</div>
  {:else if showEmptyState}
    <section class="empty-state card">
      <h3>{$_('rules.emptyTitle')}</h3>
      <p>
        {$_('rules.emptyDescPre')}<strong>DQX Studio</strong>{$_('rules.emptyDescMid1')}
        <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">Databricks Labs DQX</a>
        {$_('rules.emptyDescMid2')}
        (<code>${'{catalog}'}.quality.dqx_checks</code>){$_('rules.emptyDescMid3')}
        <em>Databricks App</em>{$_('rules.emptyDescPost')}
      </p>
      <p>
        {$_('rules.emptyEnablePre')}
        <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">{DOCS_URL}</a>
        {$_('rules.emptyEnableMid')}
        <code>DQX_STUDIO_URL</code>:
      </p>
      <ul class="steps">
        <li>
          <strong>{$_('rules.stepLocalLabel')}</strong> {$_('rules.stepLocalPre')}<code>DQX_STUDIO_URL=https://&lt;dqx-studio-app&gt;.databricksapps.com</code>
          {$_('rules.stepLocalMid')}<code>.env</code>{$_('rules.stepLocalPost')}<code>./run_local.sh</code>).
        </li>
        <li>
          <strong>{$_('rules.stepBundleLabel')}</strong> {$_('rules.stepBundlePre')}<code>DQX_STUDIO_URL</code>{$_('rules.stepBundleMid1')}
          <code>resources/app.yml</code>{$_('rules.stepBundleMid2')}<code>apps.config.env</code>){$_('rules.stepBundleMid3')}
          <code>databricks bundle deploy</code>.
        </li>
      </ul>
      <p class="hint">
        {$_('rules.emptyHint')}
      </p>
    </section>
  {:else if showFallback}
    <section class="fallback-state card">
      <h3>{$_('rules.fallbackTitle')}</h3>
      <p>
        {$_('rules.fallbackDescPre')}<code>X-Frame-Options</code> {$_('rules.fallbackDescOr')}
        <code>Content-Security-Policy</code>{$_('rules.fallbackDescPost')}
      </p>
      <p>
        {$_('rules.fallbackOpenPrompt')}
      </p>
      <button type="button" class="btn-primary" onclick={openInNewTab}>
        {$_('rules.openStudio')}
      </button>
      <p class="hint">
        {$_('rules.endpointConfigured')} <code>{studioUrl}</code>
      </p>
    </section>
  {:else if showIframe}
    <div class="studio-frame-wrap">
      {#key iframeKey}
        <iframe
          class="studio-frame"
          src={studioEntryUrl}
          title={$_('rules.iframeTitle')}
          onload={handleIframeLoad}
          onerror={handleIframeError}
          referrerpolicy="no-referrer-when-downgrade"
          sandbox="allow-forms allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts allow-downloads allow-modals"
        ></iframe>
      {/key}
    </div>
  {/if}
</div>

<style>
  .rules-page {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    height: calc(100vh - 120px);
    min-height: 480px;
    margin-bottom: calc(var(--space-6) * -1);
  }

  .loading-pane {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--gray-500);
    font-size: var(--font-size-sm);
  }

  .card {
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    padding: var(--space-6);
  }
  .empty-state, .fallback-state {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 820px;
  }
  .empty-state h3, .fallback-state h3 {
    margin: 0 0 var(--space-1);
    font-size: var(--font-size-lg);
    font-weight: 700;
    color: var(--gray-900);
  }
  .empty-state p, .fallback-state p {
    margin: 0;
    color: var(--gray-700);
    font-size: var(--font-size-base);
    line-height: 1.55;
  }
  .empty-state code, .fallback-state code, .page-sub code {
    font-family: var(--font-mono);
    font-size: var(--font-size-sm);
    background: var(--gray-100);
    padding: 1px 6px;
    border-radius: var(--radius-sm);
  }
  .empty-state a, .fallback-state a {
    color: var(--primary);
    text-decoration: none;
    font-weight: 600;
  }
  .empty-state a:hover, .fallback-state a:hover { text-decoration: underline; }

  .steps {
    margin: var(--space-2) 0 0 0;
    padding-left: var(--space-5);
    color: var(--gray-700);
    font-size: var(--font-size-sm);
    line-height: 1.7;
  }
  .steps li { margin-bottom: var(--space-2); }
  .hint { font-size: var(--font-size-sm); color: var(--gray-500); margin-top: var(--space-2) !important; }

  .studio-frame-wrap {
    flex: 1;
    width: 100%;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--white);
    min-height: 500px;
    overflow: hidden;
    position: relative;
  }
  .studio-frame {
    width: 100%;
    height: 100%;
    border: 0;
    background: var(--white);
  }

  .btn-primary {
    align-self: flex-start;
    padding: var(--space-2) var(--space-5);
    background: var(--primary);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: var(--font-size-sm);
    cursor: pointer;
    text-decoration: none;
  }
  .btn-primary:hover { background: var(--blue-500); }
</style>
