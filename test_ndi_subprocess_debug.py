#!/usr/bin/env python3
"""
Test that NDI parameters are properly passed to subprocess
"""

import asyncio
import sys
import time
import json

async def test_ndi_subprocess():
    """Test NDI parameter passing to subprocess"""
    print("Testing NDI subprocess parameter passing...")
    
    # Run publish.py with room NDI
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'publish.py',
        '--room', 'testroom123999999999',
        '--room-ndi',
        '--password', 'false',
        '--debug',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    
    # Collect output
    start_time = time.time()
    found_config = False
    ndi_params_found = False
    
    try:
        while time.time() - start_time < 30:  # Run for 30 seconds
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
                if not line:
                    break
                line = line.decode('utf-8').strip()
                
                # Look for config being sent to subprocess
                if 'Creating subprocess with' in line:
                    print(f"\n✓ Found subprocess config line: {line}")
                
                # Look for JSON config dumps
                if line.startswith('{') and '"stream_id"' in line:
                    try:
                        config = json.loads(line)
                        print(f"\n✓ Found config JSON: {json.dumps(config, indent=2)}")
                        if 'room_ndi' in config:
                            print(f"  - room_ndi: {config['room_ndi']}")
                            ndi_params_found = True
                        if 'ndi_name' in config:
                            print(f"  - ndi_name: {config['ndi_name']}")
                    except:
                        pass
                
                # Look for NDI-related logs
                if any(keyword in line.lower() for keyword in ['ndi', 'room_ndi', 'ndi_name', 'config received']):
                    print(f"[{time.time()-start_time:.1f}s] {line}")
                    
                # Look for subprocess logs about received config
                if 'DEBUG: Config received:' in line:
                    print(f"\n✓ Subprocess received config: {line}")
                    if 'room_ndi=' in line:
                        found_config = True
                        
            except asyncio.TimeoutError:
                continue
                
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        proc.terminate()
        await proc.wait()
    
    print("\n" + "="*50)
    print("RESULTS:")
    print("="*50)
    print(f"✓ NDI parameters found in config: {ndi_params_found}")
    print(f"✓ Subprocess received NDI config: {found_config}")
    
    if not ndi_params_found:
        print("\n⚠️  NDI parameters were NOT passed to subprocess!")
        print("Check that the WebRTCSubprocessManager properly forwards room_ndi and ndi_name.")
    
    if not found_config:
        print("\n⚠️  Subprocess did NOT log receiving NDI config!")
        print("The subprocess may not be receiving or logging the NDI parameters correctly.")

if __name__ == "__main__":
    asyncio.run(test_ndi_subprocess())