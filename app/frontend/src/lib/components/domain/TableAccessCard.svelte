<script>
  /**
   * Resultado da verificação de acesso a uma tabela (`GET /linking/table-access`).
   *
   * Checklist visual: cada item diz o que foi verificado e, se faltar algo, o
   * que fazer — com o GRANT já preenchido. É aviso, nunca bloqueio: o cadastro
   * segue. Texto vem do i18n por `id`; do backend só o que é neutro de idioma.
   */
  import { _ } from 'svelte-i18n';

  let { report } = $props();

  let copiedId = $state('');
  async function copy(text, id) {
    try {
      await navigator.clipboard.writeText(text);
      copiedId = id;
      setTimeout(() => { if (copiedId === id) copiedId = ''; }, 2000);
    } catch {
      // Clipboard bloqueado: o texto segue visível e selecionável.
    }
  }

  const ICON = { passed: '✓', action_required: '!', failed: '✕', skipped: '–' };
  const ok = $derived(report?.state === 'passed');
</script>

{#if report}
  <section class="access" class:ok>
    <header>
      <span class="head-icon">{ok ? '✓' : '!'}</span>
      <div>
        <h4>{ok ? $_('linking.access.okTitle') : $_('linking.access.warnTitle')}</h4>
        <p>{ok ? $_('linking.access.okSubtitle') : $_('linking.access.warnSubtitle')}</p>
      </div>
    </header>

    <ul class="checks">
      {#each report.checks as c (c.id)}
        <li class="check state-{c.state}">
          <span class="dot" aria-hidden="true">{ICON[c.state] || '?'}</span>
          <div class="body">
            <strong>{$_(`linking.access.checks.${c.id}.title`, { values: c.params || {} })}</strong>
            {#if c.state === 'failed'}
              <p>{$_('linking.access.unexpected')}</p>
            {:else if c.state === 'skipped'}
              <p>{$_('linking.access.skipped')}</p>
            {:else if c.state === 'action_required'}
              <p>{$_(`linking.access.checks.${c.id}.how`, { values: c.params || {} })}</p>
            {/if}

            {#if c.remediation}
              <div class="cmd">
                <div class="cmd-head">
                  <span>{$_('linking.access.runAsAdmin')}</span>
                  <button onclick={() => copy(c.remediation, c.id)}>
                    {copiedId === c.id ? $_('prereq.copied') : $_('prereq.copy')}
                  </button>
                </div>
                <pre>{c.remediation}</pre>
              </div>
            {/if}
            {#if c.detail && c.state !== 'passed'}
              <details><summary>{$_('prereq.technicalDetail')}</summary><pre>{c.detail}</pre></details>
            {/if}
          </div>
        </li>
      {/each}
    </ul>

    {#if report.external}
      <!-- Identidades que não são o SP do app: não dá para verificar daqui. -->
      <footer>
        <strong>{$_('linking.access.notVerifiableTitle')}</strong>
        <ul>
          <li>{$_('linking.access.notVerifiableStudio')}</li>
          <li>{$_('linking.access.notVerifiableLedger')}</li>
        </ul>
      </footer>
    {/if}
  </section>
{/if}

<style>
  .access {
    border: 1px solid rgba(243, 112, 33, 0.35);
    background: var(--warning-light);
    color: var(--orange-900);
    border-radius: var(--radius-md);
    padding: var(--space-3) var(--space-4);
    font-size: var(--font-size-xs);
  }
  .access.ok { border-color: var(--success); background: var(--success-light); color: var(--gray-700); }
  header { display: flex; gap: var(--space-3); align-items: flex-start; }
  header h4 { margin: 0; font-size: var(--font-size-sm); font-weight: 600; }
  header p { margin: 2px 0 0; opacity: 0.85; }
  .head-icon {
    width: 22px; height: 22px; flex-shrink: 0; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; color: white; background: var(--warning);
  }
  .ok .head-icon { background: var(--success); }

  .checks { list-style: none; margin: var(--space-3) 0 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .check { display: flex; gap: var(--space-2); align-items: flex-start; }
  .dot {
    width: 18px; height: 18px; flex-shrink: 0; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: white;
  }
  .state-passed .dot { background: var(--success); }
  .state-action_required .dot { background: var(--warning); }
  .state-failed .dot { background: var(--error); }
  .state-skipped .dot { background: var(--gray-400); }
  .state-skipped { opacity: 0.7; }
  .body { flex: 1; min-width: 0; }
  .body strong { font-weight: 600; }
  .body p { margin: 2px 0 0; line-height: 1.5; }

  .cmd { margin-top: var(--space-2); background: var(--surface); border-radius: var(--radius-sm); overflow: hidden; color: var(--text-primary); }
  .cmd-head { display: flex; justify-content: space-between; align-items: center; padding: var(--space-1) var(--space-2); border-bottom: 1px solid var(--border); }
  .cmd-head span { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.7; }
  .cmd-head button { background: none; border: none; cursor: pointer; font-size: var(--font-size-xs); font-weight: 600; color: var(--primary); }
  pre { margin: 0; padding: var(--space-2) var(--space-3); font-family: var(--font-mono, ui-monospace, monospace); font-size: var(--font-size-xs); line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
  details { margin-top: var(--space-1); }
  details summary { cursor: pointer; opacity: 0.85; }
  details pre { background: var(--surface); border-radius: var(--radius-sm); margin-top: var(--space-1); }

  footer { margin-top: var(--space-3); padding-top: var(--space-2); border-top: 1px dashed rgba(0, 0, 0, 0.15); }
  footer ul { margin: var(--space-1) 0 0; padding-left: var(--space-4); line-height: 1.5; }
</style>
