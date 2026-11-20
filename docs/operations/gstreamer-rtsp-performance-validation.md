# Native H.264 RTSP performance and regression validation

This procedure validates the direct H.264 handoff introduced by the native capture pipeline. Run it on the Raspberry Pi after deploying the change; CI does not have the camera, RTSP clients, or target CPU needed for meaningful measurements.

## Expected pipeline shape

- The persistent capture pipeline parses H.264 into byte-stream access units once.
- Its RTSP branch hands those access units to an appsink.
- The shared RTSP media pipeline receives them through appsrc and packetizes them for RTSP clients.
- There is no local RTP-over-UDP bridge, rtpjitterbuffer, or depayload/re-payload cycle between capture and RTSP.
- The frame-consumer valve is before the frame-branch H.264 parser and decoder. When motion and timelapse are disabled, the valve drops buffers before that branch parses or decodes them.
- The RTSP media factory remains shared, so multiple clients consume the same encoded media pipeline.
- The native RTSP handoff queue is configured with a 100 MiB byte ceiling (`max-size-buffers=0`, `max-size-time=0`). This is a capacity limit, not a preallocation: memory is committed only as buffers accumulate. The queue remains downstream-leaky, so it discards the oldest queued access units if it reaches the ceiling rather than allowing latency to grow without bound. The separate frame-consumer queue remains small and leaky to keep motion/timelapse samples fresh.

## CPU measurement

Use the same camera mode and resolution for every measurement. Keep motion and timelapse disabled. Measure three phases: no RTSP clients, one client, and two clients. Allow 10 seconds to settle after changing the number of clients, then measure for 30 seconds.

The following helper reports process CPU as a percentage of one logical CPU and the stream heartbeat:

```bash
measure_gstreamer_cpu() {
    local pid
    pid=$(pgrep -f '^/usr/bin/python3 -m petcam.infrastructure.streaming.gstreamer$' | head -n 1)
    if [ -z "$pid" ]; then
        echo "GStreamer worker not found" >&2
        return 1
    fi

    python3 - "$pid" <<'PY'
import os
import sys
import time

pid = sys.argv[1]
path = f"/proc/{pid}/stat"

def cpu_ticks():
    raw = open(path, encoding="ascii").read()
    fields = raw.rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])

start = time.monotonic()
before = cpu_ticks()
time.sleep(30)
elapsed = time.monotonic() - start
after = cpu_ticks()
cpu = (after - before) / os.sysconf("SC_CLK_TCK") / elapsed * 100
print(f"PID {pid}: {cpu:.1f}% of one logical CPU over {elapsed:.1f}s")
PY

    python3 - <<'PY'
import json
import time
p = "/run/petcam/g-streamer-status.json"
d = json.load(open(p, encoding="utf-8"))
print("heartbeat age: %.2fs | state: %s | fps: %s" %
      (time.time() - d["updated_at"], d["state"], d["fps"]))
PY
}
```

Run it once with no RTSP clients, once with one client, and once with two independent clients. Record the camera resolution, client count, CPU percentage, and reported FPS for each phase. Compare results on the same device against the pre-change baseline. Before this change, the observed baseline was approximately 20–30% CPU with no viewer and approximately 64% with one viewer; these were short samples, not controlled averages.

## Functional regression matrix

1. **No clients:** GStreamer remains healthy, reports approximately the configured camera FPS, and does not accumulate appsrc buffers.
2. **One client:** connect an RTSP viewer; confirm video is live, stable, and approximately the configured FPS.
3. **Two clients:** connect two independent viewers; confirm both receive video concurrently. Closing one must not interrupt the other.
4. **Reconnect:** close all viewers, wait for the shared RTSP media to unprepare, then reconnect. Confirm the new session receives video without restarting GStreamer.
5. **Camera mode transition:** keep at least one viewer connected while switching between supported camera resolutions/modes. Confirm the RTSP control session remains connected and video resumes at the new mode.
6. **Repeated transitions:** repeat the mode change several times and check for stale frames, frozen video, or worker restarts.
7. **Frame consumers:** enable motion or timelapse and confirm sampled frames still arrive; disable both and confirm the frame branch returns to the dropped state.

## Structural checks

After starting GStreamer, verify that the old local RTP bridge is absent:

```bash
PID=$(pgrep -f '^/usr/bin/python3 -m petcam.infrastructure.streaming.gstreamer$' | head -n 1)
ss -u -a -n -p | grep "pid=$PID" || true
top -H -b -n 1 -p "$PID" | head -n 28
```

There should be no GStreamer-owned UDP socket on port 5004 and no internal rtpjitterbuffer thread. UDP sockets used by RTSP client transports (including RTCP) are expected when clients negotiate UDP transport.

Do not consider the optimization complete based only on the structural check: the CPU comparison and functional matrix above must also pass on the target device.


## Target-device observations (2026-11-19)

The following measurements were collected on the installed `kittycam` device while an RTSP client was actively viewing the camera stream:

- Native RTSP queue configured capacity: 100 MiB.
- Sampled queue high-water mark: 0.04 MiB, 2 buffers, 68.1 ms.
- Queue occupancy was normally 0.00 MiB at the periodic log samples.
- GStreamer process RSS: 35.5 MiB at the start of the memory observation.
- RSS remained 35.5 MiB at all 16 samples taken one minute apart (15 minutes total).
- Memory breakdown remained approximately 16.0 MiB anonymous and 19.6 MiB file-backed; swap remained 0 MiB.
- A point-in-time CPU reading at the initial memory baseline was 32.1% of one logical CPU. This was not a controlled CPU benchmark and must not be compared directly with the earlier short pre-change samples (approximately 20–30% with no viewer and 64% with one viewer).

The queue's observed peak was approximately 0.04% of its configured byte ceiling. These results do not indicate queue pressure or continuing process RSS growth during this test. Keep the 100 MiB ceiling unchanged unless a repeatable workload demonstrates queue saturation or unacceptable latency.

**Instrumentation note:** queue occupancy and high-water logging were added temporarily to the installed worker for this test. The instrumentation was not committed to the repository and is not part of the PetCam release. The queue was sampled once per second, so brief sub-second peaks may have been missed.

This is a limited target-device result, not full release sign-off. Complete the zero/one/two-client CPU and functional regression matrix above, including reconnects, camera-mode transitions, and motion/time-lapse frame-consumer checks, before claiming those scenarios are validated.
