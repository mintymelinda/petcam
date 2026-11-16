// Camera selection and capture configuration
function modesFor(camera) {
  return camera.capture_modes || [];
}
function selectedCaptureMode() {
  try {
    return JSON.parse($("mode").value);
  } catch (error) {
    return null;
  }
}
function h264ModeSelectedOrActive() {
  return (
    (activeConfig?.SOURCE === "usb" && activeConfig?.FORMAT === "H264") ||
    captureStatus.active_capture_format === "H264" ||
    selectedCaptureMode()?.format === "H264"
  );
}
function syncOutputModeControls() {
  const forced = h264ModeSelectedOrActive();
  document.querySelectorAll("[data-browser-feed-link]").forEach((link) => {
    link.closest("p").hidden = forced;
  });
  $("h264-mode-note").hidden = !forced;
}

function projectedPixelRate(mode) {
  return Number(mode.estimated_pixels_per_second || 0);
}
function exceedsPerformanceBudget(_camera, mode) {
  return mode.exceeds_performance_budget === true;
}
function confirmPerformanceOverride(camera, mode) {
  if (!exceedsPerformanceBudget(camera, mode)) return false;
  const estimate = projectedPixelRate(mode),
    budget = Number(mode.performance_budget_pixels_per_second || 0);
  return confirm(
    "Performance warning: this capture mode is estimated at " +
      estimate.toLocaleString() +
      " pixels/second, above the " +
      camera.hardware_tier +
      " device guideline of " +
      budget.toLocaleString() +
      " pixels/second. It may cause low frame rates, dropped frames, or an unresponsive camera stream. Use this mode anyway?",
  );
}
function showSelectedModeWarning() {
  const c = inventory[+$("camera").value],
    raw = $("mode").value;
  if (!c || !raw) return;
  const mode = JSON.parse(raw);
  if (exceedsPerformanceBudget(c, mode))
    $("message").textContent =
      "Performance warning: this capture mode exceeds the estimated " +
      c.hardware_tier +
      " device budget. You can still apply it after confirming the warning.";
  else
    $("message").textContent =
      mode.format === "H264"
        ? "H.264 selected. The HTTP Browser Source will be disabled and the always-on RTSP service serves H.264 directly."
        : "Selected mode is within the estimated device performance budget.";
  syncOutputModeControls();
}
function activeCameraMatches(camera, config) {
  if (!config) return false;
  if (config.SOURCE === "usb")
    return (
      camera.kind === "usb" &&
      (config.USB_PHYSICAL_PATH
        ? camera.physical_path === config.USB_PHYSICAL_PATH
        : camera.device === config.DEVICE)
    );
  if (config.SOURCE === "csi")
    return (
      camera.kind === "csi" &&
      (config.CSI_DEVICE_PATH
        ? camera.device_path === config.CSI_DEVICE_PATH
        : String(camera.camera) === String(config.CAMERA))
    );
  return false;
}
function fillModes(preferred = null) {
  const camera = inventory[+$("camera").value];
  $("mode").replaceChildren();
  if (!camera) return;
  let matched = false;
  for (const mode of modesFor(camera)) {
    const option = document.createElement("option");
    option.value = JSON.stringify(mode);
    option.textContent =
      `${mode.width}×${mode.height} · ${mode.fps} fps · ${mode.format}` +
      (exceedsPerformanceBudget(camera, mode)
        ? " · ⚠ above device estimate"
        : "");
    if (
      preferred &&
      mode.width === preferred.width &&
      mode.height === preferred.height &&
      mode.format === (preferred.format || "CSI") &&
      Math.abs(mode.fps - preferred.fps) < 0.1
    ) {
      option.selected = true;
      matched = true;
    }
    $("mode").append(option);
  }
  if (preferred && !matched) {
    const mode = {
      format: preferred.format || "CSI",
      width: preferred.width,
      height: preferred.height,
      fps: Number(preferred.fps),
      exceeds_performance_budget: false,
    };
    const option = document.createElement("option");
    option.value = JSON.stringify(mode);
    option.textContent = `${mode.width}×${mode.height} · ${mode.fps} fps · ${mode.format} (saved setting; not currently advertised)`;
    option.selected = true;
    $("mode").prepend(option);
  }
  $("mode").onchange = showSelectedModeWarning;
  showSelectedModeWarning();
}
// Capture and OBS output status
function renderCaptureStatus() {
  const fps = Number(captureStatus.latest_captured_fps),
    configured = activeConfig?.FPS,
    format = captureStatus.active_capture_format;
  if (Number.isFinite(fps) && fps > 0) {
    $("capture-rate").textContent =
      "Actual captured rate: " +
      fps.toFixed(1).replace(/\.0$/, "") +
      " FPS" +
      (format ? " · " + format : "") +
      (configured && configured !== "auto"
        ? " · configured: " + configured + " FPS"
        : "") +
      (captureStatus.active_resolution
        ? " · " + captureStatus.active_resolution
        : activeConfig?.RESOLUTION && activeConfig.RESOLUTION !== "auto"
          ? " · " + activeConfig.RESOLUTION
          : "") +
      (captureStatus.capture_mode === "native_h264_csi"
        ? " · CSI hardware encoder"
        : "");
  } else
    $("capture-rate").textContent =
      "Actual captured rate: not currently reported" +
      (format ? " · " + format : "");
}
async function refreshLiveStatus() {
  try {
    const d = await request("/api/live-status");
    refreshStatistics(d);
    captureStatus = d.capture_status || {};
    renderCaptureStatus();
    syncOutputModeControls();
    const updated = new Date(d.capture_status_updated_at * 1000);
    $("capture-status-freshness").textContent =
      "Capture status refreshes every 5 seconds · last updated " +
      updated.toLocaleTimeString();
  } catch (error) {
    $("capture-status-freshness").textContent =
      "Live status unavailable: " + error.message;
  }
}

