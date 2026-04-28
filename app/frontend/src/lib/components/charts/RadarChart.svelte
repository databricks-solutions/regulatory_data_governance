<script>
  let { dimensions = [], target = 90, size = 440, onClick = null } = $props();

  const padding = 140;
  const vbSize = size + padding * 2;
  const cx = vbSize / 2;
  const cy = vbSize / 2;
  const radius = size * 0.42;
  const levels = 5;

  function angleForIndex(i) {
    return (Math.PI * 2 * i) / dimensions.length - Math.PI / 2;
  }

  function pointAt(i, value) {
    const angle = angleForIndex(i);
    const r = (value / 100) * radius;
    return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  }

  let scorePoints = $derived(
    dimensions.map((d, i) => pointAt(i, d.score)).map(p => `${p.x},${p.y}`).join(' ')
  );

  let targetPoints = $derived(
    dimensions.map((_, i) => pointAt(i, target)).map(p => `${p.x},${p.y}`).join(' ')
  );

  let labelPositions = $derived(
    dimensions.map((d, i) => {
      const angle = angleForIndex(i);
      const r = radius + 46;
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      return {
        x: cx + r * cosA,
        y: cy + r * sinA,
        anchor: Math.abs(cosA) < 0.12 ? 'middle' : cosA > 0 ? 'start' : 'end',
        vertical: sinA < -0.6 ? 'above' : sinA > 0.6 ? 'below' : 'middle',
        name: d.name,
        score: d.score,
        id: d.id,
        status: d.status
      };
    })
  );
</script>

<svg viewBox="0 0 {vbSize} {vbSize}" class="radar-chart" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="radar-fill-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="var(--primary)" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="var(--blue-400)" stop-opacity="0.05"/>
    </linearGradient>
    <linearGradient id="radar-stroke-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="var(--primary)"/>
      <stop offset="100%" stop-color="var(--blue-400)"/>
    </linearGradient>
    <filter id="point-glow">
      <feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <!-- Grid levels -->
  {#each Array(levels) as _, lvl}
    {@const r = (radius * (lvl + 1)) / levels}
    <polygon
      points={dimensions.map((_, i) => {
        const angle = angleForIndex(i);
        return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
      }).join(' ')}
      fill="none"
      stroke="var(--gray-200)"
      stroke-width="0.75"
    />
  {/each}

  <!-- Axis lines -->
  {#each dimensions as _, i}
    {@const end = pointAt(i, 100)}
    <line x1={cx} y1={cy} x2={end.x} y2={end.y} stroke="var(--gray-200)" stroke-width="0.5" />
  {/each}

  <!-- Target polygon -->
  <polygon
    points={targetPoints}
    fill="none"
    stroke="var(--gray-400)"
    stroke-width="1.5"
    stroke-dasharray="5 4"
    opacity="0.5"
  />

  <!-- Score polygon -->
  <polygon
    points={scorePoints}
    fill="url(#radar-fill-grad)"
    stroke="url(#radar-stroke-grad)"
    stroke-width="2.5"
    stroke-linejoin="round"
  />

  <!-- Score points -->
  {#each dimensions as d, i}
    {@const p = pointAt(i, d.score)}
    <circle cx={p.x} cy={p.y} r="5" fill="var(--accent)" stroke="var(--white)" stroke-width="2" filter="url(#point-glow)" />
  {/each}

  <!-- Labels -->
  {#each labelPositions as lbl}
    {@const nameDy = lbl.vertical === 'above' ? -12 : lbl.vertical === 'below' ? 4 : -8}
    {@const scoreDy = lbl.vertical === 'above' ? 8 : lbl.vertical === 'below' ? 24 : 12}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <text
      x={lbl.x}
      y={lbl.y + nameDy}
      text-anchor={lbl.anchor}
      dominant-baseline="middle"
      class="radar-label"
      class:clickable={!!onClick}
      class:warn={lbl.status === 'atencao'}
      class:fail={lbl.status === 'nao_conforme'}
      onclick={() => onClick?.(lbl.id)}
    >
      {lbl.name}
    </text>
    <text
      x={lbl.x}
      y={lbl.y + scoreDy}
      text-anchor={lbl.anchor}
      dominant-baseline="middle"
      class="radar-score"
      class:warn={lbl.status === 'atencao'}
      class:fail={lbl.status === 'nao_conforme'}
    >
      {lbl.score}%
    </text>
  {/each}
</svg>

<style>
  .radar-chart {
    width: 100%;
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 auto;
  }
  .radar-label {
    fill: var(--gray-700);
    font-size: 20px;
    font-family: var(--font-primary);
    font-weight: 600;
  }
  .radar-label.warn { fill: var(--orange-900); }
  .radar-label.fail { fill: var(--error); }
  .radar-label.clickable { cursor: pointer; }
  .radar-label.clickable:hover { fill: var(--primary); }
  .radar-score {
    fill: var(--gray-500);
    font-size: 17px;
    font-family: var(--font-primary);
    font-weight: 600;
  }
  .radar-score.warn { fill: var(--warning); }
  .radar-score.fail { fill: var(--error); }
</style>
