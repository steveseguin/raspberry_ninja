# Changelog

# Release 10.0.0

**Release Date:** 2025-12-18

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- soft jpeg (d650613)
- fix(gstreamer): Gate SDP patches to GStreamer < 1.20 (a45a77a)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 9.0.0

**Release Date:** 2025-12-18

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- fix(gstreamer): Make Gst 1.18 audio SDP Chrome-compatible (aeedb68)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 8.0.0

**Release Date:** 2025-12-17

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- fix(gstreamer): Strip audio from SDP for GStreamer < 1.20 (c62b639)
- fix(gstreamer): Remove video-specific RTCP feedback from audio SDP (10e31ee)
- chore: release v7.0.0 [release] (e350b95)
- fix(gstreamer): Fix WebRTC compatibility for GStreamer 1.18 (cbfd4a6)
- fix(gstreamer): Prevent invalid SSRC with older GStreamer versions (2eda1a2)
- docs(nvidia_jetson): Update pre-built image details and compatibility (dee4a5b)
- docs(nvidia-jetson): Update pre-built image info and installation steps (5aff772)
- Delete installers/nvidia_jetson/publish.py (f6d5ea9)
- feat(nvidia_jetson): Add initial publish.py script for NVIDIA Jetson (8240663)
- docs(jetson): Overhaul and expand NVIDIA Jetson installation guide (ebf6a02)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 7.0.0

**Release Date:** 2025-12-17

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- fix(gstreamer): Fix WebRTC compatibility for GStreamer 1.18 (cbfd4a6)
- fix(gstreamer): Prevent invalid SSRC with older GStreamer versions (2eda1a2)
- docs(nvidia_jetson): Update pre-built image details and compatibility (dee4a5b)
- docs(nvidia-jetson): Update pre-built image info and installation steps (5aff772)
- Delete installers/nvidia_jetson/publish.py (f6d5ea9)
- feat(nvidia_jetson): Add initial publish.py script for NVIDIA Jetson (8240663)
- docs(jetson): Overhaul and expand NVIDIA Jetson installation guide (ebf6a02)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 6.1.0

**Release Date:** 2025-11-16

## ✨ Minor Release

This release includes new features and improvements.

### Core Changes (publish.py)

The main streaming script has been updated. New features or improvements have been added.

### Commits

- Add files via upload (16cd312)
- Add files via upload (0d3c61e)
- chore(install): Remove quick update script for NVIDIA Jetson (af3403f)
- docs(jetson): Revise installation and usage guide (4b9916a)
- feat(video): Increase default framebuffer resolution to 1080p (9ca7c19)
- Add files via upload (729041a)
- chore: Remove .claude development configuration (54dfa9a)
- feat(webrtc): Allow forcing H264 profile for WebRTC viewers (576f430)
- chore: release v6.0.0 [release] (eb0066f)
- Add files via upload (c46b5e9)
- feat(jetson-install): Implement Jetson Nano media toolchain installer (a7c077d)
- feat(publish): Add publisher-side redundancy and viewer auto-retry controls (3bd5a14)
- feat(webrtc): Improve redundancy negotiation and status reporting (3fdd679)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 6.0.0

**Release Date:** 2025-11-08

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- Add files via upload (c46b5e9)
- feat(jetson-install): Implement Jetson Nano media toolchain installer (a7c077d)
- feat(publish): Add publisher-side redundancy and viewer auto-retry controls (3bd5a14)
- feat(webrtc): Improve redundancy negotiation and status reporting (3fdd679)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 5.0.0

