"""Application coordinator for the GStreamer RTSP output service."""


def restart_gstreamer_service(*, systemctl_command, run_command):
    result = run_command(
        systemctl_command("restart", "petcam-g-streamer-rtsp.service"),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            result.stderr.strip() or "Unable to restart the GStreamer RTSP service."
        )


def status_snapshot(status_file, snapshot):
    return snapshot(status_file)
