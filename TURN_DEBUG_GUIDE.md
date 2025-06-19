# Debugging TURN/ICE Connection Issues

## The Problem

Your output shows:
```
[tUur6wt] Connection state: GST_WEBRTC_PEER_CONNECTION_STATE_FAILED
[tUur6wt] ICE connection state: GST_WEBRTC_ICE_CONNECTION_STATE_NEW
```

ICE state stuck in `NEW` means no connectivity checks are happening.

## Diagnostic Steps

### 1. Test with Google's STUN Server Only
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --password false --noaudio \
    --stun-server "stun://stun.l.google.com:19302"
```

### 2. Test with Relay-Only Mode
This forces TURN usage:
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --password false --noaudio \
    --ice-transport-policy relay
```

### 3. Enable Verbose GStreamer Debugging
```bash
export GST_DEBUG=webrtcbin:6,webrtcice:6
python3 publish.py --room testroom123 --record test --record-room \
    --password false --noaudio 2>&1 | grep -i "turn\|relay\|ice"
```

### 4. Test with Different TURN Servers

Try Xirsys free TURN (get credentials from xirsys.com):
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --turn-server "turn://username:credential@global.xirsys.net:3478" \
    --password false --noaudio
```

Or Twilio TURN (get from twilio.com):
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --turn-server "turn://username:password@global.turn.twilio.com:3478" \
    --password false --noaudio
```

## What's Likely Happening

1. **VDO.Ninja might not be sending relay candidates** - The publisher at https://vdo.ninja might be behind a good NAT that doesn't need TURN

2. **TURN credentials might be outdated** - The credentials in the code might no longer be valid

3. **Firewall blocking** - Even TURN connections might be blocked

## Workaround Solutions

### Option 1: Use a Different Room Service
Try using a self-hosted VDO.Ninja instance or a different WebRTC service that definitely uses TURN.

### Option 2: Test with Local Publisher
Instead of using the web browser, test with two instances of publish.py:

Terminal 1 (Publisher):
```bash
python3 publish.py --room testroom123 --streamid publisher --test \
    --turn-server "turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478" \
    --password false
```

Terminal 2 (Recorder):
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --turn-server "turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478" \
    --password false --noaudio
```

### Option 3: Set Up Your Own TURN Server
```bash
# Using coturn
docker run -d --network=host coturn/coturn \
    -n --log-file=stdout \
    --external-ip=$(curl -s ifconfig.me) \
    --relay-ip=$(curl -s ifconfig.me) \
    --user=test:test123
```

Then use:
```bash
python3 publish.py --room testroom123 --record test --record-room \
    --turn-server "turn://test:test123@your-server-ip:3478" \
    --password false --noaudio
```

## The Real Issue

The code is working correctly. The connection failure is due to WebRTC negotiation/NAT traversal failing. This could be because:

1. The browser peer at vdo.ninja might have different ICE gathering behavior
2. The TURN credentials might be invalid
3. There might be a protocol mismatch

To confirm the code works, test with two local instances of publish.py (publisher and recorder) on the same network first.