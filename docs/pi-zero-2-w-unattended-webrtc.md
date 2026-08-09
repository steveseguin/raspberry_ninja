# Raspberry Pi Zero 2 W unattended VDO.Ninja sender/receiver

See the [documentation index](README.md) for recording, cross-platform compatibility, and general troubleshooting guides.

This guide sets up a Raspberry Pi Zero 2 W as either:

- an unattended HDMI receiver that waits for a fixed VDO.Ninja stream ID; or
- a low-resolution sender using a USB/CSI camera or a test source; or
- a carefully tested two-way endpoint using separate receive and return stream IDs.

The receiver may remain on continuously. When a sender starts using the matching stream ID, Raspberry Ninja reconnects and displays the stream. The same receiver works with either another Raspberry Pi sender or a normal VDO.Ninja browser publisher.

## Tested baseline

This procedure was most recently tested on August 9, 2026 with:

- Raspberry Pi Zero 2 W Rev 1.0
- Raspberry Pi OS Lite 32-bit, Debian/Raspbian 13 Trixie
- Linux `6.18.39+rpt-rpi-v7`
- GStreamer 1.26.2
- Python 3.13.5
- an 8 GB microSD card
- 424 MiB usable RAM and 423 MiB swap
- a directly connected 1920x1200 HDMI monitor
- a powered USB hub and Logitech C920 webcam/microphone
- a Pi 3 running Raspberry Pi OS Bullseye and GStreamer 1.18.4 as a second native endpoint
- current Chrome as the browser endpoint

The following paths were tested over VDO.Ninja:

- Pi 3 test source to the Zero's physical HDMI output: H.264, 640x360 at 15 fps, about 520 kbps, with 0% reported loss
- sender stop/start recovery: the Zero returned to its idle display and automatically reconnected
- Zero C920 to Chrome: native H.264 plus Opus, 1280x720 at 15 fps, about 3.4 Mbps, with 0% reported loss
- simultaneous HDMI receive and native C920/Opus return: about 104 MiB plus 94 MiB RSS, 134-148 MiB available, 8 MiB swap, 49 C, and no throttling
- systemd crash recovery and reconfiguration, including rejection of malformed configuration

The simultaneous result is a proof of this exact powered C920/native-H.264 setup, not a general promise that two software encoders will fit on a Zero 2 W. A Pi 4 or Pi 5 remains the safer two-way and 24/7 choice. The attached monitor's 1920x1200 mode also confirmed that the receiver does not assume every display is 1920x1080.

The broader v17 test bench also validated three-minute H.264/Opus operation on this Zero 2 W, direct H.264 and VP8 recordings, automatic receiver recovery, and clean decoding on a second Raspberry Pi. Those results apply to the exact baseline above; they do not prove every Raspberry Pi OS or GStreamer combination.

## 1. Image the card

Download the official Raspberry Pi Imager:

