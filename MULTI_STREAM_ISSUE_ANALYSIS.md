# Multi-Stream Recording Issue Analysis

## Summary

You're correct that this is a **multi-stream specific issue**. Single stream recording works but room recording doesn't establish ICE connections.

## Key Differences Found

### 1. **WebRTC Setup Timing**
- **Single Stream**: Creates WebRTC element after receiving the stream request
- **Room Recording**: Creates WebRTC elements proactively for each stream

### 2. **Promise Handling** 
- **Single Stream**: Uses `promise.interrupt()` and callbacks
- **Room Recording**: Was using synchronous `promise.wait()` (now fixed)

### 3. **Transceiver Creation**
- **Single Stream**: Adds transceivers based on codec preferences
- **Room Recording**: Was adding generic transceivers before offer (now fixed)

### 4. **Data Channel**
- **Single Stream**: Creates data channel on connection
- **Room Recording**: Wasn't handling data channels (now added)

## The Real Issue

The ICE connection stays in `NEW` state, which means:
1. ICE candidates are being exchanged
2. But connectivity checks never start
3. This suggests the ICE agent isn't properly initialized

## Possible Root Causes

### 1. **Thread Safety**
Room recording creates WebRTC elements from the main thread but handles callbacks in GStreamer threads. This might cause initialization issues.

### 2. **Pipeline State**
The pipeline might need to be in PLAYING state before WebRTC negotiation starts.

### 3. **Multiple WebRTC Contexts**
Having multiple WebRTC elements in separate pipelines (instead of one pipeline) might cause issues with ICE agent initialization.

## Suggested Fix

The most likely fix is to use a **single pipeline with multiple webrtcbin elements** instead of separate pipelines for each stream:

```python
# Instead of:
recorder1 = { 'pipe': Gst.Pipeline(), 'webrtc': webrtcbin1 }
recorder2 = { 'pipe': Gst.Pipeline(), 'webrtc': webrtcbin2 }

# Use:
main_pipe = Gst.Pipeline()
main_pipe.add(webrtcbin1)
main_pipe.add(webrtcbin2)
```

This would ensure:
- Single GStreamer context
- Shared ICE agent
- Better thread management

## Alternative Approach

If the above doesn't work, consider using the multi_peer_client.py approach that was partially implemented - it handles multiple peer connections differently.

## Testing Single vs Multi

To confirm it's purely a multi-stream issue:
```bash
# Works:
python3 publish.py --room testroom123 --view tUur6wt --record single --password false --noaudio

# Fails:
python3 publish.py --room testroom123 --record-room --record multi --password false --noaudio
```

The code changes we made (promise handling, data channel support) are correct improvements, but the core issue appears to be architectural - how multiple WebRTC instances are managed.