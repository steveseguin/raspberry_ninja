# Room Recording Feature Documentation

## Overview

The room recording feature allows you to record all streams in a VDO.Ninja room to separate files. This is useful for recording multi-participant sessions where each participant's stream needs to be saved individually.

## Basic Usage

```bash
# Record all streams in a room
python3 publish.py --room MyRoomName --record-room

# Record specific streams only
python3 publish.py --room MyRoomName --record-room --record-streams "stream1,stream2,stream3"

# Output all room streams as NDI sources
python3 publish.py --room MyRoomName --room-ndi
```

## How It Works

When you join a room with `--record-room` enabled:

1. The script requests a list of all current participants in the room
2. For each participant's stream, it creates a separate recording pipeline
3. New participants who join later are automatically recorded
4. Each stream is saved to a file named: `{room_name}_{stream_id}_{timestamp}_{uuid}.ts`
5. Audio and video are muxed together in MPEG-TS format without transcoding

## Requirements

### Server Requirements

**Important:** Room recording requires a VDO.Ninja-compatible handshake server that:
- Tracks room membership
- Sends room listings when participants join
- Sends notifications when participants join/leave (`videoaddedtoroom`, `someonejoined` events)

The standard VDO.Ninja handshake servers support these features.

### Custom WebSocket Server Limitations

**Room recording will NOT work with custom websocket servers (`--puuid` mode) that:**
- Only relay messages between clients
- Don't track room membership
- Don't send room event notifications

If you're using a custom websocket server, you'll see warnings like:
```
Warning: Room recording requires a server that provides room listings
Custom websocket servers may not support this feature
```

## Output Files

- **Video Formats Supported:** H264, VP8 (direct mux, no transcoding)
- **Audio Format:** Opus
- **Container:** MPEG-TS (.ts files)
- **Naming Convention:** `{room_name}_{stream_id}_{timestamp}_{uuid[:8]}.ts`

## NDI Output Mode

With `--room-ndi`, each room participant's stream is output as a separate NDI source:
- NDI source names: `{room_name}_{stream_id}`
- Requires NDI plugin for GStreamer
- Video is decoded for NDI output (CPU intensive)

## Performance Considerations

- Each stream uses separate GStreamer pipelines
- Recording doesn't transcode (low CPU usage)
- NDI output requires decoding (high CPU usage)
- Network bandwidth: sum of all participants' bitrates

## Troubleshooting

### No streams are being recorded
- Ensure you're using a VDO.Ninja-compatible server
- Check that participants have published streams (not just joined)
- Verify the room name is correct

### Recording stops working for new participants
- Check for "cleanup" or "bye" messages in the console
- Ensure the server is sending proper event notifications

### Files are created but empty
- Check GStreamer pipeline errors in the console
- Verify the incoming codec is supported (H264/VP8)

### Custom websocket server issues
- Room recording is not supported with basic relay servers
- Consider using the standard VDO.Ninja infrastructure

## Example Scenarios

### Record a meeting
```bash
python3 publish.py --room BoardMeeting --record-room
```

### Record specific presenters only
```bash
python3 publish.py --room Conference --record-room --record-streams "presenter1,presenter2"
```

### Create an NDI monitoring wall
```bash
python3 publish.py --room Studio --room-ndi
```

## Technical Details

The implementation:
1. Monitors WebSocket messages for room events
2. Creates webrtcbin elements for each incoming stream
3. Attaches recording pipelines to the 'pad-added' signal
4. Manages cleanup when participants disconnect
5. Uses thread-safe data structures for room state