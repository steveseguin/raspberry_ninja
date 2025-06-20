# Room Recording Connection Failure Diagnosis

## Issue Summary
Based on your output:
- ICE gathering completes successfully 
- 19 remote ICE candidates are received and added
- But ICE connection state stays in NEW
- Connection fails without ever attempting to connect

## Root Cause Analysis

### What's Working:
1. ✅ Offer/Answer exchange completes
2. ✅ Local ICE candidates are gathered and sent
3. ✅ Remote ICE candidates are received
4. ✅ Remote ICE candidates are added to webrtcbin

### What's Failing:
❌ ICE connection never transitions from NEW to CHECKING state

This indicates that despite adding remote candidates, the ICE agent isn't actually starting the connectivity checks.

## Potential Causes:

### 1. Timing Issue with ICE Candidates
ICE candidates might be added before both local and remote descriptions are set, causing them to be ignored.

### 2. STUN Server Accessibility  
Even though we're using setup_ice_servers(), the STUN server might not be accessible from your network.

### 3. Missing TURN Server
If you're behind a restrictive NAT/firewall, STUN alone isn't sufficient - you need TURN.

## Fixes Applied:

1. **Proper ICE Server Configuration** - Room recorders now use `setup_ice_servers()`
2. **Thread-Safe ICE Handling** - Using `asyncio.run_coroutine_threadsafe()`
3. **Session Management** - Better tracking of sessions for ICE routing
4. **Single ICE Candidate Support** - Added handling for individual ICE candidates
5. **Enhanced Debugging** - Better logging of ICE states

## Next Steps to Debug:

### 1. Test with TURN Server
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --turn "turn:your-turn-server.com:3478" \
    --turn-user username --turn-pass password \
    --password false --noaudio
```

### 2. Force TURN-only Mode
Add `--ice-transport-policy relay` to force TURN usage

### 3. Check Network
- Verify UDP ports are not blocked
- Test STUN connectivity: `stun-client stun.l.google.com`

### 4. Enable GStreamer Debug
```bash
GST_DEBUG=webrtcbin:6,webrtcice:6 python3 publish.py ...
```

## The Core Issue

The fact that ICE stays in NEW state despite having both local and remote candidates suggests either:
1. A fundamental WebRTC state machine issue
2. Network connectivity preventing ANY ICE checks
3. A timing issue where candidates are added at the wrong time

Given that regular recording works but room recording doesn't, the issue is likely in how we set up the WebRTC connection for room streams.