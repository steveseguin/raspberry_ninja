# Platform-specific installers

Most users should start with the universal installer from the repository root:

```bash
./install.sh
```

For a basic non-interactive install:

```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh | bash
```

The platform directories contain additional notes and scripts for hardware-specific or manually managed installations:

| Platform | Guide | Important distinction |
| --- | --- | --- |
| Raspberry Pi | [raspberry_pi](raspberry_pi/README.md) | Pi generation, OS camera stack, and hardware encoder differ |
| NVIDIA Jetson | [nvidia_jetson](nvidia_jetson/README.md) | JetPack/L4T controls NVIDIA plugins and NVMM behavior |
| Orange Pi | [orangepi](orangepi/README.md) | Rockchip MPP availability depends on image and kernel |
| Ubuntu/Debian | [ubuntu](ubuntu/README.md) | Desktop packages and generic software paths |
| Windows Subsystem for Linux | [wsl](wsl/README.md) | Camera, audio, display, and USB access are constrained by WSL |
| macOS | [mac](mac/readme.md) | Homebrew-based experimental setup |

Do not assume a platform guide's dated package versions apply to a newer image. Inventory the actual environment and use capability-based fallbacks described in the [platform compatibility guide](../docs/platform-compatibility.md).

After installation, prove the signaling and software codec path before adding hardware:

```bash
python3 -u publish.py \
  --test --h264 --noaudio \
  --width 640 --height 360 --framerate 15 --bitrate 500 \
  --streamid rn-test --password false
```

Continue with the [quick start](../QUICK_START.md), [operations guide](../docs/operations-guide.md), or [Pi Zero 2 W low-memory guide](../docs/pi-zero-2-w-unattended-webrtc.md).
