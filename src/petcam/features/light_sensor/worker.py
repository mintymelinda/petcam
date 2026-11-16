"""Systemd entry point for the ambient light sensor."""

import signal

from .service import _stop_handler, run


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)
    raise SystemExit(run())
