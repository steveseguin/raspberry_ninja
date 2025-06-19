# TURN Server Troubleshooting Guide

## Current Status

The automatic TURN server configuration has been successfully implemented in `publish.py`. When using `--record-room`, TURN servers are automatically configured:

```bash
python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio
```

Output shows:
```
DEBUG: room_recording=True, checking for auto TURN
Using VDO.Ninja TURN: turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478 (auto-enabled for room recording)
DEBUG: Set TURN server on webrtc element: turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478
```

## Common Issues and Solutions

### 1. Connection Still Fails with TURN

If you see:
```
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_FAILED
[KLvZZdT] ICE connection state: GST_WEBRTC_ICE_CONNECTION_STATE_NEW
```

**Possible causes:**

a) **Stream not available**: The stream ID (e.g., KLvZZdT) might not exist in the room
   - Solution: Ensure there's an active publisher in the room

b) **Firewall blocking TURN**: Your network might block outbound connections to TURN servers
   - Solution: Check firewall rules for:
     - UDP port 3478 (TURN)
     - TCP port 3478 (TURN TCP)
     - TCP port 443 (TURNS)

c) **TURN credentials expired**: VDO.Ninja's public TURN servers might have changed credentials
   - Solution: Use your own TURN server or contact VDO.Ninja for updated credentials

### 2. Force TURN Usage (Relay-Only Mode)

To force all traffic through TURN servers:

```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --ice-transport-policy relay \
    --password false --noaudio
```

### 3. Use Custom TURN Server

If VDO.Ninja's servers don't work, use your own:

```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn-server "turn://username:password@your-turn-server.com:3478" \
    --password false --noaudio
```

### 4. Test TURN Connectivity

Test if TURN servers are reachable:

```bash
# Install turnutils
sudo apt-get install coturn-utils

# Test TURN
turnutils_uclient -u steve -w setupYourOwnPlease turn-cae1.vdo.ninja
```

### 5. Debug WebRTC Issues

Enable verbose GStreamer debugging:

```bash
GST_DEBUG=webrtcbin:5,webrtcice:5 python3 publish.py --room testroom123 \
    --record test --record-room --password false --noaudio 2>&1 | grep -i ice
```

## Setting Up Your Own TURN Server

If public TURN servers don't work, set up your own using coturn:

```bash
# Install coturn
sudo apt-get install coturn

# Edit /etc/turnserver.conf
listening-port=3478
fingerprint
lt-cred-mech
user=myuser:mypass
realm=mydomain.com
# Or use shared secret:
# use-auth-secret
# static-auth-secret=mysecret

# Start coturn
sudo systemctl start coturn
```

Then use:
```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn-server "turn://myuser:mypass@mydomain.com:3478" \
    --password false --noaudio
```

## Implementation Details

The TURN configuration is implemented in `setup_ice_servers()` method:

1. When `--record-room` is used, `room_recording=True` is set
2. `setup_ice_servers()` checks if `room_recording` is True
3. If true, it automatically configures VDO.Ninja's TURN servers
4. TURN URLs are formatted as `turn://username:password@host:port`
5. Each room recorder inherits the same ICE configuration

## Verification

To verify TURN is configured:

1. Look for: `Using VDO.Ninja TURN: turn://...` in the output
2. Check for: `DEBUG: Set TURN server on webrtc element: turn://...`
3. If using relay-only: `DEBUG: Set ICE transport policy: relay`

## Next Steps

If automatic TURN still doesn't work:

1. **Test with a known working stream**: Ensure the room has active publishers
2. **Use your own TURN server**: Public servers may have usage limits
3. **Check network connectivity**: Some corporate networks block all WebRTC
4. **Try TURNS (secure)**: Use port 443 which is rarely blocked:
   ```bash
   --turn-server "turns://username:password@turn-server.com:443"
   ```