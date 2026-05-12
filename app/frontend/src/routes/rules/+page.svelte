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
  import { getBrandConfig } from '$lib/api.js';
  import { appState, setHeaderAction } from '$lib/stores.svelte.js';

  let studioUrl = $state('');
  let configLoaded = $state(false);
  let iframeLoaded = $state(false);
  let iframeBlocked = $state(false);
  let timeoutHandle = null;

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
    if (studioUrl) {
      window.open(studioUrl, '_blank', 'noopener,noreferrer');
    }
  }

  onMount(async () => {
    try {
      const cfg = await getBrandConfig();
      studioUrl = (cfg?.dqx_studio_url || '').trim();
    } catch {
      studioUrl = '';
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
        label: 'Abrir em nova aba ↗',
        title: 'Abrir DQX Studio em nova aba',
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
    <div class="loading-pane">Carregando…</div>
  {:else if showEmptyState}
    <section class="empty-state card">
      <h3>DQX Studio ainda não está configurado</h3>
      <p>
        O <strong>DQX Studio</strong> é a interface oficial do
        <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">Databricks Labs DQX</a>
        para criar, editar e monitorar regras de qualidade aplicadas no pipeline silver
        (<code>${'{catalog}'}.quality.dqx_checks</code>). Ele é entregue como uma
        <em>Databricks App</em> separada, mantida pela equipe DQX, e este acelerador
        embute essa UI ao invés de duplicar a funcionalidade.
      </p>
      <p>
        Para habilitar o módulo, faça o deploy do DQX Studio no seu workspace
        seguindo o guia oficial em
        <a href={DOCS_URL} target="_blank" rel="noopener noreferrer">{DOCS_URL}</a>
        e configure a URL pública do app na variável de ambiente
        <code>DQX_STUDIO_URL</code>:
      </p>
      <ul class="steps">
        <li>
          <strong>Local dev:</strong> defina <code>DQX_STUDIO_URL=https://&lt;dqx-studio-app&gt;.databricksapps.com</code>
          em <code>.env</code> e reinicie o backend (<code>./run_local.sh</code>).
        </li>
        <li>
          <strong>Deploy bundle:</strong> defina <code>DQX_STUDIO_URL</code> em
          <code>resources/app.yml</code> (bloco <code>apps.config.env</code>) e
          rode <code>databricks bundle deploy</code>.
        </li>
      </ul>
      <p class="hint">
        Após configurar a URL, esta página passa a renderizar o DQX Studio embarcado.
        Caso o navegador rejeite o embed (políticas X-Frame-Options/CSP do destino),
        oferecemos um botão para abrir em nova aba.
      </p>
    </section>
  {:else if showFallback}
    <section class="fallback-state card">
      <h3>O DQX Studio não pôde ser exibido embarcado</h3>
      <p>
        Este navegador bloqueou o iframe do DQX Studio — provavelmente por causa
        das políticas de segurança <code>X-Frame-Options</code> ou
        <code>Content-Security-Policy</code> configuradas no destino
        (Databricks Apps usa cabeçalhos restritivos por padrão).
      </p>
      <p>
        Abra o DQX Studio em uma nova aba para gerenciar suas regras DQX:
      </p>
      <button type="button" class="btn-primary" onclick={openInNewTab}>
        Abrir DQX Studio
      </button>
      <p class="hint">
        Endpoint configurado: <code>{studioUrl}</code>
      </p>
    </section>
  {:else if showIframe}
    <div class="studio-frame-wrap">
      {#key iframeKey}
        <iframe
          class="studio-frame"
          src={studioUrl}
          title="DQX Studio"
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
    height: calc(100vh - 96px);
    min-height: 500px;
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

  /* Scale-down trick: render DQX Studio at 1/scale of the visible slot
     (so its layout sees a wider/taller viewport), then transform-scale it
     back to fit. Eliminates iframe scrollbars at the cost of ~15% smaller
     text. Tune --dqx-scale to taste. */
  .studio-frame-wrap {
    --dqx-scale: 0.85;
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
    position: absolute;
    top: 0;
    left: 0;
    width: calc(100% / var(--dqx-scale));
    height: calc(100% / var(--dqx-scale));
    border: 0;
    background: var(--white);
    transform: scale(var(--dqx-scale));
    transform-origin: top left;
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
