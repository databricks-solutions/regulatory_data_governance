<script>
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import Skeleton from '$lib/components/ui/Skeleton.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import DocumentDataBases from '$lib/components/domain/DocumentDataBases.svelte';
  import RadarChart from '$lib/components/charts/RadarChart.svelte';
  import LineChart from '$lib/components/charts/LineChart.svelte';
  import { goto } from '$app/navigation';
  import { appState } from '$lib/stores.svelte.js';
  import { getDashboardKpis, getQualityDimensions, getQualityTrend } from '$lib/api.js';
  import { formatDataBase, formatDate, formatPercent } from '$lib/format.js';
  import { _ } from 'svelte-i18n';

  let kpis = $state({
    compliance_score: 0,
    pending_validations: { scr3040: 0, scr3050: 0 },
    last_submission: { document: '', data_base: '', status: '', submitted_at: '' },
    alerts: [],
    deadline: { date: '2026-12-31', days_remaining: 0, phase: '' }
  });

  let dimensions = $state([]);
  let overallTrend = $state([]);

  // Enquanto carrega, skeletons no lugar dos valores — não os zeros iniciais:
  // 0% de conformidade é um número, e falso. "—" fica só para KPI que falhou
  // depois dos retries do backend (com o aviso de erro acima).
  let loading = $state(true);
  let kpisLoaded = $state(false);
  let loadFailed = $state(false);

  // Só a resposta da busca mais recente é aplicada (troca rápida de data-base).
  let loadSeq = 0;

  async function loadDashboard() {
    const seq = ++loadSeq;
    loading = true;
    kpisLoaded = false;   // não mostrar KPIs da data-base anterior se esta falhar
    loadFailed = false;
    const [k, d, t] = await Promise.allSettled([
      getDashboardKpis(appState.dataBase),
      getQualityDimensions(appState.dataBase),
      // /quality/trend agrega scores de TODAS as runs DQX por mês — fonte
      // direta da Tendência de Conformidade. Antes derivávamos do trend
      // embutido em dimensions[i].trend, que nunca foi populado.
      getQualityTrend(appState.dataBase)
    ]);
    if (seq !== loadSeq) return;
    if (k.status === 'fulfilled' && k.value) {
      kpis = { ...kpis, ...k.value };
      kpisLoaded = true;
    }
    if (d.status === 'fulfilled' && d.value?.dimensions) dimensions = d.value.dimensions;
    if (t.status === 'fulfilled' && Array.isArray(t.value?.trend)) overallTrend = t.value.trend;
    loadFailed = [k, d, t].some((r) => r.status === 'rejected');
    loading = false;
  }

  // Espera o layout resolver o mês de referência (buscar antes usaria o padrão do
  // backend, diferente do seletor) e recarrega quando ele muda.
  $effect(() => {
    if (!appState.dataBaseReady) return;
    appState.dataBase;
    loadDashboard();
  });

  function shown(value) {
    return kpisLoaded ? value : '—';
  }

  function getAlertIcon(severity) {
    if (severity === 'error') return 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z';
    if (severity === 'warning') return 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z';
    return 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0Zm-9-3.75h.008v.008H12V8.25Z';
  }
</script>

