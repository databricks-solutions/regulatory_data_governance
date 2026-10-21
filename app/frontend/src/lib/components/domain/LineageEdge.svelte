<script>
  // Aresta do grafo de Linhagem. Parada por padrão (animar todas redesenha o
  // canvas sem parar); só o caminho em destaque anima e mostra rótulo — o modo
  // de ingestão das BYOL já aparece no subtítulo do nó de origem.
  import { BaseEdge, getBezierPath } from '@xyflow/svelte';
  import { lineageView } from '$lib/lineageView.svelte.js';

  let { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, markerEnd, data } = $props();

  const [path, labelX, labelY] = $derived(
    getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition })
  );
  const onPath = $derived(lineageView.pathEdges?.has(id) ?? false);
  const dimmed = $derived(lineageView.pathEdges !== null && !onPath);
  const showLabel = $derived(!!label && onPath);
  const stroke = $derived(data?.byol ? '#7A7A8A' : '#005CA9');
</script>

<BaseEdge
  {id}
  {path}
  {labelX}
  {labelY}
  label={showLabel ? label : undefined}
  labelStyle="font-size:10px;color:#4A4A5A;background:rgba(255,255,255,0.9);padding:1px 6px;border-radius:4px;"
  {markerEnd}
  class={onPath ? 'lineage-edge-flow' : ''}
  style="stroke:{stroke};stroke-width:{onPath ? 2.4 : 1.4};opacity:{dimmed ? 0.12 : onPath ? 1 : 0.7};{data?.byol ? 'stroke-dasharray:6 4;' : ''}"
/>

<style>
  :global(.lineage-edge-flow) {
    stroke-dasharray: 6 4;
    animation: lineage-edge-dash 0.8s linear infinite;
  }
  @keyframes -global-lineage-edge-dash {
    to { stroke-dashoffset: -10; }
  }
</style>
