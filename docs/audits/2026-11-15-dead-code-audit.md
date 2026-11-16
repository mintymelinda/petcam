# PetCam dead-code and configuration audit

**Audit date:** 2026-11-15  
**Audited revision:** `main` at `ad7576377fbaca7d3783b092d4292318ad5a23bf`  
**Scope:** application Python modules, dashboard/browser-source assets, package metadata, deployment configuration and systemd entry points, and CI packaging/validation.  
**Method:** static source and cross-reference inspection. This report records confirmed mismatches and high-confidence unused markup; it does not claim that dynamic runtime paths or hardware-specific behavior were exercised.

## Findings

### 1. [High] Pillow is used at runtime but is only declared as a test extra

**Evidence**

- `pyproject.toml:11` declares `dependencies = []`.
- `pyproject.toml:14` puts `Pillow>=10` under the `test` optional extra.
- `src/petcam/motion_detection.py:16` imports `PIL.Image` and `PIL.ImageChops` in the worker's normal startup path.
- `src/petcam/timelapse.py` imports `PIL.Image` when image processing is used.

**Impact**

A normal installation of the application package does not install Pillow. The test extra masks this packaging defect in CI; a clean target installed from the base package can fail when motion detection starts, and timelapse image processing can fail when resizing/re-encoding is enabled.

**Recommendation**

Declare Pillow as an application runtime dependency, or explicitly document and validate an OS-managed Pillow runtime dependency in the deployment package. Keep pytest in the test extra. Add a wheel/install smoke test that installs the base package into a clean environment and imports the worker modules.

**Confidence:** High.

### 2. [Medium] The shipped RTSP configuration contains obsolete encoder/transcode settings

**Evidence**

- `deploy/etc/petcam/rtmp.json:3-7` ships `encoder`, `width`, `height`, `fps`, and `bitrate_kbps`.
- `src/petcam/rtmp_output.py:20` defines the current configuration schema as only `{"enabled": false}`.
- `src/petcam/rtmp_output.py:27-30` filters all input keys against that schema.
- `src/petcam/rtmp_output.py:52` rewrites a loaded file when it contains unknown keys.

**Impact**

The five sample values are ignored and removed the first time the service loads the file. They imply that the current RTSP publisher supports configurable encoding or transcoding, although the current implementation is a no-transcode stream-copy publisher. This is stale configuration, not a dormant feature waiting to be enabled.

**Recommendation**

Reduce the deployed sample to the supported `enabled` setting and add a regression test that asserts the shipped configuration keys match the runtime schema. Do not retain obsolete keys solely for migration compatibility.

**Confidence:** High.

### 3. [Medium] CI does not format or syntax-check the split dashboard modules

**Evidence**

- `.github/workflows/ci.yml:29-35` runs Prettier and `node --check` only against `dashboard.js` and `browser-source.js`.
- The dashboard loads `dashboard-api.js`, `dashboard-core.js`, `dashboard-camera.js`, and `dashboard-features.js` as separate scripts in `src/petcam/static/dashboard.html`.
- The wheel inspection in `.github/workflows/ci.yml` requires the legacy dashboard/browser-source assets but does not explicitly assert the presence of all four split dashboard modules.

**Impact**

A syntax or formatting regression in any extracted dashboard module can pass the current JavaScript validation job even though the browser loads that file on every dashboard visit. Package-data currently includes the static JS glob, but the wheel test does not guard the complete runtime asset set.

**Recommendation**

Run the pinned Prettier check and `node --check` over every shipped JavaScript asset (or a maintained explicit list). Extend the wheel inspection's required-file set to include all split dashboard modules. Prefer check-only CI; keep formatting changes in the PR rather than having CI push commits to contributor branches.

**Confidence:** High.

### 4. [Low] Three hidden dashboard telemetry containers are unreferenced

**Evidence**

- `src/petcam/static/dashboard.html:79` contains hidden elements `#frame-statistics`, `#viewer-statistics`, and `#network-statistics`.
- None of the dashboard JavaScript modules references those IDs; the active telemetry display uses `#system-health-grid` and `#statistics-updated`.

**Impact**

These are inert markup remnants and make the dashboard's DOM appear to expose telemetry panels that are no longer populated.

**Recommendation**

Remove the three hidden containers. They have no references in the shipped application code; undocumented external consumers are not a reason to preserve dead internal markup without an explicit supported integration contract.

**Confidence:** Medium-high (static reference scan; external consumers cannot be ruled out).

### 5. [Medium] `camera_profiles.py` is an unused compatibility-only module

**Evidence**

- `src/petcam/camera_profiles.py` has no application imports.
- Its module docstring identifies its remaining purpose as satisfying older installed updater validation of upgrade archives.
- No current application feature or runtime entry point depends on this module.

**Impact**

The module exists solely to accommodate a past updater/upgrade path. Keeping it adds compatibility-only surface area and perpetuates obsolete upgrade behavior without providing current application functionality.

**Recommendation**

Remove `src/petcam/camera_profiles.py` and remove any remaining references that exist only to preserve the old updater compatibility path. Do not retain dead code solely for historical upgrade compatibility; current supported application behavior is the source of truth.

**Confidence:** High for absence of current application imports; verify archive-validation references are removed as part of deletion.

## Preserve active external entry points

- Camera, capture, stream, worker, and systemd entry points are externally invoked by deployment/service configuration. Lack of ordinary Python imports is not evidence that those files are unused.
- No additional function or configuration removal is proposed from name-count heuristics alone. Python worker entry points, dynamically loaded modules, service commands, and browser globals make naive single-reference counts unsafe.

## Suggested remediation order

1. Correct the Pillow runtime dependency contract and add a clean-install import smoke test.
2. Remove the obsolete RTSP sample keys and assert config-schema parity.
3. Expand JavaScript formatting, syntax, and wheel-asset coverage to all shipped modules.
4. Remove the inert hidden telemetry containers.
5. Remove the obsolete `camera_profiles.py` compatibility module and updater-only references.

## Audit limitations

This is a static audit of the recorded main revision. It does not establish that optional hardware integrations work on every supported Raspberry Pi image, nor can it detect references in external scripts or user modifications. Historical updater compatibility is not treated as a reason to preserve dead application code. The report distinguishes current externally invoked service entry points from unused compatibility-only remnants.
