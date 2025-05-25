# Changelog

## Recent Updates

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