<script>
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import Badge from '$lib/components/ui/Badge.svelte';
  import RadarChart from '$lib/components/charts/RadarChart.svelte';
  import LineChart from '$lib/components/charts/LineChart.svelte';
  import { goto } from '$app/navigation';
  import { appState } from '$lib/stores.svelte.js';
  import { getDashboardKpis, getQualityDimensions } from '$lib/api.js';
  import { formatDate, formatPercent } from '$lib/format.js';
  import { onMount } from 'svelte';

  let kpis = $state({
    compliance_score: 87.5,
    pending_validations: { scr3040: 3, scr3050: 1 },
    last_submission: { document: 'SCR 3050', data_base: '2026-03-28', status: 'aceito', submitted_at: '2026-03-30T14:22:00Z' },
    alerts: [
      { severity: 'info', message: 'Nova versão de leiaute V11 em vigor desde 07/11/2025', created_at: '2026-03-28T08:00:00Z' },
      { severity: 'error', message: 'IPOC componentes divergentes em 127 operações', created_at: '2026-03-27T16:00:00Z' }
    ],
    deadline: { date: '2026-12-31', days_remaining: 274, phase: 'Fase 1 - Fundação' }
  });

  let dimensions = $state([
    { id: 1, name: 'Acessibilidade', score: 95.0, target: 90, status: 'conforme', trend: [{month:'2025-10',score:80},{month:'2025-11',score:85},{month:'2025-12',score:88},{month:'2026-01',score:90},{month:'2026-02',score:92},{month:'2026-03',score:95}] },
    { id: 2, name: 'Acurácia', score: 92.5, target: 95, status: 'atencao', trend: [{month:'2025-10',score:85},{month:'2025-11',score:87},{month:'2025-12',score:89},{month:'2026-01',score:90},{month:'2026-02',score:91},{month:'2026-03',score:92.5}] },
    { id: 3, name: 'Adaptabilidade', score: 88.0, target: 85, status: 'conforme', trend: [{month:'2025-10',score:75},{month:'2025-11',score:78},{month:'2025-12',score:80},{month:'2026-01',score:83},{month:'2026-02',score:85},{month:'2026-03',score:88}] },
    { id: 4, name: 'Atualidade', score: 91.0, target: 90, status: 'conforme', trend: [{month:'2025-10',score:82},{month:'2025-11',score:84},{month:'2025-12',score:86},{month:'2026-01',score:88},{month:'2026-02',score:90},{month:'2026-03',score:91}] },
    { id: 5, name: 'Completude', score: 94.0, target: 90, status: 'conforme', trend: [{month:'2025-10',score:88},{month:'2025-11',score:89},{month:'2025-12',score:90},{month:'2026-01',score:91},{month:'2026-02',score:93},{month:'2026-03',score:94}] },
    { id: 6, name: 'Consistência', score: 89.5, target: 90, status: 'atencao', trend: [{month:'2025-10',score:78},{month:'2025-11',score:80},{month:'2025-12',score:83},{month:'2026-01',score:85},{month:'2026-02',score:87},{month:'2026-03',score:89.5}] },
    { id: 7, name: 'Confidencialidade', score: 97.0, target: 95, status: 'conforme', trend: [{month:'2025-10',score:93},{month:'2025-11',score:94},{month:'2025-12',score:95},{month:'2026-01',score:96},{month:'2026-02',score:96.5},{month:'2026-03',score:97}] },
    { id: 8, name: 'Disponibilidade', score: 96.0, target: 95, status: 'conforme', trend: [{month:'2025-10',score:90},{month:'2025-11',score:91},{month:'2025-12',score:93},{month:'2026-01',score:94},{month:'2026-02',score:95},{month:'2026-03',score:96}] },
    { id: 9, name: 'Granularidade', score: 85.0, target: 85, status: 'conforme', trend: [{month:'2025-10',score:70},{month:'2025-11',score:73},{month:'2025-12',score:76},{month:'2026-01',score:79},{month:'2026-02',score:82},{month:'2026-03',score:85}] },
    { id: 10, name: 'Rastreabilidade', score: 78.0, target: 85, status: 'nao_conforme', trend: [{month:'2025-10',score:60},{month:'2025-11',score:63},{month:'2025-12',score:67},{month:'2026-01',score:70},{month:'2026-02',score:74},{month:'2026-03',score:78}] },
    { id: 11, name: 'Relevância', score: 90.0, target: 85, status: 'conforme', trend: [{month:'2025-10',score:82},{month:'2025-11',score:84},{month:'2025-12',score:86},{month:'2026-01',score:87},{month:'2026-02',score:88},{month:'2026-03',score:90}] },
    { id: 12, name: 'Conformidade', score: 86.0, target: 90, status: 'atencao', trend: [{month:'2025-10',score:72},{month:'2025-11',score:75},{month:'2025-12',score:78},{month:'2026-01',score:81},{month:'2026-02',score:84},{month:'2026-03',score:86}] }
  ]);

  let overallTrend = $derived(
    dimensions[0]?.trend?.map(t => ({
      month: t.month,
      score: dimensions.reduce((sum, d) => sum + (d.trend.find(tr => tr.month === t.month)?.score || 0), 0) / dimensions.length
    })) || []
  );

  onMount(async () => {
    try {
      const data = await getDashboardKpis(appState.dataBase);
      if (data) kpis = { ...kpis, ...data };
    } catch { /* use mock data */ }
    try {
      const data = await getQualityDimensions(appState.dataBase);
      if (data?.dimensions) dimensions = data.dimensions;
    } catch { /* use mock data */ }
  });

  function getAlertIcon(severity) {
    if (severity === 'error') return 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z';
    if (severity === 'warning') return 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z';
    return 'M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0Zm-9-3.75h.008v.008H12V8.25Z';
  }
