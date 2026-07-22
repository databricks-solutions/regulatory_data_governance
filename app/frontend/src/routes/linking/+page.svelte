<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import {
    getCadocs, createCadoc, updateCadoc, deleteCadoc,
    getCadocTables, getSchemaTables, associateCadocTable, removeCadocTable,
    getLinkableRules, createLink, updateLink, deleteLink, ApiError
  } from '$lib/api.js';
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

  const DIM_OPTIONS = $derived.by(() =>
    Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `${i + 1}` }))
  );

  // ── CADOC management ────────────────────────────────────────────────────
  let cadocs = $state([]);
  let cadocsLoading = $state(false);
  let expandedCadoc = $state(null);       // documento string
  let cadocTables = $state({});            // { documento: [ {table_fqn} ] }
  let schemaResults = $state([]);          // browse results for the expanded cadoc
  let schemaFilter = $state({ schema: 'silver', search: '' });
  let tablePending = $state({});           // { table_fqn: true }

  let cadocModalOpen = $state(false);
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

  async function toggleCadoc(documento) {
    if (expandedCadoc === documento) { expandedCadoc = null; return; }
    expandedCadoc = documento;
    await Promise.all([loadCadocTables(documento), loadSchemaTables()]);
  }

  async function loadCadocTables(documento) {
    try {
      const data = await getCadocTables(documento);
      cadocTables = { ...cadocTables, [documento]: data?.tables || [] };
    } catch (e) { showToast('error', errMessage(e)); }
  }

  async function loadSchemaTables() {
    try {
      const data = await getSchemaTables(schemaFilter.schema, schemaFilter.search);
      schemaResults = data?.tables || [];
    } catch (e) { showToast('error', errMessage(e)); }
  }

  function isAssociated(documento, fqn) {
    return (cadocTables[documento] || []).some(t => t.table_fqn === fqn);
  }

  async function associate(documento, fqn) {
    tablePending = { ...tablePending, [fqn]: true };
    try {
      await associateCadocTable(documento, { table_fqn: fqn });
      await loadCadocTables(documento);
      await loadCadocs();
      showToast('success', $_('linking.associatedTable'));
    } catch (e) {
      showToast('error', errMessage(e));
    } finally {
      const { [fqn]: _drop, ...rest } = tablePending; tablePending = rest;
    }
  }

  async function disassociate(documento, fqn) {
    tablePending = { ...tablePending, [fqn]: true };
    try {
      await removeCadocTable(documento, fqn);
      await loadCadocTables(documento);
      await loadCadocs();
      showToast('success', $_('linking.removedTable'));
    } catch (e) {
      showToast('error', errMessage(e));
    } finally {
      const { [fqn]: _drop, ...rest } = tablePending; tablePending = rest;
    }
  }

  function openNewCadoc() {
    cadocForm = { documento: '', nome: '', descricao: '', leiaute_versao: '' };
    cadocModalOpen = true;
  }

  async function saveCadoc() {
    if (!cadocForm.documento || !cadocForm.nome) return;
    cadocSaving = true;
    try {
      await createCadoc({ ...cadocForm });
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
      if (expandedCadoc === documento) expandedCadoc = null;
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
  let linkForm = $state({ check_name: '', dimensao_r18: '', critica_id: '', nivel_verificacao: '', descricao: '', manualCheck: false });

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
    linkForm = {
      check_name: cur?.check_name || rule.definition_name || candidates[0] || '',
      dimensao_r18: cur?.dimensao_r18 ? String(cur.dimensao_r18) : '',
      critica_id: cur?.critica_id || '',
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
          dimensao_r18: Number(linkForm.dimensao_r18),
          critica_id: linkForm.critica_id || null,
          nivel_verificacao: linkForm.nivel_verificacao ? Number(linkForm.nivel_verificacao) : null,
          descricao: linkForm.descricao || null
        });
      } else {
        await createLink({
          check_name: linkForm.check_name,
          table_fqn: editing.table_fqn,
          rule_id: editing.rule_id || null,
          documento: editing.documento || null,
          dimensao_r18: Number(linkForm.dimensao_r18),
          critica_id: linkForm.critica_id || null,
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
              <tr class="cadoc-row" class:expanded={expandedCadoc === c.documento} onclick={() => toggleCadoc(c.documento)}>
                <td class="mono">{c.documento}</td>
                <td>{c.nome}</td>
                <td class="num">{c.table_count}</td>
                <td class="num">{c.rule_count}</td>
                <td><Badge label={c.is_ativo ? $_('linking.cadocActive') : $_('linking.cadocInactive')} variant={c.is_ativo ? 'success' : 'neutral'} /></td>
                <td class="actions">
                  <button class="btn-link-danger" onclick={(e) => { e.stopPropagation(); onDeleteCadoc(c.documento); }}>{$_('linking.remove')}</button>
                </td>
              </tr>
              {#if expandedCadoc === c.documento}
                <tr class="expand-row">
                  <td colspan="6">
                    <div class="assoc-panel">
                      <div class="assoc-current">
                        <h4>{$_('linking.tablesTitle')}</h4>
                        {#if (cadocTables[c.documento] || []).length === 0}
                          <p class="muted">{$_('linking.tablesEmpty')}</p>
                        {:else}
                          <ul class="assoc-list">
                            {#each cadocTables[c.documento] as t (t.table_fqn)}
                              <li>
                                <span class="mono">{t.table_fqn}</span>
                                <button class="btn-link-danger" disabled={tablePending[t.table_fqn]} onclick={() => disassociate(c.documento, t.table_fqn)}>{$_('linking.remove')}</button>
                              </li>
                            {/each}
                          </ul>
                        {/if}
                      </div>
                      <div class="assoc-browse">
                        <h4>{$_('linking.browseSchema')}</h4>
                        <div class="browse-filter">
                          <select bind:value={schemaFilter.schema} onchange={loadSchemaTables}>
                            <option value="silver">silver</option>
                            <option value="bronze">bronze</option>
                            <option value="gold">gold</option>
                            <option value="reference">reference</option>
                          </select>
                          <input type="text" placeholder={$_('linking.searchTable')} bind:value={schemaFilter.search} oninput={loadSchemaTables} />
                        </div>
                        <ul class="browse-list">
                          {#each schemaResults as st (st.table_fqn)}
                            <li>
                              <span class="mono">{st.table_name}</span>
                              {#if isAssociated(c.documento, st.table_fqn)}
                                <span class="tag-ok">{$_('linking.associated')}</span>
                              {:else if st.already_linked_documento && st.already_linked_documento !== c.documento}
                                <span class="tag-warn">{$_('linking.linkedTo', { values: { documento: st.already_linked_documento } })}</span>
                              {:else}
                                <button class="btn-link" disabled={tablePending[st.table_fqn]} onclick={() => associate(c.documento, st.table_fqn)}>{$_('linking.associate')}</button>
                              {/if}
                            </li>
                          {/each}
                        </ul>
                      </div>
                    </div>
                  </td>
                </tr>
              {/if}
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
                <td>
                  {#if r.current_link}
                    <Badge label={`${r.current_link.dimensao_r18} · ${r.current_link.dimension_name}`} variant="success" />
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

<!-- New CADOC modal -->
<Modal open={cadocModalOpen} title={$_('linking.newCadocTitle')} onclose={() => cadocModalOpen = false}>
  <div class="form">
    <label>{$_('linking.fieldDocument')}
      <input type="text" bind:value={cadocForm.documento} placeholder={$_('linking.fieldDocumentHint')} />
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
      <label>{$_('linking.fieldDimension')}
        <select bind:value={linkForm.dimensao_r18}>
          <option value="" disabled>—</option>
          {#each DIM_OPTIONS as d}
            <option value={d.value}>{d.value}</option>
          {/each}
        </select>
      </label>
      <label>{$_('linking.fieldNivel')}
        <select bind:value={linkForm.nivel_verificacao}>
          <option value="">—</option>
          <option value="1">{$_('linking.nivel1')}</option>
          <option value="2">{$_('linking.nivel2')}</option>
          <option value="3">{$_('linking.nivel3')}</option>
        </select>
      </label>
      <label>{$_('linking.fieldCriticaId')}
        <input type="text" bind:value={linkForm.critica_id} />
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
  .cadoc-row { cursor: pointer; }
  .cadoc-row td { padding: var(--space-3); border-bottom: 1px solid var(--gray-100); }
  .cadoc-row:hover { background: var(--blue-50); }
  .cadoc-row.expanded { background: var(--blue-50); }
  .actions { text-align: right; }

  .expand-row td { background: var(--gray-50); padding: var(--space-4); }
  .assoc-panel { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6); }
  .assoc-panel h4 { margin: 0 0 var(--space-2); font-size: var(--font-size-sm); color: var(--gray-700); }
  .assoc-list, .browse-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); max-height: 240px; overflow-y: auto; }
  .assoc-list li, .browse-list li { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-1) var(--space-2); border-radius: var(--radius-sm); }
  .assoc-list li:hover, .browse-list li:hover { background: var(--white); }
  .browse-filter { display: flex; gap: var(--space-2); margin-bottom: var(--space-2); }
  .browse-filter select, .browse-filter input { padding: var(--space-1) var(--space-2); border: 1px solid var(--border-color); border-radius: var(--radius-sm); font-size: var(--font-size-sm); }
  .browse-filter input { flex: 1; }

  .tag-ok { font-size: var(--font-size-xs); color: var(--success); font-weight: 600; }
  .tag-warn { font-size: var(--font-size-xs); color: var(--warning); }

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

  @media (max-width: 900px) { .assoc-panel { grid-template-columns: 1fr; } }
</style>
