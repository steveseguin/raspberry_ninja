# Room Recording TURN Server Solution

## The Problem
Your ICE connection is failing with state `GST_WEBRTC_ICE_CONNECTION_STATE_NEW`, which means:
- ICE candidates are exchanged but no connectivity checks are happening
- This typically indicates all STUN-based candidates failed
- You likely need TURN servers to relay the media

## Quick Solution - Use VDO.Ninja's TURN Servers

### Option 1: Basic TURN (UDP)
```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn "turn:turn-cae1.vdo.ninja:3478" \
    --turn-user "steve" \
    --turn-pass "setupYourOwnPlease" \
    --password false --noaudio
```

### Option 2: Secure TURN (TCP/TLS)
```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn "turns:www.turn.obs.ninja:443" \
    --turn-user "steve" \
    --turn-pass "setupYourOwnPlease" \
    --password false --noaudio
```

### Option 3: Force Relay Mode (TURN only)
```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn "turn:turn-usw2.vdo.ninja:3478" \
    --turn-user "vdoninja" \
    --turn-pass "theyBeSharksHere" \
    --ice-transport-policy relay \
    --password false --noaudio
```

## Available VDO.Ninja TURN Servers

From the code you provided, here are the public servers:

### North America
- `turn:turn-cae1.vdo.ninja:3478` (Canada East)
- `turn:turn-usw2.vdo.ninja:3478` (US West)
- `turn:turn-use1.vdo.ninja:3478` (US East)

### Europe
- `turn:turn-eu1.vdo.ninja:3478` (Germany)
- `turn:turn-eu2.obs.ninja:3478` (France)
- `turn:turn-eu4.vdo.ninja:3478` (Poland)
- `turn:www.turn.vdo.ninja:3478` (Germany)

### Secure (TCP/TLS)
- `turns:www.turn.obs.ninja:443`
- `turns:turn.obs.ninja:443`
- `turns:www.turn.vdo.ninja:443`

## Implementation in publish.py

The TURN configuration needs to be applied to each room recorder. With the fixes I've applied:

1. **setup_ice_servers()** is called for each recorder
2. TURN servers from command line are properly configured
3. ICE transport policy is respected

## Testing TURN Connectivity

### 1. Test TURN server directly:
```bash
# Install turnutils-client
sudo apt-get install coturn-utils

# Test TURN
turnutils_uclient -u steve -w setupYourOwnPlease turn-cae1.vdo.ninja
```

### 2. Enable WebRTC debugging:
```bash
GST_DEBUG=webrtcbin:6,webrtcice:6 python3 publish.py \
    --room testroom123 --record test --record-room \
    --turn "turn:turn-cae1.vdo.ninja:3478" \
    --turn-user "steve" --turn-pass "setupYourOwnPlease" \
    --password false --noaudio 2>&1 | grep -i "relay"
```

## If TURN Still Doesn't Work

### 1. Check Firewall
Ensure these are allowed:
- Outbound TCP 443 (for TURNS)
- Outbound UDP 3478 (for TURN)
- Outbound TCP 3478 (for TURN TCP)

### 2. Try Different Regions
Use a TURN server geographically closer to you

### 3. Set Up Your Own TURN
```bash
# Install coturn
sudo apt-get install coturn

# Basic config (/etc/turnserver.conf)
listening-port=3478
fingerprint
use-auth-secret
static-auth-secret=your-secret-here
realm=yourdomain.com
```

## Expected Output with TURN

When working correctly:
```
[KLvZZdT] ICE gathering state: GST_WEBRTC_ICE_GATHERING_STATE_GATHERING
[KLvZZdT] Answer created successfully
[KLvZZdT] Sending X pending ICE candidates
[KLvZZdT] Added 19 remote ICE candidates
[KLvZZdT] ICE connection state: GST_WEBRTC_ICE_CONNECTION_STATE_CHECKING  <-- This is key!
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_CONNECTING
[KLvZZdT] ICE connection state: GST_WEBRTC_ICE_CONNECTION_STATE_CONNECTED
[KLvZZdT] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_CONNECTED
[KLvZZdT] ✅ Recording started
```

The key difference is ICE should transition to CHECKING state, not stay in NEW.

## Summary

Your issue is almost certainly due to network restrictions requiring TURN servers. The code is working correctly, but the peer-to-peer connection cannot be established without relay servers. Use the VDO.Ninja TURN servers above and the connection should succeed.