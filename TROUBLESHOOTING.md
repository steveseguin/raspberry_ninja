# Troubleshooting Guide

## Common Issues and Solutions

### Segmentation Faults

**Problem:** The application crashes with a segmentation fault, especially with low buffer values.

**Solutions:**
1. Use a buffer value of at least 10ms (the application now enforces this minimum)
2. If using a USB HDMI capture device, try a powered USB hub
3. On Raspberry Pi, use the `--rpi` flag for better hardware support

### JPEG Decode Errors

**Problem:** Getting errors like "Failed to decode JPEG image" or "JPEG datastream contains no image"

**Solutions:**
1. These errors often indicate a faulty or incompatible USB capture device
2. Try reducing the resolution or framerate
3. Use a different USB port or a powered USB hub
4. If on Raspberry Pi, add the `--rpi` flag to use hardware-accelerated JPEG decoding

### Low Frame Rate (5fps instead of 25fps)

**Problem:** The stream runs at much lower framerate than specified

**Possible Causes:**
1. USB bandwidth limitations
2. CPU throttling due to heat
3. Network congestion
4. Corrupted frames causing pipeline stalls

**Solutions:**
1. Lower the resolution (e.g., use 720p instead of 1080p)
2. Ensure proper cooling for your device
3. Use wired Ethernet instead of WiFi
4. Try a different USB capture device

### RTP Session Warnings

**Problem:** Getting "Can't determine running time for this packet without knowing configured latency" warnings

**Solution:**
This is typically harmless but can be reduced by using a slightly higher buffer value (30-50ms instead of 20ms).

### Dynamic Bitrate Changes Not Working

**Problem:** Bitrate adjustment commands fail with certain encoders

**Solution:**
Some encoders (like v4l2h264enc) don't support dynamic bitrate changes. The application will now show a helpful message suggesting you restart with a different `--bitrate` value.

### WebSocket Connection Issues

**Problem:** "WEB SOCKETS CLOSED; retrying in 5s" messages

**Note:**
This doesn't affect active peer-to-peer connections. The WebSocket is only used for signaling, and the application will automatically reconnect.

### Room Recording Not Working

**Problem:** `--record-room` doesn't record any streams

**Solutions:**
1. Ensure you're using a VDO.Ninja-compatible server (not a custom relay server)
2. Verify participants have published streams (not just joined the room)
3. Check that the room name is correct
4. Custom websocket servers (using `--puuid`) don't support room recording

## Performance Optimization

### For Lowest Latency

1. **Use appropriate buffer size:** 30-50ms is a good balance between stability and latency
2. **Hardware encoding:** Use `--h264` with appropriate hardware support flags (`--rpi`, `--nvidia`)
3. **Wired connection:** Ethernet is more stable than WiFi
4. **Browser choice:** Firefox often has less buffering than Chrome
5. **Reduce resolution:** 720p will have lower latency than 1080p

### For Raspberry Pi Users

1. **Always use the `--rpi` flag** when available for hardware acceleration
2. **Proper cooling** is essential - consider an aluminum case or active cooling
3. **Use a quality power supply** - undervoltage can cause performance issues
4. **SD card speed** matters - use a Class 10 or better

### For USB Capture Devices

1. **Generic HDMI-to-USB adapters** often work but may have issues with corrupted frames
2. **Powered USB hubs** can help with power-hungry devices
3. **USB 2.0 vs 3.0:** Ensure your device supports the USB standard of your capture device
4. **Multiple devices:** Each USB controller has bandwidth limits

## Debug Mode

Run with `--debug` to see detailed GStreamer pipeline information:

```bash
python3 publish.py --debug --streamid YourStreamID
```

This will show:
- GStreamer debug messages
- Pipeline state changes
- Element errors
- Capability negotiations

## Checking Your Setup

### GStreamer Version
```bash
gst-launch-1.0 --version
```
Minimum recommended: 1.18 or higher

### Available Video Devices
```bash
v4l2-ctl --list-devices
```

### Raspberry Pi Model Detection
```bash
cat /proc/device-tree/model
```

### Check Available Encoders
```bash
# For H264 encoders
gst-inspect-1.0 | grep h264enc

# For VP8 encoders  
gst-inspect-1.0 | grep vp8enc

# For hardware decoders
gst-inspect-1.0 | grep -E "v4l2jpegdec|nvjpegdec"
```

## Getting Help

If you're still having issues:

1. Run with `--debug` and capture the full output
2. Note your hardware (device model, camera type, etc.)
3. Include the exact command you're running
4. Visit the Discord support channel with this information