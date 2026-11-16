"""Systemd worker entry point for the ambient light feature."""
from .service import main

if __name__ == "__main__":
    raise SystemExit(main())
