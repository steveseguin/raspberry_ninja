# Raspberry Pi Zero 2 W unattended VDO.Ninja sender/receiver

This guide sets up a Raspberry Pi Zero 2 W as either:

- an unattended HDMI receiver that waits for a fixed VDO.Ninja stream ID; or
- a low-resolution sender using a USB/CSI camera or a test source.

The receiver may remain on continuously. When a sender starts using the matching stream ID, Raspberry Ninja reconnects and displays the stream. The same receiver works with either another Raspberry Pi sender or a normal VDO.Ninja browser publisher.

## Tested baseline

This procedure was tested on August 2, 2026 with:

- Raspberry Pi Zero 2 W Rev 1.0
- Raspberry Pi OS Lite 32-bit, Debian/Raspbian 13 Trixie
- Linux `6.18.39+rpt-rpi-v7`
- GStreamer 1.26.2
- Python 3.13.5
- a 8 GB microSD card
- 424 MiB usable RAM and 423 MiB swap

Both directions were tested over VDO.Ninja:

- Pi test source to Chrome: H.264, 640x360 at 15 fps, about 500 kbps
- Chrome camera to Pi headless receiver: baseline H.264 received and decoded

The test Pi's HDMI connector was disconnected, so receiver negotiation and decoding were validated with `fakesink`. Repeat the final receiver test with the TV attached to validate the physical HDMI and audio path.

## 1. Image the card

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
python3 -u publish.py \
  --view illinois-tv \
  --password false \
  --stretch-display
```

If video works but audio does not, verify the HDMI ALSA device with `aplay -l` and test it independently. Audio device naming differs across Raspberry Pi OS, Ubuntu, kernels, and board revisions, so do not hard-code a card number copied from another Pi.

## 8. Make the receiver start on boot

Run this while logged in as the account that owns the clone. Change `illinois-tv` and the password mode before deployment.

```bash
RN_USER="$USER"
RN_DIR="$HOME/raspberry_ninja"

sudo tee /etc/systemd/system/raspberry-ninja-viewer.service >/dev/null <<EOF
[Unit]
Description=Raspberry Ninja unattended HDMI receiver
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$RN_USER
WorkingDirectory=$RN_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 $RN_DIR/publish.py --view illinois-tv --password false --stretch-display
Restart=always
RestartSec=5
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now raspberry-ninja-viewer.service
systemctl status raspberry-ninja-viewer.service --no-pager
```

Follow logs with:

```bash
journalctl -u raspberry-ninja-viewer.service -f
```

The service remains connected to signaling while no sender is present. When either the Florida Pi or a browser publishes `illinois-tv`, the receiver connects and switches to live video. Its built-in viewer retry logic handles sender disconnects and later restarts.

## 9. Optional sender auto-start

After a real camera command has been tested manually, put that exact command into a second service on the sender. For example:

```ini
[Unit]
Description=Raspberry Ninja camera sender
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/raspberry_ninja
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /home/YOUR_USER/raspberry_ninja/publish.py --v4l2 /dev/video0 --rpi --h264 --noaudio --width 640 --height 360 --framerate 15 --bitrate 500 --streamid illinois-tv --password false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Do not enable this until `/dev/video0` has been verified as the intended capture device. Stable device paths under `/dev/v4l/by-id/` are preferable for USB cameras when available.

## 10. Zero 2 W operating limits

Use these defaults until the setup has been stable for several hours:

- 640x360 at 15 fps
- 500 kbps video
- one Raspberry Ninja process
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

## 11. Troubleshooting by platform capability

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
