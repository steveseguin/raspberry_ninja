#!/usr/bin/env python3
"""
Test ICE configuration fix for room recording
"""

import subprocess
import time
import re
import glob
import os

# Clean up
for f in glob.glob("ice_*.ts") + glob.glob("ice_*.mkv"):
    try:
        os.remove(f)
    except:
        pass

print("TESTING ICE CONFIGURATION FIX")
print("="*70)
print("This test verifies that room recording uses proper ICE servers")
print()

# Run with visible output
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'ice',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

start = time.time()
ice_events = []
connection_events = []

print("Monitoring output for 30 seconds...")
print("-"*70)

while time.time() - start < 30:
    line = proc.stdout.readline()
    if not line and proc.poll() is not None:
        break
        
    if line:
        # Remove ANSI codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        
        # Capture ICE-related events
        if any(x in clean for x in ['ICE', 'STUN', 'TURN', 'ice']):
            ice_events.append(clean)
            print(f"ICE: {clean}")
            
        # Capture connection events
        elif any(x in clean for x in ['Connection state', 'Answer created', 'Recording started']):
            connection_events.append(clean)
            print(f"CONN: {clean}")
            
        # Show errors
        elif 'ERROR' in clean or 'Failed' in clean:
            print(f"ERROR: {clean}")

# Stop process
proc.terminate()
proc.wait()

# Analysis
print("\n" + "="*70)
print("ANALYSIS:")
print("="*70)

# Check ICE configuration
ice_configured = any('STUN' in e or 'setup_ice_servers' in e for e in ice_events)
print(f"\nICE Servers Configured: {'✅ Yes' if ice_configured else '❌ No'}")

# Check connection progression  
states = [e for e in connection_events if 'Connection state' in e]
if states:
    print("\nConnection States:")
    for state in states:
        print(f"  {state}")
        
# Check final result
final_state = "UNKNOWN"
if states:
    if 'CONNECTED' in states[-1]:
        final_state = "✅ CONNECTED"
    elif 'FAILED' in states[-1]:
        final_state = "❌ FAILED"
        
print(f"\nFinal Connection State: {final_state}")

# Check recordings
files = glob.glob("ice_*.ts") + glob.glob("ice_*.mkv")
print(f"\nRecordings Created: {'✅ Yes' if files else '❌ No'}")
if files:
    for f in files:
        print(f"  {f}: {os.path.getsize(f):,} bytes")

# ICE gathering analysis
gathering_states = [e for e in ice_events if 'gathering state' in e.lower()]
if gathering_states:
    print("\nICE Gathering States:")
    for state in gathering_states[-3:]:
        print(f"  {state}")
        
# Recommendations
if final_state == "❌ FAILED":
    print("\nRECOMMENDATIONS:")
    print("1. Check network connectivity")
    print("2. Verify STUN servers are accessible") 
    print("3. Consider adding TURN server support")
    print("4. Check firewall/NAT configuration")