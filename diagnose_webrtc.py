#!/usr/bin/env python3
"""
Diagnose WebRTC issue
"""

import subprocess
import sys
import re
import time
import threading

def run_publish():
    """Run publish.py and capture output"""
    cmd = [
        sys.executable, 
        "publish.py",
        "--test",
        "--streamid", "5566281",
        "--password", "false",
        "--bitrate", "500",  # Lower bitrate
        "--width", "320",
        "--height", "240",
        "--framerate", "15"
    ]
    
    print("Starting publish.py with minimal settings...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # Pattern matching
    patterns = {
        'pipeline': re.compile(r'gst-launch.*'),
        'connected': re.compile(r'Peer connection established'),
        'ice': re.compile(r'ICE:.*'),
        'quality': re.compile(r'Network quality:.*'),
        'bitrate': re.compile(r'bitrate.*kbps', re.IGNORECASE),
        'error': re.compile(r'(error|failed|warning)', re.IGNORECASE),
        'stats': re.compile(r'(packets|bytes).*sent', re.IGNORECASE),
        'encoder': re.compile(r'vp8.*target-bitrate', re.IGNORECASE)
    }
    
    # Track events
    events = {
        'pipeline_created': False,
        'ice_connected': False,
        'peer_connected': False,
        'stats_received': 0,
        'errors': []
    }
    
    start_time = time.time()
    last_stats_time = start_time
    
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
                
            line = line.strip()
            if not line:
                continue
                
            # Print everything
            print(line)
            
            # Check patterns
            for name, pattern in patterns.items():
                if pattern.search(line):
                    if name == 'pipeline':
                        events['pipeline_created'] = True
                        print(f"\n>>> PIPELINE DETECTED <<<\n")
                    elif name == 'connected':
                        events['peer_connected'] = True
                        print(f"\n>>> PEER CONNECTED after {time.time()-start_time:.1f}s <<<\n")
                    elif name == 'ice' and 'established' in line.lower():
                        events['ice_connected'] = True
                        print(f"\n>>> ICE CONNECTED <<<\n")
                    elif name == 'quality':
                        events['stats_received'] += 1
                        current_time = time.time()
                        if current_time - last_stats_time > 10:
                            print(f"\n>>> STATS UPDATE #{events['stats_received']} after {current_time-start_time:.1f}s <<<")
                            print(f">>> Look for bitrate info in the lines above <<<\n")
                            last_stats_time = current_time
                    elif name == 'error':
                        events['errors'].append(line)
                        print(f"\n>>> ERROR/WARNING: {line} <<<\n")
                        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        process.terminate()
        process.wait()
        
    # Summary
    print("\n" + "="*60)
    print("DIAGNOSTIC SUMMARY")
    print("="*60)
    print(f"Test duration: {time.time()-start_time:.1f} seconds")
    print(f"Pipeline created: {events['pipeline_created']}")
    print(f"ICE connected: {events['ice_connected']}")
    print(f"Peer connected: {events['peer_connected']}")
    print(f"Stats updates received: {events['stats_received']}")
    print(f"Errors/warnings: {len(events['errors'])}")
    
    if events['errors']:
        print("\nErrors detected:")
        for err in events['errors'][:5]:  # Show first 5
            print(f"  - {err}")
    
    if not events['peer_connected']:
        print("\n⚠️ ISSUE: Peer connection was never established!")
        print("This explains why video bitrate is 0 - no WebRTC connection")
    elif events['stats_received'] == 0:
        print("\n⚠️ ISSUE: No stats were received!")
        print("The connection might be established but not transmitting")
    else:
        print("\n✓ Connection seems established")
        print("Check the output above for bitrate information")

if __name__ == "__main__":
    print("WebRTC Diagnostic Tool")
    print("=" * 60)
    print("This will help diagnose why video bitrate might be 0")
    print("View URL: https://vdo.ninja/?view=5566281&password=false")
    print("=" * 60)
    print()
    
    run_publish()