<script>
  // Bloco de carregamento com brilho animado: ocupa o lugar do valor enquanto
  // ele não chega, no lugar de um "—" ou de um zero que pareceria dado.
  // `light` para fundos escuros (banner).
  let { width = '100%', height = '1em', radius = 'var(--radius-sm)', light = false } = $props();
</script>

<span class="skeleton" class:light aria-hidden="true"
  style="width:{width};height:{height};border-radius:{radius};"></span>

<style>
  .skeleton {
    display: inline-block;
    vertical-align: middle;
    background: linear-gradient(90deg, var(--gray-100) 0%, var(--gray-200) 50%, var(--gray-100) 100%);
    background-size: 200% 100%;
    animation: skeleton-shimmer 1.4s ease-in-out infinite;
  }
  .skeleton.light {
    background: linear-gradient(90deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.28) 50%, rgba(255,255,255,0.12) 100%);
    background-size: 200% 100%;
  }
  @keyframes skeleton-shimmer {
    from { background-position: 100% 0; }
    to   { background-position: -100% 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .skeleton { animation: none; }
  }
</style>
