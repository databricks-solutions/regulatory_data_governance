<script>
  import { onMount } from 'svelte';
  import { getLineageGraph, getColumnLineage } from '$lib/api.js';
  import { layerColors } from '$lib/theme.js';

  let SvelteFlow, MiniMap, Controls, Background;
  let flowLoaded = $state(false);
  let nodeStylesApplied = false;

  let selectedNode = $state(null);
  let columnLineage = $state(null);

  let nodes = $state([]);
  let edges = $state([]);

  function handleNodeClick(event) {
    const node = event.detail?.node || event.node;
    if (node) {
      selectedNode = node;
      columnLineage = null;
    }
  }

  async function handleColumnClick(col) {
    const tableName = selectedNode?.id;
    columnLineage = { column: col, loading: true };
    try {
      const data = await getColumnLineage(tableName, col);
      columnLineage = { column: col, ...data, loading: false };
    } catch {
      columnLineage = { column: col, loading: false, upstream_columns: [] };
    }
  }

  function getNodeStyle(layer) {
    const c = layerColors[layer] || layerColors.source;
    return `background: ${c.bg}; border: 2px solid ${c.border}; color: ${c.text}; border-radius: 8px; padding: 10px 16px; font-size: 13px; font-weight: 600; box-shadow: 0 2px 4px rgba(0,0,0,0.08); min-width: 160px;`;
  }

  onMount(async () => {
    // Apply styles to nodes
    nodes = nodes.map(n => ({ ...n, style: getNodeStyle(n.data.layer) }));

    // Load Svelte Flow dynamically
    try {
      const mod = await import('@xyflow/svelte');
      SvelteFlow = mod.SvelteFlow;
      MiniMap = mod.MiniMap;
      Controls = mod.Controls;
      Background = mod.Background;
      await import('@xyflow/svelte/dist/style.css');
      flowLoaded = true;
    } catch (err) {
      console.warn('Svelte Flow not available, using SVG fallback:', err);
    }

    // Try to fetch real lineage data from API
    try {
      const data = await getLineageGraph();
      if (data?.nodes) {
        nodes = data.nodes.map((n, i) => ({
          id: n.id,
          position: { x: 50 + (i % 4) * 300, y: 50 + Math.floor(i / 4) * 150 },
          data: { label: n.label, layer: n.layer, type: n.type, ...n.metadata },
          type: 'default',
          style: getNodeStyle(n.layer)
        }));
        edges = data.edges.map((e, i) => ({
          id: `e${i}`,
          source: e.source,
          target: e.target,
          type: 'default',
          animated: e.type === 'uc_automatic'
        }));
      }
    } catch {}
  });
</script>

