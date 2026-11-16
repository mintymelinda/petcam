"""Systemd entry point for the motion-detection feature."""

from .service import main


if __name__ == "__main__":
    raise SystemExit(main())
