<script>
  let { title, value, unit = '', trend = null, trendLabel = '', status = 'info', href = '', subtitle = '' } = $props();

  let trendClass = $derived(
    trend > 0 ? 'trend-up' : trend < 0 ? 'trend-down' : 'trend-neutral'
  );
  let trendIcon = $derived(trend > 0 ? '\u25B2' : trend < 0 ? '\u25BC' : '\u25CF');
</script>

<a class="kpi-card status-{status}" href={href || undefined} class:clickable={!!href}>
  <div class="kpi-header">
    <div class="kpi-status-dot"></div>
    <div class="kpi-title">{title}</div>
  </div>
  <div class="kpi-value">
    {value}{#if unit}<span class="kpi-unit">{unit}</span>{/if}
  </div>
  {#if subtitle}
    <div class="kpi-subtitle">{subtitle}</div>
  {/if}
  {#if trend != null}
    <div class="kpi-trend {trendClass}">
      <span class="trend-badge">
        <span class="trend-icon">{trendIcon}</span>
        {trend > 0 ? '+' : ''}{trend}{unit}
      </span>
      {#if trendLabel}<span class="trend-label">{trendLabel}</span>{/if}
    </div>
  {/if}
</a>

<style>
  .kpi-card {
    display: flex;
    flex-direction: column;
    background: var(--white);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: var(--space-3) var(--space-5);
    box-shadow: var(--shadow-sm);
    text-decoration: none;
    color: inherit;
    transition: all var(--transition-base);
    position: relative;
    overflow: hidden;
  }
  .kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    transition: opacity var(--transition-base);
  }
  .status-success::before { background: linear-gradient(90deg, var(--success), var(--success-dark)); }
  .status-warning::before { background: linear-gradient(90deg, var(--warning), var(--orange-900)); }
  .status-error::before   { background: linear-gradient(90deg, var(--error), var(--error-dark)); }
  .status-info::before    { background: linear-gradient(90deg, var(--primary), var(--blue-600)); }

  .kpi-card.clickable:hover {
    box-shadow: var(--shadow-lg);
    transform: translateY(-2px);
    border-color: transparent;
  }
  .status-success.clickable:hover { box-shadow: 0 8px 24px rgba(15, 157, 88, 0.12); }
  .status-warning.clickable:hover { box-shadow: var(--shadow-orange); }
  .status-error.clickable:hover   { box-shadow: 0 8px 24px rgba(219, 68, 55, 0.12); }
  .status-info.clickable:hover    { box-shadow: var(--shadow-blue); }

  .kpi-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  .kpi-status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .status-success .kpi-status-dot { background: var(--success); }
  .status-warning .kpi-status-dot { background: var(--warning); }
  .status-error .kpi-status-dot   { background: var(--error); }
  .status-info .kpi-status-dot    { background: var(--primary); }

  .kpi-title {
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--gray-500);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .kpi-value {
    font-size: var(--font-size-2xl);
    font-weight: 800;
    color: var(--gray-900);
    line-height: 1.1;
    letter-spacing: -0.03em;
  }
  .kpi-unit {
    font-size: var(--font-size-xl);
    font-weight: 600;
    margin-left: 2px;
    opacity: 0.7;
  }
  .kpi-subtitle {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    margin-top: var(--space-1);
    font-weight: 500;
  }
  .kpi-trend {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    margin-top: var(--space-2);
  }
  .trend-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    font-size: var(--font-size-xs);
    font-weight: 600;
  }
  .trend-up .trend-badge { background: var(--success-light); color: var(--success); }
  .trend-down .trend-badge { background: var(--error-light); color: var(--error); }
  .trend-neutral .trend-badge { background: var(--gray-100); color: var(--gray-500); }
  .trend-icon { font-size: 8px; }
  .trend-label { font-size: var(--font-size-xs); color: var(--gray-400); font-weight: 500; }
</style>