async function refreshSystemInfo() {
  try {
    const data = await request("/api/system");
    $("installed-version").textContent =
      "Installed version: " + (data.installed_version || "unknown");
  } catch (error) {
    $("installed-version").textContent =
      "Installed version unavailable: " + error.message;
  }
}

function renderGStreamerStatus(status) {
  const source =
    status.source === "native_h264_csi"
      ? "CSI hardware H.264 stream copy"
      : status.source === "native_h264"
        ? "native H.264 stream copy"
        : status.source === "mjpeg_copy"
          ? "MJPEG packet copy"
          : "camera source pending";
  $("g-streamer-status").textContent =
    "GStreamer RTSP service: " +
    (status.state || "starting") +
    (status.service_active
      ? " · always on · " + source
      : " · service unavailable");
}

async function refreshGStreamer() {
  try {
    const data = await request("/api/live-status");
    renderGStreamerStatus(data.g_streamer_status || {});
  } catch (error) {
    $("g-streamer-status").textContent =
      "GStreamer RTSP status unavailable: " + error.message;
  }
}
// System statistics
function renderStatCards(root, items) {
  root.replaceChildren();
  for (const [label, value] of items) {
    const card = document.createElement("div"),
      name = document.createElement("small"),
      reading = document.createElement("strong");
    card.style.cssText =
      "background:#1a1d22;border:1px solid #383e47;border-radius:8px;padding:.7rem;min-width:0";
    name.className = "muted";
    name.textContent = label;
    reading.style.cssText =
      "display:block;font-size:1.05rem;overflow-wrap:anywhere;margin-top:.2rem";
    reading.textContent =
      value === null || value === undefined || value === ""
        ? "Not available"
        : String(value);
    card.append(name, reading);
    root.append(card);
  }
}
async function refreshStatistics(data = null) {
  try {
    const d = data || (await request("/api/live-status")),
      capture = d.capture_status || {},
      stream = d.stream_metrics || {},
      network = d.network_status || {},
      clients = stream.clients || [],
      system = d.system_metrics || {},
      wifi = network.wifi || {};
    const fps = capture.latest_captured_fps,
      delivered = clients.length
        ? Math.max(
            ...clients.map((client) =>
              Number(client.average_fps || client.window_fps || 0),
            ),
          )
        : null,
      signal = wifi.signal_dbm,
      gStreamer = d.g_streamer_status || {};
    renderGStreamerStatus(gStreamer);
    const bars = !wifi.connected
      ? 0
      : signal === null || signal === undefined
        ? null
        : signal >= -50
          ? 4
          : signal >= -60
            ? 3
            : signal >= -67
              ? 2
              : signal >= -75
                ? 1
                : 0;
    const labels = ["none", "weak", "poor", "good", "excellent"];
    const reception = bars === null ? "unknown" : labels[bars];
    const metrics = [
      ["Camera FPS", fps ? Number(fps).toFixed(1) : "Not reported"],
      [
        "GStreamer RTSP FPS",
        gStreamer.active &&
        gStreamer.fps !== null &&
        gStreamer.fps !== undefined &&
        Number.isFinite(Number(gStreamer.fps))
          ? Number(gStreamer.fps).toFixed(1)
          : gStreamer.service_active
            ? gStreamer.state === "stalled"
              ? "No recent service heartbeat"
              : gStreamer.state
            : "Service unavailable",
      ],
      [
        "MJPEG delivered FPS (forwarded JPEG FPS)",
        delivered === null ? "No active viewers" : delivered.toFixed(1),
      ],
      [
        "Wi-Fi signal",
        reception +
          (signal === null || signal === undefined
            ? ""
            : " · " + signal + " dBm") +
          " · " +
          (bars === null ? "—" : "▮".repeat(bars) + "▯".repeat(4 - bars)),
      ],
      [
        "CPU",
        system.cpu_percent === null || system.cpu_percent === undefined
          ? "Not available"
          : Number(system.cpu_percent).toFixed(1) + "%",
      ],
      [
        "Memory",
        system.memory_used_mb === undefined
          ? "Not available"
          : system.memory_used_mb + " / " + system.memory_total_mb + " MiB",
      ],
      [
        "Network Up / Down",
        network.tx_mbps === undefined
          ? "Not available"
          : Number(network.tx_mbps).toFixed(2) +
            " / " +
            Number(network.rx_mbps || 0).toFixed(2) +
            " Mbps",
      ],
    ];
    renderStatCards($("system-health-grid"), metrics);
    $("statistics-updated").textContent =
      "Updated " +
      new Date(d.capture_status_updated_at * 1000).toLocaleTimeString() +
      " · GStreamer RTSP: " +
      (gStreamer.state || "unknown") +
      "; MJPEG delivery is measured separately.";
  } catch (error) {
    $("statistics-updated").textContent =
      "Statistics unavailable: " + error.message;
  }
}
// Camera inventory and selection refresh
async function refresh() {
  $("message").textContent = "Scanning connected cameras…";
  try {
    const d = await request("/api/cameras");
    inventory = d.cameras;
    activeConfig = d.active_config;
    captureStatus = d.capture_status || {};
    $("camera").replaceChildren();
    inventory.forEach((c, i) => {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = c.label;
      $("camera").append(o);
    });
    const activeIndex = inventory.findIndex((c) =>
      activeCameraMatches(c, activeConfig),
    );
    if (activeIndex >= 0) {
      $("camera").value = String(activeIndex);
      $("camera").options[activeIndex].textContent += " · current";
    }
    if (!inventory.length)
      $("message").textContent =
        "No supported cameras detected. Connect a USB or CSI camera and refresh.";
    else {
      const selected = activeIndex >= 0 ? activeConfig : null;
      const selectedCamera = activeIndex >= 0 ? inventory[activeIndex] : null;
      const currentResolution =
        selected && selected.RESOLUTION !== "auto"
          ? selected.RESOLUTION
          : captureStatus.active_resolution;
      const currentFps =
        selected && selected.FPS !== "auto"
          ? Number(selected.FPS)
          : Number(captureStatus.latest_captured_fps);
      let currentFormat =
        selected && selected.FORMAT !== "auto"
          ? selected.FORMAT
          : captureStatus.active_capture_format || "CSI";
      if (currentFormat === "MJPEG" || currentFormat === "JPEG")
        currentFormat = "MJPG";
      if (selectedCamera?.kind === "csi") currentFormat = "CSI";
      const preferred =
        currentResolution &&
        currentResolution !== "auto" &&
        Number.isFinite(currentFps) &&
        currentFps > 0
          ? {
              width: Number(currentResolution.split("x")[0]),
              height: Number(currentResolution.split("x")[1]),
              fps: currentFps,
              format: currentFormat,
            }
          : null;
      $("message").textContent =
        inventory.length +
        " camera(s) found. Current saved camera settings are selected.";
      fillModes(preferred);
    }
    syncOutputModeControls();
    renderCaptureStatus();
    await refreshCameraControls();
  } catch (e) {
    $("message").textContent = e.message;
  }
}

