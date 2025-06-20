# MKV Recording Renegotiation Fix

## Problem
The `webrtc_subprocess_mkv.py` file was establishing WebRTC connections but never receiving media pads. The connection would complete, data channel would open, but no video or audio streams would arrive.

## Root Cause
The MKV subprocess was missing critical data channel message handling logic. When VDO.Ninja sends a renegotiation offer through the data channel (containing the media tracks), the MKV subprocess was ignoring it completely. The `on_data_channel_message` method was just a stub that logged messages without processing them.

## Solution
Implemented the complete renegotiation handling logic from `webrtc_subprocess_glib.py`:

1. **Data Channel Message Parser**: Added JSON parsing to detect renegotiation offers and ICE candidates
2. **Renegotiation Handler**: Added `handle_renegotiation_offer` method to process offers safely
3. **Deferred Processing**: Added `try_pending_renegotiation` to handle offers when not in STABLE state
4. **Asynchronous SDP Handling**: Refactored to use promise callbacks instead of blocking `wait()`
5. **Bidirectional Data Channel**: Send answers and ICE candidates via data channel when available

## Key Changes

### 1. Enhanced `on_data_channel_message`
```python
def on_data_channel_message(self, channel, msg):
    # Now parses JSON messages
    # Detects 'description' field with type='offer'
    # Schedules renegotiation in main thread with GLib.idle_add
    # Also handles ICE candidates received via data channel
```

### 2. Added Renegotiation Methods
```python
def handle_renegotiation_offer(self, sdp_text):
    # Checks signaling state
    # Defers if not STABLE
    # Processes offer when safe

def try_pending_renegotiation(self):
    # Retry mechanism for deferred offers
    # Ensures proper state machine handling
```

### 3. Refactored SDP Handling
```python
def handle_offer(self, sdp_text):
    # Unified offer handling for both initial and renegotiation
    # Uses promise callbacks instead of blocking wait()
    
def on_offer_set(self, promise, _, user_data):
    # Callback when remote description is set
    
def on_answer_created(self, promise, _, user_data):
    # Callback when answer is created
    # Sends answer via data channel if available
```

### 4. Enhanced ICE Handling
```python
def on_ice_candidate(self, element, mline, candidate):
    # Now sends ICE candidates via data channel when open
    # Falls back to websocket path if needed
```

## Testing
Created `test_mkv_renegotiation.py` to verify the fix works correctly. The test:
- Connects to VDO.Ninja
- Establishes initial connection (data channel only)
- Waits for renegotiation with media tracks
- Verifies that video pads are received
- Checks that MKV file is created with data

## Result
The MKV subprocess now correctly:
1. Receives the renegotiation offer via data channel
2. Processes it to add media tracks to the connection
3. Receives pad-added events for video/audio
4. Records to MKV file successfully

The fix brings feature parity with the working `webrtc_subprocess_glib.py` implementation while maintaining the MKV muxing functionality.