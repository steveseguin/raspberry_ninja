#!/usr/bin/env python3
"""
Debug ICE connectivity issues in room recording
"""

import asyncio
import sys
import os
import time
import re

sys.path.insert(0, '.')

# Set up arguments for room recording
sys.argv = [
    'publish.py',
    '--room', 'testroom123',
    '--record', 'debug',
    '--record-room',
    '--password', 'false',
    '--noaudio'
]

# Capture all output
output_lines = []
ice_events = []
connection_events = []

# Monkey patch print to capture output
original_print = print
def capture_print(*args, **kwargs):
    text = ' '.join(str(arg) for arg in args)
    output_lines.append(text)
    original_print(*args, **kwargs)
print = capture_print

async def run_test():
    """Run the test with timeout"""
    from publish import main
    
    try:
        # Run for 20 seconds
        await asyncio.wait_for(main(), timeout=20)
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        print(f"Error: {e}")

# Run the test
print("="*70)
print("ICE CONNECTIVITY DEBUG TEST")
print("="*70)

try:
    asyncio.run(run_test())
except:
    pass

# Restore print
print = original_print

# Analyze output
print("\n" + "="*70)
print("ANALYSIS")
print("="*70)

# Extract ICE-related events
for line in output_lines:
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line)
    
    if any(x in clean for x in ['ICE', 'ice', 'candidate', 'STUN']):
        ice_events.append(clean)
    if any(x in clean for x in ['Connection state', 'Answer', 'Recording']):
        connection_events.append(clean)

# ICE Analysis
print("\nICE EVENTS:")
print("-"*50)

# Check ICE candidate generation
local_candidates = [e for e in ice_events if 'Queued ICE candidate' in e or 'on_ice_candidate' in e]
remote_candidates = [e for e in ice_events if 'Added' in e and 'remote' in e]
sent_candidates = [e for e in output_lines if 'candidates' in e and 'message was sent' in e]

print(f"Local ICE candidates generated: {len(local_candidates)}")
print(f"Remote ICE candidates received: {len(remote_candidates)}")
print(f"ICE candidate messages sent: {len(sent_candidates)}")

# Show ICE gathering progression
gathering_states = [e for e in ice_events if 'gathering state' in e.lower()]
if gathering_states:
    print("\nICE Gathering Progression:")
    for state in gathering_states[:5]:  # First 5 states
        print(f"  {state}")

# Connection Analysis
print("\nCONNECTION EVENTS:")
print("-"*50)

for event in connection_events[-10:]:  # Last 10 events
    print(f"  {event}")

# Check for specific issues
print("\nDIAGNOSTICS:")
print("-"*50)

# Check if answer was created
answer_created = any('Answer created' in e for e in connection_events)
print(f"Answer created: {'✅ Yes' if answer_created else '❌ No'}")

# Check if ICE candidates were sent
ice_sent = any('candidates' in line and 'message was sent' in line for line in output_lines)
print(f"ICE candidates sent: {'✅ Yes' if ice_sent else '❌ No'}")

# Check session ID
session_events = [e for e in output_lines if 'session' in e.lower() and ('None' in e or 'null' in e)]
if session_events:
    print("\n⚠️  Session ID issues detected:")
    for event in session_events[:3]:
        print(f"  {event}")

# Check timing
print("\nTIMING ANALYSIS:")
answer_time = None
first_ice_time = None

for i, line in enumerate(output_lines):
    if 'Answer created' in line and not answer_time:
        answer_time = i
    if 'candidates' in line and 'message was sent' in line and not first_ice_time:
        first_ice_time = i
        
if answer_time and first_ice_time:
    if first_ice_time < answer_time:
        print("⚠️  ICE candidates sent BEFORE answer created!")
    else:
        print("✅ ICE candidates sent AFTER answer created")

# Final state
final_states = [e for e in ice_events if 'Connection state' in e]
if final_states:
    print(f"\nFinal state: {final_states[-1]}")

# Recommendations
print("\nRECOMMENDATIONS:")
if 'GST_WEBRTC_ICE_CONNECTION_STATE_NEW' in str(ice_events):
    print("- ICE connection never started checking")
    print("- Likely ICE candidates not reaching the other peer")
    print("- Check WebSocket message routing")
    print("- Verify session IDs match between answer and ICE candidates")