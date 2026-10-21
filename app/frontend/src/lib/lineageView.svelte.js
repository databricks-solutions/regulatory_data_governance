// Estado compartilhado entre a página de Linhagem e os nós/arestas customizados
// do Svelte Flow. O destaque de caminho (hover/seleção) vive aqui, e não nos
// arrays de nós/arestas: trocar o array a cada hover faz o Svelte Flow remedir
// os nós e o grafo pisca.
export const lineageView = $state({
  focusId: null,     // nó em destaque
  pathNodes: null,   // Set de ids no caminho do nó em destaque (null = sem destaque)
  pathEdges: null,
  icons: {}          // system_type → slug do SystemTypeIcon
});
