#!/usr/bin/env python3
"""
Debug script to show what's in WebRTC stats
"""

import asyncio
import sys
import time

async def monitor_output():
    """Monitor the output of publish.py and extract stats info"""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "publish.py",
        "--test",
        "--streamid", "5566281", 
        "--password", "false",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    print("Starting publish.py with test source...")
    print("Watch: https://vdo.ninja/?view=5566281&password=false")
    print("-" * 60)
    
    last_quality_time = 0
    stats_count = 0
    
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
                
            line = line.decode('utf-8').strip()
            
            # Print all output
            print(line)
            
            # Look for specific patterns
            if "Network quality:" in line:
                stats_count += 1
                current_time = time.time()
                if current_time - last_quality_time > 5:
                    print(f"\n[DEBUG] Stats updates received: {stats_count}")
                    last_quality_time = current_time
                    
            if "Full WebRTC stats structure:" in line:
                print("\n[DEBUG] *** FOUND STATS STRUCTURE - CHECK ABOVE ***\n")
                
            if "target-bitrate:" in line:
                print(f"\n[DEBUG] *** ENCODER INFO: {line} ***\n")
                
            if "Bitrate status:" in line or "Current bitrate:" in line:
                print(f"\n[DEBUG] *** BITRATE INFO: {line} ***\n")
                
    except asyncio.CancelledError:
        process.terminate()
        await process.wait()
        raise
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()

async def main():
    try:
        # Run for 30 seconds
        await asyncio.wait_for(monitor_output(), timeout=30)
    except asyncio.TimeoutError:
        print("\n[DEBUG] Test completed after 30 seconds")
    except KeyboardInterrupt:
        print("\n[DEBUG] Interrupted by user")

if __name__ == "__main__":
    asyncio.run(main())