#!/usr/bin/env python3
import subprocess
import time

# Run the command and capture output
proc = subprocess.Popen(
    ["python3", "publish.py", "--room", "testroom123999999999", "--record-room", "--password", "false", "--noaudio", "--debug"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

start_time = time.time()
timeout = 15  # 15 second timeout

try:
    while time.time() - start_time < timeout:
        line = proc.stdout.readline()
        if not line:
            break
        
        # Print lines about sessions
        if "Answer message includes session" in line or "WARNING: No session ID" in line:
            print(f"SESSION CHECK: {line.strip()}")
        elif "Sending SDP answer" in line:
            print(f"ANSWER: {line.strip()}")
        elif "Routing offer" in line and "session:" in line:
            print(f"OFFER: {line.strip()}")
            
except KeyboardInterrupt:
    pass
finally:
    proc.terminate()
    proc.wait()