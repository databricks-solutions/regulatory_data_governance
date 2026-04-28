<script>
  let { data = [], labelKey = 'label', valueKey = 'value', maxValue = null, toleranceKey = null, horizontal = true, height = 300, barColor = 'var(--primary)' } = $props();

  const padding = horizontal ? { top: 10, right: 40, bottom: 10, left: 180 } : { top: 10, right: 10, bottom: 40, left: 40 };
  const chartW = 600;
  const innerW = chartW - padding.left - padding.right;
  const barH = 24;
  const barGap = 8;
  const computedH = horizontal ? padding.top + padding.bottom + data.length * (barH + barGap) : height;
  let computedMax = $derived(maxValue ?? Math.max(...data.map(d => d[valueKey]), 1));

  function getBarColor(d) {
    if (!toleranceKey || d[toleranceKey] == null) return barColor;
    const pct = d[valueKey];
    const tol = d[toleranceKey];
    if (pct > tol) return 'var(--error)';
    if (pct > tol * 0.8) return 'var(--warning)';
    return 'var(--success)';
  }
</script>

<svg viewBox="0 0 {chartW} {computedH}" class="bar-chart" xmlns="http://www.w3.org/2000/svg">
  {#if horizontal}
    {#each data as d, i}
      {@const y = padding.top + i * (barH + barGap)}
      {@const w = (d[valueKey] / computedMax) * innerW}

      <!-- Label -->
      <text x={padding.left - 8} y={y + barH / 2} text-anchor="end" dominant-baseline="middle" class="bar-label">
        {d[labelKey]}
      </text>

      <!-- Background bar -->
      <rect x={padding.left} y={y} width={innerW} height={barH} rx="3" fill="var(--gray-100)" />

      <!-- Value bar -->
      <rect x={padding.left} y={y} width={Math.max(w, 2)} height={barH} rx="3" fill={getBarColor(d)} opacity="0.85" />

      <!-- Tolerance marker -->
      {#if toleranceKey && d[toleranceKey] != null}
        {@const tx = padding.left + (d[toleranceKey] / computedMax) * innerW}
        <line x1={tx} y1={y - 2} x2={tx} y2={y + barH + 2} stroke="var(--gray-700)" stroke-width="1.5" stroke-dasharray="3 2" />
      {/if}

      <!-- Value label -->
      <text x={padding.left + Math.max(w, 2) + 6} y={y + barH / 2} dominant-baseline="middle" class="value-label">
        {typeof d[valueKey] === 'number' ? d[valueKey].toFixed(2) + '%' : d[valueKey]}
      </text>
    {/each}
  {/if}
</svg>

<style>
  .bar-chart {
    width: 100%;
    height: auto;
    display: block;
  }
  .bar-label {
    font-size: 11px;
    fill: var(--gray-700);
    font-family: var(--font-primary);
    font-weight: 600;
  }
  .value-label {
    font-size: 10px;
    fill: var(--gray-500);
    font-family: var(--font-mono);
  }
</style>
