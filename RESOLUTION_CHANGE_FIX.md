# Resolution Change Issue Fix

## Problem
The VP8 stream from VDO.Ninja changes resolution during streaming (from 640x360 to 960x540), causing:
- `error: Caps changes are not supported by Matroska`
- `streaming stopped, reason not-negotiated (-4)`
- Connection drops after ~15 seconds

## Root Cause
1. WebM/Matroska muxers don't support dynamic resolution changes
2. The `setup_recording_pipeline` function (used in --view mode) was using basic webmmux
3. The main recording code path was also affected

## Solutions Attempted
1. ✅ Changed to MPEG-TS/HLS (works for H264, but VP8 can't go directly to MPEG-TS)
2. ❌ Tried transcoding (too CPU intensive)
3. ❌ Tried splitmuxsink (still has issues with caps changes)

## Recommended Fix
Use a caps filter with ANY resolution to prevent negotiation failures:

```python
pipeline_str = (
    "queue name=rec_queue ! "
    "rtpvp8depay ! "
    "capsfilter caps=video/x-vp8,width=[1,4096],height=[1,4096],framerate=[0/1,120/1] ! "
    "webmmux ! "
    f"filesink location={filename}"
)
```

Or use a more robust approach with matroskamux settings:

```python
pipeline_str = (
    "queue name=rec_queue ! "
    "rtpvp8depay ! "
    "matroskamux name=mux writing-app=vdo-ninja-recorder ! "
    f"filesink location={filename}"
)
# Then set: mux.set_property('streamable', True)
```

## Temporary Workaround
The recording works for the initial ~15 seconds before the resolution change. Files are created successfully but stop when the stream resolution changes.

## Long-term Solution
1. Detect resolution changes and create new segments
2. Use a custom pad probe to monitor caps changes
3. Implement dynamic pipeline reconfiguration
4. Or use GStreamer's `videoconvert ! videoscale` to normalize resolution (with performance cost)