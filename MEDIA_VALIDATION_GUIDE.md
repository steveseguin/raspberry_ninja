# Media File Validation Guide

## Overview

The Raspberry Ninja project now includes comprehensive media file validation using GStreamer. This ensures that recorded files are not only created but are also valid, playable media files.

## Features

### 1. Automatic Validation in Tests

All recording tests now automatically validate output files to ensure:
- Files can be decoded properly
- Video frames are actually rendered
- File format matches expected codec (H.264→.ts, VP8/VP9→.mkv)
- No corruption or encoding errors

### 2. Validation Module (`validate_media_file.py`)

A standalone module that provides:
- Single file validation
- Batch validation for multiple files
- Detailed error reporting
- Frame counting and duration detection
- Format verification

### 3. GStreamer-Based Validation

Uses GStreamer pipelines to:
- Decode video streams
- Count decoded frames
- Verify container formats
- Detect encoding issues

## Usage

### Command Line Validation

```bash
# Validate a single file
python validate_media_file.py recording.ts

# Validate multiple files
python validate_media_file.py *.ts *.mkv

# Output example:
✅ recording_1234.ts is valid
   Frames: 450
   Duration: 15.02s
```

### In Python Code

```python
from validate_media_file import MediaFileValidator, validate_recording

# Simple validation
is_valid = validate_recording("my_recording.ts")

# Detailed validation
validator = MediaFileValidator()
is_valid, info = validator.validate_file("my_recording.ts")

if is_valid:
    print(f"Frames decoded: {info['frames_decoded']}")
    print(f"Duration: {info['duration_seconds']} seconds")
else:
    print(f"Error: {info['error']}")
```

### In Unit Tests

```python
def test_recording_with_validation(self):
    # Record something...
    recordings = self.find_recordings()
    
    # Validate all recordings
    all_valid, results = self.validate_recordings(recordings)
    self.assertTrue(all_valid, "Some recordings failed validation")
```

## Validation Process

1. **File Detection**: Identifies file format from extension
2. **Pipeline Creation**: Builds appropriate GStreamer decode pipeline
3. **Decoding**: Attempts to decode video frames
4. **Frame Counting**: Counts successfully decoded frames
5. **Error Detection**: Catches and reports any decoding errors
6. **Result Summary**: Returns validation status with details

## Supported Formats

- **MPEG-TS** (.ts) - H.264 video in transport stream
- **Matroska** (.mkv) - VP8/VP9 video
- **WebM** (.webm) - VP8/VP9 video
- **MP4** (.mp4) - H.264/H.265 video
- **Generic** - Attempts auto-detection for unknown formats

## Test Integration

### Updated Tests

The following tests now include media validation:
- `test_recording_validation.py` - Dedicated validation test suite
- `test_multi_peer_final.py` - Multi-peer recording validation
- `test_multi_stream_recording.py` - Multi-stream validation
- `test_validation_demo.py` - Interactive validation demo

### Running Validation Tests

```bash
# Run all validation tests
python test_recording_validation.py

# Run validation demo
python test_validation_demo.py

# Run with custom test runner
python run_all_tests.py
```

## Error Handling

Common validation errors and their meanings:

1. **"No frames decoded"** - File exists but contains no valid video
2. **"Failed to start pipeline"** - GStreamer cannot process the file format
3. **"Timeout waiting for frames"** - File may be corrupted or empty
4. **"Could not determine type of stream"** - Unknown or unsupported format

## Performance Considerations

- Validation timeout: Default 10 seconds per file
- Large files: Validation completes after decoding sufficient frames
- Memory usage: Minimal, as frames are discarded after counting
- CPU usage: Moderate during decoding

## Requirements

- GStreamer 1.0+ with plugins:
  - gst-plugins-base
  - gst-plugins-good
  - gst-plugins-bad (for some codecs)
  - gst-libav (for additional codec support)

## Troubleshooting

### GStreamer Not Found
```bash
# Ubuntu/Debian
sudo apt-get install gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good

# macOS
brew install gstreamer
```

### Missing Codec Support
```bash
# Install additional codecs
sudo apt-get install gstreamer1.0-libav gstreamer1.0-plugins-bad
```

### Validation Fails But File Plays
- Check if required GStreamer plugins are installed
- Try playing with: `gst-play-1.0 yourfile.ts`
- Check debug output: `GST_DEBUG=3 python validate_media_file.py yourfile.ts`

## Future Enhancements

Planned improvements:
- Audio validation support
- Bitrate verification
- Resolution detection
- Codec parameter validation
- Corruption recovery attempts
- Detailed quality metrics