<script>
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import Modal from '$lib/components/ui/Modal.svelte';
  import FilterBar from '$lib/components/data/FilterBar.svelte';
  import PrereqAlert from '$lib/components/ui/PrereqAlert.svelte';
  import TableAccessCard from '$lib/components/domain/TableAccessCard.svelte';
  import {
    getCadocs, createCadoc, updateCadoc, deleteCadoc,
    getLinkableRules, createLink, updateLink, deleteLink,
    getAllCadocTables, associateCadocTable, removeCadocTable, getTableAccess,
    getBrowseCatalogs, getBrowseSchemas, getSchemaTables, ApiError
  } from '$lib/api.js';
  import { dimensionNames } from '$lib/theme.js';
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';

  let activeTab = $state('cadocs');
  const tabs = $derived.by(() => [
    { key: 'cadocs', label: $_('linking.tabCadocs') },
    { key: 'tables', label: $_('linking.tabTables') },
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
  let cadocForm = $state({ documento: '', nome: '', descricao: '', leiaute_versao: '', periodicidade: '', grupo: '' });
  // Mesma lista de data_base.PERIODICIDADES no backend.
  const PERIODICIDADES = ['diaria', 'semanal', 'mensal', 'trimestral', 'semestral', 'anual', 'eventual'];
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
    cadocForm = { documento: '', nome: '', descricao: '', leiaute_versao: '', periodicidade: '', grupo: '' };
    cadocModalOpen = true;
  }

  function openEditCadoc(c) {
    cadocEditing = true;
    cadocForm = {
      documento: c.documento,
      nome: c.nome || '',
      descricao: c.descricao || '',
      leiaute_versao: c.leiaute_versao || '',
      periodicidade: c.periodicidade || '',
      grupo: c.grupo || ''
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
          leiaute_versao: cadocForm.leiaute_versao || null,
          periodicidade: cadocForm.periodicidade || null,
          grupo: cadocForm.grupo || null
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

  // Regra do Registry (tem verificações): vínculo da REGRA, uma dimensão para todas.
  const isRuleGrain = (r) => (r?.verifications || []).length > 0;
  const verifCols = (r) => (r?.verifications || []).flatMap(v => v.columns.length ? v.columns : [v.check_name]);
  const legacyCols = (r) => {
    const byName = Object.fromEntries((r?.verifications || []).map(v => [v.check_name, v.columns.join(', ') || v.check_name]));
    return (r?.legacy_links || []).map(l => byName[l.check_name] || l.check_name);
  };

  function openLink(rule) {
    editing = rule;
    if (isRuleGrain(rule)) {
      const cur = rule.current_link;
      // Sem vínculo da regra, parte do vínculo antigo (se houver) para não perder a escolha.
      const base = cur || rule.legacy_links?.[0];
      derivedDocumento = rule.documento || '';
      linkForm = {
        check_name: cur?.check_name || rule.definition_name,
        documento: cur?.documento || rule.documento || '',
        dimensao_r18: base?.dimensao_r18 ? String(base.dimensao_r18) : '',
        nivel_verificacao: base?.nivel_verificacao ? String(base.nivel_verificacao) : '',
        descricao: base?.descricao || '',
        manualCheck: false
      };
      linkModalOpen = true;
      return;
    }
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
          descricao: linkForm.descricao || null,
          // Vínculo da regra substitui os antigos, um por verificação.
          supersede_check_names: (editing.legacy_links || []).map(l => l.check_name)
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

  // ── CADOC ↔ tabelas (inclusive de outro catálogo) ───────────────────────
  let cadocTables = $state([]);
  let tablesLoading = $state(false);
  let tablesLoaded = false;
  // Verificação por tabela: { [fqn]: { loading, report } }. Só as externas são
  // verificadas ao abrir — as do próprio catálogo têm grant do deploy.
  let access = $state({});
  let expanded = $state('');

  let tableModalOpen = $state(false);
  let tableForm = $state({ documento: '', table_fqn: '' });
  let tableSaving = $state(false);
  let modalReport = $state(null);
  let modalChecking = $state(false);
  const FQN_RE = /^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$/;
  const fqnValid = $derived(FQN_RE.test(tableForm.table_fqn.trim()));

  // Por status: o ApiError não carrega o `detail.code` do backend.
  function tableErr(e) {
    const status = e instanceof ApiError ? e.status : 0;
    if (status === 409) return $_('linking.errorTableLinked');
    if (status === 400) return $_('linking.errorTableFqn');
    return $_('linking.errorGeneric');
  }

  async function verify(fqn) {
    access = { ...access, [fqn]: { loading: true, report: access[fqn]?.report || null } };
    try {
      access = { ...access, [fqn]: { loading: false, report: await getTableAccess(fqn) } };
    } catch {
      access = { ...access, [fqn]: { loading: false, report: null } };
    }
  }

  async function loadTables() {
    tablesLoading = true;
    try {
      const data = await getAllCadocTables();
      cadocTables = data?.tables || [];
      tablesLoaded = true;
      for (const t of cadocTables) if (t.external && !access[t.table_fqn]) verify(t.table_fqn);
    } catch (e) {
      showToast('error', errMessage(e));
    } finally {
      tablesLoading = false;
    }
  }

  // Navegador do modal. O que o SP do app não enxerga não aparece — e isso já
  // responde "tem acesso?"; para o resto existe o modo "digitar o nome".
  let tableMode = $state('browse'); // 'browse' | 'manual'
  let browse = $state({
    catalogs: [], catalog: '', schemas: [], schema: '', tables: [], search: '',
    loading: '', error: ''          // loading: 'catalogs' | 'schemas' | 'tables' | ''
  });
  const visibleTables = $derived(
    browse.tables.filter(t => !browse.search || t.table_name.toLowerCase().includes(browse.search.toLowerCase()))
  );

  async function loadBrowseCatalogs() {
    browse = { ...browse, loading: 'catalogs', error: '' };
    try {
      const data = await getBrowseCatalogs();
      browse = { ...browse, catalogs: data?.catalogs || [], error: data?.access_error || '' };
    } catch {
      browse = { ...browse, catalogs: [], error: $_('linking.errorGeneric') };
    } finally {
      browse = { ...browse, loading: '' };
    }
  }

  // Trocar catálogo/schema descarta a tabela escolhida e o alerta dela.
  function clearPick() {
    tableForm = { ...tableForm, table_fqn: '' };
    modalReport = null;
  }

  async function pickCatalog(catalog) {
    clearPick();
    browse = { ...browse, catalog, schemas: [], schema: '', tables: [], search: '', loading: 'schemas', error: '' };
    if (!catalog) { browse = { ...browse, loading: '' }; return; }
    try {
      const data = await getBrowseSchemas(catalog);
      browse = { ...browse, schemas: data?.schemas || [], error: data?.access_error || '' };
    } catch {
      browse = { ...browse, error: $_('linking.errorGeneric') };
    } finally {
      browse = { ...browse, loading: '' };
    }
  }

  async function pickSchema(schema) {
    clearPick();
    browse = { ...browse, schema, tables: [], search: '', loading: 'tables', error: '' };
    if (!schema) { browse = { ...browse, loading: '' }; return; }
    try {
      const data = await getSchemaTables(schema, '', browse.catalog);
      browse = { ...browse, tables: data?.tables || [], error: data?.access_error || '' };
    } catch {
      browse = { ...browse, error: $_('linking.errorGeneric') };
    } finally {
      browse = { ...browse, loading: '' };
    }
  }

  function pickTable(t) {
    tableForm = { ...tableForm, table_fqn: t.table_fqn };
    modalReport = null;
    checkModalTable(); // verificação automática: o selo aparece sem clique extra
  }

  function switchToManual() {
    tableMode = 'manual';
    modalReport = null;
  }

  function openNewTable() {
    tableForm = { documento: cadocs[0]?.documento || '', table_fqn: '' };
    modalReport = null;
    tableMode = 'browse';
    browse = { catalogs: [], catalog: '', schemas: [], schema: '', tables: [], search: '', loading: '', error: '' };
    tableModalOpen = true;
    loadBrowseCatalogs();
  }

  async function checkModalTable() {
    if (!fqnValid) return;
    modalChecking = true;
    try {
      modalReport = await getTableAccess(tableForm.table_fqn.trim());
    } catch (e) {
      modalReport = null;
      showToast('error', tableErr(e));
    } finally {
      modalChecking = false;
    }
  }

  // Cadastra mesmo com pendência: o alerta acompanha a tabela na lista.
  async function saveTable() {
    const fqn = tableForm.table_fqn.trim();
    if (!tableForm.documento || !fqnValid) return;
    tableSaving = true;
    try {
      await associateCadocTable(tableForm.documento, { table_fqn: fqn });
      const report = modalReport?.table_fqn === fqn ? modalReport : await getTableAccess(fqn).catch(() => null);
      tableModalOpen = false;
      await loadTables();
      if (report) access = { ...access, [fqn]: { loading: false, report } };
      if (report && report.state !== 'passed') {
        expanded = fqn;
        showToast('info', $_('linking.associatedWithWarnings'), 6000);
      } else {
        showToast('success', $_('linking.associatedTable'));
      }
      loadCadocs(); // contagem de tabelas por CADOC
    } catch (e) {
      showToast('error', tableErr(e));
    } finally {
      tableSaving = false;
    }
  }

  async function onRemoveTable(t) {
    if (!confirm($_('linking.confirmRemoveTable', { values: { table: t.table_fqn, documento: t.documento } }))) return;
    try {
      await removeCadocTable(t.documento, t.table_fqn);
      await loadTables();
      loadCadocs();
      showToast('success', $_('linking.removedTable'));
    } catch (e) {
      showToast('error', tableErr(e));
    }
  }

  $effect(() => { if (activeTab === 'tables' && !tablesLoaded) loadTables(); });

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
              <th>{$_('linking.cadocColGroup')}</th>
              <th>{$_('linking.cadocColPeriodicity')}</th>
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
                <td>{c.grupo || '—'}</td>
                <td>{c.periodicidade ? $_(`periodicity.${c.periodicidade}`) : '—'}</td>
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
  {:else if activeTab === 'tables'}
    <div class="section-head">
      <button class="btn-primary" onclick={openNewTable} disabled={cadocs.length === 0}>+ {$_('linking.newTable')}</button>
    </div>

    {#if tablesLoading && cadocTables.length === 0}
      <div class="state">{$_('linking.loading')}</div>
    {:else if cadocTables.length === 0}
      <div class="state">{$_('linking.tablesEmptyAll')}</div>
    {:else}
      <div class="card">
        <table class="cadoc-table">
          <thead>
            <tr>
              <th>{$_('linking.cadocColDocument')}</th>
              <th>{$_('linking.ruleColTable')}</th>
              <th>{$_('linking.tableColOrigin')}</th>
              <th>{$_('linking.tableColAccess')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each cadocTables as t (t.documento + '|' + t.table_fqn)}
              {@const a = access[t.table_fqn]}
              <tr>
                <td class="mono">{t.documento}</td>
                <td class="mono">{t.table_fqn}</td>
                <td>
                  <Badge label={t.external ? $_('linking.originExternal') : $_('linking.originOwn')} variant={t.external ? 'info' : 'neutral'} />
                </td>
                <td>
                  {#if a?.loading}
                    <span class="muted">{$_('linking.accessChecking')}</span>
                  {:else if a?.report}
                    <button class="badge-btn" onclick={() => expanded = expanded === t.table_fqn ? '' : t.table_fqn}
                            title={$_('linking.accessToggle')}>
                      <Badge label={a.report.state === 'passed' ? $_('linking.accessOk') : $_('linking.accessPending')}
                             variant={a.report.state === 'passed' ? 'success' : 'warning'} />
                    </button>
                  {:else if !t.external}
                    <span class="muted" title={$_('linking.accessOwnTitle')}>{$_('linking.accessOwn')}</span>
                  {:else}
                    <span class="muted">—</span>
                  {/if}
                </td>
                <td class="actions">
                  <button class="btn-link-danger" onclick={() => onRemoveTable(t)}>{$_('linking.remove')}</button>
                </td>
              </tr>
              {#if expanded === t.table_fqn && a?.report}
                <tr class="expand-row"><td colspan="5">
                  <TableAccessCard report={a.report} rechecking={a.loading} onrecheck={() => verify(t.table_fqn)} />
                </td></tr>
              {/if}
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  {:else}
    <FilterBar filters={ruleFilterDefs} values={ruleFilters} onchange={ruleFilterChange} onreset={ruleFilterReset} />
    <!-- Vazio pode ser falta de permissão ou ausência de regra — o diagnóstico
         separa. Só sem filtro ativo: com filtro, vazio é resultado legítimo. -->
    <PrereqAlert active={!rulesLoading && rules.length === 0 && Object.keys(ruleFilters).length === 0} />
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
            <!-- `key` vem do backend: regras lidas dos runs não têm rule_id e podem
                 não ter name; chave repetida derruba o render. -->
            {#each rules as r (r.key)}
              {@const effName = isRuleGrain(r) ? r.definition_name : (r.current_link?.check_name || r.definition_name || (r.effective_check_names && r.effective_check_names[0]) || '—')}
              <tr>
                <td class="mono">{r.rule_id || '—'}</td>
                <td>
                  <span class="mono">{effName}</span>
                  {#if isRuleGrain(r)}
                    <div class="verifs" title={(r.verifications || []).map(v => v.check_name).join('\n')}>
                      <span class="verifs-label">{$_('linking.verificationsCount', { values: { n: r.verifications.length } })}</span>
                      {#each verifCols(r) as col}<span class="verif-chip mono">{col}</span>{/each}
                    </div>
                  {/if}
                </td>
                <td>{r.function || '—'}</td>
                <td class="mono tbl-cell">{r.table_fqn.split('.').pop()}</td>
                <td>{r.current_link?.documento || r.documento || '—'}</td>
                <td>
                  {#if r.current_link}
                    <Badge label={`${r.current_link.dimensao_r18} · ${r.current_link.dimension_name}`} variant="success" />
                  {:else if (r.legacy_links || []).length}
                    <span title={$_('linking.legacyTitle', { values: { cols: legacyCols(r).join(', ') } })}>
                      <Badge label={$_('linking.legacyBadge', { values: { n: r.legacy_links.length, total: r.verifications.length } })} variant="warning" />
                    </span>
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
    <label>{$_('linking.fieldPeriodicity')}
      <select bind:value={cadocForm.periodicidade}>
        <option value="">—</option>
        {#each PERIODICIDADES as p}
          <option value={p}>{$_(`periodicity.${p}`)}</option>
        {/each}
      </select>
    </label>
    <label>{$_('linking.fieldGroup')}
      <input type="text" bind:value={cadocForm.grupo} placeholder={$_('linking.fieldGroupHint')} />
    </label>
    <div class="form-actions">
      <button class="btn-secondary" onclick={() => cadocModalOpen = false}>{$_('linking.cancel')}</button>
      <button class="btn-primary" disabled={cadocSaving || !cadocForm.documento || !cadocForm.nome} onclick={saveCadoc}>{$_('linking.save')}</button>
    </div>
  </div>
</Modal>

<!-- Associar tabela (qualquer catálogo; a verificação só avisa) -->
<Modal open={tableModalOpen} title={$_('linking.newTableTitle')} onclose={() => tableModalOpen = false}>
  <div class="form">
    <label>{$_('linking.fieldCadoc')}
      <select bind:value={tableForm.documento}>
        {#each cadocs as c}
          <option value={c.documento}>{c.documento} — {c.nome}</option>
        {/each}
      </select>
    </label>
    <div class="mode-switch" role="tablist">
      <button class:active={tableMode === 'browse'} onclick={() => { tableMode = 'browse'; modalReport = null; tableForm = { ...tableForm, table_fqn: '' }; }}>
        {$_('linking.modeBrowse')}
      </button>
      <button class:active={tableMode === 'manual'} onclick={switchToManual}>{$_('linking.modeManual')}</button>
    </div>

    {#if tableMode === 'browse'}
      <p class="browse-tip">
        {$_('linking.browseTip')}
        <button class="btn-link inline" onclick={switchToManual}>{$_('linking.browseTipAction')}</button>
      </p>
      <div class="browse-row">
        <label>{$_('linking.fieldCatalog')}
          <select value={browse.catalog} onchange={(e) => pickCatalog(e.currentTarget.value)} disabled={browse.loading === 'catalogs'}>
            <option value="">{browse.loading === 'catalogs' ? $_('linking.loading') : '—'}</option>
            {#each browse.catalogs as c (c.name)}
              <option value={c.name}>{c.name}{c.own ? ` · ${$_('linking.originOwn')}` : ''}</option>
            {/each}
          </select>
        </label>
        <label>{$_('linking.schema')}
          <select value={browse.schema} onchange={(e) => pickSchema(e.currentTarget.value)}
                  disabled={!browse.catalog || browse.loading === 'schemas'}>
            <option value="">{browse.loading === 'schemas' ? $_('linking.loading') : '—'}</option>
            {#each browse.schemas as sc (sc)}
              <option value={sc}>{sc}</option>
            {/each}
          </select>
        </label>
      </div>

      {#if browse.error}
        <div class="browse-error">
          <strong>{$_('linking.browseNoAccessTitle')}</strong>
          <span>{$_('linking.browseNoAccess')}</span>
          <details><summary>{$_('prereq.technicalDetail')}</summary><pre>{browse.error}</pre></details>
        </div>
      {:else if browse.schema}
        <div class="table-picker">
          <input type="search" placeholder={$_('linking.searchTable')} bind:value={browse.search} />
          {#if browse.loading === 'tables'}
            <div class="picker-state">{$_('linking.loading')}</div>
          {:else if visibleTables.length === 0}
            <div class="picker-state">{$_('linking.browseNoTables')}</div>
          {:else}
            <ul>
              {#each visibleTables as t (t.table_fqn)}
                {@const here = t.already_linked_documento === tableForm.documento}
                <li>
                  <button class:selected={tableForm.table_fqn === t.table_fqn} disabled={here} onclick={() => pickTable(t)}>
                    <span class="mono">{t.table_name}</span>
                    {#if here}
                      <Badge label={$_('linking.alreadyHere')} variant="neutral" />
                    {:else if t.already_linked_documento}
                      <Badge label={$_('linking.linkedTo', { values: { documento: t.already_linked_documento } })} variant="info" />
                    {/if}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
      {#if tableForm.table_fqn}
        <div class="picked"><span>{$_('linking.picked')}</span> <span class="mono">{tableForm.table_fqn}</span></div>
      {/if}
    {:else}
      <label>{$_('linking.fieldTableFqn')}
        <input type="text" class="mono" bind:value={tableForm.table_fqn} placeholder="catalogo.schema.tabela"
               oninput={() => { modalReport = null; }} />
        {#if tableForm.table_fqn && !fqnValid}
          <small class="hint warn">{$_('linking.errorTableFqn')}</small>
        {:else}
          <small class="hint">{$_('linking.fieldTableFqnHint')}</small>
        {/if}
      </label>
    {/if}

    {#if modalChecking && !modalReport}
      <div class="picker-state">{$_('linking.accessChecking')}</div>
    {:else if modalReport}
      <TableAccessCard report={modalReport} />
    {/if}

    <div class="form-actions">
      <button class="btn-secondary" onclick={() => tableModalOpen = false}>{$_('linking.cancel')}</button>
      <button class="btn-secondary" disabled={!fqnValid || modalChecking} onclick={checkModalTable}>
        {modalChecking ? $_('linking.accessChecking') : $_('linking.verifyAccess')}
      </button>
      <button class="btn-primary" disabled={tableSaving || !fqnValid || !tableForm.documento} onclick={saveTable}>
        {modalReport && modalReport.state !== 'passed' ? $_('linking.associateAnyway') : $_('linking.associate')}
      </button>
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
      {#if isRuleGrain(editing)}
        <div class="rule-grain">
          <strong>{editing.definition_name}</strong>
          <p>{$_('linking.ruleGrainHint', { values: { n: editing.verifications.length } })}</p>
          <div class="verifs">{#each verifCols(editing) as col}<span class="verif-chip mono">{col}</span>{/each}</div>
          {#if (editing.legacy_links || []).length && !editing.current_link}
            <p class="hint warn">{$_('linking.legacyReplace', { values: { cols: legacyCols(editing).join(', ') } })}</p>
          {/if}
        </div>
      {:else}
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
      {/if}
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
  .badge-btn { background: none; border: none; padding: 0; cursor: pointer; }
  .expand-row td { background: var(--gray-50); padding: var(--space-3); }
  .cadoc-table tbody tr.expand-row:hover { background: var(--gray-50); }
  .btn-secondary.sm { padding: var(--space-1) var(--space-3); }
  .btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }

  .mode-switch { display: inline-flex; border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow: hidden; align-self: flex-start; }
  .mode-switch button { background: var(--white); border: none; padding: var(--space-1) var(--space-3); font-size: var(--font-size-sm); color: var(--gray-600); cursor: pointer; }
  .mode-switch button + button { border-left: 1px solid var(--border-color); }
  .mode-switch button.active { background: var(--primary); color: white; font-weight: 600; }
  .browse-tip { margin: 0; padding: var(--space-2) var(--space-3); background: var(--info-light); border-radius: var(--radius-sm); font-size: var(--font-size-xs); color: var(--gray-700); line-height: 1.5; }
  .btn-link.inline { padding: 0; font-size: var(--font-size-xs); text-decoration: underline; }
  .browse-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
  .browse-error { display: flex; flex-direction: column; gap: 2px; padding: var(--space-2) var(--space-3); background: var(--warning-light); color: var(--orange-900); border-radius: var(--radius-sm); font-size: var(--font-size-xs); }
  .browse-error pre { white-space: pre-wrap; word-break: break-word; margin: var(--space-1) 0 0; }
  .table-picker { border: 1px solid var(--border-color); border-radius: var(--radius-sm); overflow: hidden; }
  .table-picker input { width: 100%; border: none; border-bottom: 1px solid var(--border-color); border-radius: 0; box-sizing: border-box; }
  .table-picker ul { list-style: none; margin: 0; padding: 0; max-height: 200px; overflow-y: auto; }
  .table-picker li button { width: 100%; display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); background: var(--white); border: none; border-bottom: 1px solid var(--gray-100); padding: var(--space-2) var(--space-3); cursor: pointer; text-align: left; }
  .table-picker li button:hover:not(:disabled) { background: var(--blue-50); }
  .table-picker li button.selected { background: var(--info-light); box-shadow: inset 3px 0 0 var(--primary); }
  .table-picker li button:disabled { cursor: not-allowed; opacity: 0.6; }
  .picker-state { padding: var(--space-3); text-align: center; color: var(--gray-500); font-size: var(--font-size-sm); }
  .picked { font-size: var(--font-size-xs); color: var(--gray-600); }
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
  .verifs { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 4px; }
  .verifs-label { font-size: var(--font-size-xs); color: var(--gray-500); margin-right: 2px; }
  .verif-chip { font-size: 0.75em; padding: 1px 6px; border-radius: var(--radius-full); background: var(--gray-100); color: var(--gray-700); }
  .rule-grain { display: flex; flex-direction: column; gap: 4px; padding: var(--space-2) var(--space-3); border: 1px solid var(--border-color); border-radius: var(--radius-sm); font-size: var(--font-size-sm); }
  .rule-grain p { margin: 0; font-size: var(--font-size-xs); color: var(--gray-600); }
  .rule-grain .hint.warn { color: var(--orange-900); }

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
