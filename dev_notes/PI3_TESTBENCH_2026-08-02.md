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
- Original focused unit tests: 16 passed
- Final full suites: 46 passed on Pi 3, 46 passed on Zero 2 W, and 46 passed in WSL
- Browser WebRTC playback: x264/H.264 pass, VP8 pass, explicit-server H.264 pass

## Multi-device follow-up

The same checkout was also exercised on a Raspberry Pi Zero 2 W running
32-bit Raspberry Pi OS 13 (Trixie), Linux 6.18.39, GStreamer 1.26.2, and
Python 3.13.5. The Zero has 424 MiB usable RAM. A third Pi running Pi-hole was
identified at `10.0.0.175`/`10.0.0.176`, but SSH is disabled there, so it was
limited to network-service inventory.

### Physical HDMI capture

The Pi 3 USB HDMI adapter exposes MJPEG at 1280x720@120, 640x400@210, and
640x360@210 in `v4l2-ctl`, although 100 frames actually arrived in about 4.4
seconds. Forcing the requested 15 or 25 fps on `v4l2src` failed with
`not-negotiated`. The capture path now constrains only advertised source modes
and applies the requested rate after JPEG decoding.

`v4l2jpegdec` also timed out on both adapter and synthetic JPEG input, so the
new runtime frame probe selects `jpegdec` on this host. Software encoders now
stay in system memory through `videoconvert`; routing them through
`v4l2convert` caused another negotiation failure.

End-to-end physical tests at 640x360@15 passed:

| Publisher | Receiver/recording | Result |
| --- | --- | --- |
| Pi 3 HDMI capture, x264/H.264 | Zero 2 W, direct MPEG-TS | Pass; H.264 decode exit 0 |
| Pi 3 HDMI capture, VP8 | Zero 2 W, direct WebM | Pass; WebM decode exit 0 |

The Pi 3 remained unthrottled at 45.6-48.9 C. The Zero remained unthrottled at
40.8-41.9 C.

### Headless viewer

The Zero received VP8 through `RN_FORCE_SINK=fakesink`, activated the remote
display branch, reported 0% post-repair loss, and returned to the idle branch
after the sender stopped. Its automatic recovery path tore down the stale peer
and re-issued the play request. Memory use during the test was 121 MiB.

### Recording and HLS

- Direct VP8 WebM, H.264 MPEG-TS, and Opus WebM recordings all decoded.
- Combined H.264 plus Opus input was converted to H.264 plus AAC HLS on the Pi
  3 using `--hls-splitmux`.
- GStreamer 1.18 requires `get_request_pad`; newer bindings offer
  `request_pad_simple`. Both are now supported.
- With asynchronous splitmux finalization, `muxer` is ignored and the default
  MP4 muxer was previously used inside files named `.ts`. The code now selects
  `mpegtsmux` through `muxer-factory`, with a capability-detected synchronous
  fallback. The completed segment type-found as MPEG-TS, and both H.264 and AAC
  branches decoded with exit 0.
- The legacy manual HLS backend still produced empty segments on this
  GStreamer 1.18 host. It remains available for compatibility; splitmux is the
  validated backend here.

### Three-minute Zero 2 W soak

The Zero published a 640x360@10 H.264 test source with Opus at a 400 kbps video
target to the Pi 3 subprocess recorder.

- Receiver processed about 1,800 video buffers over 180 seconds: the requested
  10 fps.
- Sender reported 388-389 kbps steady-state. Raw loss was initially 0%; one
  sample reached 0.78% without a disconnect.
- Zero process RSS stabilized near 81 MiB. Total used memory stabilized at
  158-161 MiB and returned to 122 MiB after exit.
- Zero temperature stayed between 38.6 and 40.8 C; Pi 3 stayed between 45.1 and
  47.2 C. Both reported `throttled=0x0` throughout.
- The final H.264 MPEG-TS and Opus WebM recordings both decoded with exit 0.
