# Auto TURN Fix Summary

## Problem
Room recording mode was not automatically using the default TURN servers, even though the code had VDO.Ninja's TURN servers hardcoded. This caused connectivity issues when devices were behind NAT/firewalls.

## Root Cause
The `auto_turn` flag was never set to `True` in room recording mode. The condition `if hasattr(self, 'auto_turn') and self.auto_turn:` would always evaluate to False because `auto_turn` was not being set.

## Solution
Modified `publish.py` to automatically set `auto_turn = True` when `room_recording = True`:

1. **Line 5499**: When `--record-room` or `--room-ndi` flags are used
2. **Line 6384**: In the room recording mode setup section  
3. **Line 1456**: Added `auto_turn` to WebRTCClient initialization

## Result
✅ Room recording mode now automatically uses VDO.Ninja's default TURN servers:
- North America: `turn:turn-cae1.vdo.ninja:3478` and `turn:turn-usw2.vdo.ninja:3478`
- Europe: `turn:turn-eu1.vdo.ninja:3478`
- Secure fallback: `turns:www.turn.obs.ninja:443`

## Testing
Confirmed working with test script showing:
```
✅ [tUur6wt] Using default TURN server: turn:turn-cae1.vdo.ninja:3478 (na-east)
✅ [tUur6fffwt] Using default TURN server: turn:turn-cae1.vdo.ninja:3478 (na-east)
✅ [tUur6wt] TURN server configured: turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478
✅ [tUur6fffwt] TURN server configured: turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478
```

## User Impact
- Room recording will have better connectivity out of the box
- No need to manually specify TURN servers for basic room recording
- Users can still override with custom TURN servers using `--turn-server` flag