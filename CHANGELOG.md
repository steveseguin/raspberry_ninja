# Changelog

# Release 1.0.4

**Release Date:** 2025-06-22

## 🐛 Patch Release

This release includes bug fixes and minor improvements.

### Commits

- . (5a459ff)
- chore(docs): update TOC (65f60e4)
- ndiout (ad8d2be)
- chore(docs): update TOC (64bc955)
- ndi fix (2f4226b)
- . (faa0019)
- ``` docs(install): Add aiohttp dependency to Raspberry Pi installation (1a7fdd9)
- docs: Add aiohttp to installation instructions (21211e3)
- ``` docs(wsl): Add aiohttp dependency requirement (02f6d56)
- feat: Add NDI freezing fixes and workarounds (af2ab1c)
- feat: Add alternative NDI implementation and final tuning attempts (690cfe0)
- fix: Multiple NDI freezing mitigation attempts (3be424f)
- feat: Add NDI combiner latency settings and freezing detection (6b39f56)
- fix: Simplify NDI pipeline to isolate freezing issue (e4a6cb3)
- fix: Remove videorate and adjust NDI pipeline to prevent freezing (bd75f27)
- fix: Improve NDI stability and audio/video sync (2f1cfcf)
- fix: Fix NDI stream freezing after ~1500 buffers (35d2d10)
- fix: ensure NDI combiner is available when audio arrives before video (47390bf)
- feat: implement HLS audio+video muxing for WebRTC streams (dbf84ea)
- docs: Simplify record room example command (c04d908)
- chore(docs): update TOC (3dbbd3f)
- . (573b503)
- . (0655e79)
- chore(docs): update TOC (e6bac1f)
- feat: Add web UI support for HLS recordings (76d033d)
- room recording options (9879d9c)
- Add HLS recording support with video transcoding (056d208)
- Add WSL NDI network visibility fix (c8c322a)
- Fix NDI pad request methods (c227924)
- Add raw room listing debug output (05b9a7a)
- Fix room NDI stream detection (6c0398d)
- Implement full NDI audio/video multiplexing support (43858a5)
- Fix NDI subprocess parameter passing and variable error (e4ac611)
- Enhance web interface with detailed recording information (4dddfdf)
- Add --lowlatency CLI option for reduced latency mode (eca15ab)
- Fix video transmission issue with GStreamer 1.24 (10f714d)
- Implement room recording with subprocess architecture (ee8aef9)
- Fix subprocess WebRTC routing with deterministic UUID mapping (5be851d)
- Add WebRTC compatibility improvements (1bd4d9a)
- Fix WebRTC ICE and transceiver issues in subprocess (8800066)
- Fix WebRTC connection issues in subprocess architecture (bbb9d05)
- Fix: Auto-enable TURN servers for room recording mode (40644d0)
- Use VDO.Ninja TURN servers by default for room recording (ca6f01f)
- Add ICE candidate type logging for debugging (214039f)
- Improve subprocess ICE configuration and debugging (2da8112)
- Fix subprocess ICE routing and stats_task error (38906fb)
- Improve UUID-based routing for subprocess WebRTC connections (dbcbb02)
- Add debug logging and improve session mapping for room recording (1115bf8)
- Fix subprocess message routing and async handler issues (2799a5f)
- Implement subprocess architecture for room recording (f234217)
- Fix VP8 recording resolution changes and increase heartbeat timeout (0fb8055)

### Installation

For installation instructions, please refer to the platform-specific guides:
- [Raspberry Pi](./raspberry_pi/README.md)
- [NVIDIA Jetson](./nvidia_jetson/README.md)
- [Orange Pi](./orangepi/README.md)
- [Ubuntu](./ubuntu/README.md)


---

All notable changes to Raspberry Ninja will be documented in this file.

