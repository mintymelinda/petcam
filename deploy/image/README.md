# Raspberry Pi OS image build

Docker Compose assembles a portable PetCam source bundle. The `usimd/pi-gen-action` workflow generates Raspberry Pi OS Trixie ARM64 and uses a thin custom stage to install feature-owned OS packages and place PetCam at `/opt/petcam`. The existing source installer remains usable on already-running Debian and Raspberry Pi OS systems.

## Build cache and stage ordering

The image workflow uses pi-gen-action's work-directory cache. Builds on `main` are the only writers; pull requests and other refs restore the default-branch cache in read-only mode. The cache key is commit-specific, with restore prefixes allowing a new commit to reuse the previous compatible work directory.

The PetCam stage intentionally remains **after** `stage0 stage1 stage2`. Those upstream OS stages are the expensive, relatively stable part of the build. PetCam's bundle and package manifest change more frequently, so keeping the custom stage last isolates those changes and preserves the reusable upstream work. Moving PetCam earlier would put later OS stages downstream of it and reduce the usefulness of the cache.

The cache is an optimization, not a correctness boundary: pi-gen stages still run, and the action excludes cached root filesystems when saving work artifacts to avoid stale rootfs state. We validate the generated compressed image on every build.

The cache-enabled pi-gen action source is pinned to an immutable upstream commit and packaged with `npm ci` / `npm run package` before execution, because the cache implementation is newer than the published v1.11.0 action bundle. Git is explicitly installed as a host dependency for pi-gen's build tooling; the pi-gen Docker builder also installs Git in its own image.

## Production image signing

Production releases are published only from `vMAJOR.MINOR.PATCH` tags. The Git tag is the sole source of the release version; the workflow validates the tag format and derives the manifest version and asset names directly from it. No separate version file is maintained.

The release job uses the same `PETCAM_UPDATE_SIGNING_PRIVATE_KEY` Actions secret and Ed25519 procedure as PetCam OS. The corresponding public key is pinned in `image-signing.pub`. Before signing, the helper derives the public key from the supplied private key and requires an exact match. It creates a canonical JSON manifest containing the image version, ARM64 architecture, HTTPS release URL, byte size, and SHA-256 digest, signs it with OpenSSL Ed25519, and verifies the signature against the pinned public key.

The workflow creates or reuses a draft GitHub Release, uploads the image, signed manifest, detached signature, and public key, verifies all required assets, and only then publishes the release. Missing or mismatched signing credentials fail closed.
