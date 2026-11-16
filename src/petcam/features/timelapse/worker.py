"""Systemd worker entry point for timelapse capture."""
from .service import main

if __name__ == "__main__":
    raise SystemExit(main())
