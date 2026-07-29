<script>
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';
  import {
    getLineageGraph, getColumnLineage,
    getSystemTypes, getUcTables, listExternalMetadata,
    deleteExternalMetadata, getNodeMetadata
  } from '$lib/api.js';
  import { layerColors, systemColors } from '$lib/theme.js';
  import SystemTypeIcon from '$lib/components/domain/SystemTypeIcon.svelte';
  import ExternalMetadataForm from '$lib/components/domain/ExternalMetadataForm.svelte';
  import ExternalLineageForm from '$lib/components/domain/ExternalLineageForm.svelte';

  let SvelteFlow, MiniMap, Controls, Background, SvelteFlowProvider;
  let flowLoaded = $state(false);

  let selectedNode = $state(null);
  let selectedEdge = $state(null);
  let columnLineage = $state(null);
  let nodeMeta = $state(null);        // full metadata for the selected node (async-loaded)

  // ---- BYOL management state ----
  let systemTypes = $state([]);          // dropdown options (value+label+icon)
  let externalObjects = $state([]);      // registered external metadata objects
  let ucTables = $state([]);             // UC tables for the target picker
  let showMetaForm = $state(false);
  let showRelForm = $state(false);
  let editingObject = $state(null);
  let showManager = $state(false);
  let mgmtError = $state('');

  // Map a system_type enum value → its icon slug (for node/panel rendering).
  const iconByType = $derived(Object.fromEntries(systemTypes.map(t => [t.value, t.icon])));
  function iconForSystemType(st) { return iconByType[st] || 'custom'; }

  // Layer X positions (px) — left to right: origin → external sources → ETL → Databricks medallion → validators → BCB
  const LAYER_ORDER = ['origin', 'source', 'etl', 'bronze', 'silver', 'gold', 'validator', 'output'];
  const LAYER_X     = { origin: 40, source: 290, etl: 540, bronze: 790, silver: 1040, gold: 1290, validator: 1540, output: 1790 };
  const NODE_W = 200;
  const NODE_H = 44;
  const NODE_GAP = 24;

  // Resolve node color. Validators/outputs keep their layer identity; otherwise
  // the layer color drives the node (system identity is carried by the inline
  // SVG icon, so we no longer overload color with brittle name-substring rules).
  function nodeColors(data) {
    const st = (data.system_type || '').toUpperCase();
    const sys = (data.system || '').toLowerCase();
    if (data.layer === 'validator' || sys.includes('validador')) return systemColors.BACEN;
    if (data.layer === 'output' || sys.includes('sta') || sys.includes('cadip')) return systemColors.STA;
    if (st === 'ORACLE') return systemColors.ORACLE;
    return layerColors[data.layer] || layerColors.source;
  }

  // Human label for the ingestion mode badge on a boundary source node.
  function ingestionLabel(mode) {
    if (!mode) return '';
    try { return $_(`lineageMgmt.ingestion_${mode}`); } catch { return mode; }
  }

  function nodeStyle(data) {
    const c = nodeColors(data);
    return `background:${c.bg};border:2px solid ${c.border};color:${c.text};` +
      `border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;` +
      `box-shadow:0 2px 6px rgba(0,0,0,0.10);min-width:${NODE_W}px;text-align:center;`;
  }

  // Normalize any backend layer to one of the 8 rendered columns. UC schemas
  // like `reference`/`landing`/`quality`/`unknown` are valid layers on the API
  // but have no column — without this they'd be silently dropped (and leave
  // dangling edges). Map lookups/reference to the left (source), quality to
  // silver.
  function normalizeLayer(l) {
    if (LAYER_ORDER.includes(l)) return l;
    if (l === 'quality') return 'silver';
    return 'source';
  }

  // Build Svelte-Flow node/edge arrays from the API response format
  function buildFlowGraph(apiNodes, apiEdges) {
    // Group by layer for Y distribution
    const byLayer = {};
    LAYER_ORDER.forEach(l => byLayer[l] = []);
    apiNodes.forEach(n => {
      const l = normalizeLayer(n.layer || 'source');
      byLayer[l].push(n);
    });

    const flowNodes = [];
    LAYER_ORDER.forEach(layer => {
      const group = byLayer[layer] || [];
      const totalH = group.length * (NODE_H + NODE_GAP) - NODE_GAP;
      const startY = Math.max(40, 380 - totalH / 2); // vertically center around y=380
      group.forEach((n, i) => {
        flowNodes.push({
          id: n.id,
          position: { x: LAYER_X[layer] ?? 40, y: startY + i * (NODE_H + NODE_GAP) },
          data: { label: n.label, layer, type: n.type, system: n.system, system_type: n.system_type,
                  ingestion_mode: n.ingestion_mode, properties: n.properties, metadata: n.metadata },
          type: 'default',
          style: nodeStyle({ layer, system: n.system })
        });
      });
    });

    const flowEdges = apiEdges.map((e, i) => {
      const isByol = e.type === 'external_lineage';
      return {
        id: `e${i}`,
        source: e.source,
        target: e.target,
        label: e.label || undefined,
        type: 'default',
        animated: !isByol,
        style: isByol
          ? 'stroke:#7A7A8A;stroke-dasharray:6 4;stroke-width:2;'
          : 'stroke:#005CA9;stroke-width:2;',
        labelStyle: 'font-size:10px;fill:#555;',
        labelBgStyle: 'fill:#ffffffcc;',
        markerEnd: 'url(#arrowhead)',
        data: { column_mappings: e.column_mappings, type: e.type }
      };
    });

    return { flowNodes, flowEdges };
  }

  // The graph is ALWAYS driven by the API (GET /lineage/graph). No embedded
  // fictional topology — in real mode an empty graph must render as an empty
  // state, not as stale mock data. `graphLoaded` distinguishes "still loading"
  // from "loaded and genuinely empty".
  const CATALOG = 'rc18_catalog';

  let nodes = $state([]);
  let edges = $state([]);
  let graphLoaded = $state(false);

  // Legend layer entries — descriptive captions translated; system/layer proper-names stay literal
  const legendLayers = $derived.by(() => [
    ['origin', 'LOS/CRM'], ['source', 'Oracle/DB2'], ['etl', 'Informatica ETL'],
    ['bronze', 'Bronze'], ['silver', 'Silver'], ['gold', 'Gold'],
    ['validator', $_('lineage.legendValidator')], ['output', 'STA/CADIP']
  ]);

  // SVG fallback layer headers — descriptive captions translated; layer proper-names stay literal
  const svgLayerHeaders = $derived.by(() => [
    ['origin', $_('lineage.svgHeaderOrigin'), 40], ['source', 'Oracle/DB2', 290],
    ['etl', 'ETL', 540], ['bronze', 'Bronze', 790], ['silver', 'Silver', 1040],
    ['gold', 'Gold', 1290], ['validator', $_('lineage.svgHeaderValidators'), 1540],
    ['output', 'BCB STA', 1790]
  ]);


  // Select a node and load its full metadata (columns/owner/row count/CADOCs for
  // UC tables; system_type/url/properties for external objects).
  async function selectNode(node) {
    if (!node) return;
    selectedNode = node;
    selectedEdge = null;
    columnLineage = null;
    nodeMeta = { loading: true };
    try {
      nodeMeta = { loading: false, ...(await getNodeMetadata(node.id)) };
    } catch {
      nodeMeta = { loading: false, error: true };
    }
  }

  // @xyflow/svelte v1 (Svelte 5) delivers events as callback props with a
  // `{ node, event }` / `{ edge, event }` payload — NOT a CustomEvent. (The old
  // `on:nodeclick` + `event.detail` sintaxe is silently ignored on v1, which is
  // why clicks did nothing.) Handle both shapes to stay robust.
  function handleNodeClick(payload) {
    selectNode(payload?.node || payload?.detail?.node);
  }

  function handleEdgeClick(payload) {
    const edge = payload?.edge || payload?.detail?.edge;
    if (edge) {
      selectedEdge = edge;
      selectedNode = null;
      columnLineage = null;
      nodeMeta = null;
    }
  }

  async function handleColumnClick(col) {
    const tableName = selectedNode?.id;
    columnLineage = { column: col, loading: true };
    try {
      const data = await getColumnLineage(tableName, col);
      columnLineage = { column: col, ...data, loading: false };
    } catch {
      columnLineage = {
        column: col, loading: false,
        upstream_columns: [{ table: `${CATALOG}.bronze.raw_3040_doc`, column: col, transformation: 'passthrough' }]
      };
    }
  }

  // Re-fetch the graph from the API and re-lay it out. Called on mount and after
  // any create/edit/delete. ALWAYS applies the API result — including an empty
  // graph — so a fresh (unpopulated) workspace shows the empty state instead of
  // stale data. On network error we keep whatever is on screen.
  async function refreshGraph() {
    try {
      const data = await getLineageGraph();
      const { flowNodes, flowEdges } = buildFlowGraph(data?.nodes || [], data?.edges || []);
      nodes = flowNodes;
      edges = flowEdges;
      selectedNode = null;
      selectedEdge = null;
      graphLoaded = true;
    } catch { /* keep current graph on transient failure */ }
  }

  // Refresh the management data (registered objects, dropdown options, UC tables).
  async function refreshManagement() {
    try {
      const [types, objs, tbls] = await Promise.all([
        getSystemTypes(), listExternalMetadata(), getUcTables()
      ]);
      systemTypes = types || [];
      // Attach the icon slug to each object for the relationship picker.
      const iconMap = Object.fromEntries((types || []).map(t => [t.value, t.icon]));
      externalObjects = (objs?.objects || []).map(o => ({ ...o, system_type_icon: iconMap[o.system_type] || 'custom' }));
      ucTables = tbls?.tables || [];
    } catch { /* leave as-is */ }
  }

  async function onSaved() {
    showMetaForm = false;
    showRelForm = false;
    editingObject = null;
    await Promise.all([refreshManagement(), refreshGraph()]);
  }

  function openNewObject() { editingObject = null; showMetaForm = true; }
  function openEditObject(obj) { editingObject = obj; showMetaForm = true; showManager = false; }

  async function removeObject(name) {
    mgmtError = '';
    try {
      await deleteExternalMetadata(name);
      await Promise.all([refreshManagement(), refreshGraph()]);
    } catch (e) {
      mgmtError = e?.message || String(e);
    }
  }

  onMount(async () => {
    // Load Svelte Flow
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

    await Promise.all([refreshGraph(), refreshManagement()]);
  });

  // Side panel: derive layer label
  const LAYER_LABELS = $derived.by(() => ({
    origin: $_('lineage.layerOrigin'), source: $_('lineage.layerSource'), etl: $_('lineage.layerEtl'),
    bronze: 'Bronze (Databricks)', silver: 'Silver (Databricks)', gold: 'Gold (Databricks)',
    validator: $_('lineage.layerValidator'), output: $_('lineage.layerOutput')
  }));
