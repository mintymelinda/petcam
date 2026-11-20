# Time-lapse storage

Time-lapse is disabled by default. When enabled, PetCam periodically saves still images from the shared camera sampler; it does not start a second camera capture process.

## Default settings

- Capture interval: 300 seconds (5 minutes).
- Schedule: 00:00–23:59 local device time.
- Retention: 30 days.
- Maximum storage: 2048 MiB.
- Minimum free space: 256 MiB.
- Default directory: `/var/lib/petcam/timelapse/frames`.
- Maximum width: 0 (keep the source width).
- JPEG quality: 0 (preserve the source JPEG unless resizing/re-encoding is requested).

The dashboard's Time-Lapse tab lets you enable captures and change the schedule, interval, retention, storage limits, image processing, and directory.

## Local storage

The default directory is under `/var/lib/petcam`. PetCam validates the configured path and only permits directories inside `/var/lib/petcam` or beneath the dedicated network mount at `/mnt/petcam-network`.

Keep enough free space on the device for the operating system and other PetCam data. The minimum-free-space setting stops new captures when free space falls below the configured threshold; retention and maximum-storage limits are also applied by the worker.

## SMB or NFS network storage

PetCam does not configure NAS credentials or mount network shares. Configure the SMB/CIFS or NFS mount using the operating system's normal mount tooling, and ensure it is mounted at this exact path:

```text
/mnt/petcam-network
```

The mount must be an active filesystem mount of type `cifs`, `nfs`, or `nfs4`. A directory, symlink, bind mount, or a share mounted at a different path does not satisfy the worker's network-mount check. The selected time-lapse directory must be a subdirectory beneath the mount point, for example:

```text
/mnt/petcam-network/petcam/timelapse
```

Before selecting the directory in the dashboard, create the directory on the mounted share and ensure the PetCam worker can write to it. Check the mount with:

```sh
mountpoint /mnt/petcam-network
findmnt -T /mnt/petcam-network
```

Confirm that the reported mount target is exactly `/mnt/petcam-network` and the filesystem type is CIFS/SMB or NFS.

### Missing or disconnected network share

If the configured storage directory is beneath `/mnt/petcam-network` and the expected SMB/NFS mount is not active, PetCam pauses time-lapse capture and reports `network_storage_unavailable`. It does **not** silently write frames to the Raspberry Pi's SD card. Captures can resume after the expected network filesystem is mounted again.

Do not configure the storage directory as `/mnt/petcam-network` itself; choose a folder beneath it.
