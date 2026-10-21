<script>
  // Nó do grafo de Linhagem: cartão com ícone, nome e camada/sistema. Entra pela
  // esquerda e sai pela direita — o fluxo do grafo é da esquerda para a direita.
  import { Handle, Position } from '@xyflow/svelte';
  import SystemTypeIcon from './SystemTypeIcon.svelte';
  import { lineageView } from '$lib/lineageView.svelte.js';

  let { id, data } = $props();

  const dimmed = $derived(lineageView.pathNodes !== null && !lineageView.pathNodes.has(id));
  const focused = $derived(lineageView.focusId === id);
</script>

<div class="lnode" class:dimmed class:focused style="--accent:{data.accent};" title={data.fullName}>
  <Handle type="target" position={Position.Left} isConnectable={false} />
  <span class="icon">
    {#if data.external}
      <SystemTypeIcon icon={lineageView.icons[data.system_type] || 'custom'} label={data.system} size={18} />
    {:else}
      <!-- Tabela UC: grade na cor da camada. -->
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"
        fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M3 9.5 H21 M3 14.5 H21 M9 9.5 V20" />
      </svg>
    {/if}
  </span>
  <span class="text">
    <span class="title">{data.label}</span>
    {#if data.subtitle}<span class="subtitle">{data.subtitle}</span>{/if}
  </span>
  <Handle type="source" position={Position.Right} isConnectable={false} />
</div>

<style>
  .lnode {
    width: 100%;
    height: 100%;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px 0 8px;
    background: var(--white);
    border: 1px solid var(--gray-200);
    border-left: 4px solid var(--accent);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(16, 24, 40, 0.08);
    cursor: pointer;
    transition: opacity 0.15s ease, box-shadow 0.15s ease;
  }
  .lnode:hover, .lnode.focused {
    box-shadow: 0 0 0 2px var(--accent), 0 4px 12px rgba(16, 24, 40, 0.12);
  }
  .lnode.dimmed { opacity: 0.25; }
  .icon {
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: color-mix(in srgb, var(--accent) 12%, transparent);
  }
  .text { min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }
  .title {
    font-size: 12px;
    font-weight: 600;
    color: var(--gray-800);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subtitle {
    font-size: 10px;
    color: var(--gray-500);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  /* Conexões não são editáveis no grafo: os handles só ancoram as arestas. */
  .lnode :global(.svelte-flow__handle) { opacity: 0; pointer-events: none; }
</style>