</script>

<div class="lineage-page">
  <!-- Legend bar -->
  <div class="legend-bar">
    <span class="legend-title">{$_('lineage.legendTitle')}</span>
    <div class="legend-items">
      <span class="legend-item"><span class="leg-line byol"></span> {$_('lineage.legendByol')}</span>
      <span class="legend-item"><span class="leg-line uc"></span> {$_('lineage.legendUc')}</span>
      {#each legendLayers as [l, lbl]}
        {@const c = layerColors[l]}
        <span class="legend-item">
          <span class="leg-node" style="background:{c.bg};border-color:{c.border};"></span>
          {lbl}
        </span>
      {/each}
    </div>
  </div>

  <!-- Toolbar: BYOL management actions -->
  <div class="toolbar">
    <div class="toolbar-title">{$_('lineageMgmt.toolbarTitle')}</div>
    <div class="toolbar-actions">
      <button class="tbtn ghost" onclick={() => showManager = !showManager}>
        {$_('lineageMgmt.manageObjects')} ({externalObjects.length})
      </button>
      <button class="tbtn" onclick={() => (showRelForm = true)} disabled={externalObjects.length === 0}>
        + {$_('lineageMgmt.newRelationship')}
      </button>
      <button class="tbtn primary" onclick={openNewObject}>
        + {$_('lineageMgmt.newObject')}
      </button>
    </div>
  </div>

  {#if showManager}
    <div class="manager">
      {#if mgmtError}<div class="mgmt-error">{mgmtError}</div>{/if}
      {#if externalObjects.length === 0}
        <p class="mgmt-empty">{$_('lineageMgmt.noObjects')}</p>
      {:else}
        <table class="mgmt-table">
          <thead>
            <tr>
              <th>{$_('lineageMgmt.colSystem')}</th>
              <th>{$_('lineageMgmt.fieldName')}</th>
              <th>{$_('lineageMgmt.colLayer')}</th>
              <th>{$_('lineageMgmt.colEntity')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each externalObjects as o (o.name)}
              <tr>
                <td>
                  <span class="sys-cell">
                    <SystemTypeIcon icon={o.system_type_icon} label={o.system_type} size={16} />
                    {o.properties?.sistema || o.system_type}
                  </span>
                </td>
                <td class="mono">{o.name}</td>
                <td>{o.properties?.camada || '—'}</td>
                <td>{o.entity_type}</td>
                <td class="row-actions">
                  <button class="link-btn" onclick={() => openEditObject(o)}>{$_('common.edit')}</button>
                  <button class="link-btn danger" onclick={() => removeObject(o.name)}>{$_('common.delete')}</button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {/if}

  <div class="lineage-content">
    <!-- Graph Area -->
    <div class="graph-area">
      {#if graphLoaded && nodes.length === 0}
        <!-- Loaded, but no lineage yet — real workspace with nothing registered. -->
        <div class="graph-empty">
          <div class="graph-empty-icon">⬡</div>
          <h3>{$_('lineageMgmt.graphEmptyTitle')}</h3>
          <p>{$_('lineageMgmt.graphEmptyBody')}</p>
          <button class="tbtn primary" onclick={openNewObject}>+ {$_('lineageMgmt.newObject')}</button>
        </div>
      {:else if flowLoaded && SvelteFlow}
        <svelte:component this={SvelteFlow} {nodes} {edges} fitView
          onnodeclick={handleNodeClick}
          onedgeclick={handleEdgeClick}>
          <svelte:component this={Controls} position="bottom-right" />
          <svelte:component this={MiniMap} position="bottom-left" nodeBorderRadius={8} />
          <svelte:component this={Background} variant="dots" gap={24} size={1} />
        </svelte:component>
      {:else}
        <!-- SVG fallback -->
        <div class="graph-fallback">
          <svg viewBox="0 0 2060 860" class="lineage-svg" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <marker id="arrow-uc"   markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#005CA9" />
              </marker>
              <marker id="arrow-byol" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#7A7A8A" />
              </marker>
            </defs>

            <!-- Edges -->
            {#each edges as edge}
              {@const srcNode = nodes.find(n => n.id === edge.source)}
              {@const tgtNode = nodes.find(n => n.id === edge.target)}
              {#if srcNode && tgtNode}
                {@const x1 = srcNode.position.x + NODE_W}
                {@const y1 = srcNode.position.y + NODE_H / 2}
                {@const x2 = tgtNode.position.x}
                {@const y2 = tgtNode.position.y + NODE_H / 2}
                {@const mx = (x1 + x2) / 2}
                {@const isByol = edge.data?.type === 'external_lineage'}
                <path
                  d="M{x1},{y1} C{mx},{y1} {mx},{y2} {x2},{y2}"
                  fill="none"
                  stroke={isByol ? '#7A7A8A' : '#005CA9'}
                  stroke-width="1.8"
                  stroke-dasharray={isByol ? '6 4' : 'none'}
                  marker-end={isByol ? 'url(#arrow-byol)' : 'url(#arrow-uc)'}
                  opacity="0.75"
                />
                {#if edge.label}
                  <text x={mx} y={(y1 + y2) / 2 - 4} text-anchor="middle"
                    fill="#555" font-size="9" font-family="var(--font-primary)"
                    paint-order="stroke" stroke="white" stroke-width="3">
                    {edge.label}
                  </text>
                {/if}
              {/if}
            {/each}

            <!-- Layer headers -->
            {#each svgLayerHeaders as [l, lbl, lx]}
              {@const c = layerColors[l]}
              <rect x={lx} y="8" width={NODE_W} height="22" rx="4" fill={c.bg} stroke={c.border} />
              <text x={lx + NODE_W/2} y="23" text-anchor="middle" fill={c.text} font-size="10" font-weight="700" font-family="var(--font-primary)">{lbl}</text>
            {/each}

            <!-- Nodes -->
            {#each nodes as node}
              {@const c = nodeColors(node.data)}
              <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
              <g class="lineage-node" transform="translate({node.position.x},{node.position.y})"
                onclick={() => selectNode(node)}>
                <rect width={NODE_W} height={NODE_H} rx="6" fill={c.bg} stroke={c.border} stroke-width="2"
                  class:selected={selectedNode?.id === node.id} />
                <text x={NODE_W/2} y={NODE_H/2 + 4} text-anchor="middle" fill={c.text}
                  font-size="11" font-weight="600" font-family="var(--font-primary)">
                  {node.data.label.length > 24 ? node.data.label.slice(0,24)+'…' : node.data.label}
                </text>
              </g>
            {/each}
          </svg>
          <p class="fallback-note">{$_('lineage.fallbackNote')}</p>
        </div>
      {/if}
    </div>

    <!-- Side Panel -->
    <div class="side-panel" class:open={!!(selectedNode || selectedEdge)}>
      {#if selectedNode}
        {@const lc = nodeColors(selectedNode.data)}
        <div class="panel-header" style="background:{lc.bg};border-bottom:2px solid {lc.border};">
          <div class="panel-layer-badge" style="color:{lc.text};">{LAYER_LABELS[selectedNode.data.layer] || selectedNode.data.layer}</div>
          <div class="panel-title-row">
            {#if selectedNode.data.type !== 'table'}
              <SystemTypeIcon icon={iconForSystemType(selectedNode.data.system_type)} label={selectedNode.data.system} size={20} />
            {/if}
            <h3 class="panel-title" style="color:{lc.text};">{selectedNode.data.label}</h3>
          </div>
          {#if selectedNode.data.system}
            <div class="panel-system">{selectedNode.data.system}</div>
          {/if}
        </div>

        <div class="panel-body">
          <div class="panel-section">
            <div class="panel-label">ID / FQN</div>
            <div class="panel-value mono small">{selectedNode.id}</div>
          </div>

          {#if selectedNode.data.metadata?.connection}
            <div class="panel-section">
              <div class="panel-label">{$_('lineage.connection')}</div>
              <div class="panel-value mono small">{selectedNode.data.metadata.connection}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.update_frequency}
            <div class="panel-section">
              <div class="panel-label">{$_('lineage.frequency')}</div>
              <div class="panel-value">{selectedNode.data.metadata.update_frequency}</div>
            </div>
          {/if}
          {#if selectedNode.data.ingestion_mode}
            <div class="panel-section">
              <div class="panel-label">{$_('lineageMgmt.ingestionMode')}</div>
              <div class="panel-value"><span class="ingestion-badge">{ingestionLabel(selectedNode.data.ingestion_mode)}</span></div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.row_count != null}
            <div class="panel-section">
              <div class="panel-label">{$_('lineage.rows')}</div>
              <div class="panel-value">{selectedNode.data.metadata.row_count?.toLocaleString('pt-BR')}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.last_updated}
            <div class="panel-section">
              <div class="panel-label">{$_('lineage.updated')}</div>
              <div class="panel-value">{selectedNode.data.metadata.last_updated?.slice(0,16).replace('T',' ')}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.expectations_pass_rate}
            <div class="panel-section">
              <div class="panel-label">Expectations</div>
              <div class="panel-value">{$_('lineage.expectationsPass', { values: { rate: selectedNode.data.metadata.expectations_pass_rate } })}</div>
            </div>
          {/if}

          <!-- Full node metadata (async-loaded on click) -->
          {#if nodeMeta?.loading}
            <div class="panel-section"><div class="panel-value" style="color:var(--gray-500);">{$_('common.loading')}…</div></div>
          {:else if nodeMeta && !nodeMeta.error}
            {#if nodeMeta.comment}
              <div class="panel-section">
                <div class="panel-label">{$_('lineageMgmt.metaComment')}</div>
                <div class="panel-value">{nodeMeta.comment}</div>
              </div>
            {/if}
            {#if nodeMeta.cadocs?.length}
              <div class="panel-section">
                <div class="panel-label">CADOCs</div>
                <div class="chip-row">{#each nodeMeta.cadocs as d}<span class="chip">{d}</span>{/each}</div>
              </div>
            {/if}
            {#if nodeMeta.kind === 'external'}
              {#if nodeMeta.system_type}
                <div class="panel-section">
                  <div class="panel-label">{$_('lineageMgmt.fieldSystemType')}</div>
                  <div class="panel-value">{nodeMeta.system_type}{nodeMeta.entity_type ? ` · ${nodeMeta.entity_type}` : ''}</div>
                </div>
              {/if}
              {#if nodeMeta.url}
                <div class="panel-section">
                  <div class="panel-label">URL</div>
                  <div class="panel-value mono small">{nodeMeta.url}</div>
                </div>
              {/if}
              {#if Object.keys(nodeMeta.properties || {}).length}
                <div class="panel-section">
                  <div class="panel-label">{$_('lineageMgmt.fieldProperties')}</div>
                  <table class="meta-table">
                    <tbody>
                      {#each Object.entries(nodeMeta.properties) as [k, v]}
                        <tr><td class="mono meta-k">{k}</td><td>{v}</td></tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            {:else}
              {#if nodeMeta.owner}
                <div class="panel-section">
                  <div class="panel-label">{$_('lineageMgmt.metaOwner')}</div>
                  <div class="panel-value">{nodeMeta.owner}</div>
                </div>
              {/if}
              {#if nodeMeta.row_count != null}
                <div class="panel-section">
                  <div class="panel-label">{$_('lineage.rows')}</div>
                  <div class="panel-value">{nodeMeta.row_count?.toLocaleString('pt-BR')}</div>
                </div>
              {/if}
              {#if nodeMeta.table_type}
                <div class="panel-section">
                  <div class="panel-label">{$_('lineageMgmt.metaTableType')}</div>
                  <div class="panel-value">{nodeMeta.table_type}</div>
                </div>
              {/if}
              {#if nodeMeta.updated_at}
                <div class="panel-section">
                  <div class="panel-label">{$_('lineage.updated')}</div>
                  <div class="panel-value">{nodeMeta.updated_at.slice(0,16).replace('T',' ')}</div>
                </div>
              {/if}
            {/if}
            {#if nodeMeta.columns?.length}
              <div class="panel-section">
                <div class="panel-label">{$_('lineageMgmt.metaColumns')} ({nodeMeta.columns.length})</div>
                <table class="meta-table cols">
                  <tbody>
                    {#each nodeMeta.columns as col}
                      <tr>
                        <td class="mono meta-col-name">
                          {#if nodeMeta.kind === 'uc_table'}
                            <button class="col-link" class:active={columnLineage?.column === col.name}
                              onclick={() => handleColumnClick(col.name)}>{col.name}</button>
                          {:else}{col.name}{/if}
                        </td>
                        <td class="meta-col-type">{col.type || ''}</td>
                      </tr>
                      {#if col.comment}
                        <tr><td colspan="2" class="meta-col-comment">{col.comment}</td></tr>
                      {/if}
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          {/if}

          {#if columnLineage && !columnLineage.loading}
            <div class="panel-section col-lineage-section">
              <div class="panel-label">{$_('lineage.upstreamColumn', { values: { column: columnLineage.column } })}</div>
              {#if columnLineage.upstream_columns}
                {#each columnLineage.upstream_columns as uc}
                  <div class="col-lineage-item">
                    <span class="col-table">{uc.table?.split('.').slice(-1)[0]}</span>
                    <span class="col-col">.{uc.column}</span>
                    <span class="col-transform">{uc.transformation}</span>
                  </div>
                {/each}
              {/if}
              {#if columnLineage.external_sources?.length}
                <div class="panel-label" style="margin-top:8px;">{$_('lineage.externalSources')}</div>
                {#each columnLineage.external_sources as es}
                  <div class="col-lineage-item ext-source">
                    <span class="col-table">{es.system}</span>
                    <span class="col-col"> / {es.table}</span>
                    <span class="col-transform">{es.columns?.join(', ')}</span>
                    <span class="byol-badge">BYOL</span>
                  </div>
                {/each}
              {/if}
            </div>
          {/if}
        </div>

      {:else if selectedEdge}
        {@const isByol = selectedEdge.data?.type === 'external_lineage'}
        <div class="panel-header" style="background:#F8F8FB;border-bottom:2px solid #7A7A8A;">
          <div class="panel-layer-badge" style="color:{isByol ? '#4A4A5A' : '#003D73'};">
            {isByol ? $_('lineage.badgeByol') : $_('lineage.badgeUc')}
          </div>
          <h3 class="panel-title">{selectedEdge.label || $_('lineage.lineageRelation')}</h3>
        </div>
        <div class="panel-body">
          <div class="panel-section">
            <div class="panel-label">{$_('lineage.source')}</div>
            <div class="panel-value mono small">{selectedEdge.source}</div>
          </div>
          <div class="panel-section">
            <div class="panel-label">{$_('lineage.target')}</div>
            <div class="panel-value mono small">{selectedEdge.target}</div>
          </div>
          {#if selectedEdge.data?.column_mappings?.length}
            <div class="panel-section">
              <div class="panel-label">{$_('lineage.columnMapping')}</div>
              <table class="mapping-table">
                <thead><tr><th>{$_('lineage.source')}</th><th>{$_('lineage.target')}</th></tr></thead>
                <tbody>
                  {#each selectedEdge.data.column_mappings as m}
                    <tr><td class="mono">{m.source}</td><td class="mono">{m.target}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <div class="panel-section">
              <div class="panel-label">{$_('lineage.mapping')}</div>
              <div class="panel-value" style="color:var(--gray-500);font-style:italic;">{$_('lineage.autoColumnMapping')}</div>
            </div>
          {/if}
        </div>

      {:else}
        <div class="panel-empty">
          <div class="panel-empty-icon">⬡</div>
          <p>{$_('lineage.emptyPrompt')}</p>
          <p class="panel-empty-hint">{$_('lineage.emptyHint')}</p>
        </div>
      {/if}
    </div>
  </div>
</div>

<!-- BYOL management modals -->
<ExternalMetadataForm
  open={showMetaForm}
  {systemTypes}
  editing={editingObject}
  onclose={() => { showMetaForm = false; editingObject = null; }}
  onsaved={onSaved}
/>
<ExternalLineageForm
  open={showRelForm}
  {externalObjects}
  {ucTables}
  onclose={() => (showRelForm = false)}
  onsaved={onSaved}
/>

<style>
  .lineage-page {
    display: flex;
    flex-direction: column;
    height: calc(100vh - var(--header-height) - var(--space-12));
    gap: var(--space-2);
  }

  /* ---- Legend ---- */
  .legend-bar {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-4);
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    flex-shrink: 0;
    flex-wrap: wrap;
  }
  .legend-title { font-size: var(--font-size-sm); font-weight: 700; color: var(--gray-700); white-space: nowrap; }
  .legend-items { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
  .legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--gray-600); white-space: nowrap; }
  .leg-line { display: inline-block; width: 28px; height: 2px; }
  .leg-line.byol { background: repeating-linear-gradient(90deg,#7A7A8A 0,#7A7A8A 6px,transparent 6px,transparent 10px); }
  .leg-line.uc {
    background: repeating-linear-gradient(90deg,#005CA9 0,#005CA9 6px,transparent 6px,transparent 10px);
    background-size: 10px 2px;
    animation: leg-dash-move 0.6s linear infinite;
  }
  @keyframes leg-dash-move {
    from { background-position: 0 0; }
    to   { background-position: 10px 0; }
  }
  .leg-node { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1.5px solid; }

  /* ---- Toolbar (BYOL management) ---- */
  .toolbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: var(--space-2) var(--space-4); background: var(--white);
    border: 1px solid var(--border-color); border-radius: var(--radius-md);
    flex-shrink: 0;
  }
  .toolbar-title { font-size: var(--font-size-sm); font-weight: 700; color: var(--gray-700); }
  .toolbar-actions { display: flex; gap: var(--space-2); }
  .tbtn {
    padding: 6px 12px; border-radius: var(--radius-md); font-size: var(--font-size-xs); font-weight: 600;
    cursor: pointer; border: 1px solid var(--border-color); background: var(--white); color: var(--gray-700);
  }
  .tbtn:hover:not(:disabled) { background: var(--gray-100); }
  .tbtn.primary { background: var(--primary); color: #fff; border-color: var(--primary); }
  .tbtn.primary:hover { background: var(--blue-700, #004A8A); }
  .tbtn.ghost { background: none; }
  .tbtn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ---- Manager panel ---- */
  .manager {
    background: var(--white); border: 1px solid var(--border-color); border-radius: var(--radius-md);
    padding: var(--space-3); flex-shrink: 0; max-height: 240px; overflow-y: auto;
  }
  .mgmt-error { background: #FDECEA; color: #B71C1C; border-radius: var(--radius-sm); padding: 6px 10px; font-size: var(--font-size-xs); margin-bottom: 8px; }
  .mgmt-empty { font-size: var(--font-size-sm); color: var(--gray-500); text-align: center; padding: var(--space-4); }
  .mgmt-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-xs); }
  .mgmt-table th { text-align: left; font-size: 10px; color: var(--gray-500); text-transform: uppercase; padding: 4px 8px; border-bottom: 1px solid var(--border-color); }
  .mgmt-table td { padding: 6px 8px; border-bottom: 1px solid var(--gray-100); vertical-align: middle; }
  .mgmt-table td.mono { font-family: var(--font-mono); color: var(--gray-800); }
  .sys-cell { display: flex; align-items: center; gap: 8px; }
  .row-actions { text-align: right; white-space: nowrap; }
  .link-btn { background: none; border: none; color: var(--primary); font-size: var(--font-size-xs); font-weight: 600; cursor: pointer; padding: 2px 6px; }
  .link-btn.danger { color: #C62828; }
  .link-btn:hover { text-decoration: underline; }

  .panel-title-row { display: flex; align-items: center; gap: 8px; }
  .ingestion-badge {
    display: inline-block; font-size: 11px; font-weight: 600; padding: 2px 8px;
    background: var(--blue-100, #E5F0F8); color: var(--blue-800, #003D73); border-radius: 10px;
  }

  /* ---- Layout ---- */
  .lineage-content { display: flex; flex: 1; gap: 0; min-height: 0; }

  .graph-area {
    flex: 1;
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow: hidden;
    position: relative;
    min-height: 0;
  }

  .graph-fallback {
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: var(--space-4); overflow: auto;
  }
  .graph-empty {
    width: 100%; height: 100%;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: var(--space-3); text-align: center; padding: var(--space-8); color: var(--gray-500);
  }
  .graph-empty-icon { font-size: 48px; opacity: 0.3; }
  .graph-empty h3 { margin: 0; color: var(--gray-700); font-size: var(--font-size-lg); }
  .graph-empty p { margin: 0; max-width: 420px; font-size: var(--font-size-sm); }
  .lineage-svg { width: 100%; max-height: 95%; }
  .lineage-node { cursor: pointer; }
  .lineage-node:hover rect { filter: brightness(0.93); }
  .lineage-node rect.selected { stroke-width: 3; filter: drop-shadow(0 0 6px rgba(0,0,0,0.25)); }
  .fallback-note { font-size: var(--font-size-xs); color: var(--gray-500); margin-top: var(--space-2); }

  /* ---- Side Panel ---- */
  .side-panel {
    width: 0; overflow: hidden;
    background: var(--white);
    border-left: 1px solid var(--border-color);
    transition: width 0.2s;
    flex-shrink: 0;
    display: flex; flex-direction: column;
  }
  .side-panel.open { width: 320px; overflow-y: auto; }

  .panel-header { padding: var(--space-4); flex-shrink: 0; }
  .panel-layer-badge { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; opacity: 0.8; }
  .panel-title { font-size: var(--font-size-md); font-weight: 700; margin: 0 0 4px; line-height: 1.3; }
  .panel-system { font-size: var(--font-size-xs); color: var(--gray-600); }

  .panel-body { padding: var(--space-4); flex: 1; overflow-y: auto; }
  .panel-section { margin-bottom: var(--space-4); }
  .panel-label { font-size: 10px; font-weight: 700; color: var(--gray-500); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: var(--space-1); }
  .panel-value { font-size: var(--font-size-sm); color: var(--gray-900); font-weight: 600; word-break: break-all; }
  .panel-value.mono { font-family: var(--font-mono); font-weight: 400; }
  .panel-value.small { font-size: 11px; }

  .panel-empty { display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; padding: var(--space-8); text-align: center; color: var(--gray-500); }
  .panel-empty-icon { font-size: 32px; margin-bottom: var(--space-3); opacity: 0.4; }
  .panel-empty p { font-size: var(--font-size-sm); margin: var(--space-1) 0; }
  .panel-empty-hint { font-size: var(--font-size-xs); opacity: 0.7; }

  /* Column lineage */
  .column-list { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-2); }
  .col-btn {
    padding: 2px 8px; border: 1px solid var(--border-color); border-radius: var(--radius-sm);
    background: var(--gray-100); font-size: var(--font-size-xs); font-family: var(--font-mono); color: var(--gray-700); cursor: pointer;
  }
  .col-btn:hover { background: var(--blue-100); border-color: var(--primary); }
  .col-btn.active { background: var(--primary); color: white; border-color: var(--primary); }

  .col-lineage-section { background: var(--gray-50); border-radius: var(--radius-sm); padding: var(--space-3); }
  .col-lineage-item {
    font-size: var(--font-size-xs); padding: var(--space-2) 0;
    border-bottom: 1px solid var(--gray-100); position: relative;
  }
  .col-lineage-item:last-child { border-bottom: none; }
  .col-lineage-item.ext-source { background: rgba(123,31,162,0.04); border-radius: 4px; padding: 4px 6px; }
  .col-table { font-family: var(--font-mono); color: var(--primary); font-weight: 600; }
  .col-col   { font-family: var(--font-mono); color: var(--gray-700); }
  .col-transform { display: block; font-size: 10px; color: var(--gray-500); margin-top: 2px; }
  .byol-badge {
    position: absolute; right: 0; top: 4px;
    font-size: 9px; font-weight: 700; background: #7B1FA2; color: white;
    border-radius: 3px; padding: 1px 5px;
  }

  /* Column mapping table */
  .mapping-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-xs); margin-top: var(--space-2); }
  .mapping-table th { text-align: left; font-size: 10px; color: var(--gray-500); text-transform: uppercase; padding: 4px 8px; background: var(--gray-50); }
  .mapping-table td { padding: 4px 8px; border-top: 1px solid var(--gray-100); }
  .mapping-table .mono { font-family: var(--font-mono); color: var(--gray-800); }

  /* Node metadata panel */
  .chip-row { display: flex; flex-wrap: wrap; gap: 4px; }
  .chip {
    display: inline-block; font-size: 11px; font-weight: 700; font-family: var(--font-mono);
    background: var(--blue-100, #E5F0F8); color: var(--blue-800, #003D73);
    border-radius: 10px; padding: 2px 10px;
  }
  .meta-table { width: 100%; border-collapse: collapse; font-size: var(--font-size-xs); margin-top: 4px; }
  .meta-table td { padding: 3px 6px; border-top: 1px solid var(--gray-100); vertical-align: top; }
  .meta-table .mono, .meta-table .meta-k { font-family: var(--font-mono); color: var(--gray-700); }
  .meta-table .meta-k { white-space: nowrap; color: var(--gray-500); }
  .meta-table.cols .meta-col-name { font-family: var(--font-mono); }
  .meta-table.cols .meta-col-type { text-align: right; color: var(--gray-500); font-family: var(--font-mono); white-space: nowrap; }
  .meta-col-comment { font-size: 10px; color: var(--gray-500); padding-top: 0 !important; border-top: none !important; padding-left: 6px; }
  .col-link {
    background: none; border: none; padding: 0; cursor: pointer;
    font-family: var(--font-mono); font-size: var(--font-size-xs); color: var(--primary); font-weight: 600;
  }
  .col-link:hover { text-decoration: underline; }
  .col-link.active { background: var(--primary); color: #fff; border-radius: 3px; padding: 0 4px; }
</style>
