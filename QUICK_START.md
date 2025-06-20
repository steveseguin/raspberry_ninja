# Quick Start Guide

## Basic Publishing Examples

### Raspberry Pi with CSI Camera
```bash
# Basic streaming
python3 publish.py --rpicam --streamid MyStream

# With hardware acceleration (recommended)
python3 publish.py --rpicam --rpi --streamid MyStream

# Lower latency setup
python3 publish.py --rpicam --rpi --buffer 50 --nored --streamid MyStream
```

### USB HDMI Capture Device
```bash
# Auto-detect HDMI input
python3 publish.py --hdmi --streamid MyStream

# With specific resolution and framerate
python3 publish.py --hdmi --width 1280 --height 720 --framerate 30 --streamid MyStream

# Using libcamera (for generic devices)
python3 publish.py --libcamera --streamid MyStream
```

### Lowest Latency Configuration
```bash
# For wired connection with good network
python3 publish.py --hdmi --buffer 30 --nored --h264 --rpi --streamid MyStream

# View in browser with reduced buffering
# Open in Firefox: https://vdo.ninja/?view=MyStream&buffer=0
```

## Recording Examples

### Record a Single Stream
```bash
# Record remote stream to disk
python3 publish.py --record RemoteStreamID

# Record with custom bitrate
python3 publish.py --record RemoteStreamID --bitrate 4000
```

### Record Multiple Room Participants
```bash
# Record all participants in a room (audio and video by default)
python3 publish.py --room MyRoomName --record-room --password false

# Record video only (disable audio)
python3 publish.py --room MyRoomName --record-room --noaudio

# Record specific participants only
python3 publish.py --room MyRoomName --record-room --record-streams "alice,bob,charlie"

# Output room streams as NDI sources
python3 publish.py --room MyRoomName --room-ndi
```

### Combine Audio/Video Recordings
```bash
# After recording, combine the separate audio/video files
python3 combine_recordings.py

# Combine specific files
python3 combine_recordings.py video.webm audio.wav output.mp4
```

## Advanced Examples

### Multi-viewer Mode
```bash
# Allow multiple viewers of your stream
python3 publish.py --rpicam --multiviewer --streamid MyStream
```

### Custom Pipeline
```bash
# Use a test pattern
python3 publish.py --test --streamid TestStream

# Save while streaming
python3 publish.py --hdmi --save --streamid MyStream
```

### WHIP Output
```bash
# Stream to a WHIP endpoint
python3 publish.py --hdmi --whip "https://myserver.com/whip/endpoint"
```

### NDI Output (Receive)
```bash
# Receive VDO.Ninja stream and output as NDI
python3 publish.py --ndiout RemoteStreamID
```

## Troubleshooting Quick Fixes

### Poor Quality or Low FPS
```bash
# Reduce resolution
python3 publish.py --hdmi --width 1280 --height 720 --streamid MyStream

# Increase bitrate
python3 publish.py --hdmi --bitrate 4000 --streamid MyStream
```

### Connection Issues
```bash
# Use a different STUN server
python3 publish.py --hdmi --server "wss://wss2.vdo.ninja:443" --streamid MyStream

# Disable encryption for testing
python3 publish.py --hdmi --password false --streamid MyStream
```

### USB Device Issues
```bash
# List available devices
v4l2-ctl --list-devices

# Use specific device
python3 publish.py --v4l2 /dev/video0 --streamid MyStream

# With format specification
python3 publish.py --v4l2 /dev/video0 --format JPEG --streamid MyStream
```

## Performance Tips

1. **Always use hardware flags** when available: `--rpi`, `--nvidia`
2. **Wired > WiFi** for stability and lower latency
3. **Start with lower resolutions** (720p) and work up
4. **Monitor CPU temperature** on Raspberry Pi: `vcgencmd measure_temp`
5. **Use `--nored`** on good networks to reduce bandwidth by ~50%

## Viewing Your Stream

### In a Browser
```
https://vdo.ninja/?view=YourStreamID
```

### In OBS
1. Add Browser Source
2. URL: `https://vdo.ninja/?view=YourStreamID&scene`
3. Width: 1920, Height: 1080

### With Lower Latency
```
https://vdo.ninja/?view=YourStreamID&buffer=0
```

### Multiple Viewers
```
https://vdo.ninja/?view=YourStreamID&broadcast
```