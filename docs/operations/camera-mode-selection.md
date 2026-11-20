# Camera mode selection

PetCam's automatic camera mode is a preference policy, not a promise that every camera supports the same format. The shipped defaults remain:

```ini
FORMAT=auto
RESOLUTION=auto
FPS=auto
```

## USB cameras

When all three settings are automatic, PetCam ranks advertised V4L2 modes deterministically:

1. Native H.264 modes.
2. Compressed JPEG modes (MJPG/MJPEG/JPEG).
3. Other advertised capture formats.

Within a format class, it prefers the resolution nearest **1280×720**, then the frame rate nearest **30 FPS**. Ties are resolved by device path, dimensions, and pixel format, not by the order returned by the driver. When a mode advertises a list of rates, PetCam chooses the rate nearest 30 FPS; stepwise interval ranges are resolved to an actually advertised interval.

This means a camera that advertises H.264 1280×720@30 selects that exact mode. If it does not, the next available format class and closest advertised mode are used. The fallback is based only on discovered camera capabilities.

## CSI cameras

CSI mode selection is based on the sensor modes reported by the Raspberry Pi camera stack. PetCam chooses the advertised mode nearest 1280×720 and 30 FPS, with stable camera-index and mode-value tie-breakers.

With `FORMAT=auto`, PetCam uses native hardware H.264 when a supported hardware encoder is detected. If no encoder is available, it uses the MJPEG capture path. Explicit `FORMAT=H264` requires a detected hardware encoder and fails clearly if one is unavailable.

## Explicit settings

Explicit `FORMAT`, `RESOLUTION`, and `FPS` values take precedence over automatic preferences. PetCam filters the discovered capabilities using those constraints and reports an error when the requested format, resolution, or frame rate is not advertised. It does not silently replace an explicit setting with a different mode.

## Negotiation and troubleshooting

A selected mode is not proof that a camera driver accepted it. For native USB H.264, PetCam waits for the GStreamer capture pipeline to enter PLAYING and checks the live V4L2 source caps for H.264, the selected width and height, and the selected frame rate. A mismatch or missing negotiated caps is treated as a startup failure; GStreamer bus errors are logged with their diagnostic details.

For UVC cameras, inspect the supervisor log for V4L2/GStreamer negotiation errors, including probe/commit failures. The camera status marker records the requested selection; use the GStreamer startup log as confirmation of the actual negotiated native H.264 caps.

The software tests prove deterministic selection and mismatch handling. Each supported target camera still requires a physical boot/restart test to confirm its driver negotiates the expected mode.
