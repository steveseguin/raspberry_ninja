# Troubleshooting Raspberry Ninja

Start with the first error, not the final cascade. Preserve the complete command and generated GStreamer pipeline before changing packages or settings.

## Collect an environment bundle

Run this on the affected device:

```bash
date -Is
cat /proc/device-tree/model 2>/dev/null; echo
cat /etc/os-release
uname -a
python3 --version
gst-launch-1.0 --version
free -h
df -h /
gst-device-monitor-1.0 Video/Source Audio/Source
v4l2-ctl --list-devices 2>/dev/null
arecord -l 2>/dev/null
command -v rpicam-hello libcamera-hello
vcgencmd get_throttled 2>/dev/null
vcgencmd measure_temp 2>/dev/null
```

Also include the relevant element details:

```bash
gst-inspect-1.0 webrtcbin
gst-inspect-1.0 v4l2h264enc
gst-inspect-1.0 x264enc
```

## Cannot find or SSH to a Pi

Try its configured hostname first:

```powershell
ping HOSTNAME.local
ssh USER@HOSTNAME.local
arp -a
```

Then check the router's DHCP client list. Confirm that the image customization enabled SSH and used the correct 2.4 GHz Wi-Fi SSID/country. A service responding on DNS or HTTP does not imply that SSH is enabled.

Repeated disappearance during package installation or encoding often indicates weak power. Use a suitable supply and cable, then check `vcgencmd get_throttled` after reboot.

## Installation stops or the Pi becomes unresponsive

On low-memory boards use:

```bash
sudo -v
bash install.sh --non-interactive --runtime-only --skip-system-upgrade
```

Do not run another package manager while `apt` or `dpkg` is active. After an interrupted boot, inspect rather than immediately deleting locks:

```bash
ps aux | grep -E '[a]pt|[d]pkg'
sudo dpkg --audit
sudo dpkg --configure -a
```

## Signaling connects but bitrate stays at zero

Confirm that publisher and viewer use the identical stream ID and password mode. With `--password false`, both browser and command must explicitly use `password=false`.

Look for all of these milestones:

- incoming viewer request or offer;
- SDP answer;
- ICE connected;
- media RTP pad;
- non-zero bitrate.

Test with `--test --noaudio` to separate signaling/encoding from the physical camera. If the test source works, return to the camera and inspect its modes.

## Signaling TLS or certificate errors

Secure `wss://` signaling verifies the server certificate and hostname by default. Fix an expired certificate, missing CA bundle, incorrect device clock, or wrong hostname instead of disabling verification.

For a trusted legacy/custom server only, `--insecure-signaling` additionally permits unverified TLS and a plaintext `ws://` fallback. This exposes signaling metadata and must not be used as a routine Internet-facing configuration. An explicitly supplied `ws://` URL remains plaintext by design.

## `not-negotiated` from a V4L2 source

The requested format, size, or frame rate is not accepted by the device or the next element:

```bash
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Choose an advertised mode. Some HDMI capture devices advertise only a high MJPEG rate even when their real delivery rate is lower. Do not force an unadvertised rate directly on `v4l2src`; apply rate conversion after JPEG decode.

If hardware JPEG decode stalls, test software decode. Capture `gst-inspect-1.0 v4l2jpegdec` and the full error; plugin presence alone is not proof that its driver works.

## Hardware H.264 encoder exists but fails

Raspberry Ninja probes `v4l2h264enc` with frames and normally falls back to x264. To confirm the fallback:

```bash
RN_DISABLE_V4L2_ENCODER=1 python3 -u publish.py ...
```

Only bypass the probe for a known-good native/zero-copy path:

```bash
RN_FORCE_V4L2_ENCODER=1 python3 -u publish.py ...
```

Forcing a failed encoder can hang or repeatedly restart a low-memory device. Pi 5 uses a software encoder because it does not expose the Pi 3/4 hardware H.264 path.

## Receiver works headlessly but not on HDMI

Prove receive/decode first:

```bash
RN_FORCE_SINK=fakesink python3 -u publish.py --view STREAM_ID --password false --noaudio
```

Then inspect the physical connector and sinks:

```bash
for status in /sys/class/drm/card*-HDMI-A-*/status; do echo "$status: $(cat "$status")"; done
kmsprint -m 2>/dev/null || true
gst-inspect-1.0 kmssink
aplay -l
```

Boot with the display connected when its EDID is needed. Remove `RN_FORCE_SINK` for the real test. If video works and audio does not, test the selected HDMI ALSA device independently; card numbers are not portable between systems.

For Raspberry Pi HDMI receiver mode, use `--view STREAM_ID`; do not add `--framebuffer /dev/fb0`. `--framebuffer` is the raw-frame shared-memory mode and does not select HDMI. Modern KMS images may not expose `/dev/fb0`.

If video opens in an OpenGL window on the computer running SSH, the session is probably forwarding X11. Check `echo "$DISPLAY"`; a value like `localhost:10.0` is forwarded. Run `unset DISPLAY WAYLAND_DISPLAY` and restart the receiver. With HDMI connected, Raspberry Ninja will prefer `kmssink` for direct Pi output.

## Decoder instability

Force software decoding to distinguish a hardware decoder or memory-conversion problem:

```bash
python3 -u publish.py --view STREAM_ID --disable-hw-decoder ...
```

Jetson, Rockchip, and Pi decoders use different elements and memory types. Report the actual selected decoder and conversion path.

## Receiver does not recover after sender restart

Do not use `--no-auto-retry`. Watch the complete lifecycle:

```bash
journalctl -u raspberry-ninja-viewer.service -f
```

The receiver should tear down the stale peer, return to idle, issue another play request, and activate remote output when the sender returns. If it does not, include timestamps and both sender and receiver logs.

## Recording is empty, corrupt, or mislabeled

Stop the process gracefully so muxers can finalize. Check the real container and decode it:

```bash
gst-typefind-1.0 FILE
ffprobe -hide_banner FILE
gst-launch-1.0 -q filesrc location=FILE ! decodebin ! fakesink
```

For HLS use `--hls --hls-splitmux`. On GStreamer 1.18 the older manual backend has produced empty segments. Verify that the playlist references existing segments and that `.ts` files type-find as MPEG-TS.

See the [recording guide](recording-guide.md) for expected codec/container combinations.

## Memory, swap, temperature, or packet loss grows

Reduce to one process and a conservative test source. On a Pi Zero 2 W start at 640x360, 10 fps, and 400 kbps:

```bash
watch -n 2 'free -h; ps -o pid,rss,%cpu,%mem,etime,cmd -C python3; vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null'
```

Disable audio while isolating video. Avoid VP9, multiple transcodes, a local desktop/browser, and package builds on a 512 MB device. Increasing bitrate does not repair Wi-Fi loss; use Ethernet where possible or improve signal quality.

## Still stuck

Open an issue with:

- the environment bundle;
- exact command and stream role;
- complete log from startup through failure;
- whether `--test` works;
- whether `RN_FORCE_SINK=fakesink` or `--disable-hw-decoder` changes the result;
- source modes from `v4l2-ctl`;
- a short reproducible test, without publishing real passwords or private stream IDs.

Community support is also available in the [VDO.Ninja Discord](https://discord.vdo.ninja).
