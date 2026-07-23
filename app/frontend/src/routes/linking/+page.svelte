<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import {
    getCadocs, createCadoc, updateCadoc, deleteCadoc,
    getLinkableRules, createLink, updateLink, deleteLink, ApiError
  } from '$lib/api.js';
  import { dimensionNames } from '$lib/theme.js';
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';

  let activeTab = $state('cadocs');
  const tabs = $derived.by(() => [
    { key: 'cadocs', label: $_('linking.tabCadocs') },
    { key: 'links', label: $_('linking.tabLinks') }
  ]);

  // ── Shared: toast + inflight ────────────────────────────────────────────
  let toast = $state(null); // { kind, message }
  let toastTimer = null;
  function showToast(kind, message, ms = 4000) {
    toast = { kind, message };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast = null; }, ms);
  }
  function errMessage(e, fallbackKey) {
    const code = e instanceof ApiError ? (e.body?.detail?.code || e.body?.code) : null;
    if (code === 'link_exists') return $_('linking.errorLinkExists');
    if (code === 'cadoc_exists') return $_('linking.errorCadocExists');
    if (code === 'cadoc_has_links') return $_('linking.errorCadocHasLinks');
    return $_(fallbackKey || 'linking.errorGeneric');
  }

  // Opções de dimensão para FILTROS (só número, compacto).
  const DIM_OPTIONS = $derived.by(() =>
    Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `${i + 1}` }))
  );
  // Opções para o MODAL de vínculo: número + nome (ex.: "1 · Acessibilidade").
  const DIM_OPTIONS_NAMED = Array.from({ length: 12 }, (_, i) => ({
    value: String(i + 1), label: `${i + 1} · ${dimensionNames[i]}`
  }));
  // Níveis de verificação — nomenclatura alinhada à tela de Críticas SCR.
  const NIVEL_OPTIONS = $derived.by(() => [
    { value: '1', label: `1 · ${$_('validations.levelOneSubtitle')}` },
    { value: '2', label: `2 · ${$_('validations.levelTwoSubtitle')}` },
    { value: '3', label: `3 · ${$_('validations.levelThreeSubtitle')}` },
  ]);

  // ── CADOC management ────────────────────────────────────────────────────
  let cadocs = $state([]);
  let cadocsLoading = $state(false);
  let cadocModalOpen = $state(false);
  let cadocEditing = $state(false);        // false = criar, true = editar
  let cadocForm = $state({ documento: '', nome: '', descricao: '', leiaute_versao: '' });
  let cadocSaving = $state(false);

  async function loadCadocs() {
    cadocsLoading = true;
    try {
      const data = await getCadocs();
      cadocs = data?.cadocs || [];
    } catch (e) {
      showToast('error', errMessage(e));
    } finally {
      cadocsLoading = false;
    }
  }

  function openNewCadoc() {
    cadocEditing = false;
    cadocForm = { documento: '', nome: '', descricao: '', leiaute_versao: '' };
    cadocModalOpen = true;
  }

  function openEditCadoc(c) {
    cadocEditing = true;
    cadocForm = {
      documento: c.documento,
      nome: c.nome || '',
      descricao: c.descricao || '',
      leiaute_versao: c.leiaute_versao || ''
    };
    cadocModalOpen = true;
  }

  async function saveCadoc() {
    if (!cadocForm.documento || !cadocForm.nome) return;
    cadocSaving = true;
    try {
      if (cadocEditing) {
        await updateCadoc(cadocForm.documento, {
          nome: cadocForm.nome,
          descricao: cadocForm.descricao || null,
          leiaute_versao: cadocForm.leiaute_versao || null
        });
      } else {
        await createCadoc({ ...cadocForm });
      }
      cadocModalOpen = false;
      await loadCadocs();
      showToast('success', $_('linking.savedCadoc'));
    } catch (e) {
      showToast('error', errMessage(e, 'linking.errorCadocExists'));
    } finally {
      cadocSaving = false;
    }
  }

  async function onDeleteCadoc(documento) {
    if (!confirm($_('linking.confirmDeleteCadoc'))) return;
    try {
      await deleteCadoc(documento);
      await loadCadocs();
      showToast('success', $_('linking.removedCadoc'));
    } catch (e) {
      showToast('error', errMessage(e, 'linking.errorCadocHasLinks'));
    }
  }

  // ── Rule linking ────────────────────────────────────────────────────────
  let rules = $state([]);
  let rulesLoading = $state(false);
  let ruleFilters = $state({});

  let linkModalOpen = $state(false);
  let linkSaving = $state(false);
  let editing = $state(null); // the LinkableRule being linked/edited
  let linkForm = $state({ check_name: '', documento: '', dimensao_r18: '', nivel_verificacao: '', descricao: '', manualCheck: false });
  // CADOC derivado da tabela da regra (via cadoc_tabelas) — default do seletor.
  let derivedDocumento = $state('');

  const ruleFilterDefs = $derived.by(() => [
    { key: 'document', label: $_('linking.rulesFilterDocument'), type: 'select',
      options: cadocs.map(c => ({ value: c.documento, label: c.documento })) },
    { key: 'dimensao_r18', label: $_('linking.rulesFilterDimension'), type: 'select', options: DIM_OPTIONS },
    { key: 'linked', label: $_('linking.rulesFilterStatus'), type: 'select',
      options: [{ value: 'true', label: $_('linking.statusLinked') }, { value: 'false', label: $_('linking.statusUnlinked') }] }
  ]);

  async function loadRules() {
    rulesLoading = true;
    try {
      const data = await getLinkableRules(ruleFilters);
      rules = data?.rules || [];
    } catch (e) {
      showToast('error', errMessage(e));
    } finally {
      rulesLoading = false;
    }
  }

  function ruleFilterChange(key, value) { ruleFilters = { ...ruleFilters, [key]: value }; loadRules(); }
  function ruleFilterReset() { ruleFilters = {}; loadRules(); }

  function openLink(rule) {
    editing = rule;
    const cur = rule.current_link;
    const candidates = rule.effective_check_names || [];
    // CADOC derivado: o documento que o backend resolveu a partir da tabela.
    derivedDocumento = rule.documento || '';
    linkForm = {
      check_name: cur?.check_name || rule.definition_name || candidates[0] || '',
      documento: cur?.documento || rule.documento || '',
      dimensao_r18: cur?.dimensao_r18 ? String(cur.dimensao_r18) : '',
      nivel_verificacao: cur?.nivel_verificacao ? String(cur.nivel_verificacao) : '',
      descricao: cur?.descricao || '',
      manualCheck: candidates.length === 0 && !cur
    };
    linkModalOpen = true;
  }

  async function saveLink() {
    if (!linkForm.check_name || !linkForm.dimensao_r18) return;
    linkSaving = true;
    const cur = editing?.current_link;
    try {
      if (cur?.vinculo_id) {
        await updateLink(cur.vinculo_id, {
          check_name: linkForm.check_name,
          documento: linkForm.documento || null,
          dimensao_r18: Number(linkForm.dimensao_r18),
          nivel_verificacao: linkForm.nivel_verificacao ? Number(linkForm.nivel_verificacao) : null,
          descricao: linkForm.descricao || null
        });
      } else {
        await createLink({
          check_name: linkForm.check_name,
          table_fqn: editing.table_fqn,
          rule_id: editing.rule_id || null,
          documento: linkForm.documento || editing.documento || null,
          dimensao_r18: Number(linkForm.dimensao_r18),
          nivel_verificacao: linkForm.nivel_verificacao ? Number(linkForm.nivel_verificacao) : null,
          descricao: linkForm.descricao || null
        });
      }
      linkModalOpen = false;
      await loadRules();
      showToast('success', $_('linking.savedLink'));
    } catch (e) {
      showToast('error', errMessage(e, 'linking.errorLinkExists'));
    } finally {
      linkSaving = false;
    }
  }

  async function onDeleteLink(rule) {
    const cur = rule.current_link;
    if (!cur?.vinculo_id || !confirm($_('linking.confirmDeleteLink'))) return;
    try {
      await deleteLink(cur.vinculo_id);
      await loadRules();
      showToast('success', $_('linking.removedLink'));
    } catch (e) {
      showToast('error', errMessage(e));
    }
  }

  onMount(() => { loadCadocs(); loadRules(); });
