<script>
  import { _ } from 'svelte-i18n';
  import Spinner from '$lib/components/ui/Spinner.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import { uploadXml, getXmlTree, validateXml, getXmlFields } from '$lib/api.js';

  let fileId = $state(null);
  let docType = $state('3040');
  let uploading = $state(false);
  let fileMeta = $state(null);
  let treeData = $state(null);
  let selectedNodeFields = $state(null);
  let validating = $state(false);
  let validationResult = $state(null);

  let expandedPaths = $state(new Set(['', '0', '0.0']));

  function toggleNode(path) {
    const newSet = new Set(expandedPaths);
    if (newSet.has(path)) newSet.delete(path);
    else newSet.add(path);
    expandedPaths = newSet;
  }

  async function handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (file) await handleFile(file);
  }

  async function handleFileInput(event) {
    const file = event.target.files?.[0];
    if (file) await handleFile(file);
  }

  async function handleFile(file) {
    uploading = true;
    fileMeta = { name: file.name, size: (file.size / (1024 * 1024)).toFixed(1) + ' MB' };

    try {
      const resp = await uploadXml(file, docType);
      fileId = resp.file_id;
      const tree = await getXmlTree(fileId);
      treeData = tree;
    } catch {
      treeData = null;
    }
    uploading = false;
  }

  async function handleValidate() {
    if (!fileId) return;
    validating = true;
    try {
      validationResult = await validateXml(fileId);
    } catch {
      validationResult = null;
    }
    validating = false;
  }

  function handleNodeSelect(node) {
    selectedNodeFields = node.validation || {};
  }

  function getValidationIcon(status) {
    if (status === 'pass') return '\u25CF';
    if (status === 'error') return '\u2717';
    if (status === 'warning') return '\u25CF';
    return '\u25CB';
  }

  function getValidationColor(status) {
    if (status === 'pass') return 'var(--success)';
    if (status === 'error') return 'var(--error)';
    if (status === 'warning') return 'var(--warning)';
    return 'var(--gray-500)';
  }
</script>

