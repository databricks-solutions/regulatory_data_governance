<script>
  import { onMount } from 'svelte';
  import { getLineageGraph, getColumnLineage } from '$lib/api.js';
  import { layerColors, systemColors } from '$lib/theme.js';

  let SvelteFlow, MiniMap, Controls, Background, SvelteFlowProvider;
  let flowLoaded = $state(false);

  let selectedNode = $state(null);
  let selectedEdge = $state(null);
  let columnLineage = $state(null);

  // Layer X positions (px) — left to right: external sources → ETL → Databricks medallion → validators → BCB
  const LAYER_ORDER = ['source', 'etl', 'bronze', 'silver', 'gold', 'validator', 'output'];
  const LAYER_X     = { source: 40, etl: 290, bronze: 540, silver: 790, gold: 1040, validator: 1290, output: 1540 };
  const NODE_W = 200;
  const NODE_H = 44;
  const NODE_GAP = 24;

  // Resolve node color — system-type takes priority over layer
  function nodeColors(data) {
    const sys = (data.system || '').toLowerCase();
    if (sys.includes('oracle'))      return systemColors.ORACLE;
    if (sys.includes('db2') || sys.includes('mainframe')) return systemColors.DB2;
    if (sys.includes('informatica')) return systemColors.INFORMATICA;
    if (sys.includes('validador') || data.layer === 'validator') return systemColors.BACEN;
    if (sys.includes('sta') || sys.includes('cadip'))            return systemColors.STA;
    return layerColors[data.layer] || layerColors.source;
  }

  function nodeStyle(data) {
    const c = nodeColors(data);
    return `background:${c.bg};border:2px solid ${c.border};color:${c.text};` +
      `border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;` +
      `box-shadow:0 2px 6px rgba(0,0,0,0.10);min-width:${NODE_W}px;text-align:center;`;
  }

  // Build Svelte-Flow node/edge arrays from the API response format
  function buildFlowGraph(apiNodes, apiEdges) {
    // Group by layer for Y distribution
    const byLayer = {};
    LAYER_ORDER.forEach(l => byLayer[l] = []);
    apiNodes.forEach(n => {
      const l = n.layer || 'source';
      if (!byLayer[l]) byLayer[l] = [];
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
          data: { label: n.label, layer, type: n.type, system: n.system, system_type: n.system_type, metadata: n.metadata },
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

  // ---- Initial mock data (matches backend _build_mock topology) ----
  const CATALOG = 'classic_stable_hj897w_catalog';

  const initialApiNodes = [
    { id: 'rc18_oracle_tb_operacoes_credito', label: 'Oracle: TB_OPERACOES_CREDITO', type: 'external_source', layer: 'source', system: 'Oracle Core Banking', metadata: { connection: 'jdbc:oracle:thin:@core-banking-prod:1521/CREDITO', update_frequency: 'CDC via ROWSCN 15 min' } },
    { id: 'rc18_oracle_tb_garantias',         label: 'Oracle: TB_GARANTIAS',          type: 'external_source', layer: 'source', system: 'Oracle Core Banking', metadata: { update_frequency: 'CDC via ROWSCN' } },
    { id: 'rc18_oracle_tb_contratantes',      label: 'Oracle: TB_CONTRATANTES',       type: 'external_source', layer: 'source', system: 'Oracle Core Banking', metadata: { update_frequency: 'Batch 02h00' } },
    { id: 'rc18_oracle_tb_cessoes_fidc',      label: 'Oracle: TB_CESSOES_FIDC',       type: 'external_source', layer: 'source', system: 'Oracle Core Banking', metadata: { update_frequency: 'Batch mensal D-1' } },
    { id: 'rc18_db2_clientes_credito',        label: 'DB2: CLIENTES_CREDITO',         type: 'external_source', layer: 'source', system: 'IBM DB2 Mainframe',   metadata: { connection: 'jdbc:db2://mainframe:50000/CLICRED', update_frequency: 'Batch 00h30' } },
    { id: 'rc18_db2_historico_scr',           label: 'DB2: HISTORICO_SCR',            type: 'external_source', layer: 'source', system: 'IBM DB2 Mainframe',   metadata: { update_frequency: 'Pos-envio BCB' } },
    { id: 'rc18_db2_plano_contas_cosif',      label: 'DB2: PLANO_CONTAS_COSIF',       type: 'external_source', layer: 'source', system: 'IBM DB2 Mainframe',   metadata: { update_frequency: 'Por publicacao BACEN' } },
    { id: 'rc18_etl_scr3040_extractor',       label: 'Informatica ETL: SCR3040',      type: 'etl_process',     layer: 'etl',    system: 'Informatica PowerCenter', metadata: { update_frequency: 'Diario 22h00', connection: 'RC18_SCR3040_EXTRACT' } },
    { id: 'rc18_etl_scr3050_aggregator',      label: 'Informatica ETL: SCR3050',      type: 'etl_process',     layer: 'etl',    system: 'Informatica PowerCenter', metadata: { update_frequency: 'Semanal/Mensal 23h00', connection: 'RC18_SCR3050_AGG' } },
    { id: `${CATALOG}.bronze.raw_3040_doc`,   label: 'raw_3040_doc',                  type: 'table',           layer: 'bronze', metadata: { row_count: 1, last_updated: '2026-03-31T23:15:00Z' } },
    { id: `${CATALOG}.bronze.raw_3050_doc`,   label: 'raw_3050_doc',                  type: 'table',           layer: 'bronze', metadata: { row_count: 1, last_updated: '2026-03-31T23:15:00Z' } },
    { id: `${CATALOG}.silver.operacoes_validadas`, label: 'operacoes_validadas',       type: 'table',           layer: 'silver', metadata: { row_count: 1, last_updated: '2026-03-31T01:30:00Z', expectations_pass_rate: 99.9 } },
    { id: `${CATALOG}.silver.scr3040_clientes`,    label: 'scr3040_clientes',          type: 'table',           layer: 'silver', metadata: { row_count: 1, last_updated: '2026-03-31T01:30:00Z' } },
    { id: `${CATALOG}.silver.quality_scorecard`,   label: 'quality_scorecard',         type: 'table',           layer: 'silver', metadata: { row_count: 15, last_updated: '2026-03-31T02:00:00Z' } },
    { id: `${CATALOG}.gold.posicao_mensal_3040`,   label: 'posicao_mensal_3040',       type: 'table',           layer: 'gold',   metadata: { row_count: 0, last_updated: '2026-03-31T04:00:00Z' } },
    { id: `${CATALOG}.gold.posicao_3050`,          label: 'posicao_3050',              type: 'table',           layer: 'gold',   metadata: { row_count: 0, last_updated: '2026-03-31T04:00:00Z' } },
    { id: 'rc18_bacen_validador_scr3040',     label: 'Validador BCB: Doc 3040',        type: 'validator',       layer: 'validator', system: 'BACEN Validador3040', metadata: {} },
    { id: 'rc18_bacen_validador_scr3050',     label: 'Validador BCB: Doc 3050',        type: 'validator',       layer: 'validator', system: 'BACEN ValidadorMDR',  metadata: {} },
    { id: 'rc18_sta_cadip_doc3040',           label: 'STA/CADIP: Doc 3040',            type: 'external_output', layer: 'output',    system: 'BACEN STA/CADIP',     metadata: {} },
    { id: 'rc18_sta_cadip_doc3050',           label: 'STA/CADIP: Doc 3050',            type: 'external_output', layer: 'output',    system: 'BACEN STA/CADIP',     metadata: {} }
  ];

  const initialApiEdges = [
    { source: 'rc18_oracle_tb_operacoes_credito', target: 'rc18_etl_scr3040_extractor',         type: 'external_lineage', label: 'CDC extract', column_mappings: [{source:'CD_CNPJ_IF',target:'cnpj_if'},{source:'CD_IPOC',target:'ipoc'},{source:'VLR_CONTABIL_BRL',target:'vlr_contabil'}] },
    { source: 'rc18_oracle_tb_garantias',         target: 'rc18_etl_scr3040_extractor',         type: 'external_lineage', label: 'JOIN via IPOC' },
    { source: 'rc18_oracle_tb_contratantes',      target: 'rc18_etl_scr3040_extractor',         type: 'external_lineage', label: 'lookup contratante' },
    { source: 'rc18_oracle_tb_cessoes_fidc',      target: 'rc18_etl_scr3040_extractor',         type: 'external_lineage', label: 'LEFT JOIN cessoes' },
    { source: 'rc18_db2_clientes_credito',        target: 'rc18_etl_scr3040_extractor',         type: 'external_lineage', label: 'DRDA lookup' },
    { source: 'rc18_db2_historico_scr',           target: 'rc18_etl_scr3050_aggregator',        type: 'external_lineage', label: 'agregacao mensal' },
    { source: 'rc18_db2_plano_contas_cosif',      target: 'rc18_etl_scr3050_aggregator',        type: 'external_lineage', label: 'lookup COSIF' },
    { source: 'rc18_etl_scr3040_extractor',       target: `${CATALOG}.bronze.raw_3040_doc`,     type: 'external_lineage', label: 'XML → Auto Loader', column_mappings: [{source:'ipoc',target:'header.CD_IPOC'},{source:'vlr_contabil',target:'operacoes[0].VLR_CONTABIL'}] },
    { source: 'rc18_etl_scr3050_aggregator',      target: `${CATALOG}.bronze.raw_3050_doc`,     type: 'external_lineage', label: 'TXB/XML → Auto Loader' },
    { source: `${CATALOG}.bronze.raw_3040_doc`,   target: `${CATALOG}.silver.operacoes_validadas`, type: 'uc_automatic', label: 'DLT silver' },
    { source: `${CATALOG}.bronze.raw_3040_doc`,   target: `${CATALOG}.silver.scr3040_clientes`,    type: 'uc_automatic', label: 'DLT silver' },
    { source: `${CATALOG}.silver.operacoes_validadas`, target: `${CATALOG}.gold.posicao_mensal_3040`, type: 'uc_automatic', label: 'DLT gold' },
    { source: `${CATALOG}.bronze.raw_3050_doc`,        target: `${CATALOG}.gold.posicao_3050`,         type: 'uc_automatic', label: 'DLT gold' },
    { source: `${CATALOG}.silver.quality_scorecard`,   target: `${CATALOG}.gold.posicao_mensal_3040`,  type: 'uc_automatic', label: 'quality gate' },
    { source: `${CATALOG}.gold.posicao_mensal_3040`, target: 'rc18_bacen_validador_scr3040', type: 'external_lineage', label: 'export XML' },
    { source: `${CATALOG}.gold.posicao_3050`,         target: 'rc18_bacen_validador_scr3050', type: 'external_lineage', label: 'export TXB/XML' },
    { source: 'rc18_bacen_validador_scr3040', target: 'rc18_sta_cadip_doc3040', type: 'external_lineage', label: 'SFTP transmissao' },
    { source: 'rc18_bacen_validador_scr3050', target: 'rc18_sta_cadip_doc3050', type: 'external_lineage', label: 'SFTP transmissao' }
  ];

  let { flowNodes: initNodes, flowEdges: initEdges } = buildFlowGraph(initialApiNodes, initialApiEdges);

  let nodes = $state(initNodes);
  let edges = $state(initEdges);

  const mockColumns = ['ipoc', 'modalidade', 'tipo_cliente', 'cnpj_if', 'dt_contr', 'vlr_contabil', 'dt_venc_op'];

  function handleNodeClick(event) {
    const node = event.detail?.node || event.node;
    if (node) {
      selectedNode = node;
      selectedEdge = null;
      columnLineage = null;
    }
  }

  function handleEdgeClick(event) {
    const edge = event.detail?.edge || event.edge;
    if (edge) {
      selectedEdge = edge;
      selectedNode = null;
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
      columnLineage = {
        column: col, loading: false,
        upstream_columns: [{ table: `${CATALOG}.bronze.raw_3040_doc`, column: col, transformation: 'passthrough' }]
      };
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

    // Fetch real lineage from API
    try {
      const data = await getLineageGraph();
      if (data?.nodes?.length) {
        const { flowNodes, flowEdges } = buildFlowGraph(data.nodes, data.edges || []);
        nodes = flowNodes;
        edges = flowEdges;
      }
    } catch { /* keep mock */ }
  });

  // Side panel: derive layer label
  const LAYER_LABELS = {
    source: 'Fonte Externa', etl: 'ETL / Integração', bronze: 'Bronze (Databricks)',
    silver: 'Silver (Databricks)', gold: 'Gold (Databricks)', validator: 'Validador BCB', output: 'Saída BCB'
  };
</script>

<div class="lineage-page">
  <!-- Legend bar -->
  <div class="legend-bar">
    <span class="legend-title">Linhagem RC18 — BYOL + UC Automático</span>
    <div class="legend-items">
      <span class="legend-item"><span class="leg-line byol"></span> BYOL (Externo — dashed)</span>
      <span class="legend-item"><span class="leg-line uc"></span> UC Automático (DLT — solid)</span>
      {#each [['source','Fonte Oracle/DB2'],['etl','Informatica ETL'],['bronze','Bronze'],['silver','Silver'],['gold','Gold'],['validator','Validador BCB'],['output','STA/CADIP']] as [l, lbl]}
        {@const c = layerColors[l]}
        <span class="legend-item">
          <span class="leg-node" style="background:{c.bg};border-color:{c.border};"></span>
          {lbl}
        </span>
      {/each}
    </div>
  </div>

  <div class="lineage-content">
    <!-- Graph Area -->
    <div class="graph-area">
      {#if flowLoaded && SvelteFlow}
        <svelte:component this={SvelteFlow} {nodes} {edges} fitView
          on:nodeclick={handleNodeClick}
          on:edgeclick={handleEdgeClick}>
          <svelte:component this={Controls} position="bottom-right" />
          <svelte:component this={MiniMap} position="bottom-left" nodeBorderRadius={8} />
          <svelte:component this={Background} variant="dots" gap={24} size={1} />
        </svelte:component>
      {:else}
        <!-- SVG fallback -->
        <div class="graph-fallback">
          <svg viewBox="0 0 1780 820" class="lineage-svg" xmlns="http://www.w3.org/2000/svg">
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
            {#each [['source','Fontes Externas',40],['etl','ETL',290],['bronze','Bronze',540],['silver','Silver',790],['gold','Gold',1040],['validator','Validadores',1290],['output','BCB STA',1540]] as [l, lbl, lx]}
              {@const c = layerColors[l]}
              <rect x={lx} y="8" width={NODE_W} height="22" rx="4" fill={c.bg} stroke={c.border} />
              <text x={lx + NODE_W/2} y="23" text-anchor="middle" fill={c.text} font-size="10" font-weight="700" font-family="var(--font-primary)">{lbl}</text>
            {/each}

            <!-- Nodes -->
            {#each nodes as node}
              {@const c = nodeColors(node.data)}
              <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
              <g class="lineage-node" transform="translate({node.position.x},{node.position.y})"
                onclick={() => { selectedNode = node; selectedEdge = null; columnLineage = null; }}>
                <rect width={NODE_W} height={NODE_H} rx="6" fill={c.bg} stroke={c.border} stroke-width="2"
                  class:selected={selectedNode?.id === node.id} />
                <text x={NODE_W/2} y={NODE_H/2 + 4} text-anchor="middle" fill={c.text}
                  font-size="11" font-weight="600" font-family="var(--font-primary)">
                  {node.data.label.length > 24 ? node.data.label.slice(0,24)+'…' : node.data.label}
                </text>
              </g>
            {/each}
          </svg>
          <p class="fallback-note">Instale @xyflow/svelte para interatividade completa (pan, zoom, drag)</p>
        </div>
      {/if}
    </div>

    <!-- Side Panel -->
    <div class="side-panel" class:open={!!(selectedNode || selectedEdge)}>
      {#if selectedNode}
        {@const lc = nodeColors(selectedNode.data)}
        <div class="panel-header" style="background:{lc.bg};border-bottom:2px solid {lc.border};">
          <div class="panel-layer-badge" style="color:{lc.text};">{LAYER_LABELS[selectedNode.data.layer] || selectedNode.data.layer}</div>
          <h3 class="panel-title" style="color:{lc.text};">{selectedNode.data.label}</h3>
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
              <div class="panel-label">Conexão</div>
              <div class="panel-value mono small">{selectedNode.data.metadata.connection}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.update_frequency}
            <div class="panel-section">
              <div class="panel-label">Frequência</div>
              <div class="panel-value">{selectedNode.data.metadata.update_frequency}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.row_count != null}
            <div class="panel-section">
              <div class="panel-label">Linhas</div>
              <div class="panel-value">{selectedNode.data.metadata.row_count?.toLocaleString('pt-BR')}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.last_updated}
            <div class="panel-section">
              <div class="panel-label">Atualizado</div>
              <div class="panel-value">{selectedNode.data.metadata.last_updated?.slice(0,16).replace('T',' ')}</div>
            </div>
          {/if}
          {#if selectedNode.data.metadata?.expectations_pass_rate}
            <div class="panel-section">
              <div class="panel-label">Expectations</div>
              <div class="panel-value">{selectedNode.data.metadata.expectations_pass_rate}% pass</div>
            </div>
          {/if}

          {#if selectedNode.data.type === 'table'}
            <div class="panel-section">
              <div class="panel-label">Linhagem de Colunas</div>
              <div class="column-list">
                {#each mockColumns as col}
                  <button class="col-btn" class:active={columnLineage?.column === col}
                    onclick={() => handleColumnClick(col)}>{col}</button>
                {/each}
              </div>
            </div>
          {/if}

          {#if columnLineage && !columnLineage.loading}
            <div class="panel-section col-lineage-section">
              <div class="panel-label">↑ upstream: {columnLineage.column}</div>
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
                <div class="panel-label" style="margin-top:8px;">↑ fontes externas (BYOL)</div>
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
            {isByol ? 'BYOL — Lineage Externo' : 'UC Automático — DLT'}
          </div>
          <h3 class="panel-title">{selectedEdge.label || 'Relação de Lineage'}</h3>
        </div>
        <div class="panel-body">
          <div class="panel-section">
            <div class="panel-label">Origem</div>
            <div class="panel-value mono small">{selectedEdge.source}</div>
          </div>
          <div class="panel-section">
            <div class="panel-label">Destino</div>
            <div class="panel-value mono small">{selectedEdge.target}</div>
          </div>
          {#if selectedEdge.data?.column_mappings?.length}
            <div class="panel-section">
              <div class="panel-label">Mapeamento de Colunas</div>
              <table class="mapping-table">
                <thead><tr><th>Origem</th><th>Destino</th></tr></thead>
                <tbody>
                  {#each selectedEdge.data.column_mappings as m}
                    <tr><td class="mono">{m.source}</td><td class="mono">{m.target}</td></tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {:else}
            <div class="panel-section">
              <div class="panel-label">Mapeamento</div>
              <div class="panel-value" style="color:var(--gray-500);font-style:italic;">Mapeamento automático por nome de coluna</div>
            </div>
          {/if}
        </div>

      {:else}
        <div class="panel-empty">
          <div class="panel-empty-icon">⬡</div>
          <p>Clique em um nó ou aresta para ver detalhes</p>
          <p class="panel-empty-hint">Nós = tabelas/sistemas · Arestas = relações de lineage</p>
        </div>
      {/if}
    </div>
  </div>
</div>

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
  .leg-line.uc   { background: #005CA9; }
  .leg-node { display: inline-block; width: 12px; height: 12px; border-radius: 3px; border: 1.5px solid; }

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
</style>