</script>

<div class="page">
  <p class="subtitle">{$_('linking.subtitle')}</p>

  <Tabs {tabs} active={activeTab} onchange={(k) => activeTab = k} />

  {#if activeTab === 'cadocs'}
    <div class="section-head">
      <button class="btn-primary" onclick={openNewCadoc}>+ {$_('linking.newCadoc')}</button>
    </div>

    {#if cadocsLoading}
      <div class="state">{$_('linking.loading')}</div>
    {:else if cadocs.length === 0}
      <div class="state">{$_('linking.emptyCadocs')}</div>
    {:else}
      <div class="card">
        <table class="cadoc-table">
          <thead>
            <tr>
              <th>{$_('linking.cadocColDocument')}</th>
              <th>{$_('linking.cadocColName')}</th>
              <th class="num">{$_('linking.cadocColTables')}</th>
              <th class="num">{$_('linking.cadocColRules')}</th>
              <th>{$_('linking.cadocColStatus')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each cadocs as c (c.documento)}
              <tr>
                <td class="mono">{c.documento}</td>
                <td>{c.nome}</td>
                <td class="num">{c.table_count}</td>
                <td class="num">{c.rule_count}</td>
                <td><Badge label={c.is_ativo ? $_('linking.cadocActive') : $_('linking.cadocInactive')} variant={c.is_ativo ? 'success' : 'neutral'} /></td>
                <td class="actions">
                  <button class="btn-secondary sm" onclick={() => openEditCadoc(c)}>{$_('linking.edit')}</button>
                  <button class="btn-link-danger" onclick={() => onDeleteCadoc(c.documento)}>{$_('linking.remove')}</button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else}
    <FilterBar filters={ruleFilterDefs} values={ruleFilters} onchange={ruleFilterChange} onreset={ruleFilterReset} />
    {#if rulesLoading}
      <div class="state">{$_('linking.loading')}</div>
    {:else if rules.length === 0}
      <div class="state">{$_('linking.empty')}</div>
    {:else}
      <div class="card">
        <table class="rules-table">
          <thead>
            <tr>
              <th>{$_('linking.ruleColId')}</th>
              <th>{$_('linking.ruleColCheck')}</th>
              <th>{$_('linking.ruleColFunction')}</th>
              <th>{$_('linking.ruleColTable')}</th>
              <th>{$_('linking.ruleColDocument')}</th>
              <th>{$_('linking.ruleColDimension')}</th>
              <th class="actions">{$_('linking.ruleColActions')}</th>
            </tr>
          </thead>
          <tbody>
            {#each rules as r (r.rule_id + r.table_fqn)}
              {@const effName = r.current_link?.check_name || r.definition_name || (r.effective_check_names && r.effective_check_names[0]) || '—'}
              <tr>
                <td class="mono">{r.rule_id || '—'}</td>
                <td class="mono">{effName}</td>
                <td>{r.function || '—'}</td>
                <td class="mono tbl-cell">{r.table_fqn.split('.').pop()}</td>
                <td>{r.current_link?.documento || r.documento || '—'}</td>
                <td>
                  {#if r.current_link}
                    <Badge label={`${r.current_link.dimensao_r18} · ${r.current_link.dimension_name}`} variant="success" />
                  {:else if r.tag_dimension_r18}
                    <span title={$_('linking.statusViaTagTitle')}>
                      <Badge label={`${r.tag_dimension_r18} · ${r.tag_dimension_name} (${$_('linking.statusViaTag')})`} variant="info" />
                    </span>
                  {:else}
                    <Badge label={$_('linking.statusUnlinked')} variant="neutral" />
                  {/if}
                </td>
                <td class="actions">
                  {#if r.current_link}
                    <button class="btn-secondary sm" onclick={() => openLink(r)}>{$_('linking.editLink')}</button>
                    <button class="btn-link-danger" onclick={() => onDeleteLink(r)}>{$_('linking.delete')}</button>
                  {:else}
                    <button class="btn-primary sm" onclick={() => openLink(r)}>{$_('linking.link')}</button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {/if}
</div>

<!-- CADOC modal (criar/editar) -->
<Modal open={cadocModalOpen} title={cadocEditing ? $_('linking.editCadocTitle') : $_('linking.newCadocTitle')} onclose={() => cadocModalOpen = false}>
  <div class="form">
    <label>{$_('linking.fieldDocument')}
      <input type="text" bind:value={cadocForm.documento} placeholder={$_('linking.fieldDocumentHint')} disabled={cadocEditing} />
    </label>
    <label>{$_('linking.fieldName')}
      <input type="text" bind:value={cadocForm.nome} />
    </label>
    <label>{$_('linking.fieldDescription')}
      <textarea rows="2" bind:value={cadocForm.descricao}></textarea>
    </label>
    <label>{$_('linking.fieldLayoutVersion')}
      <input type="text" bind:value={cadocForm.leiaute_versao} />
    </label>
    <div class="form-actions">
      <button class="btn-secondary" onclick={() => cadocModalOpen = false}>{$_('linking.cancel')}</button>
      <button class="btn-primary" disabled={cadocSaving || !cadocForm.documento || !cadocForm.nome} onclick={saveCadoc}>{$_('linking.save')}</button>
    </div>
  </div>
</Modal>

<!-- Link rule modal -->
<Modal open={linkModalOpen} title={$_('linking.linkRuleTitle')} onclose={() => linkModalOpen = false}>
  {#if editing}
    <div class="form">
      <div class="rule-ctx">
        <span class="mono">{editing.rule_id}</span>
        <span class="ctx-sep">·</span>
        <span class="mono">{editing.table_fqn}</span>
      </div>
      <label>{$_('linking.fieldCheckName')}
        {#if !linkForm.manualCheck && (editing.effective_check_names || []).length > 0}
          <select bind:value={linkForm.check_name}>
            {#each editing.effective_check_names as cn}
              <option value={cn}>{cn}</option>
            {/each}
          </select>
          <small class="hint">{$_('linking.fieldCheckNameHint')}</small>
        {:else}
          <input type="text" bind:value={linkForm.check_name} />
          {#if (editing.effective_check_names || []).length === 0}
            <small class="hint">{$_('linking.noCheckCandidates')}</small>
          {/if}
        {/if}
      </label>
      <label>{$_('linking.fieldCadoc')}
        <select bind:value={linkForm.documento}>
          <option value="" disabled>—</option>
          {#each cadocs as c}
            <option value={c.documento}>{c.documento} — {c.nome}</option>
          {/each}
        </select>
        {#if derivedDocumento && linkForm.documento === derivedDocumento}
          <small class="hint">{$_('linking.cadocDerived', { values: { documento: derivedDocumento } })}</small>
        {:else if derivedDocumento && linkForm.documento && linkForm.documento !== derivedDocumento}
          <small class="hint warn">{$_('linking.cadocMismatch', { values: { documento: derivedDocumento } })}</small>
        {/if}
      </label>
      <label>{$_('linking.fieldDimension')}
        <select bind:value={linkForm.dimensao_r18}>
          <option value="" disabled>—</option>
          {#each DIM_OPTIONS_NAMED as d}
            <option value={d.value}>{d.label}</option>
          {/each}
        </select>
      </label>
      <label>{$_('linking.fieldNivel')}
        <select bind:value={linkForm.nivel_verificacao}>
          <option value="">—</option>
          {#each NIVEL_OPTIONS as n}
            <option value={n.value}>{n.label}</option>
          {/each}
        </select>
      </label>
      <label>{$_('linking.fieldDescription')}
        <textarea rows="2" bind:value={linkForm.descricao}></textarea>
      </label>
      <div class="form-actions">
        <button class="btn-secondary" onclick={() => linkModalOpen = false}>{$_('linking.cancel')}</button>
        <button class="btn-primary" disabled={linkSaving || !linkForm.check_name || !linkForm.dimensao_r18} onclick={saveLink}>{$_('linking.save')}</button>
      </div>
    </div>
  {/if}
</Modal>

{#if toast}
  <div class="toast toast-{toast.kind}">{toast.message}</div>
{/if}

<style>
  .page { padding: var(--space-6); display: flex; flex-direction: column; gap: var(--space-5); }
  .subtitle { color: var(--gray-600); font-size: var(--font-size-sm); max-width: 70ch; margin: 0; }
  .section-head { display: flex; justify-content: flex-end; }
  .card { background: var(--white); border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: var(--space-4); }
  .state { padding: var(--space-8); text-align: center; color: var(--gray-500); }

  .cadoc-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
  .cadoc-table th { text-align: left; padding: var(--space-2) var(--space-3); color: var(--gray-500); font-weight: 600; border-bottom: 1px solid var(--border-color); }
  .cadoc-table th.num, .cadoc-table td.num { text-align: right; }
  .cadoc-table td { padding: var(--space-3); border-bottom: 1px solid var(--gray-100); }
  .cadoc-table tbody tr:hover { background: var(--blue-50); }
  .actions { text-align: right; white-space: nowrap; }
  .cadoc-table td.actions { display: flex; gap: var(--space-2); justify-content: flex-end; align-items: center; }

  .rules-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-sm); }
  .rules-table th { text-align: left; padding: var(--space-2) var(--space-3); color: var(--gray-500); font-weight: 600; border-bottom: 1px solid var(--border-color); }
  .rules-table td { padding: var(--space-3); border-bottom: 1px solid var(--gray-100); vertical-align: middle; }
  .rules-table th.actions, .rules-table td.actions { text-align: right; white-space: nowrap; }
  .rules-table td.actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
  .tbl-cell { color: var(--gray-600); }

  .mono { font-family: var(--font-mono); font-size: 0.85em; }
  .muted { color: var(--gray-400); }

  .form { display: flex; flex-direction: column; gap: var(--space-3); }
  .form label { display: flex; flex-direction: column; gap: var(--space-1); font-size: var(--font-size-sm); font-weight: 500; color: var(--gray-700); }
  .form input, .form select, .form textarea { padding: var(--space-2) var(--space-3); border: 1px solid var(--border-color); border-radius: var(--radius-sm); font-size: var(--font-size-sm); font-family: inherit; }
  .form .hint { font-weight: 400; color: var(--gray-500); font-size: var(--font-size-xs); }
  .form .hint.warn { color: var(--warning); }
  .form-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-2); }
  .rule-ctx { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); background: var(--gray-50); border-radius: var(--radius-sm); }
  .ctx-sep { color: var(--gray-400); }

  .btn-primary { background: var(--primary); color: white; border: none; border-radius: var(--radius-sm); padding: var(--space-2) var(--space-4); font-weight: 600; font-size: var(--font-size-sm); cursor: pointer; }
  .btn-primary.sm { padding: var(--space-1) var(--space-3); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary { background: var(--white); color: var(--gray-700); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: var(--space-2) var(--space-4); font-weight: 500; font-size: var(--font-size-sm); cursor: pointer; }
  .btn-link { background: none; border: none; color: var(--primary); font-weight: 600; cursor: pointer; font-size: var(--font-size-sm); }
  .btn-link:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-link-danger { background: none; border: none; color: var(--error); font-weight: 500; cursor: pointer; font-size: var(--font-size-sm); }

  .toast { position: fixed; bottom: var(--space-6); right: var(--space-6); padding: var(--space-3) var(--space-5); border-radius: var(--radius-md); color: white; font-size: var(--font-size-sm); font-weight: 500; box-shadow: var(--shadow-lg); z-index: 1000; }
  .toast-success { background: var(--success); }
  .toast-error { background: var(--error); }
  .toast-info { background: var(--info); }

</style>
