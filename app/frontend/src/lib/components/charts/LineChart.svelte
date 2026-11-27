<script>
  import { _ } from 'svelte-i18n';

  let { data = [], width = 600, height = 280, xKey = 'month', yKey = 'score', targetValue = null, color = 'var(--primary)', showArea = true } = $props();

  // Auto-detect compact/sparkline mode when height is small
  let compact = $derived(height <= 100);

  let padding = $derived(compact
    ? { top: 6, right: 6, bottom: 6, left: 6 }
    : { top: 20, right: (targetValue != null ? 64 : 24), bottom: 36, left: 48 }
  );

  let innerW = $derived(width - padding.left - padding.right);
  let innerH = $derived(height - padding.top - padding.bottom);

  // Escala de percentual: teto em 100% (nada de "104,9%") e ticks redondos.
  // 5 ticks em passos de 1/2/5/10/20/25 p.p., do teto até abaixo do menor valor/meta.
  let scale = $derived.by(() => {
    const values = data.map(d => d[yKey]).filter(v => Number.isFinite(v));
    if (!values.length) return { min: 0, max: 100, step: 25 };
    const top = Math.min(100, Math.max(...values, targetValue ?? -Infinity));
    const low = Math.min(...values, targetValue ?? Infinity);
    const span = Math.max(top - low, 1);
    // 3 passos cobrem a amplitude ⇒ o 4º absorve o arredondamento do teto.
    const step = [1, 2, 5, 10, 20, 25].find(s => s * 3 >= span) ?? 25;
    const max = Math.min(100, Math.ceil(top / step) * step);
    return { min: Math.max(0, max - step * 4), max, step };
  });
  let yMin = $derived(scale.min);
  let yMax = $derived(scale.max);

  function scaleX(i) {
    if (data.length === 1) return padding.left + innerW / 2;
    return padding.left + (i / (data.length - 1)) * innerW;
  }
  function scaleY(v) {
    const range = yMax - yMin;
    if (range === 0) return padding.top + innerH / 2;
    return padding.top + innerH - ((v - yMin) / range) * innerH;
  }

  let linePath = $derived(
    data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${scaleX(i)} ${scaleY(d[yKey])}`).join(' ')
  );

  let areaPath = $derived(
    linePath + ` L ${scaleX(data.length - 1)} ${scaleY(yMin)} L ${scaleX(0)} ${scaleY(yMin)} Z`
  );

  let yTicks = $derived.by(() => {
    const ticks = [];
    for (let v = yMin; v <= yMax + 1e-9; v += scale.step) ticks.push(v);
    return ticks;
  });

  // Mesmas 2 casas do card do Índice: 99,92 não pode aparecer como 100.
  function formatValue(v) { return `${Number(v).toFixed(2)}%`; }

  function formatMonth(m) {
    const months = $_('header.months').split(',');
    const parts = m.split('-');
    return months[parseInt(parts[1]) - 1] || m;
  }
</script>

<svg viewBox="0 0 {width} {height}" class="line-chart" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="area-grad-{height}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color={color} stop-opacity="0.12"/>
      <stop offset="100%" stop-color={color} stop-opacity="0.01"/>
    </linearGradient>
    <linearGradient id="line-grad-{height}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color={color}/>
      <stop offset="100%" stop-color={color} stop-opacity="0.6"/>
    </linearGradient>
    {#if !compact}
      <filter id="line-shadow">
        <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="var(--primary)" flood-opacity="0.2"/>
      </filter>
    {/if}
  </defs>

  {#if !compact}
    <!-- Y axis ticks (full mode only) -->
    {#each yTicks as tick}
      <line x1={padding.left} y1={scaleY(tick)} x2={width - padding.right} y2={scaleY(tick)} stroke="var(--gray-200)" stroke-width="0.75" />
      <text x={padding.left - 8} y={scaleY(tick)} text-anchor="end" dominant-baseline="middle" class="axis-label">
        {Number.isInteger(tick) ? tick : tick.toFixed(1)}%
      </text>
    {/each}

    <!-- X axis labels (full mode only) -->
    {#each data as d, i}
      {#if i % Math.ceil(data.length / 6) === 0 || i === data.length - 1}
        <text x={scaleX(i)} y={height - 8} text-anchor="middle" class="axis-label">
          {formatMonth(d[xKey])}
        </text>
      {/if}
    {/each}

    <!-- Target line (full mode only) -->
    {#if targetValue != null}
      <line
        x1={padding.left}
        y1={scaleY(targetValue)}
        x2={width - padding.right}
        y2={scaleY(targetValue)}
        stroke="var(--error)"
        stroke-width="1"
        stroke-dasharray="6 4"
        opacity="0.5"
      />
      <rect x={width - padding.right + 4} y={scaleY(targetValue) - 9} width="38" height="18" rx="4" fill="var(--error-light)" />
      <text x={width - padding.right + 23} y={scaleY(targetValue) + 1} dominant-baseline="middle" text-anchor="middle" class="target-label">
        {$_('charts.target', { values: { value: targetValue } })}
      </text>
    {/if}
  {/if}

  <!-- Area fill -->
  {#if showArea && data.length > 1}
    <path d={areaPath} fill="url(#area-grad-{height})" />
  {/if}

  <!-- Line -->
  {#if data.length > 1}
    <path
      d={linePath}
      fill="none"
      stroke="url(#line-grad-{height})"
      stroke-width={compact ? 2 : 2.5}
      stroke-linecap="round"
      stroke-linejoin="round"
      filter={compact ? undefined : 'url(#line-shadow)'}
    />
  {/if}

  <!-- Data points -->
  {#each data as d, i}
    <circle
      cx={scaleX(i)}
      cy={scaleY(d[yKey])}
      r={compact ? 2.5 : 4}
      fill={color}
      stroke="var(--white)"
      stroke-width={compact ? 1.5 : 2.5}
    />
    {#if !compact}
      <text x={scaleX(i)} y={scaleY(d[yKey]) - 12} text-anchor="middle" class="value-label">
        {formatValue(d[yKey])}
      </text>
      <circle cx={scaleX(i)} cy={scaleY(d[yKey])} r="12" fill="transparent" class="hover-target">
        <title>{formatMonth(d[xKey])}: {formatValue(d[yKey])}</title>
      </circle>
    {/if}
  {/each}
</svg>

<style>
  .line-chart {
    width: 100%;
    height: auto;
    display: block;
    overflow: visible;
  }
  .axis-label {
    font-size: 10px;
    fill: var(--gray-500);
    font-family: var(--font-primary);
    font-weight: 500;
  }
  .value-label {
    font-size: 10px;
    fill: var(--gray-700);
    font-family: var(--font-primary);
    font-weight: 600;
  }
  .target-label {
    font-size: 9px;
    fill: var(--error);
    font-family: var(--font-primary);
    font-weight: 600;
  }
  .hover-target {
    cursor: pointer;
  }
</style>
