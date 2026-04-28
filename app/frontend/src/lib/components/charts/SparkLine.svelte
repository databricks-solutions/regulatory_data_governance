<script>
  let { values = [], width = 80, height = 24, color = 'var(--primary)' } = $props();

  let yMin = $derived(Math.min(...values));
  let yMax = $derived(Math.max(...values));
  let range = $derived(yMax - yMin || 1);

  let path = $derived(
    values.map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * width;
      const y = height - ((v - yMin) / range) * (height - 4) - 2;
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    }).join(' ')
  );
</script>

<svg {width} {height} class="sparkline" xmlns="http://www.w3.org/2000/svg">
  <path d={path} fill="none" stroke={color} stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
</svg>

<style>
  .sparkline {
    display: inline-block;
    vertical-align: middle;
  }
</style>
