# Raspberry Ninja documentation

Raspberry Ninja publishes, receives, records, and relays VDO.Ninja streams from Linux systems and single-board computers. Start with the guide that matches the job you are trying to do.

## Start here

| Goal | Guide |
| --- | --- |
| Install and publish a first test stream | [Quick start](../QUICK_START.md) |
| Configure a Pi Zero 2 W as an unattended sender or HDMI receiver | [Pi Zero 2 W unattended WebRTC](pi-zero-2-w-unattended-webrtc.md) |
| Validate recovery, soak behavior, and unattended readiness | [Unattended validation checklist](unattended-validation-checklist.md) |
| Run and monitor publishers, receivers, and test benches | [Operations guide](operations-guide.md) |
| Record one stream, a room, or HLS segments | [Recording guide](recording-guide.md) |
| Diagnose installation, media, display, network, or resource failures | [Troubleshooting](troubleshooting.md) |
| Understand board, OS, camera-stack, and GStreamer differences | [Platform compatibility](platform-compatibility.md) |

## Platform installation

- [Installer overview](../installers/README.md)
- [Raspberry Pi](../installers/raspberry_pi/README.md)
- [NVIDIA Jetson](../installers/nvidia_jetson/README.md)
- [Orange Pi](../installers/orangepi/README.md)
- [Ubuntu](../installers/ubuntu/README.md)
- [Windows Subsystem for Linux](../installers/wsl/README.md)
- [macOS](../installers/mac/readme.md)

## Documentation conventions

- Commands are run from the repository directory unless a guide says otherwise.
- `STREAM_ID`, `ROOM_NAME`, device paths, usernames, and passwords are placeholders.
- `--password false` is useful for an isolated test, but disables VDO.Ninja's additional application-level encryption. Use the same strong password at both ends for deployment.
- A GStreamer element being installed does not prove that its driver and memory path work. Probe the actual device and keep a software fallback.
- Hardware advice is a starting point. Confirm the actual board, OS, kernel, GStreamer version, plugins, camera stack, and device modes before tuning.

## Engineering records

Files under [`dev_notes`](../dev_notes/) document dated investigations and test results. They are useful for reproducing a finding, but they are not current operator instructions. Use the guides above for deployment commands.

When reporting a bug, include the environment bundle from [Troubleshooting](troubleshooting.md#collect-an-environment-bundle), the complete command, and the first GStreamer error before any cascade of follow-on errors.
