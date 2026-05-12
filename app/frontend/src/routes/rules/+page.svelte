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
  import { onMount } from 'svelte';
  import { getBrandConfig } from '$lib/api.js';

  let studioUrl = $state('');
  let configLoaded = $state(false);
  let iframeLoaded = $state(false);
  let iframeBlocked = $state(false);
  let timeoutHandle = null;

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
    <iframe
      class="studio-frame"
      src={studioUrl}
      title="DQX Studio"
      onload={handleIframeLoad}
      onerror={handleIframeError}
      referrerpolicy="no-referrer-when-downgrade"
      sandbox="allow-forms allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts allow-downloads allow-modals"
    ></iframe>
    <footer class="page-footer">
      <button type="button" class="btn-ghost" onclick={openInNewTab} title="Abrir DQX Studio em nova aba">
        Abrir em nova aba ↗
      </button>
    </footer>
  {/if}
</div>

<style>
  .rules-page {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    height: calc(100vh - 140px);
    min-height: 500px;
  }

  .page-footer {
    display: flex;
    justify-content: flex-end;
    flex-shrink: 0;
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

  .studio-frame {
    flex: 1;
    width: 100%;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--white);
    min-height: 500px;
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

  .btn-ghost {
    padding: var(--space-2) var(--space-3);
    background: transparent;
    color: var(--primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: var(--font-size-sm);
    cursor: pointer;
    flex-shrink: 0;
  }
  .btn-ghost:hover { background: var(--blue-50); border-color: var(--primary); }
</style>
