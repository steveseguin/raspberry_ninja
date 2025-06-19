#!/usr/bin/env python3
"""
Test to trace exact message flow in room recording
"""

import subprocess
import time
import re
import json

print("TRACING MESSAGE FLOW FOR ROOM RECORDING")
print("="*70)

# Start the process
proc = subprocess.Popen([
    'python3', 'publish.py',
    '--room', 'testroom123',
    '--record', 'trace',
    '--record-room',
    '--password', 'false',
    '--noaudio'
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

# Track message flow
messages_sent = []
messages_handled = []
ice_events = []
start_time = time.time()

def parse_time():
    return f"{time.time() - start_time:6.2f}s"

# Read output
timeout = time.time() + 20
while time.time() < timeout:
    line = proc.stdout.readline()
    if not line:
        if proc.poll() is not None:
            break
        continue
    
    # Clean ANSI
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line.rstrip())
    
    # Track sent messages
    if "message was sent" in clean:
        t = parse_time()
        # Try to extract message content
        try:
            # Look for JSON in the line
            json_start = clean.find('{')
            if json_start >= 0:
                json_str = clean[json_start:]
                msg = json.loads(json_str)
                msg_type = msg.get('request', msg.get('type', 'unknown'))
                if 'description' in msg:
                    msg_type = f"description/{msg['description']['type']}"
                elif 'candidates' in msg:
                    msg_type = f"candidates({len(msg['candidates'])})"
                messages_sent.append((t, msg_type, msg.get('session', 'no-session')))
        except:
            messages_sent.append((t, "parse-error", ""))
    
    # Track handled messages  
    elif any(x in clean for x in ["Handling message", "Added remote ICE", "Setting remote desc"]):
        t = parse_time()
        messages_handled.append((t, clean))
    
    # Track ICE events
    elif "ICE" in clean:
        t = parse_time()
        ice_events.append((t, clean))

proc.terminate()
proc.wait()

# Analysis
print("\n" + "="*70)
print("MESSAGE FLOW ANALYSIS")
print("="*70)

print("\nMESSAGES SENT:")
for t, msg_type, session in messages_sent[:10]:
    print(f"{t} -> {msg_type} (session: {session[:20]}...)")

print("\nMESSAGES HANDLED:")
for t, event in messages_handled[:10]:
    print(f"{t} <- {event}")

print("\nICE EVENTS:")
for t, event in ice_events[:10]:
    print(f"{t} ** {event}")

# Check sequencing
print("\nSEQUENCE CHECK:")
answer_sent = next((m for m in messages_sent if "answer" in m[1]), None)
ice_sent = [m for m in messages_sent if "candidates" in m[1]]
ice_received = [m for m in messages_handled if "Added remote ICE" in m[1]]

if answer_sent:
    print(f"Answer sent at: {answer_sent[0]}")
    
if ice_sent:
    print(f"Local ICE sent: {len(ice_sent)} times")
    print(f"  First at: {ice_sent[0][0]}")
    
if ice_received:
    print(f"Remote ICE received: {len(ice_received)} times")
    print(f"  First at: {ice_received[0][0]}")
else:
    print("⚠️  NO REMOTE ICE CANDIDATES RECEIVED!")

# Session analysis
print("\nSESSION ANALYSIS:")
sessions = set(m[2] for m in messages_sent if m[2] and m[2] != 'no-session')
print(f"Unique sessions: {len(sessions)}")
for s in list(sessions)[:3]:
    print(f"  {s[:40]}...")

# Final diagnosis
print("\nDIAGNOSIS:")
if not ice_received:
    print("❌ Remote ICE candidates were never received/processed")
    print("   This explains why connection stays in NEW state")
    print("   Check WebSocket message routing for ICE candidates")