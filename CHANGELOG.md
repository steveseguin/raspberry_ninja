# Changelog

# Release 1.0.3

**Release Date:** 2025-05-30

## 🐛 Patch Release

This release includes bug fixes and minor improvements.

### Commits

- encoder bitrate tweak (40264fb)
- h264 encoder fix (9f4c5b6)
- chore: Remove .claude directory (787d3f4)
- chore: release v1.0.2 [release] (aa30557)
- race condition clean up (63c8e55)
- ``` fix(repo): Remove broken WSL2-Linux-Kernel submodule (b2ed98b)
- Remove broken WSL2-Linux-Kernel submodule reference (8baf5c9)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 1.0.2

**Release Date:** 2025-05-26

## 🐛 Patch Release

This release includes bug fixes and minor improvements.

### Commits

- race condition clean up (63c8e55)
- ``` fix(repo): Remove broken WSL2-Linux-Kernel submodule (b2ed98b)
- Remove broken WSL2-Linux-Kernel submodule reference (8baf5c9)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

# Release 1.0.1

**Release Date:** 2025-05-26

## 🐛 Patch Release

This release includes bug fixes and minor improvements.

### Commits

- fixes (5d58087)
- Update README.md (fe78c32)
- added a webserver (297c5df)
- better closing /  stats (1b3666c)
- chore(docs): update TOC (9a94f89)
- attemps at fixing issues; plus doc updates (b99dd9d)
- . (8349178)
- tweaks for rpi5 (b5e0373)
- tweaks for rpi5 (b7248de)
- Update publish.py (db535f7)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

All notable changes to Raspberry Ninja will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version History

### Versioning Guidelines

- **Major** (X.0.0): Breaking changes, protocol changes, major architecture updates
- **Minor** (0.X.0): New features, significant improvements, new platform support
- **Patch** (0.0.X): Bug fixes, performance improvements, minor updates

### Key Components

- `publish.py` - Core RTMP/WebRTC streaming script
- Platform installers - Installation scripts for various SBCs
- System services - Service configurations for auto-start
- Documentation - Setup guides and troubleshooting

---

<!-- New releases will be automatically added above this line -->

## [Unreleased]

### Recent Updates

### Multi-Stream Room Recording
- Added `--record-room` flag to record all participants in a room to separate files
- Added `--record-streams` to filter which room participants to record
- Added `--room-ndi` to output all room streams as separate NDI sources
- Files are saved as `{room_name}_{stream_id}_{timestamp}_{uuid}.ts`

### Stability Improvements
- Fixed segmentation fault issues when using very low buffer values (<10ms)
- Added minimum buffer validation (enforces 10ms minimum)
- Fixed GStreamer element cleanup order to prevent crashes
- Improved error handling for corrupted JPEG frames from USB devices

### Dynamic Bitrate Improvements
- Fixed v4l2h264enc bitrate error that caused crashes
- Added proper bitrate handling for all encoder types
- Shows helpful messages for encoders that don't support dynamic bitrate
- Consolidated bitrate logic into a single maintainable method

### Pipeline Improvements
- Added `jpegparse` element for better JPEG error handling
- Added queue elements before decoders to handle bursty USB input
- Improved queue configuration for low-latency scenarios
- Added leaky queues to prevent buffer overruns

### WebSocket Handling
- Fixed reconnection logic to maintain peer connections
- Improved cleanup when connections are lost
- Better error messages for connection issues

### Documentation
- Added comprehensive troubleshooting guide
- Created quick start guide with common examples
- Added room recording documentation
- Updated help text with clearer descriptions

### Bug Fixes
- Fixed audio pad linking in room recording
- Fixed UUID handling in custom websocket mode
- Added thread-safe access to room streams data
- Improved framerate stability with USB devices
- Better handling of room events in different server modes

## Known Limitations

1. **Room Recording** requires a VDO.Ninja-compatible server (not simple relay servers)
2. **v4l2h264enc** doesn't support dynamic bitrate changes
3. **USB 2.0** devices may struggle with 1080p30 on Raspberry Pi
4. **Custom websocket servers** (`--puuid` mode) don't support room features

## Upgrade Notes

- If you experience segfaults, ensure your buffer value is at least 10ms
- Add `--rpi` flag when running on Raspberry Pi for better performance
- USB HDMI capture users should use a powered USB hub for stability
- Room recording users must use standard VDO.Ninja servers