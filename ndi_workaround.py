#!/usr/bin/env python3
"""
Workaround for NDI combiner freezing issue
This creates a wrapper that monitors and restarts the NDI pipeline if it freezes
"""

import subprocess
import threading
import time
import sys
import os
import signal

class NDIMonitor:
    def __init__(self, command_args):
        self.command_args = command_args
        self.process = None
        self.last_buffer_count = 0
        self.same_count_checks = 0
        self.monitor_thread = None
        self.running = True
        
    def start(self):
        """Start the process and monitoring"""
        print(f"[NDI Monitor] Starting process with args: {' '.join(self.command_args)}")
        self.process = subprocess.Popen(
            self.command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self.monitor_output)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
        # Start checking thread
        self.check_thread = threading.Thread(target=self.check_frozen)
        self.check_thread.daemon = True
        self.check_thread.start()
        
    def monitor_output(self):
        """Monitor process output for buffer counts"""
        try:
            for line in self.process.stdout:
                print(line, end='')  # Pass through output
                
                # Look for buffer count in output
                if "buffers processed" in line:
                    try:
                        # Extract buffer count
                        parts = line.split("buffers processed")[0].split()
                        count = int(parts[-1])
                        self.last_buffer_count = count
                    except:
                        pass
                        
        except Exception as e:
            print(f"[NDI Monitor] Output monitoring error: {e}")
            
    def check_frozen(self):
        """Check if the process is frozen"""
        last_count = 0
        stuck_checks = 0
        
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            
            if self.last_buffer_count == last_count and self.last_buffer_count > 0:
                stuck_checks += 1
                print(f"\n[NDI Monitor] WARNING: Buffer count stuck at {self.last_buffer_count} (check {stuck_checks}/3)")
                
                if stuck_checks >= 3:
                    print("\n[NDI Monitor] ERROR: Process appears frozen, restarting...")
                    self.restart()
                    stuck_checks = 0
            else:
                stuck_checks = 0
                
            last_count = self.last_buffer_count
            
    def restart(self):
        """Restart the process"""
        print("[NDI Monitor] Terminating frozen process...")
        
        # Try graceful shutdown first
        if self.process:
            self.process.terminate()
            time.sleep(2)
            
            if self.process.poll() is None:
                print("[NDI Monitor] Force killing process...")
                self.process.kill()
                
        # Wait before restart
        print("[NDI Monitor] Waiting 30 seconds before restart (NDI cooldown)...")
        time.sleep(30)
        
        # Restart
        self.last_buffer_count = 0
        self.start()
        
    def run(self):
        """Run the monitor"""
        self.start()
        
        try:
            # Wait for process to complete
            self.process.wait()
        except KeyboardInterrupt:
            print("\n[NDI Monitor] Interrupted, shutting down...")
            self.running = False
            if self.process:
                self.process.terminate()
                

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 ndi_workaround.py <command> [args...]")
        print("Example: python3 ndi_workaround.py python3 publish.py --room-ndi --room test")
        sys.exit(1)
        
    # Pass through to the actual command
    command_args = sys.argv[1:]
    
    monitor = NDIMonitor(command_args)
    monitor.run()
    

if __name__ == "__main__":
    main()