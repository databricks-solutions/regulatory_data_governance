<script>
  let { brandConfig, onUpdate, onClose } = $props();

  const PRESETS = [
    { id: 'default',  name: 'Azul Padrão',              primary: '#1E3A5F', accent: '#E84C3D' },
    { id: 'slate',   name: 'Cinza Profissional',         primary: '#1E293B', accent: '#0EA5E9' },
    { id: 'verde',   name: 'Verde Institucional',        primary: '#065F46', accent: '#D97706' },
    { id: 'roxo',    name: 'Roxo Executivo',             primary: '#4C1D95', accent: '#F59E0B' },
    { id: 'amber',   name: 'Âmbar Corporativo',          primary: '#78350F', accent: '#F59E0B' },
    { id: 'custom',  name: 'Personalizado',              primary: '',        accent: ''        },
  ];

  let name = $state(brandConfig.name);
  let selectedPreset = $state(brandConfig.theme_preset || 'default');
  let customPrimary = $state(brandConfig.primary_color);
  let customAccent = $state(brandConfig.accent_color);
  // originalLogoUrl tracks what was saved — used to detect an explicit removal
  const originalLogoUrl = brandConfig.logo_url;
  let logoPreview = $state(brandConfig.logo_url);
  let logoFile = $state(null);
  let logoRemoved = $state(false);
  let saving = $state(false);
  let error = $state('');

  let currentPrimary = $derived(
    selectedPreset !== 'custom'
      ? (PRESETS.find(p => p.id === selectedPreset)?.primary ?? customPrimary)
      : customPrimary
  );
  let currentAccent = $derived(
    selectedPreset !== 'custom'
      ? (PRESETS.find(p => p.id === selectedPreset)?.accent ?? customAccent)
      : customAccent
  );

  function selectPreset(preset) {
    selectedPreset = preset.id;
    if (preset.id !== 'custom') {
      customPrimary = preset.primary;
      customAccent = preset.accent;
    }
  }

  function handleLogoChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    logoFile = file;
    logoRemoved = false;
    logoPreview = URL.createObjectURL(file);
  }

  // Deferred removal — API call only happens in save()
  function removeLogo() {
    logoFile = null;
    logoPreview = null;
    logoRemoved = true;
  }

  async function save() {
    saving = true;
    error = '';
    try {
      let logoUrl = originalLogoUrl;

      if (logoFile) {
        const form = new FormData();
        form.append('file', logoFile);
        const res = await fetch('/api/v1/brand/logo', { method: 'POST', body: form });
        if (!res.ok) throw new Error('Falha no upload do logo');
        const data = await res.json();
        logoUrl = data.logo_url;
      } else if (logoRemoved && originalLogoUrl) {
        await fetch('/api/v1/brand/logo', { method: 'DELETE' });
        logoUrl = null;
      }

      const config = {
        name: name.trim() || 'BankCorp',
        primary_color: currentPrimary,
        accent_color: currentAccent,
        logo_url: logoUrl,
        theme_preset: selectedPreset,
      };

      const res = await fetch('/api/v1/brand/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error('Falha ao salvar configuração');
      const saved = await res.json();
      onUpdate(saved);
      onClose();
    } catch (e) {
      error = e.message;
    } finally {
      saving = false;
    }
  }

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) onClose();
  }

  function handleKeydown(e) {
    if (e.key === 'Escape') onClose();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div class="backdrop" onclick={handleBackdropClick} role="dialog" aria-modal="true" aria-label="Configurações de marca">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-title-area">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
        </svg>
        <h2>Configurações de Marca</h2>
      </div>
      <button class="close-btn" onclick={onClose} aria-label="Fechar">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <div class="modal-body">
      <!-- Logo -->
      <section class="section">
        <label class="section-label">Logo</label>
        <div class="logo-area">
          <div class="logo-preview-wrap">
            {#if logoPreview}
              <div class="logo-preview has-logo">
                <img src={logoPreview} alt="Logo atual" class="logo-img" />
              </div>
              <button class="logo-remove-x" onclick={removeLogo} title="Remover logo e usar padrão" aria-label="Remover logo">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round">
                  <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
              </button>
            {:else}
              <div class="logo-preview is-default">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                  <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>
                </svg>
                <span class="default-label">Padrão</span>
              </div>
            {/if}
          </div>
          <div class="logo-actions">
            <label class="btn-upload">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
              </svg>
              {logoPreview ? 'Trocar logo' : 'Enviar logo'}
              <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" onchange={handleLogoChange} hidden />
            </label>
            {#if logoPreview}
              <button class="btn-use-default" onclick={removeLogo}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                  <path d="M3 3v5h5"/>
                </svg>
                Usar logo padrão
              </button>
            {/if}
            <p class="logo-hint">PNG, SVG, JPEG ou WebP · Máx 2 MB</p>
          </div>
        </div>
      </section>

      <!-- System name -->
      <section class="section">
        <label class="section-label" for="brand-name">Nome do Sistema</label>
        <input
          id="brand-name"
          type="text"
          class="text-input"
          bind:value={name}
          placeholder="BankCorp"
          maxlength="60"
        />
      </section>

      <!-- Theme presets -->
      <section class="section">
        <label class="section-label">Tema de Cores</label>
        <div class="presets-grid">
          {#each PRESETS as preset}
            <button
              class="preset-btn"
              class:selected={selectedPreset === preset.id}
              onclick={() => selectPreset(preset)}
            >
              <div class="preset-swatches">
                {#if preset.id === 'custom'}
                  <div class="swatch" style="background: {customPrimary || '#ccc'}"></div>
                  <div class="swatch" style="background: {customAccent || '#ccc'}"></div>
                {:else}
                  <div class="swatch" style="background: {preset.primary}"></div>
                  <div class="swatch" style="background: {preset.accent}"></div>
                {/if}
              </div>
              <span class="preset-name">{preset.name}</span>
              {#if selectedPreset === preset.id}
                <svg class="preset-check" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <path d="M20 6L9 17l-5-5"/>
                </svg>
              {/if}
            </button>
          {/each}
        </div>

        {#if selectedPreset === 'custom'}
          <div class="custom-colors">
            <div class="color-field">
              <label class="color-label" for="primary-color">Cor primária</label>
              <div class="color-input-row">
                <input type="color" id="primary-color" class="color-picker" bind:value={customPrimary} />
                <input type="text" class="color-hex" bind:value={customPrimary} placeholder="#1E3A5F" maxlength="7" />
              </div>
            </div>
            <div class="color-field">
              <label class="color-label" for="accent-color">Cor de destaque</label>
              <div class="color-input-row">
                <input type="color" id="accent-color" class="color-picker" bind:value={customAccent} />
                <input type="text" class="color-hex" bind:value={customAccent} placeholder="#E84C3D" maxlength="7" />
              </div>
            </div>
          </div>
        {/if}

        <!-- Preview bar -->
        <div class="preview-bar" style="--preview-primary: {currentPrimary}; --preview-accent: {currentAccent}">
          <div class="preview-sidebar">
            <div class="preview-icon"></div>
            <div class="preview-nav-item active"></div>
            <div class="preview-nav-item"></div>
            <div class="preview-nav-item"></div>
          </div>
          <div class="preview-content">
            <div class="preview-header"></div>
            <div class="preview-card">
              <div class="preview-badge"></div>
            </div>
          </div>
        </div>
      </section>

      {#if error}
        <p class="error-msg">{error}</p>
      {/if}
    </div>

    <div class="modal-footer">
      <button class="btn-cancel" onclick={onClose}>Cancelar</button>
      <button class="btn-save" onclick={save} disabled={saving}>
        {#if saving}
          <svg class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M21 12a9 9 0 11-6.219-8.56"/>
          </svg>
          Salvando…
        {:else}
          Salvar configurações
        {/if}
      </button>
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 17, 23, 0.55);
    backdrop-filter: blur(4px);
    z-index: 200;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-6);
  }

  .modal {
    background: var(--white);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-xl);
    width: 100%;
    max-width: 520px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-5) var(--space-6);
    border-bottom: 1px solid var(--border-color);
    flex-shrink: 0;
  }
  .modal-title-area {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--gray-800);
  }
  .modal-title-area h2 {
    font-size: var(--font-size-md);
    font-weight: 700;
    color: var(--gray-900);
    letter-spacing: -0.01em;
  }
  .close-btn {
    background: none;
    border: none;
    color: var(--gray-400);
    padding: var(--space-1);
    border-radius: var(--radius-sm);
    cursor: pointer;
    display: flex;
    transition: color var(--transition-fast);
  }
  .close-btn:hover { color: var(--gray-700); }

  .modal-body {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-6);
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .section {}
  .section-label {
    display: block;
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--gray-700);
    margin-bottom: var(--space-3);
    letter-spacing: -0.01em;
  }

  /* Logo */
  .logo-area {
    display: flex;
    align-items: flex-start;
    gap: var(--space-4);
  }
  .logo-preview-wrap {
    position: relative;
    flex-shrink: 0;
  }
  .logo-preview {
    width: 80px;
    height: 56px;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--gray-50);
    overflow: hidden;
  }
  .logo-preview.is-default {
    flex-direction: column;
    gap: 3px;
    border-style: dashed;
  }
  .default-label {
    font-size: 9px;
    font-weight: 600;
    color: var(--gray-400);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .logo-img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .logo-remove-x {
    position: absolute;
    top: -7px;
    right: -7px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--error);
    border: 2px solid var(--white);
    color: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    transition: background var(--transition-fast);
    box-shadow: var(--shadow-sm);
  }
  .logo-remove-x:hover { background: var(--error-dark); }
  .logo-actions {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-start;
  }
  .btn-upload {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-4);
    background: var(--gray-100);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--font-size-sm);
    font-weight: 500;
    color: var(--gray-700);
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: var(--font-primary);
  }
  .btn-upload:hover { background: var(--gray-200); }
  .btn-use-default {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    background: none;
    border: none;
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    cursor: pointer;
    font-family: var(--font-primary);
    padding: 0;
    transition: color var(--transition-fast);
  }
  .btn-use-default:hover { color: var(--error); }
  .logo-hint { font-size: var(--font-size-xs); color: var(--gray-400); }

  /* Name input */
  .text-input {
    width: 100%;
    padding: var(--space-3) var(--space-4);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    font-size: var(--font-size-sm);
    font-family: var(--font-primary);
    font-weight: 500;
    color: var(--gray-800);
    background: var(--white);
    transition: border-color var(--transition-fast);
    outline: none;
  }
  .text-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 12%, transparent); }

  /* Presets */
  .presets-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-2);
  }
  .preset-btn {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-3);
    border: 1.5px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--white);
    cursor: pointer;
    transition: all var(--transition-fast);
    font-family: var(--font-primary);
    text-align: left;
    position: relative;
  }
  .preset-btn:hover { border-color: var(--gray-400); background: var(--gray-50); }
  .preset-btn.selected { border-color: var(--primary); background: color-mix(in srgb, var(--primary) 5%, white); }
  .preset-swatches { display: flex; gap: 4px; flex-shrink: 0; }
  .swatch { width: 16px; height: 16px; border-radius: 4px; }
  .preset-name { font-size: var(--font-size-xs); font-weight: 500; color: var(--gray-700); flex: 1; }
  .preset-check { color: var(--primary); flex-shrink: 0; }

  /* Custom colors */
  .custom-colors {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-4);
    margin-top: var(--space-3);
    padding: var(--space-4);
    background: var(--gray-50);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-color);
  }
  .color-label { display: block; font-size: var(--font-size-xs); font-weight: 600; color: var(--gray-600); margin-bottom: var(--space-2); }
  .color-input-row { display: flex; align-items: center; gap: var(--space-2); }
  .color-picker {
    width: 36px;
    height: 36px;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    cursor: pointer;
    padding: 2px;
    background: var(--white);
  }
  .color-hex {
    flex: 1;
    padding: var(--space-2) var(--space-2);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    font-size: var(--font-size-xs);
    font-family: var(--font-mono);
    color: var(--gray-800);
    background: var(--white);
    outline: none;
  }
  .color-hex:focus { border-color: var(--primary); }

  /* Preview bar */
  .preview-bar {
    margin-top: var(--space-4);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow: hidden;
    height: 72px;
    display: flex;
    background: var(--gray-50);
  }
  .preview-sidebar {
    width: 48px;
    background: var(--preview-primary, #1E3A5F);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 8px 6px;
    gap: 6px;
    flex-shrink: 0;
  }
  .preview-icon {
    width: 24px;
    height: 16px;
    background: white;
    border-radius: 3px;
    opacity: 0.9;
  }
  .preview-nav-item {
    width: 28px;
    height: 8px;
    background: white;
    border-radius: 3px;
    opacity: 0.25;
  }
  .preview-nav-item.active {
    background: var(--preview-accent, #E84C3D);
    opacity: 0.85;
  }
  .preview-content {
    flex: 1;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .preview-header {
    height: 10px;
    background: var(--gray-200);
    border-radius: 3px;
    width: 60%;
  }
  .preview-card {
    flex: 1;
    background: var(--white);
    border-radius: 4px;
    border: 1px solid var(--gray-200);
    display: flex;
    align-items: center;
    padding: 6px;
  }
  .preview-badge {
    width: 40px;
    height: 8px;
    background: var(--preview-accent, #E84C3D);
    border-radius: 3px;
    opacity: 0.7;
  }

  .error-msg {
    font-size: var(--font-size-sm);
    color: var(--error);
    background: var(--error-light);
    padding: var(--space-3) var(--space-4);
    border-radius: var(--radius-md);
  }

  .modal-footer {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-6);
    border-top: 1px solid var(--border-color);
    flex-shrink: 0;
  }
  .btn-cancel {
    padding: var(--space-2) var(--space-5);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    background: var(--white);
    font-size: var(--font-size-sm);
    font-weight: 500;
    color: var(--gray-700);
    cursor: pointer;
    font-family: var(--font-primary);
    transition: all var(--transition-fast);
  }
  .btn-cancel:hover { background: var(--gray-100); }
  .btn-save {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-6);
    background: var(--primary);
    border: none;
    border-radius: var(--radius-md);
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: white;
    cursor: pointer;
    font-family: var(--font-primary);
    transition: all var(--transition-fast);
  }
  .btn-save:hover:not(:disabled) { background: color-mix(in srgb, var(--primary) 85%, black); }
  .btn-save:disabled { opacity: 0.65; cursor: not-allowed; }

  @keyframes spin { to { transform: rotate(360deg); } }
  .spin { animation: spin 0.8s linear infinite; }
</style>
