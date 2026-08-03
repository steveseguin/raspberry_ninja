# Raspberry Ninja project instructions

## Cross-platform compatibility

Raspberry Ninja must support the project's full hardware and operating-system range, not only the device currently being used for development or testing. Relevant differences include, but are not limited to:

- Raspberry Pi generations such as Pi 3, Pi 4, and Pi 5
- Raspberry Pi OS/Raspbian releases and Ubuntu releases
- GStreamer, kernel, firmware, and multimedia-library versions
- Legacy `libcamera`/camera-stack integrations and newer `rpicam` tooling
- Hardware encoder elements, capabilities, formats, controls, and driver behavior
- Orange Pi boards and their SoC-specific media stacks
- NVIDIA Jetson boards and their NVIDIA-specific GStreamer elements and libraries
- Other supported Linux and Python-compatible systems

When changing installers, device discovery, camera handling, media pipelines, or encoder selection:

- Inspect the actual platform, board, OS release, architecture, kernel, GStreamer version, installed elements, device capabilities, and available camera tools at runtime where practical.
- Prefer capability detection and tested fallbacks over assumptions based only on a board name or a single version number.
- Keep platform-specific behavior isolated and explicit. Do not make a fix for one environment the unconditional path for every environment.
- Preserve working legacy paths unless their replacement has been verified across the relevant support matrix.
- Fail gracefully with actionable diagnostics that report the detected environment and attempted pipeline or backend.
- Test the affected native hardware path when hardware is available, plus software/test-source fallbacks. A passing test on one Pi or distribution is not evidence that all targets behave the same way.
- Add focused regression coverage for detection, selection, fallback, and version-specific behavior whenever practical.

Treat broad support across these variations as a core product requirement rather than an optional enhancement.
