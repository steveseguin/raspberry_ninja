#!/usr/bin/env python3
"""
Demo script showing NDI room recording functionality
"""

import subprocess
import time
import sys
import signal
import threading

class NDIRoomDemo:
    def __init__(self):
        self.processes = []
        
    def cleanup(self):
        """Clean up all processes"""
        print("\nCleaning up...")
        for proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                proc.kill()
    
    def run_publisher(self, stream_id, room):
        """Run a test publisher"""
        cmd = [
            'python3', 'publish.py',
            '--test',
            '--room', room,
            '--streamid', stream_id,
            '--password', 'false'
        ]
        
        print(f"Starting publisher: {stream_id}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.processes.append(proc)
        return proc
    
    def run_ndi_recorder(self, room):
        """Run NDI recorder for the room"""
        cmd = [
            'python3', 'publish.py',
            '--room', room,
            '--room-ndi',
            '--password', 'false'
        ]
        
        print(f"Starting NDI recorder for room: {room}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        self.processes.append(proc)
        return proc
    
    def monitor_output(self, proc, duration=30):
        """Monitor NDI recorder output"""
        start_time = time.time()
        ndi_streams = set()
        subprocesses = 0
        
        while time.time() - start_time < duration:
            try:
                line = proc.stdout.readline()
                if not line:
                    break
                    
                line = line.strip()
                
                # Track NDI streams
                if 'ndi stream name:' in line.lower():
                    parts = line.split('ndi stream name:')
                    if len(parts) > 1:
                        stream_name = parts[1].strip()
                        ndi_streams.add(stream_name)
                        print(f"  ✓ NDI stream created: {stream_name}")
                
                # Track subprocess creation
                if 'creating subprocess' in line.lower():
                    subprocesses += 1
                    print(f"  ✓ Subprocess created for stream")
                
                # Show key events
                if any(word in line.lower() for word in ['connected audio to ndi', 'connected video to ndi', 'ndi output start']):
                    print(f"  📡 {line}")
                    
            except:
                break
        
        return ndi_streams, subprocesses
    
    def run_demo(self):
        """Run the complete demo"""
        print("=" * 70)
        print("NDI Room Recording Demo")
        print("=" * 70)
        print("This demo will:")
        print("1. Start 2 test video publishers in a room")
        print("2. Start NDI recording of the room")
        print("3. Each publisher will get its own NDI stream")
        print("=" * 70)
        
        room = "testroom_ndi_demo"
        
        # Start publishers
        print("\n🎬 Starting publishers...")
        self.run_publisher("publisher1", room)
        time.sleep(2)
        self.run_publisher("publisher2", room)
        time.sleep(3)
        
        # Start NDI recorder
        print("\n📹 Starting NDI recorder...")
        ndi_proc = self.run_ndi_recorder(room)
        
        # Monitor for 30 seconds
        print("\n📊 Monitoring NDI streams...")
        ndi_streams, subprocesses = self.monitor_output(ndi_proc, 30)
        
        # Results
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        print(f"✓ Publishers started: 2")
        print(f"✓ Subprocesses created: {subprocesses}")
        print(f"✓ NDI streams created: {len(ndi_streams)}")
        
        if ndi_streams:
            print("\nNDI streams available on network:")
            for stream in ndi_streams:
                print(f"  - {stream}")
        
        print("\n💡 Use an NDI viewer (like NDI Studio Monitor) to see the streams")
        print("💡 Each stream contains synchronized audio and video")
        
        print("\nPress Ctrl+C to stop the demo...")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

def main():
    demo = NDIRoomDemo()
    
    # Handle cleanup on exit
    def signal_handler(sig, frame):
        demo.cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        demo.run_demo()
    finally:
        demo.cleanup()

if __name__ == "__main__":
    main()