# Multi-Peer Room Recording Implementation

## Summary

I've implemented a proper multi-peer recording system that uses a **single shared WebSocket connection** with **multiple WebRTC peer connections** for recording multiple streams in a room.

## Key Components

### 1. **multi_peer_client.py**
- `MultiPeerClient` class manages multiple WebRTC peer connections on a single WebSocket
- `StreamRecorder` class handles individual stream recording with its own WebRTC peer
- Proper message routing based on session IDs and stream IDs
- Each peer connection is completely independent for media handling

### 2. **Modified publish.py**
- Integrated multi-peer client when `room_recording` mode is active
- Routes signaling messages to the multi-peer client
- Maintains single WebSocket connection for all peers

## Architecture

```
┌─────────────────────┐
│   WebSocket         │
│   Connection        │  ← Single shared connection
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    │ MultiPeer   │
    │ Client      │  ← Message router
    └──────┬──────┘
           │
    ┌──────┴──────────────┬─────────────────┬─────────────────┐
    │                     │                 │                 │
┌───▼────┐         ┌─────▼────┐     ┌─────▼────┐     ┌─────▼────┐
│Stream  │         │Stream    │     │Stream    │     │Stream    │
│Recorder│         │Recorder  │     │Recorder  │     │Recorder  │
│(Alice) │         │(Bob)     │     │(Charlie) │     │(...)     │
└────┬───┘         └────┬─────┘     └────┬─────┘     └────┬─────┘
     │                  │                 │                 │
┌────▼───┐         ┌────▼─────┐     ┌────▼─────┐     ┌────▼─────┐
│WebRTC  │         │WebRTC    │     │WebRTC    │     │WebRTC    │
│Peer    │         │Peer      │     │Peer      │     │Peer      │
└────────┘         └──────────┘     └──────────┘     └──────────┘
```

## How It Works

1. **Single WebSocket**: The main `WebRTCClient` maintains one WebSocket connection to the signaling server

2. **Room Discovery**: When joining a room in recording mode, it discovers all streams

3. **Multi-Peer Creation**: For each stream, creates a separate `StreamRecorder` with its own WebRTC peer connection

4. **Message Routing**: The `MultiPeerClient` routes incoming signaling messages to the correct `StreamRecorder` based on session IDs

5. **Independent Recording**: Each stream is recorded to its own file with proper codec detection (H.264→.ts, VP8/VP9→.mkv)

## Key Benefits

- **Efficient**: Single WebSocket reduces connection overhead
- **Scalable**: Can handle many streams without WebSocket connection limits
- **Clean**: Each peer connection is isolated for proper stream handling
- **Correct**: Follows WebRTC architecture where each peer connection handles one stream

## Current Integration

The multi-peer client is integrated into the existing codebase:

1. When `handle_room_listing` is called with `room_recording=True`, it creates a `MultiPeerClient`
2. All signaling messages are routed through the multi-peer client
3. Each stream gets its own recording file

## Usage

Currently activated internally when:
- Using room recording mode (`room_recording=True`)
- The multi_peer_client.py module is available

To use with current command-line interface, you would need to modify the `--record-room` handling to use the multi-peer approach instead of spawning separate processes.

## Difference from Process Spawning

**Process Spawning Approach** (current --record-room):
- Creates separate OS processes for each stream
- Each process has its own WebSocket connection
- Higher resource usage but complete isolation

**Multi-Peer Approach** (implemented here):
- Single process, single WebSocket
- Multiple WebRTC peer connections
- More efficient, follows WebRTC best practices

Both approaches solve the fundamental issue that a single WebRTC peer connection cannot handle multiple incoming streams.