<div class="dashboard">
  {#if loadFailed}
    <div class="card load-error" role="alert">
      <span>{$_('common.requestFailed')}</span>
      <button type="button" class="btn-secondary" onclick={loadDashboard}>{$_('common.retry')}</button>
    </div>
  {/if}

  <!-- Welcome Banner -->
  <div class="welcome-banner">
    <div class="welcome-content">
      <div class="welcome-left">
        <div class="welcome-badge">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2l7 4v6c0 5.25-3.5 9.74-7 11-3.5-1.26-7-5.75-7-11V6l7-4z"/></svg>
          {$_('dashboard.welcomeBadge')}
        </div>
        <h2 class="welcome-title">{$_('dashboard.welcomeTitle')}</h2>
        <p class="welcome-subtitle">{$_('dashboard.welcomeSubtitle')}</p>
      </div>
      <div class="welcome-right">
        <div class="welcome-score">
          <div class="score-ring">
            <svg viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="8" />
              {#if loading}
                <!-- Carregando: arco girando no lugar do percentual. -->
                <circle class="ring-spin" cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.45)" stroke-width="8"
                  stroke-dasharray="70 314" stroke-linecap="round" />
              {:else}
                <circle cx="60" cy="60" r="50" fill="none" stroke="var(--accent)" stroke-width="8"
                  stroke-dasharray="{(kpisLoaded ? kpis.compliance_score : 0) * 3.14} 314"
                  stroke-dashoffset="0"
                  stroke-linecap="round"
                  transform="rotate(-90 60 60)" />
              {/if}
            </svg>
            <!-- 2 casas: 99,97 não pode ser exibido como 100 (ver routers/dashboard.py). -->
            <div class="score-value">
              {#if loading}<Skeleton light width="56px" height="22px" />{:else}{shown((kpis.compliance_score ?? 0).toFixed(2))}<span>%</span>{/if}
            </div>
          </div>
          <div class="score-meta">
            <div class="score-label">{$_('dashboard.r18Index')}</div>
          </div>
        </div>
        <div class="welcome-divider"></div>
        <div class="welcome-deadline">
          <div class="deadline-days">
            {#if loading}<Skeleton light width="52px" height="0.8em" />{:else}{shown(kpis.deadline.days_remaining)}{/if}
          </div>
          <div class="deadline-text">{$_('dashboard.daysRemaining')}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-row">
    <KpiCard
      title={$_('dashboard.r18Index')}
      value={shown((kpis.compliance_score ?? 0).toFixed(2))}
      unit="%"
      status="info"
      href="/quality"
      {loading}
    />
    <KpiCard
      title={$_('dashboard.pendingValidations')}
      value={shown(kpis.pending_validations.scr3040 + kpis.pending_validations.scr3050)}
      subtitle={kpisLoaded ? `3040: ${kpis.pending_validations.scr3040} | 3050: ${kpis.pending_validations.scr3050}` : ''}
      status={!kpisLoaded ? 'info' : kpis.pending_validations.scr3040 + kpis.pending_validations.scr3050 > 0 ? 'warning' : 'success'}
      href="/validations"
      {loading}
    />
    <KpiCard
      title={$_('dashboard.r18Deadline')}
      value={shown(kpis.deadline.days_remaining)}
      unit={$_('dashboard.daysUnit')}
      status="info"
      {loading}
    />
  </div>

  <!-- Main Charts -->
  <div class="charts-row">
    <div class="card chart-card">
      <div class="chart-header">
        <div>
          <div class="card-header">{$_('dashboard.qualityDimensionsR18')}</div>
          <div class="chart-subheader">{$_('dashboard.qualityDimensionsSubheader')}</div>
        </div>
        <a href="/quality" class="chart-link">{$_('dashboard.seeDetails')}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      </div>
      {#if loading}
        <div class="chart-skeleton"><Skeleton width="300px" height="300px" radius="50%" /></div>
      {:else}
        <RadarChart {dimensions} target={90} onClick={(id) => goto(`/quality/${id}`)} size={380} />
      {/if}
    </div>
    <div class="card chart-card">
      <div class="chart-header">
        <div>
          <div class="card-header">{$_('dashboard.complianceTrend')}</div>
          <div class="chart-subheader">{$_('dashboard.last6MonthsEvolution')}</div>
        </div>
      </div>
      {#if loading}
        <div class="chart-skeleton"><Skeleton height="260px" radius="var(--radius-md)" /></div>
      {:else}
        <LineChart data={overallTrend} targetValue={90} height={260} />
      {/if}
    </div>
  </div>

  <!-- Status Row -->
  <div class="status-row">
    <!-- Last DQX run -->
    <div class="card status-card">
      <div class="status-card-header">
        <div class="status-icon-wrapper submission">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M12 19V5M5 12l7-7 7 7"/>
          </svg>
        </div>
        <div class="card-header">{$_('dashboard.lastDqxRun')}</div>
      </div>
      <div class="status-body">
        <div class="status-main-value">
          {#if loading}<Skeleton width="140px" height="0.9em" />{:else}{kpis.last_submission.document || '—'}{/if}
        </div>
        <div class="status-detail">
          <span class="detail-label">{$_('dashboard.appBaseDate')}</span>
          {#if loading}<Skeleton width="72px" />{:else}<span class="detail-value">{formatDataBase(kpis.last_submission.data_base)}</span>{/if}
        </div>
        <div class="status-detail">
          <span class="detail-label">{$_('common.status')}</span>
          {#if loading}
            <Skeleton width="72px" height="20px" radius="999px" />
          {:else if kpisLoaded}
            <Badge label={kpis.last_submission.status === 'executado' ? $_('dashboard.statusExecuted') : $_('dashboard.statusPending')} variant={kpis.last_submission.status === 'executado' ? 'success' : 'warning'} />
          {:else}
            <span class="detail-value">—</span>
          {/if}
        </div>
        <div class="status-detail">
          <span class="detail-label">{$_('dashboard.lastRun')}</span>
          {#if loading}
            <Skeleton width="110px" />
          {:else}
            <span class="detail-value">{kpis.last_submission.submitted_at ? formatDate(kpis.last_submission.submitted_at) : '—'}</span>
          {/if}
        </div>
      </div>
    </div>

    <!-- Active Alerts -->
    <div class="card status-card">
      <div class="status-card-header">
        <div class="status-icon-wrapper alerts">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0"/>
          </svg>
        </div>
        <div class="card-header">{$_('dashboard.activeAlerts')}</div>
        {#if loading}
          <Skeleton width="28px" height="20px" radius="999px" />
        {:else}
          <span class="alert-count">{shown(kpis.alerts.length)}</span>
        {/if}
      </div>
      <div class="alerts-list">
        {#if loading}
          {#each [0, 1, 2] as i (i)}
            <div class="alert-item alert-skeleton"><Skeleton width="16px" height="16px" radius="50%" /><Skeleton width="{80 - i * 15}%" /></div>
          {/each}
        {:else if kpisLoaded && kpis.alerts.length === 0}
          <div class="alerts-empty">{$_('dashboard.noOpenIncidents')}</div>
        {/if}
        {#each kpis.alerts as alert}
          <div class="alert-item sev-{alert.severity}">
            <div class="alert-icon-wrap">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d={getAlertIcon(alert.severity)} />
              </svg>
            </div>
            <div class="alert-content">
              <span class="alert-msg">{alert.message}</span>
            </div>
          </div>
        {/each}
      </div>
    </div>
  </div>

  <DocumentDataBases />
</div>

<style>
  .dashboard { display: flex; flex-direction: column; gap: var(--space-4); }
  .chart-skeleton { display: flex; align-items: center; justify-content: center; min-height: 300px; }
  .alert-skeleton { display: flex; align-items: center; gap: var(--space-3); }
  .ring-spin { transform-origin: 60px 60px; animation: ring-spin 1s linear infinite; }
  @keyframes ring-spin { to { transform: rotate(360deg); } }
  .load-error { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); color: var(--error); font-size: var(--font-size-sm); }
  .btn-secondary { background: var(--white); color: var(--gray-700); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: var(--space-2) var(--space-4); font-weight: 500; font-size: var(--font-size-sm); cursor: pointer; }

  /* Welcome Banner */
  .welcome-banner {
    background: linear-gradient(135deg, var(--blue-900) 0%, var(--primary) 50%, var(--blue-600) 100%);
    border-radius: var(--radius-xl);
    padding: var(--space-5) var(--space-6);
    color: white;
    position: relative;
    overflow: hidden;
    box-shadow: var(--shadow-blue);
  }
  .welcome-banner::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -10%;
    width: 400px;
    height: 400px;
    border-radius: 50%;
    background: rgba(243, 112, 33, 0.08);
  }
  .welcome-banner::after {
    content: '';
    position: absolute;
    bottom: -40%;
    left: 10%;
    width: 300px;
    height: 300px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.04);
  }
  .welcome-content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
    z-index: 1;
  }
  .welcome-left { flex: 1; }
  .welcome-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    background: rgba(255,255,255,0.12);
    padding: 3px 10px;
    border-radius: var(--radius-full);
    margin-bottom: var(--space-2);
    opacity: 0.85;
  }
  .welcome-title {
    font-size: var(--font-size-xl);
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 2px;
  }
  .welcome-subtitle {
    font-size: var(--font-size-sm);
    opacity: 0.6;
    font-weight: 400;
  }
  .welcome-right {
    display: flex;
    align-items: center;
    gap: var(--space-5);
  }
  .welcome-divider {
    width: 1px;
    height: 48px;
    background: rgba(255,255,255,0.2);
  }
  .welcome-score {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
  .score-ring {
    position: relative;
    width: 88px;
    height: 88px;
    flex-shrink: 0;
  }
  .score-ring svg { width: 100%; height: 100%; }
  .score-value {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    /* 17px, não 21: com 2 casas decimais o número tem 5 dígitos + '%' e
       encostava no anel de 88px (ver routers/dashboard.py sobre as 2 casas). */
    font-size: 17px;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  .score-value span {
    font-size: 11px;
    font-weight: 600;
    opacity: 0.7;
    margin-left: 1px;
  }
  .score-meta { display: flex; flex-direction: column; }
  .score-label {
    font-size: var(--font-size-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.85;
  }
  .welcome-deadline {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .deadline-days {
    font-size: var(--font-size-xl);
    font-weight: 800;
    line-height: 1;
  }
  .deadline-text {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    opacity: 0.6;
  }

  /* KPI Row — 3 cards iguais (Índice / Críticas / Prazo) */
  .kpi-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); }

  /* Charts Row */
  .charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
  .chart-card { padding: var(--space-3) var(--space-4); height: 500px; overflow: hidden; display: flex; flex-direction: column; }
  .chart-card > :global(:last-child) { flex: 1; display: flex; align-items: center; justify-content: center; }
  .chart-card .chart-header { width: 100%; flex-shrink: 0; }
  .chart-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: var(--space-2);
  }
  .chart-subheader {
    font-size: var(--font-size-xs);
    color: var(--gray-500);
    margin-top: var(--space-1);
    font-weight: 500;
  }
  .chart-link {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--font-size-xs);
    font-weight: 600;
    color: var(--primary);
    text-decoration: none;
    white-space: nowrap;
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-full);
    background: var(--blue-50);
    transition: all var(--transition-fast);
  }
  .chart-link:hover {
    background: var(--blue-100);
    text-decoration: none;
  }

  /* Status Row — 2 cards (Última Execução + Alertas) */
  .status-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-5); }
  .status-card { padding: var(--space-5) var(--space-6); }
  .alerts-empty { color: var(--gray-500); font-size: var(--font-size-sm); font-style: italic; padding: var(--space-3) 0; }
  .status-card-header {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-bottom: var(--space-5);
  }
  .status-card-header .card-header { margin-bottom: 0; flex: 1; }
  .status-icon-wrapper {
    width: 36px;
    height: 36px;
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .status-icon-wrapper.submission { background: var(--blue-50); color: var(--primary); }
  .status-icon-wrapper.recon { background: var(--orange-100); color: var(--accent); }
  .status-icon-wrapper.alerts { background: var(--error-light); color: var(--error); }

  .alert-count {
    background: var(--error);
    color: white;
    font-size: var(--font-size-xs);
    font-weight: 700;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    line-height: 1.4;
  }

  /* Submission card */
  .status-body { display: flex; flex-direction: column; gap: var(--space-3); }
  .status-main-value {
    font-size: var(--font-size-xl);
    font-weight: 700;
    color: var(--gray-900);
    letter-spacing: -0.02em;
  }
  .status-detail {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-2) 0;
    border-bottom: 1px solid var(--gray-100);
  }
  .status-detail:last-child { border-bottom: none; }
  .detail-label {
    font-size: var(--font-size-xs);
    font-weight: 500;
    color: var(--gray-500);
  }
  .detail-value {
    font-size: var(--font-size-sm);
    font-weight: 600;
    color: var(--gray-800);
  }

  /* Reconciliation list */
  .recon-list { display: flex; flex-direction: column; gap: var(--space-1); }
  .recon-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    text-decoration: none;
    padding: var(--space-3);
    border-radius: var(--radius-md);
    transition: all var(--transition-fast);
    font-weight: 500;
  }
  .recon-item:hover {
    background: var(--gray-50);
    color: var(--gray-900);
    text-decoration: none;
  }
  .recon-status {
    width: 24px;
    height: 24px;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    background: var(--gray-100);
    color: var(--gray-500);
  }
  .recon-status.passed { background: var(--success-light); color: var(--success); }
  .recon-status.warn { background: var(--warning-light); color: var(--warning); }
  .recon-label { flex: 1; }
  .recon-arrow {
    color: var(--gray-300);
    flex-shrink: 0;
    transition: color var(--transition-fast);
  }
  .recon-item:hover .recon-arrow { color: var(--gray-500); }

  /* Alerts */
  .alerts-list { display: flex; flex-direction: column; gap: var(--space-2); }
  .alert-item {
    display: flex;
    gap: var(--space-3);
    padding: var(--space-3);
    border-radius: var(--radius-md);
    align-items: flex-start;
    transition: background var(--transition-fast);
  }
  .alert-item:hover { background: var(--gray-50); }
  .alert-icon-wrap {
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .sev-error .alert-icon-wrap { background: var(--error-light); color: var(--error); }
  .sev-warning .alert-icon-wrap { background: var(--warning-light); color: var(--warning); }
  .sev-info .alert-icon-wrap { background: var(--info-light); color: var(--info); }
  .alert-content { flex: 1; min-width: 0; }
  .alert-msg {
    font-size: var(--font-size-sm);
    color: var(--gray-700);
    line-height: 1.5;
    font-weight: 500;
  }

  @media (max-width: 1200px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
    .charts-row { grid-template-columns: 1fr; }
    .status-row { grid-template-columns: 1fr; }
    .welcome-content { flex-direction: column; gap: var(--space-6); text-align: center; }
  }
</style>
