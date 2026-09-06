# Platform compatibility and media backends

Raspberry Ninja supports multiple boards and Linux generations. Media support is selected from runtime capabilities; a board name or installed plugin is not enough to prove a working path.

Raw-video format selection uses GStreamer's native capability intersection for
resolution ranges, format lists, and fractional frame rates. This avoids relying
on Python bindings to unpack range/list values, which varies across installations.
Matching advertised capabilities is only a selection check: capture and encoding
still need a frame test on the actual device and driver.

Platform hints such as `--rpi` do not override an explicitly selected video codec.
`--h265`, `--hevc`, and `--x265` select H.265; `--aom`, `--rav1e`, and `--qsv`
identify AV1 encoders. The selected backend still needs its plugins and, where
applicable, compatible hardware. RTMP retains its existing H.264 requirement.
Confirm the encoder and RTP payloader in the printed pipeline when diagnosing a
codec mismatch; a platform flag alone does not prove hardware acceleration.

If no supported H.265 encoder is installed, startup falls back to H.264 and runs
the normal H.264 encoder selection before constructing the pipeline. Check the
printed fallback message and final encoder: the requested H.265 codec is no longer
the active codec in that case. The fallback still requires a working H.264 backend.

## Support model

Treat a combination as a distinct platform when any of these differ:

- board and SoC revision;
- 32-bit versus 64-bit userspace;
- distribution and release;
- kernel, firmware, and media drivers;
- GStreamer version and plugin build;
- camera stack and source plugin;
- buffer memory type and encoder/decoder element.

A change that fixes one combination must preserve the other paths or be guarded by capability detection.

## Runtime inventory

Collect this before selecting or changing a pipeline:

```bash
cat /proc/device-tree/model 2>/dev/null; echo
dpkg --print-architecture 2>/dev/null || uname -m
cat /etc/os-release
uname -a
gst-launch-1.0 --version
gst-inspect-1.0 webrtcbin
gst-inspect-1.0 v4l2h264enc
gst-inspect-1.0 x264enc
gst-inspect-1.0 nvv4l2h264enc
gst-inspect-1.0 mpph264enc
v4l2-ctl --list-devices 2>/dev/null
v4l2-ctl -d /dev/video0 --list-formats-ext 2>/dev/null
command -v rpicam-hello libcamera-hello
```

Missing commands are useful results. Include them in a bug report rather than installing random packages until the original environment is no longer reproducible.

## Raspberry Pi generations

### Pi Zero 2 W and Pi 3

These systems have little RAM and older Pi media blocks. A `v4l2h264enc` factory can exist while the driver rejects frames. Raspberry Ninja performs a small runtime probe and falls back to x264 when necessary. Keep resolution and frame rate low until the complete WebRTC path is stable.

### Pi 4

The V4L2 H.264 path is often useful, but camera or USB-capture buffers may negotiate differently from synthetic/system-memory buffers. Validate the actual source-to-encoder path. HDMI USB adapters also vary in advertised MJPEG/YUY2 modes and true delivery rate.

### Pi 5

Pi 5 does not provide the same H.264 hardware encoder path as Pi 3/4. `--rpi` detects Pi 5 and selects a software fallback. Do not make `v4l2h264enc` mandatory for all Raspberry Pi systems.

## Raspberry Pi camera stacks

Current Raspberry Pi OS uses `libcamera`; from Bookworm onward the camera applications are named `rpicam-*`. Older releases may provide `libcamera-*`, legacy plugins, or vendor images with `rpicamsrc`. Detect both the command-line tools and GStreamer source elements:

```bash
command -v rpicam-hello libcamera-hello
rpicam-hello --list-cameras 2>/dev/null || libcamera-hello --list-cameras 2>/dev/null
gst-inspect-1.0 rpicamsrc
gst-inspect-1.0 libcamerasrc
```

Use `--rpicam` only when `rpicamsrc` is present and its pipeline has been tested. Use `--libcamera --rpi` for the libcamera GStreamer path. Do not remove a working legacy path merely because a newer OS uses another name.

The guided setup checks both camera-tool names and prefers `libcamerasrc` when
available, including with `rpicam-hello`. The application rename does not imply
that the GStreamer source was renamed to `rpicamsrc`; that is a separate backend.

