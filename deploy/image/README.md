# Raspberry Pi OS image build

Docker Compose assembles a portable PetCam source bundle. The `usimd/pi-gen-action` workflow generates Raspberry Pi OS Trixie ARM64 and uses a thin custom stage to install feature-owned OS packages and place PetCam at `/opt/petcam`. The existing source installer remains usable on already-running Debian and Raspberry Pi OS systems.

## Production image signing

Production releases are published only from `vMAJOR.MINOR.PATCH` tags matching `VERSION`. Pull-request, main-branch, and manual builds remain unsigned validation artifacts.

The release job uses the same `PETCAM_UPDATE_SIGNING_PRIVATE_KEY` Actions secret and Ed25519 procedure as PetCam OS. The corresponding public key is pinned in `image-signing.pub`. Before signing, the helper derives the public key from the supplied private key and requires an exact match. It creates a canonical JSON manifest containing the image version, ARM64 architecture, HTTPS release URL, byte size, and SHA-256 digest, signs it with OpenSSL Ed25519, and verifies the signature against the pinned public key.

The workflow creates or reuses a draft GitHub Release, uploads the image, signed manifest, detached signature, and public key, verifies all required assets, and only then publishes the release. Missing or mismatched signing credentials fail closed.
