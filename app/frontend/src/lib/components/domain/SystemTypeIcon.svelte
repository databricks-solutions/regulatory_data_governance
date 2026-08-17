<script>
  // Inline SVG glyphs for external-system types — mirrors the icons in the
  // native Catalog Explorer "New external metadata" System type dropdown.
  //
  // These are ORIGINAL, brand-neutral glyphs (a stylized cylinder/shape per
  // family + the vendor's signature accent color), NOT the vendors' trademarked
  // logos — enough to be recognizable in the picker without shipping proprietary
  // marks. Unknown/OTHER falls back to a lettered badge ("custom").
  let { icon = 'custom', size = 18, label = '' } = $props();

  // Signature accent color per system family.
  const ACCENT = {
    oracle: '#C74634', sqlserver: '#0072C6', mysql: '#00758F', postgresql: '#336791',
    teradata: '#F37440', snowflake: '#29B5E8', redshift: '#8C4FFF', bigquery: '#4285F4',
    synapse: '#0089D6', fabric: '#118DFF', mongodb: '#00ED64', sap: '#008FD3',
    salesforce: '#00A1E0', workday: '#0875E1', servicenow: '#62D84E', powerbi: '#F2C811',
    tableau: '#E8762D', looker: '#5F6368', kafka: '#231F20', confluent: '#0074A2',
    databricks: '#FF3621', custom: '#7A7A8A'
  };
  const color = $derived(ACCENT[icon] || ACCENT.custom);

  // Family grouping selects the glyph shape (database cylinder, BI chart,
  // stream, app tile). Keeps the SVG set tiny while staying recognizable.
  const DB = new Set(['oracle','sqlserver','mysql','postgresql','teradata','snowflake','redshift','bigquery','synapse','mongodb','databricks']);
  const BI = new Set(['powerbi','tableau','looker','fabric']);
  const STREAM = new Set(['kafka','confluent']);
  const APP = new Set(['sap','salesforce','workday','servicenow']);
  const family = $derived(
    DB.has(icon) ? 'db' : BI.has(icon) ? 'bi' : STREAM.has(icon) ? 'stream' : APP.has(icon) ? 'app' : 'custom'
  );

  const initial = $derived((label || icon || '?').trim().charAt(0).toUpperCase() || '?');
</script>

<span class="sys-icon" style="width:{size}px;height:{size}px;" title={label || icon}>
  {#if family === 'db'}
    <!-- database cylinder -->
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <ellipse cx="12" cy="5.5" rx="7.5" ry="3" fill={color} />
      <path d="M4.5 5.5 v13 c0 1.66 3.36 3 7.5 3 s7.5-1.34 7.5-3 v-13" fill="none" stroke={color} stroke-width="1.8" />
      <path d="M4.5 12 c0 1.66 3.36 3 7.5 3 s7.5-1.34 7.5-3" fill="none" stroke={color} stroke-width="1.5" opacity="0.7" />
    </svg>
  {:else if family === 'bi'}
    <!-- BI bar chart -->
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <rect x="3" y="13" width="4" height="8" rx="1" fill={color} opacity="0.6" />
      <rect x="10" y="8" width="4" height="13" rx="1" fill={color} opacity="0.8" />
      <rect x="17" y="4" width="4" height="17" rx="1" fill={color} />
    </svg>
  {:else if family === 'stream'}
    <!-- event stream -->
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <circle cx="6" cy="12" r="2.5" fill={color} />
      <circle cx="18" cy="6" r="2.5" fill={color} opacity="0.85" />
      <circle cx="18" cy="18" r="2.5" fill={color} opacity="0.85" />
      <path d="M8 11 L16 6.5 M8 13 L16 17.5" stroke={color} stroke-width="1.6" fill="none" />
    </svg>
  {:else if family === 'app'}
    <!-- application tile -->
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="3.5" fill="none" stroke={color} stroke-width="1.8" />
      <rect x="7" y="7" width="4" height="4" rx="1" fill={color} />
      <rect x="13" y="7" width="4" height="4" rx="1" fill={color} opacity="0.6" />
      <rect x="7" y="13" width="4" height="4" rx="1" fill={color} opacity="0.6" />
      <rect x="13" y="13" width="4" height="4" rx="1" fill={color} />
    </svg>
  {:else}
    <!-- custom / OTHER — lettered badge -->
    <span class="badge" style="background:{color};width:{size}px;height:{size}px;font-size:{Math.round(size * 0.55)}px;">{initial}</span>
  {/if}
</span>

<style>
  .sys-icon { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .badge {
    display: inline-flex; align-items: center; justify-content: center;
    color: #fff; border-radius: 5px; font-weight: 700; line-height: 1;
  }
</style>