</script>

<div class="dashboard">
  <!-- Welcome Banner -->
  <div class="welcome-banner">
    <div class="welcome-content">
      <div class="welcome-left">
        <div class="welcome-badge">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 2l7 4v6c0 5.25-3.5 9.74-7 11-3.5-1.26-7-5.75-7-11V6l7-4z"/></svg>
          Resolução Conjunta N.18
        </div>
        <h2 class="welcome-title">Conformidade SCR</h2>
        <p class="welcome-subtitle">Qualidade de dados — Banco Central do Brasil</p>
      </div>
      <div class="welcome-right">
        <div class="welcome-score">
          <div class="score-ring">
            <svg viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="8" />
              <circle cx="60" cy="60" r="50" fill="none" stroke="var(--accent)" stroke-width="8"
                stroke-dasharray="{kpis.compliance_score * 3.14} 314"
                stroke-dashoffset="0"
                stroke-linecap="round"
                transform="rotate(-90 60 60)" />
            </svg>
            <div class="score-value">{kpis.compliance_score}<span>%</span></div>
          </div>
          <div class="score-meta">
            <div class="score-label">Índice R.18</div>
          </div>
        </div>
        <div class="welcome-divider"></div>
        <div class="welcome-deadline">
          <div class="deadline-days">{kpis.deadline.days_remaining}</div>
          <div class="deadline-text">dias restantes</div>
        </div>
      </div>
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-row">
    <KpiCard
      title="Índice R.18"
      value={kpis.compliance_score}
      unit="%"
      trend={2.5}
      trendLabel="vs mês anterior"
      status="info"
      href="/quality"
    />
    <KpiCard
      title="Críticas Pendentes"
      value={kpis.pending_validations.scr3040 + kpis.pending_validations.scr3050}
      subtitle="3040: {kpis.pending_validations.scr3040} | 3050: {kpis.pending_validations.scr3050}"
      status={kpis.pending_validations.scr3040 + kpis.pending_validations.scr3050 > 0 ? 'warning' : 'success'}
      href="/validations"
    />
    <KpiCard
      title="Prazo R.18"
      value={kpis.deadline.days_remaining}
      unit=" dias"
      subtitle={kpis.deadline.phase}
      status="info"
    />
  </div>

  <!-- Main Charts -->
  <div class="charts-row">
    <div class="card chart-card">
      <div class="chart-header">
        <div>
          <div class="card-header">Dimensões de Qualidade R.18</div>
          <div class="chart-subheader">12 dimensões obrigatórias com meta de 90%</div>
        </div>
        <a href="/quality" class="chart-link">Ver detalhes
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      </div>
      <RadarChart {dimensions} target={90} onClick={(id) => goto(`/quality/${id}`)} size={380} />
    </div>
    <div class="card chart-card">
      <div class="chart-header">
        <div>
          <div class="card-header">Tendência de Conformidade</div>
          <div class="chart-subheader">Evolução dos últimos 6 meses</div>
        </div>
      </div>
      <LineChart data={overallTrend} targetValue={90} height={260} />
    </div>
  </div>

  <!-- Status Row -->
  <div class="status-row">
    <!-- Last Submission -->
    <div class="card status-card">
      <div class="status-card-header">
        <div class="status-icon-wrapper submission">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M12 19V5M5 12l7-7 7 7"/>
          </svg>
        </div>
        <div class="card-header">Última Remessa</div>
      </div>
      <div class="status-body">
        <div class="status-main-value">{kpis.last_submission.document}</div>
        <div class="status-detail">
          <span class="detail-label">Data-base</span>
          <span class="detail-value">{kpis.last_submission.data_base}</span>
        </div>
        <div class="status-detail">
          <span class="detail-label">Status</span>
          <Badge label={kpis.last_submission.status === 'aceito' ? 'Aceito' : 'Pendente'} variant={kpis.last_submission.status === 'aceito' ? 'success' : 'warning'} />
        </div>
        <div class="status-detail">
          <span class="detail-label">Enviado</span>
          <span class="detail-value">{formatDate(kpis.last_submission.submitted_at)}</span>
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
        <div class="card-header">Alertas Ativos</div>
        <span class="alert-count">{kpis.alerts.length}</span>
      </div>
      <div class="alerts-list">
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
</div>

<style>
  .dashboard { display: flex; flex-direction: column; gap: var(--space-4); }

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
    font-size: 21px;
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  .score-value span {
    font-size: 14px;
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

  /* KPI Row */
  .kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); }

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

  /* Status Row */
  .status-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--space-5); }
  .status-card { padding: var(--space-5) var(--space-6); }
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
