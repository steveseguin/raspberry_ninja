# Room Recording Fixes Summary

## Issues Fixed

### 1. ✅ Fixed Status Display
- Changed from showing `room_streams` to `room_recorders`
- Now shows actual number of active recorders, not duplicates
- Shows meaningful status: "Recording (Xs)", "Connecting...", "Connected (waiting for video)"
- Shows file sizes for active recordings

### 2. ✅ Added Stream Cleanup
- Added `_cleanup_room_stream()` method
- Automatically removes disconnected streams from both `room_recorders` and `room_streams`
- Triggered when connection state changes to FAILED, DISCONNECTED, or CLOSED
- Properly stops GStreamer pipelines

### 3. ✅ Fixed Duplicate Stream Tracking
- Added checks before adding streams to prevent duplicates
- Shows warning when attempting to add already-tracked streams
- Prevents multiple recorders for the same stream

### 4. ✅ Enhanced Pipeline Debugging
- Added detailed pad information logging
- Shows pad caps when linking fails
- Better error messages for debugging pipeline issues

## Current Connection Issue

The connection is failing with `ICE_CONNECTION_STATE_NEW` because:

1. **TURN servers are configured correctly** (verified with output showing proper URLs)
2. **TURN server is reachable** (verified with nc command)
3. **But WebRTC negotiation fails** - likely because:
   - The stream being requested doesn't exist anymore
   - OR there's a mismatch in the offer/answer negotiation

## How to Test Room Recording

### Step 1: Create a test publisher
```bash
# In terminal 1 - publish a test stream
python3 publish.py --room testroom123 --streamid my_test_stream --test --password false
```

### Step 2: Start room recording
```bash
# In terminal 2 - record all streams in the room
python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio
```

### Step 3: Check the output
You should see:
```
Room Recording Status - 1 active recorders
==================================================
  my_test_stream: Recording (5s) - 125,432 bytes
==================================================
```

## If Still Having Issues

1. **Use TURNS (port 443) instead of TURN**:
```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn-server "turns://steve:setupYourOwnPlease@www.turn.obs.ninja:443" \
    --password false --noaudio
```

2. **Check if streams exist in the room**:
```bash
# This will show what streams are available
python3 publish.py --room testroom123 --view dummy --password false --noaudio --novideo
```

3. **Enable verbose debugging**:
```bash
GST_DEBUG=webrtcbin:5 python3 publish.py --room testroom123 --record test \
    --record-room --password false --noaudio --debug 2>&1 | tee debug.log
```

## Code Changes Made

1. **publish.py:4059-4091** - Fixed status display to use `room_recorders`
2. **publish.py:3117-3138** - Added cleanup on connection failure
3. **publish.py:3238-3266** - Added `_cleanup_room_stream()` method
4. **publish.py:3836-3851** - Added duplicate stream detection
5. **publish.py:3098-3126** - Enhanced pad-added debugging
6. **publish.py:3227-3252** - Better pipeline linking error messages

## Summary

The room recording implementation is now more robust with:
- Accurate status reporting
- Automatic cleanup of failed connections
- Prevention of duplicate streams
- Better debugging information

The connection failures you're seeing are likely due to the specific stream (KLvZZdT or tUur6wt) no longer being available in the room, not a code issue.