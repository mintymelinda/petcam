// Timelapse configuration and status
async function refreshTimelapse() {
  try {
    const d = await request("/api/timelapse");
    const c = d.config,
      s = d.status;
    $("timelapse-enabled").checked = c.enabled;
    $("timelapse-interval").value = c.interval_seconds;
    $("timelapse-start").value = c.schedule_start;
    $("timelapse-end").value = c.schedule_end;
    $("timelapse-retention").value = c.retention_days;
    $("timelapse-storage").value = c.max_storage_mb;
    $("timelapse-free").value = c.min_free_mb;
    $("timelapse-width").value = c.max_width;
    $("timelapse-quality").value = c.jpeg_quality;
    $("timelapse-path").value = c.storage_path;
    $("timelapse-status").textContent =
      "Status: " +
      s.state +
      " · " +
      s.frames +
      " frames · " +
      Math.round(s.storage_bytes / 1048576) +
      " MiB" +
      (s.last_capture_at ? " · Last capture: " + s.last_capture_at : "") +
      (s.last_error ? " · " + s.last_error : "");
  } catch (e) {
    $("timelapse-status").textContent =
      "Timelapse status unavailable: " + e.message;
  }
}
// Motion detection configuration and events
async function refreshMotion() {
  try {
    const d = await request("/api/motion"),
      c = d.config,
      s = d.status;
    $("motion-enabled").checked = c.enabled;
    $("motion-sensitivity").value = c.sensitivity;
    $("motion-min-change").value = c.minimum_changed_percent;
    $("motion-sample").value = c.sample_interval_seconds;
    $("motion-confirm").value = c.confirm_samples;
    $("motion-cooldown").value = c.min_event_interval_seconds;
    $("motion-quiet-enabled").checked = c.quiet_hours_enabled;
    $("motion-quiet-start").value = c.quiet_hours_start;
    $("motion-quiet-end").value = c.quiet_hours_end;
    $("motion-retention").value = c.retention_days;
    $("motion-storage").value = c.max_storage_mb;
    $("motion-free").value = c.min_free_mb;
    $("motion-status").textContent =
      "Status: " +
      s.state +
      " · " +
      s.event_count +
      " events · " +
      s.snapshots +
      " snapshots · " +
      Math.round(s.storage_bytes / 1048576) +
      " MiB" +
      (s.last_event_at ? " · Last event: " + s.last_event_at : "") +
      (s.cpu_percent !== undefined
        ? " · Worker CPU: " + s.cpu_percent + "%"
        : "") +
      (s.peak_rss_kib !== undefined
        ? " · Peak RAM: " + Math.round(s.peak_rss_kib / 1024) + " MiB"
        : "") +
      (s.last_error ? " · " + s.last_error : "");
    const root = $("motion-events");
    root.replaceChildren();
    if (!s.events.length) {
      root.textContent = "No motion events recorded.";
      return;
    }
    for (const event of s.events) {
      const row = document.createElement("div"),
        img = document.createElement("img"),
        details = document.createElement("div"),
        time = document.createElement("div"),
        change = document.createElement("small");
      row.className = "motion-event";
      img.src = "/api/motion/events/" + encodeURIComponent(event.file);
      img.alt = "Motion snapshot " + event.timestamp;
      time.textContent = event.timestamp;
      change.textContent = "Changed pixels: " + event.changed_percent + "%";
      details.append(time, change);
      row.append(img, details);
      root.append(row);
    }
  } catch (e) {
    $("motion-status").textContent = "Motion status unavailable: " + e.message;
  }
}
// Ambient light sensor configuration and status
async function refreshLightSensor() {
  try {
    const d = await request("/api/light-sensor"),
      c = d.config,
      s = d.status;
    $("light-sensor-enabled").checked = c.ENABLED;
    $("light-bright-threshold").value = c.BRIGHT_THRESHOLD_LUX;
    $("light-dark-threshold").value = c.DARK_THRESHOLD_LUX;
    const reading =
      s.illuminance_lux === undefined
        ? "No lux reading"
        : s.illuminance_lux + " lx";
    $("light-sensor-status").textContent =
      "Status: " + s.state + " · " + reading + (s.error ? " · " + s.error : "");
  } catch (e) {
    $("light-sensor-status").textContent =
      "Light sensor status unavailable: " + e.message;
  }
}

// Diagnostics and support bundle
async function refreshDiagnostics() {
  try {
    const d = await request("/api/diagnostics");
    const layers = d.layers || {};
    const failed = Object.entries(layers).filter(
      ([k, v]) =>
        v &&
        (v.healthy === false ||
          v.reachable === false ||
          v.resolved === false ||
          v.available === false),
    );
    $("diagnostic-summary").textContent = failed.length
      ? failed
          .map(([k]) => k.replaceAll("_", " ") + ": attention needed")
          .join(" · ")
      : "Local camera, listener, and network checks look healthy.";
    const urls = (d.obs_browser_source_urls || []).join("\n");
    $("diagnostic-details").textContent =
      "OBS URL(s): " +
      urls +
      "\n" +
      (d.problems || []).join("\n") +
      "\n" +
      d.remote_client_note;
  } catch (e) {
    $("diagnostic-summary").textContent =
      "Diagnostics unavailable: " + e.message;
  }
}
// Health monitor status
async function refreshHealth() {
  try {
    const h = await request("/api/health");
    $("health-state").textContent = "Status: " + h.state.replaceAll("_", " ");
    $("health-reason").textContent = h.reason || "No active issue reported.";
    $("health-details").textContent =
      "Recoveries: " +
      (h.recovery_count || 0) +
      " · Last checked: " +
      (h.last_checked_at || "not yet") +
      (h.last_recovery_at ? " · Last recovery: " + h.last_recovery_at : "");
  } catch (e) {
    $("health-state").textContent = "Health status unavailable";
    $("health-reason").textContent = e.message;
  }
}
