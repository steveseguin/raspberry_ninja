# Raspberry Ninja quick start

## 1. Install

On Raspberry Pi OS, Ubuntu, or Debian:

```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh | bash
cd ~/raspberry_ninja
```

## 2. Choose what this Pi should do

```bash
sudo python3 tools/setup.py
```

Choose **Show video on a TV** or **Send camera video**. Setup finds the camera,
microphone, display mode, and safe video settings automatically, then makes the
Pi start itself after a reboot.

Use the same stream name and password at both ends. That is all most Raspberry
Pi setups need.

## Optional one-time test

To publish a small test pattern without changing the saved setup:

```bash
python3 publish.py --test --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-test --password false
```

Open `https://vdo.ninja/?view=rn-test&password=false` and stop the test with
Ctrl+C. Use a real password for anything beyond this first test.

If setup reports a problem, continue with [Troubleshooting](docs/troubleshooting.md).
Advanced commands remain available in the [documentation index](docs/README.md).
