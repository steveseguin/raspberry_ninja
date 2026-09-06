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

If startup reports `No usable H.264 encoder`, no backend was selected for raw
video. Check `gst-inspect-1.0 x264enc` and `gst-inspect-1.0 openh264enc`, then install
a supported encoder or choose an available codec. This can also happen after an
H.265 request falls back to H.264. Already-encoded passthrough inputs do not need
an extra encoder; the error applies when the app must encode raw frames.

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

Jetson automatic fallback identifies `nvv4l2decoder` errors from the message
source as well as diagnostic text, including custom-named decoder elements.
A recognized decoder error triggers fallback immediately; repeated warnings
use the existing warning threshold. Forced hardware decoding disables that
automatic fallback.

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

When testing a bitrate limit, check the negotiated codec and observed media rate
after the connection settles. The SDP bitrate hints apply to the selected video
track; audio and repair traffic can add to the total network rate. These hints
are requests to the peer, not a network traffic limiter. Lowering the video target
can help a constrained uplink, but cannot guarantee that every encoder or remote
publisher will honor the requested rate.

Reduce to one process and a conservative test source. On a Pi Zero 2 W start at 640x360, 10 fps, and 400 kbps:

```bash
watch -n 2 'free -h; ps -o pid,rss,%cpu,%mem,etime,cmd -C python3; vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null'
```

Disable audio while isolating video. Avoid VP9, multiple transcodes, a local desktop/browser, and package builds on a 512 MB device. Increasing bitrate does not repair Wi-Fi loss; use Ethernet where possible or improve signal quality.

## RTMP destination is rejected

Pass the RTMP URL as one command-line argument; normal shell quoting is fine.
The app escapes it for GStreamer's pipeline parser. Literal quote characters
must not surround the URL inside the sink's `location` value. If using an older
version that generated `rtmpsink location='...'`, update before investigating
server credentials or connectivity.

## File source reports an unexpected element name

Pass `--filesrc` or `--filesrc2` a single, shell-quoted filename. The app escapes
literal quotes and backslashes before constructing the GStreamer pipeline.
Older versions could interpret quotes inside a filename as pipeline syntax,
producing errors such as `no element` followed by part of the filename.

## Optional mode dependencies are missing

Framebuffer reception requires NumPy, MIDI mode requires `python-rtmidi`, and
Apple capture requires GStreamer's `applemedia` plugin. Missing requirements
stop startup with a nonzero exit status and a diagnostic on stderr. Install
Python dependencies for the interpreter used to launch the app; a package in
another virtual environment will not satisfy the requirement.

Receive-only modes such as `--view` need the negotiated codec's decoder and
depayloader, but do not require publishing encoders, RTP payloaders, or microphone
capture plugins. If an older receiver reports missing `vp9enc`, `rtpav1pay`, or
an H.264 encoder, update before installing unused publishing dependencies.

When legacy GStreamer emits phantom audio for a no-audio publisher, SDP cleanup
removes the audio section and its actual MID from BUNDLE groups. MID names do
not determine media type: numeric IDs and custom names are valid too.

## Still stuck

### Signaling disconnects during a network outage

Pending viewer retries are canceled when a new peer is created. A callback from
a canceled or replaced timer is ignored, so an old retry cannot clear the current
timer or start another retry cycle after cancellation.

After all handshake connection attempts fail, the app reports a connection error
and waits before retrying. An old closed socket is not reused for registration.
Existing peer connections may continue carrying media while signaling is down;
new viewers and renegotiation need signaling to recover. Check for both a fresh
successful connection and `WebSocket ready` in the log after connectivity returns.
Repeated connection errors call for checking the hostname, network route, and
certificate error shown in the log.

### RED/FEC is negotiated but video does not decode

Look for the `Viewer SDP: RED payload` message and its primary codec/payload
mapping. The viewer reads those mappings from the selected video section, not
another track. If the log reports `no usable primary payload`, inspect the sender's
RED format parameters and codec mappings; a RED payload alone does not identify
the video decoder. Include the negotiation log when reporting the problem.

The publisher also repairs offers that omit the primary video codec alongside
RED. That repair uses the first video section's payload mappings; following
audio or video tracks retain their own mappings even when payload IDs overlap.

### H.264 profile negotiation differs from the sender

The viewer detects the H.264 profile from the selected video media section.
Other tracks may reuse its RTP payload number, so their codec parameters must not
be treated as that video's profile. Explicit `--force-h264-profile` or
`--force-h264-profile-id` overrides apply to H.264 video parameters; audio and
other video codecs retain their own parameters. A forced profile still needs to
be compatible with the actual encoder and decoder.

Codec preference moves the selected codec's payloads to the front of the first
video media section while retaining their original profile order. It does not
borrow codec mappings from other tracks or remove alternative codecs from the
offer. A preference therefore does not guarantee which codec the peer negotiates.

### Saved configuration does not behave as expected

Use `python3 publish.py --config PATH` with the intended file. JSON numbers and
booleans should be native values such as `500` and `true`, not strings such as
`"500"` or `"true"`. Use destination names such as `video_pipeline` for keys;
incorrect boolean, numeric, or choice values produce an error naming the key
before media setup starts. Remove quotes around numbers and booleans, and choose
a supported value for options such as `ice_transport_policy` (`all` or `relay`).

Unrecognized keys are ignored, so check spelling against `publish.py --help` and
the [configuration guide](operations-guide.md#save-settings-in-a-json-configuration).

Command-line options take precedence. An explicit video-source option replaces
saved source flags, while other saved settings still apply. Editing JSON does
not reconfigure an already-running process: restart your chosen service after
validating the settings. A malformed file should produce a startup error; inspect
the service journal for the path and parser message.

### Reporting a problem

Open an issue with:

- the environment bundle;
- exact command and stream role;
- complete log from startup through failure;
- whether `--test` works;
- whether `RN_FORCE_SINK=fakesink` or `--disable-hw-decoder` changes the result;
- source modes from `v4l2-ctl`;
- a short reproducible test, without publishing real passwords or private stream IDs.

Community support is also available in the [VDO.Ninja Discord](https://discord.vdo.ninja).
