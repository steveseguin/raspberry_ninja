# Raspberry Ninja quick start

## 1. Install

The basic non-interactive installer installs dependencies and clones the repository when needed:

```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh | bash
cd ~/raspberry_ninja
```

For configuration prompts and optional auto-start, download and run the installer interactively instead:

```bash
wget https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh
chmod +x install.sh
./install.sh
```

On a Pi Zero 2 W, use the [low-memory installation guide](docs/pi-zero-2-w-unattended-webrtc.md#3-install-the-low-memory-runtime).

## 2. Publish a test stream

Start with a small synthetic stream so camera and audio drivers cannot hide a signaling problem:

```bash
python3 -u publish.py \
  --test --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-test \
  --password false
```

## 3. View it

Open:

```text
https://vdo.ninja/?view=rn-test&password=false
```

The terminal should report ICE connected and a non-zero bitrate. Stop with Ctrl+C.

`--password false` is only for a controlled first test. It disables VDO.Ninja's additional application-level encryption. For deployment, use the same strong password in the publisher, receiver, and browser URL.

## 4. Add real hardware

List cameras and audio devices before choosing them:

```bash
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
arecord -l
```

Then replace `--test` with the verified input, for example `--v4l2 /dev/video0`. Keep the low settings until remote playback is stable.

Next: [documentation index](docs/README.md), [operations](docs/operations-guide.md), [troubleshooting](docs/troubleshooting.md), or `python3 publish.py --help`.
