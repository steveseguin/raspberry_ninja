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

## Multiple viewers and stalled connections

Use `--multiviewer` to share one encoded stream with multiple viewers. Each
viewer has bounded audio and video queues. If one viewer stops accepting media,
its queues drop old packets when full so the other viewers can keep receiving.
The affected viewer may have audio gaps or need the next video keyframe when it
recovers. This does not increase the publisher's available upload bandwidth;
choose a bitrate that leaves room for all viewers.

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

For an attached HDMI display on a console-only system (no running graphical desktop), remove `RN_FORCE_SINK`:

```bash
unset DISPLAY WAYLAND_DISPLAY
python3 -u publish.py \
  --view rn-receiver \
  --password false
```

Do not add `--framebuffer /dev/fb0`; that option is the raw-frame shared-memory mode, not HDMI output. If SSH has set `DISPLAY` to a value such as `localhost:10.0`, unset it as above so an X11-forwarded OpenGL window cannot replace the Pi's local KMS output.

If a desktop is already running on the Pi, use its display session instead. Direct KMS output can fail because the desktop owns the display. See [desktop playback over SSH](troubleshooting.md#desktop-playback-over-ssh) for a Wayland example.

The default preserves aspect ratio on whatever mode the display advertises. Add `--stretch-display` only when intentional fill-to-screen distortion is preferable to black bars.

The receiver remains available while the sender is absent. Automatic retry defaults to a short sequence followed by a longer interval. Use `--no-auto-retry` only for a supervised diagnostic run.

After a detected disconnect, `--viewer-retry-initial` waits 15 seconds by default
before the first play request. The next request waits `--viewer-retry-short`
(45 seconds), and later requests use `--viewer-retry-long` (180 seconds).
Set `--viewer-retry-initial 0` for an immediate first retry. These intervals govern
viewer play requests, separately from reconnecting to the signaling server.
If a request cannot be scheduled because the signaling loop is unavailable, it
does not advance the retry count; another attempt is scheduled after the long
delay. Successful peer creation resets the retry sequence.

## Save settings in a JSON configuration

Create `sender.json` with JSON booleans and numbers (without quotes):

```json
{
  "streamid": "my-camera",
  "password": "replace-with-your-shared-password",
  "test": true,
  "h264": true,
  "noaudio": true,
  "width": 640,
  "height": 360,
  "framerate": 15,
  "bitrate": 500
}
```

Run `python3 publish.py --config sender.json`. Use the same stream ID and
password in the viewer. Protect files containing passwords with
`chmod 600 sender.json`; do not post them in bug reports.

Keys normally use argument destination names: `streamid`, `noaudio`, and
`video_pipeline`, for example. Installer-style `stream_id` is also accepted.
If both names are present, `streamid` takes precedence over `stream_id` regardless
of JSON key order. Likewise, `noaudio` takes precedence over legacy
`audio_enabled`. Explicit command-line options still take precedence over the file.
Legacy `video_source` accepts `test`, `libcamera`, `v4l2`, or `custom`.
`custom` requires a non-empty `custom_video_pipeline`; `v4l2` uses `/dev/video0`
when `video_device` is omitted, but rejects an explicitly empty or null device.
Invalid source selections stop startup instead of silently falling back to a camera.
Save as UTF-8; files with a UTF-8 byte-order mark are supported. A missing file,
invalid JSON, or a root value other than an object stops startup with an error.
Boolean flags require `true` or `false`; integer settings such as `bitrate`
require integers; floating-point settings require finite numbers. Numeric strings
such as `"500"` and boolean strings such as `"false"` are rejected rather than
interpreted as flags or passed into media setup. Options with a fixed set of
choices, such as `ice_transport_policy`, use the same choices as the CLI.
Text settings, including stream IDs, passwords, device paths, and custom
pipelines, require JSON strings. To disable the password, use `"password": "false"`
(a string); `"noaudio": false` is a boolean flag. Optional text settings whose
default is unset also accept `null`.

Explicit command-line values override saved settings, even if the value equals
the built-in default. For example, `--config sender.json --bitrate 2500` uses
2500 kbps. Unique long-option abbreviations follow the same rule, but use full
option names in scripts so future options cannot make an abbreviation ambiguous.

An explicit codec or encoder flag also replaces saved codec-selection flags.
For example, `--config sender.json --x264` selects H.264 even if the file enables
VP8 or AV1. Other saved settings, including bitrate and platform hints, still
apply. Without an explicit codec flag, the saved codec selection is used.

Likewise, `--alsa`, `--pulse`, `--audio-pipeline`, or `--noaudio` replaces saved
audio-source and audio-enable settings. For example, an explicit `--alsa DEVICE`
enables that source even if the file contains `"noaudio": true`. Saved audio
bitrate and other unrelated options still apply.

Choosing a video source on the command line also suppresses saved video-source
flags. For example, `--config sender.json --v4l2 /dev/video2` replaces the saved
test source with that camera. Conversely, `--test` replaces a saved camera source.
Other settings, including resolution, codec, bitrate, and password, still apply;
ensure they are suitable for the replacement source. This changes only the current
invocation, not the JSON file or an already-running service.

## Run unattended with systemd

For a portable Pi with a UVC camera, use a stable `/dev/v4l/by-id/` capture
path and validate its advertised formats before installing the service. Start
with 640x360 at 15 fps and 500 kbps, then tune against the actual uplink and
encoder load. Audio and transport overhead also need upload capacity.
If a selected `by-id` or `by-path` camera disappears, startup fails and the
service retries that selection. It does not substitute another camera.

The asyncio runtime services GLib events so media bus errors and queued decoder
fallbacks are delivered. Unhandled terminal media errors log the failing element and GStreamer
details, then exit with status 1. Shutdown has an independent eight-second
deadline in case a camera driver blocks during cleanup. Existing Jetson decoder
and display fallback handlers still run first. A direct CLI invocation exits;
automatic process recovery requires a supervisor such as the service below.
This detects reported media errors, not every possible silent camera freeze.

First prove the exact command interactively. Then use `tools/install_unattended.py` to create a validated receiver or sender unit whose user and working directory match the installed clone. Complete examples are in the [Pi Zero 2 W guide](pi-zero-2-w-unattended-webrtc.md#8-make-the-receiver-start-on-boot).

Useful service commands:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now raspberry-ninja-viewer.service
systemctl status raspberry-ninja-viewer.service --no-pager
journalctl -u raspberry-ninja-viewer.service -f
```

The helper uses `Restart=always`, a small `RestartSec`, unbuffered Python output, and `network-online.target`. It stores credentials in a restricted JSON config instead of the unit command. Running the installer again validates the replacement unit and restarts the existing service so new settings take effect.

Newly generated units retry every five seconds without a start-rate limit, so
a camera missing for several minutes does not permanently disable the service.
Reinstall an existing unit to apply this policy. Retries also continue for
configuration errors; inspect the journal and stop the service while correcting
them. Ordinary signaling reconnection continues inside the running application.

For USB camera/microphone recovery, select the camera under `/dev/v4l/by-id/`
and pass the microphone's `/dev/snd/by-id/` symlink to `--audio-device` (installer)
or `--alsa` (publisher). `/dev/v4l/by-path/` and `/dev/snd/by-path/` select a port
instead. The publisher resolves the sound-card symlink on every launch and new capture pipeline, opening
PCM device zero of that card even if its numeric card index has changed. A missing
explicit microphone is a startup error; the service retries instead of disabling
audio or selecting another microphone. Existing ALSA names remain supported;
use one when the required PCM device is not zero. Automatic audio discovery can
still disable audio when no mic is present, so use an explicit device unattended.

The WebRTC publisher monitors buffers from `v4l2src`, `alsasrc`, and `pulsesrc`.
If an active capture source produces no buffers for 30 seconds, it exits for
supervised recovery. `--capture-timeout SECONDS` adjusts the timeout (`0` disables
it). This also covers a source that never produces its first buffer. Paused/idle
pipelines do not expire, and quiet audio still counts as healthy capture when
buffers continue. Other camera backends retain their existing behavior. Capture
failure restarts the whole publisher, so removing the mic can also interrupt video.
This requires a service supervisor; the standalone script does not relaunch itself.

`--service-name` accepts up to 247 letters, digits, underscores, dots, hyphens,
or `@` characters before the generated `.service` suffix. It must not start with
`-` or `@`. Use a concrete instance such as `camera@front`, rather than `camera@`.

For senders, omit `--audio-device` to disable audio; an empty value is invalid.
`--camera` requires a non-empty device path. `--allow-missing-device` permits an
unplugged device but does not allow an empty path or a directory.

Configuration writes use a private temporary file in the destination directory,
then replace the destination after setting its permissions and ownership. The shared
config directory is root-owned with mode `0711` (traversal without listing), and
each config uses mode `0640` with its service user's group. Installing another
service under a different user therefore preserves access to existing configs. If that
write fails, the temporary file is removed and the previous destination remains
intact. This protects the file update; it does not guarantee that newly selected
camera or network settings will work. Check the service status and journal after
each reconfiguration. `--dry-run` prints the proposed configuration, including its
password, so keep that output private.

If writing or verifying the generated files fails before systemd is reloaded,
the installer restores replaced files atomically, including their previous
permissions and ownership, and restores the config directory's metadata.
An incomplete rollback is reported explicitly. This rollback does not cover
failures during the later service reload, enable, or restart steps.

Relative `--python` and `--camera` paths become absolute from the installer's working
directory without resolving virtual-environment or stable device symlinks. The generated service treats paths
literally, including spaces, percent signs, and dollar signs. Paths containing line breaks or NUL
bytes are rejected. Use `--dry-run` to inspect paths before installation.

## Record while publishing to RTMP

For RTMP publishing, `--save` also writes a local timestamped `.mkv` recording.
The RTMP output stays connected to its muxer even if `--multiviewer` is present;
that flag's dynamic viewer branches apply to WebRTC publishing. Verify recording
output and available disk space before leaving a sender unattended.

For a V4L2 camera that advertises H.264, `--v4l2 /dev/videoN --format H264`
can send the camera's encoded video directly to RTMP without decoding and
re-encoding. RTMP receives parsed H.264; WebRTC uses RTP packetization.
Confirm the camera's advertised modes with `v4l2-ctl --list-formats-ext`.

RTMP audio is converted and resampled to 48 kHz mono before AAC encoding, so a
44.1 kHz source can be used. A custom `--audio-pipeline` supplies its own source
and does not require a detected microphone; `--noaudio` still disables audio.

Automatic audio selection uses devices that advertise an ALSA card, preferring
a valid default device. If none is found, audio is disabled with a diagnostic.
Use `--alsa DEVICE` or `--pulse DEVICE` when the desired source is not represented
by an ALSA card in device discovery; these explicit selections bypass discovery.
Pass a device name containing spaces as one shell-quoted argument. The app
preserves the name when constructing the ALSA or PulseAudio source, including
literal quotes and backslashes; do not add GStreamer property syntax yourself.

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

For mobile connections, peer negotiation is limited to 60 seconds by default.
A stalled attempt is released so the viewer's existing reconnect schedule can
request a fresh connection. Use `--peer-connect-timeout SECONDS` to adjust this
window (`0` disables it). Established connections are not expired by this timer.

To exercise relay-only operation, configure `--ice-transport-policy relay` and
`--turn-server` (or the equivalent configuration-file keys). Startup rejects
missing or invalid TURN configuration, and applying the relay policy must succeed
before ICE servers are configured. TURN credentials are hidden in setup logs.
Test both signaling reconnection and actual TURN transport outages: a working
WebSocket alone does not demonstrate that video has recovered.

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

## Serving existing HLS files

To serve an existing playlist and its segments locally:

```bash
python3 tools/serve_hls.py --directory /path/to/hls --bind 127.0.0.1 --port 8089
```

Open the playlist at `http://127.0.0.1:8089/PLAYLIST.m3u8` in an HLS-compatible
player. The helper serves files; it does not generate the stream. It supports
concurrent requests and CORS preflight. Playlist responses disable caching so live
updates remain visible even when the playlist changes within one second.
Without options it serves the repository
root on port 8089 on all interfaces. Use `--directory` to select the files to expose
and `--bind` to choose the listening address. Stop with Ctrl+C.
