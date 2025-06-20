# MKV Audio+Video Recording Fix Summary

## Issue
The MKV subprocess (`webrtc_subprocess_mkv.py`) was not receiving media pads despite successful WebRTC connection when using `--audio` flag for room recording.

## Root Cause
The MKV subprocess was missing critical renegotiation handling logic needed to process SDP offers received through the data channel. VDO.Ninja uses a two-stage connection process:
1. Initial connection establishes only the data channel
2. After receiving a media request, it sends a renegotiation offer with media tracks
3. This renegotiation must be processed to receive video/audio pads

## Fix Applied
Enhanced the MKV subprocess with:

1. **Data Channel Message Handling**: Added JSON parsing to detect renegotiation offers and ICE candidates in `on_data_channel_message()`

2. **Renegotiation Logic**: Implemented `handle_renegotiation_offer()` and `try_pending_renegotiation()` methods to safely process offers when WebRTC is in stable state

3. **Asynchronous Promise Handling**: Changed from synchronous `promise.wait()` to callbacks (`on_offer_set`, `on_answer_created`) following GStreamer best practices

4. **Bidirectional Communication**: Both answers and ICE candidates now sent through data channel when available

## Test Results
Successfully recorded MKV file with:
- Video: VP8 codec, 1920x1080 resolution  
- Audio: Opus codec, 2 channels
- File size: ~1MB for 25 seconds of recording

## Commands That Now Work
```bash
# Record audio+video from room
python3 publish.py --room testroom123 --record-room --audio

# Record with specific codecs
python3 publish.py --room testroom123 --record-room --audio --h264
python3 publish.py --room testroom123 --record-room --audio --vp8
```

The MKV subprocess now properly handles the VDO.Ninja protocol and successfully records both audio and video streams.