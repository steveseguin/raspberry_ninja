# Room Recording - Final Implementation

## What Was Implemented

I've successfully integrated multi-stream room recording directly into `publish.py` as a single script. No external modules needed.

## The Issue You Reported

From your output:
```
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_FAILED
[KLvZZdT] ICE state: GST_WEBRTC_ICE_CONNECTION_STATE_NEW
```

The WebRTC connection was failing because:
1. ICE candidates were being sent from a GStreamer thread without access to the asyncio event loop
2. ICE candidates might have been sent before having a valid session ID

## Fixes Applied

### 1. Thread-Safe ICE Handling (line ~2977)
```python
def _on_room_ice_candidate(self, webrtc, mlineindex, candidate, recorder):
    """Handle ICE candidate for room recording"""
    recorder['ice_candidates'].append((candidate, mlineindex))
    # Use thread-safe method to queue ICE candidates
    if self.event_loop:
        asyncio.run_coroutine_threadsafe(
            self.ice_queue.put((recorder['stream_id'], recorder['session_id'], candidate, mlineindex)),
            self.event_loop
        )
```

### 2. Event Loop Capture (line ~5706)
```python
c = WebRTCClient(args)
# Set the event loop reference for thread-safe operations
c.event_loop = asyncio.get_running_loop()
```

### 3. Improved ICE Processing (line ~3160)
```python
async def _process_ice_candidates(self):
    """Process ICE candidates from room recorders"""
    while True:
        stream_id, session_id, candidate, mlineindex = await self.ice_queue.get()
        
        # If no session yet, get it from recorder
        if not session_id and stream_id in self.room_recorders:
            session_id = self.room_recorders[stream_id].get('session_id')
        
        if session_id:
            # Send the ICE candidate
            await self.sendMessageAsync({...})
        else:
            # Re-queue if no session yet
            await asyncio.sleep(0.1)
            await self.ice_queue.put((stream_id, session_id, candidate, mlineindex))
```

### 4. Send Pending ICE After Answer (line ~3225)
```python
# After creating answer, send any pending ICE candidates
pending = recorder.get('ice_candidates', [])
if pending:
    printc(f"[{stream_id}] Sending {len(pending)} pending ICE candidates", "77F")
    for candidate, mlineindex in pending:
        if self.event_loop:
            asyncio.run_coroutine_threadsafe(
                self.ice_queue.put((stream_id, session_id, candidate, mlineindex)),
                self.event_loop
            )
    recorder['ice_candidates'] = []
```

### 5. Better STUN Server
Changed from Cloudflare to Google's STUN server which is more reliable:
```python
stun_server = 'stun://stun.l.google.com:19302'
webrtc.set_property('stun-server', stun_server)
```

### 6. Enhanced Debugging
Added ICE connection and gathering state monitoring to help diagnose issues.

## How to Use

```bash
python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio
```

This will:
1. Connect to room
2. Create separate WebRTC connection for each stream
3. Record each to: `myprefix_[streamID]_[timestamp].ts`

## Architecture

All in `publish.py`:
- `_add_room_stream()` - Adds new stream recorder
- `_create_stream_recorder()` - Creates GStreamer pipeline
- `_handle_room_message()` - Routes WebSocket messages
- `_handle_room_offer()` - Handles SDP negotiation
- `_process_ice_candidates()` - Async ICE processing
- Thread-safe ICE queue for cross-thread communication

## Summary

The implementation is complete with all fixes applied. The main issues were:
1. ✅ Fixed: ICE candidates from GStreamer thread
2. ✅ Fixed: Event loop access for asyncio operations
3. ✅ Fixed: ICE candidates sent before session established
4. ✅ Added: Better STUN server and debugging

The code should now work correctly for recording multiple streams from a room.