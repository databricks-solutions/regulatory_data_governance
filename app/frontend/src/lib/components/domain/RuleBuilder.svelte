<script>
  import { fade } from 'svelte/transition';
  import { structuredToExpression, OPERATORS, SEVERITIES, DIMENSION_NAMES } from '$lib/ruleEngine.js';

  let { open = false, onclose, onsave } = $props();

  let mode = $state('structured');
  let name = $state('');
  let description = $state('');
  let nivel_verificacao = $state('1');
  let rule_type = $state('syntactic');
  let dimension_r18 = $state('');
  let severity = $state('error');
  let combinator = $state('AND');
  let conditions = $state([{ column: '{column_1}', operator: 'IS_NOT_NULL', value: null, value_is_column: false }]);
  let rawExpression = $state('');
  let paramCounter = $state(1);

  let structuredDef = $derived({
    version: 1,
    operator: combinator,
    conditions: conditions.map(c => ({
      column: c.column,
      operator: c.operator,
      value: c.value,
      value_is_column: c.value_is_column
    }))
  });

  let previewExpression = $derived(
    mode === 'structured' ? structuredToExpression(structuredDef) : rawExpression
  );

  let detectedParams = $derived.by(() => {
    const expr = mode === 'structured'
      ? JSON.stringify(structuredDef)
      : rawExpression;
    const matches = (expr || '').match(/\{([^}]+)\}/g);
    if (!matches) return [];
    return [...new Set(matches.map(m => m.slice(1, -1)))];
  });

  function addCondition() {
    paramCounter++;
    conditions = [...conditions, { column: `{column_${paramCounter}}`, operator: 'IS_NOT_NULL', value: null, value_is_column: false }];
  }

  function removeCondition(index) {
    conditions = conditions.filter((_, i) => i !== index);
  }

  function getOperatorMeta(op) {
    return OPERATORS.find(o => o.value === op) || {};
  }

  function handleSwitchToExpression() {
    if (mode === 'structured') {
      const expr = structuredToExpression(structuredDef);
      rawExpression = expr;
      mode = 'expression';
    }
  }

  function handleSave() {
    const params = detectedParams.map(p => ({ name: p, type: 'any', description: '' }));
    const rule = {
      name,
      description: description || null,
      nivel_verificacao: parseInt(nivel_verificacao),
      rule_type,
      dimension_r18: dimension_r18 ? parseInt(dimension_r18) : null,
      severity,
      authoring_mode: mode,
      structured_definition: mode === 'structured' ? structuredDef : null,
      expression: mode === 'expression' ? rawExpression : structuredToExpression(structuredDef),
      parameters: params,
      tags: []
    };
    onsave?.(rule);
    resetForm();
  }

  function resetForm() {
    name = '';
    description = '';
    nivel_verificacao = '1';
    rule_type = 'syntactic';
    dimension_r18 = '';
    severity = 'error';
    mode = 'structured';
    combinator = 'AND';
    conditions = [{ column: '{column_1}', operator: 'IS_NOT_NULL', value: null, value_is_column: false }];
    rawExpression = '';
    paramCounter = 1;
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
    <div class="builder-modal" onclick={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h3>Criar Regra</h3>
        <button class="modal-close" onclick={handleClose}>&times;</button>
      </div>

      <div class="modal-body">
        <!-- Metadata -->
        <div class="form-row">
          <div class="form-group flex-2">
            <label for="rb-name">Nome</label>
            <input id="rb-name" type="text" bind:value={name} placeholder="Ex: Campo obrigatorio NOT NULL" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group flex-2">
            <label for="rb-desc">Descricao (opcional)</label>
            <input id="rb-desc" type="text" bind:value={description} placeholder="Descricao da regra" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label for="rb-nivel">Nível</label>
            <select id="rb-nivel" bind:value={nivel_verificacao}>
              <option value="1">N1 — Verificações básicas</option>
              <option value="2">N2 — Coerência temporal</option>
              <option value="3">N3 — Regras negociais</option>
            </select>
          </div>
          <div class="form-group">
            <label for="rb-tipo">Tipo</label>
            <select id="rb-tipo" bind:value={rule_type}>
              <option value="syntactic">Sintática</option>
              <option value="semantic">Semântica</option>
              <option value="inter_document">Inter-documento</option>
              <option value="business">Regra Negocial</option>
            </select>
          </div>
          <div class="form-group">
            <label for="rb-dim">Dimensão R.18</label>
            <select id="rb-dim" bind:value={dimension_r18}>
              <option value="">Nenhuma</option>
              {#each DIMENSION_NAMES as dim, i}
                <option value={i + 1}>{i + 1} - {dim}</option>
              {/each}
            </select>
          </div>
          <div class="form-group">
            <label for="rb-sev">Severidade</label>
            <select id="rb-sev" bind:value={severity}>
              {#each SEVERITIES as s}
                <option value={s.value}>{s.label}</option>
              {/each}
            </select>
          </div>
        </div>

        <!-- Mode Toggle -->
        <div class="mode-toggle">
          <button class="mode-btn" class:active={mode === 'structured'} onclick={() => mode = 'structured'}>Estruturada</button>
          <button class="mode-btn" class:active={mode === 'expression'} onclick={handleSwitchToExpression}>Expressao</button>
        </div>

        {#if mode === 'structured'}
          <!-- Structured Builder -->
          <div class="builder-section">
            <div class="combinator-row">
              <span class="combinator-label">Combinar condicoes com:</span>
              <select class="combinator-select" bind:value={combinator}>
                <option value="AND">AND (todas devem passar)</option>
                <option value="OR">OR (pelo menos uma)</option>
              </select>
            </div>

            {#each conditions as cond, i}
              <div class="condition-row">
                <div class="condition-num">{i + 1}</div>
                <div class="condition-fields">
                  <div class="cond-field">
                    <label>Coluna</label>
                    <input type="text" bind:value={cond.column} placeholder="{'{'}column_1{'}'}" class="mono-input" />
                  </div>
                  <div class="cond-field">
                    <label>Operador</label>
                    <select bind:value={cond.operator}>
                      {#each OPERATORS as op}
                        <option value={op.value}>{op.label}</option>
                      {/each}
                    </select>
                  </div>
                  {#if getOperatorMeta(cond.operator).needsValue}
                    <div class="cond-field">
                      <label>Valor</label>
                      {#if getOperatorMeta(cond.operator).valueCount === 2}
                        <div class="between-inputs">
                          <input type="text" placeholder="Min"
                            value={Array.isArray(cond.value) ? cond.value[0] ?? '' : ''}
                            oninput={(e) => {
                              const arr = Array.isArray(cond.value) ? [...cond.value] : [null, null];
                              arr[0] = e.target.value;
                              cond.value = arr;
                            }} />
                          <span>ate</span>
                          <input type="text" placeholder="Max"
                            value={Array.isArray(cond.value) ? cond.value[1] ?? '' : ''}
                            oninput={(e) => {
                              const arr = Array.isArray(cond.value) ? [...cond.value] : [null, null];
                              arr[1] = e.target.value;
                              cond.value = arr;
                            }} />
                        </div>
                      {:else if getOperatorMeta(cond.operator).isList}
                        <input type="text" placeholder="Val1, Val2, Val3"
                          value={Array.isArray(cond.value) ? cond.value.join(', ') : cond.value ?? ''}
                          oninput={(e) => { cond.value = e.target.value.split(',').map(v => v.trim()).filter(Boolean); }} />
                      {:else}
                        <input type="text" bind:value={cond.value} placeholder="Valor ou {'{'}column_2{'}'}" />
                      {/if}
                    </div>
                    {#if getOperatorMeta(cond.operator).supportsColumn}
                      <div class="cond-field cond-checkbox">
                        <label>
                          <input type="checkbox" bind:checked={cond.value_is_column} />
                          Valor e coluna
                        </label>
                      </div>
                    {/if}
                  {/if}
                </div>
                {#if conditions.length > 1}
                  <button class="remove-btn" onclick={() => removeCondition(i)} title="Remover condicao">&times;</button>
                {/if}
              </div>
            {/each}

            <button class="add-condition-btn" onclick={addCondition}>+ Adicionar Condicao</button>
          </div>

        {:else}
          <!-- Expression Mode -->
          <div class="builder-section">
            <label class="expr-label">Expressao PySpark (use {'{'}column_N{'}'} para parametros)</label>
            <textarea class="expr-textarea" bind:value={rawExpression} rows="4" placeholder="Ex: {'{'}column_1{'}'} IS NOT NULL AND {'{'}column_1{'}'} > 0"></textarea>
            {#if detectedParams.length}
              <div class="detected-params">
                Parametros detectados: {detectedParams.map(p => `{${p}}`).join(', ')}
              </div>
            {/if}
          </div>
        {/if}

        <!-- Preview -->
        <div class="preview-section">
          <div class="preview-label">Preview da Expressao</div>
          <code class="preview-code">{previewExpression || '(vazio)'}</code>
        </div>

        {#if detectedParams.length}
          <div class="params-summary">
            <strong>Parametros ({detectedParams.length}):</strong>
            {#each detectedParams as p}
              <span class="param-tag">{'{' + p + '}'}</span>
            {/each}
          </div>
        {/if}
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" onclick={handleClose}>Cancelar</button>
        <button class="btn-primary" onclick={handleSave} disabled={!name || (!previewExpression && mode === 'structured')}>Salvar Regra</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.5);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000;
  }
  .builder-modal {
    background: var(--white);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-lg);
    width: 90%; max-width: 800px;
    max-height: 90vh; overflow-y: auto;
  }
  .modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: var(--space-5); border-bottom: 1px solid var(--border-color);
  }
  .modal-header h3 { margin: 0; }
  .modal-close { background: none; border: none; font-size: 1.5rem; color: var(--gray-500); cursor: pointer; }
  .modal-close:hover { color: var(--gray-900); }
  .modal-body { padding: var(--space-5); }
  .modal-footer {
    display: flex; gap: var(--space-3); justify-content: flex-end;
    padding: var(--space-4) var(--space-5); border-top: 1px solid var(--border-color);
  }

  .form-row { display: flex; gap: var(--space-4); margin-bottom: var(--space-4); }
  .form-group { flex: 1; }
  .form-group.flex-2 { flex: 2; }
  .form-group label {
    display: block; font-size: var(--font-size-sm); font-weight: 600;
    color: var(--gray-700); margin-bottom: var(--space-1);
  }
  .form-group input, .form-group select {
    width: 100%; padding: var(--space-2) var(--space-3);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm);
    font-size: var(--font-size-base); font-family: var(--font-primary);
  }
  .form-group input:focus, .form-group select:focus {
    outline: none; border-color: var(--primary); box-shadow: 0 0 0 2px var(--blue-100);
  }

  .mode-toggle {
    display: flex; gap: 0; margin-bottom: var(--space-4);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm); overflow: hidden; width: fit-content;
  }
  .mode-btn {
    padding: var(--space-2) var(--space-5); border: none;
    font-size: var(--font-size-sm); font-weight: 600; cursor: pointer;
    background: var(--white); color: var(--gray-700); transition: all 0.12s;
  }
  .mode-btn.active { background: var(--primary); color: white; }
  .mode-btn:not(.active):hover { background: var(--gray-100); }

  .builder-section {
    background: var(--gray-100); border-radius: var(--radius-md);
    padding: var(--space-4); margin-bottom: var(--space-4);
  }
  .combinator-row {
    display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-4);
  }
  .combinator-label { font-size: var(--font-size-sm); color: var(--gray-700); font-weight: 600; }
  .combinator-select {
    padding: var(--space-1) var(--space-3); border: 1px solid var(--gray-300);
    border-radius: var(--radius-sm); font-size: var(--font-size-sm); font-family: var(--font-primary);
  }

  .condition-row {
    display: flex; gap: var(--space-3); align-items: flex-start;
    background: var(--white); border: 1px solid var(--border-color);
    border-radius: var(--radius-sm); padding: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .condition-num {
    width: 24px; height: 24px; border-radius: var(--radius-full);
    background: var(--primary); color: white;
    display: flex; align-items: center; justify-content: center;
    font-size: var(--font-size-xs); font-weight: 700; flex-shrink: 0; margin-top: 20px;
  }
  .condition-fields { flex: 1; display: flex; flex-wrap: wrap; gap: var(--space-3); }
  .cond-field { min-width: 140px; flex: 1; }
  .cond-field label {
    display: block; font-size: var(--font-size-xs); color: var(--gray-500); margin-bottom: 2px;
  }
  .cond-field input, .cond-field select {
    width: 100%; padding: var(--space-1) var(--space-2);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm);
    font-size: var(--font-size-sm); font-family: var(--font-primary);
  }
  .cond-field input:focus, .cond-field select:focus {
    outline: none; border-color: var(--primary);
  }
  .mono-input { font-family: var(--font-mono) !important; }
  .cond-checkbox { display: flex; align-items: flex-end; min-width: 100px; }
  .cond-checkbox label {
    display: flex; align-items: center; gap: var(--space-1);
    font-size: var(--font-size-xs); cursor: pointer; white-space: nowrap;
  }
  .between-inputs { display: flex; align-items: center; gap: var(--space-2); }
  .between-inputs input { width: 80px; }
  .between-inputs span { font-size: var(--font-size-xs); color: var(--gray-500); }
  .remove-btn {
    background: none; border: none; color: var(--error);
    font-size: 1.2rem; cursor: pointer; padding: var(--space-1); margin-top: 18px;
  }
  .remove-btn:hover { color: var(--gray-900); }

  .add-condition-btn {
    padding: var(--space-2) var(--space-4); background: var(--white);
    border: 1px dashed var(--gray-300); border-radius: var(--radius-sm);
    color: var(--primary); font-weight: 600; font-size: var(--font-size-sm);
    cursor: pointer; width: 100%;
  }
  .add-condition-btn:hover { background: var(--blue-100); border-color: var(--primary); }

  .expr-label { display: block; font-size: var(--font-size-sm); font-weight: 600; color: var(--gray-700); margin-bottom: var(--space-2); }
  .expr-textarea {
    width: 100%; padding: var(--space-3);
    border: 1px solid var(--gray-300); border-radius: var(--radius-sm);
    font-family: var(--font-mono); font-size: var(--font-size-sm);
    resize: vertical; min-height: 80px;
  }
  .expr-textarea:focus { outline: none; border-color: var(--primary); }
  .detected-params {
    margin-top: var(--space-2); font-size: var(--font-size-xs); color: var(--gray-500);
    font-family: var(--font-mono);
  }

  .preview-section {
    background: var(--gray-100); border-radius: var(--radius-sm);
    padding: var(--space-3); margin-bottom: var(--space-4);
  }
  .preview-label { font-size: var(--font-size-xs); font-weight: 600; color: var(--gray-500); margin-bottom: var(--space-1); text-transform: uppercase; letter-spacing: 0.05em; }
  .preview-code {
    display: block; font-family: var(--font-mono); font-size: var(--font-size-sm);
    color: var(--blue-900); word-break: break-all;
  }

  .params-summary {
    font-size: var(--font-size-sm); color: var(--gray-700);
    display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
  }
  .param-tag {
    font-family: var(--font-mono); font-size: var(--font-size-xs);
    background: var(--blue-100); color: var(--primary);
    padding: 2px 8px; border-radius: var(--radius-full);
  }

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
