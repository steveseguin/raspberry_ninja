# Recording Usage Guide for VDO.Ninja Publisher

This guide explains how to use the recording features in `publish.py`, including single stream recording, room recording, and various output options.

## Table of Contents
- [Overview](#overview)
- [Recording Modes](#recording-modes)
- [Basic Usage Examples](#basic-usage-examples)
- [Supported Codecs and Formats](#supported-codecs-and-formats)
- [Room Recording](#room-recording)
- [Advanced Options](#advanced-options)
- [Common Issues and Troubleshooting](#common-issues-and-troubleshooting)
- [Tips for Best Results](#tips-for-best-results)
- [Limitations and Known Issues](#limitations-and-known-issues)

## Overview

The `publish.py` script offers several recording capabilities:
- **View and Record** (`--record`): Record an incoming stream to disk
- **Publish and Save** (`--save`): Publish a stream while saving a copy locally
- **Room Recording** (`--record-room`): Record all streams in a room to separate files
- **Selective Room Recording** (`--record-streams`): Record specific streams from a room

## Recording Modes

### 1. View and Record Mode (`--record`)
Records an incoming stream to disk without publishing. The system acts as a viewer that saves the stream.

```bash
# Record a specific stream
python3 publish.py --record streamID123
```

### 2. Publish and Save Mode (`--save`)
Publishes your local video/audio while simultaneously recording it to disk.

```bash
# Publish and save your webcam feed
python3 publish.py --streamid myStream --save
```

### 3. Room Recording Mode (`--record-room`)
Records all participants in a room to separate files.

```bash
# Record all streams in a room
python3 publish.py --room roomName123 --record-room
```

### 4. Selective Room Recording (`--record-streams`)
Records only specific streams from a room.

```bash
# Record specific streams from a room
python3 publish.py --room roomName123 --record-room --record-streams "stream1,stream2,stream3"
```

## Basic Usage Examples

### Recording a Single Stream

```bash
# Basic stream recording (will auto-detect codec)
python3 publish.py --record guestStreamID

# Record with specific view parameter
python3 publish.py --record guestStreamID --view guestStreamID

# Record without audio
python3 publish.py --record guestStreamID --noaudio
```

### Publishing and Saving

```bash
# Publish webcam and save to disk
python3 publish.py --streamid myStream --save

# Publish with H264 codec and save
python3 publish.py --streamid myStream --save --h264

# Publish with VP8 codec and save
python3 publish.py --streamid myStream --save --vp8
```

### Recording from a File Source

```bash
# Play a file and save the output
python3 publish.py --filesrc video.mp4 --streamid fileStream --save

# Record a stream while playing a file
python3 publish.py --filesrc background.mp4 --record otherStream
```

## Supported Codecs and Formats

### Video Codecs
- **H.264** (default): Hardware accelerated when available
- **VP8**: Software encoding, good compatibility
- **VP9**: Software encoding, better compression
- **AV1**: Auto-selects hardware or software encoder

### Audio Codecs
- **Opus**: Default audio codec, excellent quality and compression
- **PCM**: Uncompressed audio when needed

### Output Formats
| Codec | Container Format | File Extension |
|-------|-----------------|----------------|
| H.264 | MPEG-TS | .ts |
| VP8 | WebM | .webm |
| VP9 | Matroska | .mkv |
| AV1 | Matroska | .mkv |

### File Naming Convention
Files are automatically named with timestamps:
- Single stream: `streamID_timestamp.ext`
- Room recording: `roomName_streamID_timestamp_UUID.ext`

## Room Recording

### Basic Room Recording

```bash
# Record all participants in a room
python3 publish.py --room meetingRoom --record-room

# Join room as invisible recorder (no publishing)
python3 publish.py --room meetingRoom --record-room --novideo --noaudio
```

### Filtered Room Recording

```bash
# Record only specific participants
python3 publish.py --room meetingRoom --record-room --record-streams "presenter,guest1,guest2"

# Record room with custom server
python3 publish.py --room meetingRoom --record-room --hostname https://myserver.com/
```

### Room Recording with NDI Output

```bash
# Output all room streams to NDI instead of files
python3 publish.py --room meetingRoom --room-ndi
```

## Advanced Options

### Codec Selection

```bash
# Force specific codecs for recording
python3 publish.py --record streamID --h264  # Prefer H.264
python3 publish.py --record streamID --vp8   # Prefer VP8
python3 publish.py --record streamID --vp9   # Prefer VP9
python3 publish.py --record streamID --av1   # Auto-select AV1
```

### Quality Settings

```bash
# High quality recording with higher bitrate
python3 publish.py --streamid myStream --save --bitrate 8000

# Adjust video resolution
python3 publish.py --streamid myStream --save --width 1920 --height 1080

# Set framerate
python3 publish.py --streamid myStream --save --framerate 60
```

### Audio Configuration

```bash
# Record with specific audio settings
python3 publish.py --record streamID --channels 2 --samplerate 48000

# Disable audio recording
python3 publish.py --record streamID --noaudio

# Audio-only recording
python3 publish.py --record streamID --novideo
```

### Buffer and Latency

```bash
# Increase buffer for unreliable connections
python3 publish.py --record streamID --buffer 500

# Low latency mode
python3 publish.py --record streamID --buffer 50
```

## Common Issues and Troubleshooting

### 1. Recording Not Starting

**Problem**: Files are not being created
```bash
# Enable debug mode to see detailed information
python3 publish.py --record streamID --debug

# Check if stream exists
python3 publish.py --record streamID --view streamID --debug
```

### 2. Audio/Video Sync Issues

**Problem**: Audio and video are out of sync
```bash
# Increase buffer size
python3 publish.py --record streamID --buffer 400

# For severe sync issues, record streams separately
python3 publish.py --record streamID --novideo  # Audio only
python3 publish.py --record streamID --noaudio  # Video only
```

### 3. Incomplete Files

**Problem**: Recording files are corrupted or incomplete
- Always stop recording gracefully with Ctrl+C
- Check disk space before recording
- Use `--debug` to monitor recording status

### 4. High CPU Usage

**Problem**: Recording causes high CPU usage
```bash
# Use hardware encoding when available
python3 publish.py --streamid myStream --save --h264

# Reduce resolution
python3 publish.py --streamid myStream --save --width 1280 --height 720

# Lower framerate
python3 publish.py --streamid myStream --save --framerate 30
```

### 5. No Audio in Recording

**Problem**: Video records but audio is missing
```bash
# Check audio permissions
python3 publish.py --streamid myStream --save --audiodevice hw:0 --debug

# List available audio devices
python3 publish.py --audiodevice ?
```

## Tips for Best Results

### 1. Pre-Recording Checklist
- Ensure sufficient disk space (1GB per 10 minutes at default quality)
- Test with a short recording first
- Verify audio/video sources are working
- Close unnecessary applications to free resources

### 2. Optimal Settings by Use Case

**Presentations/Screenshare**:
```bash
python3 publish.py --streamid presentation --save --h264 --framerate 30 --bitrate 4000
```

**High-Motion Content**:
```bash
python3 publish.py --streamid gaming --save --h264 --framerate 60 --bitrate 8000
```

**Long Recordings**:
```bash
python3 publish.py --streamid lecture --save --vp8 --framerate 25 --bitrate 2000
```

**Audio Podcasts**:
```bash
python3 publish.py --streamid podcast --save --novideo --channels 2
```

### 3. Storage Management
- H.264 files (.ts) can be concatenated: `cat file1.ts file2.ts > combined.ts`
- VP8/WebM files are more compressed but harder to edit
- Consider post-processing with ffmpeg for smaller files

### 4. Network Considerations
- Use `--buffer` to handle network jitter
- Wired connections are more reliable than WiFi
- Monitor CPU and network usage during recording

## Limitations and Known Issues

### Current Limitations

1. **No Pause/Resume**: Recordings cannot be paused and resumed
2. **No Live Format Switching**: Codec must be chosen before recording starts
3. **Limited Edit Features**: No built-in trimming or editing capabilities
4. **Single File Output**: Each stream creates one continuous file
5. **No Automatic Retry**: Failed recordings must be manually restarted

### Known Issues

1. **Room Recording Compatibility**:
   - May not work with custom WebSocket servers
   - Requires server support for room membership tracking
   - Cannot filter by codec in room recording mode

2. **File Format Limitations**:
   - MPEG-TS files may have compatibility issues with some players
   - WebM files cannot include H.264 video
   - No MP4 container support (use post-processing if needed)

3. **Resource Constraints**:
   - Multiple simultaneous recordings can overwhelm CPU
   - Hardware encoding limited by GPU capabilities
   - Large rooms may cause memory issues

4. **Platform-Specific Issues**:
   - Raspberry Pi may struggle with high-resolution recording
   - Some ARM devices lack hardware encoding support
   - Windows may require additional codecs

### Workarounds

**Converting to MP4**:
```bash
# Convert recorded file to MP4
ffmpeg -i recording.ts -c copy output.mp4
ffmpeg -i recording.webm -c copy output.mp4
```

**Merging Audio/Video**:
```bash
# If recorded separately
ffmpeg -i video.ts -i audio.ts -c copy merged.mp4
```

**Reducing File Size**:
```bash
# Re-encode with lower bitrate
ffmpeg -i large_recording.ts -c:v libx264 -crf 23 -c:a aac compressed.mp4
```

## Getting Help

For additional support:
1. Run with `--debug` flag for detailed logging
2. Check system logs for GStreamer errors
3. Ensure all dependencies are properly installed
4. Visit the VDO.Ninja community forums

Remember to always test your recording setup before important sessions!