**Release Date:** 2025-10-30

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- . (9021269)
- ``` fix(shutdown): Improve graceful shutdown handling (278748c)
- chore: release v4.0.0 [release] (14923a4)
- error correction (6866ed5)
- feat(webrtc): Enhance hardware decoder control and graceful shutdown (da01229)
- feat(webrtc): Add options to disable hardware decoder for viewers (87fabd2)
- feat(viewer-display): Prime display with idle splash and defer video-off state (ab4cf6d)
- docs(viewer): Document splash screen options and auto-reconnect (8fb06ec)
- feat(display): Implement persistent idle state after client disconnect (08d99b7)
- feat(viewer): Improve display management and stream restart robustness (cdbdfac)
- ``` fix(gstreamer): Improve display pipeline and client cleanup robustness (a985840)
- feat(console): Add customizable splash screens, background, and input control (83f280e)
- fix(jetson): Configure dedicated console for auto-start service (91820b4)
- fix(install/jetson): Update GStreamer and X11 dependencies (e95649d)
- chore(jetson): Remove obsolete Gtk/GStreamer patch script (dee61ef)
- docs(jetson): Clarify Jetson Nano 16GB image for desktop preview (7ab69cf)
- ``` fix(jetson): Re-enable GStreamer `gtksink` preview in desktop sessions (8e3257b)
- feat(jetson): Enhance X11 display sink selection to prevent EGL issues (544a4bc)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 4.0.0

**Release Date:** 2025-10-30

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- error correction (6866ed5)
- feat(webrtc): Enhance hardware decoder control and graceful shutdown (da01229)
- feat(webrtc): Add options to disable hardware decoder for viewers (87fabd2)
- feat(viewer-display): Prime display with idle splash and defer video-off state (ab4cf6d)
- docs(viewer): Document splash screen options and auto-reconnect (8fb06ec)
- feat(display): Implement persistent idle state after client disconnect (08d99b7)
- feat(viewer): Improve display management and stream restart robustness (cdbdfac)
- ``` fix(gstreamer): Improve display pipeline and client cleanup robustness (a985840)
- feat(console): Add customizable splash screens, background, and input control (83f280e)
- fix(jetson): Configure dedicated console for auto-start service (91820b4)
- fix(install/jetson): Update GStreamer and X11 dependencies (e95649d)
- chore(jetson): Remove obsolete Gtk/GStreamer patch script (dee61ef)
- docs(jetson): Clarify Jetson Nano 16GB image for desktop preview (7ab69cf)
- ``` fix(jetson): Re-enable GStreamer `gtksink` preview in desktop sessions (8e3257b)
- feat(jetson): Enhance X11 display sink selection to prevent EGL issues (544a4bc)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 3.0.0

**Release Date:** 2025-10-20

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- fixes for view (da22423)
- chore(ci): Update Gemini API model version (7ff829a)
- tests (082b25b)
- chore: release v2.0.0 [release] (d263ef2)
- nv updates (1f567fc)
- Update README.md (9bdcdec)
- Update README.md (f6f08c6)
- Update README.md (452f0a5)
- mini update (f7d2220)
- drm (787bb77)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 2.0.0

**Release Date:** 2025-10-20

## 🚀 Major Release

This release includes breaking changes or significant new features.

### Core Changes (publish.py)

The main streaming script has been updated. This includes significant changes that may affect compatibility.

### Commits

- nv updates (1f567fc)
- mini update (f7d2220)
- drm (787bb77)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)

### ⚠️ Upgrade Notes

This is a major version upgrade. Please review the changes carefully before updating.
It's recommended to backup your configuration before upgrading.


---

# Release 1.3.0

**Release Date:** 2025-09-10

## ✨ Minor Release

This release includes new features and improvements.

### Core Changes (publish.py)

The main streaming script has been updated. New features or improvements have been added.

### Commits

- Update publish.py (bf1c925)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 1.2.0

**Release Date:** 2025-08-04

## ✨ Minor Release

This release includes new features and improvements.

### Core Changes (publish.py)

The main streaming script has been updated. New features or improvements have been added.

### Commits

- feat: Add GStreamer 1.18 framebuffer error detection and guidance (56e489f)
- Update README.md (1a5fb84)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 1.1.1

**Release Date:** 2025-07-08

## 🐛 Patch Release

This release includes bug fixes and minor improvements.

### Commits

- bitrate stat fix (3cb875c)
- chore: Remove root raspberry_ninja item (c2bbcf7)
- . (e034ff4)
- chore: release v1.1.0 [release] (544e2e5)
- chore: Delete QUICK_START.md (029353b)
- chore: Update setup infrastructure and add executable (bc5a76c)
- chore: Update configuration files and documentation (8ad67f4)
- feat(install): Enhance systemd service setup with better user guidance (7608c09)
- feat(install): Improve handling of existing installation directories (c677cc2)
- feat(install): Use existing directories and pull updates instead of erroring (7f6e6bf)
- fix(install): Handle existing directory when cloning repository (f7f701f)
- ``` fix(install): Clone repository to current directory instead of home folder (e23b181)
- ``` fix(install): Improve handling when script is run outside repository (5579c2f)
- fix(install): Refine script for repository cloning and robustness (c219499)
- apt get repo (143606a)
- ``` feat(install): Enhance setup script for repo handling and config location (1b7fca9)
- . (197e2dd)
- fixes (6a576de)
- chore(docs): update TOC (d0baeba)
- feat(install): Add non-interactive install mode (3846b16)
- clarified limits fo installer (fca0947)
- chore: Rename README_OLD.md to README.md (54e7d12)
- Delete README.md (829d4bd)
- chore(docs): update TOC (c98f047)
- docs(installation): Reorganize and improve setup documentation (bffe834)
- . (f29cb98)
- clean up (afad17d)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 1.1.0

