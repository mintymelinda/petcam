"""Systemd entry point for the timelapse feature."""

from .service import main


if __name__ == "__main__":
    raise SystemExit(main())
