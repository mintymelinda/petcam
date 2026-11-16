"""Systemd entry point for Home Assistant discovery publishing."""

from .service import main


if __name__ == "__main__":
    raise SystemExit(main())
