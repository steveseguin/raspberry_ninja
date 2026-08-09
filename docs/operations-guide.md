# Raspberry Ninja operations guide

This guide covers repeatable publisher and receiver operation after installation. For a memory-constrained Pi Zero 2 W, follow the [dedicated unattended guide](pi-zero-2-w-unattended-webrtc.md) first.

## Before every new hardware setup

Record what is actually installed:

```bash
cat /proc/device-tree/model 2>/dev/null; echo
cat /etc/os-release
uname -a
python3 --version
gst-launch-1.0 --version
gst-device-monitor-1.0 Video/Source Audio/Source
v4l2-ctl --list-devices 2>/dev/null
arecord -l 2>/dev/null
```

On Raspberry Pi, also check power and temperature:

```bash
vcgencmd get_throttled
vcgencmd measure_temp
```

Fix undervoltage before judging media stability. Do not copy a pipeline from another board solely because both machines are called Raspberry Pi.

## Prove signaling with test sources

Start with no physical media devices:

```bash
python3 -u publish.py \
  --test --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-test \
  --password false
```

View it in a browser:

```text
https://vdo.ninja/?view=rn-test&password=false
```

Expected milestones in the publisher log are WebSocket readiness, an SDP answer, ICE connected, and non-zero bitrate. A local preview alone does not prove that a remote peer received media.

Test VP8 separately because it selects a different encoder path:

```bash
python3 -u publish.py \
  --test --vp8 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-vp8-test \
  --password false
```

VP9 is software-heavy on small boards. Validate it at a low resolution before increasing load.

## Publish a USB camera or HDMI capture device

List devices and the modes of the intended capture node:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Use a stable path under `/dev/v4l/by-id/` when one exists. Start conservatively:

```bash
python3 -u publish.py \
  --v4l2 /dev/video0 --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-camera \
  --password false
```

Add `--rpi` on a Raspberry Pi to enable Pi-specific selection and probing. The selected hardware encoder may still fall back to software when its runtime frame probe fails. This is expected and is safer than selecting an element based only on its presence.

Many inexpensive HDMI adapters advertise MJPEG at a fixed source rate and reject a different rate on `v4l2src`. Raspberry Ninja constrains the source only when the requested mode is advertised, then can apply the requested rate after decode. Capture the full generated pipeline when reporting negotiation trouble.

## Add audio

Identify and test the input independently:

```bash
arecord -l
arecord -D hw:CARD,DEVICE -f S16_LE -r 48000 -c 2 -d 5 /tmp/rn-audio.wav
aplay /tmp/rn-audio.wav
```

Then add the selected ALSA input to the working video command:

```bash
python3 -u publish.py ... --alsa hw:CARD,DEVICE
```

Card numbers can change after reboot or when USB devices are reconnected. Prefer a stable ALSA name when available.

## Run a receiver

Validate signaling and decoding without a physical display:

```bash
RN_FORCE_SINK=fakesink python3 -u publish.py \
  --view rn-receiver \
  --password false \
  --noaudio
```

Publish into it from Chrome:

```text
https://vdo.ninja/?push=rn-receiver&password=false&h264
```

For an attached HDMI display, remove `RN_FORCE_SINK`:

```bash
unset DISPLAY WAYLAND_DISPLAY
python3 -u publish.py \
  --view rn-receiver \
  --password false
```

Do not add `--framebuffer /dev/fb0`; that option is the raw-frame shared-memory mode, not HDMI output. If SSH has set `DISPLAY` to a value such as `localhost:10.0`, unset it as above so an X11-forwarded OpenGL window cannot replace the Pi's local KMS output.

The default preserves aspect ratio on whatever mode the display advertises. Add `--stretch-display` only when intentional fill-to-screen distortion is preferable to black bars.

The receiver remains available while the sender is absent. Automatic retry defaults to a short sequence followed by a longer interval. Use `--no-auto-retry` only for a supervised diagnostic run.

## Run unattended with systemd

First prove the exact command interactively. Then use `tools/install_unattended.py` to create a validated receiver or sender unit whose user and working directory match the installed clone. Complete examples are in the [Pi Zero 2 W guide](pi-zero-2-w-unattended-webrtc.md#8-make-the-receiver-start-on-boot).

Useful service commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now raspberry-ninja-viewer.service
systemctl status raspberry-ninja-viewer.service --no-pager
journalctl -u raspberry-ninja-viewer.service -f
```

The helper uses `Restart=always`, a small `RestartSec`, unbuffered Python output, and `network-online.target`. It stores credentials in a restricted JSON config instead of the unit command. Running the installer again validates the replacement unit and restarts the existing service so new settings take effect.

## Conservative performance profiles

These are starting points, not guaranteed limits:

| System | Initial profile | Notes |
| --- | --- | --- |
| Pi Zero 2 W | 640x360, 10-15 fps, 400-500 kbps | One process; Lite OS; avoid VP9 and parallel builds |
| Pi 3 | 640x360, 15 fps, 500-1000 kbps | Probe V4L2; software H.264/VP8 may be the reliable path |
| Pi 4 | 1280x720, 15-30 fps, 1000-2500 kbps | Validate capture mode, encoder, and audio sync before 1080p |
| Pi 5 | 1280x720, 15-30 fps, software encoder | No Pi 3/4-style H.264 hardware encoder; watch CPU and temperature |
| Jetson | 1280x720, 30 fps | NVIDIA plugins and NVMM behavior depend on JetPack/L4T |
| Orange Pi/Rockchip | 640x360 or 1280x720 | MPP plugin names and caps depend on image and kernel |

Increase one dimension at a time: resolution, then frame rate, then bitrate, then audio. Record CPU, resident memory, temperature, throttling, actual received frame rate, and packet loss at each step.

## Stability checks

Run at least a short sender-off/sender-on recovery test and a longer steady-state soak before unattended deployment:

```bash
watch -n 2 'free -h; ps -o pid,rss,%cpu,%mem,etime,cmd -C python3; vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null'
```

During a soak, confirm:

- received frame rate matches the request;
- bitrate settles near the target instead of remaining at zero;
- packet loss does not continually increase;
- RSS and swap do not grow without bound;
- temperature and throttling remain acceptable;
- receiver returns to idle and reconnects after the sender restarts;
- a saved test recording can be decoded, not merely created.

See [Troubleshooting](troubleshooting.md) for diagnostic commands and [Recording](recording-guide.md) for file validation.
For a repeatable deployment gate, use the [unattended validation checklist](unattended-validation-checklist.md).
