# Universal HLS Fix for Jetson and x86

## Summary
This fix addresses HLS recording issues on both Nvidia Jetson (with GStreamer 1.23.0) and x86 platforms. The solution ensures proper audio/video muxing without transcoding H264.

## Changes Made

### 1. Platform Detection
- Added `is_jetson()` method to detect Nvidia Jetson platforms
- Adjusts timing delays based on platform (200ms for Jetson, 100ms for x86)

### 2. Blocking Pad Probes
- Changed from non-blocking to BLOCKING pad probes for segment event injection
- Ensures segment events are injected before any data flows to mpegtsmux
- Critical for GStreamer 1.23.0's stricter event ordering requirements

### 3. Identity Elements
- Added identity elements with `single-segment=true` for both audio and video
- Helps with segment boundary management and timestamp synchronization
- Provides better compatibility across different GStreamer versions

### 4. Improved Segment Event Handling
- Segment events now use buffer PTS as base time for better synchronization
- Handles both injected and natural segment events
- Logs segment base times for debugging

### 5. Splitmuxsink State Management
- Improved state transition handling for splitmuxsink
- Sets splitmuxsink to NULL before transitioning to PLAYING
- Configures internal muxer properties when accessible

### 6. Muxer Configuration
- Added prog-map property to mpegtsmux for better stream identification
- Ensures alignment=7 for HLS compatibility
- Sets latency=0 for live streaming

## Key Benefits

1. **Jetson Compatibility**: Fixes "Got data flow before segment event" warnings on GStreamer 1.23.0
2. **Audio/Video Sync**: Proper timestamp synchronization when audio joins existing video stream
3. **No Transcoding**: H264 video passes through without re-encoding
4. **Universal Solution**: Single codebase works on both ARM (Jetson) and x86 platforms

## Testing

To test the fix:
```bash
python3 publish.py --record-room --hls --room TestRoom --webserver 8087
```

Expected results:
- No segment event warnings in logs
- HLS segments created with both audio and video
- Playback works in video.js player
- Works on both Jetson and x86 platforms

## Technical Details

The fix addresses several race conditions:
1. **Event Ordering**: Blocking probes ensure segment events arrive before data
2. **State Transitions**: Proper NULL->PLAYING transitions for all elements
3. **Timestamp Sync**: Using buffer PTS for segment base times
4. **Platform Timing**: Different delays for ARM vs x86 architectures

## Related Files
- `webrtc_subprocess_glib.py`: Main implementation
- `HLS_SEGMENT_FIX.md`: Original Jetson-specific fix
- `JETSON_HLS_FIX_SUMMARY.md`: Jetson debugging notes