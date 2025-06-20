# Combine Recordings Tool Documentation

## Overview

The `combine_recordings.py` tool is a utility for combining separate audio and video files that were recorded asynchronously. It uses intelligent timestamp-based synchronization to ensure perfect audio/video alignment, even when the streams started at different times.

## Why This Tool?

When recording WebRTC streams, audio and video are often saved to separate files due to:
- Different codec requirements (WebM for video, WAV for audio)
- Asynchronous stream initialization
- WebRTC negotiation delays (typically 400-600ms for video)
- Better compatibility with playback software

This tool solves the synchronization challenge by analyzing the actual stream timestamps and applying precise delays to maintain perfect A/V sync.

## Basic Usage

### Combine a Single Pair

```bash
# Combine specific video and audio files
python3 combine_recordings.py video.webm audio.wav output.mp4
```

### Automatic Batch Processing

```bash
# Automatically find and combine all matching audio/video pairs
python3 combine_recordings.py
```

## How It Works

1. **Timestamp Detection**: The tool reads the actual start timestamps from both files using FFprobe
2. **Synchronization Calculation**: It calculates the time difference between audio and video starts
3. **Intelligent Processing**: Based on the time difference, it applies one of several strategies:
   - **Direct merge** (< 1ms difference): Files are already in sync
   - **Audio delay**: Delays audio to match video start time
   - **Video delay**: For small differences, delays video using PTS adjustment
   - **Audio trim**: For larger differences, trims the beginning of audio

4. **H.264 Conversion**: VP8 video is automatically converted to H.264 for MP4 compatibility

## File Naming Convention

The tool expects files to follow this naming pattern:
- Video: `roomname_streamid_timestamp.webm`
- Audio: `roomname_streamid_timestamp_audio.wav`

The tool will match files where:
- Room name and stream ID are identical
- Timestamps are within 2 seconds of each other

## Example Output

```
=== Combine Audio/Video Recordings ===

Found 8 video and 8 audio files

Combining:
  Video: testroom_abc123_1750435387.webm
  Audio: testroom_abc123_1750435388_audio.wav
  Output: combined_abc123_1750435387.mp4
  Video start time: 0.433s
  Audio start time: 0.000s
  Strategy: Delaying audio by 433ms to sync with video
  ✅ Success! Output size: 497,775 bytes
  Duration: 19.200000s, Streams: 2
  ✅ Both video and audio tracks present
  Output start time: 0.000s
```

## Recording Setup for Best Results

When recording with `publish.py`, audio is enabled by default:

```bash
# Record room (audio is enabled by default)
python3 publish.py --room testroom --record-room --password false

# Record video only if needed
python3 publish.py --room testroom --record-room --noaudio
```

This will create:
- `.webm` files for video (VP8 codec)
- `.wav` files for audio (PCM audio) when audio is enabled

## Advanced Features

### Custom Output Settings

The tool uses these default encoding settings:
- Video: H.264 with `-preset fast -crf 23`
- Audio: AAC at 192 kbps
- Container: MP4

### Synchronization Strategies

1. **Perfect Sync** (< 1ms difference):
   - Files are merged directly without adjustment

2. **Small Delays** (< 5 seconds):
   - Audio delayed using `adelay` filter
   - Video delayed using `setpts` filter

3. **Large Delays** (> 5 seconds):
   - Beginning of audio is trimmed
   - Ensures files don't have long silence at start

## Troubleshooting

### Files Not Matching

**Problem**: "No matching audio for video.webm"

**Solution**: Check that:
- Stream IDs match between files
- Timestamps are within 2 seconds
- Audio files have the `_audio` suffix

### Sync Issues in Output

**Problem**: Audio/video still seem out of sync

**Solution**: The tool uses stream timestamps, not file creation times. If sync issues persist:
- Check the original files play correctly
- Verify the WebRTC recording didn't have sync issues
- Try recording with a more stable connection

### Conversion Failures

**Problem**: "Could not find tag for codec vp8 in stream #0"

**Solution**: This is why the tool converts VP8 to H.264. Ensure ffmpeg is installed with H.264 support.

## Requirements

- Python 3.7+
- ffmpeg with H.264 encoding support
- ffprobe (usually comes with ffmpeg)

## Performance Notes

- Re-encoding VP8 to H.264 uses CPU
- Processing time is roughly 1:1 with video duration on modern hardware
- Files are processed sequentially to avoid overwhelming the system
- Original files are preserved

## Integration with Room Recording

This tool is designed to work seamlessly with the room recording feature:

1. Record a room session:
   ```bash
   python3 publish.py --room meeting --record-room --audio
   ```

2. After recording stops, combine all files:
   ```bash
   python3 combine_recordings.py
   ```

3. Find your synchronized MP4 files:
   ```bash
   ls combined_*.mp4
   ```

## Future Enhancements

Potential improvements being considered:
- Support for more input/output formats
- GPU-accelerated encoding
- Real-time combination during recording
- Multi-track output support
- Subtitle/metadata preservation

## Tips for Best Results

1. **Stable Connection**: Record with a stable internet connection to minimize timestamp variations
2. **Disk Space**: Ensure sufficient space for both original files and combined output
3. **CPU Resources**: Close unnecessary applications during combination
4. **Test First**: Always test with a short recording before important sessions

## Getting Help

If you encounter issues:
1. Run with Python errors visible: `python3 -u combine_recordings.py`
2. Check that ffmpeg is properly installed: `ffmpeg -version`
3. Verify file formats: `ffprobe -v error -show_streams video.webm`
4. Visit the Discord support channel at https://discord.vdo.ninja