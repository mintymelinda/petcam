# PetCam

PetCam is the application source for a Raspberry Pi camera streaming and management system. It supports USB UVC webcams and Raspberry Pi CSI cameras, exposes camera streams for OBS, and provides an authenticated web manager.

This repository contains the runtime application, deployment assets required by the application, tests, and feature documentation. Raspberry Pi OS image generation and publishing are maintained separately in [petcam-os](https://github.com/mintymelinda/petcam-os).

## Project layout

- `petcam/` — runtime Python application modules.
- `deploy/` — runtime configuration, systemd units, and service helpers.
- `tests/` — application unit tests.
- `docs/` — feature and operations documentation.
- `assets/` — application assets.
- `VERSION` — application release version.

## Development

The application uses Python's standard library at runtime. Install the test dependency and run the suite:

```bash
python -m pip install pytest
python -m pytest -q
```

The GitHub Actions workflow runs the test suite and Python compilation checks. No Raspberry Pi image build, pi-gen, Docker image assembly, or image publishing occurs in this repository.

## Documentation

- [Home Assistant MQTT integration](docs/home-assistant.md)
- [Optional RTMP output](docs/rtmp-output.md)
- [Motion detection](docs/motion-detection.md)
- [Timelapse capture](docs/timelapse.md)
- [Application update engine](docs/update-engine.md)