Official background: [Raspberry Pi camera software](https://www.raspberrypi.com/documentation/computers/camera_software.html).

## GStreamer version differences

Element names, caps, properties, request-pad APIs, and driver interaction vary by release. Known examples in Raspberry Ninja include:

- GStreamer 1.18 Python bindings use the legacy `get_request_pad` API in places where newer bindings offer `request_pad_simple`;
- asynchronous `splitmuxsink` must select `mpegtsmux` through `muxer-factory`, while synchronous variants use different properties;
- hardware JPEG decoders can be installed yet stall on real frames;
- decoder output memory may be incompatible with a software encoder without an explicit conversion to system memory.

The code uses compatibility helpers and frame probes for these cases. When adding a property, check it with `gst-inspect-1.0` before setting it unconditionally.

## NVIDIA Jetson

Jetson acceleration uses NVIDIA-specific elements such as `nvv4l2decoder`, encoders, converters, and NVMM buffers. Their availability and properties depend on JetPack/L4T, not just the GStreamer version. Keep NVIDIA paths isolated and preserve a software decoder fallback when memory conversion or the hardware decoder fails repeatedly.

See the [Jetson installer notes](../installers/nvidia_jetson/README.md). Those notes target specific JetPack generations; newer Jetsons should be inventoried and tested independently.

## Orange Pi and Rockchip

Orange Pi 5-class images may provide Rockchip MPP elements such as `mpph264enc`, `mpph265enc`, or `mppvp8enc`. Plugin naming, supported raw formats, bitrate property units, and kernel integration vary by image. Raspberry Ninja detects the Rockchip plugin and uses MPP-specific formats and controls only on that path.

See the [Orange Pi installer notes](../installers/orangepi/README.md). Treat their dated tested-image reference as a known baseline, not a requirement for every Orange Pi.

Rockchip format-priority detection checks bus metadata and the device name
independently; a missing bus-path property does not suppress name detection.
The MPP preference is applied only when the Rockchip MPP plugin is available.

## Source and encoder selection rules

Legacy GStreamer audio SDP repair preserves distinct audio sources and their
SSRC-group references. Replacement IDs avoid collisions with every existing
audio/video SSRC; video IDs are unchanged.

Camera mode matching uses GStreamer's native caps intersection for raw, JPEG,
and H.264 modes. Format lists, dimension ranges, fractional frame rates, and
hardware-memory features are matched as capabilities; compressed modes must
also support the requested dimensions and rate.

Pi camera auto-discovery runs only when a camera source still needs to be
selected. Explicit files, custom pipelines, pipe input, named camera backends,
and receive/audio-only modes bypass that discovery. A detected camera should
not change the encoder or source of an explicitly supplied pipeline.

On macOS, `--apple 0` selects AVFoundation device index 0. A nonnumeric value
such as `--apple "External Camera"` selects the first case-insensitive name
match. An unmatched name stops startup rather than opening the default camera.
Numeric index availability is checked by the native source when it opens.

AV1 publishing requires the `av1parse` and `rtpav1pay` elements plus an encoder.
`--av1` tries `qsvav1enc`, `av1enc`, then `rav1enc`, based on element availability.
`--qsv`, `--aom`, and `--rav1e` explicitly select their respective encoder and
report an error if it is missing. Adding `--av1` does not override that selection.
An installed plugin alone does not guarantee that it exposes the required
encoder on the current hardware; inspect the element with `gst-inspect-1.0`.

An explicit `--omx` request selects an available OMX encoder before automatic
H.264 detection (`avenc_h264_omx`, then `omxh264enc`). If neither is installed,
normal H.264 detection supplies the fallback. Selecting a plugin does not prove
that its hardware backend works; test it with frames on the target device.

Use this order when diagnosing or extending support:

1. Enumerate the real source modes with `v4l2-ctl` or the camera stack.
2. Select a source mode the device actually advertises.
3. Decode compressed capture formats before applying output rate/size conversion.
4. Probe hardware decoders and encoders with frames, not only `gst-inspect`.
5. Keep software encoders in system memory through `videoconvert` unless a tested platform path requires otherwise.
6. Fall back to a software codec and report the attempted backend and environment.
7. Test both a synthetic source and the native camera/capture path.

## Validation matrix

Document results as `pass`, `fail`, or `not tested`; do not turn an expectation into a pass. A useful matrix records:

| Field | Example |
| --- | --- |
| Board | Raspberry Pi 3 Model B Rev 1.2 |
| OS/architecture | Raspbian 11, armhf |
| Kernel/GStreamer | 6.1.21 / 1.18.4 |
| Source | USB HDMI MJPEG `/dev/video0` |
| Codec/backend | H.264 via x264 |
| Requested/received | 640x360 at 15/15 fps |
| Result | Browser playback pass; three-minute recording decoded |
| Resources | RSS, CPU, temperature, throttling, packet loss |

The dated [Pi 3 and Pi Zero 2 W test-bench record](../dev_notes/PI3_TESTBENCH_2026-08-02.md) is one example. It is evidence for those exact combinations, not the entire support matrix.
