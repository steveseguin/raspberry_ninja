#!/usr/bin/env python3
"""
Test room recording with TURN servers
"""

import subprocess
import time
import sys
import re

print("TESTING ROOM RECORDING WITH TURN SERVERS")
print("="*70)
print("Using VDO.Ninja's public TURN servers")
print()

# VDO.Ninja's public TURN servers (from the backup list)
turn_servers = [
    {
        "url": "turn:turn-cae1.vdo.ninja:3478",
        "user": "steve",
        "pass": "setupYourOwnPlease"
    },
    {
        "url": "turn:turn-usw2.vdo.ninja:3478", 
        "user": "vdoninja",
        "pass": "theyBeSharksHere"
    },
    {
        "url": "turns:www.turn.obs.ninja:443",
        "user": "steve", 
        "pass": "setupYourOwnPlease"
    }
]

# Try each TURN server
for i, turn in enumerate(turn_servers):
    print(f"\nTest {i+1}: Using TURN server {turn['url']}")
    print("-"*60)
    
    # Build command
    cmd = [
        'python3', 'publish.py',
        '--room', 'testroom123',
        '--record', f'turn_test_{i}',
        '--record-room',
        '--password', 'false',
        '--noaudio',
        '--turn', turn['url'],
        '--turn-user', turn['user'],
        '--turn-pass', turn['pass']
    ]
    
    # Run test
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Monitor output
    start = time.time()
    success = False
    connection_states = []
    
    while time.time() - start < 20:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
            
        # Clean ANSI
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
        
        # Look for key events
        if "Recording started" in clean:
            success = True
            print(f"✅ SUCCESS: {clean}")
        elif "Connection state" in clean:
            connection_states.append(clean)
            print(f"   {clean}")
        elif "ERROR" in clean or "Failed" in clean:
            print(f"❌ {clean}")
    
    # Stop process
    proc.terminate()
    proc.wait()
    
    # Results
    if success:
        print(f"\n✅ TURN server {turn['url']} WORKS!")
        break
    else:
        print(f"\n❌ TURN server {turn['url']} failed")
        if connection_states:
            print(f"   Last state: {connection_states[-1]}")

# Final check
import glob
files = glob.glob("turn_test_*.ts") + glob.glob("turn_test_*.mkv")
print("\n" + "="*70)
if files:
    print(f"✅ SUCCESS! Found {len(files)} recordings:")
    for f in files:
        print(f"  {f}: {os.path.getsize(f):,} bytes")
else:
    print("❌ No recordings created with any TURN server")
    print("\nRecommendations:")
    print("1. Check firewall - ensure outbound connections are allowed")
    print("2. Try relay-only mode: add --ice-transport-policy relay")
    print("3. Check if behind corporate proxy/firewall")
    print("4. Consider setting up your own TURN server")