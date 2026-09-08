<script>
  // "Novo metadado externo" — mirrors the native Catalog Explorer
  // "New external metadata" dialog: Name*, System type* (searchable dropdown
  // with icons), Entity type, URL, Description, Advanced options (owner,
  // columns, properties incl. camada/sistema/ingestion_mode), and a "Ver JSON"
  // toggle. Writes through to the UC External Metadata API via the backend.
  import { _ } from 'svelte-i18n';
  import Modal from '$lib/components/ui/Modal.svelte';
  import SystemTypeIcon from './SystemTypeIcon.svelte';
  import { createExternalObjectWithLineage, updateExternalMetadata } from '$lib/api.js';

  let { open = false, systemTypes = [], externalObjects = [], ucTables = [], editing = null, onclose, onsaved } = $props();

  const LAYERS = ['origin', 'source', 'etl', 'bronze', 'silver', 'gold', 'validator', 'output'];
  const ENTITY_TYPES = ['TABLE', 'JOB', 'PROCESS', 'DATASET', 'APPLICATION', 'FILE', 'DASHBOARD'];
  const INGESTION_MODES = ['', 'file_autoloader', 'federation', 'lakeflow_connect'];

  // ---- form state ----
  let name = $state('');
  let systemType = $state('OTHER');
  let entityType = $state('TABLE');
  let url = $state('');
  let description = $state('');
  let columnsText = $state('');           // one column per line
  // NOTE: no `owner` field — the External Metadata API sets owner server-side.
  let camada = $state('source');
  let sistema = $state('');
  let ingestionMode = $state('');
  let extraProps = $state([]);            // [{key, value}]
  let showAdvanced = $state(false);
  let showJson = $state(false);
  let typeSearch = $state('');
  let typeOpen = $state(false);
  let saving = $state(false);
  let error = $state('');

  // ---- lineage connection (required on create) ----
  // The new object must be wired to a node so the graph shows it and the
  // namespace stays coherent. connectDir = is the NEW object the source (feeds
  // the node) or the target (fed by it)? connectKind/connectValue = the node.
  let connectDir = $state('target');      // 'source' | 'target'
  let connectKind = $state('table');      // 'table' | 'external'
  let connectValue = $state('');
  let mappings = $state([]);              // [{source, target}]

  // Reset/prefill whenever the modal opens (create vs edit).
  $effect(() => {
    if (open) {
      error = '';
      if (editing) {
        name = editing.name;
        systemType = editing.system_type || 'OTHER';
        entityType = editing.entity_type || 'TABLE';
        url = editing.url || '';
        description = editing.description || '';
        columnsText = (editing.columns || []).join('\n');
        const p = { ...(editing.properties || {}) };
        camada = p.camada || 'source'; delete p.camada;
        sistema = p.sistema || ''; delete p.sistema;
        ingestionMode = p.ingestion_mode || ''; delete p.ingestion_mode;
        delete p.label;
        extraProps = Object.entries(p).map(([key, value]) => ({ key, value }));
      } else {
        name = ''; systemType = 'OTHER'; entityType = 'TABLE'; url = '';
        description = ''; columnsText = ''; camada = 'source';
        sistema = ''; ingestionMode = ''; extraProps = [];
      }
      // Connection defaults: new source objects feed a bronze table; reset each open.
      connectDir = 'target';
      connectKind = 'table';
      connectValue = ucTables[0]?.full_name || '';
      mappings = [];
      showAdvanced = false; showJson = false; typeSearch = ''; typeOpen = false;
    }
  });

  const selectedType = $derived(systemTypes.find(t => t.value === systemType) || { value: systemType, label: systemType, icon: 'custom' });
  const filteredTypes = $derived(
    typeSearch
      ? systemTypes.filter(t => t.label.toLowerCase().includes(typeSearch.toLowerCase()) || t.value.toLowerCase().includes(typeSearch.toLowerCase()))
      : systemTypes
  );

  function buildProperties() {
    const props = {};
    if (camada) props.camada = camada;
    if (sistema) props.sistema = sistema;
    if (ingestionMode) props.ingestion_mode = ingestionMode;
    for (const { key, value } of extraProps) {
      if (key && key.trim()) props[key.trim()] = value;
    }
    return props;
  }

  const payload = $derived({
    name: name.trim(),
    system_type: systemType,
    entity_type: entityType,
    url: url.trim() || null,
    description: description.trim() || null,
    columns: columnsText.split('\n').map(c => c.trim()).filter(Boolean),
    properties: buildProperties()
  });

  function pickType(t) { systemType = t.value; typeOpen = false; typeSearch = ''; }
  function addProp() { extraProps = [...extraProps, { key: '', value: '' }]; }
  function removeProp(i) { extraProps = extraProps.filter((_, idx) => idx !== i); }
  function addMapping() { mappings = [...mappings, { source: '', target: '' }]; }
  function removeMapping(i) { mappings = mappings.filter((_, idx) => idx !== i); }

  const connectEndpoint = $derived(
    connectKind === 'external' ? { external_metadata_name: connectValue } : { table_name: connectValue }
  );

  async function submit() {
    if (!payload.name) { error = $_('lineageMgmt.errNameRequired'); return; }
    saving = true; error = '';
    try {
      if (editing) {
        // Name is immutable on update; send the rest. Connection editing is done
        // from the side panel, not here.
        const { name: _n, ...patch } = payload;
        await updateExternalMetadata(editing.name, patch);
      } else {
        if (!connectValue) { error = $_('lineageMgmt.errConnectRequired'); saving = false; return; }
        await createExternalObjectWithLineage({
          object: payload,
          connect_direction: connectDir,
          connect_to: connectEndpoint,
          columns: mappings.filter(m => m.source && m.target),
          relationship_properties: ingestionMode ? { ingestion_mode: ingestionMode } : {},
        });
      }
      onsaved?.();
    } catch (e) {
      error = e?.message || String(e);
    } finally {
      saving = false;
    }
  }
