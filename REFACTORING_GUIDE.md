# Refactoring Guide for Multi-Stream Support

## Overview
This guide explains how to refactor `publish.py` to support multiple concurrent WebRTC connections for room recording.

## Architecture Changes

### Current Architecture (Monolithic)
- Single `WebRTCClient` class handles everything
- Tight coupling between WebSocket handling and WebRTC connections
- One pipeline per client instance
- Session conflicts when handling multiple streams

### New Architecture (Modular)
- `WebRTCConnection`: Manages a single peer connection
- `ConnectionManager`: Manages multiple connections
- `RoomRecordingManager`: Specialized manager for room recording
- Separation of concerns between WebSocket and WebRTC

## Migration Steps

### Step 1: Extract WebRTC Logic
Move WebRTC-specific code from `WebRTCClient` to `WebRTCConnection`:

```python
# Before (in WebRTCClient)
def start_pipeline(self, UUID):
    if not self.multiviewer:
        if UUID in self.clients:
            # Complex logic mixed with WebRTC
            
# After (in WebRTCConnection)
def create_pipeline(self):
    # Clean, focused pipeline creation
```

### Step 2: Implement Connection Manager
Replace the `self.clients` dictionary with `ConnectionManager`:

```python
# Before
self.clients[UUID] = {
    'webrtc': webrtc_bin,
    'session': session,
    # ...
}

# After
await self.connection_manager.create_connection(uuid, stream_id, config)
```

### Step 3: Refactor Message Handling
Separate WebSocket message routing from WebRTC logic:

```python
# Before
if 'description' in msg:
    # Handle inline
    
# After
async def handle_description(self, msg, uuid):
    await self.connection_manager.handle_offer(uuid, msg['description'])
```

### Step 4: Update Room Recording
Use `RoomRecordingManager` for room-specific features:

```python
# Before
if self.room_recording:
    # Complex inline logic
    
# After
self.recording_manager = RoomRecordingManager(room_name)
await self.recording_manager.handle_room_listing(members)
```

## Benefits

1. **Modularity**: Each component has a single responsibility
2. **Testability**: Components can be unit tested independently
3. **Scalability**: Easy to add more connections without conflicts
4. **Maintainability**: Clear separation of concerns

## Testing Strategy

### Unit Tests
- Test each component in isolation
- Mock external dependencies (GStreamer, WebSocket)
- Verify component interactions

### Integration Tests
- Test full room recording flow
- Verify multiple concurrent connections
- Check recording output

## Backward Compatibility

To maintain compatibility:
1. Keep existing command-line interface
2. Map old parameters to new architecture
3. Provide migration warnings for deprecated features

## Example Usage

```python
# Create client with new architecture
client = RefactoredWebRTCClient({
    'room': 'myroom',
    'record_room': True
})

# Run room recording
await client.run()

# Get status
status = client.get_status()
print(f"Recording {status['room_status']['recording']} streams")
```

## Next Steps

1. Run unit tests: `python3 test_webrtc_components.py`
2. Test refactored client: `python3 publish_refactored.py`
3. Gradually migrate features from `publish.py`
4. Add integration tests for complex scenarios