**Release Date:** 2025-07-07

## ✨ Minor Release

This release includes new features and improvements.

### Core Changes (publish.py)

The main streaming script has been updated. New features or improvements have been added.

### Commits

- chore: Delete QUICK_START.md (029353b)
- chore: Update setup infrastructure and add executable (bc5a76c)
- chore: Update configuration files and documentation (8ad67f4)
- feat(install): Enhance systemd service setup with better user guidance (7608c09)
- feat(install): Improve handling of existing installation directories (c677cc2)
- fix(install): Handle existing directory when cloning repository (f7f701f)
- ``` fix(install): Clone repository to current directory instead of home folder (e23b181)
- ``` fix(install): Improve handling when script is run outside repository (5579c2f)
- fix(install): Refine script for repository cloning and robustness (c219499)
- apt get repo (143606a)
- ``` feat(install): Enhance setup script for repo handling and config location (1b7fca9)
- . (197e2dd)
- fixes (6a576de)
- chore(docs): update TOC (d0baeba)
- feat(install): Add non-interactive install mode (3846b16)
- clarified limits fo installer (fca0947)
- chore: Rename README_OLD.md to README.md (54e7d12)
- Delete README.md (829d4bd)
- chore(docs): update TOC (c98f047)
- docs(installation): Reorganize and improve setup documentation (bffe834)
- . (f29cb98)
- clean up (afad17d)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 1.0.6

**Release Date:** 2025-06-30

## 🐛 Patch Release

This release includes bug fixes and minor improvements.

### Commits

- salt (bd87c80)
- salt (eeb8ce8)
- . (07d84cf)
- fix: Improve splitmuxsink configuration for HLS recording (de83af6)
- fix: Improve HLS recording startup and debugging (81cc696)
- fix: Enable HLS recording with video-only streams (dbcbca5)
- fix: Handle None hls_mux when using splitmuxsink (ee1c1ec)
- ``` test: Add missing unit test file and fix pre-push hook (cf92da1)
- test: Add missing unit test file and fix pre-push hook (a1bcf63)
- fix(ci): Update CI workflows to use supported actions (b9b1283)
- fix: Update GitHub Actions to fix deprecated versions (ee1a4d1)
- fix: Force splitmuxsink for HLS recording to ensure proper segmentation (2d461ae)
- chore(github): Delete PULL_REQUEST_ATTRIBUTION.md (4c5e118)
- chore: Remove CHANGELOG (488e03a)
- chore: Remove CONTRIBUTORS.md (4ba21c3)
- chore(docs): update TOC (8724639)
- docs: Add CONTRIBUTORS.md to credit papiche for record.py contribution (7d0838e)
- docs: Add comprehensive documentation for record.py audio recording service (1aa2c2a)
- feat: Add audio recording and transcription service (daca304)
- chore(docs): update TOC (45240b0)
- docs: Add detailed PR attribution for papiche's contribution (b9c4246)
- docs: Add CONTRIBUTORS.md to properly credit papiche for record.py (75a0e04)
- chore(docs): update TOC (e78538c)
- ``` docs: Add record.py section to table of contents (416b5ec)
- docs: Add record.py section to table of contents (b930f2e)
- docs: Add comprehensive documentation for record.py audio recording service (31e845b)
- feat: Add record.py audio recording and transcription service from PR #42 (330e531)
- fix: Handle permission errors when writing HLS files (985367a)
- docs: Add summary of Jetson HLS fix (a5e4f1c)
- docs: Add Jetson HLS fix summary (c826a57)
- fix: Comprehensive HLS segment event fix for Jetson Nano GStreamer 1.23.0 (b246444)
- fix: Simplify HLS setup and improve state logging (924a461)
- ``` fix(hls): Synchronize streams with blocking probes to prevent race condition (c5ce227)
- fix: Implement blocking pad probes to fix HLS segment event race condition (0583419)
- fix: Improve HLS segment event handling for audio and state management (02a0e2d)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

All notable changes to Raspberry Ninja will be documented in this file.

