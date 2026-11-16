# PetCam dead-code and configuration audit

**Audit date:** 2026-11-15  
**Audited revision:** `main` at `ad7576377fbaca7d3783b092d4292318ad5a23bf`  
**Implementation branch:** `audit/dead-code-and-unused-config`  
**Method:** static source and cross-reference inspection, followed by direct cleanup and regression/CI coverage for the findings below.

## Findings and changes made

### 1. [High] Pillow was missing from runtime dependencies — fixed

**Evidence:** `pyproject.toml` declared no runtime dependencies while `motion_detection.py` imports `PIL.Image` during worker startup and `timelapse.py` uses Pillow for image processing. Pillow was only in the test extra.

**Change:** Moved `Pillow>=10` into project runtime dependencies and left only pytest in the test extra. CI now installs the base application package before installing pytest, and checks the built wheel metadata for a Pillow runtime requirement.

### 2. [Medium] Shipped RTSP config contained unsupported settings — fixed

**Evidence:** `deploy/etc/petcam/rtmp.json` shipped `encoder`, `width`, `height`, `fps`, and `bitrate_kbps`, but `rtmp_output.py` accepts only `enabled`. Unknown keys are discarded and the file is rewritten on load.

**Change:** Reduced the shipped configuration to the supported `enabled` setting. Added a regression test asserting the shipped config keys exactly match the runtime schema.

### 3. [Medium] CI skipped split dashboard modules — fixed

**Evidence:** The dashboard loads `dashboard-api.js`, `dashboard-core.js`, `dashboard-camera.js`, and `dashboard-features.js`, but CI only checked the legacy dashboard entry and browser-source scripts. Wheel assertions omitted the split modules too.

**Change:** CI now runs pinned Prettier check-only validation and `node --check` over every JavaScript file shipped in the static asset directory. Wheel inspection explicitly requires all four split modules and the browser-source assets. The old CI behavior that formatted and pushed commits to pull-request branches has been removed.

### 4. [Low] Three hidden telemetry containers were unused — fixed

**Evidence:** `dashboard.html` contained hidden `#frame-statistics`, `#viewer-statistics`, and `#network-statistics` elements with no references in the shipped JavaScript. Active telemetry is rendered in `#system-health-grid` and timestamped in `#statistics-updated`.

**Change:** Removed the three inert elements.

### 5. [Medium] `camera_profiles.py` existed only for historical updater compatibility — fixed

**Evidence:** The module had no current application imports. Its docstring said its only remaining purpose was to satisfy archive validation by older installed updaters after the multi-stream profile implementation had been removed.

**Change:** Deleted `src/petcam/camera_profiles.py`. A repository code search found no remaining references. Historical upgrade compatibility is not treated as a reason to preserve dead application code.

## Deliberately retained paths

Camera, capture, stream, worker, and systemd entry points are invoked externally by deployment/service configuration. They are not candidates for removal merely because they lack ordinary Python imports. No code was deleted based solely on identifier occurrence counts or other name-based heuristics.

## Validation

The PR adds regression coverage for the shipped RTSP config schema and strengthens CI to verify:
- all shipped dashboard/browser-source JavaScript is formatted and syntactically valid;
- all split dashboard JavaScript modules are present in the built wheel;
- the wheel declares Pillow as a runtime dependency;
- the normal unit test, compile, and architecture checks continue to run.

CI results are authoritative for execution status. This was a static audit; no physical camera, Raspberry Pi hardware, or live streaming test was performed.
