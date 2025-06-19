# TURN Server Support in Room Recording

## Automatic TURN Configuration

Room recording now **automatically uses VDO.Ninja's TURN servers** when needed. This solves the ICE connectivity issues that occur behind restrictive NATs/firewalls.

## How It Works

### 1. Automatic Mode (Default for Room Recording)
When using `--record-room`, TURN servers are automatically configured:

```bash
python3 publish.py --room testroom123 --record myprefix --record-room --password false --noaudio
```

Output will show:
```
Using VDO.Ninja TURN: turn:turn-cae1.vdo.ninja:3478 (auto-enabled for room recording)
```

### 2. Manual TURN Server
Override with your own TURN server:

```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --turn-server "turn://username:password@your-turn-server.com:3478" \
    --password false --noaudio
```

### 3. Force Relay Mode
Use only TURN (no direct connections):

```bash
python3 publish.py --room testroom123 --record myprefix --record-room \
    --ice-transport-policy relay \
    --password false --noaudio
```

## Default TURN Servers

The implementation includes VDO.Ninja's public TURN servers:

- **North America**
  - `turn:turn-cae1.vdo.ninja:3478` (Canada East)
  - `turn:turn-usw2.vdo.ninja:3478` (US West)

- **Europe**
  - `turn:turn-eu1.vdo.ninja:3478` (Germany)

- **Secure (TLS)**
  - `turns:www.turn.obs.ninja:443`

## Command Line Options

```
--turn-server URL       TURN server URL (turn(s)://username:password@host:port)
--stun-server URL       STUN server URL (stun://hostname:port)  
--ice-transport-policy  ICE transport policy (all or relay)
```

## Implementation Details

1. **setup_ice_servers()** method now:
   - Checks for manual TURN configuration first
   - Automatically uses VDO.Ninja TURN for room recording
   - Properly formats credentials in the URL

2. **Room recorders** inherit the same ICE configuration as the main connection

3. **Thread-safe** ICE candidate handling ensures proper WebRTC negotiation

## Troubleshooting

If connections still fail:

1. **Check TURN connectivity**:
   ```bash
   # Install turnutils
   sudo apt-get install coturn-utils
   
   # Test TURN
   turnutils_uclient -u steve -w setupYourOwnPlease turn-cae1.vdo.ninja
   ```

2. **Enable debug logging**:
   ```bash
   GST_DEBUG=webrtcbin:5,webrtcice:5 python3 publish.py --room testroom123 \
       --record test --record-room --password false --noaudio 2>&1 | grep -i turn
   ```

3. **Try different TURN servers** - network conditions vary by region

4. **Use relay-only mode** if behind very restrictive firewall

## Expected Behavior

With TURN properly configured:
```
[KLvZZdT] Using VDO.Ninja TURN: turn:turn-cae1.vdo.ninja:3478
[KLvZZdT] ICE gathering state: GATHERING
[KLvZZdT] Answer created successfully
[KLvZZdT] ICE connection state: CHECKING    ← Key difference!
[KLvZZdT] Connection state: CONNECTING
[KLvZZdT] ICE connection state: CONNECTED
[KLvZZdT] ✅ Recording started
```

The critical change is ICE moves from NEW → CHECKING → CONNECTED instead of staying in NEW state.