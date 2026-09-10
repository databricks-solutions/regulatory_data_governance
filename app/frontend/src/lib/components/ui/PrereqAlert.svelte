<script>
  /**
   * Aviso de pré-requisito faltando: causa + comando de correção + "Re-verificar".
   *
   * Tela vazia por falta de GRANT é indistinguível de "não há regra" (o backend
   * degrada para vazio), então o diagnóstico responde qual é o caso. Só busca
   * quando o pai diz que veio vazio (`active`) — custo zero no caminho feliz.
   * Texto vem do i18n por `id`; do backend só o que é neutro de idioma.
   */
  import { _ } from 'svelte-i18n';
  import { getPrereqs } from '$lib/api.js';
  import Spinner from './Spinner.svelte';

  let { active = false } = $props();

  let report = $state(null);
  let loading = $state(false);
  let copiedId = $state('');

  // `passed`/`skipped` são ruído aqui.
  let blocking = $derived(
    (report?.checks || []).filter((c) => c.state === 'action_required' || c.state === 'failed')
  );

  async function check() {
    loading = true;
    try {
      report = await getPrereqs();
    } catch {
      report = null;
    } finally {
      loading = false;
    }
  }

  async function copy(text, id) {
    try {
      await navigator.clipboard.writeText(text);
      copiedId = id;
      setTimeout(() => { if (copiedId === id) copiedId = ''; }, 2000);
    } catch {
      // Clipboard bloqueado: o texto segue visível e selecionável.
    }
  }

  // Dispara na primeira vez que a tela reporta vazio; re-verificar é explícito.
  let requested = false;
  $effect(() => {
    if (active && !requested) {
      requested = true;
      check();
    }
  });
</script>

{#if active && (loading || blocking.length > 0)}
  <section class="prereq" role="alert">
    {#if loading && !report}
      <div class="prereq-loading"><Spinner /> <span>{$_('prereq.checking')}</span></div>
    {:else}
      <header class="prereq-head">
        <div class="prereq-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"/>
          </svg>
        </div>
        <div class="prereq-head-text">
          <h3>{$_('prereq.title')}</h3>
          <p>{$_('prereq.subtitle')}</p>
        </div>
        <button class="prereq-recheck" onclick={check} disabled={loading}>
          {loading ? $_('prereq.rechecking') : $_('prereq.recheck')}
        </button>
      </header>

      {#each blocking as c (c.id)}
        <article class="prereq-item">
          <h4>{$_(`prereq.checks.${c.id}.title`)}</h4>
          {#if c.state === 'failed'}
            <!-- Sem prescrição: o texto de "falta permissão" mandaria o
                 operador para o lugar errado. -->
            <p class="prereq-what">{$_('prereq.unexpected')}</p>
          {:else}
            <p class="prereq-what">{$_(`prereq.checks.${c.id}.what`, { values: c.params || {} })}</p>
            <p class="prereq-how">{$_(`prereq.checks.${c.id}.how`, { values: c.params || {} })}</p>
          {/if}

          {#if c.remediation}
            <div class="prereq-cmd">
              <div class="prereq-cmd-head">
                <span class="prereq-cmd-kind">{$_(`prereq.kind.${c.remediation_kind || 'shell'}`)}</span>
                <button onclick={() => copy(c.remediation, c.id)}>
                  {copiedId === c.id ? $_('prereq.copied') : $_('prereq.copy')}
                </button>
              </div>
              <pre>{c.remediation}</pre>
            </div>
            {#if c.params?.psql}
              <p class="prereq-hint">{$_('prereq.runVia')}</p>
              <div class="prereq-cmd">
                <div class="prereq-cmd-head">
                  <span class="prereq-cmd-kind">shell</span>
                  <button onclick={() => copy(c.params.psql, `${c.id}-psql`)}>
                    {copiedId === `${c.id}-psql` ? $_('prereq.copied') : $_('prereq.copy')}
                  </button>
                </div>
                <pre>{c.params.psql}</pre>
              </div>
            {/if}
          {/if}

          {#if c.detail}
            <details class="prereq-detail">
              <summary>{$_('prereq.technicalDetail')}</summary>
              <pre>{c.detail}</pre>
            </details>
          {/if}
        </article>
      {/each}
    {/if}
  </section>
{/if}

<style>
  .prereq {
    background: var(--warning-light);
    border: 1px solid rgba(243, 112, 33, 0.35);
    border-radius: var(--radius-md);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
    color: var(--orange-900);
  }
  .prereq-loading { display: flex; align-items: center; gap: var(--space-3); font-size: var(--font-size-sm); }
  .prereq-head { display: flex; align-items: flex-start; gap: var(--space-3); }
  .prereq-icon {
    width: 24px; height: 24px; flex-shrink: 0;
    border-radius: var(--radius-sm);
    background: rgba(243, 112, 33, 0.12);
    display: flex; align-items: center; justify-content: center;
  }
  .prereq-head-text { flex: 1; min-width: 0; }
  .prereq-head h3 { margin: 0; font-size: var(--font-size-sm); font-weight: 600; }
  .prereq-head p { margin: 2px 0 0; font-size: var(--font-size-xs); opacity: 0.85; }
  .prereq-recheck {
    flex-shrink: 0;
    background: var(--surface); color: var(--orange-900);
    border: 1px solid rgba(243, 112, 33, 0.4);
    border-radius: var(--radius-sm);
    padding: var(--space-1) var(--space-3);
    font-size: var(--font-size-xs); font-weight: 600; cursor: pointer;
  }
  .prereq-recheck:disabled { opacity: 0.6; cursor: default; }
  .prereq-item {
    margin-top: var(--space-4);
    padding-top: var(--space-3);
    border-top: 1px solid rgba(243, 112, 33, 0.25);
  }
  .prereq-item h4 { margin: 0 0 var(--space-1); font-size: var(--font-size-sm); font-weight: 600; }
  .prereq-what, .prereq-how { margin: 0 0 var(--space-2); font-size: var(--font-size-xs); line-height: 1.5; }
  .prereq-hint { margin: var(--space-2) 0; font-size: var(--font-size-xs); opacity: 0.85; }
  .prereq-cmd { background: var(--surface); border-radius: var(--radius-sm); overflow: hidden; }
  .prereq-cmd-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--space-1) var(--space-2);
    border-bottom: 1px solid var(--border);
  }
  .prereq-cmd-kind { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.7; }
  .prereq-cmd-head button {
    background: none; border: none; cursor: pointer;
    font-size: var(--font-size-xs); font-weight: 600; color: var(--primary);
  }
  .prereq-cmd pre {
    margin: 0; padding: var(--space-3);
    font-family: var(--font-mono, ui-monospace, monospace);
    font-size: var(--font-size-xs); line-height: 1.6;
    color: var(--text-primary);
    white-space: pre-wrap; word-break: break-word;
  }
  .prereq-detail { margin-top: var(--space-2); font-size: var(--font-size-xs); }
  .prereq-detail summary { cursor: pointer; opacity: 0.85; }
  .prereq-detail pre {
    margin: var(--space-2) 0 0; padding: var(--space-2);
    background: var(--surface); border-radius: var(--radius-sm);
    white-space: pre-wrap; word-break: break-word;
    font-family: var(--font-mono, ui-monospace, monospace);
  }
</style>
