#!/usr/bin/env python3
"""
Test the full room recording flow
"""

import subprocess
import sys
import time
import glob
import os

# Clean up
for f in glob.glob("flow_*.ts") + glob.glob("flow_*.mkv"):
    os.remove(f)

room = f"flowtest{int(time.time())}"

# Start publisher first
print(f"1. Starting publisher in room: {room}")
pub = subprocess.Popen([
    sys.executable, "publish.py",
    "--test", "--room", room,
    "--stream", "alice",
    "--noaudio", "--h264",
    "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Wait for it to connect
print("   Waiting for publisher to connect...")
for _ in range(30):
    line = pub.stdout.readline()
    if line and "WebSocket ready" in line:
        print("   ✅ Publisher connected")
        break

time.sleep(2)

# Now start recorder
print(f"\n2. Starting room recorder...")
rec = subprocess.Popen([
    sys.executable, "publish.py",
    "--room", room,
    "--record", "flow",
    "--record-room",
    "--noaudio",
    "--password", "false"
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# Monitor recorder output
print("\n3. Monitoring recorder output:")
start = time.time()
key_events = {
    "connected": False,
    "room_list": False,
    "multi_peer": False,
    "recording": False
}

while time.time() - start < 20:
    line = rec.stdout.readline()
    if not line:
        continue
        
    line = line.rstrip()
    
    # Check for key events
    if "WebSocket ready" in line:
        key_events["connected"] = True
        print("   ✅ Connected to WebSocket")
    elif "Room has" in line and "members" in line:
        key_events["room_list"] = True
        print(f"   ✅ {line}")
    elif "Multi-Peer Client" in line:
        key_events["multi_peer"] = True
        print(f"   ✅ {line}")
    elif "Will record" in line:
        print(f"   ✅ {line}")
    elif "Adding recorder" in line:
        print(f"   ✅ {line}")
    elif "Recording to:" in line or "Recording started" in line:
        key_events["recording"] = True
        print(f"   ✅ {line}")
    elif "ERROR" in line:
        print(f"   ❌ {line}")
    elif any(x in line for x in ["Creating pipeline", "Answer created", "ICE state", "Connection state"]):
        print(f"   → {line}")

# Stop processes
print("\n4. Stopping processes...")
rec.terminate()
pub.terminate()
time.sleep(3)

# Check results
print("\n5. Results:")
print(f"   Connected: {'✅' if key_events['connected'] else '❌'}")
print(f"   Room list received: {'✅' if key_events['room_list'] else '❌'}")
print(f"   Multi-peer client created: {'✅' if key_events['multi_peer'] else '❌'}")
print(f"   Recording started: {'✅' if key_events['recording'] else '❌'}")

# Check files
files = glob.glob("flow_*.ts") + glob.glob("flow_*.mkv")
if files:
    print(f"\n6. Files created:")
    for f in files:
        print(f"   ✅ {f} ({os.path.getsize(f):,} bytes)")
else:
    print(f"\n6. ❌ No files created")