// Advanced camera controls
function cameraControlLabel(name) {
  const labels = {
    auto_exposure: "Auto exposure",
    exposure_time_absolute: "Exposure time",
    exposure_dynamic_framerate: "Dynamic framerate",
    white_balance_automatic: "Automatic white balance",
    white_balance_temperature: "White balance temperature",
    power_line_frequency: "Power-line frequency",
    backlight_compensation: "Backlight compensation",
    focus_automatic_continuous: "Continuous autofocus",
    focus_absolute: "Focus",
  };
  return (
    labels[name] ||
    name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}
function updateCameraControlDirtyState(control, input, applyButton) {
  const value =
      control.type === "bool" ? (input.checked ? 1 : 0) : Number(input.value),
    original = Number(control.value);
  if (control.value !== null && Number.isFinite(original) && value === original)
    pendingCameraControlChanges.delete(control.name);
  else pendingCameraControlChanges.set(control.name, value);
  applyButton.disabled = pendingCameraControlChanges.size === 0;
}
async function applyCameraControlChanges() {
  const button = $("apply-camera-controls"),
    status = $("camera-controls-status");
  if (!pendingCameraControlChanges.size) return;
  button.disabled = true;
  status.textContent = "Applying camera control changes…";
  try {
    for (const [name, value] of pendingCameraControlChanges) {
      await request("/api/camera-controls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, value }),
      });
      pendingCameraControlChanges.delete(name);
    }
    status.textContent = "Camera controls updated.";
    await refreshCameraControls();
  } catch (error) {
    status.textContent =
      "Could not apply all camera controls: " + error.message;
    button.disabled = pendingCameraControlChanges.size === 0;
  }
}
async function refreshCameraControls() {
  const root = $("camera-controls-list"),
    status = $("camera-controls-status"),
    applyButton = $("apply-camera-controls");
  pendingCameraControlChanges.clear();
  applyButton.disabled = true;
  root.replaceChildren();
  root.style.cssText =
    "display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:.45rem";
  status.textContent = "Reading active camera controls…";
  try {
    const data = await request("/api/camera-controls");
    if (!data.supported) {
      status.textContent = data.message || "Camera controls are unavailable.";
      root.textContent = "";
      return;
    }
    status.textContent = "Controls for " + data.label + " · " + data.device;
    if (!data.controls.length) {
      root.textContent = "This camera did not report any controls.";
      return;
    }
    for (const control of data.controls) {
      const row = document.createElement("div"),
        heading = document.createElement("div"),
        label = document.createElement("label"),
        details = document.createElement("small"),
        editor = document.createElement("div");
      row.style.cssText =
        "border:1px solid #383e47;border-radius:.5rem;padding:.45rem .6rem;min-width:0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.2rem .65rem;align-items:center";
      heading.style.minWidth = "0";
      label.style.margin = "0";
      label.textContent = cameraControlLabel(control.name);
      details.className = "muted";
      details.style.cssText = "display:block;font-size:.78rem;line-height:1.25";
      const isMenu = control.type === "menu" || control.type === "intmenu",
        isBoolean = control.type === "bool",
        menuOption = (value) =>
          control.menu.find((option) => option.value === value),
        booleanLabel = (value) =>
          value === null
            ? "unknown"
            : Number(value) === 1
              ? "Enabled"
              : "Disabled",
        defaultLabel =
          control.default === null
            ? "unavailable"
            : isBoolean
              ? booleanLabel(control.default)
              : control.default;
      details.textContent =
        "Current: " +
        (isMenu
          ? (menuOption(control.value)?.label ?? "unknown")
          : isBoolean
            ? booleanLabel(control.value)
            : control.value === null
              ? "unknown"
              : control.value) +
        (isMenu
          ? " · Default: " +
            (menuOption(control.default)?.label ?? "unavailable") +
            " · Available: " +
            control.menu.map((option) => option.label).join(", ")
          : " · Default: " +
            defaultLabel +
            (control.min !== null && control.max !== null
              ? " · Range: " + control.min + "–" + control.max
              : "")) +
        (control.writable ? "" : " · Currently unavailable");
      editor.className = "row";
      editor.style.cssText =
        "align-items:center;gap:.4rem;justify-content:flex-end";
      let input,
        output,
        isRange = false;
      if (isBoolean) {
        input = document.createElement("input");
        input.type = "checkbox";
        input.checked = Number(control.value) === 1;
        input.indeterminate = control.value === null;
        input.disabled = !control.writable;
      } else if (isMenu) {
        input = document.createElement("select");
        if (control.value === null) {
          const unknown = document.createElement("option");
          unknown.value = "";
          unknown.textContent = "Unknown";
          unknown.disabled = true;
          input.append(unknown);
        }
        for (const option of control.menu) {
          const choice = document.createElement("option");
          choice.value = option.value;
          choice.textContent = option.label;
          input.append(choice);
        }
        input.value = control.value === null ? "" : String(control.value);
        input.disabled = !control.writable;
        input.style.maxWidth = "10rem";
      } else if (
        control.type === "int" &&
        control.value !== null &&
        control.min !== null &&
        control.max !== null &&
        control.max - control.min <= 10000
      ) {
        isRange = true;
        input = document.createElement("input");
        input.type = "range";
        input.min = control.min;
        input.max = control.max;
        input.step = control.step;
        input.value = control.value;
        input.disabled = !control.writable;
        input.style.maxWidth = "8rem";
        output = document.createElement("output");
        output.textContent = input.value;
        input.oninput = () => {
          output.textContent = input.value;
          updateCameraControlDirtyState(control, input, applyButton);
          if (advancedApplyHandle) clearTimeout(advancedApplyHandle);
          advancedApplyHandle = setTimeout(() => {
            if (pendingCameraControlChanges.size) applyCameraControlChanges();
          }, 800);
        };
      } else {
        input = document.createElement("input");
        input.type = "number";
        if (control.min !== null) input.min = control.min;
        if (control.max !== null) input.max = control.max;
        input.step = control.step;
        input.value = control.value ?? "";
        input.placeholder = control.value === null ? "Unknown" : "";
        input.disabled = !control.writable;
        input.style.width = "6rem";
      }
      if (output) editor.append(input, output);
      else editor.append(input);
      if (control.writable && !isRange)
        input.addEventListener("change", () => {
          updateCameraControlDirtyState(control, input, applyButton);
          if (advancedApplyHandle) clearTimeout(advancedApplyHandle);
          advancedApplyHandle = setTimeout(() => {
            if (pendingCameraControlChanges.size) applyCameraControlChanges();
          }, 800);
        });
      heading.append(label, details);
      row.append(heading, editor);
      if (control.name === "exposure_dynamic_framerate") {
        const note = document.createElement("small");
        note.className = "muted";
        note.style.gridColumn = "1 / -1";
        note.textContent =
          "When enabled, the camera may lower its delivered frame rate to accommodate exposure. Disable it if you need a stable frame-rate target.";
        row.append(note);
      }
      root.append(row);
    }
  } catch (error) {
    status.textContent = "Camera controls unavailable: " + error.message;
  }
}
