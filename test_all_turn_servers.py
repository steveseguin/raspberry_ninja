#!/usr/bin/env python3
"""Test all available TURN servers"""

import subprocess
import time
import threading

# List of TURN servers from VDO.Ninja
turn_servers = [
    {
        'name': 'Canada East',
        'url': 'turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478'
    },
    {
        'name': 'US West',
        'url': 'turn://vdoninja:theyBeSharksHere@turn-usw2.vdo.ninja:3478'
    },
    {
        'name': 'Europe',
        'url': 'turn://steve:setupYourOwnPlease@turn-eu1.vdo.ninja:3478'
    },
    {
        'name': 'Secure TURNS',
        'url': 'turns://steve:setupYourOwnPlease@www.turn.obs.ninja:443'
    }
]

def test_turn_server(server):
    print(f"\nTesting {server['name']}: {server['url']}")
    print("-" * 70)
    
    cmd = [
        'python3', 'publish.py',
        '--room', 'testroom123',
        '--record', f"turn_test_{server['name'].replace(' ', '_')}",
        '--record-room',
        '--password', 'false',
        '--noaudio',
        '--turn-server', server['url']
    ]
    
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    # Monitor for 15 seconds
    connected = False
    ice_checking = False
    
    def monitor():
        nonlocal connected, ice_checking
        for _ in range(150):  # 15 seconds
            line = proc.stdout.readline()
            if not line:
                break
            
            if "ICE_CONNECTION_STATE_CHECKING" in line:
                ice_checking = True
                print("  ✅ ICE is checking candidates")
            elif "Recording started" in line:
                connected = True
                print("  ✅ Connection established!")
                break
            elif "Connection failed" in line:
                print("  ❌ Connection failed")
                break
            
            time.sleep(0.1)
    
    t = threading.Thread(target=monitor)
    t.start()
    t.join(timeout=15)
    
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except:
        proc.kill()
    
    return connected, ice_checking

print("Testing all available TURN servers...")
print("=" * 70)

results = []
for server in turn_servers:
    connected, checking = test_turn_server(server)
    results.append({
        'server': server['name'],
        'connected': connected,
        'ice_checking': checking
    })

print("\n" + "=" * 70)
print("Summary:")
for r in results:
    status = "✅ Connected" if r['connected'] else ("🔄 ICE Checking" if r['ice_checking'] else "❌ Failed")
    print(f"  {r['server']}: {status}")

print("\nRecommendations:")
if any(r['connected'] for r in results):
    print("✅ At least one TURN server works! Use that one.")
else:
    print("❌ No TURN servers connected. Possible issues:")
    print("  1. Firewall blocking outbound connections")
    print("  2. TURN server credentials may have changed")
    print("  3. Network issues preventing TURN connectivity")
    print("  4. The test stream 'KLvZZdT' might not be available")