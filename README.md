# PetCam

PetCam is a Raspberry Pi camera streaming and management application. It supports USB UVC webcams and Raspberry Pi CSI cameras, provides an authenticated web manager, and exposes streams for OBS.

This repository owns the application source and its runtime deployment assets. [petcam-os](https://github.com/mintymelinda/petcam-os) owns operating-system image generation, assembly, signing, validation, and publishing.

## Repository layout

```text
src/petcam/       Python application
deploy/           Runtime configuration, systemd units, and privileged helpers
tests/            Application tests
tools/            Application release tooling
docs/             Feature and operations documentation
assets/           Project assets
VERSION           Application version
```

Deployment assets are grouped by purpose rather than by the image-builder mechanism that originally installed them. The OS image project is responsible for mapping these files into the target filesystem.

## Development

Python 3.11 or newer is supported. Create an environment and install the development dependencies:

```bash
python -m pip install -e ".[test]"
python -m pytest
```

Run static bytecode compilation with:

```bash
python -m compileall -q src tests tools
```

GitHub Actions runs the application test and compilation checks. It does not build Raspberry Pi OS images, run pi-gen, assemble Docker images, or publish OS images.

## Documentation

- [Home Assistant MQTT integration](docs/home-assistant.md)
- [Optional RTMP output](docs/rtmp-output.md)
- [Motion detection](docs/motion-detection.md)
- [Timelapse capture](docs/timelapse.md)
- [Application update engine](docs/update-engine.md)


## Runtime privileges

PetCam application services run as root. This is intentional for direct access to
camera devices, system services, GPIO/I²C hardware, storage mounts, and update
installation. The web manager retains its application authentication and CSRF
checks; signed-update verification remains enabled. PetCam no longer installs a
dedicated service account, sudoers policy, or privileged-command wrapper.
