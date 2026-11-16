"""Systemd worker entry point for motion detection."""
from .service import main

if __name__ == "__main__":
    raise SystemExit(main())
