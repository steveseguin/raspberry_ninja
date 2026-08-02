# Raspberry Pi 3 test bench — 2026-08-02

## Host

- Raspberry Pi 3 Model B Rev 1.2
- Raspbian GNU/Linux 11 (bullseye), 32-bit ARM
- Linux 6.1.21-v7+
- GStreamer 1.18.4
- 870 MiB usable RAM, 128 MiB GPU memory
- Ethernet: `10.0.0.12`
- Wi-Fi: `10.0.0.21`

The current workspace was deployed to `/home/pi/raspberry_ninja`. The previous clean checkout is preserved at `/home/pi/raspberry_ninja.pre-bench-20260802-a73ffaa`.

## Encoder results

| Path | Result | Notes |
| --- | --- | --- |
| Raspberry Ninja x264/H.264 | Pass | Browser received 640×360 at 15 fps; approximately 57% process CPU, 51.5°C |
| Raspberry Ninja VP8 | Pass | Browser received 640×360 at 15 fps; approximately 70% process CPU, 54.2°C |
| FFmpeg `h264_v4l2m2m` | Pass | Hardware encoder `/dev/video11` produced H.264 successfully |
| GStreamer `v4l2h264enc` | Fail | `bcm2835-codec` rejects stream start with `Failed enabling i/p port, ret -3` |
| FFmpeg `h264_omx` | Unavailable | Legacy OMX libraries are not installed |

No thermal throttling was reported during the WebRTC tests.

GStreamer hardware H.264 was tried at 320×240, 640×360, and 1280×720; with I420 and NV12; with `videoconvert` and `v4l2convert`; and with the supported V4L2 I/O modes. All variants failed, while FFmpeg's V4L2 M2M path worked. This isolates the current limitation to the installed GStreamer/driver integration rather than missing encoder hardware.

## Signaling finding

Passing an official handshake server explicitly previously generated and overwrote `puuid`, causing incoming viewer requests to be discarded as `PUUID NOT SAME`. A regression fix now treats the primary and backup VDO.Ninja handshake servers as official while retaining generated UUID behavior for custom servers and preserving an explicitly supplied `--puuid`.

The fixed explicit-server path was verified end to end against `wss://wss.vdo.ninja:443`: a normal browser viewer received 640×360 H.264 video, the publisher received an SDP answer, and no `PUUID NOT SAME` rejection occurred. At the measurement point, the publisher used approximately 18% process CPU, the Pi reported 52.1°C, and thermal throttling remained clear.

## Regression checks

- Remote Python compile check: pass
- Focused unit tests: 16 passed
- Browser WebRTC playback: x264/H.264 pass, VP8 pass, explicit-server H.264 pass
