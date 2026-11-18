// Event wiring and application startup
function initializeDashboard() {
  $("first-run-form").onsubmit = async (event) => {
    event.preventDefault();
    const password = $("setup-password").value,
      confirmation = $("setup-password-confirm").value,
      message = $("setup-message"),
      button = $("setup-submit");
    if (password !== confirmation) {
      message.textContent = "The passwords do not match.";
      return;
    }
    button.disabled = true;
    message.textContent = "Creating administrator account…";
    try {
      const response = await fetch("/api/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, password_confirmation: confirmation }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || "Initial setup failed");
      message.textContent = "Administrator account created. Opening PetCam…";
      location.reload();
    } catch (error) {
      message.textContent = error.message;
      button.disabled = false;
    }
  };
  for (const button of tabButtons) {
    button.addEventListener("click", () => activateTab(button.dataset.tab));
    button.addEventListener("keydown", (event) => {
      const index = tabButtons.indexOf(button);
      let next = null;
      if (event.key === "ArrowRight") next = (index + 1) % tabButtons.length;
      else if (event.key === "ArrowLeft")
        next = (index - 1 + tabButtons.length) % tabButtons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = tabButtons.length - 1;
      if (next !== null) {
        event.preventDefault();
        activateTab(tabButtons[next].dataset.tab, true);
      }
    });
  }
  activateTab("camera");
  refreshGStreamer();
  $("refresh-statistics").onclick = refreshStatistics;
  $("apply-camera-controls").onclick = applyCameraControlChanges;
  $("refresh-camera-controls").onclick = refreshCameraControls;
  $("advanced-camera-open").onclick = () => {
    advancedDialog.showModal();
    refreshCameraControls();
    if (advancedPollHandle) clearInterval(advancedPollHandle);
    advancedPollHandle = setInterval(() => {
      if (pendingCameraControlChanges.size === 0) refreshCameraControls();
    }, 60000);
  };
  $("advanced-camera-close").onclick = () => advancedDialog.close();
  advancedDialog.addEventListener("close", () => {
    if (advancedPollHandle) {
      clearInterval(advancedPollHandle);
      advancedPollHandle = null;
    }
    if (advancedApplyHandle) {
      clearTimeout(advancedApplyHandle);
      advancedApplyHandle = null;
    }
  });
  $("refresh").onclick = refresh;
  $("camera").onchange = () => {
    fillModes();
  };
  $("apply").onclick = async () => {
    const c = inventory[+$("camera").value],
      m = $("mode").value;
    if (!c || !m) return;
    const mode = JSON.parse(m),
      override = confirmPerformanceOverride(c, mode);
    if (exceedsPerformanceBudget(c, mode) && !override) return;
    $("apply").disabled = true;
    $("message").textContent = "Applying camera settings…";
    try {
      await request("/api/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kind: c.kind,
          camera_id: c.id,
          device: c.device,
          physical_path: c.physical_path,
          device_path: c.device_path,
          camera: c.camera,
          mode,
          allow_performance_override: override,
        }),
      });
      await refresh();
      await refreshGStreamer();
      $("message").textContent =
        mode.format === "H264"
          ? "H.264 capture enabled. The RTSP service is serving H.264."
          : "Camera settings saved. The RTSP stream has been restarted.";
    } catch (e) {
      $("message").textContent = e.message;
    } finally {
      $("apply").disabled = false;
    }
  };
  $("logout").onclick = async () => {
    try {
      await request("/api/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      csrfToken = null;
      location.reload();
    } catch (e) {
      alert(e.message);
    }
  };
  $("refresh-timelapse").onclick = refreshTimelapse;
  $("save-timelapse").onclick = async () => {
    const b = $("save-timelapse");
    b.disabled = true;
    try {
      await request("/api/timelapse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: $("timelapse-enabled").checked,
          interval_seconds: Number($("timelapse-interval").value),
          schedule_start: $("timelapse-start").value,
          schedule_end: $("timelapse-end").value,
          retention_days: Number($("timelapse-retention").value),
          max_storage_mb: Number($("timelapse-storage").value),
          min_free_mb: Number($("timelapse-free").value),
          max_width: Number($("timelapse-width").value),
          jpeg_quality: Number($("timelapse-quality").value),
          storage_path: $("timelapse-path").value,
        }),
      });
      await refreshTimelapse();
    } catch (e) {
      $("timelapse-status").textContent = e.message;
    } finally {
      b.disabled = false;
    }
  };
  refreshTimelapse();
  $("refresh-motion").onclick = refreshMotion;
  $("save-motion").onclick = async () => {
    const b = $("save-motion");
    b.disabled = true;
    try {
      await request("/api/motion", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: $("motion-enabled").checked,
          sensitivity: Number($("motion-sensitivity").value),
          minimum_changed_percent: Number($("motion-min-change").value),
          sample_interval_seconds: Number($("motion-sample").value),
          confirm_samples: Number($("motion-confirm").value),
          min_event_interval_seconds: Number($("motion-cooldown").value),
          quiet_hours_enabled: $("motion-quiet-enabled").checked,
          quiet_hours_start: $("motion-quiet-start").value,
          quiet_hours_end: $("motion-quiet-end").value,
          retention_days: Number($("motion-retention").value),
          max_storage_mb: Number($("motion-storage").value),
          min_free_mb: Number($("motion-free").value),
        }),
      });
      await refreshMotion();
    } catch (e) {
      $("motion-status").textContent = e.message;
    } finally {
      b.disabled = false;
    }
  };
  refreshMotion();
  setInterval(refreshMotion, 15000);
  $("refresh-light-sensor").onclick = refreshLightSensor;
  $("save-light-sensor").onclick = async () => {
    const b = $("save-light-sensor");
    b.disabled = true;
    try {
      await request("/api/light-sensor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ENABLED: $("light-sensor-enabled").checked,
          BRIGHT_THRESHOLD_LUX: Number($("light-bright-threshold").value),
          DARK_THRESHOLD_LUX: Number($("light-dark-threshold").value),
        }),
      });
      await refreshLightSensor();
    } catch (e) {
      $("light-sensor-status").textContent = e.message;
    } finally {
      b.disabled = false;
    }
  };
  refreshLightSensor();
  setInterval(refreshLightSensor, 10000);

  $("refresh-diagnostics").onclick = refreshDiagnostics;
  refreshDiagnostics();
  $("download-support-bundle").onclick = async () => {
    const b = $("download-support-bundle");
    b.disabled = true;
    try {
      let r = await fetch("/api/support-bundle");
      if (r.status === 401) {
        await login();
        r = await fetch("/api/support-bundle");
      }
      if (!r.ok)
        throw Error("Support bundle request failed (" + r.status + ")");
      const blob = await r.blob(),
        url = URL.createObjectURL(blob),
        a = document.createElement("a");
      a.href = url;
      a.download = "petcam-support.tar.gz";
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      $("diagnostic-summary").textContent =
        "Support bundle failed: " + e.message;
    } finally {
      b.disabled = false;
    }
  };
  $("save-full-ui").onclick = async () => {
    const button = $("save-full-ui");
    button.disabled = true;
    const disabled = $("disable-full-ui").checked;
    try {
      await request("/api/web-ui", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !disabled }),
      });
      if (disabled) {
        $("full-ui-status").textContent =
          "Full UI disabled. Opening the lightweight setup page…";
        window.location.assign("/setup");
      } else {
        $("full-ui-status").textContent =
          "Full UI enabled. The dashboard service will start within a few seconds; refresh this page if needed.";
      }
    } catch (error) {
      $("full-ui-status").textContent =
        "Unable to update Full UI setting: " + error.message;
      button.disabled = false;
    }
  };
  $("refresh-health").onclick = refreshHealth;
  refresh();
  refreshLiveStatus();
  setInterval(refreshLiveStatus, 5000);
  refreshSystemInfo();
  refreshHealth();
  setInterval(refreshHealth, 30000);
  (async () => {
    try {
      const response = await fetch("/api/setup/status", { cache: "no-store" });
      const state = await response.json();
      if (!response.ok)
        throw Error(state.error || "Unable to check setup status");
      if (!state.configured) {
        document.body.classList.add("setup-required");
        $("first-run").hidden = false;
      }
    } catch (error) {
      $("setup-message").textContent = error.message;
    }
  })();
}

initializeDashboard();
