# Room Recording Feature Documentation

## Overview

The room recording feature allows you to record all streams in a VDO.Ninja room to separate files. This is useful for recording multi-participant sessions where each participant's stream needs to be saved individually. By default, the system saves video and audio to separate files for maximum compatibility, which can then be combined using the `combine_recordings.py` tool.

## Basic Usage

```bash
# Record all streams in a room (audio and video by default)
# Note: --password false disables encryption. Without it, default password is used.
python3 publish.py --room MyRoomName --record-room --password false

# Record video only (disable audio)
python3 publish.py --room MyRoomName --record-room --noaudio --password false

# Record specific streams only
python3 publish.py --room MyRoomName --record-room --record-streams "stream1,stream2,stream3" --password false

# Output all room streams as NDI sources
python3 publish.py --room MyRoomName --room-ndi --password false
```

### Password/Encryption Behavior

- **Default**: If no `--password` flag is provided, encryption is enabled with default password `someEncryptionKey123`
- **Disable encryption**: Use `--password false` to disable encryption completely
- **Custom password**: Use `--password YourCustomPassword` to set a specific password

⚠️ **Important**: When passwords are enabled (default behavior):
- Stream IDs and room names are hashed
- WebRTC signaling messages are encrypted
- Dynamic resolution changes via data channel are not supported
- All participants must use the same password

## How It Works

When you join a room with `--record-room` enabled:

1. The script requests a list of all current participants in the room
2. For each participant's stream, it creates a separate recording pipeline
3. New participants who join later are automatically recorded
4. Files are saved with this naming convention:
   - Video: `{room_name}_{stream_id}_{timestamp}.webm`
   - Audio: `{room_name}_{stream_id}_{timestamp}_audio.wav`
5. Video is saved as WebM (VP8) and audio as WAV for maximum compatibility

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

### Default behavior (audio enabled):
- **Video:** WebM container with VP8 codec (`.webm`)
- **Audio:** WAV format with PCM audio (`.wav`)
- **Naming:** 
  - Video: `{room_name}_{stream_id}_{timestamp}.webm`
  - Audio: `{room_name}_{stream_id}_{timestamp}_audio.wav`

### When `--noaudio` is used:
- **Video Format:** WebM container with VP8 codec
- **File Extension:** `.webm`
- **Naming:** `{room_name}_{stream_id}_{timestamp}.webm`

### Combining Audio and Video:
After recording, use the `combine_recordings.py` tool to merge the separate audio/video files:
```bash
python3 combine_recordings.py
```
This creates synchronized MP4 files with H.264 video and AAC audio.

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
- **Check password settings**: Make sure all participants use the same password (or all use `--password false`)

### "New stream joined but had no UUID" error
- This typically happens with password/encryption mismatches
- Ensure all participants are using the same password setting
- Try disabling passwords with `--password false` for testing

### Recording stops working for new participants
- Check for "cleanup" or "bye" messages in the console
- Ensure the server is sending proper event notifications
- Verify password settings match across all participants

### Files are created but empty
- Check GStreamer pipeline errors in the console
- Verify the incoming codec is supported (H264/VP8)
- Ensure audio/video permissions are granted

### Custom websocket server issues
- Room recording is not supported with basic relay servers
- Consider using the standard VDO.Ninja infrastructure

## Example Scenarios

### Record a meeting (audio and video by default)
```bash
# Record with both audio and video (creates separate files)
python3 publish.py --room BoardMeeting --record-room --password false

# After recording, combine audio/video files
python3 combine_recordings.py
```

### Record video only
```bash
python3 publish.py --room BoardMeeting --record-room --noaudio
```

### Record specific presenters only
```bash
python3 publish.py --room Conference --record-room --record-streams "presenter1,presenter2"
```

### Create an NDI monitoring wall
```bash
python3 publish.py --room Studio --room-ndi
```

### Complete workflow for a podcast recording
```bash
# Step 1: Start recording all participants (audio is enabled by default)
python3 publish.py --room PodcastRoom --record-room --password false

# Step 2: Let the recording run for your session
# Press Ctrl+C to stop when done

# Step 3: Combine the audio/video files
python3 combine_recordings.py

# Step 4: Your synchronized MP4 files are ready!
ls combined_*.mp4
```

## Technical Details

The implementation:
1. Monitors WebSocket messages for room events
2. Creates webrtcbin elements for each incoming stream
3. Attaches recording pipelines to the 'pad-added' signal
4. Manages cleanup when participants disconnect
5. Uses thread-safe data structures for room state