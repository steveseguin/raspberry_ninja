#!/usr/bin/env python3
"""
Test NDI subprocess with verbose output
"""

import subprocess
import sys
import time
import os

# Set GST_DEBUG for more info
os.environ['GST_DEBUG'] = '2,ndi*:5'

def run_test():
    """Run NDI test with subprocess output"""
    cmd = [
        'python3', 'webrtc_subprocess_glib.py'
    ]
    
    # Create test config
    import json
    config = {
        'stream_id': 'test_stream',
        'mode': 'view',
        'room': 'testroom',
        'room_ndi': True,
        'ndi_name': 'TestSubprocessNDI',
        'record_audio': True
    }
    
    print("Testing subprocess with config:")
    print(json.dumps(config, indent=2))
    print("-" * 50)
    
    # Start subprocess
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Send config
    proc.stdin.write(json.dumps({"type": "config", **config}) + "\n")
    proc.stdin.flush()
    
    # Send a fake offer to trigger pipeline creation
    fake_offer = {
        "type": "sdp",
        "sdp_type": "offer",
        "sdp": "v=0\\r\\no=- 0 0 IN IP4 127.0.0.1\\r\\ns=-\\r\\nt=0 0\\r\\na=group:BUNDLE 0 1\\r\\nm=video 9 UDP/TLS/RTP/SAVPF 96\\r\\nc=IN IP4 0.0.0.0\\r\\na=rtcp:9 IN IP4 0.0.0.0\\r\\na=ice-ufrag:test\\r\\na=ice-pwd:test\\r\\na=sendrecv\\r\\na=mid:0\\r\\na=rtcp-mux\\r\\na=rtpmap:96 VP8/90000\\r\\nm=audio 9 UDP/TLS/RTP/SAVPF 111\\r\\nc=IN IP4 0.0.0.0\\r\\na=rtcp:9 IN IP4 0.0.0.0\\r\\na=ice-ufrag:test\\r\\na=ice-pwd:test\\r\\na=sendrecv\\r\\na=mid:1\\r\\na=rtcp-mux\\r\\na=rtpmap:111 opus/48000/2\\r\\n",
        "session_id": "test_session"
    }
    
    time.sleep(1)
    proc.stdin.write(json.dumps(fake_offer) + "\n")
    proc.stdin.flush()
    
    # Read output for 10 seconds
    start_time = time.time()
    while time.time() - start_time < 10:
        line = proc.stdout.readline()
        if not line:
            break
        print(line.strip())
    
    # Shutdown
    proc.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
    proc.stdin.flush()
    time.sleep(1)
    proc.terminate()
    proc.wait()
    
    print("\nTest complete")

if __name__ == "__main__":
    run_test()