<script>
  import { fade } from 'svelte/transition';
  import { resolveExpression, structuredToExpression } from '$lib/ruleEngine.js';

  let { open = false, rules = [], columns = [], onclose, onsave } = $props();

  let selectedRuleId = $state('');
  let columnBindings = $state({});

  let selectedRule = $derived(rules.find(r => r.rule_id === selectedRuleId));
  let ruleParams = $derived(selectedRule?.parameters || []);
  let ruleExpression = $derived.by(() => {
    if (!selectedRule) return '';
    if (selectedRule.authoring_mode === 'expression') return selectedRule.expression || '';
    if (selectedRule.structured_definition) return structuredToExpression(selectedRule.structured_definition);
    return '';
  });

  let resolvedPreview = $derived(resolveExpression(ruleExpression, columnBindings));
  let allBound = $derived(ruleParams.length > 0 && ruleParams.every(p => columnBindings[p.name]));

  function handleRuleChange() {
    columnBindings = {};
  }

  function handleSave() {
    if (!selectedRuleId || !allBound) return;
    onsave?.({
      rule_id: selectedRuleId,
      column_bindings: { ...columnBindings }
    });
    resetForm();
  }

  function resetForm() {
    selectedRuleId = '';
    columnBindings = {};
  }

  function handleClose() {
    resetForm();
    onclose?.();
  }
</script>

{#if open}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="modal-backdrop" transition:fade={{ duration: 150 }} onclick={handleClose}>
    <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
    <div class="binding-modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>Vincular Regra ao Dataset</h3>
        <button class="modal-close" onclick={handleClose}>&times;</button>
      </div>

      <div class="modal-body">
        <!-- Rule Selection -->
        <div class="form-group">
          <label for="bind-rule">Selecionar Regra</label>
          <select id="bind-rule" bind:value={selectedRuleId} onchange={handleRuleChange}>
            <option value="">-- Selecione uma regra --</option>
            {#each rules as rule}
              <option value={rule.rule_id}>{rule.name} ({rule.category})</option>
            {/each}
          </select>
        </div>

        {#if selectedRule}
          <div class="rule-info">
            <span class="rule-type">{selectedRule.rule_type === 'structured' ? 'Estruturada' : 'Expressao'}</span>
            <span class="rule-severity sev-{selectedRule.severity}">{selectedRule.severity}</span>
            {#if selectedRule.description}
              <p class="rule-desc">{selectedRule.description}</p>
            {/if}
          </div>

          <!-- Parameter Binding -->
          {#if ruleParams.length > 0}
            <div class="binding-section">
              <div class="binding-title">Vincular Parametros a Colunas</div>
              {#each ruleParams as param}
                <div class="param-row">
                  <div class="param-name">
                    <span class="param-tag">{'{' + param.name + '}'}</span>
                    {#if param.description}
                      <span class="param-desc">{param.description}</span>
                    {/if}
                  </div>
                  <div class="param-arrow">&#8594;</div>
                  <div class="param-col">
                    <select bind:value={columnBindings[param.name]}>
                      <option value="">-- Coluna --</option>
                      {#each columns as col}
                        <option value={col.name}>{col.name} ({col.type})</option>
                      {/each}
                    </select>
                  </div>
                </div>
              {/each}
            </div>
          {/if}

          <!-- Preview -->
          <div class="preview-section">
            <div class="preview-label">Expressao Resolvida</div>
            <code class="preview-code">{resolvedPreview || '(selecione colunas acima)'}</code>
          </div>
        {/if}
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" onclick={handleClose}>Cancelar</button>
        <button class="btn-primary" onclick={handleSave} disabled={!selectedRuleId || !allBound}>Vincular</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.5);
    display: flex; align-items: center; justify-content: center; z-index: 1000;
  }
  .binding-modal {
    background: var(--white); border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg); width: 90%; max-width: 600px;
    max-height: 85vh; overflow-y: auto;
  }
  .modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: var(--space-5); border-bottom: 1px solid var(--border-color);
  }
  .modal-header h3 { margin: 0; }
  .modal-close { background: none; border: none; font-size: 1.5rem; color: var(--gray-500); cursor: pointer; }
  .modal-body { padding: var(--space-5); }
  .modal-footer {
    display: flex; gap: var(--space-3); justify-content: flex-end;
    padding: var(--space-4) var(--space-5); border-top: 1px solid var(--border-color);
  }

  .form-group { margin-bottom: var(--space-4); }
  .form-group label {
    display: block; font-size: var(--font-size-sm); font-weight: 600;
    color: var(--gray-700); margin-bottom: var(--space-1);
  }
  .form-group select {
    width: 100%; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm);
    font-size: var(--font-size-base); font-family: var(--font-primary);
  }
  .form-group select:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px var(--blue-100); }

  .rule-info {
    display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap;
    margin-bottom: var(--space-4); padding: var(--space-3);
    background: var(--gray-100); border-radius: var(--radius-sm);
  }
  .rule-type {
    font-size: var(--font-size-xs); background: var(--blue-100); color: var(--primary);
    padding: 2px 8px; border-radius: var(--radius-full); font-weight: 600;
  }
  .rule-desc { font-size: var(--font-size-sm); color: var(--gray-500); width: 100%; margin: var(--space-2) 0 0; }

  .binding-section {
    background: var(--gray-100); border-radius: var(--radius-md);
    padding: var(--space-4); margin-bottom: var(--space-4);
  }
  .binding-title { font-size: var(--font-size-sm); font-weight: 600; color: var(--gray-700); margin-bottom: var(--space-3); }
  .param-row {
    display: flex; align-items: center; gap: var(--space-3);
    background: var(--white); border: 1px solid var(--border-color);
    border-radius: var(--radius-sm); padding: var(--space-3); margin-bottom: var(--space-2);
  }
  .param-name { flex: 1; display: flex; flex-direction: column; gap: 2px; }
  .param-tag {
    font-family: var(--font-mono); font-size: var(--font-size-sm);
    color: var(--primary); font-weight: 600;
  }
  .param-desc { font-size: var(--font-size-xs); color: var(--gray-500); }
  .param-arrow { color: var(--gray-400); font-size: var(--font-size-lg); }
  .param-col { flex: 1; }
  .param-col select {
    width: 100%; padding: var(--space-1) var(--space-2);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm);
    font-size: var(--font-size-sm); font-family: var(--font-primary);
  }

  .preview-section {
    background: var(--gray-100); border-radius: var(--radius-sm);
    padding: var(--space-3); margin-bottom: var(--space-2);
  }
  .preview-label { font-size: var(--font-size-xs); font-weight: 600; color: var(--gray-500); margin-bottom: var(--space-1); text-transform: uppercase; }
  .preview-code { display: block; font-family: var(--font-mono); font-size: var(--font-size-sm); color: var(--blue-900); word-break: break-all; }

  :global(.sev-error) { color: var(--error); font-weight: 600; }
  :global(.sev-warning) { color: var(--warning); font-weight: 600; }

  .btn-primary {
    padding: var(--space-2) var(--space-5); background: var(--primary);
    color: white; border: none; border-radius: var(--radius-sm);
    font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }
  .btn-primary:hover { background: var(--blue-500); }
  .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-secondary {
    padding: var(--space-2) var(--space-5); background: var(--gray-100);
    color: var(--gray-700); border: 1px solid var(--gray-300);
    border-radius: var(--radius-sm); font-weight: 600; font-size: var(--font-size-sm); cursor: pointer;
  }
</style>