</script>

<Modal {open} title={editing ? $_('lineageMgmt.editTitle') : $_('lineageMgmt.newTitle')} {onclose}>
  <div class="form">
    {#if error}
      <div class="form-error">{error}</div>
    {/if}

    <div class="info-banner">{$_('lineageMgmt.formBanner')}</div>

    <!-- Name -->
    <label class="field">
      <span class="field-label">{$_('lineageMgmt.fieldName')} <span class="req">*</span></span>
      <input class="input" bind:value={name} disabled={!!editing}
        placeholder="oracle_tb_operacoes_credito" spellcheck="false" />
      {#if editing}
        <span class="field-hint">{$_('lineageMgmt.nameImmutable')}</span>
      {:else}
        <span class="field-hint">{$_('lineageMgmt.namePrefixHint')}</span>
      {/if}
    </label>

    <!-- System type (searchable dropdown with icons) -->
    <div class="field">
      <span class="field-label">{$_('lineageMgmt.fieldSystemType')} <span class="req">*</span></span>
      <div class="dropdown">
        <button type="button" class="input dropdown-toggle" onclick={() => typeOpen = !typeOpen}>
          <span class="dd-selected">
            <SystemTypeIcon icon={selectedType.icon} label={selectedType.label} />
            {selectedType.label}
          </span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        {#if typeOpen}
          <div class="dropdown-menu">
            <input class="input dd-search" placeholder={$_('lineageMgmt.searchType')} bind:value={typeSearch} />
            <div class="dd-list">
              {#each filteredTypes as t (t.value)}
                <button type="button" class="dd-item" class:active={t.value === systemType} onclick={() => pickType(t)}>
                  <SystemTypeIcon icon={t.icon} label={t.label} />
                  <span>{t.label}</span>
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    </div>

    <!-- Entity type -->
    <label class="field">
      <span class="field-label">{$_('lineageMgmt.fieldEntityType')}</span>
      <select class="input" bind:value={entityType}>
        {#each ENTITY_TYPES as et}<option value={et}>{et}</option>{/each}
      </select>
    </label>

    <!-- URL -->
    <label class="field">
      <span class="field-label">{$_('lineageMgmt.fieldUrl')}</span>
      <input class="input" bind:value={url} placeholder="jdbc:oracle:thin:@host:1521/DB" spellcheck="false" />
    </label>

    <!-- Description -->
    <label class="field">
      <span class="field-label">{$_('lineageMgmt.fieldDescription')}</span>
      <textarea class="input" rows="2" bind:value={description}></textarea>
    </label>

    <!-- Camada + sistema + ingestion mode — RC18 graph placement -->
    <div class="field-row">
      <label class="field">
        <span class="field-label">{$_('lineageMgmt.fieldCamada')}</span>
        <select class="input" bind:value={camada}>
          {#each LAYERS as l}<option value={l}>{l}</option>{/each}
        </select>
      </label>
      <label class="field">
        <span class="field-label">{$_('lineageMgmt.fieldIngestion')}</span>
        <select class="input" bind:value={ingestionMode}>
          {#each INGESTION_MODES as m}
            <option value={m}>{m ? $_(`lineageMgmt.ingestion_${m}`) : '—'}</option>
          {/each}
        </select>
      </label>
    </div>
    <label class="field">
      <span class="field-label">{$_('lineageMgmt.fieldSistema')}</span>
      <input class="input" bind:value={sistema} placeholder="Oracle Core Banking 19c / IBM z/OS COBOL" spellcheck="false" />
    </label>

    <!-- Conectar linhagem (obrigatório na criação) -->
    {#if !editing}
      <div class="connect-box">
        <div class="connect-title">{$_('lineageMgmt.connectTitle')} <span class="req">*</span></div>
        <div class="connect-hint">{$_('lineageMgmt.connectHint')}</div>

        <!-- Direction -->
        <div class="dir-toggle">
          <button type="button" class:active={connectDir === 'source'} onclick={() => connectDir = 'source'}>
            {$_('lineageMgmt.dirSource')}
          </button>
          <button type="button" class:active={connectDir === 'target'} onclick={() => connectDir = 'target'}>
            {$_('lineageMgmt.dirTarget')}
          </button>
        </div>

        <!-- Node kind + value -->
        <div class="kind-toggle">
          <button type="button" class:active={connectKind === 'table'}
            onclick={() => { connectKind = 'table'; connectValue = ucTables[0]?.full_name || ''; }}>{$_('lineageMgmt.ucTable')}</button>
          <button type="button" class:active={connectKind === 'external'}
            onclick={() => { connectKind = 'external'; connectValue = externalObjects[0]?.name || ''; }}>{$_('lineageMgmt.externalObject')}</button>
        </div>
        {#if connectKind === 'table'}
          <select class="input" bind:value={connectValue}>
            {#each ucTables as t}<option value={t.full_name}>{t.full_name}</option>{/each}
          </select>
        {:else}
          <select class="input" bind:value={connectValue}>
            {#if externalObjects.length === 0}<option value="">{$_('lineageMgmt.noOtherObjects')}</option>{/if}
            {#each externalObjects as o}<option value={o.name}>{o.name}</option>{/each}
          </select>
        {/if}

        <!-- Optional column mappings -->
        {#each mappings as m, i}
          <div class="map-row">
            <input class="input mono" placeholder={$_('lineageMgmt.sourceCol')} bind:value={m.source} spellcheck="false" />
            <span class="map-arrow">→</span>
            <input class="input mono" placeholder={$_('lineageMgmt.targetCol')} bind:value={m.target} spellcheck="false" />
            <button type="button" class="prop-del" onclick={() => removeMapping(i)} aria-label="remover">×</button>
          </div>
        {/each}
        <button type="button" class="prop-add" onclick={addMapping}>+ {$_('lineageMgmt.addMapping')}</button>
      </div>
    {/if}

    <!-- Advanced options -->
    <button type="button" class="advanced-toggle" onclick={() => showAdvanced = !showAdvanced}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        style="transform: rotate({showAdvanced ? 90 : 0}deg); transition: transform .15s;"><path d="M9 6l6 6-6 6"/></svg>
      {$_('lineageMgmt.advancedOptions')}
    </button>

    {#if showAdvanced}
      <div class="advanced">
        <!-- Owner is NOT editable: the External Metadata API sets it server-side
             and rejects a supplied owner ("Must not supply an owner"). -->
        <label class="field">
          <span class="field-label">{$_('lineageMgmt.fieldColumns')}</span>
          <textarea class="input mono" rows="3" bind:value={columnsText} placeholder="CD_IPOC&#10;CD_CNPJ_IF&#10;VLR_CONTABIL"></textarea>
          <span class="field-hint">{$_('lineageMgmt.columnsHint')}</span>
        </label>
        <div class="field">
          <span class="field-label">{$_('lineageMgmt.fieldProperties')}</span>
          {#each extraProps as prop, i}
            <div class="prop-row">
              <input class="input mono" placeholder="chave" bind:value={prop.key} spellcheck="false" />
              <input class="input mono" placeholder="valor" bind:value={prop.value} spellcheck="false" />
              <button type="button" class="prop-del" onclick={() => removeProp(i)} aria-label="remover">×</button>
            </div>
          {/each}
          <button type="button" class="prop-add" onclick={addProp}>+ {$_('lineageMgmt.addProperty')}</button>
        </div>
      </div>
    {/if}

    <!-- View JSON -->
    <button type="button" class="json-toggle" onclick={() => showJson = !showJson}>
      &lt;/&gt; {showJson ? $_('lineageMgmt.hideJson') : $_('lineageMgmt.viewJson')}
    </button>
    {#if showJson}
      <pre class="json-view">{JSON.stringify(payload, null, 2)}</pre>
    {/if}

    <!-- Actions -->
    <div class="form-actions">
      <button class="btn btn-secondary" onclick={onclose} disabled={saving}>{$_('common.cancel')}</button>
      <button class="btn btn-primary" onclick={submit} disabled={saving}>
        {saving ? $_('common.saving') : (editing ? $_('common.save') : $_('lineageMgmt.create'))}
      </button>
    </div>
  </div>
</Modal>

<style>
  .form { display: flex; flex-direction: column; gap: var(--space-3); }
  .info-banner {
    background: var(--blue-50, #E5F0F8); color: var(--blue-800, #003D73);
    border: 1px solid var(--blue-200, #B3D4EA); border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-3); font-size: var(--font-size-xs);
  }
  .form-error {
    background: #FDECEA; color: #B71C1C; border: 1px solid #F5C6C0;
    border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); font-size: var(--font-size-sm);
  }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
  .field-label { font-size: var(--font-size-xs); font-weight: 700; color: var(--gray-700); }
  .req { color: #C62828; }
  .field-hint { font-size: 11px; color: var(--gray-500); }
  .input {
    width: 100%; padding: 8px 10px; border: 1px solid var(--border-color);
    border-radius: var(--radius-md); font-size: var(--font-size-sm);
    background: var(--white); color: var(--gray-900); box-sizing: border-box;
  }
  .input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(0,92,169,0.12); }
  .input.mono { font-family: var(--font-mono); font-size: 12px; }
  textarea.input { resize: vertical; }

  /* dropdown */
  .dropdown { position: relative; }
  .dropdown-toggle { display: flex; align-items: center; justify-content: space-between; cursor: pointer; text-align: left; }
  .dd-selected { display: flex; align-items: center; gap: 8px; }
  .dropdown-menu {
    position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 20;
    background: var(--white); border: 1px solid var(--border-color); border-radius: var(--radius-md);
    box-shadow: var(--shadow-lg); padding: 6px; max-height: 280px; display: flex; flex-direction: column;
  }
  .dd-search { margin-bottom: 6px; }
  .dd-list { overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  .dd-item {
    display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: none; background: none;
    border-radius: var(--radius-sm); cursor: pointer; font-size: var(--font-size-sm); text-align: left; width: 100%;
  }
  .dd-item:hover { background: var(--gray-100); }
  .dd-item.active { background: var(--blue-100, #E5F0F8); font-weight: 600; }

  .advanced-toggle, .json-toggle {
    display: flex; align-items: center; gap: 6px; background: none; border: none;
    color: var(--primary); font-size: var(--font-size-sm); font-weight: 600; cursor: pointer; padding: 4px 0;
  }
  .advanced { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-3);
    background: var(--gray-50); border-radius: var(--radius-md); }
  .prop-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 6px; margin-bottom: 6px; align-items: center; }
  .prop-del { background: none; border: 1px solid var(--border-color); border-radius: var(--radius-sm);
    width: 28px; height: 28px; cursor: pointer; color: var(--gray-500); font-size: 16px; }
  .prop-del:hover { color: #C62828; border-color: #C62828; }
  .prop-add { background: none; border: 1px dashed var(--border-color); border-radius: var(--radius-sm);
    padding: 4px 10px; font-size: var(--font-size-xs); color: var(--gray-600); cursor: pointer; }

  .json-view {
    background: #1E1E2E; color: #CDD6F4; border-radius: var(--radius-md);
    padding: var(--space-3); font-family: var(--font-mono); font-size: 11px; overflow-x: auto; margin: 0;
  }
  .form-actions { display: flex; justify-content: flex-end; gap: var(--space-2); margin-top: var(--space-2); }
  .btn { padding: 8px 16px; border-radius: var(--radius-md); font-size: var(--font-size-sm); font-weight: 600; cursor: pointer; border: 1px solid transparent; }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover:not(:disabled) { background: var(--blue-700, #004A8A); }
  .btn-secondary { background: var(--white); border-color: var(--border-color); color: var(--gray-700); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }

  /* Connect-lineage section */
  .connect-box { display: flex; flex-direction: column; gap: 8px; padding: var(--space-3);
    background: var(--blue-50, #EFF6FC); border: 1px solid var(--blue-200, #B3D4EA); border-radius: var(--radius-md); }
  .connect-title { font-size: var(--font-size-sm); font-weight: 700; color: var(--blue-800, #003D73); }
  .connect-hint { font-size: 11px; color: var(--gray-600); margin-top: -4px; }
  .dir-toggle, .kind-toggle { display: flex; gap: 0; }
  .dir-toggle button, .kind-toggle button {
    flex: 1; padding: 6px 10px; border: 1px solid var(--border-color); background: var(--white);
    font-size: var(--font-size-xs); cursor: pointer; color: var(--gray-600);
  }
  .dir-toggle button:first-child, .kind-toggle button:first-child { border-radius: var(--radius-md) 0 0 var(--radius-md); }
  .dir-toggle button:last-child, .kind-toggle button:last-child { border-radius: 0 var(--radius-md) var(--radius-md) 0; border-left: none; }
  .dir-toggle button.active, .kind-toggle button.active { background: var(--primary); color: #fff; border-color: var(--primary); }
  .map-row { display: grid; grid-template-columns: 1fr auto 1fr auto; gap: 6px; align-items: center; }
  .map-arrow { color: var(--gray-400); }
</style>
