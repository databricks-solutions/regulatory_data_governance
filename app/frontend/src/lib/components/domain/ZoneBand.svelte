<script>
  // Background "zone band" node for the lineage graph — a non-interactive
  // vertical band that visually groups a set of layers (e.g. external-input,
  // Databricks, external-output). Rendered as a Svelte Flow custom node so it
  // pans/zooms together with the graph. Sits behind the real nodes (zIndex -1).
  let { data } = $props();
</script>

<div class="zone" style="width:{data.width}px;height:{data.height}px;
    background:{data.bg};border:1.5px dashed {data.border};">
  <div class="zone-label">
    <span class="zone-logo-chip">
      {#if data.icon === 'databricks'}
        <!-- Official Databricks symbol (stacked slabs), brand red. Path from Simple Icons. -->
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="#FF3621">
          <path d="M.95 14.184L12 20.403l9.919-5.55v2.21L12 22.662l-10.484-5.96-.565.308v.77L12 24l11.05-6.218v-4.317l-.515-.309L12 19.118l-9.867-5.653v-2.21L12 16.805l11.05-6.218V6.32l-.515-.308L12 11.974 2.647 6.681 12 1.388l7.76 4.368.668-.411v-.566L12 0 .95 6.27v.72L12 13.207l9.919-5.55v2.26L12 15.52 1.516 9.56l-.565.308Z"/>
        </svg>
      {:else if data.icon === 'external-source'}
        <!-- External source systems: a database-cylinder stack. -->
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"
          fill="none" stroke={data.text} stroke-width="1.8" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="7" ry="2.6" />
          <path d="M5 5 v6 c0 1.44 3.13 2.6 7 2.6 s7-1.16 7-2.6 V5" />
          <path d="M5 11 v6 c0 1.44 3.13 2.6 7 2.6 s7-1.16 7-2.6 v-6" />
        </svg>
      {:else if data.icon === 'external-output'}
        <!-- External output/delivery: upload arrow into a tray (transmission to BCB). -->
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"
          fill="none" stroke={data.text} stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 15 V4" />
          <path d="M7.5 8.5 L12 4 l4.5 4.5" />
          <path d="M4 15 v3.5 c0 .8.7 1.5 1.5 1.5 h13 c.8 0 1.5-.7 1.5-1.5 V15" />
        </svg>
      {/if}
    </span>
    <span class="zone-text" style="color:{data.text};">{data.label}</span>
  </div>
</div>

<style>
  .zone {
    border-radius: 12px;
    box-sizing: border-box;
    pointer-events: none;         /* never intercept clicks meant for real nodes */
  }
  .zone-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 8px 12px;
    max-width: 100%;
    box-sizing: border-box;
  }
  .zone-text {
    /* Wrap instead of overflowing when the band is narrow; dim only the caption. */
    overflow-wrap: anywhere;
    line-height: 1.2;
    opacity: 0.9;
  }
  /* Full-opacity logo on a white chip so it isn't washed out by the tinted band. */
  .zone-logo-chip {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #fff;
    border-radius: 6px;
    padding: 2px;
    flex-shrink: 0;
    box-shadow: 0 1px 2px rgba(0,0,0,0.08);
  }
</style>
