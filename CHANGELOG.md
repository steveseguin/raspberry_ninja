# Changelog

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

