# Jetson Nano HLS Recording Fix Summary

## Problem
On Jetson Nano 2GB running GStreamer 1.23.0 (development version), HLS recording was showing "Got data flow before segment event" warnings from mpegtsmux. This didn't occur on x86/WSL systems.

## Root Cause
1. **GStreamer 1.23.0** has stricter segment event checking
2. **Jetson Nano 2GB** slower processing exposes race conditions
3. Dynamic pad linking from webrtcbin causes segment events to arrive after data

## Solution Implemented

### 1. Explicit mpegtsmux Control
- Create our own mpegtsmux element (except for splitmuxsink which manages its own)
- Configure with proper HLS alignment settings
- Direct control over element state transitions

### 2. Segment Event Injection
- Add pad probes on video/audio queues before mux
- Inject segment events before first buffer reaches mux
- Ensures proper event ordering

### 3. Delayed Element Start
- 100ms delay after pad connections before starting mux/sink
- Allows segment events to propagate on slower systems
- Prevents race condition

### 4. Dual Mode Support
- **splitmuxsink**: Uses internal mux, connects directly
- **manual mode**: Uses explicit mux for future m3u8 support

## Testing
Run on Jetson Nano:
```bash
python3 publish.py --record-room --hls --room TestRoom --webserver 8087
```

Expected results:
- No segment event warnings
- HLS files created successfully
- Clean state transitions logged

## Key Code Changes
1. `setup_hls_muxer()`: Creates explicit mpegtsmux or uses internal
2. Video/audio pad connections: Route through mux with segment injection
3. `check_hls_streams_ready()`: Delayed start with proper state management

## Architecture Notes
- GStreamer dev versions (1.23.x) have stricter checks than stable
- ARM scheduling differences expose latent timing bugs
- Explicit pipeline control prevents race conditions