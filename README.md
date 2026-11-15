# PetCam

PetCam is the application source for a Raspberry Pi camera streaming and management system. It supports USB UVC webcams and Raspberry Pi CSI cameras, exposes camera streams for OBS, and provides an authenticated web manager.

This repository contains the runtime application, its runtime configuration and service definitions, tests, and feature documentation. Raspberry Pi OS image generation and publishing are maintained separately in [petcam-os](https://github.com/mintymelinda/petcam-os).

## Repository contents

- Runtime Python application modules: `stage-petcam/00-install-files/files/usr/local/lib/petcam/`
- Runtime configuration, systemd units, and service helpers: `stage-petcam/00-install-files/files/`
- Unit tests: `tests/`
- Feature and operations documentation: `docs/`
- Application version: `VERSION`

The source layout is retained so existing tests and runtime packaging references remain valid. Image-generation workflows, pi-gen stages, image assembly scripts, and image publication tooling are not part of this repository.

## Development

The application uses Python's standard library at runtime. Install the test dependency and run the suite:

```bash
python -m pip install pytest
python -m pytest -q
```

GitHub Actions runs unit tests and Python compilation checks. This repository does not build Raspberry Pi OS images, run pi-gen, assemble Docker images, or publish OS images.

## Documentation

- [Home Assistant MQTT integration](docs/home-assistant.md)
- [Optional RTMP output](docs/rtmp-output.md)
- [Motion detection](docs/motion-detection.md)
- [Timelapse capture](docs/timelapse.md)
- [Application update engine](docs/update-engine.md)
