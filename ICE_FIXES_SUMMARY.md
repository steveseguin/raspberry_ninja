# Room Recording ICE Fixes - Complete Summary

## The Problem You Reported

```
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_FAILED
[KLvZZdT] ICE state: GST_WEBRTC_ICE_CONNECTION_STATE_NEW
```

The WebRTC connections for room recording were failing because:
1. They were using a hardcoded STUN server instead of the configured ICE servers
2. ICE candidates were being sent from GStreamer threads without proper event loop access
3. ICE candidates might be sent before session ID was available

## All Fixes Applied

### 1. Use Proper ICE Server Configuration (CRITICAL FIX)
```python
# OLD CODE:
webrtc.set_property('stun-server', 'stun://stun.cloudflare.com:3478')

# FIXED CODE:
# Ensure attributes exist for setup_ice_servers
if not hasattr(self, 'stun_server'):
    self.stun_server = None
if not hasattr(self, 'turn_server'):
    self.turn_server = None
if not hasattr(self, 'no_stun'):
    self.no_stun = False
if not hasattr(self, 'ice_transport_policy'):
    self.ice_transport_policy = None
    
self.setup_ice_servers(webrtc)  # Use same config as main connection
```

### 2. Thread-Safe ICE Candidate Handling
```python
def _on_room_ice_candidate(self, webrtc, mlineindex, candidate, recorder):
    recorder['ice_candidates'].append((candidate, mlineindex))
    if self.event_loop:
        asyncio.run_coroutine_threadsafe(
            self.ice_queue.put((recorder['stream_id'], recorder['session_id'], 
                               candidate, mlineindex)),
            self.event_loop
        )
```

### 3. Event Loop Capture in main()
```python
c = WebRTCClient(args)
c.event_loop = asyncio.get_running_loop()
```

### 4. Improved ICE Candidate Processing
```python
async def _process_ice_candidates(self):
    while True:
        stream_id, session_id, candidate, mlineindex = await self.ice_queue.get()
        
        # Get session from recorder if not provided
        if not session_id and stream_id in self.room_recorders:
            session_id = self.room_recorders[stream_id].get('session_id')
        
        if session_id:
            # Send ICE candidate with proper session
            await self.sendMessageAsync({...})
        else:
            # Re-queue if no session yet
            await asyncio.sleep(0.1)
            await self.ice_queue.put((stream_id, session_id, candidate, mlineindex))
```

### 5. Send Pending ICE Candidates After Answer
```python
# After creating answer, send any queued ICE candidates
pending = recorder.get('ice_candidates', [])
if pending:
    for candidate, mlineindex in pending:
        if self.event_loop:
            asyncio.run_coroutine_threadsafe(
                self.ice_queue.put((stream_id, session_id, candidate, mlineindex)),
                self.event_loop
            )
    recorder['ice_candidates'] = []
```

### 6. Enhanced ICE Monitoring
Added connections for:
- `notify::ice-connection-state`
- `notify::ice-gathering-state`

With detailed logging:
```python
def _on_room_connection_state(self, webrtc, pspec, recorder):
    state = webrtc.get_property('connection-state')
    printc(f"[{recorder['stream_id']}] Connection state: {state.value_name}", "77F")
    
    if state == GstWebRTC.WebRTCPeerConnectionState.FAILED:
        ice_state = webrtc.get_property('ice-connection-state')
        ice_gathering_state = webrtc.get_property('ice-gathering-state')
        printc(f"[{recorder['stream_id']}] ICE connection state: {ice_state.value_name}", "F00")
        printc(f"[{recorder['stream_id']}] ICE gathering state: {ice_gathering_state.value_name}", "F00")
        printc(f"[{recorder['stream_id']}] Connection failed - check STUN/TURN connectivity", "F00")
```

## Key Improvements

1. **Consistent ICE Configuration** - Room recorders now use the same ICE server setup as the main connection
2. **Thread Safety** - Proper handling of cross-thread communication
3. **Session Management** - ICE candidates only sent with valid session IDs
4. **Better Debugging** - Enhanced logging for ICE state transitions

## Usage

```bash
python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio
```

With TURN server (if needed):
```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn "turn:turnserver.com:3478?transport=tcp" \
    --turn-user myuser --turn-pass mypass \
    --password false --noaudio
```

## Expected Output After Fixes

```
[KLvZZdT] Using STUN server: stun://stun.l.google.com:19302
[KLvZZdT] ICE gathering state: GST_WEBRTC_ICE_GATHERING_STATE_GATHERING
[KLvZZdT] Answer created successfully
[KLvZZdT] Sending X pending ICE candidates
[KLvZZdT] ICE connection state: GST_WEBRTC_ICE_CONNECTION_STATE_CHECKING
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_CONNECTING
[KLvZZdT] ICE connection state: GST_WEBRTC_ICE_CONNECTION_STATE_CONNECTED
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_CONNECTED
[KLvZZdT] Video codec: H264
[KLvZZdT] Recording to: myprefix_KLvZZdT_1234567890.ts
[KLvZZdT] ✅ Recording started
```

The most critical fix was ensuring room recorders use `setup_ice_servers()` instead of a hardcoded STUN server.