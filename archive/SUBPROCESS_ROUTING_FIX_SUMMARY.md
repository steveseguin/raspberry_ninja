# Subprocess WebRTC Routing Fix Summary

## Problem Identified
The original implementation had a race condition in the UUID mapping logic. When multiple streams joined a room, the system tried to match incoming offers to subprocesses by finding "unmapped" streams. This created ambiguity and failures when responses arrived out of order.

## Root Cause
1. UUID mapping was established AFTER receiving offers, not before sending play requests
2. The "unmapped streams" matching logic was fragile and prone to race conditions
3. Multiple concurrent connections had no deterministic way to route messages

## Solution Implemented

### 1. Reversed Mapping Direction
- Changed from `stream_id_to_uuid` to `uuid_to_stream_id`
- UUID mapping is now established BEFORE sending the play request
- Creates deterministic routing from the start

### 2. Pre-established Routing
```python
# When creating a subprocess recorder:
if uuid:
    self.uuid_to_stream_id[uuid] = stream_id  # Map BEFORE play request
    
# When receiving an offer:
stream_id = self.uuid_to_stream_id.get(UUID)  # Direct lookup, no guessing
```

### 3. Proper UUID Propagation
- `videoaddedtoroom` events now use the 'from' field to get peer UUID
- Initial room listing extracts UUID for each member
- UUID is passed to `create_subprocess_recorder` to establish mapping upfront

### 4. Simplified Message Routing
- Direct UUID lookup for all messages (SDP, ICE)
- No more complex "unmapped streams" logic
- Clear error messages when UUID mapping not found

## Benefits
1. **Eliminates Race Conditions**: UUID mapping exists before any WebRTC negotiation
2. **Deterministic Routing**: Every message has a clear destination
3. **Scalable**: Handles any number of concurrent streams reliably
4. **Debuggable**: Clear mapping visibility and error messages

## Testing Results
The system now correctly:
- Establishes UUID mappings before WebRTC negotiation
- Routes messages to the correct subprocess
- Handles multiple streams joining simultaneously
- Provides clear error messages for routing issues

The fragile guessing game has been replaced with a robust, deterministic routing system.