<div class="xml-page">
  {#if !treeData}
    <!-- Upload Zone -->
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
      class="upload-zone"
      ondrop={handleDrop}
      ondragover={(e) => e.preventDefault()}
    >
      {#if uploading}
        <Spinner message={$_('xml.uploadingFile')} />
      {:else}
        <div class="upload-content">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--gray-300)" stroke-width="1.5">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
          </svg>
          <p class="upload-title">{$_('xml.uploadTitle')}</p>
          <p class="upload-sub">{$_('xml.uploadSub')}</p>
          <div class="upload-controls">
            <select class="type-select" bind:value={docType}>
              <option value="3040">SCR 3040</option>
              <option value="3050">SCR 3050</option>
            </select>
            <label class="file-btn">
              {$_('xml.selectFile')}
              <input type="file" accept=".xml" onchange={handleFileInput} hidden />
            </label>
          </div>
        </div>
      {/if}
    </div>
  {:else}
    <!-- File Summary -->
    <div class="card file-summary">
      <div class="file-info">
        <strong>{fileMeta?.name || $_('xml.defaultFileName')}</strong>
        <span class="file-size">{fileMeta?.size}</span>
      </div>
      <button class="validate-btn" onclick={handleValidate} disabled={validating}>
        {#if validating}{$_('xml.validating')}{:else}{$_('xml.validateXsd')}{/if}
      </button>
      {#if validationResult}
        <span class="val-result">
          {$_('xml.validationSummary', { values: { errors: validationResult.errors, warnings: validationResult.warnings, fields: validationResult.total_fields } })}
        </span>
      {/if}
    </div>

    <!-- Tree + Field Panel -->
    <div class="tree-panel-wrap">
      <div class="tree-view card">
        {#snippet renderNode(node, path, depth)}
          <div class="tree-node" style="padding-left: {depth * 20}px">
            <button class="tree-toggle" onclick={() => toggleNode(path)}>
              {#if node.children?.length > 0 || node.childCount > 0}
                {expandedPaths.has(path) ? '\u25BE' : '\u25B8'}
              {:else}
                &nbsp;
              {/if}
            </button>
            <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
            <span class="tree-tag" onclick={() => handleNodeSelect(node)}>{node.tag}</span>
            {#each Object.entries(node.attrs || {}) as [k, v]}
              <span class="tree-attr">
                <span class="attr-key">{k}</span>=<span class="attr-val">"{v}"</span>
                {#if node.validation?.[k]}
                  <span class="field-badge" style="color: {getValidationColor(node.validation[k])}">{getValidationIcon(node.validation[k])}</span>
                {/if}
              </span>
            {/each}
            {#if node.childCount > 0 && !expandedPaths.has(path)}
              <span class="child-count">({node.childCount})</span>
            {/if}
          </div>
          {#if expandedPaths.has(path) && node.children}
            {#each node.children as child, i}
              {@render renderNode(child, `${path}.${i}`, depth + 1)}
            {/each}
          {/if}
        {/snippet}

        {@render renderNode(treeData, '', 0)}
      </div>

      <!-- Field Detail Panel -->
      <div class="field-panel card">
        {#if selectedNodeFields && Object.keys(selectedNodeFields).length > 0}
          <h4 class="panel-title">{$_('xml.fieldValidation')}</h4>
          {#each Object.entries(selectedNodeFields) as [field, status]}
            <div class="field-row">
              <span class="field-name">{field}</span>
              <span class="field-status" style="color: {getValidationColor(status)}">
                {getValidationIcon(status)} {status}
              </span>
            </div>
          {/each}
        {:else}
          <p class="panel-empty">{$_('xml.clickElement')}</p>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .xml-page { display: flex; flex-direction: column; gap: var(--space-4); }

  .upload-zone {
    border: 2px dashed var(--gray-300);
    border-radius: var(--radius-lg);
    padding: var(--space-12);
    text-align: center;
    background: var(--white);
    transition: border-color 0.15s;
    min-height: 300px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .upload-zone:hover { border-color: var(--primary); }
  .upload-content { display: flex; flex-direction: column; align-items: center; gap: var(--space-3); }
  .upload-title { font-size: var(--font-size-md); font-weight: 600; color: var(--gray-700); }
  .upload-sub { font-size: var(--font-size-sm); color: var(--gray-500); }
  .upload-controls { display: flex; gap: var(--space-3); align-items: center; margin-top: var(--space-3); }
  .type-select {
    padding: var(--space-2) var(--space-3);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-family: var(--font-primary);
  }
  .file-btn {
    padding: var(--space-2) var(--space-5);
    background: var(--primary);
    color: white;
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: var(--font-size-sm);
    cursor: pointer;
  }

  .file-summary {
    display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap;
  }
  .file-info { display: flex; gap: var(--space-2); align-items: baseline; }
  .file-size { font-size: var(--font-size-sm); color: var(--gray-500); }
  .validate-btn {
    padding: var(--space-2) var(--space-5);
    background: var(--primary);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: var(--font-size-sm);
  }
  .validate-btn:disabled { opacity: 0.6; }
  .val-result { font-size: var(--font-size-sm); color: var(--gray-500); }

  .tree-panel-wrap { display: flex; gap: var(--space-4); min-height: 400px; }
  .tree-view { flex: 2; overflow: auto; font-family: var(--font-mono); font-size: var(--font-size-sm); max-height: calc(100vh - 300px); }
  .field-panel { flex: 1; min-width: 240px; }

  .tree-node { display: flex; align-items: center; gap: var(--space-1); padding: 2px 0; white-space: nowrap; }
  .tree-toggle { background: none; border: none; width: 16px; font-size: 12px; color: var(--gray-500); flex-shrink: 0; }
  .tree-tag { color: var(--primary); font-weight: 600; cursor: pointer; }
  .tree-tag:hover { text-decoration: underline; }
  .tree-attr { margin-left: var(--space-1); }
  .attr-key { color: var(--orange-900); }
  .attr-val { color: var(--gray-700); }
  .field-badge { margin-left: 2px; font-size: 10px; }
  .child-count { color: var(--gray-500); font-size: var(--font-size-xs); margin-left: var(--space-1); }

  .panel-title { font-size: var(--font-size-md); margin-bottom: var(--space-4); }
  .field-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: var(--space-2) 0; border-bottom: 1px solid var(--gray-100);
  }
  .field-name { font-family: var(--font-mono); font-size: var(--font-size-sm); color: var(--gray-700); }
  .field-status { font-size: var(--font-size-sm); font-weight: 600; }
  .panel-empty { color: var(--gray-500); font-size: var(--font-size-sm); }
</style>
