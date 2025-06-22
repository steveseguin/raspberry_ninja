# HLS Segment Event Fix

## Problem
When running HLS recording mode on Nvidia Jetson, GStreamer was showing warnings:
```
mpegtsmux gstmpegtsmux.c:1236:mpegtsmux_collected:<mpegtsmux0> Got data flow before segment event
```

This occurred because the mpegtsmux element was receiving data without proper segment events being propagated through the pipeline when elements are connected dynamically.

## Solution
The fix involves several improvements to ensure proper segment event propagation:

1. **Segment Event Injection**: Added pad probes that inject segment events before the first buffer for both video and audio streams
2. **Identity Elements**: Added identity elements with `single-segment=true` property to help with segment handling
3. **Mpegtsmux Configuration**: Set the `alignment` property on mpegtsmux for proper segmentation
4. **State Management**: Ensure HLS sink transitions to PLAYING state after all connections are made
5. **Monitoring**: Added file creation checks to verify HLS segments are being written

## Code Changes

### Video Pipeline (H264)
Before: `queue -> depay -> h264parse -> video_queue -> hlssink`
After: `queue -> depay -> h264parse -> identity -> video_queue -> hlssink`

### Audio Pipeline (OPUS to AAC)
Before: `queue -> depay -> decoder -> convert -> aacenc -> aacparse -> audio_queue -> hlssink`
After: `queue -> depay -> decoder -> convert -> aacenc -> aacparse -> identity -> audio_queue -> hlssink`

The identity elements help ensure proper segment boundaries, and the pad probes inject segment events when needed.

## Testing
To test the fix:
```bash
python3 publish.py --record-room --hls --room TestRoom --webserver 8080
```

The warnings should no longer appear, and HLS segments should be created properly.