- [Raspberry Pi Imager download page](https://www.raspberrypi.com/software/)
- [Windows installer](https://downloads.raspberrypi.com/imager/imager_latest.exe)
- [macOS installer](https://downloads.raspberrypi.com/imager/imager_latest.dmg)
- [Linux x86_64 AppImage](https://downloads.raspberrypi.com/imager/imager_latest_amd64.AppImage)
- [Official OS imaging instructions](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Raspberry Pi OS image/download information](https://www.raspberrypi.com/software/operating-systems/)

In Raspberry Pi Imager:

1. Choose **Raspberry Pi Zero 2 W** as the device.
2. Choose **Raspberry Pi OS Lite (32-bit)**.
3. Choose the microSD card.
4. Open customisation and set:
   - a hostname, such as `pi02w`;
   - a username and a strong password;
   - the 2.4 GHz Wi-Fi network and country;
   - the correct timezone;
   - SSH enabled with password authentication, or preferably an SSH public key.
5. Write and verify the card.

Use the current non-legacy Lite 32-bit image. The 32-bit Lite image has the smallest practical RAM and disk footprint on a 512 MB Zero 2 W. A desktop image is unnecessary for a headless receiver. Use a legacy image only for hardware that has a confirmed incompatibility with the current camera/media stack.

Use a stable 5 V power supply and a good cable. Package installation and video encoding are sensitive to weak power.

## 2. Find the Pi and connect

Allow one or two minutes for the first boot. From Windows PowerShell, try:

```powershell
ping pi02w.local
ssh YOUR_USER@pi02w.local
```

If mDNS does not resolve, find the address in the router's DHCP client list. `arp -a` can also help after another device has contacted the Pi.

After logging in, record the current environment:

```bash
hostname -I
cat /proc/device-tree/model; echo
cat /etc/os-release
uname -a
free -h
df -h /
vcgencmd get_throttled
vcgencmd measure_temp
```

`throttled=0x0` means no current or historical undervoltage/throttling has been recorded since boot. Correct any power problem before continuing.

## 3. Install the low-memory runtime

Authorize `sudo` interactively first. This matters on current Raspberry Pi OS when an installer is launched through SSH without a controlling terminal.

```bash
sudo -v
cd "$HOME"
git clone --depth 1 https://github.com/steveseguin/raspberry_ninja.git
cd raspberry_ninja
bash install.sh --non-interactive --runtime-only --skip-system-upgrade
```

The two low-memory flags are intentional:

- `--runtime-only` omits development headers and desktop-only GStreamer packages.
- `--skip-system-upgrade` refreshes package indexes but does not perform an unrelated full OS/kernel upgrade during deployment.

Perform normal OS maintenance separately, with stable power and time to let `dpkg` finish. Never interrupt an active `apt` or `dpkg` operation.

Reboot once if the installer added a new kernel or changed group memberships:

```bash
sudo reboot
```

## 4. Verify the runtime and hardware

Reconnect and run:

```bash
cd "$HOME/raspberry_ninja"

python3 - <<'PY'
import gi, websockets, cryptography, aiohttp
gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
from gi.repository import Gst
Gst.init(None)
print(Gst.version_string())
print("Python/GStreamer WebRTC imports: OK")
PY

for element in webrtcbin nice videotestsrc x264enc v4l2h264enc openh264dec avdec_h264 kmssink; do
  if gst-inspect-1.0 "$element" >/dev/null 2>&1; then
    echo "$element: available"
  else
    echo "$element: unavailable"
  fi
done

v4l2-ctl --list-devices
rpicam-hello --list-cameras
```

Do not assume that an installed encoder element works. Raspberry Ninja now sends a few tiny frames through `v4l2h264enc` before selecting it. If the driver rejects the probe, Raspberry Ninja reports the kernel and GStreamer version and falls back to x264.

The following environment overrides are available for exceptional, already-tested pipelines:

```bash
RN_DISABLE_V4L2_ENCODER=1 python3 publish.py ...
RN_FORCE_V4L2_ENCODER=1 python3 publish.py ...
```

Only force V4L2 when a known-good zero-copy/camera pipeline works even though the system-memory probe does not.

## 5. Test the Pi as a sender

Start small on a Zero 2 W:

```bash
cd "$HOME/raspberry_ninja"
python3 -u publish.py \
  --test --rpi --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid florida-test \
  --password false
```

On another computer, open:

```text
https://vdo.ninja/?view=florida-test&password=false
```

The Pi console should report WebSocket readiness, an ICE connection, and streaming bitrate. Stop it with Ctrl+C.

`--password false` is convenient for a controlled test but disables VDO.Ninja's additional application-level encryption. For deployment, replace it on both ends with a strong shared value and URL-encode that value in browser URLs.

### USB webcam or HDMI capture input

Identify a real capture node rather than selecting a Pi codec node:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --all
v4l2-ctl -d /dev/video0 --list-formats-ext
```

Then start with conservative settings:

```bash
python3 -u publish.py \
  --v4l2 /dev/video0 --rpi --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid florida-camera \
  --password false
```

Remove `--noaudio` and select an ALSA input when a microphone is ready:

```bash
arecord -l
python3 -u publish.py ... --alsa hw:CARD,DEVICE
```

Some webcams, including many Logitech C920 units, advertise an `H264` capture
format. On a Zero 2 W, use that camera-provided compressed stream to avoid
decoding MJPEG and encoding it again in software:

```bash
python3 -u publish.py \
  --v4l2 /dev/video0 --format H264 --h264 \
  --width 1280 --height 720 --framerate 15 \
  --alsa hw:1,0 --audiobitrate 48 \
  --streamid florida-camera \
  --password false
```

Use `--format H264` only when `--list-formats-ext` advertises H.264 at the
requested resolution and frame rate. Raspberry Ninja validates the advertised
mode and otherwise retains the existing MJPEG fallback. Native passthrough
cannot add clock overlays or change the webcam's internally selected H.264
bitrate; `--bitrate` still communicates the WebRTC bandwidth preference but
does not re-encode the camera stream.

A webcam can exceed the Zero 2 W's USB power budget even when capture itself is
lightweight. If the Pi reboots, disappears from Wi-Fi, or reports undervoltage
after connecting the camera, use a separately powered USB hub and verify:

```bash
lsusb
vcgencmd get_throttled
```

Increase resolution, frame rate, and bitrate one setting at a time while watching memory, temperature, throttling, and dropped frames.

### Raspberry Pi CSI camera

Camera tooling differs by OS release. Detect capabilities instead of assuming a command name:

```bash
command -v rpicam-hello libcamera-hello
gst-inspect-1.0 rpicamsrc
gst-inspect-1.0 libcamerasrc
```

- Use `--rpicam` when `rpicamsrc` is installed and tested.
- Otherwise try `--libcamera --rpi` when `libcamerasrc` is available.
- Older Raspberry Pi OS releases may expose `libcamera-*`; newer releases generally expose `rpicam-*` applications.

## 6. Test the Pi as a headless receiver

First test negotiation and decode without requiring HDMI:

```bash
cd "$HOME/raspberry_ninja"
RN_FORCE_SINK=fakesink python3 -u publish.py \
  --view illinois-tv \
  --password false \
  --noaudio
```

In Chrome on another computer, open:

```text
https://vdo.ninja/?push=illinois-tv&password=false&h264
```

Choose **Share your Camera**. The Pi should report:

- an incoming offer;
- ICE connected;
- an H.264 RTP pad;
- the display source switching to `remote`;
- a non-zero receiving bitrate.

Stop the receiver with Ctrl+C.

## 7. Validate HDMI video and audio

Connect the Pi's HDMI output to the TV before booting. Confirm the connector state:

```bash
for status in /sys/class/drm/card*-HDMI-A-*/status; do
  echo "$status: $(cat "$status")"
done
kmsprint -m 2>/dev/null || true
aplay -l
```

At least one HDMI status should say `connected`. Then run the real receiver without `RN_FORCE_SINK`:

```bash
cd "$HOME/raspberry_ninja"
unset DISPLAY WAYLAND_DISPLAY
python3 -u publish.py \
  --view illinois-tv \
  --password false
```

On a Pi 4, start with the micro-HDMI port closest to the USB-C power connector (HDMI 0). The Pi's HDMI connectors are outputs; a USB capture card is not required to display a received stream on a TV.

Do **not** add `--framebuffer /dev/fb0`. The `--framebuffer` option takes a VDO.Ninja stream ID and exposes decoded BGR frames through shared memory for another program; it does not select an HDMI output. Current Raspberry Pi OS KMS installations may not provide `/dev/fb0` at all.

If an OpenGL video window appears on the computer from which you opened SSH, check:

```bash
printf 'DISPLAY=%s\n' "$DISPLAY"
```

A value such as `localhost:10.0` is SSH X11 forwarding. `unset DISPLAY WAYLAND_DISPLAY` before the manual receiver command, as shown above. Raspberry Ninja will then prefer direct `kmssink` output with KMS mode-setting enabled when a local HDMI connector is detected. It reads the connected monitor's advertised modes instead of assuming that the framebuffer's virtual size is supported. If HDMI is disconnected, it uses a non-visible fallback instead of opening a window on the SSH client.

The default preserves the source aspect ratio and may add black bars. This avoids distorting 16:9 video on a 1920x1200 monitor or another unexpected mode. Add `--stretch-display` only when filling every pixel matters more than preserving geometry.

For a direct KMS diagnostic, stop any running receiver and test a local pattern:

```bash
MODE=""
for connector in /sys/class/drm/card*-HDMI-A-*; do
  [ "$(cat "$connector/status" 2>/dev/null)" = connected ] || continue
  MODE="$(head -n 1 "$connector/modes")"
  break
done
[ -n "$MODE" ] || { echo "No connected HDMI mode found"; exit 1; }
WIDTH="${MODE%x*}"
HEIGHT="${MODE#*x}"

gst-launch-1.0 -v videotestsrc num-buffers=100 pattern=smpte \
  ! video/x-raw,format=BGRx,width="$WIDTH",height="$HEIGHT",framerate=10/1 \
  ! kmssink sync=false force-modesetting=true
```

The pattern must appear on the Pi-connected TV, not on the SSH computer. If it fails, collect:

```bash
id
grep -H . /sys/class/drm/card*-*/status
gst-inspect-1.0 kmssink
```

The receiver user normally needs access to the `video` and `render` groups. After changing group membership, reboot before retesting.

If video works but audio does not, verify the HDMI ALSA device with `aplay -l` and test it independently. Audio device naming differs across Raspberry Pi OS, Ubuntu, kernels, and board revisions, so do not hard-code a card number copied from another Pi.

## 8. Make the receiver start on boot

First prove the receiver manually. Then run the installer while logged in as the account that owns the clone:

```bash
cd "$HOME/raspberry_ninja"
sudo python3 tools/install_unattended.py \
  receiver --stream-id illinois-tv
systemctl status raspberry-ninja-viewer.service --no-pager
```

The installer prompts for the shared VDO.Ninja password. It writes a validated systemd unit and a restricted JSON config under `/etc/raspberry-ninja/`, enables the service, and starts or restarts it. This keeps the password out of the unit's `ExecStart` line. Use the literal password `false` only for a controlled test:

```bash
sudo python3 tools/install_unattended.py --password false \
  receiver --stream-id illinois-tv
```

Aspect ratio is preserved by default. Add `--stretch-display` after `receiver` if fill-to-screen distortion is intentional. Run the same command again to safely update and restart an existing service. Use `--no-start` before the role to install without starting immediately.

Follow logs with:

```bash
journalctl -u raspberry-ninja-viewer.service -f
```

The service remains connected to signaling while no sender is present. When either the Florida Pi or a browser publishes `illinois-tv`, the receiver connects and switches to live video. Its built-in viewer retry logic handles sender disconnects and later restarts.

If the service fails, do not run random commands until its first error is known:

```bash
systemctl status raspberry-ninja-viewer.service --no-pager
journalctl -u raspberry-ninja-viewer.service -n 100 --no-pager
sudo systemd-analyze verify /etc/systemd/system/raspberry-ninja-viewer.service
```

An explicitly requested missing or malformed JSON config is a hard startup error. Raspberry Ninja will not silently fall back to publishing from a default camera.

## 9. Optional sender auto-start

After a real camera command has been tested manually, install the matching sender service. For a conservative camera-only sender:

```bash
sudo python3 tools/install_unattended.py \
  sender --stream-id illinois-tv \
  --camera /dev/v4l/by-id/YOUR-CAMERA \
  --width 640 --height 360 --framerate 15 --bitrate 500
```

For a C920 that advertises H.264 and has already passed the manual test:

```bash
sudo python3 tools/install_unattended.py \
  sender --stream-id illinois-tv \
  --camera /dev/v4l/by-id/YOUR-C920-video-index0 \
  --format H264 --width 1280 --height 720 --framerate 15 --bitrate 2500 \
  --audio-device hw:C920,0 --audio-bitrate 48
```

The installer prompts for the password. Do not enable a real-camera service until the selected node has been verified. Stable paths under `/dev/v4l/by-id/` are preferable to `/dev/video0`; use a stable ALSA name such as `hw:C920,0` when the device provides one.

For a local test that must not contact a STUN server, place `--stun-server false` before `sender` or `receiver`. Do not disable STUN for the Florida-to-Illinois deployment: peers behind different routers normally need STUN and sometimes TURN.

## 10. Optional two-way conversation

Use two different stream IDs:

- Florida to Illinois TV: `illinois-tv`
- Illinois camera/microphone back to Florida: `illinois-return`

Keep the receiver service from section 8. On the Illinois Pi, manually prove the C920/native-H.264 command, then install a second service with the return ID:

```bash
sudo python3 tools/install_unattended.py \
  sender --service-name raspberry-ninja-return \
  --stream-id illinois-return \
  --camera /dev/v4l/by-id/YOUR-C920-video-index0 \
  --format H264 --width 1280 --height 720 --framerate 15 --bitrate 2500 \
  --audio-device hw:C920,0 --audio-bitrate 48
```

The Florida laptop can publish `illinois-tv` and view `illinois-return`. If both actions are done in VDO.Ninja browser tabs, both must use the same strong shared password as their corresponding Pi services.

Two-way audio needs echo control. Raspberry Ninja's raw ALSA path does not provide browser-style acoustic echo cancellation. Use headphones, an echo-cancelling USB speakerphone, or careful microphone/speaker placement and volume. Test HDMI audio and microphone audio separately before combining them.

On the tested Zero, two processes worked only because the C920 supplied H.264 directly. Do not attempt two software encoders on this board. A Pi 4 or Pi 5 with Ethernet, cooling, and a strong power supply is the safer unattended two-way endpoint.

## 11. Zero 2 W operating limits

Use these defaults until the setup has been stable for several hours:

- 640x360 at 15 fps
- 500 kbps video
- one Raspberry Ninja process for the recommended receive-only deployment
- Raspberry Pi OS Lite without a desktop/browser on the Pi
- test video without audio while isolating problems

Monitor the board during a stream:

```bash
watch -n 2 'free -h; vcgencmd measure_temp; vcgencmd get_throttled'
```

Useful service checks are:

```bash
ps -o pid,rss,%cpu,%mem,etime,cmd -C python3
journalctl -u raspberry-ninja-viewer.service -n 100 --no-pager
sudo dpkg --audit
df -h /
```

Avoid parallel package installs, builds, browsers, or multiple software encoders on this board. Some swap use during package installation is normal; sustained video should not continually grow swap or trigger throttling.

If the exact native-H.264 two-way path is used, watch both processes for several hours. Stop or downgrade the return sender if available memory continually falls, swap keeps growing, temperature rises excessively, or either stream loses frames.

## 12. Troubleshooting by platform capability

When a pipeline fails, collect the actual environment instead of applying another board's settings:

```bash
cat /proc/device-tree/model; echo
cat /etc/os-release
uname -a
gst-launch-1.0 --version
gst-inspect-1.0 v4l2h264enc
v4l2-ctl --list-devices
command -v rpicam-vid libcamera-vid
free -h
vcgencmd get_throttled
```

Important differences include:

- Pi 3/4 V4L2 hardware encoding versus Pi 5 software encoding;
- Raspberry Pi OS versus Ubuntu package names and camera integration;
- `libcamera` versus `rpicam` tooling;
- GStreamer element properties and caps across releases;
- Orange Pi/Rockchip MPP elements;
- NVIDIA Jetson `nvv4l2*` elements and NVMM memory.

Use detected elements and tested fallbacks. Do not replace working legacy or non-Pi paths with settings verified on only this Zero 2 W.

For a shareable diagnostic checklist, continue with [Troubleshooting](troubleshooting.md). Before leaving the unit unattended, complete the [unattended validation checklist](unattended-validation-checklist.md). For broader operating guidance, see the [Operations guide](operations-guide.md#stability-checks).
