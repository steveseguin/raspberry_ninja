# Raspberry Ninja quick start

## 1. Install

On Raspberry Pi OS, Ubuntu, or Debian, run as your normal user with sudo access:

```bash
cd ~
curl -fL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh -o install-raspberry-ninja.sh && \
  bash install-raspberry-ninja.sh --non-interactive --runtime-only --skip-system-upgrade
cd ~/raspberry_ninja
```

Continue only after the installer succeeds. This installs runtime dependencies
without development headers or a full OS upgrade. If you already have a clone,
run `bash install.sh --non-interactive --runtime-only --skip-system-upgrade`
from that directory instead.

## 2. Set up a Raspberry Pi to start at boot

```bash
sudo python3 tools/setup.py
```

Choose **Show video on a TV** or **Send camera video**. Setup lists detected
cameras and microphones, writes a configuration, and enables and starts a systemd
service. Connect the camera or TV first. The selected video defaults may need
adjustment for your camera's supported resolutions and frame rates.

Use the same stream name and password at both ends. That is all most Raspberry
Pi setups need.

The guided service setup targets Raspberry Pi Linux systems with systemd. For
Jetson, Orange Pi, desktops, or other platforms, use the
[platform installation guides](installers/README.md) and manual commands.

To check a guided sender (use `raspberry-ninja-viewer` for a receiver):

```bash
sudo systemctl status raspberry-ninja-sender
sudo journalctl -u raspberry-ninja-sender -n 30 --no-pager
```

Re-run setup to change the stream name, password, or source; it restarts the
selected service. Advanced service options are documented by
`python3 tools/install_unattended.py --help` and its `sender --help` or
`receiver --help` subcommands.

## Optional one-time test

For reusable manual commands, see
[JSON configuration and command-line overrides](docs/operations-guide.md#save-settings-in-a-json-configuration).

To publish a small test pattern without changing the saved setup:

```bash
python3 publish.py --test --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-test --password false
```

Open `https://vdo.ninja/?view=rn-test&password=false` and stop the test with
Ctrl+C. Use a real password for anything beyond this first test.

For a local software encode/decode check without publishing a stream, run
`python3 tools/media_self_test.py`. Missing codecs are reported as skipped;
a failed probe or no passing probes returns a nonzero exit status. This does
not test the camera, hardware encoders, HDMI output, or network connectivity.

If setup reports a problem, continue with [Troubleshooting](docs/troubleshooting.md).
Advanced commands remain available in the [documentation index](docs/README.md).
