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

  let yMin = $derived(data.length ? Math.min(...data.map(d => d[yKey]), targetValue ?? Infinity) * 0.95 : 0);
  let yMax = $derived(data.length ? Math.max(...data.map(d => d[yKey]), targetValue ?? -Infinity) * 1.05 : 100);

  function scaleX(i) { return padding.left + (i / Math.max(data.length - 1, 1)) * innerW; }
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
    const step = (yMax - yMin) / 4;
    return Array.from({ length: 5 }, (_, i) => yMin + step * i);
  });

  function formatMonth(m) {
    const months = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
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
        {tick.toFixed(1)}%
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
      <circle cx={scaleX(i)} cy={scaleY(d[yKey])} r="12" fill="transparent" class="hover-target" />
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