<div class="lineage-page">
  <div class="lineage-content">
    <!-- Graph Area -->
    <div class="graph-area">
      {#if flowLoaded && SvelteFlow}
        <svelte:component this={SvelteFlow} {nodes} {edges} fitView on:nodeclick={handleNodeClick}>
          <svelte:component this={Controls} position="bottom-right" />
          <svelte:component this={MiniMap} position="bottom-left" />
          <svelte:component this={Background} variant="dots" gap={20} size={1} />
        </svelte:component>
      {:else}
        <!-- Fallback: Static SVG visualization -->
        <div class="graph-fallback">
          <svg viewBox="0 0 1400 320" class="lineage-svg" xmlns="http://www.w3.org/2000/svg">
            <!-- Edges -->
            {#each edges as edge}
              {@const srcNode = nodes.find(n => n.id === edge.source)}
              {@const tgtNode = nodes.find(n => n.id === edge.target)}
              {#if srcNode && tgtNode}
                <line
                  x1={srcNode.position.x + 80} y1={srcNode.position.y + 20}
                  x2={tgtNode.position.x} y2={tgtNode.position.y + 20}
                  stroke={edge.style?.includes('#F37021') ? '#F37021' : edge.style?.includes('#7A7A8A') ? '#7A7A8A' : '#005CA9'}
                  stroke-width="2"
                  stroke-dasharray={edge.style?.includes('dash') ? '5 5' : 'none'}
                  opacity="0.7"
                />
              {/if}
            {/each}

            <!-- Nodes -->
            {#each nodes as node}
              {@const lc = layerColors[node.data.layer] || layerColors.source}
              <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
              <g
                class="lineage-node"
                transform="translate({node.position.x}, {node.position.y})"
                onclick={() => { selectedNode = node; columnLineage = null; }}
              >
                <rect width="160" height="40" rx="6" fill={lc.bg} stroke={lc.border} stroke-width="2" />
                <text x="80" y="24" text-anchor="middle" fill={lc.text} font-size="11" font-weight="600" font-family="var(--font-primary)">
                  {node.data.label.length > 22 ? node.data.label.substring(0, 22) + '...' : node.data.label}
                </text>
              </g>
            {/each}
          </svg>
          <p class="fallback-note">Instale @xyflow/svelte para interatividade completa (pan, zoom, drag)</p>
        </div>
      {/if}
    </div>

    <!-- Side Panel -->
    <div class="side-panel" class:open={!!selectedNode}>
      {#if selectedNode}
        <h3 class="panel-title">Detalhes</h3>
        <div class="panel-section">
          <div class="panel-label">Tabela</div>
          <div class="panel-value">{selectedNode.id}</div>
        </div>
        <div class="panel-section">
          <div class="panel-label">Camada</div>
          <div class="panel-value layer-badge" style="color: {layerColors[selectedNode.data.layer]?.text}">{selectedNode.data.layer}</div>
        </div>
        {#if selectedNode.data.row_count}
          <div class="panel-section">
            <div class="panel-label">Linhas</div>
            <div class="panel-value">{selectedNode.data.row_count?.toLocaleString('pt-BR')}</div>
          </div>
        {/if}
        {#if selectedNode.data.last_updated}
          <div class="panel-section">
            <div class="panel-label">Atualizado</div>
            <div class="panel-value">{selectedNode.data.last_updated?.slice(0, 16).replace('T', ' ')}</div>
          </div>
        {/if}
        {#if selectedNode.data.expectations_pass_rate}
          <div class="panel-section">
            <div class="panel-label">Expectations</div>
            <div class="panel-value">{selectedNode.data.expectations_pass_rate}% pass</div>
          </div>
        {/if}
        {#if selectedNode.data.system}
          <div class="panel-section">
            <div class="panel-label">Sistema</div>
            <div class="panel-value">{selectedNode.data.system}</div>
          </div>
        {/if}

        {#if selectedNode.data.layer !== 'source' && selectedNode.data.layer !== 'output'}
          <div class="panel-section">
            <div class="panel-label">Colunas</div>
            <div class="column-list">
              {#each (selectedNode?.data?.columns || []) as col}
                <button class="col-btn" class:active={columnLineage?.column === col} onclick={() => handleColumnClick(col)}>
                  {col}
                </button>
              {/each}
            </div>
          </div>
        {/if}

        {#if columnLineage && !columnLineage.loading}
          <div class="panel-section">
            <div class="panel-label">Lineage: {columnLineage.column}</div>
            {#if columnLineage.upstream_columns}
              {#each columnLineage.upstream_columns as uc}
                <div class="col-lineage-item">
                  <span class="col-table">{uc.table}</span>
                  <span class="col-col">.{uc.column}</span>
                  <span class="col-transform">{uc.transformation}</span>
                </div>
              {/each}
            {/if}
          </div>
        {/if}
      {:else}
        <div class="panel-empty">Clique em um no para ver detalhes</div>
      {/if}
    </div>
  </div>
</div>

<style>
  .lineage-page { height: calc(100vh - var(--header-height) - var(--space-12)); }
  .lineage-content { display: flex; height: 100%; gap: 0; }
  .graph-area {
    flex: 1;
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow: hidden;
    position: relative;
  }
  .graph-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: var(--space-4);
  }
  .lineage-svg { width: 100%; max-height: 90%; }
  .lineage-node { cursor: pointer; }
  .lineage-node:hover rect { filter: brightness(0.95); }
  .fallback-note { font-size: var(--font-size-xs); color: var(--gray-500); margin-top: var(--space-3); }

  .side-panel {
    width: 0;
    overflow: hidden;
    background: var(--white);
    border-left: 1px solid var(--border-color);
    transition: width 0.2s;
    flex-shrink: 0;
  }
  .side-panel.open {
    width: 300px;
    padding: var(--space-5);
    overflow-y: auto;
  }
  .panel-title { font-size: var(--font-size-md); margin-bottom: var(--space-4); }
  .panel-section { margin-bottom: var(--space-4); }
  .panel-label { font-size: var(--font-size-xs); color: var(--gray-500); text-transform: uppercase; margin-bottom: var(--space-1); }
  .panel-value { font-size: var(--font-size-sm); color: var(--gray-900); font-weight: 600; }
  .layer-badge { text-transform: uppercase; font-size: var(--font-size-xs); }
  .panel-empty { color: var(--gray-500); font-size: var(--font-size-sm); padding: var(--space-10) var(--space-5); text-align: center; }

  .column-list { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-2); }
  .col-btn {
    padding: 2px 8px;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--gray-100);
    font-size: var(--font-size-xs);
    font-family: var(--font-mono);
    color: var(--gray-700);
  }
  .col-btn:hover { background: var(--blue-100); border-color: var(--primary); }
  .col-btn.active { background: var(--primary); color: white; border-color: var(--primary); }

  .col-lineage-item {
    font-size: var(--font-size-xs);
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--gray-100);
  }
  .col-table { font-family: var(--font-mono); color: var(--primary); }
  .col-col { font-family: var(--font-mono); color: var(--gray-700); }
  .col-transform { display: block; font-size: var(--font-size-xs); color: var(--gray-500); margin-top: 2px; }
</style>
